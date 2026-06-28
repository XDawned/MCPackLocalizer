"""
ORM 模型：备份记录表

定义 BackupRecord 表结构，用于记录翻译前后的文件备份信息。
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
)

try:
    from ..database import Base
except ImportError:
    from src.database import Base  # type: ignore


class BackupRecord(Base):
    """备份记录表"""

    __tablename__ = "backup_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    modpack_version_id = Column(
        Integer,
        ForeignKey("modpack_versions.id"),
        nullable=True,
        comment="关联的整合包版本 ID",
    )
    backup_path = Column(String(1024), nullable=True, comment="备份目录路径")
    backed_files_json = Column(Text, nullable=True, comment="已备份文件路径 JSON 列表")
    added_files_json = Column(Text, nullable=True, comment="新增文件路径 JSON 列表")
    status = Column(String(32), default="active", comment="状态：active / restored")
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        comment="创建时间",
    )

    def __repr__(self):
        return f"<BackupRecord(id={self.id}, status={self.status})>"
