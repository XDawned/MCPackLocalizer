# coding:utf-8
from PyQt6.QtWidgets import QWidget, QStackedWidget, QVBoxLayout
from qfluentwidgets import Pivot, qrouter

from common.style_sheet import StyleSheet
from .lang_widget import BrowseLangWidget, ReviewLangWidget


class PivotInterface(QWidget):
    """ Pivot interface """

    def __init__(self, data, parent=None):
        super().__init__(parent=parent)
        self.data = data
        self.pivot = Pivot(self)
        self.stackedWidget = QStackedWidget(self)
        self.vBoxLayout = QVBoxLayout(self)

        self.browseInterface = BrowseLangWidget(self.data)
        self.browseInterface.doubleClicked.connect(self.handleJumpToReview)
        self.reviewInterface = ReviewLangWidget(self.data)

        # add items to pivot
        self.addSubInterface(self.browseInterface, 'browseInterface', self.tr('浏览视图'))
        self.addSubInterface(self.reviewInterface, 'reviewInterface', self.tr('编辑视图'))

        self.vBoxLayout.addWidget(self.pivot, 0)
        self.vBoxLayout.addWidget(self.stackedWidget)
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        StyleSheet.NAVIGATION_VIEW_INTERFACE.apply(self)

        self.stackedWidget.currentChanged.connect(self.onCurrentIndexChanged)
        self.stackedWidget.setCurrentWidget(self.browseInterface)
        self.pivot.setCurrentItem(self.browseInterface.objectName())

        qrouter.setDefaultRouteKey(self.stackedWidget, self.browseInterface.objectName())

    def addSubInterface(self, widget: QWidget, objectName, text):
        widget.setObjectName(objectName)
        self.stackedWidget.addWidget(widget)
        self.pivot.addItem(
            routeKey=objectName,
            text=text,
            onClick=lambda: self.stackedWidget.setCurrentWidget(widget)
        )

    def onCurrentIndexChanged(self, index):
        # if index == 1:
        #     self.data = self.browseInterface.data
        #     self.reviewInterface.update_table(self.data)
        # else:
        #     self.data = self.reviewInterface.data_array
        #     self.browseInterface.update_table(self.data)
        widget = self.stackedWidget.widget(index)
        self.pivot.setCurrentItem(widget.objectName())
        qrouter.push(self.stackedWidget, widget.objectName())

    def handleJumpToReview(self, row):
        # self.pivot.setCurrentItem(self.reviewInterface.objectName())
        self.reviewInterface.jump_index_edit.setText(self.tr(str(row+1)))
        self.reviewInterface.jump_to()
        self.stackedWidget.setCurrentWidget(self.reviewInterface)

