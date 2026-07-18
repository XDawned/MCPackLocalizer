import copy
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget
from qfluentwidgets import Dialog, ExpandSettingCard
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets.components.settings.folder_list_setting_card import FolderItem


class FolderListCard(ExpandSettingCard):
    def __init__(self, title: str, content: str = None, folders=None, parent=None):
        super().__init__(FIF.FOLDER, title, content, parent)
        if folders is None:
            folders = []
        self.folders = folders.copy()
        self.__initWidget()

    def __initWidget(self):
        self.addWidget(QWidget())
        self.viewLayout.setSpacing(0)
        self.viewLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        for folder in self.folders:
            self.__addFolderItem(folder)

    def updateFolder(self, folders):
        self.__removeAllFolderWidget()
        self.folders = folders.copy()
        for folder in self.folders:
            self.__addFolderItem(folder)
        self._adjustViewSize()


    def __addFolderItem(self, folder: str):
        item = FolderItem(folder, self.view)
        item.removed.connect(self.__showConfirmDialog)
        self.viewLayout.addWidget(item)
        item.show()
        self._adjustViewSize()

    def __showConfirmDialog(self, item: FolderItem):
        """ show confirm dialog """
        name = Path(item.folder).name
        title = self.tr('确认删除此文件？')
        content = self.tr("提取本地键将不考虑 ") + f'"{name}"' + \
                  self.tr(",此操作不删除本地文件")
        w = Dialog(title, content, self.window())
        w.yesSignal.connect(lambda: self.__removeFolder(item))
        w.exec()

    def __removeFolder(self, item: FolderItem):
        if item.folder not in self.folders:
            return
        self.folders.remove(item.folder)
        self.viewLayout.removeWidget(item)
        item.deleteLater()
        self._adjustViewSize()

    def __removeAllFolderWidget(self):
        self.folders = []
        while self.viewLayout.count():
            item = self.viewLayout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                self.viewLayout.removeWidget(widget)
        self._adjustViewSize()
