"""
术语库服务

管理翻译术语条目，支持 CRUD、CFPA 导入和翻译提示注入。
"""

import logging

from sqlalchemy.orm import Session

try:
    from ..models.glossary import GlossaryEntry
except ImportError:
    from src.models.glossary import GlossaryEntry  # type: ignore

logger = logging.getLogger(__name__)


class GlossaryService:

    async def list_entries(
        self,
        db: Session,
        search: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[GlossaryEntry], int]:
        query = db.query(GlossaryEntry)
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                GlossaryEntry.source_term.ilike(pattern)
                | GlossaryEntry.target_term.ilike(pattern)
                | GlossaryEntry.category.ilike(pattern)
            )
        total = query.count()
        entries = query.order_by(GlossaryEntry.id).offset(offset).limit(limit).all()
        return entries, total

    async def create_entry(self, db: Session, data: dict) -> GlossaryEntry:
        entry = GlossaryEntry(
            source_term=data.get("source_term", ""),
            target_term=data.get("target_term", ""),
            category=data.get("category"),
            source=data.get("source", "manual"),
            is_regex=data.get("is_regex", False),
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        logger.info("Created glossary entry id=%d: %s → %s", entry.id, entry.source_term, entry.target_term)
        return entry

    async def update_entry(self, db: Session, entry_id: int, data: dict) -> GlossaryEntry:
        entry = db.query(GlossaryEntry).filter(GlossaryEntry.id == entry_id).first()
        if not entry:
            raise ValueError(f"GlossaryEntry id={entry_id} not found")

        for field in ("source_term", "target_term", "category", "is_regex"):
            if field in data and data[field] is not None:
                setattr(entry, field, data[field])

        db.commit()
        db.refresh(entry)
        logger.info("Updated glossary entry id=%d", entry_id)
        return entry

    async def delete_entry(self, db: Session, entry_id: int) -> bool:
        entry = db.query(GlossaryEntry).filter(GlossaryEntry.id == entry_id).first()
        if not entry:
            return False
        db.delete(entry)
        db.commit()
        logger.info("Deleted glossary entry id=%d", entry_id)
        return True

    async def import_from_cfpa(self, db: Session, url: str | None = None) -> int:
        logger.info(
            "CFPA import requested (stub) url=%s — placeholder implementation",
            url or "default",
        )
        return 0

    async def get_terms_for_translation(self, db: Session) -> list[dict]:
        entries = db.query(GlossaryEntry).all()
        return [
            {"source_term": entry.source_term, "target_term": entry.target_term}
            for entry in entries
        ]
