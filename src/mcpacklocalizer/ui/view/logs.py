# [Module: desktop.logs] [Status: 已完成] [Brief: 运行日志等级筛选、搜索高亮、复制与滚动跟随]
from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QFontDatabase, QPalette, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QTextEdit, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    FluentIcon,
    LineEdit,
    PushButton,
    TextEdit,
    TitleLabel,
    isDarkTheme,
    qconfig,
)

from ..logging import LEVEL_ORDER, MAX_LINES


class LogPage(QWidget):
    def __init__(self, window, store):
        super().__init__(window)
        self.setObjectName("runtimeLogs")
        self.window, self.store = window, store
        self.auto_scroll = True
        self.rendering = False
        self.first_record = None
        box = QVBoxLayout(self)
        box.setContentsMargins(24, 24, 24, 20)
        box.setSpacing(12)
        box.addWidget(TitleLabel("运行日志", self))
        box.addWidget(BodyLabel("查看后台报错与完整堆栈；界面保留最近 2000 行，完整日志自动保存到日志目录。", self))
        row = QHBoxLayout()
        self.level_combo = ComboBox(self)
        for text, level in (("全部等级", "ALL"), ("调试及以上", "DEBUG"), ("信息及以上", "INFO"),
                            ("警告及以上", "WARNING"), ("错误及以上", "ERROR"), ("严重错误", "CRITICAL")):
            self.level_combo.addItem(text, userData=level)
        self.level_combo.currentIndexChanged.connect(self.rerender)
        self.search_edit = LineEdit(self)
        self.search_edit.setPlaceholderText("搜索日志…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(200)
        self.search_timer.timeout.connect(self.highlight)
        self.search_edit.textChanged.connect(lambda: self.search_timer.start())
        self.copy_btn = PushButton(FluentIcon.COPY, "复制全部", self)
        self.copy_btn.clicked.connect(self.copy_all)
        self.clear_btn = PushButton(FluentIcon.DELETE, "清空显示", self)
        self.clear_btn.clicked.connect(store.clear)
        self.open_dir_btn = PushButton(FluentIcon.FOLDER, "打开日志目录", self)
        self.open_dir_btn.clicked.connect(self.open_directory)
        row.addWidget(self.level_combo)
        row.addWidget(self.search_edit, 1)
        for button in (self.copy_btn, self.clear_btn, self.open_dir_btn):
            row.addWidget(button)
        box.addLayout(row)
        self.text_edit = TextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlaceholderText("等待日志…")
        self.text_edit.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.text_edit.document().setMaximumBlockCount(MAX_LINES)
        box.addWidget(self.text_edit, 1)
        footer = QHBoxLayout()
        self.status = BodyLabel(self)
        footer.addWidget(self.status, 1)
        self.scroll_btn = PushButton(FluentIcon.DOWN, "回到底部", self)
        self.scroll_btn.clicked.connect(self.scroll_to_bottom)
        self.scroll_btn.hide()
        footer.addWidget(self.scroll_btn)
        box.addLayout(footer)
        self.text_edit.verticalScrollBar().valueChanged.connect(self.on_scroll)
        store.appended.connect(self.append_batch)
        store.cleared.connect(self.clear_view)
        qconfig.themeChangedFinished.connect(self.rerender)
        self.rerender()

    def matches(self, record):
        return LEVEL_ORDER[record.level] >= LEVEL_ORDER.get(self.level_combo.currentData(), 0)

    def clear_view(self):
        self.auto_scroll = True
        self.rerender()

    def render_record(self, record):
        colors = ({"DEBUG": "#8a9bb0", "INFO": "#d7dde5", "WARNING": "#d1b06a",
                   "ERROR": "#e58a84", "CRITICAL": "#e58a84"} if isDarkTheme() else
                  {"DEBUG": "#596a7a", "INFO": "#24292f", "WARNING": "#7a5a12",
                   "ERROR": "#a33b34", "CRITICAL": "#a33b34"})
        cursor = QTextCursor(self.text_edit.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if not self.text_edit.document().isEmpty():
            cursor.insertBlock()
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colors[record.level]))
        cursor.insertText(record.text(), fmt)

    def append_batch(self, batch):
        # 被缓冲淘汰的记录不应在筛选后重新出现。
        if self.first_record is not None and self.store.records and self.first_record is not self.store.records[0]:
            self.rerender()
        else:
            self.render_batch(batch)

    def render_batch(self, batch):
        scroll = self.text_edit.verticalScrollBar()
        position = scroll.value()
        self.rendering = True
        self.text_edit.setUpdatesEnabled(False)
        try:
            for record in batch:
                if self.matches(record):
                    self.render_record(record)
            if self.auto_scroll:
                scroll.setValue(scroll.maximum())
            else:
                scroll.setValue(position)
        finally:
            self.text_edit.setUpdatesEnabled(True)
            self.rendering = False
        self.scroll_btn.setVisible(not self.auto_scroll)
        self.status.setText(f"保留 {len(self.store.records)} 条记录 · 搜索仅高亮匹配文本")
        self.first_record = self.store.records[0] if self.store.records else None
        if self.search_edit.text():
            self.search_timer.start()

    def rerender(self, *_args):
        dark = isDarkTheme()
        surface, text, border = (("#11161d", "#d7dde5", "#2f3642") if dark else
                                 ("#fbfcfe", "#24292f", "#d0d7de"))
        self.setStyleSheet("#runtimeLogs { background-color: " + ("#202020" if dark else "#f9f9f9") + "; }")
        self.text_edit.setStyleSheet(
            f"QTextEdit {{ background-color: {surface}; color: {text}; border: 1px solid {border}; "
            "border-radius: 6px; padding: 8px; }")
        palette = self.text_edit.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(surface))
        palette.setColor(QPalette.ColorRole.Text, QColor(text))
        self.text_edit.setPalette(palette)
        self.rendering = True
        position = self.text_edit.verticalScrollBar().value()
        self.text_edit.clear()
        self.render_batch(self.store.records)
        if not self.auto_scroll:
            self.text_edit.verticalScrollBar().setValue(position)
        self.highlight()

    def highlight(self):
        selections = []
        query = self.search_edit.text()
        cursor = QTextCursor(self.text_edit.document())
        if query:
            while len(selections) < 500:
                cursor = self.text_edit.document().find(query, cursor)
                if cursor.isNull():
                    break
                selection = QTextEdit.ExtraSelection()
                selection.cursor = cursor
                selection.format.setBackground(QColor("#f1c40f"))
                selection.format.setForeground(QColor("#24292f"))
                selections.append(selection)
        self.text_edit.setExtraSelections(selections)

    def on_scroll(self, value):
        if self.rendering:
            return
        self.auto_scroll = value >= self.text_edit.verticalScrollBar().maximum() - 2
        self.scroll_btn.setVisible(not self.auto_scroll)

    def scroll_to_bottom(self):
        self.auto_scroll = True
        self.text_edit.verticalScrollBar().setValue(self.text_edit.verticalScrollBar().maximum())
        self.scroll_btn.hide()

    def copy_all(self):
        self.store.flush()
        QApplication.clipboard().setText(self.text_edit.toPlainText())
        self.window.notify("当前等级筛选下的日志已复制")

    def open_directory(self):
        directory = self.store.directory
        if directory is None:
            self.window.notify("当前会话未启用日志文件", warning=True)
            return
        try:
            directory.mkdir(parents=True, exist_ok=True)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory.resolve()))):
                self.window.notify("无法打开日志目录：" + str(directory), error=True)
        except OSError as exc:
            self.window.notify("无法打开日志目录：" + str(exc), error=True)
