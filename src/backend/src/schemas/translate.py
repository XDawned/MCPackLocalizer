"""
Pydantic v2 数据模型：翻译相关请求/响应 Schema

定义翻译配置、任务启动、进度推送等数据结构。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ==================== 翻译配置 ====================


class AIProviderOverrideConfig(BaseModel):
    """翻译任务中的 AI 提供商覆写配置

    允许翻译启动时临时覆写已保存的 provider 配置，
    而不必修改 provider 本身的设置。
    """

    api_base: Optional[str] = Field(default=None, description="覆写API基础地址")
    api_key: Optional[str] = Field(default=None, description="覆写API密钥")
    default_model: Optional[str] = Field(default=None, description="覆写默认模型")
    provider_type: Optional[str] = Field(default=None, description="覆写提供商类型")


class TranslateConfigRequest(BaseModel):
    """翻译配置请求"""

    keep_original: bool = Field(default=True, description="保留原文")
    enable_cache: bool = Field(default=True, description="启用缓存")
    cache_scope: str = Field(default="version", description="缓存范围: version/modpack/all")
    cache_reference_ids: List[str] = Field(default_factory=list, description="缓存参考版本ID列表")
    ai_provider: str = Field(default="openai", description="AI提供商类型（兼容旧字段）")
    ai_model: str = Field(default="gpt-4o", description="AI模型（兼容旧字段）")
    provider_id: Optional[int] = Field(default=None, description="AI提供商ID（优先于ai_provider字段）")
    provider_override: Optional[AIProviderOverrideConfig] = Field(
        default=None,
        description="AI提供商参数覆写（临时替换，不修改已保存配置）",
    )
    enable_glossary: bool = Field(default=True, description="启用术语库")
    batch_size: int = Field(default=20, ge=1, le=10000, description="每批翻译条数")
    concurrency: int = Field(default=3, ge=1, le=10, description="并发请求数")
    batch_retry_limit: int = Field(default=3, ge=0, le=3, description="单个翻译批次失败后的自动重试次数，0 表示不自动重试")
    custom_prompt: Optional[str] = Field(
        default=None,
        description="追加到默认系统提示词后的用户补充要求，留空则使用默认提示词",
    )
    scan_id: Optional[str] = Field(
        default=None,
        description="扫描ID，用于复用扫描缓存按范围提取可翻译内容",
    )
    game_name: Optional[str] = Field(
        default=None,
        description="当 local_path 指向 .minecraft 根目录时，指定目标实例名称",
    )
    selected_areas: Optional[List[str]] = Field(
        default=None,
        description="选中的翻译区域类型列表，如 ['mod_lang','ftb_quests']；仅在有 scan_id 时生效",
    )


# ==================== 翻译启动 ====================


class TranslateStartRequest(BaseModel):
    """启动翻译请求"""

    modpack_version_id: Optional[str] = Field(default=None, description="整合包版本ID")
    local_path: str = Field(..., description="本地整合包路径")
    config: TranslateConfigRequest = Field(default_factory=TranslateConfigRequest)


# ==================== 翻译任务 ====================


class TranslateTaskResponse(BaseModel):
    """翻译任务响应"""

    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态")
    total_items: int = Field(default=0, description="总条目数")
    completed_items: int = Field(default=0, description="已完成条目数")
    tokens_consumed: int = Field(default=0, description="已消耗Token数")
    cost: float = Field(default=0.0, description="费用")
    created_at: Optional[str] = Field(default=None, description="创建时间")
    finished_at: Optional[str] = Field(default=None, description="完成时间")


# ==================== 翻译条目 ====================


class TranslateItemResponse(BaseModel):
    """翻译条目响应"""

    id: int = Field(..., description="条目ID")
    source_file: str = Field(..., description="源文件名")
    source_path: str = Field(..., description="源文件路径")
    original_text: str = Field(..., description="原文")
    translated_text: Optional[str] = Field(default=None, description="译文")
    source_hash: str = Field(..., description="源文本哈希")
    from_cache: bool = Field(default=False, description="是否来自缓存")
    status: str = Field(..., description="条目状态")
    area_type: Optional[str] = Field(default=None, description="扫描区域类型")
    target_strategy: Optional[str] = Field(default=None, description="应用策略")
    target_path: Optional[str] = Field(default=None, description="应用/补丁输出的目标相对路径")
    apply_metadata: Dict[str, Any] = Field(default_factory=dict, description="完整应用元数据")


# ==================== WebSocket 进度推送 ====================


class TranslateProgressWS(BaseModel):
    """WebSocket进度推送"""

    type: str = Field(default="progress", description="消息类型")
    stage: str = Field(..., description="阶段: extracting / translating / assembling")
    data: Dict[str, Any] = Field(..., description="阶段数据")


class TranslateLogEvent(BaseModel):
    """翻译日志事件"""

    level: str = Field(..., description="日志级别：INFO / WARN / ERROR / DEBUG")
    timestamp: str = Field(..., description="ISO 8601 格式时间戳")
    message: str = Field(..., description="日志消息")
    context: Optional[Dict[str, Any]] = Field(default=None, description="上下文信息")


# ==================== SSE 流式进度事件 ====================


class TranslateSSEEvent(BaseModel):
    """SSE 流式进度事件

    用于 /start/stream 端点返回的 Server-Sent Events 事件结构。
    每条 SSE 事件的 data 字段为该模型的 JSON 序列化。

    type 取值:
      - progress: 阶段性进度更新
      - log:      结构化实时日志
      - error:    错误事件（可区分 fatal / non-fatal）
      - done:     翻译结束

    stage 取值（type=progress 时）:
      - started / extracting / translating / assembling / paused / cancelled

    stage 取值（type=done 时）:
      - done / cancelled
    """

    type: str = Field(..., description="事件类型: progress / log / error / done")
    stage: str = Field(..., description="当前阶段")
    data: Dict[str, Any] | TranslateLogEvent = Field(default_factory=dict, description="事件数据；当 type=log 时为 TranslateLogEvent")
