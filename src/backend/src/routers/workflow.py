"""
工作流 API 路由

提供工作流状态查询、阶段推进和阶段完成的端点。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.workflow_service import WorkflowService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflow", tags=["workflow"])
workflow_service = WorkflowService()


class AdvanceRequest(BaseModel):
    next_stage: int | None = Field(None, description="目标阶段编号（1-8），不指定则自动推进")


@router.get("/{task_id}")
async def get_workflow_state(
    task_id: int,
    db: Session = Depends(get_db),
):
    """获取任务的完整工作流状态"""
    try:
        result = await workflow_service.get_workflow_state(db=db, task_id=task_id)
        return {"code": 0, "data": result, "message": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to get workflow state: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/advance")
async def advance_workflow(
    task_id: int,
    body: AdvanceRequest = AdvanceRequest(),
    db: Session = Depends(get_db),
):
    """推进工作流到下一阶段（支持自动推导或指定目标阶段）"""
    try:
        result = await workflow_service.advance_workflow(
            db=db, task_id=task_id, next_stage=body.next_stage,
        )
        return {"code": 0, "data": result, "message": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to advance workflow: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/complete/{stage}")
async def complete_stage(
    task_id: int,
    stage: int,
    success: bool = Query(True, description="阶段是否成功完成"),
    db: Session = Depends(get_db),
):
    """完成指定阶段并根据分支逻辑推进（主要用于阶段5和阶段7的分支决策）"""
    try:
        result = await workflow_service.complete_stage(
            db=db, task_id=task_id, stage=stage, success=success,
        )
        return {"code": 0, "data": result, "message": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to complete stage: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/actions")
async def get_available_actions(
    task_id: int,
    db: Session = Depends(get_db),
):
    """获取当前阶段可执行的操作列表"""
    try:
        result = await workflow_service.get_available_actions(db=db, task_id=task_id)
        return {"code": 0, "data": result, "message": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to get available actions: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
