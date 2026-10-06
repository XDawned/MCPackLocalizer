# [Module: tests.logs] [Status: 已完成] [Brief: 日志筛选、堆栈、批量缓冲、文件与滚动回归]
import json
import logging
import sys
import threading

import pytest
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QWidget
from qfluentwidgets import Theme, setTheme

from mcpacklocalizer.ui.logging import LogStore, install_desktop_logging
from mcpacklocalizer.ui.view.logs import LogPage


@pytest.fixture
def page(qt_app, mocker):
    window = QWidget()
    window.notify = mocker.Mock()
    store = LogStore(parent=window)
    widget = LogPage(window, store)
    yield widget
    store.close()
    widget.search_timer.stop()
    window.close()
    window.deleteLater()
    qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qt_app.processEvents()


def test_structured_traceback_survives_error_filter_and_html_is_plain(page):
    page.store.append("普通消息", "INFO")
    message = '后台异常\nTraceback (most recent call last):\n  File "工作.py", line 3\nValueError: <错误>&详情'
    page.store.append(json.dumps({"type": "log", "level": "ERROR", "message": message}, ensure_ascii=False))
    page.store.flush()
    page.level_combo.setCurrentIndex(page.level_combo.findData("ERROR"))
    text = page.text_edit.toPlainText()
    assert message in text and "普通消息" not in text
    page.search_edit.setText("错误")
    page.highlight()
    assert len(page.text_edit.extraSelections()) == 1
    page.copy_all()
    from PyQt6.QtWidgets import QApplication
    assert QApplication.clipboard().text() == text


def test_highlight_limit_and_clear(page):
    page.store.append("匹配 " * 600, "WARNING")
    page.store.flush()
    page.search_edit.setText("匹配")
    page.highlight()
    assert len(page.text_edit.extraSelections()) == 500
    page.store.append("尚未渲染的错误", "ERROR")
    page.clear_btn.click()
    assert not page.store.records and page.text_edit.toPlainText() == ""
    assert not page.text_edit.extraSelections()
    page.store.flush()
    assert page.text_edit.toPlainText() == ""


def test_multiline_buffer_and_filtered_view_remain_bounded(page):
    page.level_combo.setCurrentIndex(page.level_combo.findData("ERROR"))
    page.store.append("应该淘汰的错误", "ERROR")
    page.store.flush()
    for i in range(2100):
        page.store.append(f"消息 {i}", "INFO")
    page.store.flush()
    assert page.store.line_count == 2000
    assert page.text_edit.toPlainText() == ""
    page.store.append("\n".join(f"堆栈 {i}" for i in range(2500)), "ERROR")
    page.store.flush()
    assert page.store.line_count == 2000 and len(page.store.records) == 1
    assert page.text_edit.document().blockCount() <= 2000
    assert "堆栈 2499" in page.text_edit.toPlainText()


def test_reader_scroll_is_preserved_until_return_to_bottom(page, qt_app):
    page.resize(1000, 400)
    page.window.resize(1000, 400)
    page.window.show()
    page.show()
    for i in range(100):
        page.store.append(f"日志 {i}")
    page.store.flush()
    qt_app.processEvents()
    bar = page.text_edit.verticalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(10)
    assert not page.auto_scroll
    page.store.append("新日志", "ERROR")
    page.store.flush()
    assert bar.value() == 10
    assert not page.scroll_btn.isHidden()
    page.scroll_btn.click()
    assert page.auto_scroll and bar.value() == bar.maximum()


def test_file_retains_records_after_clear_and_shutdown(qt_app, tmp_path):
    store = LogStore(tmp_path / "logs")
    try:
        store.append("清空之前的错误", "ERROR")
        store.clear()
        store.append("退出前尚未渲染的消息")
    finally:
        store.close()
    text = (tmp_path / "logs" / "desktop.log").read_text(encoding="utf-8")
    assert "清空之前的错误" in text and "退出前尚未渲染的消息" in text


def test_desktop_logging_captures_threads_and_exception_and_restores_hooks(qt_app):
    store = LogStore()
    root = logging.getLogger()
    old_handlers, old_level = root.handlers[:], root.level
    old_hook, old_thread_hook = sys.excepthook, threading.excepthook
    restore = install_desktop_logging(store)
    try:
        thread = threading.Thread(target=lambda: logging.getLogger("测试线程").warning("线程警告"))
        thread.start()
        thread.join()
        try:
            raise RuntimeError("完整堆栈")
        except RuntimeError:
            logging.getLogger("界面").exception("操作失败")
        assert not store.records
        store.flush()
        assert [record.level for record in store.records] == ["WARNING", "ERROR"]
        assert "Traceback" in store.records[-1].message and "RuntimeError: 完整堆栈" in store.records[-1].message
    finally:
        restore()
    assert root.handlers == old_handlers and root.level == old_level
    assert sys.excepthook is old_hook and threading.excepthook is old_thread_hook


def test_file_write_failure_is_visible(qt_app, tmp_path, mocker):
    store = LogStore(tmp_path / "logs")
    mocker.patch.object(store.file_handler, "doRollover", side_effect=OSError("日志目录不可写"))
    mocker.patch.object(store.file_handler, "shouldRollover", return_value=True)
    try:
        store.append("原始错误", "ERROR")
        store.flush()
        assert store.file_handler is None
        assert "原始错误" in store.records[0].message
        assert "日志文件写入失败" in store.records[1].message
    finally:
        store.close()


def test_theme_change_preserves_errors_and_search(page):
    page.store.append("错误主题测试", "ERROR")
    page.store.flush()
    page.search_edit.setText("错误")
    before = page.text_edit.toPlainText()
    try:
        setTheme(Theme.DARK)
        page.rerender()
        assert "#11161d" in page.text_edit.styleSheet()
        assert page.text_edit.toPlainText() == before
        assert len(page.text_edit.extraSelections()) == 1
        setTheme(Theme.LIGHT)
        page.rerender()
        assert "#fbfcfe" in page.text_edit.styleSheet()
        assert page.text_edit.toPlainText() == before
    finally:
        setTheme(Theme.AUTO)
