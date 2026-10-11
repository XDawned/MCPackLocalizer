# [Module: tests.core.mods.compatibility] [Status: 已完成] [Brief: 复现 ProjectE 手册空格递归并验证补丁兼容处理]
import json
import zipfile

import pytest

from mcpacklocalizer.core.mods.compatibility import export_language_value
from mcpacklocalizer.core.mods.scan import ResourceOptions, detect, parse_language
from mcpacklocalizer.core.mods.tasks import build_mod_patch, create_mod_scan
from mcpacklocalizer.core.pack.extraction import Scan
from mcpacklocalizer.core.pack.patch import build_patch
from tests.core.mods.test_mod_scan import write_zip


def manual_wrap(text, width):
    """按 ProjectE 1.12 PE1.3.2h 的断行规则检查递归是否能推进。

    对应 ManualFontRenderer.sizeStringToWidth / wrapFormStringToWidth，
    测试字体采用中文 9 像素、英文 6 像素、空格 4 像素。
    """
    lines = []
    while text:
        size, last_space, index = 0, -1, 0
        while index < len(text):
            char = text[index]
            if char == "\n":
                last_space = index
                break
            if char == " ":
                last_space = index
            size += 4 if char.isspace() else 9 if ord(char) > 127 else 6
            if size > width:
                break
            index += 1
        split = last_space if index != len(text) and 0 <= last_space < index else index
        if split == len(text):
            lines.append(text)
            break
        consumed = split + (text[split] == "\n")
        if not consumed:
            raise ValueError("手册换行递归未消费任何字符")
        lines.append(text[:split])
        text = text[consumed:]
    return lines


@pytest.mark.parametrize("text", [
    "炼金术士喜欢闪闪发光的东西，它能存储 104 组物品，只需消耗一个闪亮物和一些共价尘。" * 3,
    " EMC 可由原材料供应，也可由依附的收集器供应。" * 3,
    "与其他固体燃料一样，Aeternalis 也可以被压缩成块状，既时尚又高效。" * 3,
])
def test_projecte_manual_wrap_advances_after_compatibility_export(text):
    with pytest.raises(ValueError, match="未消费"):
        manual_wrap(text, 90)
    fixed = export_language_value("projecte", "pe.manual.introduction", text, legacy=True)
    for width in (60, 90, 140, 180):
        assert "".join(manual_wrap(fixed, width)) == fixed
    assert fixed.replace("\u00a0", " ") == text
    assert export_language_value("projecte", "pe.manual.introduction", fixed, legacy=True) == fixed


@pytest.mark.parametrize("namespace, key, legacy", [
    ("projecte", "pe.command.showbag.usage", True),
    ("projecte", "pe.manual.img_alchchest.header", True),
    ("projecte", "pe.manual.introduction.header", True),
    ("projecte", "pe.manual.pe_alchemy_chest.header", True),
    ("projecte", "pe.manual.index_button", True),
    ("example", "pe.manual.introduction", True),
    ("projecte", "pe.manual.introduction", False),
])
def test_compatibility_preserves_commands_paths_titles_and_modern_languages(namespace, key, legacy):
    text = "中文 text %s §a更多文字"
    assert export_language_value(namespace, key, text, legacy=legacy) == text


@pytest.mark.parametrize("combined", [False, True])
@pytest.mark.parametrize("origin, status", [("model", "translated"), ("library", "reused"), ("manual", "reviewed")])
def test_projecte_export_repairs_existing_translations_without_changing_snapshot(tmp_path, combined, origin, status):
    root = tmp_path / "instance"
    english = {"pe.manual.introduction": "An introduction to alchemy.",
               "pe.manual.pe_alchemy_chest": "Stores 104 stacks.",
               "pe.command.showbag.usage": "/projecte showBag <color> <player selector>",
               "pe.manual.img_alchchest.header": "alchchest.png"}
    write_zip(root / "mods/projecte.jar", {"mcmod.info": json.dumps([{"modid": "projecte", "version": "1.3.2h"}]),
                                          "assets/projecte/lang/en_us.lang": "\n".join(
                                              f"{key}={value}" for key, value in english.items()) + "\n"})
    options = ResourceOptions("1.12.2", "forge", tmp_path / "cache", offline=True)
    options.pack_metadata = {"packFormat": 3}
    mods = create_mod_scan(detect(root, [], legacy=True), options, tmp_path / "library.sqlite3")
    translations = english | {"pe.manual.introduction": "介绍 EMC " + "炼金术的奥秘。" * 20,
                              "pe.manual.pe_alchemy_chest": "炼金箱能存储 104 组物品。"}
    for entry in mods.entries:
        entry.translation = translations[entry.path[0]]
        entry.origin, entry.status = origin, status
    if combined:
        scan = Scan(mods.root, mods.pack_id, mods.source_locale, mods.target_locale,
                    mods.documents, mods.entries, mods.warnings, {"mod_resources": mods.metadata})
    else:
        scan = mods
    output = tmp_path / "task"
    manifest = build_patch(scan, output) if combined else build_mod_patch(scan, output)
    with zipfile.ZipFile(output / "patch/resourcepacks/MCPackLocalizer-Mod-Translations.zip") as archive:
        content = archive.read("assets/projecte/lang/zh_cn.lang")
    values = parse_language(content, "lang")
    assert values["pe.command.showbag.usage"] == english["pe.command.showbag.usage"]
    assert values["pe.manual.img_alchchest.header"] == "alchchest.png"
    for key in ("pe.manual.introduction", "pe.manual.pe_alchemy_chest"):
        assert values[key].replace("\u00a0", " ") == translations[key]
        assert "".join(manual_wrap(values[key], 90)) == values[key]
    assert {entry.path[0]: entry.translation for entry in scan.entries} == translations
    assert {item["key"] for item in manifest["compatibility_adjustments"]} == {
        "pe.manual.introduction", "pe.manual.pe_alchemy_chest"}
    assert "栈溢出" in (output / "report.html").read_text(encoding="utf-8")
