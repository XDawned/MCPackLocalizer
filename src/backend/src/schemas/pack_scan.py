"""
Pydantic v2 数据模型：本地整合包扫描相关请求/响应 Schema
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class PackScanRequest(BaseModel):
    """本地整合包扫描请求"""

    local_path: str = Field(..., description="本地整合包目录绝对路径")
    platform: Optional[str] = Field(default=None, description="手动指定平台类型")
    game_name: Optional[str] = Field(default=None, description="用户选择的游戏实例名称")


class PackDiscoverRequest(BaseModel):
    """本地整合包候选发现请求"""

    local_path: str = Field(..., description="本地整合包目录绝对路径")
    platform: Optional[str] = Field(default=None, description="手动指定平台类型")


class VersionCandidate(BaseModel):
    """版本候选信息"""

    game_name: str = Field(..., description=".minecraft/versions 下的二级目录名称")
    version_root: str = Field(..., description="候选版本目录绝对路径")
    mc_version: str = Field(default="", description="解析得到的 Minecraft 版本")
    source_field: Optional[Literal["inheritsFrom", "clientVersion"]] = Field(
        default=None,
        description="版本来源字段",
    )
    has_version_work_root: bool = Field(default=False, description="版本目录下是否存在 mods/config/kubejs")
    version_work_root: Optional[str] = Field(default=None, description="版本层工作根目录")
    fallback_minecraft_root_usable: bool = Field(default=False, description=".minecraft 根是否可作为回退工作根")
    loader: Optional[str] = Field(default=None, description="识别到的加载器类型，如 forge/neoforge/fabric/quilt")
    loader_version: Optional[str] = Field(default=None, description="识别到的加载器版本")
    version_json_path: Optional[str] = Field(default=None, description="对应版本 json 的绝对路径")


class ScanArea(BaseModel):
    """待翻译区域"""

    type: str = Field(..., description="区域类型: mod_lang/ftb_quests/ftbquests_lang/better_questing/kubejs_json/kubejs_lang/kubejs_js")
    label: str = Field(..., description="区域显示标签")
    count: int = Field(default=0, description="文件/条目数量")
    items: List[dict] = Field(default_factory=list, description="子项目详情列表，含 entry_count/target_strategy/target_path 等信息")


class DiscoverResultData(BaseModel):
    """候选发现结果数据"""

    input_path: str = Field(..., description="用户输入路径")
    minecraft_root: str = Field(..., description="解析得到的 .minecraft 或普通整合包根目录")
    pack_type: str = Field(..., description="整合包类型")
    candidates: List[VersionCandidate] = Field(default_factory=list, description="版本候选列表")
    has_versions_structure: bool = Field(default=False, description="是否检测到 versions 结构")
    fallback_minecraft_root_usable: bool = Field(default=False, description="根目录是否可直接作为工作根")
    direct_scan_compatible: bool = Field(default=False, description="是否兼容旧版直接扫描流程")
    recommended_action: str = Field(default="scan_direct", description="推荐动作：select_game_name 或 scan_direct")


class ScanResultData(BaseModel):
    """扫描结果数据"""

    scan_id: str = Field(..., description="扫描ID")
    pack_type: str = Field(..., description="整合包类型")
    mc_version: str = Field(default="", description="MC 版本")
    loader: Optional[str] = Field(default=None, description="识别到的加载器类型")
    loader_version: Optional[str] = Field(default=None, description="识别到的加载器版本")
    name: str = Field(default="", description="整合包名称")
    game_name: Optional[str] = Field(default=None, description="选中的游戏实例名称")
    mod_count: int = Field(default=0, description="Mod 个数")
    minecraft_root: str = Field(..., description="解析得到的 .minecraft 或普通整合包根目录")
    selected_version_root: Optional[str] = Field(default=None, description="选中的版本目录绝对路径")
    version_json_path: Optional[str] = Field(default=None, description="用于识别版本/加载器的 version json 绝对路径")
    work_root: str = Field(..., description="任务/脚本扫描工作根目录")
    work_root_source: Literal["version", "minecraft_root"] = Field(..., description="工作根来源")
    version_resolution_source: Optional[Literal["inheritsFrom", "clientVersion", "legacy"]] = Field(
        default=None,
        description="MC 版本解析来源",
    )
    real_path: str = Field(..., description="兼容旧字段，等同于 work_root")
    areas: List[ScanArea] = Field(default_factory=list, description="待翻译区域列表")


class ScanStatusData(BaseModel):
    """扫描状态响应"""

    scan_id: str = Field(..., description="扫描ID")
    status: str = Field(..., description="状态: scanning/completed/failed")
    pack_type: Optional[str] = Field(default=None)
    mc_version: Optional[str] = Field(default=None)
    name: Optional[str] = Field(default=None)
    progress: float = Field(default=0.0, description="进度 0-100")
    error: Optional[str] = Field(default=None)


class ExtractRequest(BaseModel):
    """提取待翻译内容请求"""

    selected_areas: Optional[List[str]] = Field(default=None, description="要提取的区域类型列表，为空则全部提取")
