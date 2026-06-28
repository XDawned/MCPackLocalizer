"""
Pydantic v2 数据模型：应用翻译相关请求/响应 Schema

定义应用翻译、备份记录、恢复操作等数据结构。
"""

from __future__ import annotations

from typing import Optional, List
from datetime import datetime

from pydantic import BaseModel, Field


# ==================== 应用翻译请求 ====================


class ApplyRequest(BaseModel):
    """应用翻译请求"""

    task_id: str = Field(..., description="翻译任务ID")


# ==================== 备份记录 ====================


class BackupRecordResponse(BaseModel):
    """备份记录响应"""

    id: int = Field(..., description="记录ID")
    modpack_version_id: Optional[int] = Field(default=None, description="整合包版本ID")
    backup_path: str = Field(..., description="备份路径")
    backed_files: List[str] = Field(default_factory=list, description="已备份文件列表")
    added_files: List[str] = Field(default_factory=list, description="新增文件列表")
    status: str = Field(..., description="备份状态")
    created_at: Optional[str] = Field(default=None, description="创建时间")


# ==================== 恢复操作 ====================


class RestoreResponse(BaseModel):
    """恢复操作响应"""

    restored_files: List[str] = Field(default_factory=list, description="已恢复文件列表")
    removed_files: List[str] = Field(default_factory=list, description="已移除文件列表")
