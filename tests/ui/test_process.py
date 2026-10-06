# [Module: desktop.test_process] [Status: 已完成] [Brief: 分块 UTF-8 协议、非阻塞启动、故障及进程树暂停]
import json
import sys

import pytest
from PyQt6.QtCore import QByteArray, QEventLoop, QProcess, QTimer

from mcpacklocalizer.application.tasks.jobs import Job
from mcpacklocalizer.ui.process import ProgressDecoder, TaskLoader, TaskProcess


def test_utf8_chunking_and_progress_final_line():
    decoder = ProgressDecoder()
    data = json.dumps({"completed": 1, "failed": 0, "remaining": 2, "entry_id": "汉字"}, ensure_ascii=False).encode()
    results = []
    for byte in data:
        results.extend(decoder.feed(bytes([byte])))
    results.extend(decoder.feed(b"", final=True))
    assert len(results) == 1
    assert results[0][0]["entry_id"] == "汉字"


def test_native_log_and_other_json_are_not_progress():
    rows = ProgressDecoder().feed(b'ggml_vulkan: ready\n{"error":"oops"}\n')
    assert [row[0] for row in rows] == [None, None]


def test_nonblocking_launch_uses_argument_vector(qt_app, mocker):
    runner = TaskProcess()
    start = mocker.patch.object(runner.process, "start")
    runner.start(Job("translate", text="text with spaces & quotes"))
    assert start.call_args.args[1] == ["-u", "-m", "mcpacklocalizer.application.tasks.worker"]
    assert json.loads(runner.payload)["text"] == "text with spaces & quotes"
    assert runner.busy
    with pytest.raises(ValueError, match="正在运行"):
        runner.start([])
    runner.busy = False


def test_started_process_receives_json_on_stdin_and_eof(qt_app, mocker):
    runner = TaskProcess()
    mocker.patch.object(runner.process, "start")
    write = mocker.patch.object(runner.process, "write")
    close = mocker.patch.object(runner.process, "closeWriteChannel")
    runner.start(Job("translate", text='&6文本\n"引号"'))
    runner.send_job()
    assert json.loads(write.call_args.args[0])["text"] == '&6文本\n"引号"'
    close.assert_called_once()
    runner.busy = False


def test_partial_result_survives_nonzero_exit(qt_app, mocker):
    runner = TaskProcess()
    runner.busy = True
    runner.output = bytearray(b'{"partial": true, "patch": "D:/task/patch"}')
    runner.decoder = ProgressDecoder()
    mocker.patch.object(runner.process, "readAllStandardOutput", return_value=QByteArray())
    mocker.patch.object(runner.process, "readAllStandardError", return_value=QByteArray())
    done = []
    runner.done.connect(lambda *args: done.append(args))
    runner.finished(1, QProcess.ExitStatus.NormalExit)
    assert done[0] == (1, {"partial": True, "patch": "D:/task/patch"}, False)
    assert not runner.busy


def test_failed_to_start_clears_busy(qt_app):
    runner = TaskProcess()
    runner.busy = True
    done = []
    runner.done.connect(lambda *args: done.append(args))
    runner.process_error(QProcess.ProcessError.FailedToStart)
    assert not runner.busy
    assert done[0][0] == 2


def test_cannot_restart_while_tree_cleanup_is_running(qt_app, mocker):
    runner = TaskProcess()
    mocker.patch.object(runner.stopper, "state", return_value=QProcess.ProcessState.Running)
    with pytest.raises(ValueError, match="正在运行"):
        runner.start(["scan", "D:/game"])


def test_cancel_owned_tree_without_shell(qt_app, mocker):
    runner = TaskProcess()
    runner.busy = True
    mocker.patch("mcpacklocalizer.ui.process.sys.platform", "win32")
    mocker.patch.object(runner.process, "processId", return_value=12345)
    start = mocker.patch.object(runner.stopper, "start")
    runner.cancel()
    assert start.call_args.args[1] == ["/PID", "12345", "/T", "/F"]
    assert runner.cancelled
    runner.busy = False


def test_task_loader_reports_error(qt_app, mocker):
    mocker.patch("mcpacklocalizer.ui.process.load_task", side_effect=ValueError("bad checkpoint"))
    loader = TaskLoader("D:/task")
    failures = []
    loader.failed.connect(failures.append)
    loader.run()
    assert failures == ["bad checkpoint"]


def test_progress_error_and_traceback_are_logged_without_losing_progress(qt_app):
    runner = TaskProcess()
    logs, progress = [], []
    runner.log.connect(logs.append)
    runner.progress.connect(progress.append)
    payload = {"completed": 0, "failed": 1, "remaining": 2, "entry_id": "条目一", "error": "接口 401"}
    runner.stderr_line(payload, json.dumps(payload))
    for line in ('Traceback (most recent call last):', '  File "后台.py", line 2', 'RuntimeError: 模型加载失败'):
        runner.stderr_line(None, line)
    assert progress == [payload]
    assert "条目一：接口 401" in logs[0]
    assert 'File "后台.py"' in logs[1] and "RuntimeError" in logs[1]
    assert len(logs) == 2


