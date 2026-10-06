"""Versioned, local translation memory for mod language keys."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ..pack.extraction import digest, locale_name
from ..pack.snapshots import atomic_write
from ..translation.local import validate

STATES = {"draft", "reviewed", "rejected", "superseded"}
POLICIES = {"reviewed", "all", "off"}


def now():
    return datetime.now(UTC).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def identity(record):
    providers = record.get("provider_ids", [])
    if (not isinstance(providers, list) or not providers
            or any(not isinstance(p, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]*", p) for p in providers)):
        raise ValueError("共享译文需要经过验证的 provider_ids")
    namespace = record.get("namespace", "")
    if not isinstance(namespace, str) or not re.fullmatch(r"[a-z0-9_.-]+", namespace) or namespace in {".", ".."}:
        raise ValueError("翻译命名空间无效")
    for name in ("key", "source", "source_locale", "target_locale"):
        if not isinstance(record.get(name), str) or not record[name]:
            raise ValueError(f"共享记录必须提供 {name}")
    for name in ("source_locale", "target_locale"):
        if record[name] != locale_name(record[name]):
            raise ValueError("共享语言代码必须为小写")
    return (record["source_locale"], record["target_locale"], canonical(sorted(set(providers))),
            namespace, record["key"], digest(record["source"]))


class ModLibrary:
    def __init__(self, path: Path, readonly=False):
        self.path = path.resolve()
        self.db = None
        if readonly and not self.path.is_file():
            return
        if readonly:
            self.db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=10)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(self.path, timeout=10)
        self.db.row_factory = sqlite3.Row
        if readonly:
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version != 1 or self.db.execute("PRAGMA application_id").fetchone()[0] != 0x4D43504C:
                self.close()
                raise ValueError("不支持的模组译库数据结构")
        else:
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            application = self.db.execute("PRAGMA application_id").fetchone()[0]
            existing = self.db.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            if version not in {0, 1} or (version == 1 and application != 0x4D43504C) or (version == 0 and existing):
                self.close()
                raise ValueError("不支持的模组译库数据结构")
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS translations (
                    id INTEGER PRIMARY KEY, source_locale TEXT NOT NULL, target_locale TEXT NOT NULL,
                    provider_key TEXT NOT NULL, namespace TEXT NOT NULL, lang_key TEXT NOT NULL,
                    source_hash TEXT NOT NULL, source_text TEXT NOT NULL, translation TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('draft','reviewed','rejected','superseded')),
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(source_locale,target_locale,provider_key,namespace,lang_key,source_hash,translation)
                );
                CREATE INDEX IF NOT EXISTS lookup_key ON translations
                    (source_locale,target_locale,provider_key,namespace,lang_key,source_hash,state);
                CREATE TABLE IF NOT EXISTS provenance (
                    record_id INTEGER NOT NULL REFERENCES translations(id), kind TEXT NOT NULL,
                    payload TEXT NOT NULL, payload_hash TEXT NOT NULL, created_at TEXT NOT NULL,
                    UNIQUE(record_id,kind,payload_hash)
                );
                PRAGMA user_version=1;
                PRAGMA application_id=0x4D43504C;
            """)
            self.db.execute("PRAGMA foreign_keys=ON")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None

    def _public(self, row):
        return {"id": row["id"], "provider_ids": json.loads(row["provider_key"]),
                "namespace": row["namespace"], "key": row["lang_key"], "source": row["source_text"],
                "source_sha256": row["source_hash"], "source_locale": row["source_locale"],
                "target_locale": row["target_locale"], "translation": row["translation"], "state": row["state"],
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def _event(self, record_id, kind, payload):
        serialized = canonical(payload)
        self.db.execute("INSERT OR IGNORE INTO provenance VALUES (?,?,?,?,?)",
                        (record_id, kind, serialized, digest(serialized), now()))

    def add(self, record, state="draft", provenance=None):
        if self.db is None:
            raise ValueError("译库不可写")
        if state not in STATES:
            raise ValueError("审核状态无效")
        key = identity(record)
        translation = record.get("translation")
        if not isinstance(translation, str):
            raise TypeError("共享译文必须是文字")
        validate(record["source"], translation)  # Shared memory always requires the strict format policy.
        with self.db:
            row = self.db.execute("SELECT * FROM translations WHERE source_locale=? AND target_locale=? "
                "AND provider_key=? AND namespace=? AND lang_key=? AND source_hash=? AND translation=?",
                (*key, translation)).fetchone()
            if row:
                if row["source_text"] != record["source"]:
                    raise ValueError("译库原文哈希冲突")
                record_id = row["id"]
                # Import/draft publication never reactivates rejected or superseded records.
                if row["state"] == "draft" and state == "reviewed":
                    self.db.execute("UPDATE translations SET state='reviewed',updated_at=? WHERE id=?", (now(), record_id))
            else:
                cursor = self.db.execute("INSERT INTO translations (source_locale,target_locale,provider_key,namespace,"
                    "lang_key,source_hash,source_text,translation,state,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (*key, record["source"], translation, state, now(), now()))
                record_id = cursor.lastrowid
            self._event(record_id, "publication", provenance or {})
        return record_id

    def lookup(self, record, policy="reviewed"):
        if policy not in POLICIES:
            raise ValueError("复用策略无效")
        if policy == "off":
            return {"status": "disabled"}
        if not record.get("reusable", True):
            return {"status": "ineligible"}
        try:
            key = identity(record)
        except ValueError:
            return {"status": "ineligible"}
        if self.db is None:
            return {"status": "unavailable"}
        rows = self.db.execute("SELECT * FROM translations WHERE source_locale=? AND target_locale=? AND provider_key=? "
                               "AND namespace=? AND lang_key=? AND state IN ('draft','reviewed') "
                               "ORDER BY (state='reviewed') DESC,updated_at DESC,id DESC", key[:5]).fetchall()
        exact = [r for r in rows if r["source_hash"] == key[5] and r["source_text"] == record["source"]]
        reviewed = [r for r in exact if r["state"] == "reviewed"]
        accepted = reviewed or (exact if policy == "all" else [])
        valid = []
        for row in accepted:
            try:
                validate(record["source"], row["translation"])
                valid.append(row)
            except ValueError:
                continue
        translations = {row["translation"] for row in valid}
        if len(translations) == 1:
            row = valid[0]
            return {"status": "reused", "translation": row["translation"], "record_id": row["id"], "state": row["state"]}
        if len(translations) > 1:
            return {"status": "conflict", "candidates": [self._public(r) for r in valid[:5]]}
        if exact:
            return {"status": "draft_only" if not accepted else "invalid", "candidates": [self._public(r) for r in exact[:5]]}
        if rows:
            return {"status": "source_changed", "candidates": [self._public(r) for r in rows[:5]]}
        return {"status": "unavailable"}

    def resolve(self, record_id, reject=False):
        if self.db is None:
            raise ValueError("译库记录不存在")
        row = self.db.execute("SELECT * FROM translations WHERE id=?", (record_id,)).fetchone()
        if row is None:
            raise ValueError("译库记录不存在")
        validate(row["source_text"], row["translation"])
        with self.db:
            if not reject:
                self.db.execute("UPDATE translations SET state='superseded',updated_at=? WHERE source_locale=? AND "
                    "target_locale=? AND provider_key=? AND namespace=? AND lang_key=? AND source_hash=? AND id<>? "
                    "AND state IN ('draft','reviewed')", (now(), row["source_locale"], row["target_locale"],
                    row["provider_key"], row["namespace"], row["lang_key"], row["source_hash"], record_id))
            state = "rejected" if reject else "reviewed"
            self.db.execute("UPDATE translations SET state=?,updated_at=? WHERE id=?", (state, now(), record_id))
            self._event(record_id, "reject" if reject else "resolve", {"selected_id": record_id})
        return {"record_id": record_id, "state": state}

    def stats(self):
        counts = dict.fromkeys(sorted(STATES), 0)
        if self.db is not None:
            counts.update({r["state"]: r["n"] for r in self.db.execute("SELECT state,count(*) AS n FROM translations GROUP BY state")})
        return {"path": str(self.path), "records": sum(counts.values()), "states": counts}

    def list_records(self, namespace=None, key=None, state=None, limit=20):
        if not 1 <= limit <= 1000 or (state is not None and state not in STATES):
            raise ValueError("译库列表筛选条件或数量上限无效")
        if self.db is None:
            return []
        conditions, values = [], []
        for column, value in (("namespace", namespace), ("lang_key", key), ("state", state)):
            if value is not None:
                conditions.append(column + "=?")
                values.append(value)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        return [self._public(row) for row in self.db.execute(
            "SELECT * FROM translations" + where + " ORDER BY updated_at DESC,id DESC LIMIT ?", (*values, limit))]

    def export(self, output):
        if output.exists():
            raise ValueError("译库导出目标已存在")
        records = []
        if self.db is not None:
            for row in self.db.execute("SELECT * FROM translations ORDER BY id"):
                record = self._public(row)
                record["provenance"] = [{"kind": e["kind"], "payload": json.loads(e["payload"]), "created_at": e["created_at"]}
                    for e in self.db.execute("SELECT * FROM provenance WHERE record_id=? ORDER BY rowid", (row["id"],))]
                records.append(record)
        atomic_write(output, json.dumps({"schema_version": 1, "kind": "mcpl-mod-library", "records": records},
                                       ensure_ascii=False, indent=2))
        return {"output": str(output.resolve()), "records": len(records)}

    def import_records(self, payload):
        if not isinstance(payload, dict):
            raise TypeError("可移植模组译库必须是 JSON 对象")
        if payload.get("schema_version") != 1 or payload.get("kind") != "mcpl-mod-library":
            raise ValueError("不支持的可移植模组译库")
        records = payload.get("records")
        if not isinstance(records, list):
            raise TypeError("译库记录必须是数组")
        # Validate the complete input before the first write.
        for record in records:
            if not isinstance(record, dict) or record.get("state") not in STATES:
                raise ValueError("译库记录无效")
            identity(record)
            if not isinstance(record.get("translation"), str):
                raise TypeError("共享译文必须是文字")
            if record.get("source_sha256") != digest(record["source"]):
                raise ValueError("可移植译库原文校验和不匹配")
            validate(record["source"], record["translation"])
        count = 0
        for record in records:
            self.add(record, record["state"], {"imported_record_id": record.get("id"), "history": record.get("provenance", [])})
            count += 1
        return {"imported": count, **self.stats()}


def record_for_entry(scan, entry):
    detail = scan.metadata.get("mod_entries", {}).get(entry.id)
    if not detail or not detail.get("reusable"):
        return None
    return {"namespace": detail["namespace"], "key": detail["key"], "provider_ids": detail["provider_ids"],
            "source": entry.source, "translation": entry.translation, "source_locale": scan.source_locale,
            "target_locale": scan.target_locale, "reusable": detail["reusable"]}


def reuse_library(scan, path, policy="reviewed"):
    counts = {"reused": 0, "source_changed": 0, "conflict": 0, "draft_only": 0, "ineligible": 0, "invalid": 0}
    existing = scan.metadata.get("mod_library", {}).get("matches", {})
    suggestions = {entry.id: existing[entry.id] for entry in scan.entries
                   if entry.id in existing and entry.translation is not None and entry.origin.startswith("mod-library-")}
    counts["reused"] = len(suggestions)
    with ModLibrary(path, readonly=True) as library:
        for entry in scan.entries:
            if entry.translation is not None:
                continue
            record = record_for_entry(scan, entry)
            result = library.lookup(record, policy) if record else {"status": "ineligible"}
            status = result["status"]
            if status == "reused" and scan.metadata.get("legacy_mod_language") and any(
                    c in result["translation"] for c in ("\n", "\r")):
                result = {"status": "invalid", "candidates": [result], "reason": "Literal newline cannot fit legacy .lang"}
                status = "invalid"
            if status in counts:
                counts[status] += 1
            if status == "reused":
                entry.translation, entry.status, entry.origin, entry.error = (
                    result["translation"], "reused", "mod-library-" + result["state"], "")
                suggestions[entry.id] = result
            elif result.get("candidates"):
                suggestions[entry.id] = result
    scan.metadata["mod_library"] = {"path": str(path.resolve()), "policy": policy, "counts": counts, "matches": suggestions}
    return counts


def publish_scan(scan, path, include_drafts=True, only_entry=None):
    candidates, skipped = [], 0
    for entry in scan.entries:
        if only_entry is not None and entry.id != only_entry:
            continue
        record = record_for_entry(scan, entry)
        if record is None or entry.translation is None:
            continue
        reviewed = entry.origin == "manual" or entry.origin == "mod-library-reviewed"
        if not include_drafts and not reviewed:
            continue
        try:
            validate(entry.source, entry.translation)
        except ValueError:
            skipped += 1
            continue
        provenance = {"pack_id": scan.pack_id, "minecraft_version": scan.metadata.get("minecraft_version"),
                      "loader": scan.metadata.get("loader"), "entry_id": entry.id, "origin": entry.origin,
                      "provider_versions": scan.metadata["mod_entries"][entry.id].get("provider_versions", {}),
                      "task_model_at_publication": scan.metadata.get("model_config", {}).get("model"),
                      "task_created_at": scan.metadata.get("created_at")}
        candidates.append((record, "reviewed" if reviewed else "draft", provenance))
    ids = []
    if candidates:
        with ModLibrary(path) as library:
            for record, state, provenance in candidates:
                ids.append(library.add(record, state, provenance))
    return {"published": len(ids), "skipped_invalid_format": skipped, "record_ids": ids, "path": str(path.resolve())}
