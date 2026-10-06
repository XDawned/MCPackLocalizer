# [Module: mcpacklocalizer.core.pack.patch] [Status: 开发中] [Brief: 只写独立补丁目录并生成覆盖清单和审核报告]
from __future__ import annotations

import base64
import html
import json
from pathlib import Path, PureWindowsPath

from ..formats.documents import encode_text
from ..formats.rendering import render_document
from ..kubejs.javascript import split_translation
from ..translation.local import quality_warnings as translation_warnings
from ..translation.local import validate_entry, warning_text
from .extraction import Scan, digest, resource_exclusions
from .snapshots import atomic_write


def safe_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or PureWindowsPath(relative).drive or ".." in path.parts or ".." in PureWindowsPath(relative).parts:
        raise ValueError(f"不安全的相对路径：{relative}")
    resolved_root = root.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(resolved_root) or target == resolved_root:
        raise ValueError(f"输出路径超出补丁目录范围：{relative}")
    return target


def validate_output(root: Path, output: Path):
    root, output = root.resolve(), output.resolve()
    if output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError("任务或补丁目录必须位于游戏实例之外，不能选择实例目录、其中的子目录或包含实例的上级目录。请使用独立的空目录。")


def validate_sources(scan: Scan):
    if scan.metadata.get("task_kind") == "mod-languages":
        from ..mods.tasks import validate_mod_sources
        return validate_mod_sources(scan)
    root = Path(scan.root)
    if "patchouli" in scan.metadata:
        from ..patchouli.discovery import validate_sources as validate_books
        validate_books(scan)
    if "mod_resources" in scan.metadata:
        from ..mods.combined import mod_scan
        from ..mods.tasks import validate_mod_sources
        validate_mod_sources(mod_scan(scan))
    excluded = resource_exclusions(scan)
    for document in scan.documents:
        if document.kind.startswith("patchouli-") or document.kind == "mod-lang":
            continue
        if document.path in excluded:
            continue
        path = safe_path(root, document.path)
        if digest(path.read_bytes()) != document.source_hash:
            raise ValueError(f"源文件在识别后已变化：{document.path}；请使用 --baseline 新建任务")
        stored = (base64.b64decode(document.text, validate=True) if document.kind == "ftb-nbt"
                  else encode_text(document.text, document.encoding))
        if digest(stored) != document.source_hash:
            raise ValueError(f"快照文档与源文件哈希不一致：{document.path}")


def archive_excluded_patch_files(scan: Scan, output: Path, excluded: set[str], prepared_paths=()):
    """Remove only files owned by the previous manifest, with a recoverable backup."""
    manifest_path = output / "manifest.json"
    if not excluded or not manifest_path.is_file():
        return
    previous = json.loads(manifest_path.read_text(encoding="utf-8"))
    excluded_documents = [d for d in scan.documents if d.path in excluded]
    expected_targets = {d.target for d in excluded_documents}
    excluded_archives = {d.resource["container"] for d in excluded_documents
                         if d.resource.get("output_mode") == "archive"}
    for record in previous.get("files", []):
        if record["path"] in prepared_paths:
            continue
        if record.get("source") not in excluded and not (
                record.get("kind") == "patchouli-mod-archive" and record.get("source") in excluded_archives):
            continue
        source = Path(record["source"])
        expected = source.with_name(scan.target_locale + source.suffix).as_posix()
        if record["path"] not in expected_targets and record["path"].casefold() != expected.casefold():
            raise ValueError("已排除资源清单中的目标路径不符合预期")
        target = safe_path(output / "patch", record["path"])
        if not target.is_file():
            continue
        raw = target.read_bytes()
        checksum = digest(raw)
        relative_backup = f"excluded-resources/{checksum}/{record['path']}"
        atomic_write(safe_path(output, relative_backup), raw)
        target.unlink()
        scan.metadata.setdefault("excluded_resource_backups", []).append(
            {"path": record["path"], "backup": relative_backup, "sha256": checksum})


