# [Module: desktop.test_commands] [Status: 已完成] [Brief: 结构化任务协议、路径安全及配置继承]
from pathlib import Path

import pytest

from mcpacklocalizer.application.config.settings import Settings
from mcpacklocalizer.application.tasks.requests import (
    PackRequest,
    PatchOptions,
    language_job,
    new_task_output,
    pack_job,
    review_job,
    task_job,
)


@pytest.mark.parametrize("mods,action", [(False, "scan"), (False, "extract"), (False, "localize"),
                                        (False, "diff"), (True, "scan"), (True, "extract"), (True, "localize")])
def test_pack_jobs_create_structured_requests(mocker, mods, action):
    mocker.patch("pathlib.Path.is_dir", return_value=True)
    request = PackRequest("D:/games/pack", "D:/tasks/pack", "same-pack", "D:/tasks/old", mods=mods,
                          offline=True, cfpa_pack="D:/cfpa.zip", game_version="1.21.1", loader="neoforge")
    patch = PatchOptions(allow_partial=True, offline=True, game_version="1.21.1", loader="neoforge")
    args = pack_job(action, request, Settings(), patch, limit=20)
    parsed = args
    assert parsed.operation == action + ("-mods" if mods else "")
    assert parsed.pack_id == "same-pack"
    if action == "localize":
        assert parsed.limit == 20
        assert parsed.allow_partial
        assert parsed.allow_missing_placeholders is False
        assert args.game_version == "1.21.1"


@pytest.mark.parametrize("output", ["D:/games/pack", "D:/games/pack/output", "D:/games"])
def test_cannot_put_output_in_or_above_game(mocker, output):
    mocker.patch("pathlib.Path.is_dir", return_value=True)
    with pytest.raises(ValueError, match="实例之外"):
        pack_job("extract", PackRequest("D:/games/pack", output), Settings(), PatchOptions())


def test_screenshot_mplt_output_is_rejected_before_recognition(mocker):
    mocker.patch("pathlib.Path.is_dir", return_value=True)
    root = "D:/Game/MC/.minecraft/versions/Forever Stranded"
    with pytest.raises(ValueError, match="实例之外"):
        pack_job("extract", PackRequest(root, root + "/.mplt"), Settings(), PatchOptions())


def test_new_task_output_preserves_custom_external_location(mocker):
    create = mocker.patch("pathlib.Path.mkdir")
    output = Path(new_task_output("D:/games/pack", "D:/translations"))
    assert output.parent == Path("D:/translations")
    create.assert_not_called()


def test_invalid_default_inside_game_falls_back_to_external_home(mocker):
    mocker.patch("mcpacklocalizer.application.tasks.requests.DATA_HOME", Path("C:/user-data/MCPackLocalizer"))
    root = "D:/Game/MC/.minecraft/versions/Forever Stranded"
    output = Path(new_task_output(root, root + "/.mplt"))
    assert output.parent == Path("C:/user-data/MCPackLocalizer/tasks")
    assert not output.is_relative_to(Path(root))


def test_task_home_above_game_can_generate_a_safe_sibling():
    output = Path(new_task_output("D:/games/pack", "D:/games"))
    assert output.parent == Path("D:/games")
    assert not output.is_relative_to(Path("D:/games/pack"))


def test_diff_requires_baseline(mocker):
    mocker.patch("pathlib.Path.is_dir", return_value=True)
    with pytest.raises(ValueError, match="上一版本"):
        pack_job("diff", PackRequest("D:/game"), Settings(), PatchOptions())


def test_multiple_recognition_scopes_keep_pack_job_and_forward_version(mocker):
    mocker.patch("pathlib.Path.is_dir", return_value=True)
    request = PackRequest("D:/game", "D:/task", recognition_scope=["patchouli", "mods"],
                          game_version="1.20.1", loader="forge", offline=True)
    job = pack_job("extract", request, Settings(), PatchOptions())
    assert job.operation == "extract"
    assert job.recognition_scope == ["patchouli", "mods"]
    assert job.game_version == "1.20.1" and job.offline
    plain = pack_job("extract", PackRequest("D:/game", "D:/task", recognition_scope=["patchouli"],
                                           game_version="1.20.1"), Settings(), PatchOptions())
    assert plain.game_version == "1.20.1"


def test_multiple_scopes_reject_empty_selection_and_unsupported_mod_language(mocker):
    mocker.patch("pathlib.Path.is_dir", return_value=True)
    with pytest.raises(ValueError, match="至少选择"):
        pack_job("scan", PackRequest("D:/game", recognition_scope=[]), Settings(), PatchOptions())
    with pytest.raises(ValueError, match="模组共享译库"):
        pack_job("scan", PackRequest("D:/game", recognition_scope=["patchouli", "mods"]),
                 Settings(source_locale="ja_jp"), PatchOptions())


def test_missing_root_is_rejected(mocker):
    mocker.patch("pathlib.Path.is_dir", return_value=False)
    with pytest.raises(ValueError, match="不存在"):
        pack_job("scan", PackRequest("D:/missing"), Settings(), PatchOptions())


def test_resume_inherits_saved_model_policy():
    settings = Settings(allow_missing_placeholders=True)
    args = task_job("resume", "D:/task", settings, PatchOptions(), limit=2)
    parsed = args
    assert parsed.allow_missing_placeholders is None
    assert parsed.model is None
    assert parsed.limit == 2
    assert parsed.runtime_python == settings.runtime_python


def test_resume_explicit_override_applies_model_and_policy():
    args = task_job("resume", "D:/task", Settings(allow_missing_placeholders=True), PatchOptions(),
                        override_model=True)
    assert args.allow_missing_placeholders is True


def test_export_does_not_send_model_options():
    args = task_job("export", "D:/task", Settings(), PatchOptions(include_i18n_mod=True))
    assert args.include_i18n_mod
    assert args.model is None


def test_review_keeps_multiline_text_and_special_characters():
    text = "第一行\n&6第二行 &r %s \"带引号\""
    parsed = review_job("D:/task with space", "id-1", text)
    assert parsed.translation == text
    assert str(parsed.output) == "D:\\task with space"


def test_review_empty_text_is_rejected():
    with pytest.raises(ValueError, match="不能为空"):
        review_job("D:/task", "id", " \n")


@pytest.mark.parametrize("action", ["extract-lang", "backfill", "convert-lang"])
def test_language_tools_parse(action):
    args = language_job(action, "D:/game", "D:/output", "D:/en_us.json", "json5", PatchOptions(True, True),
                        source_locale="ja_jp", target_locale="en_us")
    parsed = args
    assert parsed.operation == action
    if action == "backfill":
        assert parsed.allow_partial and parsed.replace_existing_locale
    else:
        assert parsed.format == "json5"
    if action == "extract-lang":
        assert (parsed.source_locale, parsed.target_locale) == ("ja_jp", "en_us")
