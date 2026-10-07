# [Module: core.mods.tasks] [Status: 已完成] [Brief: 模组任务检查点、译库复用及稀疏补丁导出]
"""Mod coverage tasks, resumable translation, and sparse resource-pack export."""
from __future__ import annotations

import html
import io
import json
import re
import zipfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from ..pack.extraction import Document, Entry, Scan, digest, resource_exclusions
from ..pack.patch import safe_path, validate_output
from ..pack.snapshots import atomic_write
from ..translation.local import quality_warnings, validate, warning_text
from .library import reuse_library
from .scan import LANG_PATH, ResourceOptions, default_cache, detect, file_digest, get_cfpa, version_tuple


def game_settings(root):
    for file in sorted(root.glob("*.json")):
        try:
            data = json.loads(file.read_bytes())
            if not isinstance(data, dict) or not ("libraries" in data or "inheritsFrom" in data):
                continue
            arguments = data.get("arguments", {}).get("game", [])
            versions = [data.get(k) for k in ("clientVersion", "minecraftVersion", "inheritsFrom", "id")]
            if "--fml.mcVersion" in arguments:
                index = arguments.index("--fml.mcVersion")
                if index + 1 < len(arguments):
                    versions.insert(0, arguments[index + 1])
            version = next((v for v in versions if isinstance(v, str) and re.fullmatch(r"\d+\.\d+(?:\.\d+)?", v)), None)
            libraries = " ".join(x.get("name", "") for x in data.get("libraries", []) if isinstance(x, dict))
            loader = next((name for name, token in (("neoforge", "net.neoforged"), ("quilt", "org.quiltmc"),
                          ("forge", "net.minecraftforge"), ("fabric", "net.fabricmc")) if token in libraries), None)
            return {"game_version": version, "loader": loader, "version_file": str(file)}
        except (ValueError, OSError, TypeError, AttributeError):
            continue
    return {}


def resource_options(args):
    inferred = game_settings(args.root.resolve())
    version = args.game_version or inferred.get("game_version")
    loader = args.loader or inferred.get("loader")
    if not version or loader not in {"forge", "fabric", "quilt", "neoforge"}:
        raise ValueError("无法识别 Minecraft 版本/加载器；请设置 game_version 和 loader")
    return ResourceOptions(version, loader, args.cache, args.offline, args.cfpa_pack or [],
                           args.i18n_metadata, args.i18n_metadata_jar, args.cfpa_release)


def validate_locations(root, cache, library, output=None):
    root = root.resolve()
    for path in (cache, library):
        if path.resolve().is_relative_to(root):
            raise ValueError("CFPA 缓存和共享译库必须位于游戏实例之外")
    if output is not None:
        validate_output(root, output)
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise ValueError("输出目录不为空；请选择新目录或继续现有任务")
        for path in (cache, library):
            if path.resolve().is_relative_to(output.resolve()):
                raise ValueError("共享缓存/译库必须位于任务输出之外")


def coverage(args):
    root = args.root.resolve(strict=True)
    if not (root / "mods").is_dir():
        raise ValueError("实例必须包含 mods/ 目录")
    options = resource_options(args)
    library = args.translation_library or default_cache() / "mod-translations.sqlite3"
    validate_locations(root, options.cache, library, getattr(args, "output", None))
    for path in [*options.cfpa_pack, *args.resource_pack]:
        if not path.exists():
            raise ValueError(f"资源包缺失：{path}")
    sources = get_cfpa(options)
    report = detect(root, sources, args.coverage_mode, args.resource_pack,
                    version_tuple(options.game_version) < (1, 13, 0))
    report.update({"game_version": options.game_version, "loader": options.loader,
                   "pack_metadata": options.pack_metadata, "source_locale": "en_us", "target_locale": "zh_cn"})
    return report, options, library


def _locale_files(folder):
    return [file for file in (folder / "assets").glob("*/lang/*")
            if file.is_file() and LANG_PATH.fullmatch(file.relative_to(folder).as_posix())]


