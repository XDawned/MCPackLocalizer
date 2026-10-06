"""Background paginated preset browsing and user term/no-translate editing."""
import json
from dataclasses import replace

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QHeaderView, QTableWidgetItem
from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    SearchLineEdit,
    TableWidget,
    TextEdit,
)

from ....application.config.settings import validate_glossary
from ....application.config.terminology import GlossaryCatalog
from ....core.pack.snapshots import atomic_write
from ...components.forms import Page


class CatalogQuery(QThread):
    loaded = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, catalog, options, parent):
        super().__init__(parent)
        self.catalog, self.options = catalog, options

    def run(self):
        try:
            self.loaded.emit(self.catalog.query(**self.options))
        except (ValueError, OSError, TypeError) as exc:
            self.failed.emit(str(exc))


class TranslationRulesPage(Page):
    def __init__(self, window):
        super().__init__("translationRules", "术语库与禁翻表", "系统预设保留，修改以用户覆盖项保存；适用于本地 GGUF 和 API 翻译。", window)
        self.window = window
        self.catalog = GlossaryCatalog()
        self.page = 0
        self.total = 0
        self.rows = []
        self.loader = None
        self.pending_query = False
        self.initialized = False
        self.settings_signature = None
        self.dirty = {}
        terms = self.section("术语表", "每页最多 200 条。后台读取预设，界面只创建当前页；修改译文后保存，清空译文可禁用预设术语。")
        row = QHBoxLayout()
        self.scope = ComboBox()
        self.scope.addItems(["系统 / 所选预设", "用户覆盖（含外部覆盖文件）"])
        self.search = SearchLineEdit()
        self.search.setPlaceholderText("搜索原文或译文")
        self.size = ComboBox()
        self.size.addItems(["50", "100", "200"])
        self.size.setCurrentText("100")
        for widget in (self.scope, self.search, self.size):
            row.addWidget(widget)
        terms.addLayout(row)
        self.table = TableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["原文", "译文（空白表示禁用）"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        self.table.setMinimumHeight(360)
        self.table.itemChanged.connect(self.edit_term)
        terms.addWidget(self.table)
        row = QHBoxLayout()
        self.previous = PushButton("上一页")
        self.next = PushButton("下一页")
        self.page_info = BodyLabel("打开本页时加载预设")
        self.previous.clicked.connect(lambda: self.turn(-1))
        self.next.clicked.connect(lambda: self.turn(1))
        for widget in (self.previous, self.page_info, self.next):
            row.addWidget(widget)
        row.addStretch()
        refresh = PushButton("刷新")
        refresh.clicked.connect(self.query)
        row.addWidget(refresh)
        terms.addLayout(row)
        row = QHBoxLayout()
        self.new_source, self.new_target = LineEdit(), LineEdit()
        self.new_source.setPlaceholderText("新增 / 调整术语原文")
        self.new_target.setPlaceholderText("首选中文译文；留空禁用")
        add = PushButton("加入覆盖")
        add.clicked.connect(self.add_term)
        for widget in (self.new_source, self.new_target, add):
            row.addWidget(widget)
        terms.addLayout(row)
        row = QHBoxLayout()
        save = PrimaryPushButton("保存术语修改")
        save.clicked.connect(self.save_terms)
        restore = PushButton("移除选中界面覆盖")
        restore.clicked.connect(self.restore_selected)
        import_button = PushButton("导入覆盖 JSON")
        import_button.clicked.connect(self.import_terms)
        export_button = PushButton("导出用户覆盖")
        export_button.clicked.connect(self.export_terms)
        for widget in (save, restore, import_button, export_button):
            row.addWidget(widget)
        terms.addLayout(row)
        forbidden = self.section("禁翻表", "每行一个精确词条，区分大小写，并匹配英文单词边界；命中部分原样保留，其余内容照常翻译。资源 ID、变量、URL 和格式代码已自动保护，无需列入。")
        self.non_translate = TextEdit()
        self.non_translate.setMinimumHeight(140)
        self.non_translate.setPlaceholderText("例如整合包名称或需要保留的模组名称；不自动提取人物或角色信息")
        self.non_translate.setPlainText(window.settings.non_translate)
        forbidden.addWidget(self.non_translate)
        save_forbidden = PrimaryPushButton("保存禁翻表")
        save_forbidden.clicked.connect(lambda: window.save_settings(replace(window.settings, non_translate=self.non_translate.toPlainText())))
        forbidden.addWidget(save_forbidden)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.query)
        self.search.textChanged.connect(self.filter_changed)
        self.scope.currentIndexChanged.connect(self.filter_changed)
        self.size.currentIndexChanged.connect(self.filter_changed)
        self.body.addStretch()

    def showEvent(self, event):
        super().showEvent(event)
        settings = self.window.settings
        signature = (settings.glossary, settings.overrides, settings.glossary_inline)
        if not self.initialized or signature != self.settings_signature:
            self.initialized = True
            self.query()

    def filter_changed(self, *args):
        self.page = 0
        self.timer.start()

    def turn(self, delta):
        self.page = max(0, self.page + delta)
        self.query()

    def merged(self):
        data = validate_glossary(self.window.settings.glossary_inline)
        for key, value in self.dirty.items():
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
        return data

    def query(self):
        if self.loader:
            self.pending_query = True
            return
        self.previous.setEnabled(False)
        self.next.setEnabled(False)
        self.table.setEnabled(False)
        self.page_info.setText("正在后台查询…")
        settings = self.window.settings
        self.settings_signature = (settings.glossary, settings.overrides, settings.glossary_inline)
        self.loader = CatalogQuery(self.catalog, {"path": settings.glossary, "overrides": settings.overrides,
                                   "inline": json.dumps(self.merged(), ensure_ascii=False), "search": self.search.text(),
                                   "page": self.page, "size": int(self.size.currentText()), "custom": self.scope.currentIndex() == 1}, self)
        self.loader.loaded.connect(self.loaded)
        self.loader.failed.connect(self.load_failed)
        self.loader.finished.connect(self.finished)
        self.loader.start()

    def load_failed(self, error):
        self.page_info.setText("查询失败，请检查术语文件并刷新")
        self.window.notify(error, error=True)

    def loaded(self, result):
        if self.pending_query:
            return
        self.rows, self.total = result["rows"], result["total"]
        size, page = result["size"], result["page"]
        if page and not self.rows:
            self.page = max(0, (self.total - 1) // size)
            self.pending_query = True
            return
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.rows))
        for i, (source, target) in enumerate(self.rows):
            item = QTableWidgetItem(source)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 0, item)
            self.table.setItem(i, 1, QTableWidgetItem(target))
        self.table.blockSignals(False)
        self.page_info.setText(f"第 {page + 1} / {max(1, (self.total + size - 1) // size)} 页 · 共 {self.total:,} 条 · 未保存修改 {len(self.dirty)} 条")
        self.previous.setEnabled(page > 0)
        self.next.setEnabled((page + 1) * size < self.total)

    def finished(self):
        self.loader.deleteLater()
        self.loader = None
        self.table.setEnabled(True)
        if self.pending_query:
            self.pending_query = False
            self.query()

    def edit_term(self, item):
        if item.column() == 1:
            source = self.table.item(item.row(), 0).text()
            self.dirty[source] = item.text().strip()

    def add_term(self):
        if source := self.new_source.text().strip():
            self.dirty[source] = self.new_target.text().strip()
            self.query()

    def restore_selected(self):
        row = self.table.currentRow()
        if row >= 0:
            source = self.table.item(row, 0).text()
            if source not in self.merged():
                self.window.notify("此条没有界面覆盖；外部覆盖文件可在设置中更换，或在本页另设译文。", warning=True)
                return
            self.dirty[source] = None
            self.save_terms()

    def save_terms(self):
        settings = replace(self.window.settings, glossary_inline=json.dumps(self.merged(), ensure_ascii=False))
        self.window.save_settings(settings)
        self.dirty.clear()
        self.query()

    def import_terms(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入术语覆盖", "", "JSON (*.json)")
        if not path:
            return
        try:
            from pathlib import Path
            self.dirty.update(validate_glossary(Path(path).read_text(encoding="utf-8-sig")))
            self.query()
        except (ValueError, OSError) as exc:
            self.window.notify(str(exc), error=True)

    def export_terms(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出用户术语覆盖", "", "JSON (*.json)")
        if path:
            try:
                from pathlib import Path
                atomic_write(Path(path), json.dumps(self.merged(), ensure_ascii=False, indent=2))
            except OSError as exc:
                self.window.notify(str(exc), error=True)
