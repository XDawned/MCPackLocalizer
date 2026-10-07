# [Module: tests.model_setup] [Status: 已完成] [Brief: 本地接口弹窗、配置迁移、独立激活和下载续传回归]
import json
from dataclasses import asdict

import pytest
from PyQt6.QtCore import QEvent
from qfluentwidgets import SubtitleLabel

from mcpacklocalizer.application.config.interfaces import LEGACY_LOCAL_ID, profile_for_model
from mcpacklocalizer.application.config.settings import Settings
from mcpacklocalizer.application.tasks.models import MODEL_VARIANTS, model_spec
from mcpacklocalizer.core.translation.api import INDEX_PROFILE_ID, ApiProfile
from mcpacklocalizer.ui.view.api.dialogs import AddApiDialog
from mcpacklocalizer.ui.view.api.local import LocalEditDialog, LocalParametersDialog
from mcpacklocalizer.ui.view.window import MainWindow


@pytest.fixture
def setup_window(qt_app, mocker, tmp_path):
    windows = []
    stored = {}
    mocker.patch("mcpacklocalizer.application.tasks.models.MODEL_HOME", tmp_path / "program")
    destination = model_spec("7b").path
    mocker.patch.object(Settings, "defaults", side_effect=lambda: Settings(model=str(tmp_path / "missing.gguf"), glossary=""))

    def create(settings=None):
        for previous in windows:
            previous.close()
            previous.deleteLater()
        windows.clear()
        qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qt_app.processEvents()
        preferences = mocker.Mock()
        values = {"settings": json.dumps(asdict(settings))} if settings is not None else dict(stored)
        preferences.value.side_effect = lambda key, default="": values.get(key, default)
        preferences.setValue.side_effect = lambda key, value: (values.update({key: value}), stored.update({key: value}))
        window = MainWindow(preferences)
        mocker.patch.object(window, "notify")
        mocker.patch.object(window.runner, "start")
        windows.append(window)
        return window

    yield create, destination
    for window in windows:
        window.runner.busy = False
        if window.rules.loader:
            window.rules.loader.wait(5000)
            qt_app.processEvents()
        window.close()
        window.deleteLater()
    qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qt_app.processEvents()


def local_dialog(window, variant="7b"):
    dialog = AddApiDialog(window)
    dialog.select_platform("gguf")
    assert not dialog.validate() and dialog.stack.currentIndex() == 2
    dialog.local_details.source.setCurrentIndex(dialog.local_details.source.findData("preset"))
    dialog.local_details.variant.setCurrentIndex(dialog.local_details.variant.findData(variant))
    return dialog


def accept_local(window, mocker, variant="7b"):
    dialog = local_dialog(window, variant)
    assert dialog.validate()
    profile = dialog.profile
    mocker.patch.object(dialog, "exec", return_value=1)
    window.api.run_editor(dialog)
    return profile


def test_first_launch_opens_interfaces_without_setup_form_or_automatic_download(setup_window):
    create, _ = setup_window
    window = create()
    assert window.stackedWidget.currentWidget() == window.api
    assert INDEX_PROFILE_ID in window.api.cards and LEGACY_LOCAL_ID not in window.api.cards
    assert "本地专用翻译模型" not in [label.text() for label in window.api.findChildren(SubtitleLabel)]
    assert not hasattr(window.api, "model_variant")
    window.runner.start.assert_not_called()


@pytest.mark.parametrize("variant", list(MODEL_VARIANTS))
def test_add_dialog_contains_local_presets_and_binds_the_correct_template(setup_window, variant):
    create, _ = setup_window
    window = create()
    dialog = local_dialog(window, variant)
    assert dialog.validate()
    assert dialog.profile.model == str(model_spec(variant).path)
    assert dialog.profile.template_id == model_spec(variant).template_id
    assert dialog.yesButton.text() == "添加并下载"
    assert dialog.download_local
    dialog.deleteLater()


