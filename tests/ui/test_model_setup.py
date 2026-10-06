# [Module: tests.model_setup] [Status: 已完成] [Brief: 首次启动导航与本地、远端模型激活流程]
import json
from dataclasses import asdict

import pytest
from PyQt6.QtCore import QEvent

from mcpacklocalizer.application.config.settings import Settings
from mcpacklocalizer.application.tasks.models import model_spec
from mcpacklocalizer.core.translation.api import ApiProfile
from mcpacklocalizer.ui.view.api.page import BUILTIN_LOCAL
from mcpacklocalizer.ui.view.window import MainWindow


@pytest.fixture
def setup_window(qt_app, mocker, tmp_path):
    windows = []
    stored = {}
    mocker.patch("mcpacklocalizer.application.tasks.models.MODEL_HOME", tmp_path / "program")
    destination = model_spec("7b").path
    mocker.patch.object(Settings, "defaults", side_effect=lambda: Settings(
        model=str(tmp_path / "missing.gguf"), glossary=""))

    def create(settings=None):
        # 模拟重启时先完成旧窗口与刷新卡片的延迟销毁，再刷新全局主题。
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


def test_first_launch_opens_interfaces_without_automatic_download(setup_window):
    create, _ = setup_window
    window = create()
    assert window.stackedWidget.currentWidget() == window.api
    assert not window.api.cards[BUILTIN_LOCAL].active
    assert window.api.cards[BUILTIN_LOCAL].actions["activate"][0].isEnabled()
    window.runner.start.assert_not_called()


def test_saved_missing_local_model_returns_to_interfaces(setup_window):
    create, _ = setup_window
    window = create(Settings(model="", glossary=""))
    assert window.stackedWidget.currentWidget() == window.api
    assert "尚未激活" in window.api.status.text()


def test_first_launch_opens_interfaces_even_with_discovered_model(setup_window, mocker, tmp_path):
    create, _ = setup_window
    model = tmp_path / "existing.gguf"
    model.write_bytes(b"GGUF")
    mocker.patch.object(Settings, "defaults", return_value=Settings(model=str(model), glossary=""))
    window = create()
    assert window.stackedWidget.currentWidget() == window.api
    assert window.api.cards[BUILTIN_LOCAL].active


def test_local_activation_starts_download_and_stays_on_interfaces(setup_window, mocker):
    create, destination = setup_window
    window = create()
    discard = mocker.patch.object(window.review, "discard_changes", return_value=False)
    window.api.local_button.click()
    job = window.runner.start.call_args.args[0]
    assert job.operation == "download-model" and job.output == destination
    assert window.pending_label == "模型下载"
    assert window.stackedWidget.currentWidget() == window.api
    assert not window.api.cards[BUILTIN_LOCAL].active
    discard.assert_not_called()


def test_successful_download_persists_model_and_next_launch_opens_workspace(setup_window):
    create, destination = setup_window
    window = create()
    window.api.activate(BUILTIN_LOCAL)
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"GGUF")
    window.job_done(0, {"model": str(destination)}, False)
    assert window.settings.model == str(destination) and window.settings.engine == "local"
    assert window.settings_page.model.text() == str(destination)
    assert window.api.cards[BUILTIN_LOCAL].active
    assert window.stackedWidget.currentWidget() == window.api
    restored = create()
    assert restored.settings.model == str(destination)
    assert restored.stackedWidget.currentWidget() == restored.workspace
    restored.runner.start.assert_not_called()


@pytest.mark.parametrize("cancelled", [False, True])
def test_failed_or_paused_download_does_not_activate_and_can_retry(setup_window, cancelled):
    create, _ = setup_window
    window = create()
    previous_model = window.settings.model
    window.api.activate(BUILTIN_LOCAL)
    window.job_done(130 if cancelled else 2, {"error": "连接失败"}, cancelled)
    assert window.settings.model == previous_model
    assert not window.api.cards[BUILTIN_LOCAL].active
    assert "暂停" in window.api.model_status.text() if cancelled else "连接失败" in window.api.model_status.text()
    window.api.local_button.click()
    assert window.runner.start.call_count == 2


def test_remote_activation_never_downloads_gguf_and_is_restored(setup_window):
    create, _ = setup_window
    window = create()
    window.api.store_profile(ApiProfile(id="remote", model="hy-mt", base_url="https://example.test/v1"))
    window.api.activate("remote")
    assert window.settings.engine == "api" and window.api.cards["remote"].active
    window.runner.start.assert_not_called()
    restored = create()
    assert restored.stackedWidget.currentWidget() == restored.workspace
    restored.runner.start.assert_not_called()


