# [Module: desktop.logging] [Status: 已完成] [Brief: 线程安全日志缓冲、轮转文件及桌面异常接入]
from __future__ import annotations

import json
import logging
import queue
import re
import sys
import threading
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

MAX_LINES = 2000
LEVEL_ORDER = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
LEVEL_PATTERN = re.compile(r"\b(DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|FATAL)\b", re.IGNORECASE)


@dataclass(frozen=True)
class LogRecord:
    message: str
    level: str
    timestamp: str
    source: str = ""

    def text(self):
        source = f" [{self.source}]" if self.source else ""
        return f"[{self.timestamp}] [{self.level}]{source} {self.message}"


class LogFileHandler(RotatingFileHandler):
    def handleError(self, record):
        # 文件错误由缓冲区反馈到界面，不能只写到隐藏的桌面控制台。
        error = sys.exception()
        raise OSError("日志文件操作失败：" + str(error)) from error


class LogStore(QObject):
    appended = pyqtSignal(list)
    cleared = pyqtSignal()

    def __init__(self, directory=None, parent=None):
        super().__init__(parent)
        self.directory = directory
        self.records = deque()
        self.line_count = 0
        self.pending = queue.SimpleQueue()
        self.file_handler = None
        if directory is not None:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                self.file_handler = LogFileHandler(directory / "desktop.log", maxBytes=5 * 1024 * 1024,
                                                   backupCount=3, encoding="utf-8")
                self.file_handler.setFormatter(logging.Formatter("%(message)s"))
            except OSError as exc:
                self.append("无法创建日志文件：" + str(exc), "ERROR")
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.flush)
        self.timer.start()

    def append(self, message, level=None, source=""):
        """任何线程只入队，文件和界面由主线程批量处理。"""
        message = ANSI_ESCAPE.sub("", str(message)).replace("\r", "").rstrip()
        if not message.strip():
            return
        if level is None:
            try:
                payload = json.loads(message)
            except ValueError:
                payload = None
            if isinstance(payload, dict) and payload.get("type") == "log":
                message, level, source = str(payload.get("message", "")), payload.get("level"), payload.get("source", "")
            else:
                match = LEVEL_PATTERN.search(message)
                level = match[1].upper() if match else "ERROR" if (
                    "Traceback (most recent call last)" in message or
                    re.search(r"\b\w*(?:Error|Exception):", message) or "失败" in message) else "INFO"
        level = {"WARN": "WARNING", "FATAL": "CRITICAL"}.get(str(level).upper(), str(level).upper())
        if level not in LEVEL_ORDER:
            level = "INFO"
        timestamp = datetime.now(tz=UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        self.pending.put(LogRecord(message, level, timestamp, source))

    def flush(self):
        batch = []
        while not self.pending.empty():
            record = self.pending.get_nowait()
            if self.file_handler:
                try:
                    self.file_handler.handle(logging.LogRecord("desktop", LEVEL_ORDER[record.level], "", 0,
                                                               record.text(), (), None))
                except OSError as exc:
                    self.file_handler.close()
                    self.file_handler = None
                    self.append("日志文件写入失败：" + str(exc), "ERROR")
            # 文件保存完整输出；界面最多保留两千行，单条巨型记录也受限。
            lines = record.message.split("\n")
            if len(lines) > MAX_LINES:
                record = LogRecord("\n".join(lines[-MAX_LINES:]), record.level, record.timestamp, record.source)
            self.records.append(record)
            self.line_count += record.message.count("\n") + 1
            while self.line_count > MAX_LINES and len(self.records) > 1:
                self.line_count -= self.records.popleft().message.count("\n") + 1
            batch.append(record)
        if batch:
            self.appended.emit(batch)

    def clear(self):
        # 先保存尚未渲染的记录，清空显示不会删掉诊断文件。
        self.flush()
        self.records.clear()
        self.line_count = 0
        self.cleared.emit()

    def close(self):
        self.timer.stop()
        self.flush()
        if self.file_handler:
            self.file_handler.close()
            self.file_handler = None


class DesktopLogHandler(logging.Handler):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record):
        self.store.append(self.format(record), record.levelname, record.name)


def install_desktop_logging(store):
    """返回清理函数，避免重复入口调用留下处理器和异常钩子。"""
    root = logging.getLogger()
    previous_level = root.level
    handler = DesktopLogHandler(store)
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    previous_hook, previous_thread_hook = sys.excepthook, threading.excepthook

    def exception_hook(kind, value, tb):
        logging.getLogger("desktop").critical("界面发生未处理异常", exc_info=(kind, value, tb))
        previous_hook(kind, value, tb)

    def thread_hook(args):
        logging.getLogger("desktop").error("后台线程发生未处理异常：%s", args.thread.name,
                                           exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        previous_thread_hook(args)

    sys.excepthook, threading.excepthook = exception_hook, thread_hook

    def restore():
        sys.excepthook, threading.excepthook = previous_hook, previous_thread_hook
        root.removeHandler(handler)
        root.setLevel(previous_level)
        store.close()

    return restore