def input_paths(root, report):
    files = {p.resolve() for p in (root / "mods").iterdir() if p.is_file() and p.suffix.lower() == ".jar"}
    if (root / "options.txt").is_file():
        files.add((root / "options.txt").resolve())
    for folder in (root / "resources", root / "kubejs"):
        files.update(p.resolve() for p in _locale_files(folder))
    for source in report["custom_sources"]:
        path = Path(source["path"])
        files.update([path.resolve()] if path.is_file() else (p.resolve() for p in _locale_files(path)))
    return sorted(files)


def input_inventory(root, report):
    inventory = []
    for path in input_paths(root, report):
        relative = path.relative_to(root).as_posix() if path.is_relative_to(root) else None
        inventory.append({"path": relative, "external_path": str(path) if relative is None else None,
                          "sha256": file_digest(path)})
    return inventory


def create_mod_scan(report, options, library, pack_id=None, policy="reviewed"):
    root = Path(report["instance"])
    scan = Scan(str(root), pack_id or root.name, "en_us", "zh_cn")
    by_namespace = defaultdict(dict)
    details = {}
    deferred = []
    for row in report["missing"]:
        if row.get("requires_structured_translation") or not row["english"].strip():
            deferred.append(row)
            continue
        namespace, key = row["namespace"], row["key"]
        provider = ",".join(row["provider_ids"]) or "unverified"
        semantic = f"mod:{provider}/{namespace}/{key}"
        entry_id = digest("en_us\0zh_cn\0" + semantic)[:24]
        document = f"mod-language/{namespace}/en_us.json"
        context = f"Mod {provider}; language key {namespace}:{key}"
        scan.entries.append(Entry(entry_id, semantic, document, [key], row["english"], -1, -1, context))
        details[entry_id] = row
        by_namespace[namespace][key] = row["english"]
    for namespace, values in sorted(by_namespace.items()):
        text = json.dumps(values, ensure_ascii=False, sort_keys=True, indent=2)
        scan.documents.append(Document(f"mod-language/{namespace}/en_us.json", f"assets/{namespace}/lang/zh_cn.json",
                                       "mod-lang", text, digest(text)))
    scan.warnings = [f"{w['severity']}: {w['source']}: {w['message']}" for w in report["warnings"]]
    scan.metadata = {"task_kind": "mod-languages", "created_at": datetime.now(UTC).isoformat(),
                     "minecraft_version": options.game_version, "loader": options.loader,
                     "legacy_mod_language": version_tuple(options.game_version) < (1, 13, 0),
                     "pack_metadata": options.pack_metadata, "mod_entries": details,
                     "deferred_mod_entries": deferred, "coverage_complete": report["scan_complete"],
                     "coverage_totals": report["totals"], "cfpa_sources": report["cfpa_sources"],
                     "custom_sources": report["custom_sources"], "coverage_mode": report["mode"],
                     "source_inputs": input_inventory(root, report),
                     "mod_jar_inventory": sorted(p.name for p in (root / "mods").iterdir()
                                                  if p.is_file() and p.suffix.lower() == ".jar")}
    reuse_library(scan, library, policy)
    return scan


def annotate_reuse(report, scan):
    entries = {entry.id: entry for entry in scan.entries}
    matches = scan.metadata["mod_library"]["matches"]
    report["reuse"] = scan.metadata["mod_library"]
    report["totals"]["library_reused_keys"] = scan.metadata["mod_library"]["counts"]["reused"]
    report["totals"]["translation_pending_keys"] = sum(entry.translation is None for entry in entries.values())
    report["totals"]["deferred_keys"] = len(scan.metadata["deferred_mod_entries"])
    by_key = {(detail["namespace"], detail["key"]): entry_id
              for entry_id, detail in scan.metadata["mod_entries"].items()}
    for row in report["missing"]:
        entry_id = by_key.get((row["namespace"], row["key"]))
        if entry_id:
            row["entry_id"] = entry_id
            if entry_id in matches:
                row["library_match"] = matches[entry_id]
                if entries[entry_id].translation is not None:
                    row["reused_translation"] = entries[entry_id].translation


