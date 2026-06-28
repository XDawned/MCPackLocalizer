"""
ORM 模型：术语表

定义 GlossaryEntry 表结构，用于存储翻译术语对照。
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
)

try:
    from ..database import Base
except ImportError:
    from src.database import Base  # type: ignore


class GlossaryEntry(Base):
    """术语表"""

    __tablename__ = "glossary_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_term = Column(String(512), nullable=False, comment="源术语")
    target_term = Column(String(512), nullable=False, comment="目标术语")
    category = Column(String(128), nullable=True, comment="分类")
    source = Column(String(64), default="manual", comment="来源：manual / cfpa")
    is_regex = Column(Boolean, default=False, comment="是否为正则表达式")
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        comment="创建时间",
    )

    def __repr__(self):
        return f"<GlossaryEntry(id={self.id}, source_term={self.source_term}, category={self.category})>"
