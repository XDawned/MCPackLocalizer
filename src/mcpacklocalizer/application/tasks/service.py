# [Module: mcpacklocalizer.application.tasks.service] [Status: 开发中] [Brief: 不依赖 Qt 的扫描、翻译、续跑、审核与补丁应用服务]
from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict
from pathlib import Path

import httpx

from ...core.formats.languages import backfill_language, convert_language, extract_language
from ...core.kubejs.javascript import split_translation
from ...core.mods.combined import merge_mod_scan, mod_scan
from ...core.mods.i18n import attach_i18n, attach_local
from ...core.mods.library import ModLibrary, publish_scan, reuse_library
from ...core.mods.scan import write_report
from ...core.mods.tasks import (
    annotate_reuse,
    coverage,
    create_mod_scan,
    validate_mod_snapshot,
    validate_mod_translation,
)
from ...core.pack.extraction import Scan, resource_exclusions, scan_pack
from ...core.pack.patch import build_patch, validate_output, validate_sources
from ...core.pack.scopes import recognition_scopes
from ...core.pack.snapshots import Store, atomic_write, load_snapshot, reuse_baseline
from ...core.translation.api import ApiClient, validate_api_config
from ...core.translation.local import ModelConfig, WorkerClient, quality_warnings, validate_entry
from ...core.translation.rules import NoTranslate
from ...core.translation.script import ScriptApiClient
from ...paths import migrated_path
from ...runtime import inference_python
from ..config.settings import validate_glossary
from .jobs import Job
from .polishing import accept_polishing, run_polishing


def config_for(args, saved=None):
    values = asdict(ModelConfig())
    if saved:
        values.update({key: value for key, value in saved.items() if key in values})
    for key in values:
        if key == "overrides":
            continue
        value = getattr(args, key, None)
        if value is not None:
            values[key] = value
    if args.glossary_overrides is not None:
        values["overrides"] = args.glossary_overrides
    if args.no_glossary:
        values["glossary"] = values["overrides"] = None
        values["glossary_inline"] = "{}"
    if args.request_timeout is None and (not saved or "request_timeout" not in saved):
        values["request_timeout"] = args.timeout
    for key in ("glossary", "overrides"):
        if values.get(key):
            values[key] = migrated_path(values[key])
    if values["threads"] < 0 or values["gpu_layers"] < -1 or values["context_size"] < 256:
        raise ValueError("threads、gpu-layers 或 context-size 无效")
    if values["max_tokens"] < 1 or values["term_tokens"] < 0 or args.timeout <= 0:
        raise ValueError("token 上限和超时必须为正数（term-tokens 可为零）")
    if not 1 <= values["concurrency"] <= 32 or not 0 <= values["retries"] <= 10 or not 0 <= values["request_interval"] <= 60:
        raise ValueError("concurrency、retries 或请求间隔无效")
    validate_glossary(values["glossary_inline"])
    config = ModelConfig(**values)
    if config.engine == "api":
        validate_api_config(config)
    elif config.engine != "local":
        raise ValueError("未知翻译引擎")
    return config


def translation_client(config, args, log_path=None):
    if config.engine == "api":
        return ApiClient(config, args.credentials, config.request_timeout)
    return WorkerClient(config, args.runtime_python, args.timeout, log_path)


def translation_results(model, pending, cache, config):
    """Bounded requests; duplicate text/context shares one result. Only caller writes SQLite."""
    grouped = {}
    rules = NoTranslate(config.non_translate)
    for entry in pending:
        grouped.setdefault((entry.source, entry.context), []).append(entry)

    def translate(key):
        try:
            candidate = cache.get(key)
            if candidate is not None:
                try:
                    for entry in grouped[key]:
                        validate_entry(entry, candidate, config.allow_missing_placeholders)
                        if entry.script:
                            split_translation(key[0], candidate)
                    rules.validate(key[0], candidate)
                    return candidate, None
                except ValueError:
                    pass
            entry = grouped[key][0]
            if entry.patchouli:
                from ...core.patchouli.text import translate_text
                return translate_text(model, *key, entry.patchouli.get("macros", ())), None
            return model.translate(*key), None
        except (ValueError, RuntimeError, OSError) as exc:
            return None, str(exc)

    if config.engine == "local" or config.concurrency == 1:
        for key, entries in grouped.items():
            yield entries, translate(key)
        return
    remaining = iter(grouped.items())
    with ThreadPoolExecutor(max_workers=config.concurrency) as pool:
        active = {}

        def submit():
            item = next(remaining, None)
            if item is not None:
                key, entries = item
                active[pool.submit(translate, key)] = entries

        for _ in range(config.concurrency):
            submit()
        while active:
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                entries = active.pop(future)
                yield entries, future.result()
                submit()


