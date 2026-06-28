"""
ORM 模型：翻译缓存表

定义 TranslationCache 表结构，用于缓存翻译结果以降低 API 调用成本。
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)

try:
    from ..database import Base
except ImportError:
    from src.database import Base  # type: ignore


class TranslationCache(Base):
    """翻译缓存表"""

    __tablename__ = "translation_cache"
    __table_args__ = (
        Index("ix_translation_cache_source_hash", "source_hash"),
        Index("ix_translation_cache_modpack_key", "modpack_key"),
        Index("ix_translation_cache_mc_version", "mc_version"),
        Index(
            "ix_translation_cache_lookup",
            "source_hash",
            "target_language",
            "modpack_version_id",
            "modpack_key",
            "mc_version",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_hash = Column(String(64), nullable=False, comment="原文哈希值")
    original_text = Column(Text, nullable=True, comment="原文")
    translated_text = Column(Text, nullable=True, comment="译文")
    modpack_id = Column(
        Integer,
        ForeignKey("modpacks.id"),
        nullable=True,
        comment="关联整合包 ID（保留兼容字段）",
    )
    modpack_version_id = Column(
        Integer,
        ForeignKey("modpack_versions.id"),
        nullable=True,
        comment="关联整合包版本 ID",
    )
    modpack_key = Column(String(255), nullable=True, comment="整合包级缓存作用域键")
    mc_version = Column(String(64), nullable=True, comment="MC 版本")
    ai_model = Column(String(128), nullable=True, comment="使用的 AI 模型")
    source_language = Column(String(32), nullable=True, default="auto", comment="源语言")
    target_language = Column(String(32), nullable=True, default="zh_cn", comment="目标语言")
    reliability_score = Column(Integer, default=0, comment="可靠性评分")
    use_count = Column(Integer, default=0, comment="缓存命中次数")
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        comment="创建时间",
    )
    last_used = Column(DateTime, nullable=True, comment="最后命中时间")

    def __repr__(self):
        return (
            "<TranslationCache("
            f"id={self.id}, source_hash={self.source_hash}, "
            f"target_language={self.target_language}, use_count={self.use_count}"
            ")>"
        )
