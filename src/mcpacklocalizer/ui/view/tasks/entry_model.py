# [Module: desktop.entry_model] [Status: 已完成] [Brief: 大规模文本虚拟表格与原文译文搜索]
from PyQt6.QtCore import QAbstractTableModel, QSortFilterProxyModel, Qt
from PyQt6.QtGui import QColor

from ....application.tasks.store import STATUS, entry_hints


class EntryModel(QAbstractTableModel):
    HEADERS = ("状态", "文件 / 语言键", "原文", "译文")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = []
        self.polish_errors = {}
        self.excluded_documents = set()

    def replace(self, entries):
        self.beginResetModel()
        self.entries = entries
        self.endResetModel()

    def set_excluded_documents(self, documents):
        self.excluded_documents = set(documents)
        if self.entries:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.entries) - 1, 3))

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.entries)

    def columnCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        entry = self.entries[index.row()]
        position = f"第 {entry.script['line']} 行" if entry.script else str(entry.path[-1] if entry.path else "")
        excluded = entry.document in self.excluded_documents
        values = ["已排除" if excluded else STATUS.get(entry.status, entry.status), entry.document + " / " + position,
                  entry.source, entry.translation or ""]
        if role == Qt.ItemDataRole.DisplayRole:
            return values[index.column()].replace("\n", " ↵ ")[:350]
        if role == Qt.ItemDataRole.ToolTipRole:
            if excluded:
                return "已排除：保留识别与译文记录，不参与翻译或补丁导出。\n" + values[index.column()]
            if self.polish_errors.get(entry.id):
                return "修润候选被拦截：" + self.polish_errors[entry.id] + "\n" + values[index.column()]
            return entry_hints(entry) or values[index.column()]
        if role == Qt.ItemDataRole.ForegroundRole and index.column() == 0 and entry.status == "failed":
            return QColor("#c42b1c")
        if role == Qt.ItemDataRole.ForegroundRole and excluded:
            return QColor("#888888")


class EntryFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.query = ""
        self.status = "all"
        self.documents = None
        self.polish_failures = set()

    def set_polish_failures(self, entries):
        self.polish_failures = set(entries)
        self.invalidateFilter()

    def set_documents(self, documents):
        self.documents = frozenset(documents) if documents is not None else None
        self.invalidateFilter()

    def set_query(self, query, status):
        self.query, self.status = query.casefold(), status
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        entry = self.sourceModel().entries[row]
        if self.documents is not None and entry.document not in self.documents:
            return False
        if self.status == "untranslated" and entry.translation is not None:
            return False
        if self.status == "polish_failed" and entry.id not in self.polish_failures and not entry.error.startswith("API 修润失败："):
            return False
        if self.status not in {"all", "untranslated", "polish_failed"} and entry.status != self.status:
            return False
        return not self.query or any(self.query in text.casefold() for text in
                                     (entry.document, entry.source, entry.translation or "", entry.semantic_key))
