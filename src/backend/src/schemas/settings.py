"""
Pydantic v2 数据模型：设置相关请求/响应 Schema

定义AI提供商配置、设置更新、连接测试、模型列表等数据结构。
"""

from __future__ import annotations

from typing import Optional, List, Dict
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# ==================== 通用设置 ====================


class SettingsUpdateRequest(BaseModel):
    """批量更新设置请求"""

    settings: Dict[str, str] = Field(..., description="设置键值对")


class SettingsResponse(BaseModel):
    """设置响应"""

    settings: Dict[str, str] = Field(..., description="设置键值对")


# ==================== AI 提供商 ====================


class AIProviderCreate(BaseModel):
    """AI提供商创建请求"""

    name: str = Field(..., min_length=1, max_length=128, description="提供商名称")
    provider_type: str = Field(
        ..., min_length=1, max_length=64, description="提供商类型: openai / anthropic / deepseek / qwen / zhipu / ollama"
    )
    api_base: Optional[str] = Field(default=None, description="API基础地址，为空时使用默认值")
    api_key: Optional[str] = Field(default=None, description="API密钥（原始值，后端存储；传null表示不设置）")
    default_model: Optional[str] = Field(default=None, description="默认模型")
    is_enabled: bool = Field(default=True, description="是否启用")

    @field_validator("provider_type")
    @classmethod
    def validate_provider_type(cls, v: str) -> str:
        allowed = {"openai", "anthropic", "deepseek", "qwen", "zhipu", "ollama"}
        v_lower = v.strip().lower()
        if v_lower not in allowed:
            raise ValueError(f"不支持的提供商类型: {v}，允许值: {', '.join(sorted(allowed))}")
        return v_lower

    @field_validator("api_base")
    @classmethod
    def normalize_api_base(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                return None
            # 确保末尾没有斜杠
            v = v.rstrip("/")
        return v


class AIProviderUpdate(BaseModel):
    """AI提供商更新请求

    api_key 字段语义：
      - 传字符串值 → 更新为新密钥
      - 传 null / 不传 → 保持原值不变
      - 传空字符串 "" → 显式清空密钥
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=128, description="提供商名称")
    provider_type: Optional[str] = Field(default=None, description="提供商类型")
    api_base: Optional[str] = Field(default=None, description="API基础地址")
    api_key: Optional[str] = Field(default=None, description="API密钥；null=保持原值，空字符串=清空")
    default_model: Optional[str] = Field(default=None, description="默认模型")
    is_enabled: Optional[bool] = Field(default=None, description="是否启用")

    @field_validator("provider_type")
    @classmethod
    def validate_provider_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = {"openai", "anthropic", "deepseek", "qwen", "zhipu", "ollama"}
        v_lower = v.strip().lower()
        if v_lower not in allowed:
            raise ValueError(f"不支持的提供商类型: {v}，允许值: {', '.join(sorted(allowed))}")
        return v_lower

    @field_validator("api_base")
    @classmethod
    def normalize_api_base(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                return None
            v = v.rstrip("/")
        return v


class AIProviderResponse(BaseModel):
    """AI提供商响应（不包含明文API Key）"""

    id: int = Field(..., description="提供商ID")
    name: str = Field(..., description="提供商名称")
    provider_type: str = Field(..., description="提供商类型")
    api_base: Optional[str] = Field(default=None, description="API基础地址")
    has_api_key: bool = Field(..., description="是否已设置API密钥")
    default_model: Optional[str] = Field(default=None, description="默认模型")
    is_enabled: bool = Field(..., description="是否启用")
    created_at: Optional[str] = Field(default=None, description="创建时间")

    @classmethod
    def from_orm_model(cls, obj) -> "AIProviderResponse":
        """从 ORM 模型构建响应，自动脱敏 API Key"""
        has_key = bool(obj.api_key_encrypted)
        created_at = None
        if obj.created_at:
            if isinstance(obj.created_at, datetime):
                created_at = obj.created_at.isoformat()
            else:
                created_at = str(obj.created_at)
        return cls(
            id=obj.id,
            name=obj.name,
            provider_type=obj.provider_type,
            api_base=obj.api_base,
            has_api_key=has_key,
            default_model=obj.default_model,
            is_enabled=obj.is_enabled,
            created_at=created_at,
        )


# ==================== AI 连接测试 ====================


class AIProviderOverride(BaseModel):
    """AI提供商参数覆写（用于测试/拉取模型时临时替换配置）"""

    api_base: Optional[str] = Field(default=None, description="覆写API基础地址")
    api_key: Optional[str] = Field(default=None, description="覆写API密钥")
    default_model: Optional[str] = Field(default=None, description="覆写默认模型")
    provider_type: Optional[str] = Field(default=None, description="覆写提供商类型")


class AITestRequest(BaseModel):
    """AI连接测试请求"""

    provider_id: Optional[int] = Field(default=None, description="提供商ID；为空时使用 override 中的临时配置")
    override: Optional[AIProviderOverride] = Field(default=None, description="可选参数覆写")
    model: Optional[str] = Field(default=None, description="指定测试模型，为空时使用提供商默认模型")


class AITestResponse(BaseModel):
    """AI连接测试响应"""

    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="测试消息")
    latency_ms: int = Field(default=0, description="延迟（毫秒）")
    model_used: Optional[str] = Field(default=None, description="实际使用的模型")


# ==================== 模型列表 ====================


class AIModelItem(BaseModel):
    """单个模型信息"""

    id: str = Field(..., description="模型标识")
    name: Optional[str] = Field(default=None, description="模型显示名称")
    owned_by: Optional[str] = Field(default=None, description="模型提供方")


class AIModelsRequest(BaseModel):
    """拉取模型列表请求"""

    provider_id: Optional[int] = Field(default=None, description="提供商ID；为空时使用 override 中的临时配置")
    override: Optional[AIProviderOverride] = Field(default=None, description="可选参数覆写")


class AIModelsResponse(BaseModel):
    """模型列表响应"""

    models: List[AIModelItem] = Field(default_factory=list, description="模型列表")
    provider_type: str = Field(..., description="实际使用的提供商类型")
    api_base: str = Field(..., description="实际使用的API基础地址")


class CacheStatsResponse(BaseModel):
    """缓存统计响应"""

    entries: int = Field(default=0, description="缓存条目总数")
    hits: int = Field(default=0, description="累计缓存命中次数")
    by_target_language: Dict[str, int] = Field(default_factory=dict, description="按目标语言分组的条目数量")
    by_scope: Dict[str, int] = Field(default_factory=dict, description="按作用域分组的条目数量")
    last_used_at: Optional[str] = Field(default=None, description="最近命中时间")
    last_created_at: Optional[str] = Field(default=None, description="最近写入时间")


class ClearCacheResponse(BaseModel):
    """清空缓存响应"""

    cleared_entries: int = Field(default=0, description="清理掉的缓存条目数")
