"""
CurseForge API 适配器

封装 CurseForge Core API（https://api.curseforge.com），提供整合包搜索和详情查询。
所有方法返回标准化的 dict 列表。
"""

import logging
from typing import Optional

import httpx

try:
    from ..config import settings
except ImportError:
    from src.config import settings  # type: ignore

logger = logging.getLogger(__name__)

# CurseForge API 基础地址
# CF_BASE_URL = "https://api.curseforge.com"
CF_BASE_URL = "https://mod.mcimirror.top/curseforge"

# ModPack 的 classId
MODPACK_CLASS_ID = 4471


def _get_headers() -> dict:
    """构建请求头"""
    return {
        "x-api-key": settings.CURSEFORGE_API_KEY,
        "Accept": "application/json",
    }


def _normalize_result(item: dict) -> dict:
    """
    将 CurseForge API 返回的 mod 数据转换为标准化格式。
    """
    # 提取分类名称
    categories = []
    if "categories" in item and item["categories"]:
        categories = [c.get("name", "") for c in item["categories"]]

    # 提取支持的游戏版本
    game_versions = []
    if "latestFiles" in item and item["latestFiles"]:
        for f in item["latestFiles"]:
            if "gameVersions" in f:
                game_versions.extend(f["gameVersions"])
        game_versions = list(set(game_versions))

    # 提取加载器
    loaders = []
    if "latestFiles" in item and item["latestFiles"]:
        for f in item["latestFiles"]:
            if "modLoader" in f and f["modLoader"]:
                loaders.append(f["modLoader"])
        loaders = list(set(loaders))

    # 提取发布日期
    release_date = ""
    if "dateReleased" in item:
        release_date = item["dateReleased"]
    elif "latestFiles" in item and item["latestFiles"]:
        release_date = item["latestFiles"][0].get("fileDate", "")

    return {
        "platform": "curseforge",
        "id": str(item.get("id", "")),
        "slug": item.get("slug", ""),
        "name": item.get("name", ""),
        "summary": item.get("summary", ""),
        "download_count": item.get("downloadCount", 0),
        "categories": categories,
        "game_versions": game_versions,
        "loaders": loaders,
        "icon_url": item.get("logo", {}).get("url", "") if item.get("logo") else "",
        "author": item.get("authors", [{}])[0].get("name", "") if item.get("authors") else "",
        "last_updated": item.get("dateModified", ""),
        "release_date": release_date,
    }


def _normalize_version(item: dict) -> dict:
    """标准化版本数据"""
    # 提取哈希值
    hash_value = ""
    hashes_list = item.get("hashes", []) or []
    for h in hashes_list:
        if h.get("algo", 0) == 1:  # 1 = SHA-1
            hash_value = h.get("value", "")
            break
    if not hash_value:
        # 备用：从 fileFingerprint 获取
        hash_value = str(item.get("fileFingerprint", "")) if item.get("fileFingerprint") else ""

    return {
        "id": str(item.get("id", "")),
        "version_number": item.get("displayName", item.get("name", "")),
        "mc_version": "",
        "loader": item.get("gameVersionTypeName", ""),
        "download_url": item.get("downloadUrl", ""),
        "file_size": item.get("fileLength", 0),
        "game_versions": item.get("gameVersions", []) or [],
        "released_at": item.get("fileDate", ""),
        "hash": hash_value,
    }


