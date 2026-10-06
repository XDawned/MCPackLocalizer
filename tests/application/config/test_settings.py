# [Module: desktop.test_settings] [Status: 已完成] [Brief: 配置兼容性、环境变量与参数校验]
from dataclasses import asdict, replace

import pytest

from mcpacklocalizer.application.config.settings import Settings
from mcpacklocalizer.core.translation.api import ApiProfile


def test_roundtrip():
    settings = Settings(backend="vulkan", allow_missing_placeholders=True, output_home="D:/tasks")
    assert Settings.from_dict(asdict(settings)) == settings


def test_invalid_persisted_types_and_unknown_keys_are_ignored():
    settings = Settings.from_dict({"threads": "64", "allow_missing_placeholders": "false", "api_key": "secret"})
    assert settings.threads == 0
    assert settings.allow_missing_placeholders is False
    assert not hasattr(settings, "api_key")


def test_invalid_persisted_ranges_reset_defaults():
    settings = Settings.from_dict({"max_tokens": -4, "backend": "invalid"})
    settings.validate()
    assert settings.max_tokens > 0


def test_environment_runtime_wins_over_discovered_vulkan(mocker, monkeypatch):
    mocker.patch("pathlib.Path.is_file", return_value=True)
    monkeypatch.setenv("MPLT_RUNTIME_PYTHON", "D:/runtime/python.exe")
    monkeypatch.setenv("MPLT_MODEL_PATH", "D:/model.gguf")
    monkeypatch.setenv("MPLT_DATA_DIR", "D:/data")
    settings = Settings.defaults()
    assert settings.runtime_python == "D:/runtime/python.exe"
    assert settings.model == "D:/model.gguf"
    assert settings.output_home.replace("\\", "/") == "D:/data/tasks"
    assert settings.backend == "auto"


@pytest.mark.parametrize("field,value", [("threads", -1), ("gpu_layers", -2), ("context_size", 128),
                                         ("max_tokens", 0), ("timeout", 0), ("theme", "invalid"),
                                         ("theme_color", "red"), ("theme_color", "#3268c")])
def test_reject_invalid_settings(field, value):
    settings = Settings()
    setattr(settings, field, value)
    with pytest.raises(ValueError):
        settings.validate()


def test_output_must_fit_context():
    with pytest.raises(ValueError, match="输出"):
        Settings(context_size=512, max_tokens=512).validate()


def test_glossary_off_does_not_inject_paths():
    args = Settings(glossary_enabled=False, overrides="overrides.json").model_options()
    assert args["no_glossary"] is True
    assert "glossary" not in args
    assert "glossary_overrides" not in args


def test_local_and_each_api_keep_independent_limits():
    profiles = [ApiProfile(id="local-api", model="small", context_size=8192, max_tokens=1024,
                           term_tokens=256, timeout=180, concurrency=2, retries=1, request_interval=0.5),
                ApiProfile(id="cloud", model="large", base_url="https://example.test/v1",
                           context_size=65536, max_tokens=8192, term_tokens=2048, timeout=60,
                           concurrency=8, retries=4, request_interval=1.5)]
    settings = Settings(context_size=2048, max_tokens=128, term_tokens=64, timeout=900,
                        api_profiles=[asdict(p) for p in profiles], script_api="cloud")
    local = settings.model_options()
    assert (local["context_size"], local["max_tokens"], local["term_tokens"], local["timeout"]) == (2048, 128, 64, 900)
    assert "concurrency" not in local and "request_interval" not in local
    for profile in profiles:
        options = replace(settings, engine="api", active_api=profile.id).model_options()
        for key in ("context_size", "max_tokens", "term_tokens", "timeout", "concurrency", "retries", "request_interval"):
            assert options[key] == getattr(profile, key)
    script = settings.script_options()
    assert (script["max_tokens"], script["concurrency"], script["request_timeout"]) == (8192, 8, 60)
    assert Settings.from_dict(asdict(settings)) == settings


def test_legacy_shared_limits_migrate_once_without_overwriting_profile_values():
    old = {"max_tokens": 256, "context_size": 16384, "term_tokens": 128, "timeout": 600,
           "concurrency": 3, "retries": 4, "request_interval": 0.7,
           "api_profiles": [{"id": "old", "model": "small"},
                            {"id": "explicit", "model": "large", "max_tokens": 2048, "concurrency": 8}]}
    migrated = Settings.from_dict(old)
    first, second = (ApiProfile(**p) for p in migrated.api_profiles)
    assert (first.max_tokens, first.timeout, first.concurrency, first.retries, first.request_interval) == (256, 600, 3, 4, 0.7)
    assert second.max_tokens == 2048 and second.concurrency == 8
    assert "concurrency" not in asdict(migrated)
    migrated.max_tokens, migrated.timeout = 512, 900
    restored = Settings.from_dict(asdict(migrated))
    assert restored.api_profiles == migrated.api_profiles
    assert restored.max_tokens == 512 and restored.timeout == 900
    # New profiles receive their own defaults, irrespective of the old limits.
    assert ApiProfile(id="new", model="new").concurrency == 1


@pytest.mark.parametrize("field,value", [("max_tokens", 0), ("context_size", 128), ("term_tokens", -1),
                                         ("concurrency", 0), ("concurrency", True), ("timeout", 0),
                                         ("retries", 11), ("request_interval", float("nan"))])
def test_reject_invalid_profile_limits(field, value):
    profile = ApiProfile(id="test", model="model")
    setattr(profile, field, value)
    with pytest.raises(ValueError):
        profile.validate()


def test_api_output_must_fit_its_own_context():
    with pytest.raises(ValueError, match="输出"):
        ApiProfile(id="test", model="model", context_size=512, max_tokens=512).validate()
