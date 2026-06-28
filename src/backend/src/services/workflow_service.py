"""
工作流编排服务

管理本地化流水线的阶段推进、分支逻辑和状态追踪。
覆盖项目开发规划中定义的 8 个阶段及其分支路由。
"""

import logging
from enum import IntEnum

from sqlalchemy.orm import Session

try:
    from ..models.translation import TranslationTask
except ImportError:
    from src.models.translation import TranslationTask  # type: ignore

logger = logging.getLogger(__name__)


class WorkflowStage(IntEnum):
    """工作流阶段枚举，值为流程顺序号"""

    PACKAGE_RETRIEVAL = 1      # 检索整合包
    LOCALIZATION_CONFIG = 2    # 本地化配置
    AI_TRANSLATION = 3         # AI翻译工作流
    FILE_APPLICATION = 4       # 汉化文件应用
    EFFECT_VERIFICATION = 5    # 效果验证
    CACHE_RECORDING = 6        # 记录缓存
    AI_REPAIR = 7              # AI Agent修复
    MANUAL_INTERVENTION = 8    # 人工介入


STAGE_LABELS: dict[int, str] = {
    1: "检索整合包",
    2: "本地化配置",
    3: "AI翻译工作流",
    4: "汉化文件应用",
    5: "效果验证",
    6: "记录缓存",
    7: "AI Agent修复",
    8: "人工介入",
}

# TranslationTask.status → WorkflowStage 映射
STATUS_TO_STAGE: dict[str, int | None] = {
    "pending": WorkflowStage.LOCALIZATION_CONFIG,
    "configuring": WorkflowStage.LOCALIZATION_CONFIG,
    "extracting": WorkflowStage.AI_TRANSLATION,
    "translating": WorkflowStage.AI_TRANSLATION,
    "assembling": WorkflowStage.AI_TRANSLATION,
    "ready_to_apply": WorkflowStage.FILE_APPLICATION,
    "applied": WorkflowStage.EFFECT_VERIFICATION,
    "completed": WorkflowStage.EFFECT_VERIFICATION,
    "verified": WorkflowStage.CACHE_RECORDING,
    "needs_fix": WorkflowStage.AI_REPAIR,
    "fixing": WorkflowStage.AI_REPAIR,
    "failed": WorkflowStage.MANUAL_INTERVENTION,
    "cancelled": None,
}

# WorkflowStage → TranslationTask.status 映射
STAGE_TO_STATUS: dict[int, str] = {
    1: "pending",
    2: "configuring",
    3: "translating",
    4: "ready_to_apply",
    5: "applied",
    6: "verified",
    7: "needs_fix",
    8: "failed",
}

# 允许的阶段跳转
VALID_TRANSITIONS: set[tuple[int, int]] = {
    (1, 2), (2, 3), (3, 4), (4, 5),
    (5, 6), (5, 7),
    (7, 6), (7, 8),
}

# 无法自动前进的终态阶段
TERMINAL_STAGES: set[int] = {6, 8}

# 线性阶段自动推进映射
LINEAR_NEXT: dict[int, int] = {1: 2, 2: 3, 3: 4, 4: 5}

# 需要分支决策的阶段
BRANCH_STAGES: set[int] = {5, 7}


