# [Module: mcpacklocalizer.core.pack.snapshots] [Status: 开发中] [Brief: SQLite 逐条检查点、便携快照与版本升级复用]
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from ..kubejs.javascript import split_translation
from ..translation.local import validate_entry
from .extraction import Entry, Scan


def atomic_write(path: Path, content: str | bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        if isinstance(content, bytes):
            temporary.write_bytes(content)
        else:
            temporary.write_text(content, encoding="utf-8", newline="")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_snapshot(path: Path) -> Scan:
    if path.is_dir():
        database = path / "state.sqlite3"
        if database.is_file():
            # An interrupted run may have committed entries newer than the JSON export.
            connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
            try:
                connection.execute("BEGIN")
                row = connection.execute("SELECT payload FROM metadata WHERE id=1").fetchone()
                if row is None:
                    raise ValueError("任务检查点缺少元数据")
                data = json.loads(row[0])
                data["entries"] = [json.loads(row[0]) for row in
                                   connection.execute("SELECT payload FROM entries ORDER BY rowid")]
            finally:
                connection.close()
            return Scan.from_dict(data)
        path = path / "snapshot.json"
    return Scan.from_dict(json.loads(path.read_text(encoding="utf-8")))


def reuse_baseline(current: Scan, old: Scan, allow_missing_placeholders=False):
    if (current.pack_id, current.source_locale, current.target_locale) != (old.pack_id, old.source_locale, old.target_locale):
        raise ValueError("基准属于其他整合包或语言对；请在各版本间使用相同的 --pack-id")
    by_id = {entry.id: entry for entry in old.entries}
    by_semantic = {}
    for entry in old.entries:
        by_semantic.setdefault(entry.semantic_key, []).append(entry)
    matched_old = set(by_id).intersection(e.id for e in current.entries)
    counts = {"unchanged": 0, "changed": 0, "added": 0, "moved": 0, "reused": 0, "ambiguous": 0, "removed": 0}
    for entry in current.entries:
        direct = by_id.get(entry.id)
        peers = by_semantic.get(entry.semantic_key, [])
        if direct:
            kind = "unchanged" if (entry.source, entry.context) == (direct.source, direct.context) else "changed"
        else:
            remaining = [p for p in peers if p.id not in matched_old]
            kind = "moved" if remaining else "added"
            if remaining:
                # Count physical entries once: a renamed source is not also deleted.
                previous = next((p for p in remaining if (p.source, p.context) == (entry.source, entry.context)), remaining[0])
                matched_old.add(previous.id)
        counts[kind] += 1
        matches = []
        for previous in ([direct] if direct else peers):
            if previous and (previous.source, previous.context) == (entry.source, entry.context) and previous.translation:
                try:
                    validate_entry(entry, previous.translation, allow_missing_placeholders)
                    if entry.script:
                        split_translation(entry.source, previous.translation)
                    matches.append(previous)
                except ValueError:
                    continue
        translations = {p.translation for p in matches}
        if len(translations) == 1:
            entry.translation = next(iter(translations))
            entry.status = "reused"
            entry.origin = "manual" if any(p.origin == "manual" for p in matches) else "baseline"
            counts["reused"] += 1
        elif len(translations) > 1:
            entry.error = "基准译文存在冲突，未自动复用"
            counts["ambiguous"] += 1
    counts["removed"] = len(set(by_id) - matched_old)
    current.metadata["delta"] = counts
    current.metadata["obsolete_patch_files"] = sorted({d.target for d in old.documents} - {d.target for d in current.documents})
    return counts


class Store:
    def __init__(self, output: Path, create=False):
        self.output = output.resolve()
        database = self.output / "state.sqlite3"
        if not create and not database.is_file():
            raise ValueError(f"{self.output} 中没有可续跑的任务")
        self.output.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(database)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS metadata (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS entries (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")

    def create(self, scan: Scan):
        if self.db.execute("SELECT count(*) FROM metadata").fetchone()[0]:
            raise ValueError("任务已存在；请使用续跑")
        data = scan.to_dict()
        entries = data.pop("entries")
        with self.db:
            self.db.execute("INSERT INTO metadata VALUES (1, ?)", (json.dumps(data, ensure_ascii=False),))
            self.db.executemany("INSERT INTO entries VALUES (?, ?)",
                                [(e["id"], json.dumps(e, ensure_ascii=False)) for e in entries])

    def load(self):
        row = self.db.execute("SELECT payload FROM metadata WHERE id=1").fetchone()
        if not row:
            raise ValueError("任务元数据缺失")
        data = json.loads(row[0])
        data["entries"] = [json.loads(r[0]) for r in self.db.execute("SELECT payload FROM entries ORDER BY rowid")]
        return Scan.from_dict(data)

    def update(self, entry: Entry):
        with self.db:
            cursor = self.db.execute("UPDATE entries SET payload=? WHERE id=?", (json.dumps(asdict(entry), ensure_ascii=False), entry.id))
            if cursor.rowcount != 1:
                raise ValueError("未知的条目 ID")

    def metadata(self, scan: Scan):
        data = scan.to_dict()
        data.pop("entries")
        with self.db:
            self.db.execute("UPDATE metadata SET payload=? WHERE id=1", (json.dumps(data, ensure_ascii=False),))

    def update_many(self, entries, scan):
        data = scan.to_dict()
        data.pop("entries")
        with self.db:
            for entry in entries:
                cursor = self.db.execute("UPDATE entries SET payload=? WHERE id=?",
                                         (json.dumps(asdict(entry), ensure_ascii=False), entry.id))
                if cursor.rowcount != 1:
                    raise ValueError("未知的条目 ID")
            self.db.execute("UPDATE metadata SET payload=? WHERE id=1", (json.dumps(data, ensure_ascii=False),))

    def export(self):
        scan = self.load()
        data = scan.to_dict()
        atomic_write(self.output / "snapshot.json", json.dumps(data, ensure_ascii=False, indent=2))
        return scan

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
