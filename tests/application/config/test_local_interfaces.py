# [Module: tests.config.local_interfaces] [Status: 已完成] [Brief: 本地接口迁移、模型身份与独立参数的配置回归]
from dataclasses import asdict, replace

import pytest

from mcpacklocalizer.application.config.interfaces import LEGACY_LOCAL_ID, profile_for_model
from mcpacklocalizer.application.config.settings import Settings
from mcpacklocalizer.core.translation.api import ApiProfile


def test_legacy_hy_model_does_not_become_index_when_bound_to_index_template(tmp_path):
    hy = tmp_path / "Hy-MT2-1.8B-Q4_K_M.gguf"
    hy.write_bytes(b"GGUF")
    data = asdict(Settings(model=str(hy), local_template_id="index", download_variant="7b", max_tokens=128))
    data.pop("local_profiles")
    data.pop("active_local")
    restored = Settings.from_dict(data)
    profile = restored.current_local_profile()
    assert profile.id == LEGACY_LOCAL_ID and profile.download_variant == "1.8b"
    assert "HY-MT-2" in restored.engine_label() and "Index-Translate" not in restored.engine_label()
    options = restored.model_options()
    assert options["model"] == str(hy) and options["model_family"] == "hy_mt"
    assert options["prompt_family"] == "index" and options["max_tokens"] == 128


def test_legacy_local_history_is_recovered_without_discarding_api_profiles(tmp_path):
    hy, index = tmp_path / "Hy-MT2-1.8B-Q4_K_M.gguf", tmp_path / "Index-Translate-2B.Q4_K_M.gguf"
    api = ApiProfile(id="api", name="远端", model="large", base_url="https://example.test/v1")
    restored = Settings.from_dict({"model": str(hy), "local_model_templates": {str(hy): "hy_mt", str(index): "index"},
                                   "engine": "api", "active_api": "api", "api_profiles": [asdict(api)]})
    profiles = restored.local_interfaces()
    assert len(profiles) == 2 and {p.model_family for p in profiles} == {"hy_mt", "index"}
    assert {p.download_variant for p in profiles} == {"1.8b", "index-2b"}
    assert restored.engine == "api" and restored.selected_profile().id == "api"
    assert Settings.from_dict(asdict(restored)) == restored


def test_model_switches_preserve_individual_paths_templates_and_parameters(tmp_path):
    hy, index = tmp_path / "Hy-MT2-1.8B-Q4_K_M.gguf", tmp_path / "Index-Translate-2B.Q4_K_M.gguf"
    hy.write_bytes(b"GGUF")
    index.write_bytes(b"GGUF")
    settings = Settings(model=str(hy), glossary="")
    profile = profile_for_model(str(index), "index_plain", "index-2b", profile_id="index", parameters={"max_tokens": 256})
    settings = settings.store_local_profile(profile)
    old = asdict(settings)
    settings = settings.use_local_profile("index")
    assert settings.model_options()["max_tokens"] == 256
    assert settings.model_options()["prompt_template_id"] == "index_plain"
    settings = settings.use_local_profile(LEGACY_LOCAL_ID)
    assert settings.model_options()["max_tokens"] == 768 and settings.model == str(hy)
    assert settings.local_profiles == old["local_profiles"]
    assert Settings.from_dict(asdict(settings)) == settings


def test_local_profile_edit_while_api_is_active_preserves_remote_selection(tmp_path):
    path = tmp_path / "Hy-MT2-1.8B-Q4_K_M.gguf"
    path.write_bytes(b"GGUF")
    api = ApiProfile(id="api", model="large")
    settings = Settings(model=str(path), engine="api", active_api="api", api_profiles=[asdict(api)])
    local = replace(settings.current_local_profile(), template_id="index")
    updated = settings.store_local_profile(local)
    assert updated.engine == "api" and updated.active_api == "api"
    assert "HY-MT-2" in updated.local_interfaces()[0].name


def test_invalid_legacy_variant_resets_defaults_without_raising(tmp_path):
    path = tmp_path / "model.gguf"
    path.write_bytes(b"GGUF")
    restored = Settings.from_dict({"model": str(path), "download_variant": "invalid"})
    assert restored.download_variant == "7b"


def test_local_profile_cannot_share_identity_with_api(tmp_path):
    path = tmp_path / "Hy-MT2-1.8B-Q4_K_M.gguf"
    profile = profile_for_model(str(path), profile_id="same")
    settings = Settings(local_profiles=[asdict(profile)], api_profiles=[asdict(ApiProfile(id="same", model="large"))])
    with pytest.raises(ValueError, match="标识"):
        settings.validate()
