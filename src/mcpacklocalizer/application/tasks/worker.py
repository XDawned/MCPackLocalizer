# [Module: application.worker] [Status: 已完成] [Brief: 桌面后台单任务 JSON 标准输入协议]
from __future__ import annotations

import json
import logging
import sys
from contextlib import redirect_stdout

from ..diagnostics import worker_logging
from .jobs import Job


def perform(job: Job) -> int:
    try:
        # 普通 Python 输出进入日志通道，标准输出只承载最终结果。
        with redirect_stdout(sys.stderr):
            from .service import execute

            result = execute(job)
        code = 2 if result.get("scan_complete") is False else 1 if result.get("partial") else 0
    except KeyboardInterrupt:
        result, code = {"error": "任务已暂停，已提交条目保存在检查点中"}, 130
    except Exception as exc:
        logging.getLogger(__name__).exception("后台任务失败：%s", job.operation)
        result, code = {"error": str(exc), "operation": job.operation}, 2
    if job.operation == "polish":
        result.setdefault("run_id", job.polish_run_id)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return code


def main() -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    with worker_logging():
        return read_request()


def read_request() -> int:
    try:
        payload = sys.stdin.read(16 * 1024 * 1024 + 1)
        if len(payload) > 16 * 1024 * 1024:
            raise ValueError("任务数据过大")
        job = Job.from_payload(json.loads(payload))
    except (ValueError, TypeError) as exc:
        logging.getLogger(__name__).exception("后台任务输入无效")
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), flush=True)
        return 2
    return perform(job)


if __name__ == "__main__":
    raise SystemExit(main())
