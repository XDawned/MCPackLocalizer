"""
ORM 模型：系统设置与 AI 提供商配置

定义 Setting、AIProvider 两个表结构。
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
)

try:
    from ..database import Base
except ImportError:
    from src.database import Base  # type: ignore


class Setting(Base):
    """系统设置键值表"""

    __tablename__ = "settings"

    key = Column(String(256), primary_key=True, comment="设置键")
    value = Column(Text, nullable=True, comment="设置值")
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="更新时间",
    )

    def __repr__(self):
        return f"<Setting(key={self.key}, value={self.value})>"


class AIProvider(Base):
    """AI 提供商配置表"""

    __tablename__ = "ai_providers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False, comment="提供商名称")
    provider_type = Column(String(64), nullable=False, comment="提供商类型：openai / anthropic / deepseek")
    api_base = Column(String(512), nullable=True, comment="API 基础地址")
    api_key_encrypted = Column(Text, nullable=True, comment="加密后的 API Key")
    default_model = Column(String(128), nullable=True, comment="默认模型")
    is_enabled = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        comment="创建时间",
    )

    def __repr__(self):
        return f"<AIProvider(id={self.id}, name={self.name}, provider_type={self.provider_type})>"
