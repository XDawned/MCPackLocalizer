# coding:utf-8
from typing import Union

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtWidgets import QPushButton
from qfluentwidgets import SettingCard, InfoBar, LineEdit
from qfluentwidgets.common.config import qconfig, ConfigItem
from qfluentwidgets.common.icon import FluentIconBase

""" Setting card with a input button """


class PushEditSettingCard(SettingCard):
    """ Setting card with a push button """

    valueChanged = pyqtSignal(str)

    def __init__(self, text, icon: Union[str, QIcon, FluentIconBase], title, content=None, edit=None,
                 configItem: ConfigItem = None, parent=None):

        super().__init__(icon, title, content, parent)
        self.configItem = configItem

        self.lineEdit = LineEdit(self)
        if configItem:
            configItem.valueChanged.connect(self.setValue)
            self.lineEdit.setText(qconfig.get(configItem))
        else:
            self.lineEdit.setText(edit)

        self.lineEdit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.lineEdit.setMinimumWidth(350)
        self.lineEdit.setMinimumHeight(30)
        self.lineEdit.setFont(QFont("Arial", 9))
        self.hBoxLayout.addWidget(self.lineEdit, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.button = QPushButton(text, self)
        self.hBoxLayout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignCenter)
        self.hBoxLayout.addSpacing(32)
        self.button.clicked.connect(self.__onValueChanged)

    def __onValueChanged(self):
        """ slider value changed slot """
        value = self.lineEdit.text()
        self.setValue(value)
        self.valueChanged.emit(value)

    def setValue(self, value):
        qconfig.set(self.configItem, value)
        self.lineEdit.setText(value)
        InfoBar.success(
            self.tr('更新成功'),
            self.tr(''),
            duration=500,
            parent=self
        )
