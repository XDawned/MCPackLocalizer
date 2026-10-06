import json
from dataclasses import asdict

import pytest
from PyQt6.QtCore import QEvent

from mcpacklocalizer.application.config.settings import Settings
from mcpacklocalizer.core.pack.extraction import Scan
from mcpacklocalizer.core.translation.api import ApiProfile
from mcpacklocalizer.ui.view.window import MainWindow


@pytest.fixture
def kubejs_window(qt_app, mocker):
    preferences = mocker.Mock()
    preferences.value.side_effect = lambda key, default="": json.dumps(asdict(Settings(glossary=""))) if key == "settings" else default
    window = MainWindow(preferences)
    mocker.patch.object(window, "notify")
    yield window
    if window.rules.loader:
        window.rules.loader.wait(5000)
    window.close()
    window.deleteLater()
    qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qt_app.processEvents()


def test_default_all_and_kubejs_selection_reaches_background_job(kubejs_window, mocker):
    workspace = kubejs_window.workspace
    assert "kubejs" in workspace.mode.selectedData()
    assert "resources" in workspace.mode.selectedData()
    workspace.mode.setSelectedData("kubejs")
    workspace.root.setText("D:/games/test")
    workspace.output.setText("D:/tasks/test")
    mocker.patch("pathlib.Path.is_dir", return_value=True)
    jobs = []
    mocker.patch.object(kubejs_window, "run_job", side_effect=lambda factory, *args: jobs.append(factory()))
    workspace.start("extract")
    assert jobs[0].recognition_scope == ["kubejs"] and jobs[0].operation == "extract"


def test_script_profile_is_independent_and_edit_preserves_normal_engine(kubejs_window):
    kubejs_window.api.store_profile(ApiProfile(id="large", name="脚本接口", model="large-model"))
    selector = kubejs_window.workspace.translation.script_api
    selector.setCurrentIndex(selector.findData("large"))
    assert kubejs_window.settings.script_api == "large"
    assert kubejs_window.settings.engine == "local"
    assert kubejs_window.settings.script_options()["api_model"] == "large-model"


def test_kubejs_scope_roundtrips_when_opening_existing_task(kubejs_window):
    scan = Scan("D:/games/test", "test", "en_us", "zh_cn", metadata={"recognition_scope": "kubejs"})
    kubejs_window.workspace.bind_task(scan, "D:/tasks/test")
    assert kubejs_window.workspace.mode.selectedData() == ["kubejs"]
    assert kubejs_window.workspace.task_path == "D:/tasks/test"
