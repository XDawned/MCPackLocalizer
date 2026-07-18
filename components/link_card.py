# coding:utf-8
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget, QHBoxLayout
from qfluentwidgets import IconWidget, FluentIcon, TextWrap, SingleDirectionScrollArea

from common.style_sheet import StyleSheet


class LinkCard(QFrame):

    def __init__(self, icon, title, content, url, parent=None):
        super().__init__(parent=parent)
        self.url = QUrl(url)
        self.setFixedSize(198, 220)
        self.iconWidget = IconWidget(icon, self)
        self.titleLabel = QLabel(title, self)
        self.contentLabel = QLabel(TextWrap.wrap(content, 28, False)[0], self)
        self.urlWidget = IconWidget(FluentIcon.LINK, self)

        self.__initWidget()

    def __initWidget(self):
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.iconWidget.setFixedSize(54, 54)
        self.urlWidget.setFixedSize(16, 16)

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setSpacing(0)
        self.vBoxLayout.setContentsMargins(24, 24, 0, 13)
        self.vBoxLayout.addWidget(self.iconWidget)
        self.vBoxLayout.addSpacing(16)
        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addSpacing(8)
        self.vBoxLayout.addWidget(self.contentLabel)
        self.vBoxLayout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.urlWidget.move(170, 192)

        self.titleLabel.setObjectName('titleLabel')
        self.contentLabel.setObjectName('contentLabel')

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        QDesktopServices.openUrl(self.url)


class LinkCardView(SingleDirectionScrollArea):
    """ Link card view """

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Orientation.Horizontal)
        self.view = QWidget(self)
        self.hBoxLayout = QHBoxLayout(self.view)

        self.hBoxLayout.setContentsMargins(36, 0, 0, 0)
        self.hBoxLayout.setSpacing(12)
        self.hBoxLayout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.view.setObjectName('view')
        StyleSheet.LINK_CARD.apply(self)

    def addCard(self, icon, title, content, url):
        """ add link card """
        card = LinkCard(icon, title, content, url, self.view)
        self.hBoxLayout.addWidget(card, 0, Qt.AlignmentFlag.AlignLeft)


class SuggestCard(QFrame):
    clickSignal = pyqtSignal(str)
    def __init__(self, author, trans, ori, icon, parent=None):
        super().__init__(parent=parent)
        self.setFixedHeight(50)
        self.authorLabel = QLabel(author)
        self.transLabel = QLabel(trans)
        self.transLabel.setFixedHeight(20)
        self.oriLabel = QLabel(ori)
        self.oriLabel.setFixedHeight(15)
        self.rightWidget = QWidget()

        self.suggestIcon = IconWidget(icon)

        self.hBoxLayout = QHBoxLayout(self)
        self.rightLayout = QVBoxLayout()

        self.__initWidget()

    def __initWidget(self):
        self.suggestIcon.setFixedSize(18, 18)
        self.__initLayout()
        self.setLayout(self.hBoxLayout)

        self.transLabel.setObjectName('transLabel')
        self.oriLabel.setObjectName('oriLabel')
        self.authorLabel.setObjectName('authorLabel')

    def __initLayout(self):
        self.hBoxLayout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.hBoxLayout.setSpacing(0)
        self.hBoxLayout.setContentsMargins(0, 0, 0, 0)

        self.hBoxLayout.addWidget(self.suggestIcon, 0, Qt.AlignmentFlag.AlignLeft)
        self.rightLayout.addWidget(self.transLabel)
        self.rightLayout.addWidget(self.oriLabel)
        self.rightWidget.setLayout(self.rightLayout)
        self.hBoxLayout.addWidget(self.rightWidget, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addWidget(self.authorLabel, 0, Qt.AlignmentFlag.AlignLeft)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clickSignal.emit(self.transLabel.text())


class SuggestCardWidget(QFrame):

    clickSignal = pyqtSignal(str)
    cardList = []

    def __init__(self, parent=None):
        super().__init__(parent)
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(10, 0, 0, 0)
        self.vBoxLayout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.vBoxLayout.setSpacing(0)
        self.setFixedHeight(52)
        self.setObjectName('view')

    def addCard(self, icon, trans, ori, author):
        self.setFixedHeight(self.height()+52)
        card = SuggestCard(icon=icon, trans=trans, ori=ori, author=author, parent=self)
        card.clickSignal.connect(self.clickSignal)
        self.cardList.append(card)
        self.vBoxLayout.addWidget(card, 0, Qt.AlignmentFlag.AlignVCenter)
        StyleSheet.LINK_CARD.apply(self)

    def removeAllCard(self):
        self.setFixedHeight(52)
        while self.vBoxLayout.count() > 0:
            item = self.vBoxLayout.itemAt(0)
            widget = item.widget()
            self.vBoxLayout.removeWidget(widget)
            widget.deleteLater()
