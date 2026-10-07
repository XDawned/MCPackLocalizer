# [Module: desktop.api_cards] [Status: 已完成] [Brief: 分组接口卡片与激活、测试菜单]
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QStackedLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    Action,
    CaptionLabel,
    CardWidget,
    DropDownPushButton,
    FlowLayout,
    FluentIcon,
    HorizontalSeparator,
    IconWidget,
    PrimaryDropDownPushButton,
    RoundMenu,
    StrongBodyLabel,
)


class ApiTypeCard(CardWidget):
    def __init__(self, title, description, icon, parent=None):
        super().__init__(parent)
        box = QVBoxLayout(self)
        box.setContentsMargins(22, 18, 22, 22)
        box.setSpacing(16)
        header = QHBoxLayout()
        image = IconWidget(icon, self)
        image.setFixedSize(28, 28)
        header.addWidget(image)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addWidget(StrongBodyLabel(title, self))
        description_label = CaptionLabel(description, self)
        description_label.setWordWrap(True)
        titles.addWidget(description_label)
        header.addLayout(titles, 1)
        box.addLayout(header)
        box.addWidget(HorizontalSeparator(self))
        self.container = QWidget(self)
        self.flow = FlowLayout(self.container, needAni=False)
        self.flow.setContentsMargins(0, 0, 0, 0)
        self.flow.setHorizontalSpacing(12)
        self.flow.setVerticalSpacing(12)
        box.addWidget(self.container)

    def clear(self):
        self.flow.takeAllWidgets()

    def add(self, card):
        self.flow.addWidget(card)


class ApiItemCard(QWidget):
    activateClicked = pyqtSignal(str)
    testClicked = pyqtSignal(str)
    editClicked = pyqtSignal(str)
    argsClicked = pyqtSignal(str)
    promptClicked = pyqtSignal(str)
    copyClicked = pyqtSignal(str)
    deleteClicked = pyqtSignal(str)

    def __init__(self, profile_id, name, description, *, builtin=False, local=False, parent=None):
        super().__init__(parent)
        self.profile_id = profile_id
        self.active = False
        self.busy = False
        self.actions = {}
        self.buttons = (DropDownPushButton(self), PrimaryDropDownPushButton(self))
        self.stack = QStackedLayout(self)
        self.stack.setContentsMargins(0, 0, 0, 0)
        icon = FluentIcon.ROBOT if builtin or local else FluentIcon.CONNECT
        for button in self.buttons:
            button.setText(button.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, 202))
            button.setIcon(icon)
            button.setFixedWidth(260)
            button.setToolTip(name + "\n" + description)
            menu = RoundMenu(parent=button)
            entries = [
                ("activate", "激活接口", FluentIcon.ACCEPT, self.activateClicked),
                ("test", "测试接口", FluentIcon.SEND, self.testClicked),
                ("edit", "模型与设置" if builtin else "编辑接口", FluentIcon.EDIT, self.editClicked),
                ("prompts", "编辑翻译模板", FluentIcon.EDIT, self.promptClicked),
            ]
            if not builtin:
                entries += [("args", "调整参数", FluentIcon.DEVELOPER_TOOLS, self.argsClicked),
                            ("copy", "复制接口", FluentIcon.COPY, self.copyClicked),
                            ("delete", "删除接口", FluentIcon.DELETE, self.deleteClicked)]
            for key, title, action_icon, signal in entries:
                if key in {"edit", "copy", "delete"}:
                    menu.addSeparator()
                action = Action(action_icon, title, parent=menu,
                                triggered=lambda checked=False, signal=signal: signal.emit(self.profile_id))
                self.actions.setdefault(key, []).append(action)
                menu.addAction(action)
            button.setMenu(menu)
            button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            button.customContextMenuRequested.connect(lambda pos, menu=menu, button=button: menu.exec(button.mapToGlobal(pos)))
            self.stack.addWidget(button)
        self.setFixedSize(260, self.buttons[0].sizeHint().height())
        self.set_active(False)

    def set_active(self, active):
        self.active = active
        self.stack.setCurrentIndex(1 if active else 0)
        for action in self.actions["activate"]:
            action.setEnabled(not active and not self.busy)

    def set_busy(self, busy):
        self.busy = busy
        for action in self.actions["test"]:
            action.setEnabled(not busy)
        for action in self.actions["activate"]:
            action.setEnabled(not busy and not self.active)
