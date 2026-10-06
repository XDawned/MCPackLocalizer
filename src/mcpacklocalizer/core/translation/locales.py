"""Minecraft locale codes shared by settings, prompts and task validation."""
import re

LANGUAGES = (
    ("en_us", "英语（美国）", "English"), ("en_gb", "英语（英国）", "British English"),
    ("zh_cn", "简体中文", "Simplified Chinese"), ("zh_tw", "繁体中文", "Traditional Chinese"),
    ("ja_jp", "日语", "Japanese"), ("ko_kr", "韩语", "Korean"),
    ("de_de", "德语", "German"), ("fr_fr", "法语", "French"),
    ("es_es", "西班牙语", "Spanish"), ("pt_br", "葡萄牙语（巴西）", "Brazilian Portuguese"),
    ("ru_ru", "俄语", "Russian"), ("uk_ua", "乌克兰语", "Ukrainian"),
    ("it_it", "意大利语", "Italian"), ("pl_pl", "波兰语", "Polish"),
    ("tr_tr", "土耳其语", "Turkish"), ("vi_vn", "越南语", "Vietnamese"),
)


def validate_locale(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z]{2,3}_[a-z]{2,4}", value):
        raise ValueError("语言代码应为 Minecraft 语言标识，例如 en_us、zh_cn、ja_jp")
    return value


def language_name(value, *, english=False):
    return next((row[2 if english else 1] for row in LANGUAGES if row[0] == value), value)


def validate_pair(source, target):
    validate_locale(source)
    validate_locale(target)
    if source == target:
        raise ValueError("原文语言和译文语言不能相同")
