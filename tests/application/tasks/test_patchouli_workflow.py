import json
import zipfile

import pytest

from mcpacklocalizer.application.config.settings import Settings
from mcpacklocalizer.application.tasks.jobs import Job
from mcpacklocalizer.application.tasks.requests import PackRequest, PatchOptions, pack_job
from mcpacklocalizer.application.tasks.service import execute
from mcpacklocalizer.application.tasks.store import load_task
from mcpacklocalizer.core.mods.library import ModLibrary
from tests.core.mods.test_mod_scan import mod_fixture, write_zip
from tests.core.mods.test_mod_tasks import flags
from tests.core.pack.test_patchouli import book_files, mod, put


def test_patchouli_multiscope_checkpoint_resume_review_and_export(tmp_path, mocker):
    root, task = tmp_path / "game", tmp_path / "task"
    mod(root, book_files(pages=["Read$(br2)the guide"]))
    put(root, "config/ftbquests/quests/chapters/a.snbt", '{id:"a",title:"Quest"}')
    settings = Settings(glossary_enabled=False)
    request = PackRequest(str(root), str(task), game_version="1.20.1", recognition_scope=["resources", "patchouli"])
    job = pack_job("extract", request, settings, PatchOptions(include_i18n_mod=False))
    worker = mocker.patch("mcpacklocalizer.application.tasks.service.WorkerClient")
    execute(job)
    worker.assert_not_called()
    scan = load_task(str(task))
    assert scan.metadata["recognition_scopes"] == ["resources", "patchouli"]
    model = worker.return_value.__enter__.return_value
    model.info = {"backend": "test"}
    model.translate.side_effect = lambda source, context: source.replace("Read", "阅读") + "汉化"
    partial = execute(Job("resume", output=task, limit=1, allow_partial=True, no_glossary=True))
    assert partial["pending_entries"] == len(scan.entries) - 1
    result = execute(Job("resume", output=task, no_glossary=True))
    assert not result["partial"]
    scan = load_task(str(task))
    entry = next(e for e in scan.entries if e.source == "Read$(br2)the guide")
    assert any("{{MCPL_PATCHOULI_" in call.args[0] for call in model.translate.call_args_list)
    with pytest.raises(ValueError):
        execute(Job("review", output=task, entry_id=entry.id, translation="丢失标记"))
    execute(Job("review", output=task, entry_id=entry.id, translation="阅读$(br2)手册"))
    execute(Job("export", output=task))
    output = task / "patch/resourcepacks/MCPackLocalizer-Patchouli/assets/demo/patchouli_books/guide/zh_cn/entries/start.json"
    assert json.loads(output.read_bytes())["pages"][0] == "阅读$(br2)手册"
    assert load_task(str(task)).entries[-1].translation is not None
    assert "MCPackLocalizer-Patchouli" in (task / "report.html").read_text(encoding="utf-8")


def test_mixed_mod_and_patchouli_task_reuses_existing_keys_and_shared_library(tmp_path, mocker):
    root, sources = mod_fixture(tmp_path, english={"iron": "Iron %s"})
    jar = root / "mods/example.jar"
    with zipfile.ZipFile(jar) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    files.update(book_files(declaration={"name": "Guide", "landing_text": "Welcome",
                                        "i18n": True, "use_resource_pack": True}, pages=["iron"]))
    write_zip(jar, files)
    task = tmp_path / "task"
    execute(Job("extract", root=root, output=task, recognition_scope=["mods", "patchouli"], **flags(tmp_path, sources)))
    scan = load_task(str(task))
    assert len([e for e in scan.entries if e.source == "Iron %s"]) == 1
    assert not any(d.kind == "patchouli-lang" for d in scan.documents)
    model = mocker.patch("mcpacklocalizer.application.tasks.service.WorkerClient").return_value.__enter__.return_value
    model.info = {"backend": "test"}
    model.translate.side_effect = lambda source, context: source.replace("Iron", "铁") + "汉化"
    result = execute(Job("resume", output=task, no_glossary=True))
    assert result["coverage_complete"] and not result["partial"]
    assert (task / "patch/mods/example.jar").is_file()
    assert (task / "patch/resourcepacks/MCPackLocalizer-Mod-Translations.zip").is_file()
    scan = load_task(str(task))
    entry = next(e for e in scan.entries if e.semantic_key.startswith("mod:"))
    execute(Job("review", output=task, entry_id=entry.id, translation="铁 %s"))
    with ModLibrary(tmp_path / "shared.sqlite3", readonly=True) as library:
        assert library.stats()["states"]["reviewed"] == 1
    execute(Job("export", output=task))
    with zipfile.ZipFile(task / "patch/resourcepacks/MCPackLocalizer-Mod-Translations.zip") as archive:
        assert json.loads(archive.read("assets/example/lang/zh_cn.json")) == {"iron": "铁 %s"}


def test_mixed_mod_language_tooltip_uses_one_composite_output(tmp_path, mocker):
    root, sources = mod_fixture(tmp_path, english={"iron": "$(t:Hint)Iron$(/t)"})
    jar = root / "mods/example.jar"
    with zipfile.ZipFile(jar) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    files.update(book_files(declaration={"name": "Guide", "landing_text": "Welcome",
                                        "i18n": True, "use_resource_pack": True}, pages=["iron"]))
    write_zip(jar, files)
    task = tmp_path / "task"
    execute(Job("extract", root=root, output=task, recognition_scope=["mods", "patchouli"], **flags(tmp_path, sources)))
    scan = load_task(str(task))
    assert len([e for e in scan.entries if e.source == "$(t:Hint)Iron$(/t)"]) == 1
    model = mocker.patch("mcpacklocalizer.application.tasks.service.WorkerClient").return_value.__enter__.return_value
    model.info = {"backend": "test"}
    model.translate.side_effect = lambda source, context: source.replace("Iron", "铁").replace("Hint", "提示")
    execute(Job("resume", output=task, no_glossary=True))
    values = json.loads((task / "patch/resourcepacks/MCPackLocalizer-Patchouli/assets/example/lang/zh_cn.json").read_bytes())
    assert values == {"iron": "$(t:提示)铁$(/t)"}
    with zipfile.ZipFile(task / "patch/resourcepacks/MCPackLocalizer-Mod-Translations.zip") as archive:
        assert "assets/example/lang/zh_cn.json" not in archive.namelist()
