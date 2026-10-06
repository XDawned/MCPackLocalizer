"""Compose offline JS and component JSON discovery into the pack task."""
from __future__ import annotations

import re
from pathlib import Path

from ..formats.documents import Parser, String
from ..pack.extraction import Document, Entry, digest, read_text
from ..translation.local import PROTECTED
from .javascript import MARKER, discover_script

DISPLAY = {"tip", "description", "name", "title", "subtitle", "tooltip", "message"}
COMPONENT_FIELDS = {"text", "translate", "fallback", "with", "extra", "color", "bold", "italic", "underlined",
                    "strikethrough", "obfuscated", "font", "insertion", "hoverEvent", "clickEvent", "hover"}
SKIP_DIRS = {"backup", "backups", "cache", ".cache", ".git", "node_modules"}


def source_text(value, locale):
    visible = PROTECTED.sub(" ", MARKER.sub("", value))
    return bool(re.search(r"[A-Za-z]", visible) if locale.startswith("en_") else any(c.isalpha() for c in visible))


def json_texts(node, path=(), display=False):
    if isinstance(node, list):
        for index, child in enumerate(node):
            yield from json_texts(child, path + (index,), display)
    elif isinstance(node, dict):
        component = "text" in node and (display or set(node).issubset(COMPONENT_FIELDS))
        for key, child in node.items():
            if component and key == "text" and isinstance(child, String):
                yield path + (key,), child
            elif key in DISPLAY or key in {"extra", "with"} and (component or "translate" in node):
                yield from json_texts(child, path + (key,), key in DISPLAY or display or component)
            elif key in {"hover", "hoverEvent"} and (component or "translate" in node):
                # A show_text hover contains a component, never click commands or item NBT.
                if key == "hover":
                    yield from json_texts(child, path + (key,), True)
                elif isinstance(child, dict) and isinstance(child.get("action"), String) and child["action"].value == "show_text":
                    for content_key in ("contents", "value"):
                        if content_key in child:
                            yield from json_texts(child[content_key], path + (key, content_key), True)
            elif key not in COMPONENT_FIELDS and key not in {"conditions", "effects", "recipes", "textures"}:
                yield from json_texts(child, path + (key,), False)


def scan_kubejs(scan):
    root = Path(scan.root)
    files, diagnostics = [], []
    for directory in ("startup_scripts", "server_scripts", "client_scripts", "assets"):
        folder = root / "kubejs" / directory
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or any(part.casefold() in SKIP_DIRS for part in path.relative_to(folder).parts):
                continue
            if directory == "assets":
                if ({"lang", "patchouli_books"}.intersection(part.casefold() for part in path.relative_to(folder).parts)
                        or path.suffix.lower() not in {".json", ".json5"}):
                    continue
            elif path.suffix.lower() != ".js":
                continue
            files.append(path)
    for path in files:
        relative = path.relative_to(root).as_posix()
        if not path.resolve().is_relative_to(root):
            scan.warnings.append(f"KubeJS 文件离开实例目录，已跳过：{relative}")
            continue
        try:
            text, encoding, checksum = read_text(path)
            entries = []
            if path.suffix.lower() == ".js":
                kind = "kubejs-script"
                units, warnings = discover_script(text)
                diagnostics.extend({"document": relative, **warning} for warning in warnings)
                duplicates = {}
                for unit in sorted(units, key=lambda unit: unit.script["slots"][0]["start"]):
                    if not source_text(unit.source, scan.source_locale):
                        continue
                    anchor = unit.script["rule"] + ":" + unit.script["anchor"]
                    number = duplicates.get(anchor, 0)
                    duplicates[anchor] = number + 1
                    semantic = f"kubejs:{anchor}/{number}"
                    slots = unit.script["slots"]
                    entries.append(Entry(digest(relative + "\0" + semantic), semantic, relative,
                                         [unit.script["rule"], number], unit.source,
                                         slots[0]["start"], slots[-1]["end"], unit.context, script=unit.script))
            else:
                kind = "kubejs-asset-text"
                node = Parser(text, path.suffix.lower()[1:]).parse()
                for keypath, string in json_texts(node):
                    if not source_text(string.value, scan.source_locale):
                        continue
                    semantic = "kubejs-json:" + "/".join(map(str, keypath))
                    entries.append(Entry(digest(relative + "\0" + semantic), semantic, relative, list(keypath),
                                         string.value, string.start, string.end, semantic))
            if entries:
                scan.documents.append(Document(relative, relative, kind, text, checksum, encoding))
                scan.entries.extend(entries)
        except (ValueError, OSError, RecursionError, UnicodeError) as exc:
            scan.warnings.append(f"KubeJS 无法处理 {relative}：{exc}")
            diagnostics.append({"document": relative, "reason": str(exc)})
    scan.metadata["kubejs"] = {"scanner_version": 1, "files_scanned": len(files), "diagnostics": diagnostics}
    if diagnostics:
        scan.warnings.append(f"KubeJS 有 {len(diagnostics)} 项需人工检查；详见识别报告与补丁报告。")
