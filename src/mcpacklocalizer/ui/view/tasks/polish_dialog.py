# [Module: desktop.polish_dialog] [Status: 已完成] [Brief: 修润结果对照、失败原始返回、人工修复与选择接受]
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, MessageBoxBase, PushButton, ScrollArea, SubtitleLabel, TableWidget, TextEdit

from ....application.tasks.polishing import validate_polish_candidate


class PolishResultsDialog(MessageBoxBase):
    def __init__(self, scan, run, parent):
        super().__init__(parent)
        self.scan, self.run = scan, run
        self.updates = {}
        self.current_key = None
        self._loading = True
        self.by_id = {entry.id: entry for entry in scan.entries}
        self.keys = [key for key in run.get("previous", {}) if key in run.get("results", {}) and key in self.by_id]
        self.edits = {key: run["results"][key].get("accepted_translation", run["results"][key].get("translation")) or ""
                      for key in self.keys}
        self.checked_repairs = set()
        self.widget.setFixedSize(min(1100, max(640, parent.width() - 80)), min(850, max(520, parent.height() - 70)))
        self.viewLayout.addWidget(SubtitleLabel("修润结果预览与接受", self.widget))
        summary = BodyLabel("正式译文保持原样。通过项默认勾选；失败项可查看原始返回，手动修复后重新校验。只有确认接受才会保存。", self.widget)
        summary.setWordWrap(True)
        self.viewLayout.addWidget(summary)
        content = QWidget(self.widget)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        self.table = TableWidget(content)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["接受", "结果", "原文"])
        self.table.setRowCount(len(self.keys))
        self.table.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(TableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(150)
        self.table.setMaximumHeight(200)
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 150)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().hide()
        for row, key in enumerate(self.keys):
            proposal = run["results"][key]
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Checked if not proposal.get("error") and not proposal.get("accepted") else Qt.CheckState.Unchecked)
            if proposal.get("accepted"):
                check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(row, 0, check)
            state = "已接受" if proposal.get("accepted") else "守卫拦截" if proposal.get("error") else "通过，待接受"
            self.table.setItem(row, 1, QTableWidgetItem(state))
            item = QTableWidgetItem(self.by_id[key].source.replace("\n", " ↵ ")[:160])
            item.setToolTip(self.by_id[key].document + "\n" + self.by_id[key].source)
            self.table.setItem(row, 2, item)
        layout.addWidget(self.table)
        row = QHBoxLayout()
        self.select_passed = PushButton("勾选所有通过项", content)
        self.reject_all = PushButton("全部不接受", content)
        self.recheck = PushButton("重新校验并勾选此条", content)
        self.select_passed.clicked.connect(self.check_passed)
        self.reject_all.clicked.connect(self.uncheck_all)
        self.recheck.clicked.connect(self.validate_current)
        for button in (self.select_passed, self.reject_all, self.recheck):
            row.addWidget(button)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.source, self.before = TextEdit(content), TextEdit(content)
        for label, text in (("原文", self.source), ("修润前译文", self.before)):
            column = QVBoxLayout()
            column.addWidget(BodyLabel(label, content))
            text.setReadOnly(True)
            text.setFixedHeight(100)
            column.addWidget(text)
            row.addLayout(column)
        layout.addLayout(row)
        self.tabs = QTabWidget(content)
        self.candidate, self.raw = TextEdit(content), TextEdit(content)
        self.candidate.setPlaceholderText("在这里手动修复候选译文，之后点击重新校验")
        self.raw.setReadOnly(True)
        self.tabs.addTab(self.candidate, "候选译文（可手动修复）")
        self.tabs.addTab(self.raw, "API 原始返回（包括失败内容）")
        self.tabs.setMinimumHeight(180)
        layout.addWidget(self.tabs)
        self.original_reason, self.guard = BodyLabel("", content), BodyLabel("", content)
        for label in (self.original_reason, self.guard):
            label.setWordWrap(True)
            layout.addWidget(label)
        self.guard.setStyleSheet("color: #c43b34;")
        scroll = ScrollArea(self.widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(ScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        content.setAutoFillBackground(False)
        self.viewLayout.addWidget(scroll, 1)
        self.error = BodyLabel("", self.widget)
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #c43b34;")
        self.viewLayout.addWidget(self.error)
        self.yesButton.setText("接受勾选结果并保存")
        self.cancelButton.setText("关闭，保留原译文")
        self.table.currentCellChanged.connect(self.select_result)
        self.candidate.textChanged.connect(self.edit_current)
        self._loading = False
        if self.keys:
            self.table.setCurrentCell(0, 2)
        else:
            self.error.setText("本批还没有返回结果；关闭后可以在校润页重新打开预览。")

    def select_result(self, row, *_):
        if self._loading or not 0 <= row < len(self.keys):
            return
        self._loading = True
        key = self.keys[row]
        self.current_key = key
        proposal = self.run["results"][key]
        self.source.setPlainText(self.by_id[key].source)
        self.before.setPlainText(self.run["previous"][key].get("translation") or "（未翻译）")
        self.candidate.setPlainText(self.edits[key])
        self.candidate.setReadOnly(bool(proposal.get("accepted")))
        self.raw.setPlainText(proposal.get("raw_response") or "没有获得可展示的 API 返回内容。")
        self.original_reason.setText("原始拦截原因：" + (proposal.get("error") or "已通过校验"))
        self.guard.setText("")
        self.recheck.setEnabled(not proposal.get("accepted"))
        self._loading = False

    def edit_current(self):
        if self._loading or self.current_key is None:
            return
        key = self.current_key
        self.edits[key] = self.candidate.toPlainText()
        self.checked_repairs.discard(key)
        row = self.keys.index(key)
        self.table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
        self.table.item(row, 1).setText("已修改，待校验")
        self.guard.setText("修改后请重新校验。")

    def validate_current(self):
        if self.current_key is None:
            return
        key = self.current_key
        try:
            validate_polish_candidate(self.scan, self.by_id[key], self.edits[key], self.run)
        except ValueError as exc:
            self.guard.setText("当前守卫拦截：" + str(exc))
            return False
        self.checked_repairs.add(key)
        row = self.keys.index(key)
        self.table.item(row, 1).setText("修复后通过，待接受")
        self.table.item(row, 0).setCheckState(Qt.CheckState.Checked)
        self.guard.setText("当前校验已通过，确认接受后才会保存。")
        return True

    def check_passed(self):
        for row, key in enumerate(self.keys):
            proposal = self.run["results"][key]
            passed = (not proposal.get("error") and self.edits[key] == (proposal.get("translation") or "")) or key in self.checked_repairs
            self.table.item(row, 0).setCheckState(Qt.CheckState.Checked if passed and not proposal.get("accepted") else Qt.CheckState.Unchecked)

    def uncheck_all(self):
        for row in range(len(self.keys)):
            self.table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)

    def validate(self):
        updates = {}
        for row, key in enumerate(self.keys):
            if self.table.item(row, 0).checkState() != Qt.CheckState.Checked:
                continue
            try:
                validate_polish_candidate(self.scan, self.by_id[key], self.edits[key], self.run)
            except ValueError as exc:
                self.table.setCurrentCell(row, 2)
                self.error.setText("勾选条目尚未通过校验：" + str(exc))
                return False
            updates[key] = self.edits[key]
        if not updates:
            self.error.setText("请勾选至少一条要接受的结果，或关闭弹窗保留原译文。")
            return False
        self.updates = updates
        self.error.clear()
        return True