def test_native_stdout_noise_does_not_hide_valid_result(qt_app, mocker):
    runner = TaskProcess()
    runner.busy = True
    runner.output = bytearray()
    runner.decoder = ProgressDecoder()
    chunks = [QByteArray('原生输出 <文本>\n{"translation":"译文"}\n'.encode()), QByteArray()]
    mocker.patch.object(runner.process, "readAllStandardOutput", side_effect=chunks)
    mocker.patch.object(runner.process, "readAllStandardError", return_value=QByteArray(b""))
    logs, done = [], []
    runner.log.connect(logs.append)
    runner.done.connect(lambda *args: done.append(args))
    runner.read_stdout()
    runner.finished(0, QProcess.ExitStatus.NormalExit)
    assert done == [(0, {"translation": "译文"}, False)]
    assert logs == ["原生输出 <文本>"]


def test_crash_preserves_last_stderr_line_and_reports_failure(qt_app, mocker):
    runner = TaskProcess()
    runner.busy = True
    runner.output = bytearray()
    mocker.patch.object(runner.process, "readAllStandardOutput", return_value=QByteArray())
    mocker.patch.object(runner.process, "readAllStandardError", return_value=QByteArray('原生崩溃：显存不足'.encode()))
    logs = []
    runner.log.connect(logs.append)
    runner.finished(-1, QProcess.ExitStatus.CrashExit)
    assert logs[0] == "原生崩溃：显存不足"
    assert "后台任务未返回有效结果" in logs[1]


def test_illegal_instruction_reports_exit_code_interpreter_and_native_stack(qt_app, mocker):
    runner = TaskProcess()
    mocker.patch.object(runner.process, "start")
    mocker.patch("mcpacklocalizer.ui.process.task_python", return_value="D:/运行时/python.exe")
    runner.start(Job("scan", root="D:/Game/JOSEFO'S PACK 2"))
    mocker.patch.object(runner.process, "readAllStandardOutput", return_value=QByteArray())
    native_stack = 'Windows fatal exception: illegal instruction\n  File "解析器.py", line 59 in parse'
    mocker.patch.object(runner.process, "readAllStandardError", return_value=QByteArray(native_stack.encode()))
    done = []
    runner.done.connect(lambda *args: done.append(args))
    runner.finished(-1073741795, QProcess.ExitStatus.CrashExit)
    code, result, cancelled = done[0]
    assert code == -1073741795 and not cancelled
    assert "0xC000001D" in result["error"] and "非法指令" in result["error"]
    assert result["python"] == "D:/运行时/python.exe" and result["operation"] == "scan"
    assert result["diagnostics"] == native_stack
    assert native_stack in result["error"]


def test_stderr_exception_is_included_when_worker_returns_no_json(qt_app, mocker):
    runner = TaskProcess()
    runner.busy = True
    runner.output = bytearray()
    mocker.patch.object(runner.process, "readAllStandardOutput", return_value=QByteArray())
    record = {"type": "log", "level": "ERROR", "message": "无法导入后台模块：缺少 httpx"}
    mocker.patch.object(runner.process, "readAllStandardError", return_value=QByteArray(json.dumps(record).encode()))
    done = []
    runner.done.connect(lambda *args: done.append(args))
    runner.finished(2, QProcess.ExitStatus.NormalExit)
    assert record["message"] in done[0][1]["error"]


def test_crash_after_valid_json_cannot_report_success(qt_app, mocker):
    runner = TaskProcess()
    runner.busy = True
    runner.output = bytearray(b'{"files": 2, "entries": 2273}')
    mocker.patch.object(runner.process, "readAllStandardOutput", return_value=QByteArray())
    mocker.patch.object(runner.process, "readAllStandardError", return_value=QByteArray())
    done = []
    runner.done.connect(lambda *args: done.append(args))
    runner.finished(-1073741795, QProcess.ExitStatus.CrashExit)
    assert done[0][1]["entries"] == 2273 and "error" in done[0][1]


def test_cancelled_worker_does_not_report_native_crash(qt_app, mocker):
    runner = TaskProcess()
    runner.busy = runner.cancelled = True
    runner.output = bytearray()
    mocker.patch.object(runner.process, "readAllStandardOutput", return_value=QByteArray())
    mocker.patch.object(runner.process, "readAllStandardError", return_value=QByteArray())
    done = []
    runner.done.connect(lambda *args: done.append(args))
    runner.finished(-1073741795, QProcess.ExitStatus.CrashExit)
    assert done[0][2] and "暂停" in done[0][1]["error"]
    assert "非法指令" not in done[0][1]["error"]


def test_real_worker_exception_reaches_log_and_result(qt_app, tmp_path, mocker):
    mocker.patch("mcpacklocalizer.ui.process.task_python", return_value=sys.executable)
    runner = TaskProcess()
    logs, results = [], []
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    runner.log.connect(logs.append)
    runner.done.connect(lambda *args: (results.append(args), loop.quit()))
    try:
        runner.start(Job("convert-lang", source=tmp_path / "missing.json", output=tmp_path / "out.json"))
        timer.start(15000)
        loop.exec()
        assert results and results[0][0] == 2 and "error" in results[0][1]
        text = "\n".join(logs)
        assert "Traceback" in text and "missing.json" in text
    finally:
        timer.stop()
        if runner.busy:
            runner.process.kill()
            runner.process.waitForFinished(5000)
