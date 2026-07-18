# coding:utf-8
import os
import sys

from PyQt6.QtCore import Qt, pyqtSignal, QEasingCurve, QUrl
from PyQt6.QtGui import QIcon, QDesktopServices, QGuiApplication
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QWidget
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import (NavigationInterface, NavigationItemPosition, qrouter, PopUpAniStackedWidget)
from qframelesswindow import FramelessWindow, StandardTitleBar

from common.activate import activate
from common.config import cfg, SUPPORT_URL
from common.signal_bus import signalBus
from common.style_sheet import StyleSheet
from components.avatar_widget import AvatarWidget
from view.generate_resourcepack_interface import GenerateResourcepackInterface
from view.modpack_extract_interface import ModpackExtractInterface
from view.setting_interface import SettingInterface
from view.work_interface import WorkInterface
from resource import resource

class StackedWidget(QFrame):
    currentWidgetChanged = pyqtSignal(QWidget)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.hBoxLayout = QHBoxLayout(self)
        self.view = PopUpAniStackedWidget(self)

        self.hBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.hBoxLayout.addWidget(self.view)

        self.view.currentChanged.connect(
            lambda i: self.currentWidgetChanged.emit(self.view.widget(i)))

    def addWidget(self, widget):
        """ add widget to view """
        self.view.addWidget(widget)

    def setCurrentWidget(self, widget, popOut=True):
        widget.verticalScrollBar().setValue(0)
        if not popOut:
            self.view.setCurrentWidget(widget, duration=300)
        else:
            self.view.setCurrentWidget(
                widget, True, False, 200, QEasingCurve.InQuad)

    def setCurrentIndex(self, index, popOut=False):
        self.setCurrentWidget(self.view.widget(index), popOut)


class MainWindow(FramelessWindow):

    def __init__(self):
        super().__init__()
        self.setTitleBar(StandardTitleBar(self))
        self.hBoxLayout = QHBoxLayout(self)
        self.widgetLayout = QHBoxLayout()

        self.stackWidget = StackedWidget(self)
        self.navigationInterface = NavigationInterface(self, True, True)

        self.workInterface = WorkInterface(self)
        self.modpackExtractInterface = ModpackExtractInterface(self)
        self.generateResourcepackInterface = GenerateResourcepackInterface(self)
        # self.migrateInterface = MigrateInterface(self)
        self.settingInterface = SettingInterface(self)

        self.initLayout()

        self.initNavigation()

        self.initWindow()

    def initLayout(self):
        self.hBoxLayout.setSpacing(0)
        self.hBoxLayout.setContentsMargins(0, 0, 0, 0, )
        self.hBoxLayout.addWidget(self.navigationInterface)
        self.hBoxLayout.addLayout(self.widgetLayout)
        self.hBoxLayout.setStretchFactor(self.widgetLayout, 1)

        self.widgetLayout.addWidget(self.stackWidget)
        self.widgetLayout.setContentsMargins(0, 48, 0, 0)

        signalBus.supportSignal.connect(self.onSupport)

        self.navigationInterface.displayModeChanged.connect(
            self.titleBar.raise_)
        self.titleBar.raise_()

    def initNavigation(self):
        self.addSubInterface(self.workInterface, 'workInterface', FIF.PENCIL_INK, self.tr('工作台'),
                             NavigationItemPosition.TOP)
        self.navigationInterface.addSeparator()
        self.addSubInterface(self.modpackExtractInterface, 'toolInterface', FIF.SCROLL, '整合包待翻译部分提取',
                             NavigationItemPosition.SCROLL)
        # self.addSubInterface(self.migrateInterface, 'migrateInterface', FIF.SHARE, '语言文件迁移',
        #                      NavigationItemPosition.SCROLL)
        self.addSubInterface(self.generateResourcepackInterface, 'resourceInterface', FIF.MINIMIZE, '生成资源包',
                             NavigationItemPosition.SCROLL)

        self.navigationInterface.addWidget(
            routeKey='avatar',
            widget=AvatarWidget(':/images/xdawned-pro.jpg') if activate.activate else AvatarWidget(':/images/xdawned.jpg'),
            onClick=self.onSupport,
            position=NavigationItemPosition.BOTTOM,
        )
        self.addSubInterface(
            self.settingInterface, 'settingInterface', FIF.SETTING, self.tr('设置'), NavigationItemPosition.BOTTOM)

        qrouter.setDefaultRouteKey(self.stackWidget, self.workInterface.objectName())

        # set default widget
        self.stackWidget.currentWidgetChanged.connect(self.onCurrentWidgetChanged)
        self.navigationInterface.setCurrentItem(
            self.workInterface.objectName())
        self.workInterface.setObjectName('workInterface')
        self.stackWidget.setCurrentIndex(0)

    def initWindow(self):
        self.setMinimumWidth(760)
        self.setWindowIcon(QIcon(f':/images/logo.png'))
        self.setWindowTitle('整合包本地化工具')
        self.titleBar.setObjectName('titleBar')
        self.titleBar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        screen = QGuiApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        w, h = screen_geometry.width(), screen_geometry.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)

        StyleSheet.MAIN_WINDOW.apply(self)

    def addSubInterface(self, interface: QWidget, objectName: str, icon, text: str,
                        position=NavigationItemPosition.SCROLL):
        """ add sub interface """
        interface.setObjectName(objectName)
        self.stackWidget.addWidget(interface)
        self.navigationInterface.addItem(
            routeKey=objectName,
            icon=icon,
            text=text,
            onClick=lambda t: self.switchTo(interface, t),
            position=position,
            tooltip=text
        )

    def switchTo(self, widget, triggerByUser=True):
        self.stackWidget.setCurrentWidget(widget, not triggerByUser)

    def onSupport(self):
        QDesktopServices.openUrl(QUrl(SUPPORT_URL))

    def onCurrentWidgetChanged(self, widget: QWidget):
        self.navigationInterface.setCurrentItem(widget.objectName())
        qrouter.push(self.stackWidget, widget.objectName())

    def resizeEvent(self, e):
        self.titleBar.move(46, 0)
        self.titleBar.resize(self.width() - 46, self.titleBar.height())


if __name__ == '__main__':
    # enable dpi scale
    if cfg.get(cfg.dpiScale) == "Auto":
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    else:
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
        os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))

    # create application
    app = QApplication(sys.argv)
    app.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings)

    window = MainWindow()

    screen = QGuiApplication.primaryScreen()
    screen_geometry = screen.geometry()
    window.setGeometry(screen_geometry.x(), screen_geometry.y(),
                       screen_geometry.width(), screen_geometry.height() - 40)  # 减去任务栏高度（一般为40）

    window.show()
    app.exec()
