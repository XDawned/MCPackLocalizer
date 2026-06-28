"""
反馈 API 路由

提供翻译确认、问题报告、AI诊断和修复应用等端点。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.feedback_service import FeedbackService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])
feedback_service = FeedbackService()


class ReportIssueRequest(BaseModel):
    error_log: str = Field(..., description="错误日志内容")


@router.post("/{task_id}/confirm")
async def confirm_translation(
    task_id: int,
    db: Session = Depends(get_db),
):
    try:
        result = await feedback_service.confirm_translation(db=db, task_id=task_id)
        return {
            "code": 0,
            "data": result,
            "message": "ok",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to confirm translation: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/report")
async def report_issue(
    task_id: int,
    body: ReportIssueRequest,
    db: Session = Depends(get_db),
):
    try:
        result = await feedback_service.report_issue(db=db, task_id=task_id, error_log=body.error_log)
        return {
            "code": 0,
            "data": result,
            "message": "ok",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to report issue: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/diagnosis")
async def get_diagnosis(
    task_id: int,
    db: Session = Depends(get_db),
):
    try:
        result = await feedback_service.get_diagnosis(db=db, task_id=task_id)
        return {
            "code": 0,
            "data": result,
            "message": "ok",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to get diagnosis: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/apply-fix")
async def apply_fix(
    task_id: int,
    db: Session = Depends(get_db),
):
    try:
        result = await feedback_service.apply_fix(db=db, task_id=task_id)
        return {
            "code": 0,
            "data": result,
            "message": "ok",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to apply fix: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
