"""
ORM 模型：本地整合包表

存储从本地目录扫描到的整合包信息。
"""

import json
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Column, Integer, String, Text, DateTime

try:
    from ..database import Base
except ImportError:
    from src.database import Base  # type: ignore


class LocalModpack(Base):
    """本地整合包表"""

    __tablename__ = "local_modpacks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(512), nullable=False, comment="整合包名称")
    local_path = Column(String(1024), nullable=False, comment="本地绝对路径")
    pack_type = Column(String(32), nullable=True, comment="整合包类型: curseforge/hmcl/multimc/modrinth/mcbbs/unknown")
    mc_version = Column(String(64), nullable=True, comment="Minecraft 版本")
    mod_list_json = Column(Text, nullable=True, comment="Mod 清单 JSON")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间")

    @property
    def mod_list(self) -> List[dict]:
        if self.mod_list_json:
            try:
                return json.loads(self.mod_list_json)
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    @mod_list.setter
    def mod_list(self, value: Optional[List[dict]]):
        if value is None:
            self.mod_list_json = None
        else:
            self.mod_list_json = json.dumps(value, ensure_ascii=False)

    def __repr__(self):
        return f"<LocalModpack(id={self.id}, name={self.name}, pack_type={self.pack_type})>"
