"""Offline language codecs and lossless extraction/backfill bundles."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from ..pack.extraction import Scan, read_text, scan_pack
from ..pack.patch import build_patch, safe_path, validate_output, validate_sources
from ..pack.snapshots import atomic_write
from ..translation.local import validate
from .documents import Parser, String

FORMATS = ("lang", "snbt", "json", "json5")


def loads_language(text: str, format: str) -> dict[str, str]:
    if format not in FORMATS:
        raise ValueError(f"不支持的语言文件格式：{format}")
    if format == "lang":
        result = {}
        for index, line in enumerate(text.splitlines(), 1):
            if not line.strip() or line.lstrip().startswith(("#", "!")):
                continue
            if "=" not in line:
                raise ValueError(f".lang 第 {index} 行的条目无效：应为 key=value")
            key, value = line.split("=", 1)
            if not key or key in result:
                raise ValueError(f"第 {index} 行的语言键为空或重复：{key}")
            result[key] = value.replace("%n", "\n")
        return result
    node = Parser(text, format).parse()
    if not isinstance(node, dict) or any(not isinstance(value, String) for value in node.values()):
        raise ValueError("语言文件必须是值为字符串的扁平对象")
    return {key: value.value for key, value in node.items()}


def dumps_language(data: dict[str, str], format: str) -> str:
    if format not in FORMATS:
        raise ValueError(f"不支持的语言文件格式：{format}")
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in data.items()):
        raise ValueError("语言键和值必须是字符串")
    if format == "lang":
        lines = []
        for key, value in data.items():
            if not key or "=" in key or "\n" in key or "\r" in key or key.lstrip().startswith(("#", "!")):
                raise ValueError(f"语言键无法用 .lang 表示：{key!r}；请改用 JSON/SNBT")
            if "%n" in value or "\r" in value:
                raise ValueError("字面 %n 或回车符无法通过 .lang 往返；请改用 JSON/SNBT")
            lines.append(key + "=" + value.replace("\n", "%n"))
        return "\n".join(lines) + ("\n" if lines else "")
    # JSON's quoted-key syntax is also valid SNBT and JSON5, including Unicode/escapes.
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def load_language(path: Path) -> dict[str, str]:
    text, _, _ = read_text(path)
    return loads_language(text, path.suffix.lower().lstrip("."))


def convert_language(source: Path, output: Path, format=None):
    format = format or output.suffix.lower().lstrip(".")
    data = load_language(source)
    content = dumps_language(data, format)
    if source.resolve() == output.resolve():
        raise ValueError("转换输出不能与输入文件相同")
    if output.exists():
        raise ValueError("转换输出已存在；请选择新文件")
    atomic_write(output, content)
    return {"output": str(output.resolve()), "format": format, "entries": len(data)}


def language_bindings(scan: Scan):
    documents = {document.path: document for document in scan.documents}
    proposed = {}
    for entry in scan.entries:
        if entry.semantic_key.startswith("lang:") or documents[entry.document].kind.startswith("ftb-lang-"):
            key = ".".join(map(str, entry.path))
        else:
            namespace = "betterquesting" if entry.semantic_key.startswith("bq:") else "ftbquests"
            key = namespace + "." + quote(entry.semantic_key.split(":", 1)[1], safe="._").replace("%2F", ".")
        proposed[entry.id] = key
    counts = Counter(proposed.values())
    # Original locale keys survive when unique; disambiguate physical duplicates deterministically.
    bindings = {}
    for entry in scan.entries:
        key = proposed[entry.id]
        if counts[key] > 1:
            key += "." + entry.id
        if key in bindings:
            raise ValueError("语言键冲突")
        bindings[key] = entry.id
    return bindings


def extract_language(root: Path, output: Path, format="json", source_locale="en_us", target_locale="zh_cn", pack_id=None):
    validate_output(root, output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("输出目录非空；请选择新目录")
    scan = scan_pack(root, source_locale, target_locale, pack_id)
    if not scan.entries:
        raise ValueError("没有受支持的条目；请查看识别警告")
    bindings = language_bindings(scan)
    entries = {entry.id: entry for entry in scan.entries}
    data = {key: (entries[entry_id].source.replace("%n", "\n")
                  if Path(entries[entry_id].document).suffix.lower() == ".lang" else entries[entry_id].source)
            for key, entry_id in bindings.items()}
    content = dumps_language(data, format)
    validate_sources(scan)
    language = output / (scan.source_locale + "." + format)
    mapping = output / "mapping.json"
    atomic_write(language, content)
    atomic_write(mapping, json.dumps({"schema_version": 1, "bindings": bindings, "scan": scan.to_dict()},
                                    ensure_ascii=False, indent=2))
    return {**scan.summary(), "output": str(output.resolve()), "language": str(language.resolve()),
            "mapping": str(mapping.resolve()), "format": format}


def backfill_language(bundle: Path, language: Path, output: Path, allow_partial=False, replace_existing_locale=False):
    mapping = bundle / "mapping.json" if bundle.is_dir() else bundle
    data = json.loads(mapping.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("不支持的语言映射结构")
    try:
        scan = Scan.from_dict(data["scan"])
        bindings = data["bindings"]
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("语言映射结构无效") from exc
    entries = {entry.id: entry for entry in scan.entries}
    if (not isinstance(bindings, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in bindings.items())
            or len(bindings) != len(entries)
            or set(bindings.values()) != set(entries)):
        raise ValueError("语言映射必须为每个条目恰好绑定一次")
    translations = load_language(language)
    unknown = sorted(set(translations) - set(bindings))
    if unknown:
        raise ValueError(f"未知语言键（{len(unknown)} 个）：{', '.join(unknown[:5])}")
    validate_output(Path(scan.root), output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("回填输出目录非空；请选择新目录")
    if any(path.resolve().is_relative_to(output.resolve()) for path in (mapping, language)):
        raise ValueError("回填输出目录会包含输入文件")
    document_by_path = {document.path: document for document in scan.documents}
    if len(entries) != len(scan.entries) or any(entry.document not in document_by_path for entry in scan.entries):
        raise ValueError("语言映射存在重复条目或缺少文档")
    for key, value in translations.items():
        entry = entries[bindings[key]]
        # .lang retains %n on disk while the interchange codec decodes it for other formats.
        if Path(document_by_path[entry.document].path).suffix.lower() == ".lang":
            value = value.replace("\n", "%n")
        validate(entry.source, value)
        entry.translation, entry.status, entry.origin = value, "reviewed", "manual"
    manifest = build_patch(scan, output, allow_partial, replace_existing_locale)
    atomic_write(safe_path(output, "snapshot.json"), json.dumps(scan.to_dict(), ensure_ascii=False, indent=2))
    return {"output": str(output.resolve()), "patch": str((output / "patch").resolve()),
            "files": len(manifest["files"]), "partial": manifest["partial"],
            "pending_entries": manifest["pending_entries"], "quality_warnings": manifest["quality_warnings"],
            "warnings": scan.warnings}
