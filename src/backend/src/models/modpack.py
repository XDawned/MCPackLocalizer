"""
ORM 模型：整合包相关表

定义 Modpack、ModpackVersion、ModReference 三个表结构。
"""

import json
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship

try:
    from ..database import Base
except ImportError:
    from src.database import Base  # type: ignore


class Modpack(Base):
    """整合包表"""

    __tablename__ = "modpacks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(32), nullable=False, comment="平台：curseforge / modrinth")
    external_id = Column(String(64), nullable=False, comment="外部平台 ID")
    slug = Column(String(256), nullable=True, comment="Slug 标识")
    name = Column(String(512), nullable=False, comment="名称")
    summary = Column(Text, nullable=True, comment="简介")
    download_count = Column(Integer, default=0, comment="下载量")
    icon_url = Column(String(1024), nullable=True, comment="图标 URL")
    author = Column(String(256), nullable=True, comment="作者")
    last_updated = Column(DateTime, nullable=True, comment="最后更新时间")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="更新时间",
    )

    # ---- 新增字段（P2-1：数据库模型字段对齐） ----
    mc_version = Column(String(64), nullable=True, comment="主要 MC 版本")
    game_versions_json = Column(Text, nullable=True, comment="支持的 MC 版本 JSON 列表")
    loaders_json = Column(Text, nullable=True, comment="加载器 JSON 列表（备用详细数据）")
    hash = Column(String(128), nullable=True, comment="文件哈希值")
    pack_format = Column(Integer, nullable=True, comment="数据包格式版本")
    release_date = Column(DateTime, nullable=True, comment="发布日期")

    # 关联版本
    versions = relationship("ModpackVersion", back_populates="modpack", cascade="all, delete-orphan")

    # ---- 属性：前端字段别名 ----

    @property
    def game_versions(self) -> List[str]:
        """返回解析后的 MC 版本列表，与前端 game_versions 字段对齐"""
        if self.game_versions_json:
            try:
                return json.loads(self.game_versions_json)
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    @game_versions.setter
    def game_versions(self, value: Optional[List[str]]):
        """设置 MC 版本列表，自动序列化为 JSON"""
        if value is None:
            self.game_versions_json = None
        else:
            self.game_versions_json = json.dumps(value, ensure_ascii=False)

    @property
    def loaders(self) -> List[str]:
        """返回解析后的加载器列表，与前端 loaders 字段对齐"""
        if self.loaders_json:
            try:
                return json.loads(self.loaders_json)
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    @loaders.setter
    def loaders(self, value: Optional[List[str]]):
        """设置加载器列表，自动序列化为 JSON"""
        if value is None:
            self.loaders_json = None
        else:
            self.loaders_json = json.dumps(value, ensure_ascii=False)

    def __repr__(self):
        return f"<Modpack(id={self.id}, platform={self.platform}, slug={self.slug}, name={self.name})>"


class ModpackVersion(Base):
    """整合包版本表"""

    __tablename__ = "modpack_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    modpack_id = Column(Integer, ForeignKey("modpacks.id", ondelete="CASCADE"), nullable=False, comment="所属整合包 ID")
    version_number = Column(String(128), nullable=False, comment="版本号")
    mc_version = Column(String(64), nullable=True, comment="MC 版本")
    loader = Column(String(64), nullable=True, comment="模组加载器")
    external_version_id = Column(String(128), nullable=True, comment="外部平台版本 ID")
    download_url = Column(String(1024), nullable=True, comment="下载链接")
    file_size = Column(Integer, nullable=True, comment="文件大小（字节）")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    # 关联
    modpack = relationship("Modpack", back_populates="versions")
    mods = relationship("ModReference", back_populates="version", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ModpackVersion(id={self.id}, version={self.version_number})>"


class ModReference(Base):
    """Mod 引用表"""

    __tablename__ = "mod_references"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version_id = Column(
        Integer,
        ForeignKey("modpack_versions.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属版本 ID",
    )
    mod_external_id = Column(String(128), nullable=False, comment="Mod 外部 ID")
    name = Column(String(512), nullable=True, comment="Mod 名称")
    platform = Column(String(32), nullable=True, comment="平台")
    download_url = Column(String(1024), nullable=True, comment="下载链接")
    required = Column(Boolean, default=True, comment="是否必须")

    # 关联
    version = relationship("ModpackVersion", back_populates="mods")

    def __repr__(self):
        return f"<ModReference(id={self.id}, name={self.name})>"
