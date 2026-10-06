import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest

from mcpacklocalizer.core.pack.extraction import Scan
from mcpacklocalizer.ui.components.scope_selector import ScopeSelector
from tests.ui.test_translation_pages import window as window  # noqa: PLC0414 -- shared pytest fixture


def test_scope_checkboxes_allow_multiple_choices_and_keep_menu_open(qt_app):
    selector = ScopeSelector()
    try:
        selector.show()
        selector.setSelectedData("resources")
        QTest.mouseClick(selector, Qt.MouseButton.LeftButton)
        qt_app.processEvents()
        assert selector.menu().isVisible()
        box = selector.checkboxes["patchouli"]
        assert box.isEnabled()
        QTest.mouseClick(box, Qt.MouseButton.LeftButton, pos=QPoint(12, box.height() // 2))
        assert selector.selectedData() == ["resources", "patchouli"]
        assert selector.menu().isVisible()
        assert "帕秋莉手册" in selector.text()
        box = selector.checkboxes["mods"]
        QTest.mouseClick(box, Qt.MouseButton.LeftButton, pos=QPoint(12, box.height() // 2))
        assert selector.selectedData() == ["resources", "patchouli", "mods"]
        selector.setSelectedData("all")
        assert selector.selectedData() == ["resources", "kubejs", "patchouli"]
    finally:
        selector.menu().close()
        selector.close()
        selector.deleteLater()


def test_restoring_multiscope_task_and_changing_selection_invalidates_checkpoint(window):
    page = window.workspace.recognition
    scan = Scan("C:/game", "test", "en_us", "zh_cn", metadata={"recognition_scopes": ["patchouli", "mods"]})
    window.workspace.bind_task(scan, "C:/task")
    assert page.mode.selectedData() == ["patchouli", "mods"]
    assert page.cfpa.isEnabled() and page.baseline.isEnabled()
    page.mode.setSelectedData("mods")
    assert not window.workspace.task_path
    assert not page.baseline.isEnabled()


@pytest.mark.parametrize("scope", ["all", "resources", "kubejs", "patchouli"])
def test_scope_restores_legacy_single_choice(scope, qt_app):
    selector = ScopeSelector()
    selector.setSelectedData(scope)
    assert scope == "all" or selector.selectedData() == [scope]
    selector.deleteLater()
