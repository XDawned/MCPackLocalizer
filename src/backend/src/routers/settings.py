"""
设置 API 路由

提供全局设置管理、AI 提供商配置 CRUD、模型列表拉取及连接测试端点。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.settings import Setting, AIProvider as AIProviderModel
from ..schemas.settings import (
    AIProviderCreate,
    AIProviderUpdate,
    AIProviderResponse,
    AIProviderOverride,
    AITestRequest,
    AITestResponse,
    AIModelsRequest,
    AIModelsResponse,
    AIModelItem,
    CacheStatsResponse,
    ClearCacheResponse,
    SettingsUpdateRequest,
    SettingsResponse,
)
from ..adapters.ai_provider import (
    AIProvider,
    normalize_api_base,
    PROVIDER_CONFIGS,
    DEFAULT_MODELS,
)

from ..services.cache_service import CacheService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])
cache_service = CacheService()

TRANSLATE_BATCH_RETRY_LIMIT_KEY = "translate_batch_retry_limit"
DEFAULT_TRANSLATE_BATCH_RETRY_LIMIT = 3
MAX_TRANSLATE_BATCH_RETRY_LIMIT = 3
DEFAULT_SETTINGS = {
    TRANSLATE_BATCH_RETRY_LIMIT_KEY: str(DEFAULT_TRANSLATE_BATCH_RETRY_LIMIT),
    "target_minecraft_root": "",
    "patch_output_dir": "",
    "include_i18n_update_mod": "false",
    "i18n_mod_cache_dir": "",
}


def _normalize_setting_value(key: str, value) -> str:
    if key == TRANSLATE_BATCH_RETRY_LIMIT_KEY:
        try:
            retry_limit = int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail="单批失败自动重试次数必须为 0~3 的整数",
            ) from exc

        if retry_limit < 0 or retry_limit > MAX_TRANSLATE_BATCH_RETRY_LIMIT:
            raise HTTPException(
                status_code=422,
                detail="单批失败自动重试次数必须在 0~3 之间",
            )
        return str(retry_limit)

    if value is None:
        return ""
    return str(value)


# ==================== 通用设置 ====================


@router.get("/")
async def get_settings(db: Session = Depends(get_db)):
    """获取所有通用设置键值对"""
    try:
        rows = db.query(Setting).all()
        data = dict(DEFAULT_SETTINGS)
        data.update({row.key: row.value for row in rows})
        return {"code": 0, "data": data, "message": "ok"}
    except Exception as e:
        logger.error("Failed to get settings: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/")
async def update_settings(
    body: SettingsUpdateRequest,
    db: Session = Depends(get_db),
):
    """批量更新通用设置键值对"""
    try:
        for key, value in body.settings.items():
            normalized_value = _normalize_setting_value(key, value)
            existing = db.query(Setting).filter(Setting.key == key).first()
            if existing:
                existing.value = normalized_value
            else:
                db.add(Setting(key=key, value=normalized_value))
        db.commit()

        # Return updated settings
        rows = db.query(Setting).all()
        data = dict(DEFAULT_SETTINGS)
        data.update({row.key: row.value for row in rows})
        return {"code": 0, "data": data, "message": "ok"}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error("Failed to update settings: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== AI Provider CRUD ====================


@router.get("/ai/providers")
async def list_ai_providers(db: Session = Depends(get_db)):
    """获取所有 AI 提供商列表（不回传明文 API Key）"""
    try:
        providers = db.query(AIProviderModel).order_by(AIProviderModel.id).all()
        data = [AIProviderResponse.from_orm_model(p).model_dump() for p in providers]
        return {"code": 0, "data": data, "message": "ok"}
    except Exception as e:
        logger.error("Failed to list AI providers: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai/providers/{provider_id}")
async def get_ai_provider(provider_id: int, db: Session = Depends(get_db)):
    """获取单个 AI 提供商详情"""
    try:
        provider = db.query(AIProviderModel).filter(AIProviderModel.id == provider_id).first()
        if not provider:
            raise HTTPException(status_code=404, detail=f"AI provider {provider_id} not found")
        data = AIProviderResponse.from_orm_model(provider).model_dump()
        return {"code": 0, "data": data, "message": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get AI provider: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai/providers")
async def create_ai_provider(
    body: AIProviderCreate,
    db: Session = Depends(get_db),
):
    """新增 AI 提供商"""
    try:
        # Normalize api_base
        api_base = normalize_api_base(body.api_base, body.provider_type)

        provider = AIProviderModel(
            name=body.name,
            provider_type=body.provider_type,
            api_base=api_base,
            api_key_encrypted=body.api_key or "",
            default_model=body.default_model,
            is_enabled=body.is_enabled,
        )
        db.add(provider)
        db.commit()
        db.refresh(provider)

        data = AIProviderResponse.from_orm_model(provider).model_dump()
        return {"code": 0, "data": data, "message": "ok"}
    except Exception as e:
        db.rollback()
        logger.error("Failed to create AI provider: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/ai/providers/{provider_id}")
async def update_ai_provider(
    provider_id: int,
    body: AIProviderUpdate,
    db: Session = Depends(get_db),
):
    """
    更新 AI 提供商配置

    api_key 语义：
      - null 或不传 → 保持原值不变
      - 非空字符串 → 更新为新密钥
      - 空字符串 "" → 显式清空密钥
    """
    try:
        provider = db.query(AIProviderModel).filter(AIProviderModel.id == provider_id).first()
        if not provider:
            raise HTTPException(status_code=404, detail=f"AI provider {provider_id} not found")

        if body.name is not None:
            provider.name = body.name
        if body.provider_type is not None:
            provider.provider_type = body.provider_type
        if body.api_base is not None:
            provider.api_base = normalize_api_base(body.api_base, body.provider_type or provider.provider_type)
        if body.default_model is not None:
            provider.default_model = body.default_model
        if body.is_enabled is not None:
            provider.is_enabled = body.is_enabled

        # api_key handling: null=keep, ""=clear, "xxx"=update
        if body.api_key is not None:
            if body.api_key == "":
                # Explicitly clear
                provider.api_key_encrypted = ""
            else:
                # Update to new value
                provider.api_key_encrypted = body.api_key

        db.commit()
        db.refresh(provider)

        data = AIProviderResponse.from_orm_model(provider).model_dump()
        return {"code": 0, "data": data, "message": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Failed to update AI provider: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/ai/providers/{provider_id}")
async def delete_ai_provider(
    provider_id: int,
    db: Session = Depends(get_db),
):
    """删除 AI 提供商"""
    try:
        provider = db.query(AIProviderModel).filter(AIProviderModel.id == provider_id).first()
        if not provider:
            raise HTTPException(status_code=404, detail=f"AI provider {provider_id} not found")

        db.delete(provider)
        db.commit()
        return {"code": 0, "data": None, "message": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error("Failed to delete AI provider: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== AI 模型列表 ====================


def _build_provider_from_override(
    db_provider: AIProviderModel,
    override: AIProviderOverride | None,
) -> AIProvider:
    """
    Build an AIProvider instance from a DB record, optionally applying overrides.

    This merges the saved provider config with any runtime overrides, allowing
    the test/models endpoints to work with temporary configurations.
    """
    provider_type = override.provider_type if (override and override.provider_type) else db_provider.provider_type
    api_key = override.api_key if (override and override.api_key is not None) else (db_provider.api_key_encrypted or "")
    api_base = override.api_base if (override and override.api_base is not None) else db_provider.api_base
    model = override.default_model if (override and override.default_model) else (db_provider.default_model or DEFAULT_MODELS.get(provider_type, "gpt-4o"))

    # Normalize api_base
    api_base = normalize_api_base(api_base, provider_type)

    return AIProvider(
        provider_type=provider_type,
        api_key=api_key,
        api_base=api_base,
        model=model,
    )


def _build_temporary_provider_from_override(
    override: AIProviderOverride | None,
) -> AIProvider:
    """Build an AIProvider instance only from runtime override data."""
    if override is None:
        raise HTTPException(status_code=422, detail="缺少 provider_id 时必须提供 override")

    provider_type = (override.provider_type or "openai").strip().lower()
    if provider_type not in PROVIDER_CONFIGS:
        raise HTTPException(status_code=422, detail=f"不支持的 provider_type: {provider_type}")

    api_base = normalize_api_base(override.api_base, provider_type)
    model = override.default_model or DEFAULT_MODELS.get(provider_type, "gpt-4o")

    return AIProvider(
        provider_type=provider_type,
        api_key=override.api_key or "",
        api_base=api_base,
        model=model,
    )


@router.post("/ai/models")
async def fetch_ai_models(
    body: AIModelsRequest,
    db: Session = Depends(get_db),
):
    """
    拉取指定提供商的可用模型列表。

    接受可选 provider_id 以及可选的覆写参数（base URL、API Key、model、provider_type）；
    当 provider_id 为空时，使用 override 中的临时配置。
    """
    try:
        if body.provider_id is not None:
            db_provider = db.query(AIProviderModel).filter(AIProviderModel.id == body.provider_id).first()
            if not db_provider:
                raise HTTPException(status_code=404, detail=f"AI provider {body.provider_id} not found")
            provider = _build_provider_from_override(db_provider, body.override)
            provider_label = str(body.provider_id)
        else:
            provider = _build_temporary_provider_from_override(body.override)
            provider_label = "temporary override"

        try:
            models_raw = await provider.fetch_models()
            models = [
                AIModelItem(
                    id=m["id"],
                    name=m.get("name"),
                    owned_by=m.get("owned_by"),
                )
                for m in models_raw
            ]
        except Exception as e:
            logger.warning("Failed to fetch models for provider %s: %s", provider_label, e)
            raise HTTPException(
                status_code=502,
                detail=f"无法获取模型列表：{str(e)[:200]}",
            )

        response = AIModelsResponse(
            models=models,
            provider_type=provider.provider_type,
            api_base=provider.api_base,
        )
        return {"code": 0, "data": response.model_dump(), "message": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch AI models: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 缓存统计 / 清理 ====================


@router.get("/cache/stats")
async def get_cache_stats(db: Session = Depends(get_db)):
    try:
        stats = await cache_service.get_cache_stats(db)
        response = CacheStatsResponse(
            entries=int(stats.get("entries") or 0),
            hits=int(stats.get("hits") or 0),
            by_target_language=stats.get("by_target_language") or {},
            by_scope=stats.get("by_scope") or {},
            last_used_at=stats.get("last_used_at"),
            last_created_at=stats.get("last_created_at"),
        )
        return {"code": 0, "data": response.model_dump(), "message": "ok"}
    except Exception as e:
        logger.error("Failed to get cache stats: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cache")
async def clear_cache(db: Session = Depends(get_db)):
    try:
        result = await cache_service.clear_cache(db)
        response = ClearCacheResponse(cleared_entries=int(result.get("cleared_entries") or 0))
        return {"code": 0, "data": response.model_dump(), "message": "ok"}
    except Exception as e:
        logger.error("Failed to clear cache: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== AI 连接测试 ====================


@router.post("/ai/test")
async def te4st_ai_connection(
    body: AITestRequest,
    db: Session = Depends(get_db),
):
    """
    测试 AI 提供商连接是否可用。

    接受 provider_id 以及可选的覆写参数和指定测试模型，
    返回测试结果（成功/失败、延迟、消息）。
    """
    try:
        if body.provider_id is not None:
            db_provider = db.query(AIProviderModel).filter(AIProviderModel.id == body.provider_id).first()
            if not db_provider:
                raise HTTPException(status_code=404, detail=f"AI provider {body.provider_id} not found")
            provider = _build_provider_from_override(db_provider, body.override)
        else:
            provider = _build_temporary_provider_from_override(body.override)

        # Use specified model or fall back to provider default
        test_model = body.model or provider.model

        result = await provider.test_connection(model=test_model)

        response = AITestResponse(
            success=result["success"],
            message=result["message"],
            latency_ms=result.get("latency_ms", 0),
            model_used=result.get("model_used"),
        )
        return {"code": 0, "data": response.model_dump(), "message": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to test AI connection: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
