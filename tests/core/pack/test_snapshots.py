# [Module: tests.snapshots] [Status: 开发中] [Brief: 增量复用、人工修订保留、迁移歧义和持久化检查点]
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from mcpacklocalizer.core.pack.extraction import Entry, Scan
from mcpacklocalizer.core.pack.snapshots import Store, reuse_baseline


def entry(**kwargs):
    original = Entry("one", "ftb:A/title", "a.snbt", ["title"], "Iron Ingot", 0, 12, "title", "铁锭", "reviewed", "manual")
    return replace(original, **kwargs)


def scan(entries):
    return Scan("C:/mcpl-tests/pack", "pack", "en_us", "zh_cn", entries=entries)


def test_unchanged_preserves_manual_but_changed_source_is_not_reused():
    current = scan([entry(translation=None), entry(id="two", semantic_key="ftb:B/title", source="Gold Ingot", translation=None)])
    old = scan([entry(), entry(id="two", semantic_key="ftb:B/title")])
    counts = reuse_baseline(current, old)
    assert current.entries[0].translation == "铁锭" and current.entries[0].origin == "manual"
    assert current.entries[1].translation is None and counts["changed"] == 1


def test_move_reuses_only_unambiguous_exact_source_and_context():
    current = scan([entry(id="new", translation=None)])
    counts = reuse_baseline(current, scan([entry()]))
    assert counts["reused"] == 1 and counts["moved"] == 1 and counts["removed"] == 0
    current = scan([entry(id="new", translation=None)])
    counts = reuse_baseline(current, scan([entry(), entry(id="other", translation="铁条")]))
    assert current.entries[0].translation is None and counts["ambiguous"] == 1


def test_removed_duplicate_is_counted_without_marking_move_as_deletion():
    current = scan([entry(id="new", translation=None)])
    counts = reuse_baseline(current, scan([entry(), entry(id="duplicate")]))
    assert counts["moved"] == 1 and counts["removed"] == 1 and counts["reused"] == 1


def test_different_pack_cannot_be_baseline():
    old = scan([entry()])
    old.pack_id = "other"
    with pytest.raises(ValueError, match="其他整合包"):
        reuse_baseline(scan([entry()]), old)


def test_baseline_missing_placeholder_requires_current_task_opt_in():
    old = scan([entry(source="&bGrapes&r", translation="葡萄")])
    old.metadata["model_config"] = {"allow_missing_placeholders": True}
    current = scan([entry(source="&bGrapes&r", translation=None)])
    assert reuse_baseline(current, old)["reused"] == 0
    assert current.entries[0].translation is None
    assert reuse_baseline(current, old, True)["reused"] == 1
    assert current.entries[0].translation == "葡萄"


def test_committed_translation_survives_store_reload(mocker):
    connection = sqlite3.connect(":memory:")
    mocker.patch("mcpacklocalizer.core.pack.snapshots.sqlite3.connect", return_value=connection)
    mocker.patch.object(Path, "mkdir")
    store = Store(Path("C:/mcpl-tests/output"), create=True)
    original = scan([entry(translation=None)])
    original.metadata["model_config"] = {"allow_missing_placeholders": True}
    store.create(original)
    store.update(entry())
    loaded = store.load()
    assert loaded.entries[0].translation == "铁锭" and loaded.entries[0].origin == "manual"
    assert loaded.metadata["model_config"]["allow_missing_placeholders"] is True
    store.close()
