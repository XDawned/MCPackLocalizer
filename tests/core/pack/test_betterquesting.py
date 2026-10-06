import json
from pathlib import Path

import pytest

from mcpacklocalizer.core.formats.documents import Parser
from mcpacklocalizer.core.formats.rendering import render_document
from mcpacklocalizer.core.pack.extraction import scan_pack
from mcpacklocalizer.core.pack.patch import build_patch

ROOT = "C:/mcpl-tests/pack"
FILE = ROOT + "/config/betterquesting/DefaultQuests.json"


def test_old_bq_compound_collections_keep_paths_and_untranslated_properties(memory_files):
    data = {"format:8": "2.0.0", "questDatabase:9": {"0:10": quest(0), "1:10": quest(8)},
            "questLines:9": {"0:10": {"lineID:3": 7, "properties:10": {
                "betterquesting:10": {"name:8": "Chapter", "desc:8": "Description"}}}}}
    memory_files[FILE] = json.dumps(data)
    scan = scan_pack(Path(ROOT), scope="resources")
    assert len(scan.entries) == 6 and not scan.warnings
    assert scan.entries[0].path == ["questDatabase:9", "0:10", "properties:10", "betterquesting:10", "name:8"]
    for entry in scan.entries:
        entry.translation = "中文" + entry.source
    rendered = json.loads(render_document(scan.documents[0], scan.entries))
    assert rendered["questDatabase:9"]["0:10"]["questID:3"] == 0
    assert rendered["questDatabase:9"]["0:10"]["tasks:9"] == data["questDatabase:9"]["0:10"]["tasks:9"]
    assert rendered["questDatabase:9"]["0:10"]["properties:10"]["betterquesting:10"]["name:8"] == "中文Quest 0"
    assert rendered["questLines:9"]["0:10"]["lineID:3"] == 7


def quest(identity, typed=True):
    suffix = lambda key, tag: f"{key}:{tag}" if typed else key
    return {suffix("questID", 3): identity,
            suffix("properties", 10): {suffix("betterquesting", 10): {
                suffix("name", 8): f"Quest {identity}", suffix("desc", 8): 'Line 1\n"Line 2" &a%s',
                suffix("icon", 10): {suffix("name", 8): "DO NOT TRANSLATE"}}},
            suffix("tasks", 9): [{suffix("command", 8): "say untouched"}],
            suffix("preRequisites", 11): [10]}


@pytest.mark.parametrize("typed", [True, False])
def test_bq_display_fields_only_and_stable_ids_across_reordering(memory_files, mocker, typed):
    database = "questDatabase:9" if typed else "questDatabase"
    memory_files[FILE] = json.dumps({database: [quest(1, typed), quest(2, typed)], "questLines:9": [
        {"lineID:3": 1, "properties:10": {"betterquesting:10": {"name:8": "Chapter", "desc:8": "Description"}}}]})
    memory_files[ROOT + "/config/betterquesting/QuestProgress.json"] = '{"name:8":"Ignored progress"}'
    memory_files[ROOT + "/config/betterquesting/backup/DefaultQuests.json"] = memory_files[FILE]
    scan = scan_pack(Path(ROOT))
    assert len(scan.entries) == 6 and not scan.warnings
    ids = {entry.semantic_key: entry.id for entry in scan.entries}
    assert "bq:questDatabase/1/name" in ids and "bq:questLines/1/name" in ids
    data = json.loads(memory_files[FILE])
    data[database].reverse()
    memory_files[FILE] = json.dumps(data)
    scan = scan_pack(Path(ROOT))
    assert ids == {entry.semantic_key: entry.id for entry in scan.entries}
    for entry in scan.entries:
        entry.translation = "中文" + entry.source
    write = mocker.patch("mcpacklocalizer.core.pack.patch.atomic_write")
    build_patch(scan, Path("C:/mcpl-tests/output"))
    result = write.call_args_list[0].args[1].decode()
    parsed = Parser(result, "json").parse()
    assert parsed[database][0]["questID:3" if typed else "questID"].raw == "2"
    assert "say untouched" in result and "DO NOT TRANSLATE" in result
    assert '中文Line 1\\n\\"Line 2\\" &a%s' in result


def test_duplicate_bq_id_reports_file_error_without_partial_extraction(memory_files):
    memory_files[FILE] = json.dumps({"questDatabase:9": [quest(1), quest(1)]})
    scan = scan_pack(Path(ROOT))
    assert not scan.entries
    assert any("Better Questing 标识重复" in warning for warning in scan.warnings)


def test_legacy_uid_and_image_hover_and_pagebreak(memory_files):
    memory_files[ROOT + "/config/ftbquests/chapters/A/quest.snbt"] = '''{
        title: "Quest", text: ["Hello", "{@pagebreak}", "{image:test}"],
        images: [{hover: ["Image tooltip"]}], tasks: [{uid: 10, title: "Task"}],
        rewards: [{uid: 11, title: "Reward", item: {tag: {display: {Name: "Untouched"}}}}]
    }'''
    scan = scan_pack(Path(ROOT))
    assert [e.source for e in scan.entries] == ["Quest", "Hello", "Image tooltip", "Task", "Reward"]
    assert scan.metadata["preserved_directives"] == 2
    assert any(e.semantic_key == "ftb:10/title/" for e in scan.entries)


def test_old_pack_modes_are_discovered_and_backups_are_ignored(memory_files):
    for mode in ("normal", "expert", "custom-mode", "backups"):
        memory_files[ROOT + f"/config/ftbquests/{mode}/chapters/A/quest.snbt"] = '{title:"' + mode + '"}'
        memory_files[ROOT + f"/config/ftbquests/{mode}/file.snbt"] = '{title:"Book ' + mode + '"}'
    scan = scan_pack(Path(ROOT))
    assert len(scan.entries) == 6
    assert {e.source for e in scan.entries} == {"normal", "expert", "custom-mode", "Book normal", "Book expert", "Book custom-mode"}


def test_existing_locale_references_are_preserved(memory_files):
    memory_files[ROOT + "/config/ftbquests/normal/chapters/A/chapter.snbt"] = '{title:"{ftbquests.chapter.A.title}"}'
    memory_files[FILE] = json.dumps({"questDatabase:9": [{"questID:3": 1,
        "properties:10": {"betterquesting:10": {"name:8": "pack.quest.one", "desc:8": "bq.quest1.desc"}}}]})
    memory_files[ROOT + "/resources/assets/custom/lang/en_us.json"] = '{"pack.quest.one":"Quest One"}'
    scan = scan_pack(Path(ROOT))
    assert [e.source for e in scan.entries] == ["Quest One"]
    assert scan.metadata["preserved_language_references"] == 3
    assert any("未解析的 BQ 语言键" in warning for warning in scan.warnings)
    memory_files[ROOT + "/resources/assets/custom/lang/zh_cn.json"] = '{"pack.quest.one":"已有译文"}'
    scan = scan_pack(Path(ROOT))
    assert not scan.entries and scan.metadata["preserved_language_references"] == 3
