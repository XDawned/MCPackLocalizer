# [Module: tests.paths] [Status: 已完成] [Brief: 已有任务及术语设置的迁移兼容]
from dataclasses import asdict
from pathlib import Path

from mcpacklocalizer.application.config.settings import Settings
from mcpacklocalizer.application.tasks.jobs import Job
from mcpacklocalizer.application.tasks.service import config_for
from mcpacklocalizer.core.translation.local import ModelConfig
from mcpacklocalizer.paths import migrated_path


def test_old_task_and_glossary_paths_resolve_only_if_migrated_target_exists(mocker):
    workspace = Path("D:/project")
    mocker.patch("mcpacklocalizer.paths.WORKSPACE", workspace)
    exists = mocker.patch("pathlib.Path.exists", return_value=True)
    assert migrated_path("D:/project/cli/output/task") == str(workspace / "data/tasks/task")
    assert migrated_path("D:/project/common/glossary_en_zh.json") == str(workspace / "resources/glossary/glossary_en_zh.json")
    assert migrated_path("D:/another/cli/output/task") == "D:/another/cli/output/task"
    exists.return_value = False
    assert migrated_path("D:/project/cli/output/task") == "D:/project/cli/output/task"


def test_persisted_glossary_and_output_home_follow_migration(mocker):
    mocker.patch("mcpacklocalizer.paths.WORKSPACE", Path("D:/project"))
    mocker.patch("pathlib.Path.exists", return_value=True)
    settings = Settings.from_dict({"glossary": "D:/project/common/glossary_en_zh.json",
                                  "output_home": "D:/project/cli/output"})
    assert Path(settings.glossary) == Path("D:/project/resources/glossary/glossary_en_zh.json")
    assert Path(settings.output_home) == Path("D:/project/data/tasks")


def test_resume_remaps_saved_glossary_without_mutating_checkpoint_config(mocker):
    mocker.patch("mcpacklocalizer.paths.WORKSPACE", Path("D:/project"))
    mocker.patch("pathlib.Path.exists", return_value=True)
    saved = asdict(ModelConfig(glossary="D:/project/common/glossary_en_zh.json"))
    config = config_for(Job("resume", output="D:/project/cli/output/task"), saved)
    assert Path(config.glossary) == Path("D:/project/resources/glossary/glossary_en_zh.json")
    assert saved["glossary"] == "D:/project/common/glossary_en_zh.json"


def test_structured_job_remaps_task_library_and_cache_paths(mocker):
    mocker.patch("mcpacklocalizer.paths.WORKSPACE", Path("D:/project"))
    mocker.patch("pathlib.Path.exists", return_value=True)
    job = Job("resume", output="D:/project/cli/output/task", cache="D:/project/cache",
              translation_library="D:/project/cache/shared.sqlite3")
    assert job.output == Path("D:/project/data/tasks/task")
    assert job.translation_library == Path("D:/project/data/legacy/cache/shared.sqlite3")
    assert job.cache == Path("D:/project/data/legacy/cache")
