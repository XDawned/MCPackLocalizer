"""
WebSocket 连接管理器

管理按 task_id 分组的 WebSocket 连接，支持广播翻译进度、日志、错误和完成消息。
"""

import logging
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

try:
    from ..schemas.translate import TranslateLogEvent
except ImportError:
    from src.schemas.translate import TranslateLogEvent  # type: ignore

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 连接管理器，按 task_id 维护连接列表，支持按任务广播消息。"""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, task_id: str, websocket: WebSocket) -> None:
        """接受 WebSocket 连接并加入指定任务的连接列表。"""
        await websocket.accept()
        if task_id not in self.active_connections:
            self.active_connections[task_id] = []
        self.active_connections[task_id].append(websocket)
        logger.info("WebSocket connected to task_id=%s (total=%d)", task_id, len(self.active_connections[task_id]))

    def disconnect(self, task_id: str, websocket: WebSocket) -> None:
        """从指定任务的连接列表中移除连接，若列表为空则清理该 task_id 条目。"""
        if task_id not in self.active_connections:
            return
        try:
            self.active_connections[task_id].remove(websocket)
        except ValueError:
            pass
        if not self.active_connections[task_id]:
            del self.active_connections[task_id]
        logger.info("WebSocket disconnected from task_id=%s", task_id)

    async def broadcast_to_task(self, task_id: str, data: dict[str, Any]) -> None:
        """向指定任务的所有 WebSocket 连接广播 JSON 消息，同时自动清理已断开的连接。"""
        if task_id not in self.active_connections:
            return
        dead_connections: list[WebSocket] = []
        for connection in self.active_connections[task_id]:
            try:
                await connection.send_json(data)
            except WebSocketDisconnect:
                dead_connections.append(connection)
            except Exception:
                dead_connections.append(connection)
        for conn in dead_connections:
            self.disconnect(task_id, conn)

    async def broadcast_event(
        self,
        task_id: str,
        event_type: str,
        stage: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "type": event_type,
            "stage": stage,
            "data": data or {},
        }
        await self.broadcast_to_task(task_id, payload)

    async def broadcast_progress(self, task_id: str, stage: str, **kwargs) -> None:
        """广播翻译进度更新消息。"""
        await self.broadcast_event(task_id, "progress", stage, kwargs)

    async def broadcast_log_event(self, task_id: str, stage: str, event: TranslateLogEvent) -> None:
        """广播结构化日志事件。"""
        await self.broadcast_event(task_id, "log", stage, event.model_dump(exclude_none=True))

    async def broadcast_log(self, task_id: str, stage: str, **kwargs) -> None:
        """广播翻译实时日志消息。"""
        if {"level", "timestamp", "message"}.issubset(kwargs.keys()):
            event = TranslateLogEvent(
                level=str(kwargs.get("level") or "INFO"),
                timestamp=str(kwargs.get("timestamp") or ""),
                message=str(kwargs.get("message") or ""),
                context=kwargs.get("context") if isinstance(kwargs.get("context"), dict) else None,
            )
            payload = dict(kwargs)
            payload.update(event.model_dump(exclude_none=True))
            await self.broadcast_event(task_id, "log", stage, payload)
            return
        await self.broadcast_event(task_id, "log", stage, kwargs)

    async def broadcast_error(self, task_id: str, stage: str = "failed", **kwargs) -> None:
        """广播翻译错误消息。"""
        await self.broadcast_event(task_id, "error", stage, kwargs)

    async def broadcast_done(self, task_id: str, stage: str = "done", **kwargs) -> None:
        """广播翻译结束消息。"""
        await self.broadcast_event(task_id, "done", stage, kwargs)

    async def broadcast_complete(self, task_id: str) -> None:
        """兼容旧调用：广播翻译完成消息。"""
        await self.broadcast_done(task_id, "done")


manager = ConnectionManager()
