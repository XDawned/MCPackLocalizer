"""
Pydantic v2 数据模型：资源包/补丁交付相关 Schema
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ResourcePackConfig(BaseModel):
    """资源包生成配置"""

    pack_format: Optional[int] = Field(default=None, description="pack_format 版本，为空则自动检测")
    description: str = Field(default="MCPackLocalizer 汉化资源包", description="pack.mcmeta 描述")
    name: Optional[str] = Field(default=None, description="资源包名称，为空则自动生成")


class GenerateResourcePackResponse(BaseModel):
    """资源包生成响应"""

    resourcepack_id: str = Field(..., description="资源包生成记录 ID")
    download_url: str = Field(..., description="下载资源包的相对 API 路径")
    filename: str = Field(..., description="文件名")
    file_path: str = Field(..., description="本地文件绝对路径")
    file_size: int = Field(default=0, description="文件大小")
    pack_format: int = Field(default=0, description="实际使用的 pack_format")
    item_count: int = Field(default=0, description="包含的翻译条目数量")


class PatchPackageConfig(BaseModel):
    """补丁目录生成配置"""

    name: Optional[str] = Field(default=None, description="补丁目录名称，为空则自动生成")
    output_dir: Optional[str] = Field(default=None, description="补丁输出根目录，为空则使用后端设置/工作区默认目录")


class GeneratePatchPackageResponse(BaseModel):
    """补丁目录生成响应"""

    patch_id: str = Field(..., description="补丁生成记录 ID")
    patch_path: str = Field(..., description="补丁目录绝对路径")
    file_count: int = Field(default=0, description="实际写入文件数量")
    written_files: List[str] = Field(default_factory=list, description="写入补丁目录的相对路径列表")
    placeholder_directories: List[str] = Field(default_factory=list, description="预留但未写入内容的目录列表")
    skipped_resourcepack_targets: List[str] = Field(default_factory=list, description="当前阶段仅预留 resourcepacks 时跳过的资源包目标")
    resourcepacks_reserved_only: bool = Field(default=True, description="当前阶段 resourcepacks 是否仅做空目录预留")
    i18n_mod: dict = Field(default_factory=dict, description="I18nUpdateMod 解析/复用/下载结果")
