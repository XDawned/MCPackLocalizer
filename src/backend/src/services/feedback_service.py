"""
翻译反馈服务

处理翻译确认、问题报告、诊断和修复流程。
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

try:
    from ..models.cache import TranslationCache
    from ..models.translation import TranslationTask, TranslateItem
except ImportError:
    from src.models.cache import TranslationCache  # type: ignore
    from src.models.translation import TranslationTask, TranslateItem  # type: ignore

logger = logging.getLogger(__name__)


class FeedbackService:

    async def confirm_translation(self, db: Session, task_id: int) -> dict:
        task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
        if not task:
            raise ValueError(f"TranslationTask id={task_id} not found")

        task.status = "verified"
        db.commit()

        items = db.query(TranslateItem).filter(TranslateItem.task_id == task.id).all()
        confirmed_count = 0
        for item in items:
            if item.source_hash:
                cache_entries = (
                    db.query(TranslationCache)
                    .filter(TranslationCache.source_hash == item.source_hash)
                    .all()
                )
                for cache_entry in cache_entries:
                    cache_entry.reliability_score = 5
                    confirmed_count += 1

        db.commit()
        logger.info(
            "Task id=%d confirmed as verified, %d cache entries marked reliable",
            task_id,
            confirmed_count,
        )
        return {"confirmed": confirmed_count}

    async def report_issue(self, db: Session, task_id: int, error_log: str) -> dict:
        task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
        if not task:
            raise ValueError(f"TranslationTask id={task_id} not found")

        config = json.loads(task.config_json) if task.config_json else {}
        config["_error_log"] = error_log
        config["_reported_at"] = datetime.now(timezone.utc).isoformat()
        task.config_json = json.dumps(config, ensure_ascii=False)
        task.status = "needs_fix"
        db.commit()

        logger.info("Task id=%d reported with issue, status set to needs_fix", task_id)
        return {"task_id": task_id, "status": "needs_fix"}

    async def get_diagnosis(self, db: Session, task_id: int) -> dict:
        task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
        if not task:
            raise ValueError(f"TranslationTask id={task_id} not found")

        items = db.query(TranslateItem).filter(TranslateItem.task_id == task.id).all()
        total = len(items)
        completed = sum(1 for i in items if i.status == "completed")
        pending = sum(1 for i in items if i.status == "pending")
        failed = sum(1 for i in items if i.status == "failed")
        from_cache = sum(1 for i in items if i.from_cache)

        diagnosis = {
            "task_id": task_id,
            "status": task.status,
            "total_items": task.total_items,
            "completed_items": task.completed_items,
            "items_breakdown": {
                "total": total,
                "completed": completed,
                "pending": pending,
                "failed": failed,
                "from_cache": from_cache,
            },
            "tokens_consumed": task.tokens_consumed,
            "cost": task.cost if task.cost is not None else 0.0,
            "analysis": (
                "Translation appears healthy."
                if failed == 0 and task.status != "needs_fix"
                else f"Found {failed} failed items. Task status: {task.status}."
                if failed > 0
                else f"Task is in '{task.status}' state and may need review."
            ),
        }
        return diagnosis

    async def apply_fix(self, db: Session, task_id: int) -> dict:
        task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
        if not task:
            raise ValueError(f"TranslationTask id={task_id} not found")

        items = db.query(TranslateItem).filter(TranslateItem.task_id == task.id).all()
        fixed_count = 0
        for item in items:
            if item.status == "failed":
                item.status = "pending"
                fixed_count += 1

        task.status = "translating"
        db.commit()

        logger.info("Applied fix to task id=%d: %d items reset to pending", task_id, fixed_count)
        return {
            "task_id": task_id,
            "status": task.status,
            "fixed_count": fixed_count,
        }