def test_existing_local_model_is_kept_when_adding_index(setup_window, mocker, tmp_path):
    create, _ = setup_window
    hy = tmp_path / "Hy-MT2-1.8B-Q4_K_M.gguf"
    hy.write_bytes(b"GGUF-hy")
    window = create(Settings(model=str(hy), local_template_id="index", glossary=""))
    assert "HY-MT-2" in window.api.cards[LEGACY_LOCAL_ID].buttons[0].text()
    profile = accept_local(window, mocker, "index-2b")
    assert LEGACY_LOCAL_ID in window.api.cards and profile.id in window.api.cards
    assert window.settings.model == str(hy) and window.api.cards[LEGACY_LOCAL_ID].active
    job = window.runner.start.call_args.args[0]
    assert job.operation == "download-model" and job.download_variant == "index-2b"
    assert hy.read_bytes() == b"GGUF-hy"


def test_successful_download_activates_only_the_new_interface_and_survives_restart(setup_window, mocker, tmp_path):
    create, _ = setup_window
    hy = tmp_path / "Hy-MT2-1.8B-Q4_K_M.gguf"
    hy.write_bytes(b"GGUF-hy")
    window = create(Settings(model=str(hy), glossary=""))
    profile = accept_local(window, mocker, "index-2b")
    path = model_spec("index-2b").path
    path.parent.mkdir(parents=True)
    path.write_bytes(b"GGUF-index")
    window.job_done(0, {"model": str(path), "download_variant": "index-2b"}, False)
    assert window.settings.active_local == profile.id and window.api.cards[profile.id].active
    assert not window.api.cards[LEGACY_LOCAL_ID].active and hy.read_bytes() == b"GGUF-hy"
    assert window.settings_page.model.text() == str(path)
    restored = create()
    assert restored.api.cards[profile.id].active and LEGACY_LOCAL_ID in restored.api.cards
    assert restored.stackedWidget.currentWidget() == restored.workspace
    restored.runner.start.assert_not_called()


@pytest.mark.parametrize("cancelled", [False, True])
def test_failed_or_paused_download_can_be_resumed_from_the_saved_interface(setup_window, mocker, cancelled):
    create, _ = setup_window
    window = create()
    profile = accept_local(window, mocker, "1.8b")
    previous_model = window.settings.model
    window.job_done(130 if cancelled else 2, {"error": "连接失败"}, cancelled)
    assert window.settings.model == previous_model and not window.api.cards[profile.id].active
    assert "暂停" in window.api.model_status.text() if cancelled else "连接失败" in window.api.model_status.text()
    restored = create()
    restored.api.activate(profile.id)
    assert restored.runner.start.call_args.args[0].output == model_spec("1.8b").path


def test_existing_model_is_added_from_dialog_without_downloading(setup_window, mocker, tmp_path):
    create, _ = setup_window
    model = tmp_path / "Hy-MT2-1.8B-Q4_K_M.gguf"
    model.write_bytes(b"GGUF")
    window = create()
    dialog = local_dialog(window)
    dialog.local_details.source.setCurrentIndex(dialog.local_details.source.findData("existing"))
    dialog.local_details.model.setText(str(model))
    assert not dialog.local_details.variant.isEnabled()
    assert dialog.validate() and not dialog.download_local
    profile = dialog.profile
    assert profile.template_id == "hy_mt" and profile.download_variant == "1.8b"
    mocker.patch.object(dialog, "exec", return_value=1)
    window.api.run_editor(dialog)
    window.runner.start.assert_not_called()
    assert profile.id in window.api.cards
    window.api.activate(profile.id)
    assert window.settings.model == str(model) and window.api.cards[profile.id].active


def test_local_model_path_can_be_changed_without_renaming_or_losing_other_interfaces(setup_window, tmp_path):
    create, _ = setup_window
    hy = tmp_path / "Hy-MT2-1.8B-Q4_K_M.gguf"
    hy.write_bytes(b"GGUF")
    index = tmp_path / "Index-Translate-2B.Q4_K_M.gguf"
    index.write_bytes(b"GGUF")
    window = create(Settings(model=str(hy), glossary=""))
    other = profile_for_model(str(index), "index", "index-2b", profile_id="index")
    window.api.store_profile(other)
    window.api.activate(other.id)
    dialog = LocalEditDialog(window.api.get_local_profile(LEGACY_LOCAL_ID), window)
    dialog.details.template.setCurrentIndex(dialog.details.template.findData("index_plain"))
    assert dialog.validate()
    window.api.store_profile(dialog.profile)
    assert window.settings.active_local == other.id and window.api.cards[other.id].active
    assert "HY-MT-2" in window.api.cards[LEGACY_LOCAL_ID].buttons[0].text()
    window.api.activate(LEGACY_LOCAL_ID)
    assert window.settings.model_options()["prompt_template_id"] == "index_plain"
    assert window.settings.model_options()["model_family"] == "hy_mt"
    dialog.deleteLater()


