# [Module: desktop.main] [Status: 已完成] [Brief: 高 DPI PyQt6 应用入口]
import logging
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from ..paths import DATA_HOME
from .logging import LogStore, install_desktop_logging
from .view.window import MainWindow


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setOrganizationName("MCPackLocalizer")
    app.setApplicationName("MCPackLocalizer Desktop")
    store = LogStore(DATA_HOME / "logs")
    restore = install_desktop_logging(store)
    try:
        window = MainWindow(log_store=store)
        store.append("桌面已启动", "INFO", "界面")
        window.show()
        return app.exec()
    except Exception:
        logging.getLogger("desktop").exception("桌面启动或运行失败")
        raise
    finally:
        restore()


if __name__ == "__main__":
    raise SystemExit(main())
