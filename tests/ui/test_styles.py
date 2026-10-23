# [Module: tests.styles] [Status: 已完成] [Brief: 样式缓存所有权、Fluent 创建入口及原生 GC 生命周期回归]
import gc
import os
import subprocess
import sys
import weakref
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtWidgets import QStyle, QStyleFactory, QWidget
from qfluentwidgets.common import style_sheet
from qfluentwidgets.components.widgets import menu

from mcpacklocalizer.ui.styles import PinnedStyleFactory, pin_fluent_styles


def test_factory_styles_are_owned_by_application_and_cached_case_insensitively(qt_app):
    style = PinnedStyleFactory.create("fusion")
    assert style is PinnedStyleFactory.create("FUSION")
    assert style.parent() is qt_app
    assert not sip.ispyowned(style)
    assert PinnedStyleFactory.keys() == QStyleFactory.keys()
    assert PinnedStyleFactory.create("mcpl-不存在的样式") is None


def test_menu_style_cache_preserves_icon_sizes_and_application_ownership(qt_app):
    small = menu.CustomMenuStyle()
    large = menu.CustomMenuStyle(iconSize=24)
    assert small is menu.CustomMenuStyle(14)
    assert large is menu.CustomMenuStyle(24)
    assert small is not large
    assert small.pixelMetric(QStyle.PixelMetric.PM_SmallIconSize, None, None) == 14
    assert large.pixelMetric(QStyle.PixelMetric.PM_SmallIconSize, None, None) == 24
    assert small.parent() is large.parent() is qt_app
    assert not sip.ispyowned(small) and not sip.ispyowned(large)


def test_installation_is_idempotent_and_covers_both_factory_imports(qt_app):
    custom = menu.CustomMenuStyle
    fusion = PinnedStyleFactory.create("fusion")
    pin_fluent_styles()
    pin_fluent_styles()
    assert menu.QStyleFactory is style_sheet.QStyleFactory is PinnedStyleFactory
    assert menu.CustomMenuStyle is custom
    assert menu.QStyleFactory.create("fusion") is fusion


def test_dynamic_style_is_retained_after_widget_style_is_replaced(qt_app):
    widget = QWidget()
    try:
        style_sheet.updateDynamicStyle(widget)
        style = widget.style()
        widget.setStyle(QStyleFactory.create("fusion"))
        assert not sip.isdeleted(style)
        assert style.parent() is qt_app
    finally:
        sip.delete(widget)


def test_style_registry_releases_widget_without_cyclic_gc(qt_app):
    def register():
        widget = QWidget()
        style_sheet.FluentStyleSheet.LABEL.apply(widget)
        return weakref.ref(widget)

    enabled = gc.isenabled()
    gc.disable()
    try:
        before = len(list(style_sheet.styleSheetManager.items()))
        reference = register()
        assert reference() is None
        assert len(list(style_sheet.styleSheetManager.items())) == before
    finally:
        if enabled:
            gc.enable()


def test_shared_style_watchers_are_application_owned_and_update_each_widget(qt_app):
    widgets = [QWidget(), QWidget()]
    try:
        for widget, color in zip(widgets, ("#112233", "#445566"), strict=True):
            style_sheet.FluentStyleSheet.LABEL.apply(widget)
            qss = f"QWidget {{ color: {color}; }}"
            style_sheet.setCustomStyleSheet(widget, qss, qss)
            assert color in widget.styleSheet()
        assert "#445566" not in widgets[0].styleSheet()
        assert "#112233" not in widgets[1].styleSheet()
        for watcher_type in (style_sheet.CustomStyleSheetWatcher, style_sheet.DirtyStyleSheetWatcher):
            watchers = qt_app.findChildren(watcher_type)
            assert len(watchers) == 1 and watchers[0].parent() is qt_app
    finally:
        for widget in widgets:
            sip.delete(widget)


def test_window_refresh_gc_polish_and_teardown_survive_in_subprocess(tmp_path):
    # 原生崩溃无法捕获为 Python 异常，必须在子进程中测试完整的 Qt 生命周期。
    code = """
import ctypes
import gc
import sys
from pathlib import Path
if sys.platform == "win32":
    ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
from PyQt6.QtCore import QEvent, QSettings
from PyQt6.QtWidgets import QApplication, QMenu
from qfluentwidgets.components.widgets.menu import DWMMenu
from mcpacklocalizer.ui.view.window import MainWindow
app = QApplication([])
window = MainWindow(preferences=QSettings(str(Path(sys.argv[1]) / "preferences.ini"), QSettings.Format.IniFormat))
popup = DWMMenu(parent=window)
popup.ensurePolished()
popup.deleteLater()
window.show()
gc.collect()
for _ in range(4):
    window.api.refresh()
    gc.collect()
    app.processEvents()
    for popup in window.findChildren(QMenu):
        popup.ensurePolished()
window.close()
window.deleteLater()
app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
app.processEvents()
gc.collect()
print("生命周期检查完成", flush=True)
"""
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONUTF8": "1",
           "PYTHONPATH": str(root / "src"), "MPLT_DATA_DIR": str(tmp_path / "data"),
           "MPLT_CACHE_DIR": str(tmp_path / "cache"), "PYTHONFAULTHANDLER": "1"}
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path)], cwd=root, env=env,
                            capture_output=True, text=True, encoding="utf-8", timeout=30, check=False)
    assert result.returncode == 0, f"原生退出码：0x{result.returncode & 0xffffffff:08X}\n{result.stderr}"
    assert "生命周期检查完成" in result.stdout
