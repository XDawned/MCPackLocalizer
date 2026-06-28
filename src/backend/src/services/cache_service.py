"""
翻译缓存服务

实现多作用域缓存查找策略和缓存条目管理，降低重复翻译的 API 调用成本。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

try:
    from ..models.cache import TranslationCache
except ImportError:
    from src.models.cache import TranslationCache  # type: ignore

logger = logging.getLogger(__name__)


class CacheService:
    """翻译缓存服务。"""

    @staticmethod
    def _normalize_language(value: Optional[str], fallback: str) -> str:
        normalized = str(value or fallback).strip().lower()
        return normalized or fallback

    @staticmethod
    def _normalize_scope(scope: Optional[str]) -> str:
        normalized = str(scope or "version").strip().lower()
        if normalized not in {"version", "modpack", "all"}:
            return "version"
        return normalized

    @staticmethod
    def _normalize_reference_ids(reference_ids: Optional[Iterable[int | str]]) -> list[int]:
        result: list[int] = []
        for raw in reference_ids or []:
            try:
                value = int(str(raw).strip())
            except (TypeError, ValueError):
                continue
            if value > 0 and value not in result:
                result.append(value)
        return result

    async def lookup(
        self,
        db: Session,
        *,
        source_hash: str,
        scope: str = "version",
        target_language: str = "zh_cn",
        modpack_version_id: int | None = None,
        reference_version_ids: Optional[Iterable[int | str]] = None,
        modpack_key: str | None = None,
        mc_version: str | None = None,
    ) -> TranslationCache | None:
        if not source_hash:
            return None

        normalized_scope = self._normalize_scope(scope)
        normalized_target_language = self._normalize_language(target_language, "zh_cn")
        normalized_reference_ids = self._normalize_reference_ids(reference_version_ids)
        current_time = datetime.now(timezone.utc)

        version_candidates: list[int] = []
        if modpack_version_id is not None and modpack_version_id > 0:
            version_candidates.append(modpack_version_id)
        for version_id in normalized_reference_ids:
            if version_id not in version_candidates:
                version_candidates.append(version_id)

        for version_id in version_candidates:
            entry = (
                db.query(TranslationCache)
                .filter(
                    TranslationCache.source_hash == source_hash,
                    TranslationCache.target_language == normalized_target_language,
                    TranslationCache.modpack_version_id == version_id,
                )
                .order_by(
                    TranslationCache.reliability_score.desc(),
                    TranslationCache.use_count.desc(),
                    TranslationCache.id.desc(),
                )
                .first()
            )
            if entry:
                entry.use_count = int(entry.use_count or 0) + 1
                entry.last_used = current_time
                db.flush()
                logger.debug(
                    "Cache HIT (scope=version) hash=%s version=%s target_language=%s",
                    source_hash,
                    version_id,
                    normalized_target_language,
                )
                return entry

        if normalized_scope in {"modpack", "all"} and modpack_key:
            entry = (
                db.query(TranslationCache)
                .filter(
                    TranslationCache.source_hash == source_hash,
                    TranslationCache.target_language == normalized_target_language,
                    TranslationCache.modpack_key == modpack_key,
                )
                .order_by(
                    TranslationCache.reliability_score.desc(),
                    TranslationCache.use_count.desc(),
                    TranslationCache.id.desc(),
                )
                .first()
            )
            if entry:
                entry.use_count = int(entry.use_count or 0) + 1
                entry.last_used = current_time
                db.flush()
                logger.debug(
                    "Cache HIT (scope=modpack) hash=%s modpack_key=%s target_language=%s",
                    source_hash,
                    modpack_key,
                    normalized_target_language,
                )
                return entry

        if normalized_scope == "all":
            if mc_version:
                entry = (
                    db.query(TranslationCache)
                    .filter(
                        TranslationCache.source_hash == source_hash,
                        TranslationCache.target_language == normalized_target_language,
                        TranslationCache.mc_version == mc_version,
                    )
                    .order_by(
                        TranslationCache.reliability_score.desc(),
                        TranslationCache.use_count.desc(),
                        TranslationCache.id.desc(),
                    )
                    .first()
                )
                if entry:
                    entry.use_count = int(entry.use_count or 0) + 1
                    entry.last_used = current_time
                    db.flush()
                    logger.debug(
                        "Cache HIT (scope=all, mc_version) hash=%s mc_version=%s target_language=%s",
                        source_hash,
                        mc_version,
                        normalized_target_language,
                    )
                    return entry

            entry = (
                db.query(TranslationCache)
                .filter(
                    TranslationCache.source_hash == source_hash,
                    TranslationCache.target_language == normalized_target_language,
                )
                .order_by(
                    TranslationCache.reliability_score.desc(),
                    TranslationCache.use_count.desc(),
                    TranslationCache.id.desc(),
                )
                .first()
            )
            if entry:
                entry.use_count = int(entry.use_count or 0) + 1
                entry.last_used = current_time
                db.flush()
                logger.debug(
                    "Cache HIT (scope=all, fallback) hash=%s target_language=%s",
                    source_hash,
                    normalized_target_language,
                )
                return entry

        logger.debug(
            "Cache MISS hash=%s scope=%s target_language=%s",
            source_hash,
            normalized_scope,
            normalized_target_language,
        )
        return None

    async def store(
        self,
        db: Session,
        *,
        source_hash: str,
        original_text: str,
        translated_text: str,
        ai_model: str,
        modpack_version_id: int | None = None,
        modpack_key: str | None = None,
        mc_version: str | None = None,
        source_language: str = "auto",
        target_language: str = "zh_cn",
    ) -> TranslationCache:
        normalized_source_language = self._normalize_language(source_language, "auto")
        normalized_target_language = self._normalize_language(target_language, "zh_cn")

        query = db.query(TranslationCache).filter(
            TranslationCache.source_hash == source_hash,
            TranslationCache.target_language == normalized_target_language,
        )
        if modpack_version_id is None:
            query = query.filter(TranslationCache.modpack_version_id.is_(None))
        else:
            query = query.filter(TranslationCache.modpack_version_id == modpack_version_id)

        if modpack_key:
            query = query.filter(TranslationCache.modpack_key == modpack_key)
        else:
            query = query.filter(TranslationCache.modpack_key.is_(None))

        if mc_version:
            query = query.filter(TranslationCache.mc_version == mc_version)
        else:
            query = query.filter(TranslationCache.mc_version.is_(None))

        existing = query.first()
        current_time = datetime.now(timezone.utc)

        if existing:
            existing.original_text = original_text
            existing.translated_text = translated_text
            existing.ai_model = ai_model or existing.ai_model
            existing.source_language = normalized_source_language
            existing.target_language = normalized_target_language
            existing.last_used = current_time
            db.flush()
            logger.debug(
                "Updated cache entry id=%d hash=%s target_language=%s",
                existing.id,
                source_hash,
                normalized_target_language,
            )
            return existing

        entry = TranslationCache(
            source_hash=source_hash,
            original_text=original_text,
            translated_text=translated_text,
            modpack_id=None,
            modpack_version_id=modpack_version_id,
            modpack_key=modpack_key,
            mc_version=mc_version,
            ai_model=ai_model,
            source_language=normalized_source_language,
            target_language=normalized_target_language,
            reliability_score=0,
            use_count=0,
            last_used=current_time,
        )
        db.add(entry)
        db.flush()
        logger.debug(
            "Created cache entry hash=%s target_language=%s scope=(version=%s, modpack_key=%s, mc_version=%s)",
            source_hash,
            normalized_target_language,
            modpack_version_id,
            modpack_key,
            mc_version,
        )
        return entry

    async def mark_reliable(self, db: Session, cache_id: int) -> None:
        entry = (
            db.query(TranslationCache)
            .filter(TranslationCache.id == cache_id)
            .first()
        )
        if entry:
            entry.reliability_score = 5
            db.commit()
            logger.debug("Marked cache entry id=%d as reliable (score=5)", cache_id)

    async def get_cache_stats(self, db: Session) -> dict:
        total_entries = db.query(func.count(TranslationCache.id)).scalar() or 0
        total_hits = db.query(func.sum(TranslationCache.use_count)).scalar() or 0
        latest_used = db.query(func.max(TranslationCache.last_used)).scalar()
        latest_created = db.query(func.max(TranslationCache.created_at)).scalar()

        target_language_rows = (
            db.query(
                TranslationCache.target_language,
                func.count(TranslationCache.id),
            )
            .group_by(TranslationCache.target_language)
            .all()
        )
        by_target_language = {
            str(language or "unknown"): int(count or 0)
            for language, count in target_language_rows
        }

        by_scope = {"version": 0, "modpack": 0, "all": 0}
        scope_rows = (
            db.query(
                TranslationCache.modpack_version_id,
                TranslationCache.modpack_key,
                TranslationCache.mc_version,
            )
            .all()
        )
        for modpack_version_id, modpack_key, mc_version in scope_rows:
            if modpack_version_id is not None:
                by_scope["version"] += 1
            elif modpack_key:
                by_scope["modpack"] += 1
            elif mc_version:
                by_scope["all"] += 1
            else:
                by_scope["all"] += 1

        return {
            "entries": int(total_entries),
            "hits": int(total_hits),
            "by_target_language": by_target_language,
            "by_scope": by_scope,
            "last_used_at": latest_used.isoformat() if latest_used else None,
            "last_created_at": latest_created.isoformat() if latest_created else None,
        }

    async def clear_cache(self, db: Session) -> dict:
        cleared_entries = db.query(TranslationCache).count()
        db.query(TranslationCache).delete(synchronize_session=False)
        db.commit()
        logger.info("Cleared translation cache, deleted_count=%d", cleared_entries)
        return {"cleared_entries": int(cleared_entries)}