def validate_mod_sources(scan):
    validate_mod_snapshot(scan)
    root = Path(scan.root).resolve()
    current = sorted(p.name for p in (root / "mods").iterdir() if p.is_file() and p.suffix.lower() == ".jar")
    if current != scan.metadata["mod_jar_inventory"]:
        raise ValueError("已安装的模组发生变化；请重新识别任务并复用共享译库")
    for item in scan.metadata["source_inputs"]:
        path = safe_path(root, item["path"]) if item["path"] is not None else Path(item["external_path"])
        if not path.is_file() or file_digest(path) != item["sha256"]:
            raise ValueError(f"模组/资源来源已变化：{path}；请重新识别任务")
    report_sources = {"custom_sources": scan.metadata["custom_sources"]}
    actual_paths = {str(p) for p in input_paths(root, report_sources)}
    expected_paths = {str(safe_path(root, item["path"]) if item["path"] is not None else Path(item["external_path"]).resolve())
                      for item in scan.metadata["source_inputs"]}
    if actual_paths != expected_paths:
        raise ValueError("语言来源清单已变化；请重新识别任务")


def validate_mod_snapshot(scan):
    """Check portable task integrity without requiring the original instance."""
    if scan.source_locale != "en_us" or scan.target_locale != "zh_cn":
        raise ValueError("模组任务目前仅支持英语 en_us → 简体中文 zh_cn")
    if len({entry.id for entry in scan.entries}) != len(scan.entries):
        raise ValueError("模组快照条目 ID 重复")
    documents = {}
    for document in scan.documents:
        if document.path in documents or document.kind != "mod-lang" or digest(document.text) != document.source_hash:
            raise ValueError("模组快照文档无效")
        documents[document.path] = json.loads(document.text)
    for entry in scan.entries:
        detail = scan.metadata["mod_entries"].get(entry.id)
        if not detail or documents.get(entry.document, {}).get(detail["key"]) != entry.source:
            raise ValueError("模组快照源与其条目不匹配")
        if digest(entry.source) != detail["english_sha256"] or entry.path != [detail["key"]]:
            raise ValueError("模组快照身份/哈希已变化")
        if entry.source != detail["english"]:
            raise ValueError("模组快照来源已变化")
        namespace = detail["namespace"]
        if (not re.fullmatch(r"[a-z0-9_.-]+", namespace) or namespace in {".", ".."}
                or entry.document != f"mod-language/{namespace}/en_us.json"):
            raise ValueError("模组快照命名空间无效")
        provider = ",".join(detail["provider_ids"]) or "unverified"
        semantic = f"mod:{provider}/{namespace}/{detail['key']}"
        if entry.semantic_key != semantic or entry.id != digest("en_us\0zh_cn\0" + semantic)[:24]:
            raise ValueError("模组快照提供者身份已变化")


def validate_mod_translation(scan, source, translation, *, manual=False):
    if manual:
        if not isinstance(translation, str) or not translation.strip():
            raise ValueError("译文不能为空")
    else:
        validate(source, translation, scan.metadata.get("model_config", {}).get("allow_missing_placeholders", False))
    if scan.metadata["legacy_mod_language"] and ("\n" in translation or "\r" in translation):
        raise ValueError("旧版 .lang 译文不能包含字面换行符；请保留源中的 %n")