def export_task(store, args):
    scan = store.export()
    manifest = build_patch(scan, store.output, args.allow_partial, args.replace_existing_locale)
    store.metadata(scan)
    store.export()
    if args.include_i18n_mod or args.i18n_jar:
        try:
            attachment = (attach_local(store.output, args.i18n_jar) if args.i18n_jar else attach_i18n(store.output,
                args.game_version or scan.metadata.get("minecraft_version", ""),
                args.loader or scan.metadata.get("loader", ""), args.offline))
            manifest["files"] = [f for f in manifest["files"] if f.get("kind") != "i18n-mod"]
            manifest["files"].append({"path": attachment["path"], "sha256": attachment["sha256"], "kind": "i18n-mod"})
        except (ValueError, OSError, httpx.HTTPError, zipfile.BadZipFile) as exc:
            attachment = {"status": "unavailable", "message": str(exc)}
        scan.metadata["i18n_mod"] = manifest["i18n_mod"] = attachment
        store.metadata(scan)
        store.export()
        atomic_write(store.output / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return {"output": str(store.output), "patch": str(store.output / "patch"),
            "files": len(manifest["files"]), "partial": manifest["partial"],
            "pending_entries": manifest["pending_entries"], "i18n_mod": manifest["i18n_mod"],
            "excluded_resources": manifest["excluded_resources"],
            "quality_warnings": manifest["quality_warnings"],
            "kubejs_diagnostics": manifest.get("kubejs_diagnostics", []),
            "delta": scan.metadata.get("delta", {}), "warnings": scan.warnings,
            **({"coverage_complete": manifest["coverage_complete"], "deferred_entries": manifest["deferred_entries"],
                "mod_library": manifest["mod_library"]} if "coverage_complete" in manifest else {})}


def run_translation(store, args):
    scan = store.load()
    validate_sources(scan)
    mods = mod_scan(scan)
    if mods is not None:
        library_path = args.translation_library or Path(migrated_path(mods.metadata["mod_library"]["path"]))
        if library_path.resolve().is_relative_to(Path(scan.root).resolve()):
            raise ValueError("共享译库必须位于游戏实例之外")
        pending_ids = {entry.id for entry in scan.entries if entry.translation is None}
        reuse_library(mods, library_path, args.reuse_policy or mods.metadata["mod_library"]["policy"])
        for entry in scan.entries:
            if entry.id in pending_ids and entry.translation is not None:
                store.update(entry)
    excluded = resource_exclusions(scan)
    config = config_for(args, scan.metadata.get("model_config"))
    # A checkpoint's language pair is immutable even when current settings change.
    config.source_locale, config.target_locale = scan.source_locale, scan.target_locale
    scan.metadata["model_config"] = asdict(config)
    mods = mod_scan(scan)
    store.metadata(scan)
    pending = [e for e in scan.entries if e.translation is None and e.document not in excluded]
    if args.limit is not None:
        if args.limit < 0:
            raise ValueError("--limit 不能为负数")
        pending = pending[:args.limit]
    completed, failures = 0, 0
    previous_usage = scan.metadata.get("api_usage", {}).copy()
    groups = [(False, [entry for entry in pending if not entry.script]),
              (True, [entry for entry in pending if entry.script])]
    script_saved = args.script_config if args.script_config is not None else scan.metadata.get("script_model_config", {})
    if args.script_config is not None:
        scan.metadata["script_model_config"] = script_saved
        store.metadata(scan)
    try:
        for is_script, group in groups:
            if not group:
                continue
            active_config = config
            if is_script:
                if not script_saved:
                    for entry in group:
                        entry.status, entry.error = "failed", "请在整合包翻译页选择脚本大模型接口，再使用当前配置继续翻译"
                        store.update(entry)
                        failures += 1
                        print(json.dumps({"completed": completed, "failed": failures,
                                          "remaining": len(pending) - completed - failures, "entry_id": entry.id,
                                          "error": entry.error}, ensure_ascii=False), file=sys.stderr, flush=True)
                    continue
                active_config = config_for(Job("resume", output=store.output), script_saved)
                if active_config.engine != "api":
                    raise ValueError("KubeJS 脚本翻译需要单独配置 API 大模型")
                active_config.source_locale, active_config.target_locale = scan.source_locale, scan.target_locale
                active_config.allow_missing_placeholders = False
                scan.metadata["script_model_config"] = asdict(active_config)
            elif (config.engine == "local" or config.api_prompt_mode == "hy_mt") and config.target_locale != "zh_cn":
                raise ValueError("HY-MT-2 固定模板输出中文；此任务请使用 API 的 MC 提示词模式")
            candidates = {}
            for entry in scan.entries:
                if bool(entry.script) == is_script and entry.translation is not None and entry.document not in excluded:
                    candidates.setdefault((entry.source, entry.context), set()).add(entry.translation)
            cache = {key: next(iter(values)) for key, values in candidates.items() if len(values) == 1}
            rules = NoTranslate(active_config.non_translate)
            client = (ScriptApiClient(active_config, args.credentials, active_config.request_timeout) if is_script else
                      translation_client(config, args, store.output / "inference.log"))
            with client as model:
                scan.metadata["script_runtime" if is_script else "runtime"] = model.info
                store.metadata(scan)
                for entries, (translation, error) in translation_results(model, group, cache, active_config):
                    if active_config.engine == "api":
                        scan.metadata["api_usage"] = {key: previous_usage.get(key, 0) + value
                                                      for key, value in model.usage_snapshot().items()}
                        store.metadata(scan)
                    for entry in entries:
                        try:
                            if error:
                                raise ValueError(error)
                            validate_entry(entry, translation, active_config.allow_missing_placeholders)
                            rules.validate(entry.source, translation)
                            if mods is not None and entry.semantic_key.startswith("mod:"):
                                validate_mod_translation(mods, entry.source, translation)
                            entry.translation, entry.status, entry.origin, entry.error = translation, "translated", active_config.engine, ""
                            completed += 1
                        except (ValueError, RuntimeError, OSError) as exc:
                            entry.status, entry.error = "failed", str(exc)
                            failures += 1
                        store.update(entry)
                        print(json.dumps({"completed": completed, "failed": failures,
                                          "remaining": len(pending) - completed - failures, "entry_id": entry.id,
                                          "error": entry.error,
                                          "api_usage": scan.metadata.get("api_usage", {}),
                                          "quality_warnings": quality_warnings(entry.source, entry.translation)
                                          if entry.translation is not None else []}, ensure_ascii=False), file=sys.stderr, flush=True)
            previous_usage = scan.metadata.get("api_usage", {}).copy()
    finally:
        store.export()
    if mods is not None:
        scan.metadata["library_publication"] = publish_scan(mods, library_path)
        store.metadata(scan)
    result = export_task(store, args)
    if mods is not None:
        result.update({"mod_library": mods.metadata["mod_library"], "library_publication": scan.metadata["library_publication"],
                       "coverage_complete": mods.metadata["coverage_complete"]})
    result.update({"translated_this_run": completed, "failed_this_run": failures})
    if "api_usage" in scan.metadata:
        result["api_usage"] = scan.metadata["api_usage"]
    return result


def execute(args: Job) -> dict:
    if args.operation == "download-model":
        from .models import download_model
        return download_model(args.output, args.download_variant)
    if args.operation == "mod-library":
        action = args.library_action
        if action == "import":
            path = args.source / "snapshot.json" if args.source.is_dir() else args.source
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise TypeError("译库导入内容必须是 JSON 对象")
            if payload.get("kind") == "mcpl-mod-library":
                with ModLibrary(args.translation_library) as library:
                    return library.import_records(payload)
            scan = Scan.from_dict(payload)
            if scan.metadata.get("task_kind") != "mod-languages":
                raise ValueError("只有模组任务快照可以进入共享译库")
            validate_mod_snapshot(scan)
            if args.translation_library.resolve().is_relative_to(Path(scan.root).resolve()):
                raise ValueError("共享译库必须位于游戏实例之外")
            return publish_scan(scan, args.translation_library, args.include_drafts)
        with ModLibrary(args.translation_library, readonly=action in {"stats", "list", "export"}) as library:
            if action == "stats":
                return library.stats()
            if action == "list":
                return {"records": library.list_records(args.namespace, args.key, args.state, args.limit)}
            if action == "export":
                return library.export(args.output)
            return library.resolve(args.record_id, reject=action == "reject")
    if args.operation in {"scan-mods", "extract-mods", "localize-mods"}:
        report, options, library = coverage(args)
        scan = create_mod_scan(report, options, library, args.pack_id, args.reuse_policy or "reviewed")
        annotate_reuse(report, scan)
        result = {"root": scan.root, "minecraft_version": options.game_version, "loader": options.loader,
                  "scan_complete": report["scan_complete"], "totals": report["totals"],
                  "reuse": scan.metadata["mod_library"], "warnings": report["warnings"]}
        if args.output is not None:
            write_report(report, args.output)
            result["output"] = str(args.output.resolve())
        if args.operation == "scan-mods":
            return result
        with Store(args.output, create=True) as store:
            store.create(scan)
            store.export()
            if args.operation == "localize-mods":
                return run_translation(store, args)
            result["snapshot"] = str(store.output / "snapshot.json")
            result["pending_entries"] = sum(entry.translation is None for entry in scan.entries)
            return result
    if args.operation == "extract-lang":
        return extract_language(args.root, args.output, args.format, args.source_locale, args.target_locale, args.pack_id)
    if args.operation == "backfill":
        return backfill_language(args.bundle, args.lang, args.output, args.allow_partial, args.replace_existing_locale)
    if args.operation == "convert-lang":
        return convert_language(args.source, args.output, args.format)
    if args.operation == "doctor":
        config = config_for(args)
        if config.engine == "api":
            result = {"backend": "api", "protocol": config.api_protocol, "model": config.api_model,
                      "profile_id": config.api_profile_id, "configuration_valid": True}
            if args.probe:
                with translation_client(config, args) as model:
                    result.update(probe_translation=model.translate("Iron Ingot"), runtime=model.info,
                                  api_usage=model.usage_snapshot())
            return result
        result = {"python": sys.executable, "runtime_python": inference_python(args.runtime_python),
                  "model": config.model, "model_exists": Path(config.model).is_file(),
                  "inference_installed_here": importlib.util.find_spec("llama_cpp") is not None,
                  "glossary_exists": bool(config.glossary and Path(config.glossary).is_file())}
        if args.probe:
            with WorkerClient(config, args.runtime_python, args.timeout) as model:
                result["runtime"] = model.info
                result["probe_translation"] = model.translate("Iron Ingot")
        return result
    if args.operation == "translate":
        config = config_for(args)
        with translation_client(config, args) as model:
            translation = model.translate(args.text, args.context)
            return {"source": args.text, "translation": translation, "runtime": model.info,
                    "quality_warnings": quality_warnings(args.text, translation),
                    **({"api_usage": model.usage_snapshot()} if config.engine == "api" else {})}
    if args.operation in {"scan", "extract", "localize", "diff"}:
        if "mods" in recognition_scopes(args.recognition_scope) and (args.source_locale, args.target_locale) != ("en_us", "zh_cn"):
            raise ValueError("模组缺失汉化目前仅支持 en_us → zh_cn")
        baseline = load_snapshot(args.baseline) if args.baseline else None
        pack_id = args.pack_id or (baseline.pack_id if baseline else None)
        scan = scan_pack(args.root, args.source_locale, args.target_locale, pack_id, args.recognition_scope,
                         resource_packs=[*args.resource_pack, *args.cfpa_pack], game_version=args.game_version,
                         loader=args.loader)
        if "mods" in recognition_scopes(args.recognition_scope):
            report, options, library = coverage(args)
            mods = create_mod_scan(report, options, library, pack_id, args.reuse_policy or "reviewed")
            merge_mod_scan(scan, mods)
        if baseline is not None:
            reuse_baseline(scan, baseline, bool(args.allow_missing_placeholders))
            if args.operation == "extract":
                # Reused translations can be exported before any model is selected.
                scan.metadata["model_config"] = {"allow_missing_placeholders": bool(args.allow_missing_placeholders)}
        result = scan.summary()
        result["sample"] = [asdict(e) for e in scan.entries[:max(0, args.sample)]]
        if args.operation in {"scan", "diff"}:
            return result
        validate_output(args.root, args.output)
        if args.output.exists() and any(args.output.iterdir()):
            raise ValueError("输出目录不为空；请使用新目录或续跑现有任务")
        if not scan.entries and not any(d.resource.get("recognition_warnings") for d in scan.documents):
            raise ValueError("没有受支持的条目；请查看识别警告")
        with Store(args.output, create=True) as store:
            store.create(scan)
            store.export()
            if args.operation == "localize":
                return run_translation(store, args)
            result["output"] = str(store.output)
            result["snapshot"] = str(store.output / "snapshot.json")
            return result
    with Store(args.output) as store:
        if args.operation == "resource-exclusion":
            scan = store.load()
            documents = {d.path for d in scan.documents}
            selected = set(args.resource_paths)
            if selected - documents:
                raise ValueError("排除操作包含不属于当前任务的资源，请重新打开任务")
            manual = set(scan.metadata.get("manual_excluded_resources", []))
            manual = manual | selected if args.resource_action == "exclude" else manual - selected
            scan.metadata["manual_excluded_resources"] = sorted(manual)
            resource_exclusions(scan)
            # 已导出过的任务同步重建补丁，防止旧目录中的译文继续生效。
            if (store.output / "manifest.json").is_file():
                build_patch(scan, store.output, allow_partial=True, replace_existing_locale=args.replace_existing_locale)
            store.metadata(scan)
            store.export()
            return {"operation": "resource-exclusion", "action": args.resource_action,
                    "changed_documents": len(selected), "excluded_documents": len(resource_exclusions(scan)),
                    "output": str(store.output), "excluded_resources": scan.metadata.get("excluded_resources", [])}
        if args.operation == "polish-accept":
            return accept_polishing(store, args)
        if args.operation == "polish":
            return run_polishing(store, args, config_for(args))
        if args.operation == "resume":
            return run_translation(store, args)
        if args.operation == "export":
            return export_task(store, args)
        scan = store.load()
        entry = next((e for e in scan.entries if e.id == args.entry_id), None)
        if entry is None:
            raise ValueError("未知条目 ID")
        validate_entry(entry, args.translation, scan.metadata.get("model_config", {}).get("allow_missing_placeholders", False))
        if entry.script:
            split_translation(entry.source, args.translation)
        model_config = scan.metadata.get("script_model_config" if entry.script else "model_config", {})
        NoTranslate(model_config.get("non_translate", "")).validate(entry.source, args.translation)
        mods = mod_scan(scan)
        if mods is not None and entry.semantic_key.startswith("mod:"):
            validate_mod_translation(mods, entry.source, args.translation)
        entry.translation, entry.status, entry.origin, entry.error = args.translation, "reviewed", "manual", ""
        store.update(entry)
        publication = None
        if mods is not None and entry.semantic_key.startswith("mod:"):
            library_path = Path(migrated_path(mods.metadata["mod_library"]["path"]))
            if library_path.resolve().is_relative_to(Path(scan.root).resolve()):
                raise ValueError("共享译库必须位于游戏实例之外")
            publication = publish_scan(mods, library_path, only_entry=entry.id)
            scan.metadata["library_publication"] = publication
            store.metadata(scan)
        store.export()
        return {"entry_id": entry.id, "status": entry.status, "translation": entry.translation,
                "quality_warnings": quality_warnings(entry.source, entry.translation),
                **({"library_publication": publication} if publication is not None else {})}

