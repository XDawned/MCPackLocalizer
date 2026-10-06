# [Module: desktop.process] [Status: 已完成] [Brief: 非阻塞任务执行、UTF-8 进度协议和进程树暂停]
from __future__ import annotations

import codecs
import json
import os
import sqlite3
import sys
from collections import deque
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, QThread, pyqtSignal

from ..application.tasks.jobs import Job
from ..application.tasks.store import load_task
from ..runtime import external_dll_search, task_python, worker_environment


class ProgressDecoder:
    def __init__(self):
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.buffer = ""

    def feed(self, data: bytes, final=False):
        self.buffer += self.decoder.decode(data, final=final)
        lines = self.buffer.split("\n")
        self.buffer = lines.pop()
        if final and self.buffer:
            lines.append(self.buffer)
            self.buffer = ""
        result = []
        for line in lines:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                payload = None
            progress = isinstance(payload, dict) and all(k in payload for k in ("completed", "failed", "remaining"))
            result.append((payload if progress else None, line))
        return result


class TaskProcess(QObject):
    progress = pyqtSignal(dict)
    log = pyqtSignal(str)
    done = pyqtSignal(int, dict, bool)
    busyChanged = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.started.connect(self.send_job)
        self.process.readyReadStandardOutput.connect(self.read_stdout)
        self.process.readyReadStandardError.connect(self.read_stderr)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.stopper = QProcess(self)
        self.stopper.finished.connect(self.stop_finished)
        self.stopper.errorOccurred.connect(self.stop_error)
        self.busy = False
        self.cancelled = False
        self.decoder = ProgressDecoder()
        self.stdout_decoder = ProgressDecoder()
        self.stdout_candidate = ""
        self.traceback_lines = []
        self.diagnostic_lines = deque(maxlen=40)
        self.native_failure = False

    def start(self, job: Job):
        if self.busy or self.stopper.state() != QProcess.ProcessState.NotRunning:
            raise ValueError("已有任务正在运行，请等待完成或先暂停")
        python = task_python()
        self.payload = json.dumps(job.payload(), ensure_ascii=False).encode("utf-8")
        self.output = bytearray()
        self.decoder = ProgressDecoder()
        self.stdout_decoder = ProgressDecoder()
        self.stdout_candidate = ""
        self.traceback_lines = []
        self.diagnostic_lines.clear()
        self.native_failure = False
        self.worker_python = python
        self.operation = job.operation
        self.cancelled = False
        self.busy = True
        self.busyChanged.emit(True)
        env = QProcessEnvironment()
        for key, value in worker_environment().items():
            env.insert(key, value)
        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(str(Path.home()))
        self.log.emit("后台解释器：" + python)
        try:
            with external_dll_search():
                self.process.start(python, ["-u", "-m", "mcpacklocalizer.application.tasks.worker"])
        except (OSError, RuntimeError):
            self.busy = False
            self.busyChanged.emit(False)
            raise

    def send_job(self):
        self.process.write(self.payload)
        self.process.closeWriteChannel()

    def read_stdout(self):
        data = bytes(self.process.readAllStandardOutput())
        self.output.extend(data)
        for _, line in self.stdout_decoder.feed(data):
            self.stdout_line(line)

    def stdout_line(self, line):
        try:
            payload = json.loads(line)
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            if self.stdout_candidate:
                self.log.emit(self.stdout_candidate)
            self.stdout_candidate = line
        else:
            self.log.emit(line)

    def read_stderr(self):
        for progress, line in self.decoder.feed(bytes(self.process.readAllStandardError())):
            self.stderr_line(progress, line)

    def stderr_line(self, progress, line):
        if progress is None:
            try:
                record = json.loads(line)
            except ValueError:
                record = None
            message = record.get("message", line) if isinstance(record, dict) and record.get("type") == "log" else line
            self.diagnostic_lines.append(str(message)[-4096:])
            if line.startswith(("Windows fatal exception:", "Fatal Python error:")):
                self.native_failure = True
        if progress is not None:
            self.progress.emit(progress)
            if progress.get("error"):
                self.log.emit("[ERROR] 条目 " + str(progress.get("entry_id", "未知")) + "：" + str(progress["error"]))
            for warning in progress.get("quality_warnings", []):
                self.log.emit("[WARNING] 条目 " + str(progress.get("entry_id", "未知")) + "：" + str(warning["message"]))
        elif line.startswith("Traceback (most recent call last)"):
            self.flush_traceback()
            self.traceback_lines.append(line)
        elif self.traceback_lines:
            self.traceback_lines.append(line)
            if not line.startswith((" ", "\t")):
                self.flush_traceback()
        else:
            self.log.emit("[ERROR] " + line if self.native_failure else line)

    def flush_traceback(self):
        if self.traceback_lines:
            self.log.emit("[ERROR] " + "\n".join(self.traceback_lines))
            self.traceback_lines.clear()

    def failure_result(self, code, status):
        message = f"后台任务未返回有效结果；退出码：{code}"
        if sys.platform == "win32" and (status == QProcess.ExitStatus.CrashExit or code < 0):
            native_code = code & 0xFFFFFFFF
            reasons = {
                0xC000001D: "非法指令（STATUS_ILLEGAL_INSTRUCTION）；可能是解释器或原生依赖与 CPU 指令集不兼容，或原生代码异常",
                0xC0000005: "内存访问违规（STATUS_ACCESS_VIOLATION）；原生代码访问了无效内存",
                0xC00000FD: "线程栈溢出（STATUS_STACK_OVERFLOW）；请检查资源嵌套深度或解析器递归",
                0xC0000135: "缺少运行时 DLL（STATUS_DLL_NOT_FOUND）；请检查解释器及其依赖是否完整",
                0xC000007B: "运行时或 DLL 架构不匹配（STATUS_INVALID_IMAGE_FORMAT）",
                0xC0000409: "原生程序快速终止（STATUS_STACK_BUFFER_OVERRUN）；请查看下面的崩溃堆栈",
            }
            reason = reasons.get(native_code, "Windows 原生进程异常")
            message += f"（0x{native_code:08X}）：{reason}"
        elif status == QProcess.ExitStatus.CrashExit:
            message += "；进程崩溃"
        diagnostics = "\n".join(self.diagnostic_lines)[-16384:]
        python = getattr(self, "worker_python", self.process.program())
        if python:
            message += "\n后台解释器：" + python
        message += "\n后台诊断：\n" + diagnostics if diagnostics else "\n后台未输出诊断信息，请查看运行日志中的启动信息"
        return {"error": message, "exit_code": code,
                "exit_status": "crashed" if status == QProcess.ExitStatus.CrashExit else "normal",
                "operation": getattr(self, "operation", ""), "python": python, "diagnostics": diagnostics}

    def finished(self, code, status):
        if not self.busy:
            return
        self.read_stdout()
        self.read_stderr()
        for progress, line in self.decoder.feed(b"", final=True):
            self.stderr_line(progress, line)
        self.flush_traceback()
        for _, line in self.stdout_decoder.feed(b"", final=True):
            self.stdout_line(line)
        try:
            output = bytes(self.output).decode("utf-8", errors="replace")
            try:
                result = json.loads(output)
            except ValueError:
                # 原生库可能直接写 stdout，保留这些日志并读取末尾的协议结果。
                result = json.loads(output.rstrip().split("\n")[-1])
            if not isinstance(result, dict):
                raise TypeError("任务结果不是对象")
        except (ValueError, TypeError):
            result = ({"error": "操作已暂停，已提交条目可继续翻译"} if self.cancelled else
                      self.failure_result(code, status))
        if not self.cancelled:
            if not result.get("error") and (status == QProcess.ExitStatus.CrashExit or code not in (0, 1)):
                result.update(self.failure_result(code, status))
            if result.get("error"):
                self.log.emit("[ERROR] " + str(result["error"]))
        self.busy = False
        self.busyChanged.emit(False)
        self.done.emit(code, result, self.cancelled)

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart and self.busy:
            self.log.emit("[ERROR] 无法启动后台进程：" + self.process.errorString())
            self.busy = False
            self.busyChanged.emit(False)
            self.done.emit(2, {"error": self.process.errorString()}, False)
        elif not self.cancelled and error != QProcess.ProcessError.Crashed:
            self.log.emit("[ERROR] 后台进程错误：" + self.process.errorString())

    def cancel(self):
        if not self.busy or self.cancelled:
            return
        # On Windows kill the owned tree, including llama_cpp, so VRAM is released.
        # QProcess invokes taskkill directly; no interpolated shell commands.
        self.cancelled = True
        pid = self.process.processId()
        if sys.platform == "win32" and pid:
            executable = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/taskkill.exe"
            self.stopper.start(str(executable), ["/PID", str(pid), "/T", "/F"])
        else:
            self.process.kill()

    def stop_finished(self, code, status):
        if code and self.busy:
            self.cancelled = False
            self.log.emit("[ERROR] 未能暂停整个进程树，请查看任务是否仍在运行并重试")

    def stop_error(self, error):
        self.cancelled = False
        self.log.emit("[ERROR] 无法启动进程树暂停工具：" + self.stopper.errorString())


class TaskLoader(QThread):
    loaded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            self.loaded.emit(load_task(self.path))
        except (ValueError, TypeError, OSError, sqlite3.Error, KeyError) as exc:
            self.failed.emit(str(exc))
