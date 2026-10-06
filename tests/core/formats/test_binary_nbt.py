import gzip
import struct
from pathlib import Path

import pytest

from mcpacklocalizer.core.formats.binary_nbt import decode_string, encode_string, parse_nbt, replace_nbt
from mcpacklocalizer.core.formats.documents import ParseError
from mcpacklocalizer.core.pack.extraction import scan_pack
from mcpacklocalizer.core.pack.patch import build_patch
from mcpacklocalizer.core.pack.snapshots import reuse_baseline

ROOT = "C:/mcpl-tests/pack"


def named(tag, name, payload):
    return bytes([tag]) + encode_string(name) + payload


def sample_nbt():
    task = named(8, "uid", encode_string("TASK")) + named(8, "title", encode_string("Task")) + b"\0"
    return (b"\x0a" + encode_string("root😀") + named(8, "title", encode_string("Chapter"))
            + named(9, "tasks", b"\x0a" + struct.pack(">i", 1) + task)
            + named(10, "item", named(8, "title", encode_string("Untouched"))
                    + named(8, "id", encode_string("minecraft:stone")) + b"\0")
            + named(4, "long", struct.pack(">q", 2**60 + 1))
            + named(5, "float", bytes.fromhex("7fc01234"))  # NaN payload must survive byte for byte.
            + named(7, "bytes", struct.pack(">i", 3) + b"\x00\x7f\xff")
            + named(11, "ints", struct.pack(">iii", 2, 1, -1))
            + named(12, "longs", struct.pack(">iq", 1, 2**60)) + b"\0")


def test_java_modified_utf8_and_byte_limit():
    text = 'NUL\0 😀 中文 " \\ \n'
    encoded = encode_string(text)
    assert b"\xc0\x80" in encoded and b"\xed\xa0\xbd\xed\xb8\x80" in encoded
    assert decode_string(encoded[2:]) == text
    with pytest.raises(ValueError, match="65535"):
        encode_string("中" * 22000)


@pytest.mark.parametrize("compressed", [False, True])
def test_old_layout_nbt_scan_patch_and_snapshot_preserve_all_other_bytes(memory_files, mocker, compressed):
    raw = sample_nbt()
    filename = ROOT + "/config/ftbquests/chapters/A/quest.nbt"
    memory_files[filename] = gzip.compress(raw) if compressed else raw
    scan = scan_pack(Path(ROOT))
    assert [e.source for e in scan.entries] == ["Chapter", "Task"]
    assert any(e.semantic_key == "ftb:TASK/title/" for e in scan.entries)
    for entry in scan.entries:
        entry.translation = "章节😀" if entry.source == "Chapter" else "任务"
    portable = type(scan).from_dict(scan.to_dict())
    write = mocker.patch("mcpacklocalizer.core.pack.patch.atomic_write")
    build_patch(portable, Path("C:/mcpl-tests/out"))
    result = write.call_args_list[0].args[1]
    assert result.startswith(b"\x1f\x8b") == compressed
    result = gzip.decompress(result) if compressed else result
    expected = raw.replace(encode_string("Chapter"), encode_string("章节😀"))
    expected = expected.replace(encode_string("Task"), encode_string("任务"))
    assert result == expected
    assert parse_nbt(result)["title"].value == "章节😀"
    assert reuse_baseline(scan_pack(Path(ROOT)), portable)["reused"] == 2


def test_binary_nbt_rejects_corrupt_data_and_tampered_spans():
    for raw in (b"", b"bad", sample_nbt()[:-1], sample_nbt() + b"extra", b"\x1f\x8bBAD"):
        with pytest.raises((ValueError, UnicodeError)):
            parse_nbt(raw)
    raw = sample_nbt()
    node = parse_nbt(raw)["title"]
    with pytest.raises(ValueError, match="范围"):
        replace_nbt(raw, [(type(node)("Wrong source", node.start, node.end), "译文")])
    with pytest.raises(ParseError):
        parse_nbt(b"\x0a\x00\x00" + named(7, "bad", struct.pack(">i", -1)) + b"\0")
