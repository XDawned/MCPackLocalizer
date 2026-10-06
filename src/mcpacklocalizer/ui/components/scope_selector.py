"""A Fluent dropdown whose checkboxes remain open for multiple selections."""
from PyQt6.QtCore import QSignalBlocker, pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import CheckBox, DropDownPushButton, RoundMenu

from ...core.pack.scopes import PACK_SCOPES, recognition_scopes

LABELS = {"resources": "任务与整合包语言资源", "kubejs": "KubeJS",
          "patchouli": "帕秋莉手册", "mods": "模组缺失汉化"}


class ScopeSelector(DropDownPushButton):
    selectionChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.popup = RoundMenu(parent=self)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 10, 14, 10)
        self.all = CheckBox("所有整合包文本", content)
        layout.addWidget(self.all)
        self.checkboxes = {}
        for scope, title in LABELS.items():
            checkbox = CheckBox(title, content)
            layout.addWidget(checkbox)
            self.checkboxes[scope] = checkbox
            checkbox.toggled.connect(self.changed)
        content.adjustSize()
        content.setMinimumWidth(270)
        content.resize(290, content.sizeHint().height())
        self.popup.addWidget(content, selectable=False)
        self.setMenu(self.popup)
        self.all.toggled.connect(self.select_all)
        self.setSelectedData("all")

    def selectedData(self):
        return [scope for scope, checkbox in self.checkboxes.items() if checkbox.isChecked()]

    def setSelectedData(self, value):
        selected = recognition_scopes(value)
        blockers = [QSignalBlocker(checkbox) for checkbox in self.checkboxes.values()]
        for scope, checkbox in self.checkboxes.items():
            checkbox.setChecked(scope in selected)
        del blockers
        self.changed()

    def select_all(self, checked):
        blockers = [QSignalBlocker(self.checkboxes[scope]) for scope in PACK_SCOPES]
        for scope in PACK_SCOPES:
            self.checkboxes[scope].setChecked(checked)
        del blockers
        self.changed()

    def changed(self):
        selected = self.selectedData()
        blocker = QSignalBlocker(self.all)
        complete = set(PACK_SCOPES).issubset(selected)
        self.all.setChecked(complete)
        del blocker
        labels = ["所有整合包文本"] if complete else [LABELS[s] for s in selected if s != "mods"]
        if "mods" in selected:
            labels.append(LABELS["mods"])
        self.setText("、".join(labels) or "请选择识别范围")
        self.setToolTip("、".join(LABELS[s] for s in selected))
        self.selectionChanged.emit()