class WorkflowService:
    """工作流编排服务 —— 驱动本地化流水线的阶段推进"""

    def _get_current_stage(self, task: TranslationTask) -> int | None:
        """从任务状态推导当前工作流阶段"""
        return STATUS_TO_STAGE.get(task.status)

    def _build_step_statuses(self, current_stage: int | None) -> dict[int, str]:
        """构建 1-8 阶段各自的状态字典"""
        statuses: dict[int, str] = {}
        if current_stage is None:
            return statuses
        for stage in range(1, 9):
            if stage < current_stage:
                statuses[stage] = "completed"
            elif stage == current_stage:
                statuses[stage] = "active"
            else:
                statuses[stage] = "pending"
        return statuses

    def _build_actions(self, task_id: int, current_stage: int) -> list[dict]:
        """根据当前阶段生成可用操作列表"""
        base = f"/api/v1/workflow/{task_id}"
        actions: list[dict] = []

        if current_stage in (1, 2, 3, 4):
            next_label = STAGE_LABELS.get(current_stage + 1, "下一阶段")
            actions.append({
                "action_key": "advance",
                "label": f"进入{next_label}",
                "description": f"推进到{next_label}",
                "route": f"{base}/advance",
            })
        elif current_stage == 5:
            actions.append({
                "action_key": "complete_success",
                "label": "验证通过",
                "description": "效果验证成功，进入记录缓存",
                "route": f"{base}/complete/5?success=true",
            })
            actions.append({
                "action_key": "complete_failure",
                "label": "验证失败",
                "description": "效果验证失败，启动AI修复",
                "route": f"{base}/complete/5?success=false",
            })
        elif current_stage == 7:
            actions.append({
                "action_key": "complete_success",
                "label": "修复成功",
                "description": "AI修复成功，进入记录缓存",
                "route": f"{base}/complete/7?success=true",
            })
            actions.append({
                "action_key": "complete_failure",
                "label": "修复失败",
                "description": "AI修复失败，进入人工介入",
                "route": f"{base}/complete/7?success=false",
            })

        return actions

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    async def get_workflow_state(self, db: Session, task_id: int) -> dict:
        """获取任务的完整工作流状态"""
        task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
        if not task:
            raise ValueError(f"TranslationTask id={task_id} not found")

        current_stage = self._get_current_stage(task)

        if current_stage is None:
            return {
                "task_id": task_id,
                "current_stage": None,
                "current_stage_label": None,
                "step_statuses": {},
                "can_advance": False,
                "next_stage": None,
                "available_actions": [],
            }

        step_statuses = self._build_step_statuses(current_stage)
        can_advance = current_stage not in TERMINAL_STAGES
        next_stage = LINEAR_NEXT.get(current_stage) or (6 if current_stage in (5, 7) else None)
        available_actions = self._build_actions(task_id, current_stage)

        return {
            "task_id": task_id,
            "current_stage": current_stage,
            "current_stage_label": STAGE_LABELS.get(current_stage, ""),
            "step_statuses": step_statuses,
            "can_advance": can_advance,
            "next_stage": next_stage,
            "available_actions": available_actions,
        }

    async def advance_workflow(
        self, db: Session, task_id: int, next_stage: int | None = None
    ) -> dict:
        """
        推进工作流到下一阶段。

        若未指定 next_stage 则自动推导：
          - 线性阶段 (1-4) → current + 1
          - 分支阶段 (5, 7) → 默认成功路径 (6)
        """
        task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
        if not task:
            raise ValueError(f"TranslationTask id={task_id} not found")

        current_stage = self._get_current_stage(task)
        if current_stage is None:
            raise ValueError(
                f"Task id={task_id} has no active workflow (status: {task.status})"
            )
        if current_stage in TERMINAL_STAGES:
            raise ValueError(
                f"Task id={task_id} is at terminal stage {current_stage}"
                f" ({STAGE_LABELS.get(current_stage)})"
            )

        if next_stage is None:
            next_stage = LINEAR_NEXT.get(current_stage) or (
                6 if current_stage in (5, 7) else None
            )

        if next_stage is None:
            raise ValueError(
                f"Cannot determine next stage from stage {current_stage}"
            )

        transition = (current_stage, next_stage)
        if transition not in VALID_TRANSITIONS:
            raise ValueError(
                f"Invalid transition from stage {current_stage}"
                f" ({STAGE_LABELS.get(current_stage)})"
                f" to stage {next_stage}"
                f" ({STAGE_LABELS.get(next_stage)})"
            )

        new_status = STAGE_TO_STATUS.get(next_stage)
        if new_status:
            task.status = new_status
            db.commit()
            logger.info(
                "Task id=%d: advanced from stage %d to stage %d (status=%s)",
                task_id, current_stage, next_stage, new_status,
            )

        return await self.get_workflow_state(db=db, task_id=task_id)

    async def complete_stage(
        self, db: Session, task_id: int, stage: int, success: bool = True
    ) -> dict:
        """
        完成当前阶段并根据分支逻辑推进。

        分支规则：
          - 阶段 5（效果验证）：成功 → 6，失败 → 7
          - 阶段 7（AI修复）：  成功 → 6，失败 → 8
          - 其他阶段：仅记录完成，不自动推进
        """
        task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
        if not task:
            raise ValueError(f"TranslationTask id={task_id} not found")

        current_stage = self._get_current_stage(task)
        if current_stage is None:
            raise ValueError(f"Task id={task_id} has no active workflow")
        if current_stage != stage:
            raise ValueError(
                f"Task id={task_id} is at stage {current_stage},"
                f" cannot complete stage {stage}"
            )

        if stage == WorkflowStage.EFFECT_VERIFICATION:
            next_stage = WorkflowStage.CACHE_RECORDING if success else WorkflowStage.AI_REPAIR
            new_status = STAGE_TO_STATUS.get(next_stage)
            if new_status:
                task.status = new_status
            db.commit()
            logger.info(
                "Task id=%d: stage 5 completed (success=%s), advancing to stage %d",
                task_id, success, next_stage,
            )
            return await self.get_workflow_state(db=db, task_id=task_id)

        if stage == WorkflowStage.AI_REPAIR:
            next_stage = WorkflowStage.CACHE_RECORDING if success else WorkflowStage.MANUAL_INTERVENTION
            new_status = STAGE_TO_STATUS.get(next_stage)
            if new_status:
                task.status = new_status
            db.commit()
            logger.info(
                "Task id=%d: stage 7 completed (success=%s), advancing to stage %d",
                task_id, success, next_stage,
            )
            return await self.get_workflow_state(db=db, task_id=task_id)

        logger.info("Task id=%d: stage %d marked as completed", task_id, stage)
        return await self.get_workflow_state(db=db, task_id=task_id)

    async def get_available_actions(self, db: Session, task_id: int) -> list[dict]:
        """返回当前阶段可执行的操作列表"""
        task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
        if not task:
            raise ValueError(f"TranslationTask id={task_id} not found")

        current_stage = self._get_current_stage(task)
        if current_stage is None:
            return []

        return self._build_actions(task_id, current_stage)
