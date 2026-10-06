# [Module: tests.jobs] [Status: 已完成] [Brief: 后台输入边界、续跑继承与结构化协议]
import io
import json
import logging
from pathlib import Path

import pytest

from mcpacklocalizer.application.tasks.jobs import Job
from mcpacklocalizer.application.tasks.worker import main


def test_roundtrip_preserves_multiline_text_and_paths():
    text = '第一行\n&6第二行&r %1$s "引号"'
    job = Job("review", output="D:/tasks/a b", entry_id="id", translation=text)
    restored = Job.from_payload(json.loads(json.dumps(job.payload(), ensure_ascii=False)))
    assert restored == job
    assert isinstance(restored.output, Path)
    assert restored.translation == text


@pytest.mark.parametrize("payload", [[], {}, {"operation": "unknown"}, {"operation": "export"},
    {"operation": "doctor", "arbitrary": True}, {"operation": "doctor", "threads": "2"},
    {"operation": "doctor", "probe": "false"}, {"operation": "doctor", "timeout": None},
    {"operation": "doctor", "backend": "invalid"}, {"operation": "doctor", "resource_pack": "a.zip"},
    {"operation": "resume", "output": "D:/task", "limit": -1}])
def test_invalid_payload_does_not_execute(payload, monkeypatch, mocker, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    execute = mocker.patch("mcpacklocalizer.application.tasks.service.execute")
    assert main() == 2
    assert "error" in json.loads(capsys.readouterr().out)
    execute.assert_not_called()


def test_invalid_json_has_machine_readable_result(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO('{broken'))
    assert main() == 2
    assert "error" in json.loads(capsys.readouterr().out)


def test_worker_reads_one_request_and_preserves_partial_result(monkeypatch, mocker, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(Job("export", output="D:/task").payload())))
    execute = mocker.patch("mcpacklocalizer.application.tasks.service.execute", return_value={"partial": True})
    assert main() == 1
    assert json.loads(capsys.readouterr().out) == {"partial": True}
    assert execute.call_args.args[0].output == Path("D:/task")


def test_worker_logs_full_traceback_and_keeps_stdout_protocol(monkeypatch, mocker, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(Job("doctor").payload())))
    mocker.patch("mcpacklocalizer.application.tasks.service.execute", side_effect=AssertionError("意外后台错误"))
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    assert main() == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["error"] == "意外后台错误"
    record = json.loads(captured.err)
    assert record["level"] == "ERROR" and "Traceback" in record["message"]
    assert "AssertionError: 意外后台错误" in record["message"]
    assert root.handlers == handlers and root.level == level


def test_worker_redirects_library_prints_to_stderr(monkeypatch, mocker, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(Job("doctor").payload())))

    def execute(job):
        print("后台库的诊断输出")
        return {"ready": True}

    mocker.patch("mcpacklocalizer.application.tasks.service.execute", side_effect=execute)
    assert main() == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"ready": True}
    assert "后台库的诊断输出" in captured.err
