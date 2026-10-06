# [Module: desktop.tasks] [Status: 已完成] [Brief: 只读加载数据库检查点或便携快照与条目摘要]
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

from mcpacklocalizer.core.pack.extraction import Scan, resource_exclusions
from mcpacklocalizer.core.translation.local import quality_warnings, warning_text

from ...paths import migrated_path

STATUS = {"pending": "待翻译", "translated": "已翻译", "reviewed": "已审核", "reused": "已复用", "failed": "失败"}


def load_task(path: str) -> Scan:
    folder = Path(migrated_path(path))
    if folder.is_file():
        return Scan.from_dict(json.loads(folder.read_text(encoding="utf-8")))
    database = folder / "state.sqlite3"
    if database.is_file():
        # Read committed entries, even if snapshot.json predates an interrupted run.
        connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            connection.execute("BEGIN")
            row = connection.execute("SELECT payload FROM metadata WHERE id=1").fetchone()
            if row is None:
                raise ValueError("任务检查点缺少元数据")
            data = json.loads(row[0])
            data["entries"] = [json.loads(row[0]) for row in
                               connection.execute("SELECT payload FROM entries ORDER BY rowid")]
        finally:
            connection.close()
        return Scan.from_dict(data)
    return Scan.from_dict(json.loads((folder / "snapshot.json").read_text(encoding="utf-8")))


def task_counts(scan):
    excluded = resource_exclusions(scan)
    active = [e for e in scan.entries if e.document not in excluded]
    counts = Counter(entry.status for entry in active)
    counts["total"] = len(active)
    counts["complete"] = sum(entry.translation is not None for entry in active)
    counts["remaining"] = counts["total"] - counts["complete"]
    if len(active) != len(scan.entries):
        counts["excluded"] = len(scan.entries) - len(active)
    return dict(counts)


def entry_hints(entry):
    hints = quality_warnings(entry.source, entry.translation) if entry.translation is not None else []
    return "\n".join(filter(None, [entry.error] + [warning_text(hint) for hint in hints]))


def reuse_summary(metadata):
    parts = []
    delta = metadata.get("delta", {})
    if delta:
        parts.append(f"上一版本复用 {delta.get('reused', 0)} 条")
        parts.append(f"变更 {delta.get('changed', 0)} · 新增 {delta.get('added', 0)} · 删除 {delta.get('removed', 0)}")
        if delta.get("ambiguous"):
            parts.append(f"基准冲突 {delta['ambiguous']} 条")
    library = metadata.get("mod_library") or metadata.get("mod_resources", {}).get("mod_library", {})
    if library:
        counts = library.get("counts", {})
        parts.append(f"共享译库复用 {counts.get('reused', 0)} 条")
        for key, label in (("draft_only", "仅有草稿"), ("source_changed", "原文已变更"), ("conflict", "译库冲突")):
            if counts.get(key):
                parts.append(f"{label} {counts[key]} 条")
    return " · ".join(parts)


def result_summary(result):
    if "error" in result:
        return str(result["error"])
    if "translation" in result:
        return result["translation"]
    if result.get("operation") == "resource-exclusion":
        action = "已排除" if result["action"] == "exclude" else "已恢复"
        return f"{action} {result['changed_documents']} 个资源文件；翻译与补丁导出将遵守排除设置。"
    if result.get("operation") == "polish":
        return f"修润候选已生成 · 通过 {result['polished_this_run']} 条 · 拦截 {result['failed_this_run']} 条；请在预览弹窗中选择接受。"
    if result.get("operation") == "polish-accept":
        return f"已接受并保存 {result['accepted']} 条修润结果，可重新导出补丁。"
    if "patch" in result:
        partial = "部分补丁" if result.get("partial") else "完整补丁"
        return (f"{partial}已导出 · {result.get('files', 0)} 个文件 · "
                f"待翻译 {result.get('pending_entries', 0)} 条 · "
                f"质量提示 {len(result.get('quality_warnings', []))} 条")
    if "entries" in result:
        reuse = reuse_summary(result.get("metadata", {}))
        suffix = " · " + reuse if reuse else ""
        return f"发现 {result['entries']} 条文本 · {result.get('files', 0)} 个文件" + suffix
    if "totals" in result:
        reuse = reuse_summary({"mod_library": result.get("reuse", {})})
        return "模组覆盖扫描完成" + (" · " + reuse if reuse else "；详细统计见下方结果")
    if "probe_translation" in result:
        return f"推理检查通过 · Iron Ingot → {result['probe_translation']}"
    if "model_exists" in result:
        model = "模型文件已找到" if result["model_exists"] else "模型文件不存在，请调整设置"
        return model + "；推理能力需通过加载模型试译确认"
    return "操作完成；详细结果见下方"
