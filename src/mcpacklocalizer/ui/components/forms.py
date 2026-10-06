# [Module: desktop.forms] [Status: 已完成] [Brief: 可滚动 Fluent 页面、设置卡片与路径选择器]
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    ColorPickerButton,
    ComboBox,
    FluentIcon,
    LineEdit,
    PushButton,
    PushSettingCard,
    ScrollArea,
    SettingCard,
    SpinBox,
    SubtitleLabel,
    TitleLabel,
    TransparentToolButton,
)


class FormLayout(QFormLayout):
    def addRow(self, label, field=None):
        if field is None:
            super().addRow(label)
        else:
            super().addRow(BodyLabel(label) if isinstance(label, str) else label, field)


class Page(ScrollArea):
    def __init__(self, name, title, description, parent=None, *, heading=True):
        super().__init__(parent)
        self.setObjectName(name)
        self.setWidgetResizable(True)
        self.setFrameShape(ScrollArea.Shape.NoFrame)
        self.content = QWidget(self)
        self.content.setObjectName("pageContent")
        self.setWidget(self.content)
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(32, 24, 32, 28)
        self.body.setSpacing(18)
        if heading:
            self.body.addWidget(TitleLabel(title, self.content))
            label = BodyLabel(description, self.content)
            label.setWordWrap(True)
            self.body.addWidget(label)
        self.setStyleSheet("Page, #pageContent { background: transparent; }")

    def section(self, title, description=""):
        card = CardWidget(self.content)
        box = QVBoxLayout(card)
        box.setContentsMargins(22, 18, 22, 20)
        box.setSpacing(12)
        box.addWidget(SubtitleLabel(title, card))
        if description:
            label = BodyLabel(description, card)
            label.setWordWrap(True)
            box.addWidget(label)
        self.body.addWidget(card)
        return box


class PathPicker(QWidget):
    textChanged = pyqtSignal(str)

    def __init__(self, placeholder="", mode="directory", file_filter="所有文件 (*)", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.file_filter = file_filter
        self.edit = LineEdit(self)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setClearButtonEnabled(True)
        self.edit.textChanged.connect(self.textChanged)
        self.button = PushButton("浏览", self)
        self.button.clicked.connect(self.browse)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self.edit, 1)
        row.addWidget(self.button)

    def text(self):
        return self.edit.text().strip()

    def setText(self, value):
        self.edit.setText(str(value))

    def browse(self):
        if self.mode == "directory":
            path = QFileDialog.getExistingDirectory(self, "选择目录", self.text())
        elif self.mode == "save":
            path, _ = QFileDialog.getSaveFileName(self, "选择输出文件", self.text(), self.file_filter)
        else:
            path, _ = QFileDialog.getOpenFileName(self, "选择文件", self.text(), self.file_filter)
        if path:
            self.setText(path)


class ComboSettingCard(SettingCard):
    """Setting card with a combo box whose value the page collects itself."""

    valueChanged = pyqtSignal()

    def __init__(self, icon, title, content=None, parent=None):
        super().__init__(icon, title, content, parent)
        self.combo = ComboBox(self)
        self.combo.setMinimumWidth(200)
        self.hBoxLayout.addWidget(self.combo, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.combo.currentIndexChanged.connect(lambda *_: self.valueChanged.emit())

    def addItem(self, text, data=None):
        self.combo.addItem(text, userData=data)

    def addItems(self, texts):
        self.combo.addItems(texts)

    def findData(self, data):
        return self.combo.findData(data)

    def setCurrentIndex(self, index):
        self.combo.setCurrentIndex(index)

    def currentIndex(self):
        return self.combo.currentIndex()

    def currentData(self):
        return self.combo.currentData()

    def currentText(self):
        return self.combo.currentText()

    def setCurrentText(self, text):
        self.combo.setCurrentText(text)


class SpinSettingCard(SettingCard):
    """Setting card with an integer spin box."""

    valueChanged = pyqtSignal()

    def __init__(self, icon, title, content=None, minimum=0, maximum=100, parent=None):
        super().__init__(icon, title, content, parent)
        self.spin = SpinBox(self)
        self.spin.setRange(minimum, maximum)
        self.spin.setMinimumWidth(140)
        self.hBoxLayout.addWidget(self.spin, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.spin.valueChanged.connect(lambda *_: self.valueChanged.emit())

    def setValue(self, value):
        self.spin.setValue(value)

    def value(self):
        return self.spin.value()


class PathSettingCard(PushSettingCard):
    """Push setting card that stores a path and opens a file or directory dialog."""

    valueChanged = pyqtSignal()

    def __init__(self, text, icon, title, content="", mode="file", file_filter="所有文件 (*)",
                 placeholder="未选择", parent=None):
        super().__init__(text, icon, title, content or placeholder, parent)
        self.mode = mode
        self.file_filter = file_filter
        self.placeholder = placeholder
        self.path = content
        self.clicked.connect(self.browse)

    def browse(self):
        if self.mode == "directory":
            chosen = QFileDialog.getExistingDirectory(self.window(), self.titleLabel.text(), self.path)
        else:
            chosen, _ = QFileDialog.getOpenFileName(self.window(), self.titleLabel.text(), self.path, self.file_filter)
        if chosen:
            self.setPath(chosen)

    def setPath(self, path):
        path = str(path or "")
        if path == self.path:
            return
        self.path = path
        super().setContent(self.path or self.placeholder)
        self.valueChanged.emit()

    def text(self):
        return self.path


class PaletteSettingCard(SettingCard):
    """Setting card with a color picker and a reset button."""

    colorChanged = pyqtSignal(QColor)

    def __init__(self, icon, title, content=None, color="#3268c8", parent=None):
        super().__init__(icon, title, content, parent)
        self.defaultColor = QColor(color)
        self.picker = ColorPickerButton(QColor(color), title, self)
        self.resetButton = TransparentToolButton(FluentIcon.SYNC, self)
        self.resetButton.setToolTip("恢复默认主题色")
        self.resetButton.clicked.connect(lambda: self.setColor(self.defaultColor))
        self.hBoxLayout.addWidget(self.picker, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(6)
        self.hBoxLayout.addWidget(self.resetButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.picker.colorChanged.connect(self.colorChanged)

    def setColor(self, color):
        color = QColor(color)
        changed = color != self.picker.color
        self.picker.setColor(color)
        if changed:
            self.colorChanged.emit(color)

    def color(self):
        return self.picker.color.name()
