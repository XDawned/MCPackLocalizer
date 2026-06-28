"""
Modrinth API 适配器

封装 Modrinth API v2（https://api.modrinth.com/v2），提供整合包搜索和详情查询。
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

# Modrinth API 基础地址
# MR_BASE_URL = "https://api.modrinth.com/v2"
MR_BASE_URL = "https://mod.mcimirror.top/modrinth/v2"


def _get_headers() -> dict:
    """构建请求头"""
    headers = {
        "Accept": "application/json",
        "User-Agent": "MCPackLocalizer/2.0",
    }
    if settings.MODRINTH_API_KEY:
        headers["Authorization"] = settings.MODRINTH_API_KEY
    return headers


def _build_facets(
    game_version: Optional[str] = None,
    category: Optional[str] = None,
    mod_loader: Optional[str] = None,
    category_slug: Optional[str] = None,
) -> Optional[str]:
    """
    构建 Modrinth facets 查询参数。

    Facets 格式为 JSON 二维数组：
      内层数组 = OR 关系，外层数组 = AND 关系。
    例如: [["project_type:modpack"], ["versions:1.20.1"], ["categories:forge"]]

    Args:
        category_slug: 优先使用的分类 slug（来自 ParsedCategory）
        category: 兼容旧格式的回退参数
    """
    facets: list[list[str]] = []

    # 限定 project_type 为 modpack
    facets.append(["project_type:modpack"])

    if game_version:
        facets.append([f"versions:{game_version}"])

    cat = category_slug if category_slug else category
    if cat:
        facets.append([f"categories:{cat}"])

    if mod_loader:
        facets.append([f"categories:{mod_loader}"])

    import json
    return json.dumps(facets)


def _normalize_result(item: dict) -> dict:
    """
    将 Modrinth API 返回的项目数据转换为标准化格式。
    """
    # 提取分类名称
    categories = item.get("categories", []) or []

    # 提取加载器（Modrinth 中加载器混在 categories 中）
    known_loaders = {"forge", "fabric", "quilt", "neoforge", "liteloader", "rift"}
    loaders = [c for c in categories if c.lower() in known_loaders]
    # 从 categories 中移除加载器
    pure_categories = [c for c in categories if c.lower() not in known_loaders]

    # 提取发布日期
    release_date = item.get("date_released", item.get("published", ""))

    return {
        "platform": "modrinth",
        "id": item.get("project_id", item.get("id", "")),
        "slug": item.get("slug", ""),
        "name": item.get("title", ""),
        "summary": item.get("description", ""),
        "download_count": item.get("downloads", 0),
        "categories": pure_categories,
        "game_versions": item.get("versions", []) or [],
        "loaders": loaders,
        "icon_url": item.get("icon_url", ""),
        "author": item.get("author", ""),
        "last_updated": item.get("updated", item.get("date_modified", "")),
        "release_date": release_date,
    }


def _normalize_version(item: dict) -> dict:
    """标准化版本数据"""
    # 提取 MC 版本（game_versions 中通常第一个是 MC 版本）
    game_versions = item.get("game_versions", []) or []
    mc_version = ""
    loaders = item.get("loaders", []) or []

    for v in game_versions:
        if v.count(".") >= 2 or (v.count(".") >= 1 and len(v.split(".")[0]) <= 2):
            mc_version = v
            break

    # 提取下载链接
    files = item.get("files", []) or []
    download_url = ""
    file_size = 0
    if files:
        primary = files[0]
        download_url = primary.get("url", "")
        file_size = primary.get("size", 0)

    # 提取哈希值
    hash_value = ""
    if files:
        hashes = files[0].get("hashes", {}) or {}
        hash_value = hashes.get("sha1", hashes.get("sha512", ""))

    # 提取发布日期
    released_at = item.get("date_published", "")

    return {
        "id": item.get("id", ""),
        "version_number": item.get("version_number", item.get("name", "")),
        "mc_version": mc_version,
        "loader": loaders[0] if loaders else "",
        "download_url": download_url,
        "file_size": file_size,
        "game_versions": game_versions,
        "released_at": released_at,
        "hash": hash_value,
    }


async def search_modpacks(
    query: str = "",
    offset: int = 0,
    limit: int = 20,
    game_version: Optional[str] = None,
    category: Optional[str] = None,
    mod_loader: Optional[str] = None,
    category_slug: Optional[str] = None,
) -> list[dict]:
    """
    搜索 Modrinth ModPack。

    Args:
        query: 搜索关键词
        offset: 分页偏移
        limit: 每页数量
        game_version: 游戏版本筛选
        category: 分类筛选（兼容旧格式；优先使用 category_slug）
        mod_loader: 模组加载器筛选
        category_slug: 分类筛选 slug（优先级高于 category）

    Returns:
        标准化 dict 列表
    """
    url = f"{MR_BASE_URL}/search"

    facets = _build_facets(
        game_version=game_version,
        category=category,
        mod_loader=mod_loader,
        category_slug=category_slug,
    )

    params: dict = {
        "query": query,
        "offset": offset,
        "limit": limit,
    }
    if facets:
        params["facets"] = facets

    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
            response = await client.get(url, params=params, headers=_get_headers())
            response.raise_for_status()
            data = response.json()

            items = data.get("hits", [])
            logger.info(
                "Modrinth search: query=%r, total_hits=%d, returned=%d",
                query,
                data.get("total_hits", 0),
                len(items),
            )

            return [_normalize_result(item) for item in items]
    except httpx.HTTPStatusError as e:
        logger.error("Modrinth search HTTP error: %s", e)
        return []
    except httpx.RequestError as e:
        logger.error("Modrinth search request error: %s", e)
        return []
    except Exception as e:
        logger.exception("Modrinth search unexpected error: %s", e)
        return []


async def get_modpack(project_id: str) -> Optional[dict]:
    """
    获取 Modrinth 整合包详情。

    Args:
        project_id: 项目 ID 或 slug

    Returns:
        标准化 dict，失败返回 None
    """
    url = f"{MR_BASE_URL}/project/{project_id}"

    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
            response = await client.get(url, headers=_get_headers())
            response.raise_for_status()
            item = response.json()
            if not item:
                return None

            result = _normalize_result(item)
            # 追加详细描述
            result["description"] = item.get("body", "")  # Modrinth 用 body 存长描述
            return result
    except httpx.HTTPStatusError as e:
        logger.error("Modrinth get_modpack HTTP error: %s", e)
        return None
    except httpx.RequestError as e:
        logger.error("Modrinth get_modpack request error: %s", e)
        return None
    except Exception as e:
        logger.exception("Modrinth get_modpack unexpected error: %s", e)
        return None


async def get_versions(project_id: str) -> list[dict]:
    """
    获取 Modrinth 整合包版本列表。

    Args:
        project_id: 项目 ID 或 slug

    Returns:
        标准化版本列表
    """
    url = f"{MR_BASE_URL}/project/{project_id}/version"

    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
            response = await client.get(url, headers=_get_headers())
            response.raise_for_status()
            items = response.json()
            if not isinstance(items, list):
                items = []
            return [_normalize_version(item) for item in items]
    except httpx.HTTPStatusError as e:
        logger.error("Modrinth get_versions HTTP error: %s", e)
        return []
    except httpx.RequestError as e:
        logger.error("Modrinth get_versions request error: %s", e)
        return []
    except Exception as e:
        logger.exception("Modrinth get_versions unexpected error: %s", e)
        return []


async def get_version_detail(project_id: str, version_id: str) -> Optional[dict]:
    """
    获取 Modrinth 整合包指定版本详情（含依赖 Mod 清单）。

    Args:
        project_id: 项目 ID（保留以保持接口一致，Modrinth API 实际不需要此参数）
        version_id: 版本 ID

    Returns:
        标准化版本详情 dict，失败返回 None
    """
    url = f"{MR_BASE_URL}/version/{version_id}"

    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
            response = await client.get(url, headers=_get_headers())
            response.raise_for_status()
            item = response.json()
            if not item:
                return None

            result = _normalize_version(item)

            # 提取依赖 Mod 清单
            mods_list = []
            dependencies = item.get("dependencies", []) or []
            for dep in dependencies:
                # Modrinth 依赖格式: { version_id, project_id, file_name, dependency_type }
                dep_type = dep.get("dependency_type", "")
                mods_list.append({
                    "mod_external_id": dep.get("project_id", ""),
                    "name": dep.get("file_name", ""),
                    "platform": "modrinth",
                    "download_url": "",
                    "required": dep_type == "required",
                })

            result["mods"] = mods_list
            return result
    except httpx.HTTPStatusError as e:
        logger.error("Modrinth get_version_detail HTTP error: %s", e)
        return None
    except httpx.RequestError as e:
        logger.error("Modrinth get_version_detail request error: %s", e)
        return None
    except Exception as e:
        logger.exception("Modrinth get_version_detail unexpected error: %s", e)
        return None
