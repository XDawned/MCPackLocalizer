# [Module: desktop.tests] [Status: 已完成] [Brief: 无真实写盘或外部进程的测试固件]
import os

import pytest
from PyQt6.QtWidgets import QApplication

from mcpacklocalizer.ui.styles import pin_fluent_styles

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pin_fluent_styles()


@pytest.fixture(scope="session")
def qt_app():
    return QApplication.instance() or QApplication([])
