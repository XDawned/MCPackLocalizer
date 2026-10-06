# [Module: tests.extraction] [Status: 开发中] [Brief: 老版内嵌、新版单文件/拆分语言文件识别]
from pathlib import Path

import pytest

from mcpacklocalizer.core.pack.extraction import scan_pack

ROOT = "C:/mcpl-tests/pack"
QUESTS = ROOT + "/config/ftbquests/quests/"


def test_inline_only_translates_quest_objects_not_item_nbt(memory_files):
    memory_files[QUESTS + "chapters/one.snbt"] = '''{
      id: "CHAPTER" title: "Chapter" quests: [{id: "QUEST" title: "Quest"
      description: ["Line" ""] tasks: [{id: "TASK" title: "Task"
      item: {id: "minecraft:stone" tag: {title: "Do not translate"}}}]
      rewards: [{id: "REWARD" title: "Reward" command: "say do not translate"}]}]
    }'''
    scan = scan_pack(Path(ROOT))
    assert [e.source for e in scan.entries] == ["Chapter", "Quest", "Line", "Task", "Reward"]
    assert any(e.semantic_key == "ftb:QUEST/description/0" for e in scan.entries)
    assert scan.documents[0].target == "config/ftbquests/quests/chapters/one.snbt"


def test_flat_and_split_locales_and_case_variants(memory_files):
    memory_files[QUESTS + "lang/en_US.snbt"] = '{quest.A.title: "Iron Ingot"}'
    memory_files[QUESTS + "lang/en_us/chapters/one.json5"] = "{'quest.B.quest_desc': ['Hello', 'world'],}"
    memory_files[QUESTS + "lang/zh_cn.snbt"] = '{quest.A.title: "Existing"}'
    memory_files[QUESTS + "lang/recovery/en_us_123.snbt"] = '{quest.C.title: "Old"}'
    memory_files[ROOT + "/mods/example.jar"] = "not even opened"
    scan = scan_pack(Path(ROOT))
    assert len(scan.entries) == 3
    assert {d.target for d in scan.documents} == {"config/ftbquests/quests/lang/zh_cn.snbt",
        "config/ftbquests/quests/lang/zh_cn/chapters/one.json5"}


def test_pack_languages_and_parse_failures_are_reported(memory_files):
    memory_files[ROOT + "/kubejs/assets/custom/lang/en_us.json"] = '{"item.custom.name":"Test"}'
    memory_files[QUESTS + "chapters/bad.snbt"] = '{title: "unterminated}'
    memory_files[QUESTS + "old.nbt"] = "binary"
    scan = scan_pack(Path(ROOT))
    assert len(scan.entries) == 1
    assert any("无法处理" in w for w in scan.warnings)
    assert any("NBT" in w for w in scan.warnings)


def test_stable_identity_survives_quest_reordering(memory_files):
    file = QUESTS + "chapters/a.snbt"
    memory_files[file] = '{id:"C" quests:[{id:"A" title:"First"} {id:"B" title:"Second"}]}'
    first = {e.source: e.id for e in scan_pack(Path(ROOT)).entries}
    memory_files[file] = '{id:"C" quests:[{id:"B" title:"Second"} {id:"A" title:"First"}]}'
    assert first == {e.source: e.id for e in scan_pack(Path(ROOT)).entries}


@pytest.mark.parametrize("assets,filename", [
    ("kubejs/assets/minecraft", "zh_cn.json"),
    ("kubejs/assets/custom", "ZH_CN.json5"),
    ("resources/assets/custom", "zh_CN.lang")])
def test_existing_resource_locale_is_preserved_across_namespace_case_and_format(memory_files, assets, filename):
    directory = ROOT + "/" + assets + "/lang/"
    memory_files[directory + "en_us.json"] = '{"item.custom.a":"English","item.custom.b":"Missing in Chinese"}'
    memory_files[directory + filename] = '{}'  # Preserve even partial or intentionally empty locale overrides.
    scan = scan_pack(Path(ROOT))
    assert scan.entries == [] and scan.documents == []
    assert scan.metadata["excluded_resources"] == [{"source": assets + "/lang/en_us.json",
        "target": assets + "/lang/" + filename, "reason": "existing-target-locale"}]


def test_locale_descriptor_is_not_translated_without_target_file(memory_files):
    memory_files[ROOT + "/kubejs/assets/minecraft/lang/en_us.json"] = '''{
        "language.name":"English", "language.region":"United States", "language.code":"en_us",
        "event.minecraft.raid":"\\uE903", "chat.type.text":"%s > %s"}'''
    scan = scan_pack(Path(ROOT))
    assert not scan.entries
    assert scan.metadata["excluded_resources"][0]["reason"] == "locale-descriptor"


def test_minecraft_custom_text_without_existing_locale_is_still_translatable(memory_files):
    memory_files[ROOT + "/kubejs/assets/minecraft/lang/en_us.json"] = '{"item.minecraft.stone":"Custom Stone","event.minecraft.raid":"\\uE903"}'
    scan = scan_pack(Path(ROOT))
    assert [e.source for e in scan.entries] == ["Custom Stone"]
