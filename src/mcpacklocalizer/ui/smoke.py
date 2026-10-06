# [Module: desktop.smoke] [Status: 已完成] [Brief: 发布 EXE 的无交互界面与真实子进程协议检查]
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QSettings, QTimer
from PyQt6.QtWidgets import QApplication

from ..application.tasks.jobs import Job
from .view.window import MainWindow


def main():
    output, root = Path(sys.argv[2]), Path(sys.argv[3])
    app = QApplication(sys.argv)
    report = {"code": 2, "result": {"error": "桌面后台扫描检查超时"}}
    with tempfile.TemporaryDirectory(prefix="mcpl-desktop-smoke-") as temporary:
        preferences = QSettings(str(Path(temporary) / "preferences.ini"), QSettings.Format.IniFormat)
        window = MainWindow(preferences=preferences)

        def done(code, result, cancelled):
            report.update(code=code, result=result, cancelled=cancelled)
            app.quit()

        window.runner.done.connect(done)
        QTimer.singleShot(90000, app.quit)
        QTimer.singleShot(0, lambda: window.runner.start(Job("scan", root=root, recognition_scope="kubejs")))
        app.exec()
        if window.runner.busy:
            window.runner.cancel()
            window.runner.process.waitForFinished(5000)
        window.deleteLater()
        app.processEvents()
    output.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return report["code"]