def test_local_parameters_are_independent_between_models(setup_window, tmp_path):
    create, _ = setup_window
    hy, index = tmp_path / "hy.gguf", tmp_path / "Index-Translate-2B.Q4_K_M.gguf"
    hy.write_bytes(b"GGUF")
    index.write_bytes(b"GGUF")
    window = create(Settings(model=str(hy), glossary=""))
    profile = profile_for_model(str(index), "index", "index-2b", profile_id="index")
    window.api.store_profile(profile)
    dialog = LocalParametersDialog(profile, window)
    dialog.numbers["max_tokens"].setValue(256)
    assert dialog.validate()
    window.api.store_profile(dialog.profile)
    window.api.activate("index")
    assert window.settings.model_options()["max_tokens"] == 256
    window.api.activate(LEGACY_LOCAL_ID)
    assert window.settings.model_options()["max_tokens"] == 768
    dialog.deleteLater()


def test_removing_local_interface_does_not_delete_the_model_or_resurrect_it(setup_window, mocker, tmp_path):
    create, _ = setup_window
    model = tmp_path / "hy.gguf"
    model.write_bytes(b"GGUF")
    window = create(Settings(model=str(model), glossary=""))
    mocker.patch("mcpacklocalizer.ui.view.api.page.MessageBox.exec", return_value=1)
    window.api.remove(LEGACY_LOCAL_ID)
    assert LEGACY_LOCAL_ID not in window.api.cards and model.read_bytes() == b"GGUF"
    restored = create()
    assert LEGACY_LOCAL_ID not in restored.api.cards and not restored.settings.interface_ready()


def test_local_and_remote_testing_does_not_change_the_active_interface(setup_window, mocker, tmp_path):
    create, _ = setup_window
    model = tmp_path / "hy.gguf"
    model.write_bytes(b"GGUF")
    window = create(Settings(model=str(model), glossary=""))
    window.api.store_profile(ApiProfile(id="remote", model="large", base_url="https://example.test/v1"))
    window.api.activate("remote")
    calls = []
    mocker.patch.object(window, "run_job", side_effect=lambda factory, label: calls.append(factory()))
    window.api.test(LEGACY_LOCAL_ID)
    assert calls[0].engine == "local" and calls[0].model == str(model)
    assert window.settings.engine == "api" and window.settings.active_api == "remote"


def test_download_progress_and_busy_state_are_shown_without_configuration_controls(setup_window, mocker):
    create, _ = setup_window
    window = create()
    profile = accept_local(window, mocker)
    window.runner.busy = True
    window.busy_changed(True)
    assert not window.api.add_button.isEnabled() and not window.api.pause_download.isHidden()
    window.api.update_progress({"operation": "download-model", "completed": 50, "failed": 0, "remaining": 50,
                                "total": 100, "phase": "正在下载模型"})
    assert window.api.download_progress.value() == 50
    assert not window.api.cards[profile.id].actions["activate"][0].isEnabled()
    window.runner.busy = False
    window.busy_changed(False)
    assert window.api.add_button.isEnabled() and window.api.pause_download.isHidden()


def test_custom_download_destination_is_preserved(setup_window, tmp_path):
    create, _ = setup_window
    window = create()
    dialog = local_dialog(window, "index-2b")
    destination = tmp_path / "other" / model_spec("index-2b").filename
    dialog.local_details.model.setText(str(destination))
    assert dialog.validate() and dialog.profile.model == str(destination)
    dialog.deleteLater()
