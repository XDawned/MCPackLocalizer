"""
翻译 API 路由

提供翻译配置、任务管理、状态查询、SSE 流式进度事件与 WebSocket 实时推送端点。
"""

import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from ..schemas.translate import (
    TranslateConfigRequest,
    TranslateStartRequest,
    TranslateTaskResponse,
    TranslateItemResponse,
)
from ..services.translate_service import TranslationService
from ..utils.ws_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/translate", tags=["translate"])
translation_service = TranslationService()


@router.post("/config")
async def save_translate_config(
    body: TranslateConfigRequest,
    db: Session = Depends(get_db),
):
    try:
        config_dict = body.model_dump()
        return {
            "code": 0,
            "data": config_dict,
            "message": "ok",
        }
    except Exception as e:
        logger.error("Failed to save translate config: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start")
async def start_translation(
    body: TranslateStartRequest,
    db: Session = Depends(get_db),
):
    try:
        task = await translation_service.create_task(
            db=db,
            modpack_version_id=body.modpack_version_id or "",
            local_path=body.local_path,
            config=body.config.model_dump(),
        )

        result = await translation_service.start_translation(db=db, task_id=task.id)
        return {
            "code": 0,
            "data": result,
            "message": "ok",
        }
    except Exception as e:
        logger.error("Failed to start translation: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start/stream")
async def start_translation_stream(
    body: TranslateStartRequest,
):
    """流式启动翻译：以 SSE（Server-Sent Events）持续推送结构化事件。

    响应 ``Content-Type`` 为 ``text/event-stream``，每条事件格式为：
        data: {"type":"progress","stage":"extracting","data":{...}}\n\n
    事件类型：
      - progress: 阶段性进度更新（started / extracting / translating / assembling / paused / cancelled）
      - log:      结构化实时日志
      - error:    错误事件，``data.fatal`` 区分致命 / 非致命
      - done:     任务结束，``stage`` 为 done / cancelled

    正常结束条件：
      - 收到 ``done`` 事件后关闭流；
      - 若发生致命错误，会先推送 ``error`` 事件，再关闭流。
    """
    db = SessionLocal()

    try:
        task = await translation_service.create_task(
            db=db,
            modpack_version_id=body.modpack_version_id or "",
            local_path=body.local_path,
            config=body.config.model_dump(),
        )
    except Exception as e:
        db.close()
        logger.error("Failed to create task for streaming: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    task_id = task.id
    event_queue: asyncio.Queue = asyncio.Queue()

    async def event_generator():
        """SSE 事件生成器：后台执行翻译，同时从队列中转发结构化事件。"""
        yield (
            f"event: message\n"
            f"data: {json.dumps({'type': 'progress', 'stage': 'started', 'data': {'task_id': task_id}}, ensure_ascii=False)}\n\n"
        )

        async def _run_translation():
            try:
                await translation_service.start_translation_streaming(
                    db=db,
                    task_id=task_id,
                    event_queue=event_queue,
                )
            except Exception:
                # 具体错误事件已由 service 层推送到队列
                pass
            finally:
                await event_queue.put(None)

        background_task = asyncio.create_task(_run_translation())

        try:
            while True:
                event = await event_queue.get()
                if event is None:
                    break
                yield f"event: message\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            logger.info("SSE stream cancelled for task_id=%d", task_id)
            raise
        finally:
            background_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await background_task
            db.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history")
async def list_translation_history(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    try:
        data = await translation_service.list_history(db=db, offset=offset, limit=limit)
        return {
            "code": 0,
            "data": data,
            "message": "ok",
        }
    except Exception as e:
        logger.error("Failed to list translation history: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{task_id}/restore-context")
async def get_translation_restore_context(
    task_id: int,
    db: Session = Depends(get_db),
):
    try:
        data = await translation_service.get_task_restore_context(db=db, task_id=task_id)
        return {
            "code": 0,
            "data": data,
            "message": "ok",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to get translation restore context: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/status")
async def get_task_status(
    task_id: int,
    db: Session = Depends(get_db),
):
    try:
        data = await translation_service.get_task_status(db=db, task_id=task_id)
        return {
            "code": 0,
            "data": data,
            "message": "ok",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to get task status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/pause")
async def pause_translation(
    task_id: int,
    db: Session = Depends(get_db),
):
    try:
        await translation_service.pause_task(db=db, task_id=task_id)
        status_data = await translation_service.get_task_status(db=db, task_id=task_id)
        return {
            "code": 0,
            "data": status_data,
            "message": "ok",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to pause translation: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/resume")
async def resume_translation(
    task_id: int,
    db: Session = Depends(get_db),
):
    try:
        await translation_service.resume_task(db=db, task_id=task_id)
        status_data = await translation_service.get_task_status(db=db, task_id=task_id)
        return {
            "code": 0,
            "data": status_data,
            "message": "ok",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to resume translation: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/cancel")
async def cancel_translation(
    task_id: int,
    db: Session = Depends(get_db),
):
    try:
        await translation_service.cancel_task(db=db, task_id=task_id)
        status_data = await translation_service.get_task_status(db=db, task_id=task_id)
        return {
            "code": 0,
            "data": status_data,
            "message": "ok",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to cancel translation: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/items")
async def get_task_items(
    task_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    try:
        items, total = await translation_service.get_task_items(
            db=db,
            task_id=task_id,
            offset=offset,
            limit=limit,
        )
        item_list = [
            TranslateItemResponse(
                id=item.id,
                source_file=item.source_file,
                source_path=item.source_path,
                original_text=item.original_text,
                translated_text=item.translated_text,
                source_hash=item.source_hash,
                from_cache=item.from_cache,
                status=item.status,
                area_type=item.get_apply_metadata().get("area_type") or None,
                target_strategy=item.get_apply_metadata().get("target_strategy") or None,
                target_path=item.get_apply_metadata().get("target_path") or item.get_apply_metadata().get("target_relative_path") or None,
                apply_metadata=item.get_apply_metadata(),
            ).model_dump()
            for item in items
        ]
        return {
            "code": 0,
            "data": {"items": item_list, "total": total, "offset": offset, "limit": limit},
            "message": "ok",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to get task items: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/ws/translate/{task_id}")
async def websocket_translate(websocket: WebSocket, task_id: str):
    await manager.connect(task_id, websocket)
    try:
        while True:
            try:
                message = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            if message == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket error for task %s: %s", task_id, e)
    finally:
        manager.disconnect(task_id, websocket)
