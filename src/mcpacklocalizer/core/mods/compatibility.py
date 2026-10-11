# [Module: core.mods.compatibility] [Status: 已完成] [Brief: 模组语言资源的特定兼容适配]
"""读取可编辑的模组语言适配配置，按命名空间、语言键和格式应用正则替换。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ...paths import editable_resource_path

RULES_RESOURCE = "compatibility/mod_language_rules.json"


@dataclass(frozen=True)
class Replacement:
    pattern: re.Pattern[str]
    replacement: str
    count: int


@dataclass(frozen=True)
class LanguageRule:
    id: str
    description: str
    namespace: re.Pattern[str]
    key: re.Pattern[str]
    language_format: str
    replacements: tuple[Replacement, ...]


def _text(record, field):
    value = record.get(field)
    if not isinstance(value, str):
        raise TypeError(f"{field} 必须是字符串")
    return value


def load_rules(path: Path | None = None) -> tuple[LanguageRule, ...]:
    """每次导出重新读取并校验规则；错误配置包含文件路径和规则位置。"""
    path = path if path is not None else editable_resource_path(RULES_RESOURCE)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"无法读取模组兼容配置：{path}；{exc}") from exc
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError(f"模组兼容配置 schema_version 必须为 1：{path}")
    if not isinstance(data.get("rules"), list):
        raise ValueError(f"模组兼容配置 rules 必须是数组：{path}")  # noqa: TRY004 - 外部配置错误统一按校验失败返回。
    rules, identities = [], set()
    for index, record in enumerate(data["rules"], 1):
        try:
            if not isinstance(record, dict):
                raise TypeError("规则必须是对象")
            identity = _text(record, "id")
            if not identity.strip() or identity in identities:
                raise ValueError("规则 id 不能为空或重复")
            identities.add(identity)
            enabled = record.get("enabled", True)
            if not isinstance(enabled, bool):
                raise TypeError("enabled 必须是布尔值")
            if not enabled:
                continue
            description = record.get("description", identity)
            if not isinstance(description, str):
                raise TypeError("description 必须是字符串")
            language_format = record.get("language_format", "any")
            if language_format not in ("any", "lang", "json"):
                raise ValueError("language_format 必须为 any、lang 或 json")
            namespace = re.compile(_text(record, "namespace"))
            key = re.compile(_text(record, "key"))
            substitutions = record.get("replacements")
            if not isinstance(substitutions, list) or not substitutions:
                raise ValueError("replacements 必须是非空数组")
            replacements = []
            for substitution in substitutions:
                if not isinstance(substitution, dict):
                    raise TypeError("替换规则必须是对象")
                pattern = re.compile(_text(substitution, "pattern"))
                replacement = _text(substitution, "replacement")
                count = substitution.get("count", 0)
                if type(count) is not int or count < 0:
                    raise ValueError("count 必须是非负整数，0 表示替换全部匹配")
                # 提前校验替换字符串中的分组引用，避免只在特定条目上才报错。
                pattern.sub(replacement, "", count=count)
                replacements.append(Replacement(pattern, replacement, count))
            rules.append(LanguageRule(identity, description, namespace, key, language_format, tuple(replacements)))
        except (ValueError, TypeError, re.error, IndexError) as exc:
            raise ValueError(f"模组兼容配置无效：{path}；第 {index} 条规则；{exc}") from exc
    return tuple(rules)


def apply_language_rules(namespace: str, key: str, value: str, *, legacy: bool,
                         rules: tuple[LanguageRule, ...]) -> tuple[str, tuple[LanguageRule, ...]]:
    """按配置顺序应用规则，并返回实际改变文本的规则以供导出报告记录。"""
    language_format = "lang" if legacy else "json"
    applied = []
    for rule in rules:
        if (rule.language_format not in ("any", language_format)
                or rule.namespace.fullmatch(namespace) is None or rule.key.fullmatch(key) is None):
            continue
        previous = value
        for replacement in rule.replacements:
            value = replacement.pattern.sub(replacement.replacement, value, count=replacement.count)
        if value != previous:
            applied.append(rule)
    return value, tuple(applied)


def export_language_value(namespace: str, key: str, value: str, *, legacy: bool,
                          rules: tuple[LanguageRule, ...] | None = None) -> str:
    """应用匹配的语言值导出适配，保留任务和共享译库中的原始译文。"""
    return apply_language_rules(namespace, key, value, legacy=legacy,
                                rules=load_rules() if rules is None else rules)[0]
