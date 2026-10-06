"""Validate snapshot locations and render only selected text values."""
from __future__ import annotations

import base64
from dataclasses import replace
from pathlib import Path

from .binary_nbt import parse_nbt, replace_nbt
from .documents import Parser, String, encode_text, replace_strings, strings


def render_document(document, entries) -> bytes:
    if document.kind.startswith("patchouli-"):
        from ..patchouli.rendering import render
        return render(document, entries)
    if document.kind == "kubejs-script":
        from ..kubejs.javascript import render_script
        return encode_text(render_script(document.text, entries), document.encoding)
    # A normal pack language file may also contain keys referenced by a book.
    # Compose its tooltip children before the regular span-preserving renderer.
    if any(e.patchouli for e in entries):
        from ..patchouli.rendering import compose
        groups = {}
        plain = []
        for entry in entries:
            if entry.patchouli:
                groups.setdefault(tuple(entry.path), []).append(entry)
            else:
                plain.append(entry)
        for group in groups.values():
            first = group[0]
            source = first.patchouli.get("parent_source", first.source)
            plain.append(replace(first, source=source, translation=compose(source, group), patchouli={}))
        entries = plain
    if document.kind == "ftb-nbt":
        raw = base64.b64decode(document.text, validate=True)
        node = parse_nbt(raw)
    elif Path(document.path).suffix.lower() == ".lang":
        from ..pack.extraction import _lang_lines
        node = None
        values = {(s.start, s.end): (list(p), s.value) for p, s, _, _ in _lang_lines(document.text)}
    else:
        node = Parser(document.text, Path(document.path).suffix.lower()[1:]).parse()
    if node is not None:
        values = {(s.start, s.end): (list(p), s.value) for p, s in strings(node)}
    if any(values.get((e.start, e.end)) != (e.path, e.source) for e in entries):
        raise ValueError("快照的原文范围/路径与对应条目不匹配")
    updates = [(String(e.source, e.start, e.end), e.translation) for e in entries]
    if document.kind == "ftb-nbt":
        return replace_nbt(raw, updates)
    if Path(document.path).suffix.lower() == ".lang":
        text = document.text
        previous = len(text) + 1
        for entry in sorted(entries, key=lambda e: e.start, reverse=True):
            if entry.end > previous:
                raise ValueError("语言字符串替换范围重叠")
            if "\n" in entry.translation or "\r" in entry.translation:
                raise ValueError("旧式 .lang 译文不能包含字面换行符")
            text = text[:entry.start] + entry.translation + text[entry.end:]
            previous = entry.start
    else:
        text = replace_strings(document.text, updates)
        Parser(text, Path(document.path).suffix.lower()[1:]).parse()
    return encode_text(text, document.encoding)
