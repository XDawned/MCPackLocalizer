"""
翻译服务

处理翻译任务的创建、执行、暂停、恢复和状态查询等核心业务流程。
支持基于真实解析器的内容提取、结构化输出解析、批次级自动重试与实时日志推送。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

try:
    from ..models.translation import TranslationTask, TranslateItem
    from ..models.settings import AIProvider as AIProviderModel, Setting
    from ..models.local_modpack import LocalModpack
    from ..models.modpack import Modpack, ModpackVersion
    from ..schemas.translate import TranslateLogEvent
    from ..adapters.ai_provider import (
        AIProvider,
        DEFAULT_MODELS,
        build_translation_messages,
        estimate_cost,
        get_ai_provider,
        normalize_api_base,
    )
    from ..services.cache_service import CacheService
    from ..services.structured_translation_parser import (
        StructuredTranslationParseError,
        StructuredTranslationParser,
    )
    from ..services.translation_metadata import build_apply_metadata
    from ..utils.ws_manager import manager
except ImportError:
    from src.models.translation import TranslationTask, TranslateItem  # type: ignore
    from src.models.settings import AIProvider as AIProviderModel, Setting  # type: ignore
    from src.models.local_modpack import LocalModpack  # type: ignore
    from src.models.modpack import Modpack, ModpackVersion  # type: ignore
    from src.schemas.translate import TranslateLogEvent  # type: ignore
    from src.adapters.ai_provider import (  # type: ignore
        AIProvider,
        DEFAULT_MODELS,
        build_translation_messages,
        estimate_cost,
        get_ai_provider,
        normalize_api_base,
    )
    from src.services.cache_service import CacheService  # type: ignore
    from src.services.structured_translation_parser import (  # type: ignore
        StructuredTranslationParseError,
        StructuredTranslationParser,
    )
    from src.services.translation_metadata import build_apply_metadata  # type: ignore
    from src.utils.ws_manager import manager  # type: ignore

logger = logging.getLogger(__name__)

TRANSLATE_BATCH_RETRY_LIMIT_KEY = "translate_batch_retry_limit"
DEFAULT_BATCH_RETRY_LIMIT = 3
MAX_BATCH_RETRY_LIMIT = 3
LOG_TEXT_LIMIT = 180
ERROR_PREVIEW_LIMIT = 1200
INITIAL_RETRY_DELAY_SECONDS = 1
MAX_RETRY_DELAY_SECONDS = 5


@dataclass(slots=True)
class TranslationRuntimeState:
    """翻译运行期上下文。"""

    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    processed_items: int = 0
    cache_hit_items: int = 0
    cache_write_items: int = 0
    error_items: list[dict[str, Any]] = field(default_factory=list)
    failed_batches: list[dict[str, Any]] = field(default_factory=list)
    cancelled: bool = False
    cancel_logged: bool = False


class TaskEventEmitter:
    """统一封装 WebSocket / SSE 事件推送。"""

    def __init__(self, task_id: str, event_queue: Optional[asyncio.Queue] = None):
        self.task_id = task_id
        self.event_queue = event_queue

    async def emit(self, event_type: str, stage: str, **data) -> None:
        event = {"type": event_type, "stage": stage, "data": data}
        safe_data = {k: v for k, v in data.items() if k != "task_id"}

        if event_type == "progress":
            await manager.broadcast_progress(self.task_id, stage, **safe_data)
        elif event_type == "log":
            await manager.broadcast_log(self.task_id, stage, **safe_data)
        elif event_type == "error":
            await manager.broadcast_error(self.task_id, stage, **safe_data)
        elif event_type == "done":
            await manager.broadcast_done(self.task_id, stage, **safe_data)

        if self.event_queue is not None:
            await self.event_queue.put(event)

    async def progress(self, stage: str, **data) -> None:
        await self.emit("progress", stage, **data)

    async def log_event(
        self,
        level: str,
        message: str,
        context: dict[str, Any] | None = None,
        *,
        stage: str = "log",
    ) -> None:
        event = TranslateLogEvent(
            level=_normalize_log_level(level),
            timestamp=_current_iso_timestamp(),
            message=message,
            context=context or None,
        )
        await self.emit("log", stage, **event.model_dump(exclude_none=True))

    async def log(
        self,
        level: str,
        stage: str,
        message: str,
        *,
        context: dict[str, Any] | None = None,
        **details,
    ) -> None:
        timestamp = _current_iso_timestamp()
        normalized_level = _normalize_log_level(level)
        formatted = _format_log_line(normalized_level, timestamp, context or {}, message, details)
        await self.emit(
            "log",
            stage,
            level=normalized_level,
            timestamp=timestamp,
            context=context or {},
            message=message,
            details=details,
            formatted=formatted,
        )

    async def error(
        self,
        stage: str,
        message: str,
        *,
        fatal: bool,
        context: dict[str, Any] | None = None,
        **details,
    ) -> None:
        timestamp = _current_iso_timestamp()
        payload = {
            "level": "ERROR",
            "timestamp": timestamp,
            "context": context or {},
            "message": message,
            "details": details,
            "fatal": fatal,
            "formatted": _format_log_line("ERROR", timestamp, context or {}, message, details),
        }
        await self.emit("error", stage, **payload)

    async def done(self, stage: str, **data) -> None:
        await self.emit("done", stage, **data)


class TranslationService:

    def __init__(self):
        self._postprocessor_pipeline = None
        self.cache_service = CacheService()

    # ------------------------------------------------------------------ #
    #  AI Provider 解析：从 config 中解析出最终生效的 AIProvider 实例
    # ------------------------------------------------------------------ #

    def _resolve_ai_provider(self, config: dict, db: Session) -> AIProvider:
        """从任务配置解析最终生效的 AI provider。"""
        provider_id = config.get("provider_id")
        provider_override = config.get("provider_override") or {}

        if provider_id not in (None, "", 0):
            try:
                provider_id_int = int(provider_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("翻译配置中的 provider_id 非法") from exc

            db_provider = (
                db.query(AIProviderModel)
                .filter(AIProviderModel.id == provider_id_int)
                .first()
            )
            if not db_provider:
                raise ValueError(f"AI provider {provider_id_int} 不存在")
            if not db_provider.is_enabled:
                raise ValueError(f"AI provider {provider_id_int} 已被禁用")

            provider_type = str(
                provider_override.get("provider_type") or db_provider.provider_type
            ).strip().lower()
            if provider_type not in DEFAULT_MODELS:
                raise ValueError(f"不支持的 AI provider 类型: {provider_type}")

            api_key = (
                provider_override.get("api_key")
                if provider_override.get("api_key") is not None
                else (db_provider.api_key_encrypted or "")
            )
            api_base = normalize_api_base(
                provider_override.get("api_base")
                if provider_override.get("api_base") is not None
                else db_provider.api_base,
                provider_type,
            )
            model = (
                provider_override.get("default_model")
                or db_provider.default_model
                or DEFAULT_MODELS.get(provider_type, "gpt-4o")
            )

            if not api_key:
                raise ValueError(
                    f"AI provider {provider_id_int}（{db_provider.name}）缺少 API Key，无法启动翻译"
                )

            return AIProvider(
                provider_type=provider_type,
                api_key=api_key,
                api_base=api_base,
                model=model,
            )

        provider_type = str(
            provider_override.get("provider_type") or config.get("ai_provider") or "openai"
        ).strip().lower()
        if provider_type not in DEFAULT_MODELS:
            raise ValueError(f"不支持的 AI provider 类型: {provider_type}")

        base_provider = get_ai_provider(provider_type)
        api_key = (
            provider_override.get("api_key")
            if provider_override.get("api_key") is not None
            else base_provider.api_key
        )
        api_base = normalize_api_base(
            provider_override.get("api_base")
            if provider_override.get("api_base") is not None
            else base_provider.api_base,
            provider_type,
        )
        model = (
            provider_override.get("default_model")
            or config.get("ai_model")
            or base_provider.model
            or DEFAULT_MODELS.get(provider_type, "gpt-4o")
        )

        if not api_key:
            raise ValueError(
                "翻译配置缺少 API Key。请优先选择已保存的 provider_id，或通过旧配置环境变量提供。"
            )

        return AIProvider(
            provider_type=provider_type,
            api_key=api_key,
            api_base=api_base,
            model=model,
        )

    def _resolve_batch_retry_limit(self, config: dict, db: Session) -> int:
        raw_value = config.get("batch_retry_limit")
        if raw_value is None:
            setting = (
                db.query(Setting)
                .filter(Setting.key == TRANSLATE_BATCH_RETRY_LIMIT_KEY)
                .first()
            )
            raw_value = (
                setting.value
                if setting and setting.value not in (None, "")
                else DEFAULT_BATCH_RETRY_LIMIT
            )

        try:
            retry_limit = int(str(raw_value).strip())
        except (TypeError, ValueError):
            retry_limit = DEFAULT_BATCH_RETRY_LIMIT

        return max(0, min(MAX_BATCH_RETRY_LIMIT, retry_limit))

    def _get_postprocessors(self):
        if self._postprocessor_pipeline is None:
            try:
                from ..postprocessors.json_validator import JsonValidator
                from ..postprocessors.placeholder_checker import PlaceholderChecker
                from ..postprocessors.formatting_checker import FormattingChecker
                from ..postprocessors.glossary_checker import GlossaryChecker
                from ..postprocessors.snbt_validator import SnbtValidator
            except ImportError:
                from src.postprocessors.json_validator import JsonValidator  # type: ignore
                from src.postprocessors.placeholder_checker import PlaceholderChecker  # type: ignore
                from src.postprocessors.formatting_checker import FormattingChecker  # type: ignore
                from src.postprocessors.glossary_checker import GlossaryChecker  # type: ignore
                from src.postprocessors.snbt_validator import SnbtValidator  # type: ignore
            self._postprocessor_pipeline = [
                JsonValidator(),
                PlaceholderChecker(),
                FormattingChecker(),
                GlossaryChecker(),
                SnbtValidator(),
            ]
        return self._postprocessor_pipeline

    async def create_task(
        self,
        db: Session,
        modpack_version_id: str,
        local_path: str,
        config: dict,
    ) -> TranslationTask:
        modpack_vid = int(modpack_version_id) if modpack_version_id and modpack_version_id.isdigit() else None
        normalized_local_path = os.path.abspath(local_path) if local_path else ""
        scan_result = self._load_scan_result_snapshot(config)
        local_modpack = None
        if normalized_local_path:
            local_modpack = (
                db.query(LocalModpack)
                .filter(LocalModpack.local_path == normalized_local_path)
                .order_by(LocalModpack.id.desc())
                .first()
            )

        config_payload = {**config, "local_path": normalized_local_path or local_path}
        if scan_result.get("name") and not config_payload.get("modpack_name"):
            config_payload["modpack_name"] = scan_result.get("name")
        elif local_modpack and local_modpack.name and not config_payload.get("modpack_name"):
            config_payload["modpack_name"] = local_modpack.name

        task = TranslationTask(
            modpack_version_id=modpack_vid if (modpack_vid and modpack_vid > 0) else None,
            local_modpack_id=local_modpack.id if local_modpack else None,
            local_path=normalized_local_path or None,
            scan_result_json=json.dumps(scan_result, ensure_ascii=False) if scan_result else None,
            status="configuring",
            config_json=json.dumps(config_payload, ensure_ascii=False),
            total_items=0,
            completed_items=0,
            tokens_consumed=0,
            cost=0.0,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        logger.info(
            "Created translation task id=%d for modpack_version_id=%s, local_path=%s",
            task.id,
            modpack_version_id,
            local_path,
        )
        return task

    async def start_translation(self, db: Session, task_id: int) -> dict:
        task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
        if not task:
            raise ValueError(f"TranslationTask id={task_id} not found")
        return await self._run_translation_task(db, task)

    async def start_translation_streaming(
        self,
        db: Session,
        task_id: int,
        event_queue: Optional[asyncio.Queue] = None,
    ) -> dict:
        """流式翻译：通过 event_queue 产出 progress / log / error / done 事件。"""
        task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
        if not task:
            raise ValueError(f"TranslationTask id={task_id} not found")
        return await self._run_translation_task(db, task, event_queue=event_queue)

    async def _run_translation_task(
        self,
        db: Session,
        task: TranslationTask,
        event_queue: Optional[asyncio.Queue] = None,
    ) -> dict:
        task_id_str = str(task.id)
        config = json.loads(task.config_json) if task.config_json else {}
        emitter = TaskEventEmitter(task_id_str, event_queue=event_queue)
        runtime = TranslationRuntimeState()

        try:
            ai_provider = self._resolve_ai_provider(config, db)
            batch_retry_limit = self._resolve_batch_retry_limit(config, db)
            batch_size = max(int(config.get("batch_size", 20) or 20), 1)
            cache_context = self._build_cache_context(task, config)

            task.status = "extracting"
            db.commit()
            await emitter.progress(
                "extracting",
                **self._build_progress_payload(
                    task,
                    runtime,
                    message="正在扫描并提取可翻译内容...",
                ),
            )

            extracted_items = self._extract_content(config, task, db)
            if not extracted_items:
                await emitter.log_event(
                    "WARN",
                    "未提取到可翻译内容，正式流程不会再注入示例条目",
                    {
                        "task_id": task_id_str,
                        "item_count": 0,
                    },
                    stage="extracting",
                )
                raise ValueError("未扫描到可翻译内容，请先执行扫描并确认存在可翻译区域")

            await emitter.log_event(
                "INFO",
                "内容提取完成",
                {
                    "task_id": task_id_str,
                    "item_count": len(extracted_items),
                },
                stage="extracting",
            )

            task.status = "translating"
            task.total_items = len(extracted_items)
            task.completed_items = 0
            db.commit()

            for extracted_item in extracted_items:
                src_file = extracted_item.get("source_file", "")
                src_path = extracted_item.get("source_path", "")
                original_text = extracted_item.get("original_text", "")
                source_hash = hashlib.sha256((original_text or "").encode("utf-8")).hexdigest()
                item = TranslateItem(
                    task_id=task.id,
                    source_file=src_file,
                    source_path=src_path,
                    original_text=original_text,
                    source_hash=source_hash,
                    from_cache=False,
                    status="pending",
                )
                item.set_apply_metadata(extracted_item.get("apply_metadata") or {})
                db.add(item)
            db.commit()

            cache_hit_count = await self._apply_cache_hits(
                db=db,
                task=task,
                runtime=runtime,
                cache_context=cache_context,
            )

            if cache_context["enabled"]:
                await emitter.log_event(
                    "INFO",
                    f"缓存预检查完成，命中 {cache_hit_count} 条，待调用 AI {max((task.total_items or 0) - cache_hit_count, 0)} 条",
                    {
                        "task_id": task_id_str,
                        "cache_scope": cache_context["scope"],
                        "cache_hits": cache_hit_count,
                        "remaining_items": max((task.total_items or 0) - cache_hit_count, 0),
                    },
                    stage="translating",
                )
            else:
                await emitter.log_event(
                    "INFO",
                    "已禁用翻译缓存，本次任务将全部调用 AI",
                    {"task_id": task_id_str},
                    stage="translating",
                )

            total_files = len(
                {
                    (item.get("source_path") or item.get("source_file") or "").strip()
                    for item in extracted_items
                    if (item.get("source_path") or item.get("source_file") or "").strip()
                }
            )
            await emitter.log_event(
                "INFO",
                f"翻译任务开始，共 {total_files} 个文件，{task.total_items or 0} 个条目",
                {
                    "task_id": task_id_str,
                    "file_count": total_files,
                    "item_count": task.total_items or 0,
                    "provider": ai_provider.provider_type,
                    "model_name": ai_provider.model,
                    "batch_size": batch_size,
                    "batch_retry_limit": batch_retry_limit,
                },
                stage="started",
            )
            await emitter.progress(
                "translating",
                **self._build_progress_payload(
                    task,
                    runtime,
                    message=f"已编排 {task.total_items} 条待翻译内容",
                ),
            )

            await self._translate_items(
                db=db,
                task=task,
                config=config,
                ai_provider=ai_provider,
                emitter=emitter,
                runtime=runtime,
                batch_retry_limit=batch_retry_limit,
                cache_context=cache_context,
            )

            db.refresh(task)
            if runtime.cancelled or task.status == "cancelled":
                task.status = "cancelled"
                db.commit()
                result = self._build_task_result(task, runtime)
                await self._emit_task_cancelled_log(emitter, task, runtime)
                await emitter.done("cancelled", **result)
                return result

            task.status = "assembling"
            db.commit()
            await emitter.progress(
                "assembling",
                **self._build_progress_payload(
                    task,
                    runtime,
                    message="正在组装翻译结果...",
                ),
            )
            await emitter.log_event(
                "INFO",
                "开始组装翻译结果",
                {
                    "task_id": task_id_str,
                    "completed_items": task.completed_items or 0,
                    "failed_batches": len(runtime.failed_batches),
                },
                stage="assembling",
            )

            task.status = "ready_to_apply"
            task.finished_at = datetime.now(timezone.utc)
            db.commit()

            result = self._build_task_result(task, runtime)
            success_items = max((task.total_items or 0) - len(runtime.error_items), 0)
            await emitter.log_event(
                "INFO",
                f"翻译任务完成，成功 {success_items} 条，失败 {len(runtime.error_items)} 条",
                {
                    "task_id": task_id_str,
                    "success_items": success_items,
                    "failed_items": len(runtime.error_items),
                    "tokens_consumed": result["tokens_consumed"],
                    "estimated_cost": result["cost"],
                },
                stage="done",
            )
            await emitter.done("done", **result)
            return result
        except Exception as exc:
            db.rollback()
            task.status = "failed"
            task.finished_at = datetime.now(timezone.utc)
            db.commit()
            error_message = _summarize_exception(exc, 500)
            logger.exception("Task id=%d failed: %s", task.id, error_message)
            await emitter.error(
                "failed",
                "翻译任务失败",
                fatal=True,
                context={"task": task_id_str},
                reason=error_message,
            )
            raise

    def _extract_content(self, config: dict, task: TranslationTask, db: Session) -> list[dict]:
        local_path = os.path.abspath(task.local_path or config.get("local_path", ""))
        scan_id = config.get("scan_id") or ""
        selected_areas = config.get("selected_areas") or None

        if not local_path or not os.path.isdir(local_path):
            return []

        if scan_id:
            try:
                from ..routers.pack_scan import pack_scanner as _scanner
            except ImportError:
                from src.routers.pack_scan import pack_scanner as _scanner  # type: ignore

            try:
                extracted = _scanner.extract_content(scan_id, selected_areas)
                if extracted:
                    logger.info(
                        "Task id=%d: using scan cache scan_id=%s, selected_areas=%s, %d items",
                        task.id,
                        scan_id,
                        selected_areas,
                        len(extracted),
                    )
                    return extracted
                logger.info(
                    "Task id=%d: scan cache scan_id=%s returned empty, no items to translate",
                    task.id,
                    scan_id,
                )
                return []
            except Exception as exc:
                logger.warning(
                    "Task id=%d: scan cache scan_id=%s unavailable, falling back to full scan: %s",
                    task.id,
                    scan_id,
                    exc,
                )

        try:
            from ..services.pack_scanner import PackScanError, PackScannerService
        except ImportError:
            from src.services.pack_scanner import PackScanError, PackScannerService  # type: ignore

        scanner = PackScannerService()
        try:
            scan_result = scanner.scan_directory(local_path, config.get("game_name"))
            extracted = scanner.extract_content(scan_result["scan_id"], selected_areas)
            logger.info(
                "Task id=%d: full scan extracted %d items from local_path=%s, selected_areas=%s",
                task.id,
                len(extracted),
                local_path,
                selected_areas,
            )
            return extracted
        except PackScanError as exc:
            logger.warning(
                "Task id=%d: full scan failed for local_path=%s: %s",
                task.id,
                local_path,
                exc,
            )
            return []

    def _load_scan_result_snapshot(self, config: dict) -> dict:
        scan_id = config.get("scan_id") or ""
        if not scan_id:
            return {}

        try:
            from ..routers.pack_scan import pack_scanner as _scanner
        except ImportError:
            from src.routers.pack_scan import pack_scanner as _scanner  # type: ignore

        cache = getattr(_scanner, "_scan_cache", {}).get(scan_id)
        if not isinstance(cache, dict):
            return {}
        result = cache.get("result")
        return result if isinstance(result, dict) else {}

    def _build_cache_context(self, task: TranslationTask, config: dict) -> dict[str, Any]:
        raw_scan_result = {}
        if task.scan_result_json:
            try:
                raw_scan_result = json.loads(task.scan_result_json)
            except Exception:
                raw_scan_result = {}

        local_path = os.path.abspath(task.local_path or config.get("local_path", "")) if (task.local_path or config.get("local_path")) else ""
        explicit_modpack_key = str(config.get("modpack_key") or "").strip()
        platform = str(config.get("modpack_platform") or "").strip().lower()
        external_id = str(config.get("modpack_external_id") or "").strip()

        if explicit_modpack_key:
            modpack_key = explicit_modpack_key[:255]
        elif task.local_modpack_id:
            modpack_key = f"local:{task.local_modpack_id}"
        elif platform and external_id:
            modpack_key = f"{platform}:{external_id}"[:255]
        elif local_path:
            modpack_key = f"path:{hashlib.sha1(local_path.lower().encode('utf-8')).hexdigest()}"
        else:
            modpack_key = None

        reference_ids: list[int] = []
        for raw_reference_id in config.get("cache_reference_ids") or []:
            try:
                parsed_reference_id = int(str(raw_reference_id).strip())
            except (TypeError, ValueError):
                continue
            if parsed_reference_id > 0 and parsed_reference_id not in reference_ids:
                reference_ids.append(parsed_reference_id)

        return {
            "enabled": bool(config.get("enable_cache", True)),
            "scope": str(config.get("cache_scope") or "version").strip().lower() or "version",
            "reference_version_ids": reference_ids,
            "source_language": str(config.get("source_language") or "auto").strip().lower() or "auto",
            "target_language": str(config.get("target_language") or "zh_cn").strip().lower() or "zh_cn",
            "modpack_version_id": task.modpack_version_id,
            "modpack_key": modpack_key,
            "mc_version": str(raw_scan_result.get("mc_version") or config.get("mc_version") or "").strip() or None,
        }

    async def _apply_cache_hits(
        self,
        db: Session,
        task: TranslationTask,
        runtime: TranslationRuntimeState,
        cache_context: dict[str, Any],
    ) -> int:
        if not cache_context.get("enabled"):
            return 0

        postprocessors = self._get_postprocessors()
        items = (
            db.query(TranslateItem)
            .filter(TranslateItem.task_id == task.id, TranslateItem.status == "pending")
            .order_by(TranslateItem.id)
            .all()
        )
        if not items:
            return 0

        hit_count = 0
        for item in items:
            cache_entry = await self.cache_service.lookup(
                db=db,
                source_hash=item.source_hash or "",
                scope=cache_context["scope"],
                target_language=cache_context["target_language"],
                modpack_version_id=cache_context["modpack_version_id"],
                reference_version_ids=cache_context["reference_version_ids"],
                modpack_key=cache_context["modpack_key"],
                mc_version=cache_context["mc_version"],
            )
            if not cache_entry or not cache_entry.translated_text:
                continue

            translated = self._apply_postprocessors(
                postprocessors,
                cache_entry.translated_text,
                item.original_text or "",
                item.get_apply_metadata(),
            )
            item.translated_text = translated
            item.from_cache = True
            item.status = "completed"
            hit_count += 1

        if hit_count > 0:
            runtime.processed_items += hit_count
            runtime.cache_hit_items += hit_count
            task.completed_items = runtime.processed_items
            db.commit()

        return hit_count

    async def _store_cache_entries(
        self,
        db: Session,
        items: Sequence[TranslateItem],
        ai_model: str,
        cache_context: dict[str, Any],
    ) -> int:
        if not cache_context.get("enabled"):
            return 0

        stored_count = 0
        for item in items:
            if item.status != "completed" or item.from_cache:
                continue
            if not item.source_hash or item.translated_text is None:
                continue

            await self.cache_service.store(
                db=db,
                source_hash=item.source_hash,
                original_text=item.original_text or "",
                translated_text=item.translated_text,
                ai_model=ai_model,
                modpack_version_id=cache_context["modpack_version_id"],
                modpack_key=cache_context["modpack_key"],
                mc_version=cache_context["mc_version"],
                source_language=cache_context["source_language"],
                target_language=cache_context["target_language"],
            )
            stored_count += 1

        return stored_count

    def _fallback_sample_items(self, local_root: str) -> list[dict]:
        return [
            {
                "area_type": "mod_lang",
                "source_file": "example_mod.jar",
                "source_path": os.path.join(local_root, "mods", "example_mod.jar"),
                "key": "examplemod.hello_world",
                "original_text": "Hello World",
                "apply_metadata": build_apply_metadata(
                    area_type="mod_lang",
                    source_file="example_mod.jar",
                    source_path=os.path.join(local_root, "mods", "example_mod.jar"),
                    key="examplemod.hello_world",
                    local_root=local_root,
                    original_text="Hello World",
                ),
            },
            {
                "area_type": "ftb_quests",
                "source_file": "chapter1.snbt",
                "source_path": os.path.join(local_root, "config", "ftbquests", "quests", "chapter1.snbt"),
                "key": "title.Complete the first quest",
                "original_text": "Complete the first quest",
                "apply_metadata": build_apply_metadata(
                    area_type="ftb_quests",
                    source_file="chapter1.snbt",
                    source_path=os.path.join(local_root, "config", "ftbquests", "quests", "chapter1.snbt"),
                    key="title.Complete the first quest",
                    local_root=local_root,
                    original_text="Complete the first quest",
                ),
            },
            {
                "area_type": "better_questing",
                "source_file": "DefaultQuests.json",
                "source_path": os.path.join(local_root, "config", "betterquesting", "DefaultQuests.json"),
                "key": "bq.quest.1.name",
                "original_text": "Quest Name",
                "apply_metadata": build_apply_metadata(
                    area_type="better_questing",
                    source_file="DefaultQuests.json",
                    source_path=os.path.join(local_root, "config", "betterquesting", "DefaultQuests.json"),
                    key="bq.quest.1.name",
                    local_root=local_root,
                    original_text="Quest Name",
                ),
            },
        ]

    async def _translate_items(
        self,
        db: Session,
        task: TranslationTask,
        config: dict,
        ai_provider: AIProvider,
        emitter: TaskEventEmitter,
        runtime: TranslationRuntimeState,
        batch_retry_limit: int,
        cache_context: dict[str, Any],
    ) -> None:
        task_id_str = str(task.id)
        items = (
            db.query(TranslateItem)
            .filter(TranslateItem.task_id == task.id, TranslateItem.status == "pending")
            .order_by(TranslateItem.id)
            .all()
        )
        batch_size = max(int(config.get("batch_size", 20) or 20), 1)
        postprocessors = self._get_postprocessors()
        total_batches = (len(items) + batch_size - 1) // batch_size if items else 0
        debug_enabled = _should_emit_debug_logs(config)

        if not items:
            await emitter.log_event(
                "INFO",
                "无需调用 AI，剩余条目均已由缓存处理完成",
                {
                    "task_id": task_id_str,
                    "completed_items": task.completed_items or 0,
                    "total_items": task.total_items or 0,
                },
                stage="translating",
            )
            return

        for batch_start in range(0, len(items), batch_size):
            db.refresh(task)
            if task.status == "paused":
                paused_payload = self._build_progress_payload(
                    task,
                    runtime,
                    message="翻译已暂停，等待恢复...",
                )
                await emitter.progress("paused", **paused_payload)
                await emitter.log_event(
                    "WARN",
                    "翻译任务已暂停",
                    {
                        "task_id": task_id_str,
                        "completed_items": task.completed_items or 0,
                    },
                    stage="paused",
                )
                while task.status == "paused":
                    await asyncio.sleep(1)
                    db.refresh(task)
                    if task.status == "cancelled":
                        break
                if task.status == "cancelled":
                    logger.info("Task id=%d: cancelled while paused", task.id)
                    await self._emit_task_cancelled_log(emitter, task, runtime)
                    return
                if task.status not in ("translating", "running"):
                    logger.warning(
                        "Task id=%d: unexpected status %s after pause, aborting",
                        task.id,
                        task.status,
                    )
                    return
                await emitter.log_event(
                    "INFO",
                    "翻译任务已恢复",
                    {
                        "task_id": task_id_str,
                        "completed_items": task.completed_items or 0,
                    },
                    stage="translating",
                )

            if task.status == "cancelled":
                logger.info("Task id=%d: cancelled at batch boundary", task.id)
                await self._emit_task_cancelled_log(emitter, task, runtime)
                return

            batch_index = batch_start // batch_size + 1
            batch_items = items[batch_start: batch_start + batch_size]
            source_texts = [
                {"key": str(index), "original": item.original_text or ""}
                for index, item in enumerate(batch_items)
            ]
            expected_keys = [entry["key"] for entry in source_texts]
            parser = StructuredTranslationParser(expected_keys)
            custom_prompt = self._build_structured_prompt(
                parser.get_format_instructions(),
                config.get("custom_prompt") or None,
            )
            current_messages = build_translation_messages(source_texts, custom_prompt=custom_prompt)
            current_file = batch_items[0].source_path or batch_items[0].source_file or ""
            batch_context = {
                "task_id": task_id_str,
                "batch_index": batch_index,
                "total_batches": total_batches,
                "item_count": len(batch_items),
                "current_file": current_file,
            }

            await emitter.log_event(
                "INFO",
                f"批次 {batch_index}/{total_batches} 开始翻译，条目数：{len(batch_items)}",
                batch_context,
                stage="translating",
            )

            partial_translations: dict[str, str] = {}
            last_error_message = ""

            for attempt_index in range(batch_retry_limit + 1):
                db.refresh(task)
                if task.status == "cancelled":
                    await self._emit_task_cancelled_log(emitter, task, runtime)
                    return

                attempt_context = {
                    **batch_context,
                    "max_retry": batch_retry_limit,
                }
                if attempt_index > 0:
                    attempt_context["retry_attempt"] = attempt_index

                try:
                    await emitter.log_event(
                        "INFO",
                        f"调用 AI 模型：{ai_provider.model}",
                        {
                            **attempt_context,
                            "provider": ai_provider.provider_type,
                            "model_name": ai_provider.model,
                        },
                        stage="translating",
                    )

                    structured_result = await self._try_structured_output_translation(
                        ai_provider=ai_provider,
                        parser=parser,
                        messages=current_messages,
                    )

                    if structured_result is None:
                        result = await ai_provider.translate(current_messages)
                        response_text = str(result.get("text", "") or "")
                        if result.get("error"):
                            raise RuntimeError(str(result["error"]))
                        tokens_used, model_used = self._accumulate_usage(task, ai_provider, result)
                        parsed = parser.parse(response_text)
                    else:
                        response_text = str(structured_result.get("text", "") or "")
                        tokens_used, model_used = self._accumulate_usage(task, ai_provider, structured_result)
                        parsed = structured_result["parsed"]

                    db.commit()
                    await emitter.log_event(
                        "INFO",
                        f"收到 AI 响应，长度：{len(response_text)} 字符",
                        {
                            **attempt_context,
                            "model_name": model_used,
                            "tokens_consumed": tokens_used,
                            "response_length": len(response_text),
                        },
                        stage="translating",
                    )

                    if parsed.missing_keys:
                        raise StructuredTranslationParseError(
                            f"结构化结果缺少 {len(parsed.missing_keys)} 个 key",
                            response_text,
                            partial_translations=parsed.translations_by_key,
                            missing_keys=parsed.missing_keys,
                            unexpected_keys=parsed.unexpected_keys,
                            duplicate_keys=parsed.duplicate_keys,
                            candidate_text=parsed.candidate_text,
                        )

                    await emitter.log_event(
                        "INFO",
                        f"批次 {batch_index} 解析成功，有效翻译 {len(parsed.translations_by_key)} 条",
                        {
                            **attempt_context,
                            "translated_count": len(parsed.translations_by_key),
                            "unexpected_keys": parsed.unexpected_keys,
                            "duplicate_keys": parsed.duplicate_keys,
                        },
                        stage="translating",
                    )

                    for index, item in enumerate(batch_items):
                        item_key = str(index)
                        translated = parsed.translations_by_key.get(item_key, item.original_text or "")
                        translated = self._apply_postprocessors(
                            postprocessors,
                            translated,
                            item.original_text or "",
                            item.get_apply_metadata(),
                        )
                        item.translated_text = translated
                        item.status = "completed"
                        item.from_cache = False

                        if debug_enabled:
                            await emitter.log_event(
                                "DEBUG",
                                f"原文：{_truncate_text(item.original_text or '', LOG_TEXT_LIMIT)}；译文：{_truncate_text(translated, LOG_TEXT_LIMIT)}",
                                {
                                    "task_id": task_id_str,
                                    "batch_index": batch_index,
                                    "item_index": batch_start + index + 1,
                                    "source_file": item.source_file or "-",
                                },
                                stage="translating",
                            )

                    stored_cache_count = await self._store_cache_entries(
                        db=db,
                        items=batch_items,
                        ai_model=model_used,
                        cache_context=cache_context,
                    )
                    runtime.cache_write_items += stored_cache_count
                    runtime.processed_items += len(batch_items)
                    task.completed_items = runtime.processed_items
                    db.commit()

                    await emitter.log_event(
                        "INFO",
                        f"批次 {batch_index}/{total_batches} 翻译完成",
                        {
                            **batch_context,
                            "completed_items": task.completed_items or 0,
                            "total_items": len(items),
                        },
                        stage="translating",
                    )
                    await emitter.progress(
                        "translating",
                        **self._build_progress_payload(
                            task,
                            runtime,
                            message=f"批次 {batch_index} 已完成",
                            current_file=current_file,
                        ),
                    )
                    break
                except StructuredTranslationParseError as exc:
                    partial_translations = dict(exc.partial_translations)
                    last_error_message = _summarize_exception(exc, 200)
                    raw_preview = _truncate_text(_normalize_whitespace(exc.raw_text or exc.raw_preview), 500)

                    if attempt_index < batch_retry_limit:
                        retry_number = attempt_index + 1
                        await emitter.log_event(
                            "WARN",
                            f"批次 {batch_index} 翻译异常：{_truncate_text(_normalize_whitespace(str(exc)), 100)}；正在重试 {retry_number}/{batch_retry_limit}",
                            {
                                **batch_context,
                                "retry_attempt": retry_number,
                                "max_retry": batch_retry_limit,
                                "error": str(exc),
                                "missing_keys": exc.missing_keys,
                                "unexpected_keys": exc.unexpected_keys,
                                "duplicate_keys": exc.duplicate_keys,
                            },
                            stage="translating",
                        )
                        current_messages = parser.build_repair_messages(
                            source_texts,
                            exc.raw_text,
                            str(exc),
                            custom_prompt=config.get("custom_prompt") or None,
                        )
                        if not await self._wait_retry_delay_or_cancel(
                            db=db,
                            task=task,
                            runtime=runtime,
                            emitter=emitter,
                            retry_attempt=retry_number,
                        ):
                            return
                        continue

                    await self._mark_batch_failed(
                        db=db,
                        task=task,
                        runtime=runtime,
                        batch_items=batch_items,
                        batch_index=batch_index,
                        batch_start=batch_start,
                        current_file=current_file,
                        reason=last_error_message,
                        emitter=emitter,
                        partial_translations=partial_translations,
                        retry_attempts=batch_retry_limit,
                        raw_preview=raw_preview,
                        missing_keys=exc.missing_keys,
                        unexpected_keys=exc.unexpected_keys,
                        duplicate_keys=exc.duplicate_keys,
                    )
                    break
                except Exception as exc:
                    last_error_message = _summarize_exception(exc, 200)
                    if attempt_index < batch_retry_limit:
                        retry_number = attempt_index + 1
                        await emitter.log_event(
                            "WARN",
                            f"批次 {batch_index} 调用异常：{type(exc).__name__}: {_truncate_text(_normalize_whitespace(str(exc)), 100)}；正在重试 {retry_number}/{batch_retry_limit}",
                            {
                                **batch_context,
                                "retry_attempt": retry_number,
                                "max_retry": batch_retry_limit,
                                "error_type": type(exc).__name__,
                                "error": str(exc),
                            },
                            stage="translating",
                        )
                        if not await self._wait_retry_delay_or_cancel(
                            db=db,
                            task=task,
                            runtime=runtime,
                            emitter=emitter,
                            retry_attempt=retry_number,
                        ):
                            return
                        continue

                    await self._mark_batch_failed(
                        db=db,
                        task=task,
                        runtime=runtime,
                        batch_items=batch_items,
                        batch_index=batch_index,
                        batch_start=batch_start,
                        current_file=current_file,
                        reason=last_error_message,
                        emitter=emitter,
                        partial_translations=partial_translations,
                        retry_attempts=batch_retry_limit,
                    )
                    break

        task.completed_items = runtime.processed_items
        db.commit()

    async def _mark_batch_failed(
        self,
        db: Session,
        task: TranslationTask,
        runtime: TranslationRuntimeState,
        batch_items: Sequence[TranslateItem],
        batch_index: int,
        batch_start: int,
        current_file: str,
        reason: str,
        emitter: TaskEventEmitter,
        partial_translations: dict[str, str],
        retry_attempts: int,
        raw_preview: str | None = None,
        missing_keys: Sequence[str] | None = None,
        unexpected_keys: Sequence[str] | None = None,
        duplicate_keys: Sequence[str] | None = None,
    ) -> None:
        postprocessors = self._get_postprocessors()
        normalized_reason = _truncate_text(_normalize_whitespace(reason), 200)
        normalized_raw_preview = _truncate_text(_normalize_whitespace(raw_preview or ""), 500)
        batch_record = {
            "batch_index": batch_index,
            "batch_range": f"{batch_start + 1}-{batch_start + len(batch_items)}",
            "current_file": current_file,
            "reason": normalized_reason,
            "retry_attempts": retry_attempts,
        }
        runtime.failed_batches.append(batch_record)

        for index, item in enumerate(batch_items):
            key = str(index)
            translated = partial_translations.get(key, item.original_text or "")
            translated = self._apply_postprocessors(
                postprocessors,
                translated,
                item.original_text or "",
                item.get_apply_metadata(),
            )
            item.translated_text = translated
            item.status = "failed"
            item.from_cache = False

            runtime.error_items.append(
                {
                    "batch_index": batch_index,
                    "source_file": item.source_file,
                    "source_path": item.source_path,
                    "original_text": _truncate_text(item.original_text or "", LOG_TEXT_LIMIT),
                    "translated_text": _truncate_text(translated, LOG_TEXT_LIMIT),
                    "message": normalized_reason,
                    "retry_attempts": retry_attempts,
                }
            )

        runtime.processed_items += len(batch_items)
        task.completed_items = runtime.processed_items
        db.commit()

        failure_message = f"批次 {batch_index} 翻译最终失败：{normalized_reason}"
        if normalized_raw_preview:
            failure_message += f"；原始内容：{normalized_raw_preview}"
        await emitter.log_event(
            "ERROR",
            failure_message,
            {
                "task_id": str(task.id),
                "batch_index": batch_index,
                "retry_attempt": retry_attempts,
                "max_retry": retry_attempts,
                "current_file": current_file,
                "error": normalized_reason,
                "raw_text": normalized_raw_preview or None,
                "missing_keys": list(missing_keys or []),
                "unexpected_keys": list(unexpected_keys or []),
                "duplicate_keys": list(duplicate_keys or []),
            },
            stage="translating",
        )
        await emitter.progress(
            "translating",
            **self._build_progress_payload(
                task,
                runtime,
                message=f"批次 {batch_index} 失败，已跳过并继续后续任务",
                current_file=current_file,
            ),
        )

    async def _emit_task_cancelled_log(
        self,
        emitter: TaskEventEmitter,
        task: TranslationTask,
        runtime: TranslationRuntimeState,
    ) -> None:
        runtime.cancelled = True
        if runtime.cancel_logged:
            return
        runtime.cancel_logged = True
        await emitter.log_event(
            "WARN",
            "翻译任务已被用户中止",
            {
                "task_id": str(task.id),
                "completed_items": task.completed_items or 0,
                "failed_items": len(runtime.error_items),
            },
            stage="cancelled",
        )

    async def _wait_retry_delay_or_cancel(
        self,
        db: Session,
        task: TranslationTask,
        runtime: TranslationRuntimeState,
        emitter: TaskEventEmitter,
        retry_attempt: int,
    ) -> bool:
        remaining = float(_retry_delay_seconds(retry_attempt))
        while remaining > 0:
            sleep_window = min(remaining, 0.2)
            await asyncio.sleep(sleep_window)
            remaining -= sleep_window
            db.refresh(task)
            if task.status == "cancelled":
                await self._emit_task_cancelled_log(emitter, task, runtime)
                return False
        return True

    async def _try_structured_output_translation(
        self,
        ai_provider: AIProvider,
        parser: StructuredTranslationParser,
        messages: Sequence[dict[str, str]],
    ) -> dict[str, Any] | None:
        llm = self._build_langchain_chat_model(ai_provider)
        if llm is None:
            return None

        try:
            chain = parser.get_structured_output_chain(llm)
        except (AttributeError, NotImplementedError, TypeError, ValueError) as exc:
            logger.debug(
                "Structured output chain unavailable for provider=%s model=%s, fallback to manual parsing: %s",
                ai_provider.provider_type,
                ai_provider.model,
                exc,
            )
            return None

        chain_result = await chain.ainvoke(self._to_langchain_messages(messages))
        return self._normalize_structured_output_response(parser, ai_provider, chain_result)

    def _build_langchain_chat_model(self, ai_provider: AIProvider) -> Any | None:
        try:
            if ai_provider.provider_type == "anthropic":
                from langchain_anthropic import ChatAnthropic

                anthropic_kwargs = {
                    "model": ai_provider.model,
                    "anthropic_api_key": ai_provider.api_key,
                    "temperature": 0.3,
                }
                if ai_provider.api_base:
                    anthropic_kwargs["base_url"] = ai_provider.api_base
                try:
                    return ChatAnthropic(**anthropic_kwargs)
                except TypeError:
                    anthropic_kwargs.pop("base_url", None)
                    return ChatAnthropic(**anthropic_kwargs)

            from langchain_openai import ChatOpenAI

            openai_kwargs = {
                "model": ai_provider.model,
                "api_key": ai_provider.api_key,
                "temperature": 0.3,
            }
            if ai_provider.api_base:
                openai_kwargs["base_url"] = ai_provider.api_base
            return ChatOpenAI(**openai_kwargs)
        except ImportError:
            logger.debug(
                "LangChain chat model adapter unavailable for provider=%s",
                ai_provider.provider_type,
            )
            return None
        except Exception as exc:
            logger.debug(
                "Failed to build LangChain chat model for provider=%s: %s",
                ai_provider.provider_type,
                exc,
            )
            return None

    def _to_langchain_messages(self, messages: Sequence[dict[str, str]]) -> list[Any]:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        converted: list[Any] = []
        for message in messages:
            role = str(message.get("role") or "user").strip().lower()
            content = str(message.get("content") or "")
            if role == "system":
                converted.append(SystemMessage(content=content))
            elif role == "assistant":
                converted.append(AIMessage(content=content))
            else:
                converted.append(HumanMessage(content=content))
        return converted

    def _normalize_structured_output_response(
        self,
        parser: StructuredTranslationParser,
        ai_provider: AIProvider,
        chain_result: Any,
    ) -> dict[str, Any]:
        payload = chain_result
        raw_message = None
        parsing_error = None
        if isinstance(chain_result, dict) and "parsed" in chain_result:
            parsing_error = chain_result.get("parsing_error")
            payload = chain_result.get("parsed")
            raw_message = chain_result.get("raw")

        raw_text = self._extract_langchain_message_text(raw_message)
        if parsing_error is not None:
            if raw_text:
                parsed = parser.parse(raw_text)
            else:
                raise parsing_error
        elif payload is None:
            if raw_text:
                parsed = parser.parse(raw_text)
            else:
                raise ValueError("结构化输出链未返回可用结果")
        else:
            try:
                parsed = parser.parse_payload(payload, raw_text=raw_text)
            except StructuredTranslationParseError:
                if raw_text:
                    parsed = parser.parse(raw_text)
                else:
                    raise

        response_text = raw_text or parsed.raw_text or parsed.candidate_text
        return {
            "parsed": parsed,
            "text": response_text,
            "tokens_used": self._extract_langchain_tokens(raw_message),
            "model": self._extract_langchain_model_name(raw_message, ai_provider.model),
        }

    def _extract_langchain_message_text(self, raw_message: Any) -> str:
        if raw_message is None:
            return ""

        content = getattr(raw_message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    text = block.get("text") or block.get("content") or ""
                    if text:
                        parts.append(str(text))
            return "".join(parts)
        return str(content or "")

    def _extract_langchain_tokens(self, raw_message: Any) -> int:
        if raw_message is None:
            return 0

        usage_metadata = getattr(raw_message, "usage_metadata", None)
        if isinstance(usage_metadata, dict):
            total_tokens = usage_metadata.get("total_tokens") or usage_metadata.get("total_token_count")
            if total_tokens is not None:
                return int(total_tokens)
            return int(usage_metadata.get("input_tokens") or usage_metadata.get("prompt_tokens") or 0) + int(
                usage_metadata.get("output_tokens") or usage_metadata.get("completion_tokens") or 0
            )

        response_metadata = getattr(raw_message, "response_metadata", None)
        if isinstance(response_metadata, dict):
            token_usage = response_metadata.get("token_usage") or response_metadata.get("usage") or {}
            if isinstance(token_usage, dict):
                total_tokens = token_usage.get("total_tokens")
                if total_tokens is not None:
                    return int(total_tokens)
                return int(token_usage.get("prompt_tokens") or token_usage.get("input_tokens") or 0) + int(
                    token_usage.get("completion_tokens") or token_usage.get("output_tokens") or 0
                )

        return 0

    def _extract_langchain_model_name(self, raw_message: Any, fallback: str) -> str:
        if raw_message is None:
            return fallback

        response_metadata = getattr(raw_message, "response_metadata", None)
        if isinstance(response_metadata, dict):
            return str(response_metadata.get("model_name") or response_metadata.get("model") or fallback)
        return fallback

    def _apply_postprocessors(
        self,
        postprocessors: Sequence[Any],
        translated: str,
        original_text: str,
        metadata: dict | None = None,
    ) -> str:
        result = translated
        metadata = metadata or {}
        for postproc in postprocessors:
            try:
                result = postproc.process(result, original_text, metadata)
            except Exception as exc:
                logger.debug("Postprocessor %s failed: %s", type(postproc).__name__, exc)
        return result

    def _accumulate_usage(
        self,
        task: TranslationTask,
        ai_provider: AIProvider,
        result: dict[str, Any],
    ) -> tuple[int, str]:
        tokens_used = int(result.get("tokens_used") or 0)
        model_used = str(result.get("model") or ai_provider.model)
        task.tokens_consumed = (task.tokens_consumed or 0) + tokens_used
        task.cost = round((task.cost or 0.0) + estimate_cost(model_used, tokens_used), 6)
        return tokens_used, model_used

    def _build_structured_prompt(
        self,
        format_instructions: str,
        custom_prompt: str | None,
    ) -> str:
        sections = [
            "Strict structured output requirement:",
            format_instructions,
            "Do not wrap the JSON with markdown fences, explanations, or any extra text.",
        ]
        if custom_prompt and custom_prompt.strip():
            sections.append(custom_prompt.strip())
        return "\n\n".join(sections)

    def _build_progress_payload(
        self,
        task: TranslationTask,
        runtime: TranslationRuntimeState,
        *,
        message: str,
        current_file: str = "",
    ) -> dict[str, Any]:
        elapsed_seconds = int((datetime.now(timezone.utc) - runtime.started_at).total_seconds())
        return {
            "message": message,
            "current": task.completed_items or 0,
            "total": task.total_items or 0,
            "completed_items": task.completed_items or 0,
            "total_items": task.total_items or 0,
            "current_file": current_file,
            "tokens_consumed": task.tokens_consumed or 0,
            "cost": task.cost or 0.0,
            "elapsed_seconds": elapsed_seconds,
            "failed_items": len(runtime.error_items),
            "failed_batches": len(runtime.failed_batches),
            "cache_hits": runtime.cache_hit_items,
            "cache_writes": runtime.cache_write_items,
            "errors": runtime.error_items[-50:],
        }

    def _build_task_result(
        self,
        task: TranslationTask,
        runtime: TranslationRuntimeState,
    ) -> dict[str, Any]:
        return {
            "task_id": str(task.id),
            "status": task.status,
            "total_items": task.total_items or 0,
            "completed_items": task.completed_items or 0,
            "tokens_consumed": task.tokens_consumed or 0,
            "cost": task.cost or 0.0,
            "failed_items_count": len(runtime.error_items),
            "failed_batches_count": len(runtime.failed_batches),
            "cache_hits_count": runtime.cache_hit_items,
            "cache_writes_count": runtime.cache_write_items,
            "errors": runtime.error_items[-50:],
            "failed_batches": runtime.failed_batches,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        }

    async def pause_task(self, db: Session, task_id: int) -> None:
        task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
        if not task:
            raise ValueError(f"TranslationTask id={task_id} not found")
        task.status = "paused"
        db.commit()
        logger.info("Task id=%d: paused", task.id)

    async def resume_task(self, db: Session, task_id: int) -> None:
        task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
        if not task:
            raise ValueError(f"TranslationTask id={task_id} not found")
        task.status = "translating"
        db.commit()
        logger.info("Task id=%d: resumed", task.id)

    async def cancel_task(self, db: Session, task_id: int) -> None:
        task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
        if not task:
            raise ValueError(f"TranslationTask id={task_id} not found")
        task.status = "cancelled"
        task.finished_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("Task id=%d: cancelled", task.id)

    async def get_task_status(self, db: Session, task_id: int) -> dict:
        task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
        if not task:
            raise ValueError(f"TranslationTask id={task_id} not found")
        cache_hits_count = (
            db.query(TranslateItem)
            .filter(TranslateItem.task_id == task.id, TranslateItem.from_cache.is_(True))
            .count()
        )
        return {
            "task_id": str(task.id),
            "status": task.status,
            "total_items": task.total_items,
            "completed_items": task.completed_items,
            "tokens_consumed": task.tokens_consumed,
            "cost": task.cost if task.cost is not None else 0.0,
            "cache_hits_count": cache_hits_count,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        }

    def _resolve_history_route(self, status: str | None) -> tuple[str, int | None]:
        normalized_status = str(status or "").strip().lower()
        if normalized_status in {"pending", "configuring"}:
            return "/l10n-config", 2
        if normalized_status in {"extracting", "translating", "assembling", "paused", "cancelled"}:
            return "/translating", 3
        if normalized_status == "ready_to_apply":
            return "/apply", 4
        if normalized_status in {"applied", "completed", "verified", "needs_fix", "fixing", "failed"}:
            return "/translation-review", 5
        return "/workflow", None

    def _resolve_task_modpack_summary(self, db: Session, task: TranslationTask, config: dict[str, Any]) -> dict[str, Any]:
        modpack_name = str(config.get("modpack_name") or "").strip()
        platform = str(config.get("modpack_platform") or "").strip().lower() or None
        external_id = str(config.get("modpack_external_id") or "").strip() or None
        version_number = None
        mc_version = str(config.get("mc_version") or "").strip() or None

        if task.modpack_version_id:
            version = db.query(ModpackVersion).filter(ModpackVersion.id == task.modpack_version_id).first()
            if version:
                version_number = version.version_number
                mc_version = mc_version or version.mc_version
                modpack = db.query(Modpack).filter(Modpack.id == version.modpack_id).first()
                if modpack:
                    modpack_name = modpack_name or modpack.name
                    platform = platform or modpack.platform
                    external_id = external_id or modpack.external_id
                    mc_version = mc_version or modpack.mc_version

        if task.local_modpack_id:
            local_modpack = db.query(LocalModpack).filter(LocalModpack.id == task.local_modpack_id).first()
            if local_modpack:
                modpack_name = modpack_name or local_modpack.name
                mc_version = mc_version or local_modpack.mc_version

        if not modpack_name and task.local_path:
            normalized_path = str(task.local_path).rstrip("\\/")
            modpack_name = os.path.basename(normalized_path) or normalized_path

        return {
            "name": modpack_name or f"任务 #{task.id}",
            "platform": platform,
            "external_id": external_id,
            "version_number": version_number,
            "mc_version": mc_version,
        }

    def _collect_task_tags(self, db: Session, task_id: int) -> list[str]:
        items = db.query(TranslateItem).filter(TranslateItem.task_id == task_id).all()
        tags: list[str] = []
        for item in items:
            area_type = str(item.get_apply_metadata().get("area_type") or "").strip()
            if area_type and area_type not in tags:
                tags.append(area_type)
        return tags

    async def list_history(
        self,
        db: Session,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        query = db.query(TranslationTask).order_by(TranslationTask.created_at.desc(), TranslationTask.id.desc())
        total = query.count()
        tasks = query.offset(offset).limit(limit).all()

        records: list[dict[str, Any]] = []
        for task in tasks:
            config = json.loads(task.config_json) if task.config_json else {}
            recommended_route, current_step = self._resolve_history_route(task.status)
            modpack_summary = self._resolve_task_modpack_summary(db, task, config)
            records.append(
                {
                    "task_id": str(task.id),
                    "modpack_name": modpack_summary["name"],
                    "processed_at": (task.finished_at or task.created_at).isoformat() if (task.finished_at or task.created_at) else None,
                    "status": task.status,
                    "is_completed": task.status in {"applied", "completed", "verified"},
                    "tags": self._collect_task_tags(db, task.id),
                    "recommended_route": recommended_route,
                    "current_step": current_step,
                    "completed_items": task.completed_items or 0,
                    "total_items": task.total_items or 0,
                }
            )

        return {
            "items": records,
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    async def get_task_restore_context(self, db: Session, task_id: int) -> dict[str, Any]:
        task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
        if not task:
            raise ValueError(f"TranslationTask id={task_id} not found")

        config = json.loads(task.config_json) if task.config_json else {}
        scan_result = json.loads(task.scan_result_json) if task.scan_result_json else {}
        recommended_route, current_step = self._resolve_history_route(task.status)
        modpack_summary = self._resolve_task_modpack_summary(db, task, config)
        route_query = {
            "taskId": str(task.id),
            "localPath": task.local_path or config.get("local_path") or None,
            "modpackVersionId": str(task.modpack_version_id) if task.modpack_version_id else None,
        }

        return {
            "task": {
                "task_id": str(task.id),
                "status": task.status,
                "completed_items": task.completed_items or 0,
                "total_items": task.total_items or 0,
                "tokens_consumed": task.tokens_consumed or 0,
                "cost": task.cost or 0.0,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "finished_at": task.finished_at.isoformat() if task.finished_at else None,
            },
            "modpack": modpack_summary,
            "recommended_route": recommended_route,
            "current_step": current_step,
            "route_query": {key: value for key, value in route_query.items() if value not in (None, "")},
            "config": config,
            "scan_result": scan_result,
            "selected_areas": config.get("selected_areas") or [],
            "tags": self._collect_task_tags(db, task.id),
        }

    async def get_task_items(
        self,
        db: Session,
        task_id: int,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[TranslateItem], int]:
        query = db.query(TranslateItem).filter(TranslateItem.task_id == task_id)
        total = query.count()
        items = query.order_by(TranslateItem.id).offset(offset).limit(limit).all()
        return items, total


def _format_log_line(
    level: str,
    timestamp: str,
    context: dict[str, Any],
    message: str,
    details: dict[str, Any],
) -> str:
    context_text = _format_context(context)
    detail_parts = []

    label_map = {
        "provider": "提供商",
        "model": "模型",
        "batch_size": "批大小",
        "batch_retry_limit": "自动重试",
        "batch_range": "范围",
        "item_count": "条目数",
        "current_file": "文件",
        "attempt": "尝试",
        "retry": "重试",
        "reason": "原因",
        "original_text": "原文",
        "translated_text": "译文",
        "raw_preview": "原始内容",
        "missing_keys": "缺失键",
        "unexpected_keys": "额外键",
        "duplicate_keys": "重复键",
        "completed_items": "已完成",
        "total_items": "总条目",
        "failed_items": "失败条目",
        "failed_batches": "失败批次",
        "tokens_consumed": "Token",
        "estimated_cost": "费用",
    }

    for key, value in details.items():
        if value in (None, "", [], {}):
            continue
        label = label_map.get(key, key)
        rendered = value
        if isinstance(value, list):
            rendered = ", ".join(str(item) for item in value[:10])
            if len(value) > 10:
                rendered += " ..."
        rendered_text = _truncate_text(str(rendered), ERROR_PREVIEW_LIMIT)
        detail_parts.append(f"{label}：{rendered_text}")

    suffix = "；".join([message, *detail_parts]) if detail_parts else message
    return f"【{level.upper()}】【{timestamp}】【{context_text}】{suffix}"


def _format_context(context: dict[str, Any]) -> str:
    if not context:
        return "task:-"
    parts = []
    for key, value in context.items():
        if value in (None, ""):
            continue
        parts.append(f"{key}:{value}")
    return " ".join(parts) if parts else "task:-"


def _truncate_text(text: str, limit: int) -> str:
    value = str(text or "")
    if len(value) <= limit:
        return value
    return value[:limit] + "...(truncated)"


def _normalize_whitespace(text: str) -> str:
    return " ".join(str(text or "").split())


def _current_iso_timestamp() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _normalize_log_level(level: str) -> str:
    normalized = str(level or "INFO").strip().upper()
    if normalized == "WARNING":
        return "WARN"
    if normalized not in {"DEBUG", "INFO", "WARN", "ERROR"}:
        return "INFO"
    return normalized


def _retry_delay_seconds(retry_attempt: int) -> int:
    safe_attempt = max(1, int(retry_attempt))
    return min(INITIAL_RETRY_DELAY_SECONDS * (2 ** (safe_attempt - 1)), MAX_RETRY_DELAY_SECONDS)


def _should_emit_debug_logs(config: dict[str, Any]) -> bool:
    if str(config.get("log_level") or "").strip().upper() == "DEBUG":
        return True
    for key in ("debug", "debug_mode"):
        value = config.get(key)
        if isinstance(value, bool) and value:
            return True
        if isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "on", "debug"}:
            return True
    return False


def _summarize_exception(exc: Exception, limit: int) -> str:
    message = str(exc) or type(exc).__name__
    return _truncate_text(_normalize_whitespace(f"{type(exc).__name__}: {message}" if type(exc).__name__ not in message else message), limit)
