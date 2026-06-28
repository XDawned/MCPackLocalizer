"""
术语库 API 路由

提供术语条目 CRUD、CFPA 导入等端点。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.glossary import (
    GlossaryEntryCreate,
    GlossaryEntryUpdate,
    GlossaryEntryResponse,
    GlossaryImportRequest,
)
from ..services.glossary_service import GlossaryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/glossary", tags=["glossary"])
glossary_service = GlossaryService()


@router.get("/")
async def list_glossary_entries(
    search: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    try:
        entries, total = await glossary_service.list_entries(
            db=db,
            search=search,
            offset=offset,
            limit=limit,
        )
        entry_list = [
            GlossaryEntryResponse(
                id=entry.id,
                source_term=entry.source_term,
                target_term=entry.target_term,
                category=entry.category,
                source=entry.source,
                is_regex=entry.is_regex,
                created_at=entry.created_at.isoformat() if entry.created_at else None,
            ).model_dump()
            for entry in entries
        ]
        return {
            "code": 0,
            "data": {"items": entry_list, "total": total, "offset": offset, "limit": limit},
            "message": "ok",
        }
    except Exception as e:
        logger.error("Failed to list glossary entries: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def create_glossary_entry(
    body: GlossaryEntryCreate,
    db: Session = Depends(get_db),
):
    try:
        entry = await glossary_service.create_entry(db=db, data=body.model_dump())
        return {
            "code": 0,
            "data": GlossaryEntryResponse(
                id=entry.id,
                source_term=entry.source_term,
                target_term=entry.target_term,
                category=entry.category,
                source=entry.source,
                is_regex=entry.is_regex,
                created_at=entry.created_at.isoformat() if entry.created_at else None,
            ).model_dump(),
            "message": "ok",
        }
    except Exception as e:
        logger.error("Failed to create glossary entry: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{entry_id}")
async def update_glossary_entry(
    entry_id: int,
    body: GlossaryEntryUpdate,
    db: Session = Depends(get_db),
):
    try:
        entry = await glossary_service.update_entry(
            db=db,
            entry_id=entry_id,
            data=body.model_dump(exclude_none=True),
        )
        return {
            "code": 0,
            "data": GlossaryEntryResponse(
                id=entry.id,
                source_term=entry.source_term,
                target_term=entry.target_term,
                category=entry.category,
                source=entry.source,
                is_regex=entry.is_regex,
                created_at=entry.created_at.isoformat() if entry.created_at else None,
            ).model_dump(),
            "message": "ok",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to update glossary entry: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{entry_id}")
async def delete_glossary_entry(
    entry_id: int,
    db: Session = Depends(get_db),
):
    try:
        deleted = await glossary_service.delete_entry(db=db, entry_id=entry_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"GlossaryEntry id={entry_id} not found")
        return {
            "code": 0,
            "data": None,
            "message": "ok",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete glossary entry: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import")
async def import_glossary_from_cfpa(
    body: GlossaryImportRequest,
    db: Session = Depends(get_db),
):
    try:
        count = await glossary_service.import_from_cfpa(db=db, url=body.url)
        return {
            "code": 0,
            "data": {"imported_count": count},
            "message": "ok",
        }
    except Exception as e:
        logger.error("Failed to import glossary from CFPA: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
