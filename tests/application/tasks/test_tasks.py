# [Module: desktop.test_tasks] [Status: 已完成] [Brief: 只读检查点优先、条目摘要及质量提醒]
import json

import pytest

from mcpacklocalizer.application.tasks.store import entry_hints, load_task, result_summary, task_counts
from mcpacklocalizer.core.pack.extraction import Entry, Scan


def sample():
    return Scan("D:/games/pack", "pack", "en_us", "zh_cn", entries=[
        Entry("one", "one", "quests.snbt", ["title"], "6 buckets", 0, 10, "chapter", "六桶", "translated"),
        Entry("two", "two", "quests.snbt", ["title"], "Iron", 0, 4, "chapter", status="failed", error="failure"),
    ])


def test_database_is_readonly_and_takes_priority(mocker):
    data = sample().to_dict()
    entries = data.pop("entries")
    mocker.patch("pathlib.Path.is_file", side_effect=lambda path: path.name == "state.sqlite3", autospec=True)
    read = mocker.patch("pathlib.Path.read_text")
    connect = mocker.patch("mcpacklocalizer.application.tasks.store.sqlite3.connect")
    connection = connect.return_value
    connection.execute.side_effect = [mocker.Mock(), mocker.Mock(fetchone=lambda: (json.dumps(data),)),
                                      [(json.dumps(e),) for e in entries]]
    scan = load_task("D:/task")
    assert scan.entries[0].translation == "六桶"
    assert "?mode=ro" in connect.call_args.args[0]
    assert connect.call_args.kwargs["uri"] is True
    connection.execute.assert_any_call("BEGIN")
    connection.close.assert_called_once()
    read.assert_not_called()


def test_snapshot_fallback_is_read_only(mocker):
    mocker.patch("pathlib.Path.is_file", return_value=False)
    read = mocker.patch("pathlib.Path.read_text", return_value=json.dumps(sample().to_dict()))
    connect = mocker.patch("mcpacklocalizer.application.tasks.store.sqlite3.connect")
    assert load_task("D:/task").pack_id == "pack"
    read.assert_called_once()
    connect.assert_not_called()


def test_missing_metadata_closes_connection(mocker):
    mocker.patch("pathlib.Path.is_file", side_effect=lambda path: path.name == "state.sqlite3", autospec=True)
    connect = mocker.patch("mcpacklocalizer.application.tasks.store.sqlite3.connect")
    connect.return_value.execute.return_value.fetchone.return_value = None
    with pytest.raises(ValueError, match="元数据"):
        load_task("D:/task")
    connect.return_value.close.assert_called_once()


def test_counts_use_translation_presence():
    assert task_counts(sample()) == {"translated": 1, "failed": 1, "total": 2, "complete": 1, "remaining": 1}


def test_quality_and_failure_hints():
    scan = sample()
    assert "数字" in entry_hints(scan.entries[0])
    assert entry_hints(scan.entries[1]) == "failure"


def test_partial_is_visible_in_summary():
    result = {"patch": "D:/task/patch", "partial": True, "pending_entries": 5, "files": 2,
              "quality_warnings": [{}]}
    assert "部分补丁" in result_summary(result)
    assert "待翻译 5" in result_summary(result)
    assert "质量提示 1" in result_summary(result)


def test_environment_check_does_not_claim_inference_works():
    assert "不存在" in result_summary({"model_exists": False})
    assert "试译确认" in result_summary({"model_exists": True})