async def search_modpacks(
    query: str = "",
    offset: int = 0,
    limit: int = 20,
    game_version: Optional[str] = None,
    mod_loader: Optional[str] = None,
    category_id: Optional[int] = None,
) -> list[dict]:
    """
    搜索 CurseForge ModPack。

    Args:
        query: 搜索关键词
        offset: 分页偏移
        limit: 每页数量
        game_version: 游戏版本筛选
        mod_loader: 模组加载器筛选
        category_id: 分类筛选 (整数 categoryId，优先级高于 category)

    Returns:
        标准化 dict 列表
    """
    url = f"{CF_BASE_URL}/v1/mods/search"
    params: dict = {
        "gameId": 432,  # Minecraft
        "classId": MODPACK_CLASS_ID,
        "searchFilter": query,
        "index": offset,
        "pageSize": limit,
        "sortField": 2,  # Popularity
        "sortOrder": "desc",
    }

    if game_version:
        params["gameVersion"] = game_version

    cf_cat_id: Optional[int] = category_id
    if cf_cat_id is not None:
        params["categoryId"] = cf_cat_id

    if mod_loader:
        params["modLoaderType"] = mod_loader

    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
            response = await client.get(url, params=params, headers=_get_headers())
            response.raise_for_status()
            data = response.json()
            items = data.get("data", [])
            logger.info(
                "CurseForge search: query=%r, returned %d results, total %d results",
                query,
                len(items),
                data.get('pagination', {}).get('totalCount', 0),
            )
            return [_normalize_result(item) for item in items]
    except httpx.HTTPStatusError as e:
        logger.error("CurseForge search HTTP error: %s", e)
        return []
    except httpx.RequestError as e:
        logger.error("CurseForge search request error: %s", e)
        return []
    except Exception as e:
        logger.exception("CurseForge search unexpected error: %s", e)
        return []


async def get_modpack(mod_id: str | int) -> Optional[dict]:
    """
    获取 CurseForge 整合包详情。

    Args:
        mod_id: Mod ID

    Returns:
        标准化 dict，失败返回 None
    """
    url = f"{CF_BASE_URL}/v1/mods/{mod_id}"

    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
            response = await client.get(url, headers=_get_headers())
            response.raise_for_status()
            data = response.json()
            item = data.get("data", {})
            if not item:
                return None
            result = _normalize_result(item)
            # 追加详细描述
            result["description"] = item.get("description", "")
            return result
    except httpx.HTTPStatusError as e:
        logger.error("CurseForge get_modpack HTTP error: %s", e)
        return None
    except httpx.RequestError as e:
        logger.error("CurseForge get_modpack request error: %s", e)
        return None
    except Exception as e:
        logger.exception("CurseForge get_modpack unexpected error: %s", e)
        return None


async def get_versions(mod_id: str | int) -> list[dict]:
    """
    获取 CurseForge 整合包版本列表。

    Args:
        mod_id: Mod ID

    Returns:
        标准化版本列表
    """
    url = f"{CF_BASE_URL}/v1/mods/{mod_id}/files"

    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
            response = await client.get(url, headers=_get_headers())
            response.raise_for_status()
            data = response.json()
            items = data.get("data", [])
            return [_normalize_version(item) for item in items]
    except httpx.HTTPStatusError as e:
        logger.error("CurseForge get_versions HTTP error: %s", e)
        return []
    except httpx.RequestError as e:
        logger.error("CurseForge get_versions request error: %s", e)
        return []
    except Exception as e:
        logger.exception("CurseForge get_versions unexpected error: %s", e)
        return []


async def get_version_detail(mod_id: str | int, version_id: str | int) -> Optional[dict]:
    """
    获取 CurseForge 整合包指定版本详情（含依赖 Mod 清单）。

    Args:
        mod_id: Mod ID
        version_id: 文件/版本 ID

    Returns:
        标准化版本详情 dict，失败返回 None
    """
    url = f"{CF_BASE_URL}/v1/mods/{mod_id}/files/{version_id}"

    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
            response = await client.get(url, headers=_get_headers())
            response.raise_for_status()
            data = response.json()
            item = data.get("data", {})
            if not item:
                return None

            result = _normalize_version(item)

            # 提取依赖 Mod 清单
            mods = []
            dependencies = item.get("dependencies", []) or []
            for dep in dependencies:
                mods.append({
                    "mod_external_id": str(dep.get("modId", "")),
                    "name": dep.get("modName", ""),
                    "platform": "curseforge",
                    "download_url": "",
                    "required": dep.get("relationType", 0) == 3,  # 3 = RequiredDependency
                })

            result["mods"] = mods
            return result
    except httpx.HTTPStatusError as e:
        logger.error("CurseForge get_version_detail HTTP error: %s", e)
        return None
    except httpx.RequestError as e:
        logger.error("CurseForge get_version_detail request error: %s", e)
        return None
    except Exception as e:
        logger.exception("CurseForge get_version_detail unexpected error: %s", e)
        return None
