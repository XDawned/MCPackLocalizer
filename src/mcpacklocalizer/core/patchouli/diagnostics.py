# [Module: core.patchouli.diagnostics] [Status: 已完成] [Brief: 未解析语言键拦截及旧任务识别提示]
from __future__ import annotations

import re

LANGUAGE_KEY = re.compile(r"[a-z_][a-z0-9_]*(?:[.:][a-z0-9_/-]+)+", re.IGNORECASE)


def looks_like_language_key(value):
    return bool(LANGUAGE_KEY.fullmatch(value))


def unresolved_key_documents(scan):
    """旧任务中的声明 key 也不能作为正文翻译或回写。"""
    declarations = {d.path for d in scan.documents if d.kind == "patchouli-book"}
    return {e.document for e in scan.entries if e.document in declarations and looks_like_language_key(e.source)}


def resource_warnings(scan):
    warnings = {d.path: list(d.resource.get("recognition_warnings", [])) for d in scan.documents
                if d.resource.get("recognition_warnings")}
    blocked = unresolved_key_documents(scan)
    for entry in scan.entries:
        if entry.document in blocked and looks_like_language_key(entry.source):
            message = f"疑似未解析的帕秋莉语言 key：{entry.source}；已拦截此声明文件的翻译与导出，请重新识别或检查语言资源。"
            warnings.setdefault(entry.document, []).append(message)
    return warnings
