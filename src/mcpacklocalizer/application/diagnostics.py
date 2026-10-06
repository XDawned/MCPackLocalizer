# [Module: application.diagnostics] [Status: 已完成] [Brief: 后台日志的结构化标准错误输出]
from __future__ import annotations

import json
import logging
import sys
from contextlib import contextmanager


class WorkerLogFormatter(logging.Formatter):
    def format(self, record):
        message = record.getMessage()
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)
        return json.dumps({"type": "log", "level": record.levelname, "message": message,
                           "source": record.name}, ensure_ascii=False)


@contextmanager
def worker_logging():
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(WorkerLogFormatter())
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        yield
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)
        handler.close()
