"""
搜索 API 路由

提供整合包搜索、详情查询、版本列表等端点。
"""

import logging
from typing import Optional

from fastapi import APIRouter

from ..schemas.search import (
    SearchRequest,
    SearchResponse,
    SearchResponseData,
    ModpackDetailSchema,
    VersionSchema,
    VersionDetailSchema,
    ModReferenceSchema,
    ApiResponse,
)
from ..services.search_service import search_modpacks as search_modpacks_svc
from ..adapters.curseforge import (
    get_modpack as curseforge_get_modpack,
    get_versions as curseforge_get_versions,
    get_version_detail as curseforge_get_version_detail,
)
from ..adapters.modrinth import (
    get_modpack as modrinth_get_modpack,
    get_versions as modrinth_get_versions,
    get_version_detail as modrinth_get_version_detail,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    搜索整合包（CurseForge + Modrinth 聚合）。

    请求体示例：
    ```json
    {
        "query": "SkyFactory",
        "offset": 0,
        "limit": 20,
        "sources": ["curseforge", "modrinth"]
    }
    ```
    """
    return await search_modpacks_svc(request)


@router.get("/modpacks/{platform}/{modpack_id}")
async def get_modpack_detail(platform: str, modpack_id: str):
    """
    获取整合包详情。

    - **platform**: curseforge 或 modrinth
    - **modpack_id**: 整合包的外部平台 ID
    """
    if platform == "curseforge":
        detail = await curseforge_get_modpack(modpack_id)
    elif platform == "modrinth":
        detail = await modrinth_get_modpack(modpack_id)
    else:
        return {"code": -1, "message": f"Unknown platform: {platform}"}

    if detail is None:
        return {"code": -1, "message": "Modpack not found"}

    return {
        "code": 0,
        "data": ModpackDetailSchema(
            platform=detail.get("platform", platform),
            id=detail.get("id", modpack_id),
            slug=detail.get("slug", ""),
            name=detail.get("name", ""),
            summary=detail.get("summary", ""),
            description=detail.get("description", ""),
            download_count=detail.get("download_count", 0),
            categories=detail.get("categories", []) or [],
            game_versions=detail.get("game_versions", []) or [],
            loaders=detail.get("loaders", []) or [],
            icon_url=detail.get("icon_url", ""),
            author=detail.get("author", ""),
            last_updated=detail.get("last_updated", ""),
        ).model_dump(),
    }


@router.get("/modpacks/{platform}/{modpack_id}/versions")
async def get_modpack_versions(platform: str, modpack_id: str):
    """
    获取整合包版本列表。

    - **platform**: curseforge 或 modrinth
    - **modpack_id**: 整合包的外部平台 ID
    """
    if platform == "curseforge":
        versions = await curseforge_get_versions(modpack_id)
    elif platform == "modrinth":
        versions = await modrinth_get_versions(modpack_id)
    else:
        return {"code": -1, "message": f"Unknown platform: {platform}"}

    result = []
    for v in versions:
        result.append(
            VersionSchema(
                id=v.get("id", ""),
                version_number=v.get("version_number", ""),
                mc_version=v.get("mc_version", ""),
                loader=v.get("loader", ""),
                download_url=v.get("download_url", ""),
                file_size=v.get("file_size"),
                game_versions=v.get("game_versions", []) or [],
                released_at=v.get("released_at", ""),
            ).model_dump()
        )

    return {"code": 0, "data": result}


@router.get("/modpacks/{platform}/{modpack_id}/versions/{version_id}")
async def get_version_detail(platform: str, modpack_id: str, version_id: str):
    """
    获取指定版本详情（含 Mod 清单）。

    - **platform**: curseforge 或 modrinth
    - **modpack_id**: 整合包的外部平台 ID
    - **version_id**: 版本 ID
    """
    if platform == "curseforge":
        detail = await curseforge_get_version_detail(modpack_id, version_id)
    elif platform == "modrinth":
        detail = await modrinth_get_version_detail(modpack_id, version_id)
    else:
        return {"code": -1, "message": f"Unknown platform: {platform}"}

    if detail is None:
        return {"code": -1, "message": "Version not found"}

    # 转换 Mod 清单
    mods = []
    for m in detail.get("mods", []) or []:
        mods.append(
            ModReferenceSchema(
                mod_external_id=m.get("mod_external_id", ""),
                name=m.get("name", ""),
                platform=m.get("platform", ""),
                download_url=m.get("download_url", ""),
                required=m.get("required", True),
            ).model_dump()
        )

    result = VersionDetailSchema(
        id=detail.get("id", version_id),
        version_number=detail.get("version_number", ""),
        mc_version=detail.get("mc_version", ""),
        loader=detail.get("loader", ""),
        download_url=detail.get("download_url", ""),
        file_size=detail.get("file_size"),
        game_versions=detail.get("game_versions", []) or [],
        released_at=detail.get("released_at", ""),
        mods=mods,
    ).model_dump()

    return {"code": 0, "data": result}
