# [Module: desktop.test_entry_model] [Status: 已完成] [Brief: 虚拟表格完整文本搜索、状态筛选和大任务模型]
from PyQt6.QtCore import QModelIndex, Qt

from mcpacklocalizer.core.pack.extraction import Entry
from mcpacklocalizer.ui.view.tasks.entry_model import EntryFilter, EntryModel


def entries():
    return [Entry("1", "namespace/iron", "chapter.snbt", ["title"], "Iron Ingot", 0, 10, "", "铁锭", "reviewed"),
            Entry("2", "namespace/gold", "chapter.snbt", ["title"], "Gold Ingot", 0, 10, "", status="failed"),
            Entry("3", "namespace/copper", "other.snbt", ["title"], "Copper Ingot", 0, 10, "")]


def test_virtual_table_is_read_only_and_preserves_full_source(qt_app):
    model = EntryModel()
    values = entries()
    values[0].source = "prefix" + "x" * 400 + "hidden-suffix"
    model.replace(values)
    assert model.rowCount() == 3 and model.columnCount() == 4
    assert model.rowCount(model.index(0, 0)) == 0
    assert model.data(QModelIndex()) is None
    assert len(model.data(model.index(0, 2))) == 350
    assert "hidden-suffix" in model.data(model.index(0, 2), Qt.ItemDataRole.ToolTipRole)
    assert not (model.flags(model.index(0, 2)) & Qt.ItemFlag.ItemIsEditable)


def test_searches_translation_filename_semantic_key_and_untruncated_source(qt_app):
    model = EntryModel()
    values = entries()
    values[0].source += "x" * 400 + "hidden-suffix"
    model.replace(values)
    proxy = EntryFilter()
    proxy.setSourceModel(model)
    for query, count in (("铁锭", 1), ("other.snbt", 1), ("namespace/gold", 1), ("INGOT", 3), ("hidden-suffix", 1)):
        proxy.set_query(query, "all")
        assert proxy.rowCount() == count


def test_untranslated_includes_failures(qt_app):
    model = EntryModel()
    model.replace(entries())
    proxy = EntryFilter()
    proxy.setSourceModel(model)
    proxy.set_query("", "untranslated")
    assert proxy.rowCount() == 2
    proxy.set_query("", "failed")
    assert proxy.rowCount() == 1
    proxy.set_query("", "reviewed")
    assert proxy.rowCount() == 1


def test_large_task_does_not_create_cell_widgets(qt_app):
    model = EntryModel()
    value = entries()[0]
    model.replace([value] * 20000)
    assert model.rowCount() == 20000
    assert model.data(model.index(19999, 3)) == "铁锭"
    model.replace([])
    assert model.rowCount() == 0
