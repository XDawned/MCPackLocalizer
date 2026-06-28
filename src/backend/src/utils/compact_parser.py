"""
Category Parser — 双源分类解析器

解析 "CurseForgeID/ModrinthCategory" 格式的复合字符串，
将其拆分为 CurseForge 和 Modrinth 各自的查询参数。

支持三种格式:
  - 标准格式 (A/B): 拆分 '/'，A 为 CurseForge 整数 ID，B 为 Modrinth slug
  - CurseForge-Only (A/): 以 '/' 结尾，仅用于 CurseForge 筛选
  - Modrinth-Only (/B): 以 '/' 开头，仅用于 Modrinth 筛选
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedCompactPairs:
    """解析后的分类参数"""
    curseforge_id: Optional[int] = None
    modrinth_slug: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return self.curseforge_id is None and self.modrinth_slug is None


def parse_category(raw: Optional[str]) -> ParsedCompactPairs:
    """
    解析复合分类字符串。

    Args:
        raw: 原始字符串，格式为 "CF_ID/MR_slug"

    Returns:
        ParsedCompactPairs: 包含 curseforge_id 和 modrinth_slug

    Examples:
        >>> parse_category("423/technology")
        ParsedCompactPairs(curseforge_id=423, modrinth_slug='technology')

        >>> parse_category("423/")
        ParsedCompactPairs(curseforge_id=423, modrinth_slug=None)

        >>> parse_category("/adventure")
        ParsedCompactPairs(curseforge_id=None, modrinth_slug='adventure')

        >>> parse_category("")
        ParsedCompactPairs(curseforge_id=None, modrinth_slug=None)

        >>> parse_category(None)
        ParsedCompactPairs(curseforge_id=None, modrinth_slug=None)

        >>> parse_category("magic")
        ParsedCompactPairs(curseforge_id=None, modrinth_slug='magic')
    """
    if raw is None:
        return ParsedCompactPairs()

    raw = raw.strip()
    if not raw:
        return ParsedCompactPairs()

    if '/' in raw:
        parts = raw.split('/', 1)
        cf_part = parts[0].strip()
        mr_part = parts[1].strip()

        cf_id = _try_parse_int(cf_part) if cf_part else None

        return ParsedCompactPairs(
            curseforge_id=cf_id,
            modrinth_slug=mr_part if mr_part else None,
        )

    # Fallback: plain string — try integer first, otherwise treat as Modrinth slug
    cf_id = _try_parse_int(raw)
    if cf_id is not None:
        return ParsedCompactPairs(curseforge_id=cf_id, modrinth_slug=None)
    else:
        return ParsedCompactPairs(curseforge_id=None, modrinth_slug=raw)


def _try_parse_int(value: str) -> Optional[int]:
    """安全地将字符串解析为整数，失败返回 None。"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
