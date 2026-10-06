# [Module: tests.polish_dialog] [Status: 已完成] [Brief: 修润预览、失败原文、手动修复、拒绝及接受前校验]
import json

import pytest
from PyQt6.QtCore import QEvent, QPropertyAnimation, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QWidget

from mcpacklocalizer.core.pack.extraction import Entry, Scan
from mcpacklocalizer.ui.view.tasks.polish_dialog import PolishResultsDialog


@pytest.fixture
def dialog(qt_app):
    parent = QWidget()
    parent.resize(1200, 900)
    entries = [Entry("one", "one", "a.json", ["one"], "&bGrapes&r", 0, 1, "葡萄名称",
                     translation="&b旧葡萄&r", status="reviewed", origin="manual"),
               Entry("two", "two", "a.json", ["two"], "Keep ${player}", 0, 1, "玩家变量",
                     translation="保留${player}"),
               Entry("three", "three", "a.json", ["three"], "Iron Ingot", 0, 1, "铁锭", translation="旧铁锭")]
    run = {"id": "draft", "preview_only": True,
           "previous": {entry.id: {"translation": entry.translation} for entry in entries},
           "results": {"one": {"translation": "&b葡萄&r", "raw_response": '{"translation":"&b葡萄&r"}', "error": ""},
                       "two": {"translation": "保留玩家", "raw_response": '{"translation":"保留玩家"}', "error": "缺失保留符：${player}"},
                       "three": {"translation": None, "raw_response": '{"translation":"铁', "error": "API 输出被截断"}}}
    scan = Scan("D:/game", "pack", "en_us", "zh_cn", entries=entries, metadata={"polish_runs": [run]})
    widget = PolishResultsDialog(scan, run, parent)
    yield widget
    for animation in widget.findChildren(QPropertyAnimation):
        animation.stop()
    widget.hide()
    widget.deleteLater()
    qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    parent.deleteLater()
    qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qt_app.processEvents()


def test_failed_response_and_guard_reason_remain_visible(dialog):
    dialog.table.setCurrentCell(1, 2)
    assert dialog.source.toPlainText() == "Keep ${player}"
    assert dialog.before.toPlainText() == "保留${player}"
    assert dialog.candidate.toPlainText() == "保留玩家"
    assert json.loads(dialog.raw.toPlainText())["translation"] == "保留玩家"
    assert "${player}" in dialog.original_reason.text()
    dialog.table.setCurrentCell(2, 2)
    assert dialog.raw.toPlainText() == '{"translation":"铁' and "截断" in dialog.original_reason.text()
    assert [entry.translation for entry in dialog.scan.entries] == ["&b旧葡萄&r", "保留${player}", "旧铁锭"]


def test_failed_candidate_can_be_repaired_checked_and_accepted(dialog):
    dialog.table.setCurrentCell(1, 2)
    dialog.candidate.setPlainText("保留${player}，请继续")
    dialog.recheck.click()
    assert dialog.table.item(1, 0).checkState() == Qt.CheckState.Checked
    assert "已通过" in dialog.guard.text()
    assert dialog.validate()
    assert dialog.updates == {"one": "&b葡萄&r", "two": "保留${player}，请继续"}
    assert dialog.run["results"]["two"]["translation"] == "保留玩家"
    assert dialog.scan.entries[0].translation == "&b旧葡萄&r"


def test_manually_checking_invalid_candidate_cannot_bypass_guard(dialog):
    dialog.table.item(1, 0).setCheckState(Qt.CheckState.Checked)
    assert not dialog.validate()
    assert "${player}" in dialog.error.text()
    assert dialog.updates == {}


def test_rejecting_or_editing_does_not_change_original_translations(dialog):
    dialog.table.setCurrentCell(0, 2)
    dialog.candidate.setPlainText("损坏格式")
    assert dialog.table.item(0, 0).checkState() == Qt.CheckState.Unchecked
    assert not dialog.validate_current()
    dialog.reject_all.click()
    assert not dialog.validate()
    dialog.reject()
    QTest.qWait(150)
    assert dialog.scan.entries[0].translation == "&b旧葡萄&r"
    assert dialog.run["results"]["one"]["translation"] == "&b葡萄&r"
