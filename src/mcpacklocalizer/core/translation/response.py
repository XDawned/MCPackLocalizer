# [Module: translation.response] [Status: 已完成] [Brief: 轻量译文边界协议与响应提取，不猜测或改写正文]
from __future__ import annotations

import hashlib
import json
import re

THINK = re.compile(r"^<think\b[^>]*>.*?</think\s*>\s*", re.DOTALL | re.IGNORECASE)
FENCE = re.compile(r"^(`{3,}|~{3,})[^\r\n]*\r?\n(.*?)\r?\n\1[ \t]*$", re.DOTALL | re.MULTILINE)


def response_tag(source):
    # 原文本身含协议标签时换用专属边界，避免把游戏正文当成包裹。
    if re.search(r"</?(?:translation|textarea)\b", source, re.IGNORECASE):
        return "mcpl_" + hashlib.sha256(source.encode()).hexdigest()[:12]
    return "translation"


def output_instruction(source):
    tag = response_tag(source)
    return f"将完整译文放在 <{tag}>...</{tag}> 内；标签外的内容不会写入译文。\n"


def strip_thinking(raw):
    text = raw.strip()
    while match := THINK.match(text):
        text = text[match.end():].strip()
    if re.match(r"^</?think\b", text, re.IGNORECASE):
        raise ValueError("模型思考段不完整，无法提取译文")
    if not text:
        raise ValueError("模型响应为空")
    return text


def extract_translation(raw, source):
    """优先明确边界，兼容代码围栏、单字段 JSON 和旧模型的纯译文。"""
    text = raw.strip() if re.match(r"^\s*<think\b", source, re.IGNORECASE) else strip_thinking(raw)
    tag = response_tag(source)
    tags = [tag]
    if not re.search(r"</?textarea\b", source, re.IGNORECASE):
        tags.append("textarea")
    # 只接受一个完整结果；多个候选或残缺边界不能靠“取最后一个”决定。
    names = "|".join(re.escape(name) for name in tags)
    starts = list(re.finditer(rf"</?(?:{names})\b", text, re.IGNORECASE))
    boundaries = list(re.finditer(rf"</?(?:{names})\b[^>]*>", text, re.IGNORECASE))
    if len(starts) != len(boundaries):
        raise ValueError("译文标签不完整")
    if boundaries:
        opened = re.fullmatch(rf"<({names})\s*>", boundaries[0].group(), re.IGNORECASE)
        if (len(boundaries) != 2 or opened is None
                or boundaries[1].group().lower() != f"</{opened[1].lower()}>"):
            raise ValueError("译文标签不完整或含多个结果")
        candidate = text[boundaries[0].end():boundaries[1].start()].strip()
    else:
        candidate = text
        # 原文中的 Markdown 是正文；只清除模型额外添加的完整围栏。
        if not re.search(r"(?m)^\s*(?:`{3,}|~{3,})", source):
            fences = list(FENCE.finditer(text))
            if fences:
                if len(fences) != 1:
                    raise ValueError("响应含多个代码围栏，无法确定译文")
                candidate = fences[0][2].strip()
                outside = text[:fences[0].start()] + text[fences[0].end():]
                if re.search(r"(?m)^\s*(?:`{3,}|~{3,})", outside):
                    raise ValueError("译文代码围栏不完整")
            elif re.search(r"(?m)^\s*(?:`{3,}|~{3,})", text):
                raise ValueError("译文代码围栏不完整")
        # JSON 仅兼容明确的 translation 字段；不尝试修复损坏的 JSON。
        if (candidate.startswith("{") and re.search(r'"translation"\s*:', candidate)
                and not re.search(r'"translation"\s*:', source)):
            try:
                pairs = json.loads(candidate, object_pairs_hook=list)
            except ValueError:
                raise ValueError("译文 JSON 不完整") from None
            if len(pairs) != 1 or pairs[0][0] != "translation" or not isinstance(pairs[0][1], str):
                raise ValueError("译文 JSON 必须只含文本字段 translation")
            candidate = pairs[0][1].strip()
    if not candidate:
        raise ValueError("译文为空")
    return candidate


def preview_translation(raw, source, *mappings):
    """试译保留未通过守卫的返回；只还原已知标记，不作为自动翻译结果。"""
    try:
        text = extract_translation(raw, source)
    except ValueError:
        text = raw.strip()
    for mapping in mappings:
        if mapping:
            text = re.sub("|".join(map(re.escape, mapping)), lambda match, values=mapping: values[match.group()], text)
    return text