def test_select_existing_model_activates_without_download(setup_window, mocker, tmp_path):
    create, _ = setup_window
    model = tmp_path / "existing.gguf"
    model.write_bytes(b"GGUF")
    window = create()
    mocker.patch("mcpacklocalizer.ui.view.api.page.QFileDialog.getOpenFileName", return_value=(str(model), ""))
    window.api.select_model()
    assert window.settings.model == str(model) and window.api.cards[BUILTIN_LOCAL].active
    window.runner.start.assert_not_called()


def test_already_downloaded_default_model_is_reused(setup_window):
    create, destination = setup_window
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"GGUF")
    window = create()
    window.api.activate(BUILTIN_LOCAL)
    assert window.settings.model == str(destination) and window.api.cards[BUILTIN_LOCAL].active
    window.runner.start.assert_not_called()


def test_download_progress_and_busy_controls_are_on_interfaces(setup_window):
    create, _ = setup_window
    window = create()
    window.pending_label = "模型下载"
    window.runner.busy = True
    window.busy_changed(True)
    assert not window.api.local_button.isEnabled() and not window.api.choose_model.isEnabled()
    assert not window.api.model_variant.isEnabled()
    assert not window.api.pause_download.isHidden()
    assert not window.api.cards[BUILTIN_LOCAL].actions["activate"][0].isEnabled()
    window.runner.progress.emit({"operation": "download-model", "completed": 2312324448, "failed": 0,
                                 "remaining": 2312324448, "total": 4624648896, "phase": "正在下载模型"})
    assert window.api.download_progress.value() == 50
    assert "正在下载模型" in window.api.model_status.text()
    window.api.activate(BUILTIN_LOCAL)
    window.runner.start.assert_not_called()
    window.runner.busy = False
    window.busy_changed(False)
    assert window.api.local_button.isEnabled() and window.api.pause_download.isHidden()


def test_small_model_choice_is_persisted_and_sent_to_worker(setup_window):
    create, _ = setup_window
    window = create()
    window.api.model_variant.setCurrentIndex(window.api.model_variant.findData("1.8b"))
    assert window.settings.download_variant == "1.8b"
    assert "1.13 GB" in window.api.model_variant.currentText()
    window.api.local_button.click()
    job = window.runner.start.call_args.args[0]
    assert job.download_variant == "1.8b" and job.output == model_spec("1.8b").path
    window.job_done(130, {}, True)
    restored = create()
    assert restored.api.model_variant.currentData() == "1.8b"
    assert restored.stackedWidget.currentWidget() == restored.api
    restored.api.local_button.click()
    assert restored.runner.start.call_args.args[0].output == job.output


def test_small_model_can_be_downloaded_with_large_model_already_active(setup_window):
    create, large = setup_window
    large.parent.mkdir(parents=True)
    large.write_bytes(b"GGUF")
    window = create(Settings(model=str(large), glossary=""))
    window.api.model_variant.setCurrentIndex(window.api.model_variant.findData("1.8b"))
    assert window.settings.model == str(large)
    window.api.local_button.click()
    small = model_spec("1.8b").path
    job = window.runner.start.call_args.args[0]
    assert job.output == small and job.download_variant == "1.8b"
    small.parent.mkdir(parents=True)
    small.write_bytes(b"GGUF")
    window.job_done(0, {"model": str(small), "download_variant": "1.8b"}, False)
    assert window.settings.model == str(small) and large.read_bytes() == b"GGUF"
    window.api.model_variant.setCurrentIndex(window.api.model_variant.findData("7b"))
    window.api.local_button.click()
    assert window.settings.model == str(large)
    assert window.runner.start.call_count == 1


def test_selected_small_model_already_on_disk_is_activated_without_download(setup_window):
    create, _ = setup_window
    small = model_spec("1.8b").path
    small.parent.mkdir(parents=True)
    small.write_bytes(b"GGUF")
    window = create()
    window.api.model_variant.setCurrentIndex(window.api.model_variant.findData("1.8b"))
    assert window.api.local_button.text() == "激活1.8B 模型"
    window.api.local_button.click()
    assert window.settings.model == str(small)
    window.runner.start.assert_not_called()
