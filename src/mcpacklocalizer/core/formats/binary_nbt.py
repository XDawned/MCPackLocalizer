"""Big-endian Java NBT with string byte spans, preserving every other tag byte."""
from __future__ import annotations

import gzip
import struct
import zlib

from .documents import Atom, ParseError, String


def decode_string(raw: bytes) -> str:
    # DataInput.readUTF uses modified UTF-8: encoded NUL and UTF-16 surrogate pairs.
    text = raw.replace(b"\xc0\x80", b"\0").decode("utf-8", errors="surrogatepass")
    return text.encode("utf-16-be", errors="surrogatepass").decode("utf-16-be")


def encode_string(text: str) -> bytes:
    result = bytearray()
    units = text.encode("utf-16-be")
    for offset in range(0, len(units), 2):
        value = int.from_bytes(units[offset:offset + 2], "big")
        if 0 < value < 128:
            result.append(value)
        elif value < 2048:
            result.extend((192 | value >> 6, 128 | value & 63))
        else:
            result.extend((224 | value >> 12, 128 | (value >> 6) & 63, 128 | value & 63))
    if len(result) > 65535:
        raise ValueError("NBT 字符串超过 Java 的 65535 字节上限")
    return struct.pack(">H", len(result)) + result


class NBTParser:
    def __init__(self, raw: bytes):
        self.raw, self.pos = raw, 0

    def take(self, size):
        if size < 0 or self.pos + size > len(self.raw):
            raise ParseError("二进制 NBT 被截断或无效")
        start = self.pos
        self.pos += size
        return self.raw[start:self.pos]

    def number(self, fmt):
        return struct.unpack(">" + fmt, self.take(struct.calcsize(fmt)))[0]

    def string(self):
        start = self.pos
        value = decode_string(self.take(self.number("H")))
        return String(value, start, self.pos)

    def payload(self, tag, depth=0):
        if depth > 128:
            raise ParseError("二进制 NBT 嵌套超过 128 层")
        if tag in {1, 2, 3, 4, 5, 6}:
            return Atom(str(self.number({1: "b", 2: "h", 3: "i", 4: "q", 5: "f", 6: "d"}[tag])))
        if tag == 8:
            return self.string()
        if tag in {7, 11, 12}:
            count = self.number("i")
            self.take(count * {7: 1, 11: 4, 12: 8}[tag])
            return Atom("<array>")
        if tag == 9:
            child, count = self.number("B"), self.number("i")
            if count < 0 or count > len(self.raw) - self.pos or not 0 <= child <= 12 or (count and child == 0):
                raise ParseError("二进制 NBT 列表无效")
            return [self.payload(child, depth + 1) for _ in range(count)]
        if tag == 10:
            result = {}
            while True:
                child = self.number("B")
                if child == 0:
                    return result
                key = self.string().value
                if key in result:
                    raise ParseError(f"NBT 键重复：{key}")
                result[key] = self.payload(child, depth + 1)
        raise ParseError(f"未知的二进制 NBT 标签：{tag}")

    def parse(self):
        if self.number("B") != 10:
            raise ParseError("二进制 NBT 根标签必须是复合标签")
        self.string()  # Root name is metadata, not a translation target.
        result = self.payload(10)
        if self.pos != len(self.raw):
            raise ParseError("二进制 NBT 根标签后有多余字节")
        return result


def unpack(raw: bytes) -> tuple[bytes, bool]:
    compressed = raw.startswith(b"\x1f\x8b")
    try:
        return (gzip.decompress(raw) if compressed else raw), compressed
    except (OSError, EOFError, zlib.error) as exc:
        raise ParseError(f"压缩的二进制 NBT 无效：{exc}") from exc


def parse_nbt(raw: bytes):
    payload, _ = unpack(raw)
    return NBTParser(payload).parse()


def replace_nbt(raw: bytes, updates: list[tuple[String, str]]) -> bytes:
    payload, compressed = unpack(raw)
    original = payload
    previous = len(payload) + 1
    for node, value in sorted(updates, key=lambda pair: pair[0].start, reverse=True):
        if not 0 <= node.start < node.end <= len(original) or node.end > previous:
            raise ValueError("二进制 NBT 字符串替换无效或范围重叠")
        parser = NBTParser(original)
        parser.pos = node.start
        if parser.string() != node:
            raise ValueError("快照 NBT 范围与对应条目不匹配")
        payload = payload[:node.start] + encode_string(value) + payload[node.end:]
        previous = node.start
    NBTParser(payload).parse()
    return gzip.compress(payload, mtime=0) if compressed else payload
