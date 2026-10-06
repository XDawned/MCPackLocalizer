# [Module: tests.tasks.resource_exclusions] [Status: 已完成] [Brief: 手动排除持久化、续跑过滤、恢复与旧补丁归档回归]
import json
import zipfile

import pytest

from mcpacklocalizer.application.tasks.jobs import Job
from mcpacklocalizer.application.tasks.service import execute
from mcpacklocalizer.application.tasks.store import load_task, task_counts


@pytest.fixture
def exclusion_task(tmp_path):
    root = tmp_path / "game"
    quest = root / "config/ftbquests/quests/chapters/first.snbt"
    quest.parent.mkdir(parents=True)
    quest.write_text('{id:"first",title:"First Steps"}', encoding="utf-8")
    language = root / "kubejs/assets/demo/lang/en_us.json"
    language.parent.mkdir(parents=True)
    language.write_text('{"item.demo.iron":"Iron"}', encoding="utf-8")
    output = tmp_path / "task"
    execute(Job("extract", root=root, output=output, recognition_scope="resources"))
    return root, output, quest.relative_to(root).as_posix()


def exclusion(output, paths, action="exclude"):
    return execute(Job("resource-exclusion", output=output, resource_paths=paths, resource_action=action))


def test_exclusion_persists_and_counts_only_active_entries(exclusion_task):
    _, output, document = exclusion_task
    result = exclusion(output, [document])
    scan = load_task(str(output))
    assert result["excluded_documents"] == 1
    assert scan.metadata["manual_excluded_resources"] == [document]
    assert task_counts(scan) == {"pending": 1, "total": 1, "complete": 0, "remaining": 1, "excluded": 1}
    assert len(scan.entries) == 2
    assert not (output / "patch").exists()
    exclusion(output, [document], "restore")
    assert task_counts(load_task(str(output)))["remaining"] == 2


def test_resume_does_not_translate_excluded_entries(exclusion_task, mocker):
    _, output, document = exclusion_task
    exclusion(output, [document])
    client = mocker.patch("mcpacklocalizer.application.tasks.service.translation_client")
    model = client.return_value.__enter__.return_value
    model.info = {}
    model.translate.return_value = "铁"
    execute(Job("resume", output=output, no_glossary=True))
    model.translate.assert_called_once()
    assert model.translate.call_args.args[0] == "Iron"
    scan = load_task(str(output))
    assert next(e for e in scan.entries if e.document == document).translation is None
    assert not (output / "patch" / document).exists()


def test_exclusion_archives_owned_inline_patch_and_restore_reuses_translation(exclusion_task):
    root, output, document = exclusion_task
    original = (root / document).read_bytes()
    scan = load_task(str(output))
    for entry in scan.entries:
        execute(Job("review", output=output, entry_id=entry.id, translation="汉化文本"))
    execute(Job("export", output=output))
    patch = output / "patch" / document
    translated = patch.read_bytes()
    exclusion(output, [document])
    assert not patch.exists()
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    backup = next(record for record in manifest["excluded_resource_backups"] if record["path"] == document)
    assert (output / backup["backup"]).read_bytes() == translated
    assert (root / document).read_bytes() == original
    exclusion(output, [document], "restore")
    assert patch.read_bytes() == translated
    assert next(e for e in load_task(str(output)).entries if e.document == document).translation == "汉化文本"


def test_unknown_resource_is_rejected_without_changing_checkpoint(exclusion_task):
    _, output, _ = exclusion_task
    before = (output / "snapshot.json").read_bytes()
    with pytest.raises(ValueError, match="不属于当前任务"):
        exclusion(output, ["other/book.json"])
    assert (output / "snapshot.json").read_bytes() == before


def test_key_only_book_can_be_saved_as_inspectable_task(tmp_path):
    root = tmp_path / "game"
    jar = root / "mods/demo.jar"
    jar.parent.mkdir(parents=True)
    with zipfile.ZipFile(jar, "w") as archive:
        archive.writestr("data/demo/patchouli_books/guide/book.json",
                         json.dumps({"name": "book.demo.name", "use_resource_pack": True}))
    output = tmp_path / "task"
    result = execute(Job("extract", root=root, output=output, recognition_scope="patchouli"))
    assert result["entries"] == 0 and result["warnings"]
    scan = load_task(str(output))
    assert len(scan.documents) == 1 and scan.documents[0].resource["recognition_warnings"]


@pytest.mark.parametrize("paths,action", [([], "exclude"), (["a", "a"], "exclude"), ([1], "exclude"),
                                        (["a"], "delete")])
def test_invalid_exclusion_requests_are_rejected(paths, action):
    with pytest.raises(ValueError):
        Job("resource-exclusion", output="D:/task", resource_paths=paths, resource_action=action)
