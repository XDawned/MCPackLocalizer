# [Module: tests.core.formats.test_binary_nbt] [Status: 已完成] [Brief: 二进制任务扫描、快照和补丁数据保真测试]
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
@pytest.mark.parametrize("relative", ["config/ftbquests/chapters/A/quest.nbt", "questpacks/normal.nbt",
                                      "questpacks/expert.NBT"])
def test_old_layout_nbt_scan_patch_and_snapshot_preserve_all_other_bytes(memory_files, mocker, compressed, relative):
    raw = sample_nbt()
    filename = ROOT + "/" + relative
    memory_files[filename] = gzip.compress(raw) if compressed else raw
    scan = scan_pack(Path(ROOT))
    assert [(d.path, d.target, d.kind) for d in scan.documents] == [(relative, relative, "ftb-nbt")]
    assert [e.source for e in scan.entries] == ["Chapter", "Task"]
    assert any(e.semantic_key == "ftb:TASK/title/" for e in scan.entries)
    for entry in scan.entries:
        entry.translation = "章节😀" if entry.source == "Chapter" else "任务"
    portable = type(scan).from_dict(scan.to_dict())
    write = mocker.patch("mcpacklocalizer.core.pack.patch.atomic_write")
    build_patch(portable, Path("C:/mcpl-tests/out"))
    assert write.call_args_list[0].args[0] == Path("C:/mcpl-tests/out/patch") / relative
    result = write.call_args_list[0].args[1]
    assert result.startswith(b"\x1f\x8b") == compressed
    result = gzip.decompress(result) if compressed else result
    expected = raw.replace(encode_string("Chapter"), encode_string("章节😀"))
    expected = expected.replace(encode_string("Task"), encode_string("任务"))
    assert result == expected
    assert parse_nbt(result)["title"].value == "章节😀"
    assert reuse_baseline(scan_pack(Path(ROOT)), portable)["reused"] == 2


def test_questpacks_nested_chapters_and_multiple_modes_ignore_backups(memory_files):
    task = named(8, "title", encode_string("Task")) + b"\0"
    quest = (named(3, "uid", struct.pack(">i", 42)) + named(8, "title", encode_string("Quest"))
             + named(8, "description", encode_string("Description"))
             + named(9, "tasks", b"\x0a" + struct.pack(">i", 1) + task)
             + named(10, "item", named(8, "title", encode_string("保持物品数据")) + b"\0") + b"\0")
    chapter = (named(8, "title", encode_string("Chapter"))
               + named(9, "quests", b"\x0a" + struct.pack(">i", 1) + quest) + b"\0")
    raw = (b"\x0a\x00\x00" + named(8, "title", encode_string("Book"))
           + named(9, "chapters", b"\x0a" + struct.pack(">i", 1) + chapter) + b"\0")
    for mode in ("normal", "expert", "custom-mode"):
        memory_files[ROOT + f"/questpacks/{mode}.nbt"] = gzip.compress(raw)
    memory_files[ROOT + "/questpacks/backups/normal.nbt"] = gzip.compress(raw)
    memory_files[ROOT + "/questpacks/normal.nbt.bak"] = gzip.compress(raw)
    memory_files[ROOT + "/questpacks/readme.txt"] = "保持说明文件"
    scan = scan_pack(Path(ROOT), scope="resources")
    assert not scan.warnings
    assert {d.target for d in scan.documents} == {f"questpacks/{mode}.nbt" for mode in ("normal", "expert", "custom-mode")}
    assert [e.source for e in scan.entries] == ["Book", "Chapter", "Quest", "Description", "Task"] * 3
    assert any(e.path == ["chapters", 0, "quests", 0, "description"]
               and e.semantic_key == "ftb:42/description/" for e in scan.entries)
    assert not scan_pack(Path(ROOT), scope="kubejs").documents


def test_corrupt_questpack_reports_warning_without_hiding_valid_mode(memory_files):
    memory_files[ROOT + "/questpacks/normal.nbt"] = sample_nbt()
    memory_files[ROOT + "/questpacks/expert.nbt"] = b"\x1f\x8bBAD"
    scan = scan_pack(Path(ROOT), scope="resources")
    assert [d.path for d in scan.documents] == ["questpacks/normal.nbt"]
    assert len(scan.warnings) == 1 and "questpacks/expert.nbt" in scan.warnings[0]


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
