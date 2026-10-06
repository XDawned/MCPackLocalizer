import json
import threading
from dataclasses import asdict
from pathlib import Path

import pytest

from mcpacklocalizer.application.config.settings import Settings
from mcpacklocalizer.application.tasks.jobs import Job
from mcpacklocalizer.application.tasks.requests import PatchOptions, task_job
from mcpacklocalizer.application.tasks.service import config_for, run_translation
from mcpacklocalizer.core.pack.extraction import Entry, Scan
from mcpacklocalizer.core.translation.api import ApiProfile
from mcpacklocalizer.core.translation.local import ModelConfig


def settings():
    profile = ApiProfile(id="remote", name="远程", base_url="https://example.test/v1", model="test-model", api_key="secret")
    return Settings(engine="api", active_api=profile.id, api_profiles=[asdict(profile)])


def test_api_settings_roundtrip_and_job_separates_credentials_from_saved_config():
    prefs = settings()
    restored = Settings.from_dict(asdict(prefs))
    assert restored == prefs
    args = Job("translate", text="Iron Ingot", **prefs.model_options())
    assert Job.from_payload(args.payload()) == args
    assert args.credentials == {"remote": "secret"}
    assert "secret" not in repr(args)
    cfg = config_for(args)
    assert cfg.api_model == "test-model" and cfg.engine == "api"
    assert "secret" not in json.dumps(asdict(cfg))


def test_resume_keeps_saved_profile_even_if_another_is_current():
    prefs = settings()
    prefs.api_profiles.append(asdict(ApiProfile(id="other", model="different", api_key="other-key")))
    prefs.active_api = "other"
    saved = asdict(config_for(Job("translate", text="Iron Ingot", **settings().model_options())))
    args = task_job("resume", "D:/task", prefs, PatchOptions())
    cfg = config_for(args, saved)
    assert cfg.api_profile_id == "remote" and cfg.api_model == "test-model"
    assert args.credentials["remote"] == "secret" and args.credentials["other"] == "other-key"
    override = config_for(task_job("resume", "D:/task", prefs, PatchOptions(), override_model=True), saved)
    assert override.api_profile_id == "other"


def test_resume_keeps_profile_timeout_and_override_selects_new_limits(mocker):
    prefs = settings()
    prefs.api_profiles[0].update(timeout=75, concurrency=4, max_tokens=1024)
    saved = asdict(config_for(Job("translate", **prefs.model_options())))
    prefs.api_profiles[0].update(timeout=120, concurrency=8, max_tokens=2048)
    prefs.timeout = 900
    args = task_job("resume", "D:/task", prefs, PatchOptions())
    config = config_for(args, saved)
    assert (config.request_timeout, config.concurrency, config.max_tokens) == (75, 4, 1024)
    from mcpacklocalizer.application.tasks.service import translation_client
    factory = mocker.patch("mcpacklocalizer.application.tasks.service.ApiClient")
    translation_client(config, args)
    assert factory.call_args.args[2] == 75
    override = config_for(task_job("resume", "D:/task", prefs, PatchOptions(), override_model=True), saved)
    assert (override.request_timeout, override.concurrency, override.max_tokens) == (120, 8, 2048)


def test_resume_explicit_settings_can_clear_external_glossary_override():
    cfg = config_for(Job("translate", text="Hello", glossary_overrides=""), asdict(ModelConfig(overrides="old.json")))
    assert not cfg.overrides


def test_old_model_snapshot_remains_local_with_fixed_template():
    saved = {"model": "old.gguf", "backend": "cpu", "max_tokens": 64}
    cfg = config_for(Job("resume", output="D:/task"), saved)
    assert cfg.engine == "local" and cfg.model == "old.gguf"


@pytest.mark.parametrize("field,value", [("concurrency", 0), ("retries", -1), ("request_interval", -1.0)])
def test_invalid_api_task_limits_are_rejected(field, value):
    with pytest.raises(ValueError):
        config_for(Job("translate", text="Hello", **{field: value}))


def test_concurrent_api_translation_deduplicates_and_commits_on_main_thread(mocker, capsys):
    entries = [Entry(str(i), "lang:key", "a.json", [str(i)], text, 1, 2, "key")
               for i, text in enumerate(["Iron Ingot", "Gold Ingot", "Iron Ingot"])]
    scan = Scan("C:/pack", "pack", "en_us", "zh_cn", entries=entries)
    store = mocker.Mock(output=Path("C:/output"))
    store.load.return_value = scan
    main_thread = threading.get_ident()
    writers = []
    store.update.side_effect = lambda entry: writers.append(threading.get_ident())
    model = mocker.patch("mcpacklocalizer.application.tasks.service.ApiClient").return_value.__enter__.return_value
    model.info = {"backend": "api"}
    model.usage_snapshot.return_value = {"requests": 2, "input_tokens": 10, "output_tokens": 4}
    barrier = threading.Barrier(2)
    translations = {"Iron Ingot": "铁锭", "Gold Ingot": "金锭"}

    def translate(source, context):
        assert threading.get_ident() != main_thread
        barrier.wait(timeout=5)
        return translations[source]

    model.translate.side_effect = translate
    mocker.patch("mcpacklocalizer.application.tasks.service.validate_sources")
    mocker.patch("mcpacklocalizer.application.tasks.service.export_task", return_value={"partial": False})
    options = settings().model_options()
    options.update(concurrency=2, no_glossary=True)
    args = Job("resume", output="C:/output", **options)
    result = run_translation(store, args)
    assert result["translated_this_run"] == 3
    assert model.translate.call_count == 2
    assert writers == [main_thread] * 3
    assert all(entry.origin == "api" for entry in entries)
    assert "secret" not in json.dumps(scan.metadata)
    assert len(capsys.readouterr().err.splitlines()) == 3


def test_changed_no_translate_policy_does_not_reuse_invalid_cached_translation(mocker):
    scan = Scan("C:/pack", "pack", "en_us", "zh_cn", entries=[
        Entry("one", "lang:key", "a.json", ["one"], "Use Create", 1, 2, "key", translation="使用创造"),
        Entry("two", "lang:key", "a.json", ["two"], "Use Create", 1, 2, "key")])
    store = mocker.Mock(output=Path("C:/output"))
    store.load.return_value = scan
    model = mocker.patch("mcpacklocalizer.application.tasks.service.WorkerClient").return_value.__enter__.return_value
    model.translate.return_value = "使用 Create"
    model.info = {"backend": "cpu"}
    mocker.patch("mcpacklocalizer.application.tasks.service.validate_sources")
    mocker.patch("mcpacklocalizer.application.tasks.service.export_task", return_value={})
    run_translation(store, Job("resume", output="C:/output", non_translate="Create"))
    model.translate.assert_called_once()
    assert scan.entries[1].translation == "使用 Create"
