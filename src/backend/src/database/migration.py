"""
数据库迁移与 Schema 修复

为历史 SQLite 数据库补齐缺失字段并修正旧约束。
"""

try:
    from .engine import Base, engine, settings
except ImportError:
    from src.database.engine import Base, engine, settings  # type: ignore


def _table_exists(cursor, table_name: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _get_table_columns(cursor, table_name: str) -> dict[str, tuple]:
    cursor.execute(f"PRAGMA table_info({table_name})")
    rows = cursor.fetchall()
    return {row[1]: row for row in rows}


def _has_unique_source_hash_index(cursor) -> bool:
    cursor.execute("PRAGMA index_list(translation_cache)")
    for row in cursor.fetchall():
        index_name = row[1]
        is_unique = int(row[2] or 0) == 1
        if not is_unique:
            continue
        cursor.execute(f"PRAGMA index_info({index_name})")
        index_columns = [info_row[2] for info_row in cursor.fetchall()]
        if index_columns == ["source_hash"]:
            return True
    return False


def _rebuild_translation_tasks_table(cursor):
    """重建 translation_tasks 表，使其兼容本地翻译任务。"""
    cursor.execute("DROP TABLE IF EXISTS translation_tasks_new")
    cursor.execute(
        """
        CREATE TABLE translation_tasks_new (
            id INTEGER NOT NULL,
            modpack_version_id INTEGER,
            local_modpack_id INTEGER,
            local_path TEXT,
            scan_result_json TEXT,
            status VARCHAR(32) NOT NULL,
            config_json TEXT,
            total_items INTEGER,
            completed_items INTEGER,
            tokens_consumed INTEGER,
            cost FLOAT,
            created_at DATETIME,
            finished_at DATETIME,
            PRIMARY KEY (id),
            FOREIGN KEY(modpack_version_id) REFERENCES modpack_versions (id),
            FOREIGN KEY(local_modpack_id) REFERENCES local_modpacks (id)
        )
        """
    )
    cursor.execute(
        """
        INSERT INTO translation_tasks_new (
            id,
            modpack_version_id,
            local_modpack_id,
            local_path,
            scan_result_json,
            status,
            config_json,
            total_items,
            completed_items,
            tokens_consumed,
            cost,
            created_at,
            finished_at
        )
        SELECT
            id,
            modpack_version_id,
            local_modpack_id,
            local_path,
            scan_result_json,
            status,
            config_json,
            total_items,
            completed_items,
            tokens_consumed,
            cost,
            created_at,
            finished_at
        FROM translation_tasks
        """
    )
    cursor.execute("DROP TABLE translation_tasks")
    cursor.execute("ALTER TABLE translation_tasks_new RENAME TO translation_tasks")


def _rebuild_translation_cache_table(cursor):
    """重建 translation_cache 表，使其支持多作用域缓存。"""
    cursor.execute("DROP TABLE IF EXISTS translation_cache_new")
    cursor.execute(
        """
        CREATE TABLE translation_cache_new (
            id INTEGER NOT NULL,
            source_hash VARCHAR(64) NOT NULL,
            original_text TEXT,
            translated_text TEXT,
            modpack_id INTEGER,
            modpack_version_id INTEGER,
            modpack_key VARCHAR(255),
            mc_version VARCHAR(64),
            ai_model VARCHAR(128),
            source_language VARCHAR(32),
            target_language VARCHAR(32),
            reliability_score INTEGER,
            use_count INTEGER,
            created_at DATETIME,
            last_used DATETIME,
            PRIMARY KEY (id),
            FOREIGN KEY(modpack_id) REFERENCES modpacks (id),
            FOREIGN KEY(modpack_version_id) REFERENCES modpack_versions (id)
        )
        """
    )
    cursor.execute(
        """
        INSERT INTO translation_cache_new (
            id,
            source_hash,
            original_text,
            translated_text,
            modpack_id,
            modpack_version_id,
            modpack_key,
            mc_version,
            ai_model,
            source_language,
            target_language,
            reliability_score,
            use_count,
            created_at,
            last_used
        )
        SELECT
            id,
            source_hash,
            original_text,
            translated_text,
            modpack_id,
            modpack_version_id,
            CASE
                WHEN modpack_id IS NOT NULL THEN 'remote:' || modpack_id
                WHEN modpack_version_id IS NOT NULL THEN 'version:' || modpack_version_id
                ELSE NULL
            END,
            mc_version,
            ai_model,
            'auto',
            'zh_cn',
            reliability_score,
            use_count,
            created_at,
            last_used
        FROM translation_cache
        """
    )
    cursor.execute("DROP TABLE translation_cache")
    cursor.execute("ALTER TABLE translation_cache_new RENAME TO translation_cache")


def _ensure_translation_cache_indexes(cursor):
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_translation_cache_source_hash ON translation_cache (source_hash)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_translation_cache_modpack_key ON translation_cache (modpack_key)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS ix_translation_cache_mc_version ON translation_cache (mc_version)"
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_translation_cache_lookup
        ON translation_cache (
            source_hash,
            target_language,
            modpack_version_id,
            modpack_key,
            mc_version
        )
        """
    )


def _ensure_legacy_sqlite_schema():
    """为历史 SQLite 数据库补齐缺失字段并修正旧约束。"""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return

    raw_conn = engine.raw_connection()
    try:
        cursor = raw_conn.cursor()

        if _table_exists(cursor, "translation_tasks"):
            existing_columns = _get_table_columns(cursor, "translation_tasks")
            required_columns = {
                "local_modpack_id": "INTEGER",
                "local_path": "TEXT",
                "scan_result_json": "TEXT",
            }
            rebuild_required = (
                int(existing_columns.get("modpack_version_id", (None, None, None, 0))[3] or 0) == 1
            )

            if rebuild_required:
                cursor.execute("PRAGMA foreign_keys = OFF")

            for column_name, column_sql in required_columns.items():
                if column_name in existing_columns:
                    continue
                cursor.execute(
                    f"ALTER TABLE translation_tasks ADD COLUMN {column_name} {column_sql}"
                )

            if rebuild_required:
                _rebuild_translation_tasks_table(cursor)
                cursor.execute("PRAGMA foreign_keys = ON")

        if _table_exists(cursor, "translate_items"):
            item_columns = _get_table_columns(cursor, "translate_items")
            if "apply_metadata_json" not in item_columns:
                cursor.execute(
                    "ALTER TABLE translate_items ADD COLUMN apply_metadata_json TEXT"
                )

        if _table_exists(cursor, "translation_cache"):
            cache_columns = _get_table_columns(cursor, "translation_cache")
            cache_rebuild_required = (
                "modpack_key" not in cache_columns
                or "source_language" not in cache_columns
                or "target_language" not in cache_columns
                or _has_unique_source_hash_index(cursor)
            )

            if cache_rebuild_required:
                cursor.execute("PRAGMA foreign_keys = OFF")
                _rebuild_translation_cache_table(cursor)
                cursor.execute("PRAGMA foreign_keys = ON")
            else:
                if "modpack_key" not in cache_columns:
                    cursor.execute(
                        "ALTER TABLE translation_cache ADD COLUMN modpack_key VARCHAR(255)"
                    )
                if "source_language" not in cache_columns:
                    cursor.execute(
                        "ALTER TABLE translation_cache ADD COLUMN source_language VARCHAR(32) DEFAULT 'auto'"
                    )
                if "target_language" not in cache_columns:
                    cursor.execute(
                        "ALTER TABLE translation_cache ADD COLUMN target_language VARCHAR(32) DEFAULT 'zh_cn'"
                    )

            _ensure_translation_cache_indexes(cursor)

        raw_conn.commit()
    except Exception:
        raw_conn.rollback()
        raise
    finally:
        raw_conn.close()


def init_db():
    """
    初始化数据库：创建所有表。
    应在应用启动时调用。
    """
    try:
        from .. import models  # noqa: F401
    except ImportError:
        import src.models  # type: ignore  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_legacy_sqlite_schema()