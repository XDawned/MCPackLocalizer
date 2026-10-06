import json
import sqlite3

import pytest

from mcpacklocalizer.core.mods.library import ModLibrary
from mcpacklocalizer.core.pack.extraction import digest


def record(**updates):
    return {"provider_ids": ["example"], "namespace": "example", "key": "item.example.iron",
            "source": "Iron %s", "translation": "铁 %s", "source_locale": "en_us", "target_locale": "zh_cn",
            **updates}


def test_reviewed_exact_identity_reuses_across_version_provenance(tmp_path):
    path = tmp_path / "library.sqlite3"
    with ModLibrary(path) as library:
        number = library.add(record(), "reviewed", {"pack_id": "pack-a", "game_version": "1.20.1"})
        result = library.lookup(record())
        assert result == {"status": "reused", "translation": "铁 %s", "record_id": number, "state": "reviewed"}
        assert library.lookup(record(source="Gold %s"))["status"] == "source_changed"
        assert library.lookup(record(key="other"))["status"] == "unavailable"
        assert library.lookup(record(namespace="other"))["status"] == "unavailable"
        assert library.lookup(record(provider_ids=["other"]))["status"] == "unavailable"
        assert library.lookup(record(target_locale="zh_tw"))["status"] == "unavailable"
        assert library.lookup(record(source="Iron %s "))["status"] == "source_changed"


def test_drafts_are_opt_in_and_cannot_override_reviewed_translation(tmp_path):
    with ModLibrary(tmp_path / "memory.sqlite3") as library:
        library.add(record(), "draft")
        assert library.lookup(record())["status"] == "draft_only"
        assert library.lookup(record(), "all")["translation"] == "铁 %s"
        library.add(record(translation="铁制 %s"), "reviewed")
        assert library.lookup(record(), "all")["translation"] == "铁制 %s"
        assert library.lookup(record(), "off")["status"] == "disabled"


def test_conflict_needs_explicit_resolution_and_rejection_preserves_history(tmp_path):
    with ModLibrary(tmp_path / "memory.sqlite3") as library:
        old = library.add(record(), "reviewed")
        new = library.add(record(translation="铁制 %s"), "reviewed")
        assert library.lookup(record())["status"] == "conflict"
        library.resolve(new)
        assert library.lookup(record())["translation"] == "铁制 %s"
        assert library.stats()["states"]["superseded"] == 1
        library.resolve(new, reject=True)
        assert library.lookup(record())["status"] == "unavailable"
        library.add(record(), "reviewed")
        assert library.lookup(record())["status"] == "unavailable"  # Import never resurrects superseded rows.
        library.resolve(old)
        assert library.lookup(record())["translation"] == "铁 %s"


def test_strict_format_is_required_even_for_reviewed_records(tmp_path):
    with ModLibrary(tmp_path / "memory.sqlite3") as library:
        with pytest.raises(ValueError):
            library.add(record(translation="铁"), "reviewed")
        assert library.stats()["records"] == 0
        with pytest.raises(ValueError, match="provider"):
            library.add(record(provider_ids=[]))


def test_portable_export_import_preserves_states_and_provenance(tmp_path):
    exported = tmp_path / "portable.json"
    with ModLibrary(tmp_path / "a.sqlite3") as library:
        library.add(record(), "reviewed", {"pack_id": "a", "provider_versions": {"example": "1.0"}})
        library.add(record(key="draft", translation="铁 %s"), "draft")
        library.export(exported)
    payload = json.loads(exported.read_bytes())
    with ModLibrary(tmp_path / "b.sqlite3") as library:
        result = library.import_records(payload)
        assert result["imported"] == 2
        assert library.lookup(record())["state"] == "reviewed"
        assert library.lookup(record(key="draft"))["status"] == "draft_only"
        assert library.list_records(state="draft")[0]["key"] == "draft"
        library.export(tmp_path / "roundtrip.json")
    roundtrip = json.loads((tmp_path / "roundtrip.json").read_bytes())
    assert roundtrip["records"][0]["provenance"][0]["payload"]["history"][0]["payload"]["pack_id"] == "a"


def test_invalid_portable_checksum_is_rejected_before_record_writes(tmp_path):
    value = record() | {"source_sha256": digest("different"), "state": "reviewed"}
    with ModLibrary(tmp_path / "memory.sqlite3") as library:
        with pytest.raises(ValueError, match="校验和"):
            library.import_records({"kind": "mcpl-mod-library", "schema_version": 1, "records": [value]})
        assert library.stats()["records"] == 0


def test_readonly_missing_library_creates_no_files_and_unrelated_database_is_preserved(tmp_path):
    path = tmp_path / "absent" / "memory.sqlite3"
    with ModLibrary(path, readonly=True) as library:
        assert library.lookup(record())["status"] == "unavailable"
    assert not path.parent.exists()
    other = tmp_path / "other.sqlite3"
    with sqlite3.connect(other) as db:
        db.execute("CREATE TABLE original(value TEXT)")
    with pytest.raises(ValueError, match="数据结构"):
        ModLibrary(other)
    with sqlite3.connect(other) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [("original",)]
