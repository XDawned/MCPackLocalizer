"""
Pydantic v2 数据模型：搜索相关请求/响应 Schema

定义搜索请求、搜索结果、整合包详情、版本详情等数据结构。
"""

from __future__ import annotations

from typing import Optional, List
from datetime import datetime

from pydantic import BaseModel, Field


# ==================== 搜索请求 ====================


class SearchRequest(BaseModel):
    """搜索请求"""

    query: str = Field(default="", description="搜索关键词")
    type: str = Field(default="modpack", description="搜索类型")
    category: Optional[str] = Field(
        default=None,
        description=(
            "双源分类筛选 — 复合格式: 'CurseForgeID/ModrinthSlug'。"
            "后端解析器将 '/' 分隔的两侧分别传递给 CurseForge (整数 categoryId) 和 Modrinth (字符串 facets slug)。"
            "支持部分格式: 'ID/' 仅筛选 CurseForge; '/slug' 仅筛选 Modrinth。"
        ),
    )
    mod_loader: Optional[str] = Field(default=None, description="模组加载器筛选")
    game_version: Optional[str] = Field(default=None, description="游戏版本筛选")
    offset: int = Field(default=0, ge=0, description="偏移量")
    limit: int = Field(default=20, ge=1, le=100, description="每页数量")
    sources: List[str] = Field(
        default=["curseforge", "modrinth"],
        description="搜索来源：curseforge / modrinth",
    )


# ==================== 搜索结果 ====================


class ModpackResult(BaseModel):
    """整合包搜索结果"""

    platform: str = Field(..., description="平台：curseforge / modrinth")
    id: str = Field(..., description="外部平台 ID")
    slug: Optional[str] = Field(default=None, description="Slug 标识")
    name: str = Field(..., description="名称")
    summary: Optional[str] = Field(default=None, description="简介")
    download_count: int = Field(default=0, description="下载量")
    categories: List[str] = Field(default_factory=list, description="分类列表")
    game_versions: List[str] = Field(default_factory=list, description="支持的 MC 版本")
    loaders: List[str] = Field(default_factory=list, description="模组加载器")
    icon_url: Optional[str] = Field(default=None, description="图标 URL")
    author: Optional[str] = Field(default=None, description="作者")
    last_updated: Optional[str] = Field(default=None, description="最后更新时间（ISO 8601）")


class SearchResponseData(BaseModel):
    """搜索结果数据"""

    count: int = Field(..., description="数量")
    results: List[ModpackResult] = Field(default_factory=list, description="结果列表")


class SearchResponse(BaseModel):
    """搜索响应"""

    code: int = Field(default=0, description="状态码：0=成功，-1=失败")
    data: SearchResponseData = Field(..., description="响应数据")


# ==================== 整合包详情 ====================


class ModpackDetailSchema(BaseModel):
    """整合包详情"""

    platform: str = Field(..., description="平台")
    id: str = Field(..., description="外部平台 ID")
    slug: Optional[str] = Field(default=None, description="Slug")
    name: str = Field(..., description="名称")
    summary: Optional[str] = Field(default=None, description="简介")
    description: Optional[str] = Field(default=None, description="详细描述（HTML）")
    download_count: int = Field(default=0, description="下载量")
    categories: List[str] = Field(default_factory=list, description="分类")
    game_versions: List[str] = Field(default_factory=list, description="支持的 MC 版本")
    loaders: List[str] = Field(default_factory=list, description="模组加载器")
    icon_url: Optional[str] = Field(default=None, description="图标 URL")
    author: Optional[str] = Field(default=None, description="作者")
    last_updated: Optional[str] = Field(default=None, description="最后更新时间")
    versions: Optional[List[VersionSchema]] = Field(default=None, description="版本列表")


# ==================== 版本详情 ====================


class VersionSchema(BaseModel):
    """整合包版本"""

    id: str = Field(..., description="版本 ID")
    version_number: str = Field(..., description="版本号")
    mc_version: Optional[str] = Field(default=None, description="MC 版本")
    loader: Optional[str] = Field(default=None, description="模组加载器")
    download_url: Optional[str] = Field(default=None, description="下载链接")
    file_size: Optional[int] = Field(default=None, description="文件大小")
    game_versions: List[str] = Field(default_factory=list, description="支持的 MC 版本列表")
    released_at: Optional[str] = Field(default=None, description="发布日期（ISO 8601）")


class ModReferenceSchema(BaseModel):
    """Mod 引用"""

    mod_external_id: str = Field(..., description="Mod 外部 ID")
    name: Optional[str] = Field(default=None, description="Mod 名称")
    platform: Optional[str] = Field(default=None, description="平台")
    download_url: Optional[str] = Field(default=None, description="下载链接")
    file_size: Optional[int] = Field(default=None, description="文件大小（字节）")
    hash: Optional[str] = Field(default=None, description="文件哈希值")
    required: bool = Field(default=True, description="是否必须")


class VersionDetailSchema(VersionSchema):
    """版本详情（含 Mod 清单）"""

    mods: List[ModReferenceSchema] = Field(default_factory=list, description="Mod 清单")


# ==================== 通用响应包装 ====================


class ApiResponse(BaseModel):
    """通用 API 响应"""

    code: int = Field(default=0, description="状态码")
    message: Optional[str] = Field(default=None, description="消息（错误时使用）")
    data: Optional[object] = Field(default=None, description="响应数据")
