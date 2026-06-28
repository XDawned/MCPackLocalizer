"""
搜索聚合服务

并发调用 CurseForge 和 Modrinth adapter，实现去重、排序和分页。
"""

import asyncio
import logging
from difflib import SequenceMatcher

from ..adapters.curseforge import search_modpacks as curseforge_search
from ..adapters.modrinth import search_modpacks as modrinth_search
from ..config import settings
from ..schemas.search import (
    SearchRequest,
    SearchResponse,
    SearchResponseData,
    ModpackResult,
)
from ..utils.compact_parser import parse_category

logger = logging.getLogger(__name__)


def _name_similarity(a: str, b: str) -> float:
    """
    计算两个名称的相似度（0.0 ~ 1.0）。

    使用 difflib.SequenceMatcher。
    """
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _deduplicate(results: list[dict]) -> list[dict]:
    """
    基于 slug + 名称相似度去重。

    规则：
      1. slug 完全相同 → 视为重复，保留下载量更高的
      2. 名称相似度 > 80% → 视为重复，保留下载量更高的

    Args:
        results: 标准化 dict 列表

    Returns:
        去重后的结果列表
    """
    if not results:
        return []

    unique: list[dict] = []
    for item in results:
        is_dup = False
        item_slug = item.get("slug", "").lower()
        item_name = item.get("name", "").lower()

        for i, existing in enumerate(unique):
            existing_slug = existing.get("slug", "").lower()
            existing_name = existing.get("name", "").lower()

            # 规则1: slug 完全相同
            if item_slug and existing_slug and item_slug == existing_slug:
                is_dup = True
                # 保留下载量更高的
                if item.get("download_count", 0) > existing.get("download_count", 0):
                    unique[i] = item
                break

            # 规则2: 名称相似度 > 80%
            similarity = _name_similarity(item_name, existing_name)
            if similarity >= settings.DEDUP_SIMILARITY_THRESHOLD:
                is_dup = True
                if item.get("download_count", 0) > existing.get("download_count", 0):
                    unique[i] = item
                break

        if not is_dup:
            unique.append(item)

    return unique


def _score_item(item: dict) -> float:
    """
    为搜索结果计算综合评分。

    公式：下载量 × 平台权重

    Args:
        item: 标准化 dict

    Returns:
        综合评分
    """
    platform = item.get("platform", "")
    weight = settings.PLATFORM_WEIGHTS.get(platform, 1.0)
    downloads = item.get("download_count", 0)

    # 归一化下载量（取对数避免极大值主导排序）
    import math
    normalized = math.log1p(downloads)  # log(1 + downloads)

    return normalized * weight


async def search_modpacks(request: SearchRequest) -> SearchResponse:
    """
    聚合搜索入口。

    并发调用 CurseForge 和/或 Modrinth adapter，然后去重、排序、分页。

    对 request.category 执行双源解析（"CF_ID/MR_slug" 格式），
    将解析后的 curseforge_id 传递给 CurseForge adapter，
    将 modrinth_slug 传递给 Modrinth adapter，防止参数交叉污染。

    Args:
        request: 搜索请求

    Returns:
        SearchResponse
    """
    # 解析复合分类字符串
    parsed_cat = parse_category(request.category)
    parsed_loader = parse_category(request.mod_loader)
    print(parsed_cat)
    tasks = {}

    if "curseforge" in request.sources:
        if parsed_cat.is_empty or parsed_cat.curseforge_id:
            tasks["curseforge"] = curseforge_search(
                query=request.query,
                offset=request.offset,
                limit=request.limit,
                game_version=request.game_version,
                mod_loader=parsed_loader.curseforge_id,
                category_id=parsed_cat.curseforge_id,
            )

    if "modrinth" in request.sources:
        if parsed_cat.is_empty or parsed_cat.modrinth_slug:
            tasks["modrinth"] = modrinth_search(
                query=request.query,
                offset=request.offset,
                limit=request.limit,
                game_version=request.game_version,
                mod_loader=parsed_loader.modrinth_slug,
                category_slug=parsed_cat.modrinth_slug,
            )

    if not tasks:
        return SearchResponse(
            code=0,
            data=SearchResponseData(total=0, results=[]),
        )

    # 并发执行
    try:
        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
    except Exception as e:
        logger.exception("Search aggregation error: %s", e)
        return SearchResponse(
            code=-1,
            message=str(e),
            data=SearchResponseData(total=0, results=[]),
        )

    # 合并结果
    all_results: list[dict] = []
    for idx, result in enumerate(gathered):
        if isinstance(result, Exception):
            logger.error("Search source '%s' failed: %s", list(tasks.keys())[idx], result)
            continue
        if isinstance(result, list):
            all_results.extend(result)

    # 去重
    unique_results = _deduplicate(all_results)

    # 排序：按评分降序
    unique_results.sort(key=_score_item, reverse=True)

    count = len(unique_results)

    # 转换为 ModpackResult schema
    modpack_results = []
    for item in unique_results:
        try:
            modpack_result = ModpackResult(
                platform=item.get("platform", ""),
                id=item.get("id", ""),
                slug=item.get("slug", ""),
                name=item.get("name", ""),
                summary=item.get("summary", ""),
                download_count=item.get("download_count", 0),
                categories=item.get("categories", []) or [],
                game_versions=item.get("game_versions", []) or [],
                loaders=item.get("loaders", []) or [],
                icon_url=item.get("icon_url", ""),
                author=item.get("author", ""),
                last_updated=item.get("last_updated", ""),
            )
            modpack_results.append(modpack_result)
        except Exception as e:
            logger.error("Failed to convert search result: %s", e)

    return SearchResponse(
        code=0,
        data=SearchResponseData(
            count=count,
            results=modpack_results,
        ),
    )
