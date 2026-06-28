"""
Pydantic v2 数据模型：术语库相关请求/响应 Schema

定义术语条目创建、更新、导入等数据结构。
"""

from __future__ import annotations

from typing import Optional, List
from datetime import datetime

from pydantic import BaseModel, Field


# ==================== 术语条目创建 ====================


class GlossaryEntryCreate(BaseModel):
    """术语条目创建请求"""

    source_term: str = Field(..., description="源术语")
    target_term: str = Field(..., description="目标术语")
    category: Optional[str] = Field(default=None, description="分类")
    source: str = Field(default="manual", description="来源: manual / cfpa")
    is_regex: bool = Field(default=False, description="是否正则表达式")


# ==================== 术语条目更新 ====================


class GlossaryEntryUpdate(BaseModel):
    """术语条目更新请求"""

    source_term: Optional[str] = Field(default=None, description="源术语")
    target_term: Optional[str] = Field(default=None, description="目标术语")
    category: Optional[str] = Field(default=None, description="分类")
    is_regex: Optional[bool] = Field(default=None, description="是否正则表达式")


# ==================== 术语条目响应 ====================


class GlossaryEntryResponse(BaseModel):
    """术语条目响应"""

    id: int = Field(..., description="条目ID")
    source_term: str = Field(..., description="源术语")
    target_term: str = Field(..., description="目标术语")
    category: Optional[str] = Field(default=None, description="分类")
    source: str = Field(..., description="来源")
    is_regex: bool = Field(..., description="是否正则表达式")
    created_at: Optional[str] = Field(default=None, description="创建时间")


# ==================== 术语库导入 ====================


class GlossaryImportRequest(BaseModel):
    """CFPA术语库导入请求"""

    url: Optional[str] = Field(default=None, description="CFPA术语库URL")
    file_content: Optional[str] = Field(default=None, description="直接上传的文件内容")
