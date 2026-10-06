# [Module: desktop.tests] [Status: 已完成] [Brief: 无真实写盘或外部进程的测试固件]
import os

import pytest
from PyQt6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qt_app():
    return QApplication.instance() or QApplication([])