def build_patch(scan: Scan, output: Path, allow_partial=False, replace_existing_locale=False):
    if scan.metadata.get("task_kind") == "mod-languages":
        from ..mods.tasks import build_mod_patch
        return build_mod_patch(scan, output, allow_partial)
    validate_output(Path(scan.root), output)
    validate_sources(scan)
    excluded = resource_exclusions(scan)
    active = [e for e in scan.entries if e.document not in excluded]
    pending = [e for e in active if e.translation is None]
    if pending and not allow_partial:
        raise ValueError(f"{len(pending)} 个条目尚无译文；请审核或续跑，或显式使用 --allow-partial")
    by_document, quality_warnings, hints_by_entry = {}, [], {}
    for entry in active:
        if entry.translation is not None:
            validate_entry(entry, entry.translation,
                           not entry.script and scan.metadata.get("model_config", {}).get("allow_missing_placeholders", False))
            if entry.script:
                split_translation(entry.source, entry.translation)
            hints = translation_warnings(entry.source, entry.translation)
            hints_by_entry[entry.id] = "; ".join(warning_text(hint) for hint in hints)
            quality_warnings.extend({"entry_id": entry.id, "document": entry.document,
                                     "semantic_key": entry.semantic_key, **hint} for hint in hints)
            by_document.setdefault(entry.document, []).append(entry)
    # Recompute from current translations, including reused/manual entries, so
    # hints disappear after correction and never become pending/failed entries.
    scan.metadata["quality_warnings"] = quality_warnings
    prepared = []
    targets = set()
    for document in scan.documents:
        if document.kind.startswith("patchouli-") or document.kind == "mod-lang":
            continue
        if document.path in excluded:
            continue
        target = safe_path(output / "patch", document.target)
        if str(target).lower() in targets:
            raise ValueError("两个文档指向同一个补丁文件")
        targets.add(str(target).lower())
        entries = by_document.get(document.path, [])
        if not entries:
            continue
        existing = safe_path(Path(scan.root), document.target)
        if document.target != document.path and existing.exists() and not replace_existing_locale:
            raise ValueError(f"已存在目标语言文件：{document.target}；请先审核，再使用 --replace-existing-locale")
        raw = render_document(document, entries)
        original_target_hash = digest(existing.read_bytes()) if existing.is_file() else None
        prepared.append((target, raw, {"path": document.target, "source": document.path,
            "source_sha256": document.source_hash, "expected_target_sha256": original_target_hash,
            "sha256": digest(raw), "translated_entries": len(entries)}))
    if "patchouli" in scan.metadata:
        from ..patchouli.rendering import prepare_outputs
        prepared.extend((safe_path(output / "patch", relative), raw, record)
                        for relative, raw, record in prepare_outputs(scan, by_document))
    mod_manifest = None
    if "mod_resources" in scan.metadata:
        from ..mods.combined import mod_scan
        from ..mods.tasks import prepare_mod_patch
        relative, raw, mod_manifest, _ = prepare_mod_patch(mod_scan(scan), allow_partial)
        prepared.append((safe_path(output / "patch", relative), raw, mod_manifest["files"][0]))
    if len({str(target).casefold() for target, _, _ in prepared}) != len(prepared):
        raise ValueError("多个所选资源指向同一个补丁文件")
    archive_excluded_patch_files(scan, output, excluded, {record["path"] for _, _, record in prepared})
    for target, raw, _ in prepared:
        atomic_write(target, raw)
    manifest = {"schema_version": 1, "pack_id": scan.pack_id, "source_locale": scan.source_locale,
                "target_locale": scan.target_locale, "partial": bool(pending), "pending_entries": len(pending),
                "files": [record for _, _, record in prepared],
                "obsolete_patch_files": scan.metadata.get("obsolete_patch_files", []),
                "excluded_resources": scan.metadata.get("excluded_resources", []),
                "excluded_resource_backups": scan.metadata.get("excluded_resource_backups", []),
                "quality_warnings": quality_warnings,
                "kubejs_diagnostics": scan.metadata.get("kubejs", {}).get("diagnostics", []),
                "i18n_mod": scan.metadata.get("i18n_mod", {"status": "disabled"})}
    if "kubejs" in scan.metadata:
        manifest["kubejs_complete"] = not bool(manifest["kubejs_diagnostics"])
        manifest["partial"] |= not manifest["kubejs_complete"]
    if mod_manifest:
        manifest.update({name: mod_manifest[name] for name in ("coverage_complete", "deferred_entries", "mod_library")})
        manifest["partial"] |= mod_manifest["partial"]
    if "patchouli" in scan.metadata:
        manifest["patchouli"] = scan.metadata["patchouli"]
        manifest["partial"] |= not scan.metadata["patchouli"]["complete"]
    attachment = manifest["i18n_mod"]
    if attachment.get("status") in {"downloaded", "provided_local"}:
        attached = safe_path(output / "patch", attachment["path"])
        if attached.is_file() and digest(attached.read_bytes()) == attachment["sha256"]:
            manifest["files"].append({"path": attachment["path"], "sha256": attachment["sha256"], "kind": "i18n-mod"})
        else:
            manifest["i18n_mod"] = {"status": "unavailable", "message": "此前附加的 JAR 已丢失或发生变化"}
    atomic_write(output / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    rows = "".join(f"<tr><td>{html.escape(e.document)}</td><td>{html.escape(e.semantic_key)}</td>"
                   f"<td>{html.escape(e.source)}</td><td>{html.escape(e.translation or '')}</td>"
                   f"<td>{html.escape(e.status + ': ' + e.error)}</td>"
                   f"<td>{html.escape(hints_by_entry.get(e.id, ''))}</td></tr>" for e in active)
    warnings = "".join(f"<li>{html.escape(w)}</li>" for w in scan.warnings)
    warnings += "".join(f"<li>{html.escape(record['document'])}:{record.get('line', '')} — "
                        f"{html.escape(record['reason'])}</li>" for record in manifest["kubejs_diagnostics"])
    exclusion_reasons = {"manual": "用户手动排除", "unresolved-language-key": "未解析语言 key，已拦截",
                         "existing-target-locale": "已存在目标语言文件", "locale-descriptor": "保留语言描述信息"}
    preserved = "".join(f"<li>{html.escape(r['source'])}：{html.escape(exclusion_reasons.get(r['reason'], r['reason']))}</li>"
                        for r in manifest["excluded_resources"])
    instructions = ""
    if any(r.get("kind") == "patchouli-resourcepack" for r in manifest["files"]):
        instructions += "<p>在游戏资源包设置中启用 MCPackLocalizer-Patchouli，并放在待覆盖资源包之上。</p>"
    if any(r.get("kind") == "patchouli-mod-archive" for r in manifest["files"]):
        instructions += "<p>帕秋莉 JAR 补丁需替换对应模组文件；书名和首页说明的直写译文对所有游戏语言生效。</p>"
    if mod_manifest:
        instructions += "<p>在游戏资源包设置中启用 MCPackLocalizer-Mod-Translations。</p>"
    report = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>汉化报告</title>'
              '<style>body{font-family:system-ui;margin:24px}table{border-collapse:collapse;width:100%}'
              'td,th{border:1px solid #ccc;padding:8px;vertical-align:top;white-space:pre-wrap}</style>'
              f'<h1>{html.escape(scan.pack_id)} 汉化报告</h1><p>复制 patch/ 内的内容到对应游戏实例目录。'
              f'文件数：{len(prepared)}；待处理条目：{len(pending)}。覆盖前备份。</p>'
              f'{instructions}'
              f'<ul>{warnings}</ul><p>已排除资源（保留整合包原文件）：</p><ul>{preserved}</ul>'
              '<p>过时文件需单独核对，覆盖目录不会自动删除它们。</p>'
              '<table><tr><th>文件</th><th>条目</th><th>原文</th><th>译文</th><th>状态</th><th>质量提示（不阻断）</th></tr>' + rows + '</table></html>')
    atomic_write(output / "report.html", report)
    return manifest
