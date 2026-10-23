# [Module: desktop.smoke] [Status: 已完成] [Brief: 发布 EXE 的无交互界面与真实子进程协议检查]
from __future__ import annotations

import gc
import json
import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QEvent, QSettings, Qt, QTimer
from PyQt6.QtWidgets import QApplication

from ..application.tasks.jobs import Job
from .view.window import MainWindow

OBSERVATION_MS = 3000


def main():
    output, root = Path(sys.argv[2]), Path(sys.argv[3])
    app = QApplication(sys.argv)
    report = {"code": 2, "result": {"error": "桌面后台扫描检查超时"}}
    with tempfile.TemporaryDirectory(prefix="mcpl-desktop-smoke-") as temporary:
        preferences = QSettings(str(Path(temporary) / "preferences.ini"), QSettings.Format.IniFormat)
        window = MainWindow(preferences=preferences)
        observed = False
        completed = False
        collections = 0

        def collect():
            nonlocal collections
            gc.collect()
            collections += 1

        def finish():
            if observed and completed:
                app.quit()

        def done(code, result, cancelled):
            nonlocal completed
            report.update(code=code, result=result, cancelled=cancelled)
            completed = True
            finish()

        def observation_done():
            nonlocal observed
            observed = True
            finish()

        window.runner.done.connect(done)
        timeout = QTimer(window)
        timeout.setSingleShot(True)
        timeout.timeout.connect(app.quit)
        timeout.start(90000)
        observation = QTimer(window)
        observation.setSingleShot(True)
        observation.setTimerType(Qt.TimerType.PreciseTimer)
        observation.timeout.connect(observation_done)
        collector = QTimer(window)
        collector.timeout.connect(collect)
        collector.start(100)
        window.show()
        # 首轮 polish / DeferredDelete 之前回收，覆盖 issue #12 的危险时机。
        collect()
        observation.start(OBSERVATION_MS)
        QTimer.singleShot(0, lambda: window.runner.start(Job("scan", root=root, recognition_scope="kubejs")))
        app.exec()
        if window.runner.busy:
            window.runner.cancel()
            window.runner.process.waitForFinished(5000)
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    report["ui"] = {"observation_complete": observed, "gc_cycles": collections}
    if not observed:
        report.update(code=2, result={"error": "桌面窗口与 GC 观察未完成"})
    output.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return report["code"]
