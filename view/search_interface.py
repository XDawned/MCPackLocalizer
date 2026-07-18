# coding:utf-8
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QApplication, QTreeWidgetItem
from qfluentwidgets import (ScrollArea, SearchLineEdit, InfoBar, TreeWidget)

from common.style_sheet import StyleSheet
from common.util import parse_json_file, find_similar_terms
from common.terms_dict import TERMS


class SearchDictInterface(ScrollArea):

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setFixedWidth(300)
        self.view = QWidget(self)
        self.vBoxLayout = QVBoxLayout()
        self.lineEdit = SearchLineEdit(self.view)
        self.lineEdit.searchSignal.connect(self.handle_search)
        self.lineEdit.setPlaceholderText('术语检索')
        self.lineEdit.returnPressed.connect(self.handle_search)

        # 绑定快捷键
        shortcut_edit = QShortcut(QKeySequence("Ctrl+/"), self)
        shortcut_edit.activated.connect(self.lineEdit.setFocus)

        self.tree = TreeWidget(self.view)
        self.setStyleSheet('font-size: 10px;border-top: none;border-right: none')
        self.tree.setColumnCount(1)
        self.tree.setHeaderHidden(True)

        # self.tree.setRowCount(1)
        # self.tree.setColumnWidth(0, 100)

        self.vBoxLayout.addWidget(self.lineEdit)
        self.vBoxLayout.addWidget(self.tree)
        self.view.setLayout(self.vBoxLayout)

        self.setWidget(self.view)
        self.setWidgetResizable(True)

        self.vBoxLayout.setSpacing(30)
        self.vBoxLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.vBoxLayout.setContentsMargins(36, 20, 36, 36)

        self.update_table({'spawner': ['刷怪笼']})
        self.tree.itemClicked.connect(self.copy_text)

        self.view.setObjectName('view')

    def update_table(self, data):
        self.tree.clear()
        for key, values in data.items():
            parent_item = QTreeWidgetItem(self.tree, [key])
            for value in values:
                child_item = QTreeWidgetItem(parent_item, [value])
                child_item.setText(0, value)
                child_item.setToolTip(0, f"点击复制: {value}")
        self.tree.expandAll()

    def handle_search(self):
        term = self.lineEdit.text()
        result = find_similar_terms(term, TERMS)
        if result:
            self.update_table(result)
        else:
            InfoBar.warning(
                self.tr('检索为空'),
                self.tr(''),
                duration=1500,
                parent=self
            )


    def copy_text(self, item):
        if item.childCount() == 0:
            text = item.text(0)
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            InfoBar.success(
                self.tr('已复制到剪切板'),
                self.tr(''),
                duration=1500,
                parent=self
            )

    def resizeEvent(self, e):
        super().resizeEvent(e)

class SearchCacheInterface(ScrollArea):

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.term_dict = TERMS

        self.setFixedWidth(300)
        self.view = QWidget(self)
        self.vBoxLayout = QVBoxLayout()
        self.lineEdit = SearchLineEdit(self.view)
        self.lineEdit.searchSignal.connect(self.handle_search)
        self.lineEdit.setPlaceholderText('记忆库检索')
        self.lineEdit.returnPressed.connect(self.handle_search)

        self.tree = TreeWidget(self.view)
        self.setStyleSheet('font-size: 10px;border-top: none;border-right: none')
        self.tree.setColumnCount(1)
        self.tree.setHeaderHidden(True)

        # self.tree.setRowCount(1)
        # self.tree.setColumnWidth(0, 100)

        self.vBoxLayout.addWidget(self.lineEdit)
        self.vBoxLayout.addWidget(self.tree)
        self.view.setLayout(self.vBoxLayout)

        self.setWidget(self.view)
        self.setWidgetResizable(True)

        self.vBoxLayout.setSpacing(30)
        self.vBoxLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.vBoxLayout.setContentsMargins(36, 20, 36, 36)

        self.update_table({'spawner': ['刷怪笼']})
        self.tree.itemClicked.connect(self.copy_text)

        self.view.setObjectName('view')

    def update_table(self, data):
        self.tree.clear()
        for key, values in data.items():
            parent_item = QTreeWidgetItem(self.tree, [key])
            for value in values:
                child_item = QTreeWidgetItem(parent_item, [value])
                child_item.setText(0, value)
                child_item.setToolTip(0, f"点击复制: {value}")
        self.tree.expandAll()

    def handle_search(self):
        term = self.lineEdit.text()
        result = find_similar_terms(term, self.term_dict)
        if result:
            self.update_table(result)
        else:
            InfoBar.warning(
                self.tr('检索为空'),
                self.tr(''),
                duration=1500,
                parent=self
            )


    def copy_text(self, item):
        if item.childCount() == 0:
            text = item.text(0)
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            InfoBar.success(
                self.tr('已复制到剪切板'),
                self.tr(''),
                duration=1500,
                parent=self
            )

    def resizeEvent(self, e):
        super().resizeEvent(e)
