# coding: utf-8
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import QVBoxLayout, QWidget, QTableWidgetItem, QHBoxLayout, QFrame, QLabel, \
    QSpacerItem, QSizePolicy, QApplication
from qfluentwidgets import TableWidget, TextEdit, PushButton, SearchLineEdit, LineEdit, ScrollArea, ExpandLayout, \
    FluentIcon, InfoBar

from common.config import cfg
from common.style_sheet import StyleSheet
from common.util import merge_dicts, parse_json_file, ACA, global_aca
from components.link_card import SuggestCardWidget
from components.mc_color_edit import McColorEdit


class Frame(QFrame):

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(0, 8, 0, 0)

        self.setObjectName('frame')
        StyleSheet.VIEW_INTERFACE.apply(self)

    def addWidget(self, widget):
        self.vBoxLayout.addWidget(widget)


class BrowseLangWidget(Frame):
    doubleClicked = pyqtSignal(int)

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.data = data

        self.table = TableWidget(self)
        self.searchWorkEdit = SearchLineEdit()
        self.searchWorkEdit.searchSignal.connect(self.handle_work_search)
        self.searchWorkEdit.setPlaceholderText('从原文中检索')
        self.searchWorkEdit.returnPressed.connect(self.handle_work_search)

        self.table.doubleClicked.connect(self.handle_item_clicked)

        self.addWidget(self.table)
        self.addWidget(self.searchWorkEdit)

        # self.table.setColumnCount(3)
        self.table.setColumnCount(2)
        self.table.setRowCount(len(self.data))
        self.table.setColumnWidth(0, 300)
        # self.table.setColumnWidth(1, 300)
        self.update_table(self.data)
        # self.table.cellChanged.connect(self.handleCellChanged)
        self.table.setRowCount(8)
        self.setFixedHeight(720)
        self.table.horizontalHeader().setStretchLastSection(True)

    def handle_work_search(self):
        search_text = self.searchWorkEdit.text().strip().lower()
        if search_text:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 1)
                if search_text in item.text().lower():
                    item.setFont(QFont("Segoe UI", 12, QFont.Bold))
                else:
                    item.setFont(QFont("SimSun", 10))

    def handle_item_clicked(self, item):
        self.doubleClicked.emit(item.row())

    def update_table(self, data):
        self.data = data
        self.table.clear()
        self.table.setHorizontalHeaderLabels([
            self.tr('键值'), self.tr('原文')
        ])
        # self.table.setHorizontalHeaderLabels([
        #     self.tr('键值'), self.tr('原文'), self.tr('译文')
        # ])
        self.table.setRowCount(len(self.data))
        for i, item in enumerate(self.data):
            # for j in range(3):
            for j in range(2):
                item_ = QTableWidgetItem(item[j])
                if j < 2:
                    item_.setFlags(item_.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(i, j, item_)

    def handleCellChanged(self, row, column):
        try:
            self.data[row][2] = self.table.item(row, 2).text()
        except Exception as e:
            return


class ReviewLangWidget(ScrollArea):
    dataUpdated = pyqtSignal(str)

    def __init__(self, data_array):
        super().__init__()
        self.suggestPanel = None
        self.text_edit_ori = None
        self.label_key = None
        self.text_edit_trans = None
        self.expandLayout = None
        self.scrollWidget = None
        self.suggetPanel = None
        self.current_edit_info = None
        self.current_trans_info = None
        self.jump_index_edit = None
        self.index_label = None
        self.all_cache_dic = {}
        self.data_array = data_array
        self.current_index = 0
        self.str_count_all = 0
        self.translator_thread = None
        self.aca = global_aca

        self.init_ui()

    def init_ui(self):
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setViewportMargins(0, 0, 0, 0)
        self.scrollWidget = QWidget()
        self.scrollWidget.setStyleSheet('background-color: transparent')
        self.expandLayout = ExpandLayout(self.scrollWidget)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)

        self.text_edit_ori = McColorEdit(self.scrollWidget)
        self.text_edit_ori.setReadOnly(True)
        self.text_edit_trans = McColorEdit(self.scrollWidget)

        self.text_edit_ori.setFixedHeight(100)
        self.text_edit_trans.setFixedHeight(100)

        shortcut_edit = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut_cancel = QShortcut(QKeySequence("Esc"), self)
        self.text_edit_trans.textChanged.connect(self.handleTextChanged)
        shortcut_edit.activated.connect(self.text_edit_trans.setFocus)
        shortcut_cancel.activated.connect(self.text_edit_trans.clearFocus)

        self.label_key = QLabel('键值', self.scrollWidget)
        label2 = QLabel('原文', self.scrollWidget)
        label3 = QLabel('译文', self.scrollWidget)
        self.label_key.setStyleSheet('font-size: 15px; font-weight: bold')
        self.label_key.setFixedHeight(18)
        label2.setFixedHeight(15)
        label3.setFixedHeight(15)

        button_box = QWidget(self.scrollWidget)
        button_box.setFixedHeight(40)
        button_layout = QHBoxLayout()
        button_layout.setSpacing(0)
        prev_button = PushButton('<', button_box)
        shortcut_prev_button = QShortcut(QKeySequence("Ctrl+A"), self)
        self.text_edit_trans.textChanged.connect(self.handleTextChanged)
        prev_button.setFixedHeight(40)
        prev_button.clicked.connect(self.prev_data)
        shortcut_prev_button.activated.connect(self.prev_data)
        next_button = PushButton('>', button_box)
        shortcut_next_button = QShortcut(QKeySequence("Ctrl+D"), self)
        next_button.setFixedHeight(40)
        next_button.clicked.connect(self.next_data)
        shortcut_next_button.activated.connect(self.prev_data)
        button_layout.addWidget(prev_button)
        self.jump_index_edit = LineEdit(button_box)
        self.jump_index_edit.setFixedSize(65, 40)
        self.jump_index_edit.returnPressed.connect(self.jump_to)
        self.index_label = QLabel(button_box)
        self.index_label.setFixedHeight(40)
        self.current_trans_info = QLabel()
        self.current_trans_info.setFixedHeight(40)
        self.current_edit_info = QLabel('此节字符：0     总字符：0')
        self.current_edit_info.setStyleSheet('margin-left:20px')
        self.current_edit_info.setFixedHeight(40)
        button_layout.addWidget(self.index_label)
        button_layout.addWidget(next_button)
        button_layout.addItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        jump_label = QLabel(self.tr('跳转到'), button_box)
        jump_label.setFixedHeight(40)
        button_layout.addWidget(jump_label)
        button_layout.addWidget(self.jump_index_edit)
        button_layout.addWidget(self.current_edit_info)
        button_layout.addStretch(1)
        button_layout.addWidget(self.current_trans_info)
        button_box.setLayout(button_layout)

        self.suggestPanel = SuggestCardWidget(self.scrollWidget)
        # self.suggestPanel.addCard(author='离线翻译', trans='苹果', ori='apple', icon=FluentIcon.GLOBE)
        # self.suggestPanel.addCard(author='百度翻译', trans='苹果', ori='apple', icon=FluentIcon.GLOBE)
        self.suggestPanel.clickSignal.connect(self.copy_text)

        self.expandLayout.setSpacing(28)
        self.expandLayout.setContentsMargins(36, 10, 36, 0)
        self.expandLayout.addWidget(self.label_key)
        self.expandLayout.addWidget(label2)
        self.expandLayout.addWidget(self.text_edit_ori)
        self.expandLayout.addWidget(label3)
        self.expandLayout.addWidget(self.text_edit_trans)
        self.expandLayout.addWidget(button_box)
        self.expandLayout.addWidget(self.suggestPanel)

        # self.setLayout(layout)
        self.update_data()

    def copy_text(self, text):
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        InfoBar.success(
            self.tr('已复制到剪切板'),
            self.tr(''),
            duration=1500,
            parent=self
        )


    def update_table(self, data):
        self.data_array = data
        self.current_index = 0
        self.str_count_all = 0
        self.get_all_cache_dic()
        for i in data:
            self.str_count_all += len(i[1])
        self.update_data()

    def update_data(self):
        self.jump_index_edit.setText(f"{self.current_index + 1}")
        self.index_label.setText(f"{self.current_index + 1}/{len(self.data_array)}")
        if len(self.data_array) != 0:
            if self.current_index < len(self.data_array):
                data = self.data_array[self.current_index]
                if len(data) >= 3:
                    self.label_key.setText('' + data[0])
                    self.text_edit_ori.setHtml(data[1])
                    self.text_edit_ori.fresh_color()
                    self.text_edit_trans.setHtml(data[2])
                    self.text_edit_trans.fresh_color()
                    self.current_edit_info.setText(
                        '此节字符：%d     总字符：%d' % (len(self.data_array[self.current_index][1]), self.str_count_all))
                    self.dataUpdated.emit(self.data_array[self.current_index][1])
        self.update_suggest_card()

    def handleTextChanged(self):
        try:
            self.data_array[self.current_index][2] = self.text_edit_trans.toPlainText()
        except Exception as e:
            return

    def prev_data(self):
        if len(self.data_array) == 0:
            self.current_index = -1
        else:
            self.current_index = (self.current_index - 1) % len(self.data_array)
        self.update_data()

    def jump_to(self):
        text = self.jump_index_edit.text()
        if text.isdigit():
            index = int(text) - 1
            if index > -1:
                self.current_index = (int(text) - 1) % len(self.data_array)
                self.update_data()

    def next_data(self):
        if len(self.data_array) == 0:
            self.current_index = -1
        else:
            self.current_index = (self.current_index + 1) % len(self.data_array)
        self.update_data()

    def update_suggest_card(self):  # 更新翻译建议
        self.suggestPanel.removeAllCard()
        if self.data_array:
            # 记忆库
            ori = self.data_array[self.current_index][1]
            for key, value in self.all_cache_dic.items():
                if ori == self.all_cache_dic[key]['ori']:
                    trans = self.all_cache_dic[key]['trans']
                    self.suggestPanel.addCard(author='进度缓存', trans=trans, ori=ori, icon=FluentIcon.PIN)
            # 机翻
            current_trans = self.data_array[self.current_index][3]
            if current_trans:
                trans = current_trans
                api = cfg.get(cfg.translateApi)
                if api == '0':
                    api = '百度翻译'
                elif api == '1':
                    api = '离线翻译'
                else:
                    api = 'ChatGPT'
                self.suggestPanel.addCard(author=api, trans=trans, ori=ori, icon=FluentIcon.GLOBE)
            # 术语词典
            term_search = self.aca.find(ori)
            if term_search:
                for term in term_search:
                    self.suggestPanel.addCard(author='术语库', trans='|'.join(term[1][1]), ori=term[1][0], icon=FluentIcon.HELP)

    def get_all_cache_dic(self):
        self.all_cache_dic = {}
        cache_path = f"{cfg.get(cfg.workFolder)}/.mplt/cache"
        for path in Path(cache_path).rglob("*.json"):
            cache_dic = parse_json_file(str(path))
            self.all_cache_dic = merge_dicts(self.all_cache_dic, cache_dic)
