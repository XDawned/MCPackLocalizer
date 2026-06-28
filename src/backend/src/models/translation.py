"""
ORM 模型：翻译任务相关表

定义 TranslationTask、TranslateItem 两个表结构。
"""

from datetime import datetime, timezone
import json

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship

try:
    from ..database import Base
except ImportError:
    from src.database import Base  # type: ignore


class TranslationTask(Base):
    """翻译任务表"""

    __tablename__ = "translation_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    modpack_version_id = Column(
        Integer,
        ForeignKey("modpack_versions.id"),
        nullable=True,
        comment="关联的整合包版本 ID (远程)，本地导入时可为空",
    )
    local_modpack_id = Column(
        Integer,
        ForeignKey("local_modpacks.id"),
        nullable=True,
        comment="关联的本地整合包 ID",
    )
    local_path = Column(Text, nullable=True, comment="本地整合包路径")
    scan_result_json = Column(Text, nullable=True, comment="扫描结果缓存 JSON")
    status = Column(String(32), nullable=False, comment="任务状态")
    config_json = Column(Text, nullable=True, comment="任务配置 JSON")
    total_items = Column(Integer, default=0, comment="总条目数")
    completed_items = Column(Integer, default=0, comment="已完成条目数")
    tokens_consumed = Column(Integer, default=0, comment="已消耗 token 数")
    cost = Column(Float, default=0.0, comment="费用")
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        comment="创建时间",
    )
    finished_at = Column(DateTime, nullable=True, comment="完成时间")

    items = relationship("TranslateItem", back_populates="task", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<TranslationTask(id={self.id}, status={self.status}, total_items={self.total_items})>"


class TranslateItem(Base):
    """翻译条目表"""

    __tablename__ = "translate_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(
        Integer,
        ForeignKey("translation_tasks.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属翻译任务 ID",
    )
    source_file = Column(String(512), nullable=True, comment="源文件名")
    source_path = Column(String(1024), nullable=True, comment="源文件路径")
    apply_metadata_json = Column(Text, nullable=True, comment="应用元数据 JSON")
    original_text = Column(Text, nullable=True, comment="原文")
    translated_text = Column(Text, nullable=True, comment="译文")
    source_hash = Column(String(64), nullable=True, comment="原文哈希值")
    from_cache = Column(Boolean, default=False, comment="是否来自缓存")
    status = Column(String(32), nullable=True, comment="条目状态")
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        comment="创建时间",
    )

    task = relationship("TranslationTask", back_populates="items")

    def get_apply_metadata(self) -> dict:
        if not self.apply_metadata_json:
            return {}
        try:
            data = json.loads(self.apply_metadata_json)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def set_apply_metadata(self, metadata: dict | None) -> None:
        if metadata:
            self.apply_metadata_json = json.dumps(metadata, ensure_ascii=False)
        else:
            self.apply_metadata_json = None

    def __repr__(self):
        return f"<TranslateItem(id={self.id}, task_id={self.task_id}, status={self.status})>"