def prepare_mod_patch(scan, allow_partial=False):
    validate_mod_sources(scan)
    excluded = resource_exclusions(scan)
    active = [entry for entry in scan.entries if entry.document not in excluded]
    pending = [entry for entry in active if entry.translation is None]
    deferred = scan.metadata["deferred_mod_entries"]
    if (pending or deferred) and not allow_partial:
        raise ValueError(f"仍有 {len(pending)} 个未翻译条目和 {len(deferred)} 个延期处理的富文本/空条目；请使用 --allow-partial")
    values = defaultdict(dict)
    hints, rows = [], []
    for entry in active:
        detail = scan.metadata["mod_entries"][entry.id]
        if entry.translation is not None:
            validate_mod_translation(scan, entry.source, entry.translation,
                                     manual=entry.status == "reviewed" and entry.origin == "manual")
            values[detail["namespace"]][detail["key"]] = entry.translation
            entry_hints = quality_warnings(entry.source, entry.translation)
            hints.extend({"entry_id": entry.id, **hint} for hint in entry_hints)
        else:
            entry_hints = []
        cells = [detail["namespace"], detail["key"], entry.source, entry.translation or "", entry.status,
                 "; ".join(warning_text(h) for h in entry_hints)]
        rows.append("<tr>" + "".join("<td>" + html.escape(value) + "</td>" for value in cells) + "</tr>")
    buffer = io.BytesIO()
    game = scan.metadata["pack_metadata"]
    pack = {"description": "MCPackLocalizer 补充模组汉化；置于 CFPA 与整合包资源包上方"}
    if "packFormat" in game:
        pack["pack_format"] = game["packFormat"]
    else:
        pack.update({"min_format": game["minFormat"], "max_format": game["maxFormat"]})
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("pack.mcmeta", json.dumps({"pack": pack}, ensure_ascii=False, indent=2).encode())
        for namespace, translations in sorted(values.items()):
            if scan.metadata["legacy_mod_language"]:
                for key in translations:
                    if not key or "=" in key or "\n" in key or "\r" in key or key.lstrip().startswith(("#", "!")):
                        raise ValueError("语言键无法在旧版 .lang 中表示")
                content = "\n".join(key + "=" + value for key, value in sorted(translations.items())) + "\n"
                name = f"assets/{namespace}/lang/zh_cn.lang"
            else:
                content = json.dumps(translations, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
                name = f"assets/{namespace}/lang/zh_cn.json"
            archive.writestr(name, content.encode("utf-8"))
    raw = buffer.getvalue()
    relative = "resourcepacks/MCPackLocalizer-Mod-Translations.zip"
    scan.metadata["quality_warnings"] = hints
    manifest = {"schema_version": 1, "task_kind": "mod-languages", "pack_id": scan.pack_id,
                "source_locale": scan.source_locale, "target_locale": scan.target_locale,
                "partial": bool(pending or deferred or not scan.metadata["coverage_complete"]),
                "pending_entries": len(pending), "deferred_entries": len(deferred),
                "coverage_complete": scan.metadata["coverage_complete"],
                "files": [{"path": relative, "sha256": digest(raw), "translated_entries": sum(map(len, values.values())),
                           "kind": "mod-language-resourcepack"}], "quality_warnings": hints,
                "excluded_resources": scan.metadata.get("excluded_resources", []), "i18n_mod": {"status": "disabled"},
                "mod_library": scan.metadata["mod_library"], "cfpa_sources": scan.metadata["cfpa_sources"],
                "note": "Enable this sparse resource pack above CFPA/custom packs; CFPA itself is not bundled"}
    warning_html = "".join("<li>" + html.escape(warning) + "</li>" for warning in scan.warnings)
    page = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>模组汉化审核</title>'
            '<style>body{font-family:system-ui;margin:24px}table{border-collapse:collapse;width:100%}'
            'td,th{border:1px solid #ddd;padding:8px;white-space:pre-wrap;vertical-align:top}</style>'
            f'<h1>{html.escape(scan.pack_id)} 模组汉化</h1><p>待翻译：{len(pending)}；延期：{len(deferred)}。'
            '补充资源包只包含已翻译键，复制 patch/ 后手动启用并置于其他汉化包上方。</p>'
            f'<ul>{warning_html}</ul><table><tr><th>命名空间</th><th>语言键</th><th>英文</th><th>中文</th>'
            '<th>状态</th><th>质量提示</th></tr>' + "".join(rows) + '</table></html>')
    return relative, raw, manifest, page


def build_mod_patch(scan, output, allow_partial=False):
    validate_output(Path(scan.root), output)
    relative, raw, manifest, page = prepare_mod_patch(scan, allow_partial)
    atomic_write(safe_path(output / "patch", relative), raw)
    atomic_write(output / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    atomic_write(output / "report.html", page)
    return manifest
