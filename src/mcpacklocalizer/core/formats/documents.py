# [Module: mcpacklocalizer.core.formats.documents] [Status: 开发中] [Brief: 保留非文本字节的 FTB SNBT/JSON5 文本位置解析]
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class String:
    value: str
    start: int
    end: int


@dataclass(frozen=True)
class Atom:
    raw: str


class ParseError(ValueError):
    pass


def encode_text(text: str, encoding: str) -> bytes:
    # UTF-16 big-endian sources carry a BOM; preserve their original byte order.
    return (b"\xfe\xff" if encoding == "utf-16-be" else b"") + text.encode(encoding)


class Parser:
    """Parse FTB's comma-optional SNBT while keeping source spans, not numeric coercions.

    JSON5 is additionally validated by its reference Python parser. Unsupported or
    malformed syntax fails the document instead of silently extracting half a file.
    """

    def __init__(self, text: str, syntax: str = "snbt"):
        self.text, self.pos, self.syntax = text, 0, syntax

    def error(self, message: str):
        line = self.text.count("\n", 0, self.pos) + 1
        raise ParseError(f"{message}（第 {line} 行）")

    def space(self):
        while self.pos < len(self.text):
            if self.text[self.pos].isspace():
                self.pos += 1
            elif self.text.startswith("//", self.pos) or self.text[self.pos] == "#":
                end = self.text.find("\n", self.pos)
                self.pos = len(self.text) if end == -1 else end + 1
            elif self.text.startswith("/*", self.pos):
                end = self.text.find("*/", self.pos + 2)
                if end == -1:
                    self.error("注释未闭合")
                self.pos = end + 2
            else:
                break

    def quoted(self) -> String:
        start, quote = self.pos, self.text[self.pos]
        self.pos += 1
        while self.pos < len(self.text):
            c = self.text[self.pos]
            self.pos += 1
            if c == "\\":
                self.pos += 1
            elif c == quote:
                raw = self.text[start:self.pos]
                if self.syntax == "json":
                    # 严格 JSON 使用标准库解码；避免为每个语言键和值重复调用 JSON5 解析器。
                    decoded = json.loads(raw)
                elif self.syntax == "json5":
                    import json5
                    decoded = json5.loads(raw)
                else:
                    body = raw[1:-1]
                    escapes = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f",
                               "\\": "\\", '"': '"', "'": "'"}
                    def decode(match, escapes=escapes):
                        v = match.group(1)
                        return chr(int(v[1:], 16)) if v.startswith("u") else escapes.get(v, "\\" + v)
                    decoded = re.sub(r"\\(u[0-9a-fA-F]{4}|.)", decode, body, flags=re.DOTALL)
                return String(decoded, start, self.pos)
        self.error("字符串未闭合")

    def value(self) -> Any:
        self.space()
        if self.pos >= len(self.text):
            self.error("缺少值")
        c = self.text[self.pos]
        if c in "\"'":
            return self.quoted()
        if c == "{":
            return self.compound()
        if c == "[":
            return self.sequence()
        start = self.pos
        while self.pos < len(self.text) and not self.text[self.pos].isspace() and self.text[self.pos] not in ",]}":
            self.pos += 1
        if self.pos == start:
            self.error("缺少标量值")
        return Atom(self.text[start:self.pos])

    def compound(self):
        self.pos += 1
        result = {}
        while True:
            self.space()
            if self.pos >= len(self.text):
                self.error("复合标签未闭合")
            if self.text[self.pos] == "}":
                self.pos += 1
                return result
            if self.text[self.pos] in "\"'":
                key = self.quoted().value
            else:
                start = self.pos
                while self.pos < len(self.text) and not self.text[self.pos].isspace() and self.text[self.pos] not in ":{}[],":
                    self.pos += 1
                key = self.text[start:self.pos]
            self.space()
            if not key or self.pos >= len(self.text) or self.text[self.pos] != ":":
                self.error("缺少键值对")
            if key in result:
                self.error(f"键重复：{key!r}")
            self.pos += 1
            result[key] = self.value()
            self.space()
            if self.pos < len(self.text) and self.text[self.pos] == ",":
                self.pos += 1

    def sequence(self):
        self.pos += 1
        result = []
        # Typed SNBT arrays contain only atoms and are never translation targets.
        self.space()
        if self.text[self.pos:self.pos + 2].upper() in {"B;", "I;", "L;"}:
            self.pos += 2
        while True:
            self.space()
            if self.pos >= len(self.text):
                self.error("列表未闭合")
            if self.text[self.pos] == "]":
                self.pos += 1
                return result
            result.append(self.value())
            self.space()
            if self.pos < len(self.text) and self.text[self.pos] == ",":
                self.pos += 1

    def parse(self):
        if self.syntax == "json":
            json.loads(self.text)
        elif self.syntax == "json5":
            import json5
            json5.loads(self.text, allow_duplicate_keys=False)
        result = self.value()
        self.space()
        if self.pos != len(self.text):
            self.error("末尾存在多余内容")
        return result


def strings(node: Any, path: tuple = ()):
    if isinstance(node, String):
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from strings(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from strings(value, path + (index,))


def replace_strings(text: str, updates: list[tuple[String, str]]) -> str:
    """Replace only quoted value spans; comments, keys, suffixes and whitespace survive."""
    previous = len(text) + 1
    for node, translation in sorted(updates, key=lambda pair: pair[0].start, reverse=True):
        if not 0 <= node.start < node.end <= len(text) or node.end > previous:
            raise ValueError("字符串替换无效或范围重叠")
        text = text[:node.start] + json.dumps(translation, ensure_ascii=False) + text[node.end:]
        previous = node.start
    return text
