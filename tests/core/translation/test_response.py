# [Module: tests.translation.response] [Status: 已完成] [Brief: 译文边界提取、歧义拒绝及正文保真回归]
import pytest

from mcpacklocalizer.core.translation.response import extract_translation, output_instruction, response_tag


@pytest.mark.parametrize("raw", [
    "铁锭",
    "说明\n<translation>铁锭</translation>\n备注",
    "说明\n<TEXTAREA>铁锭</TEXTAREA>\n备注",
    "<think>比较几个术语</think><think>选择铁锭</think><translation>铁锭</translation>",
    "```text\n铁锭\n```",
    "说明\n~~~\n铁锭\n~~~\n备注",
    '{"translation":"铁锭"}',
    '```json\n{"translation":"铁锭"}\n```',
])
def test_extracts_one_complete_translation(raw):
    assert extract_translation(raw, "Iron Ingot") == "铁锭"


@pytest.mark.parametrize("raw", [
    "", "<think>未完成", "<think>只有思考</think>",
    "<translation>铁锭", "</translation>铁锭", "<translation></translation>",
    "<translation", "<translation>铁锭</translation><translation",
    "<translation>铁锭</translation><translation>金锭</translation>",
    "<translation>铁锭</translation><textarea>金锭</textarea>",
    "<translation><translation>铁锭</translation></translation>",
    "```text\n铁锭", "```text\n铁锭\n```\n```text\n金锭\n```",
    '{"translation":"铁锭"', '{"translation":42}', '{"translation":"铁锭","notes":"说明"}',
    '{"notes":"说明","translation":"铁锭"}', '{"translation":"铁锭","translation":"金锭"}',
])
def test_rejects_empty_partial_or_ambiguous_results(raw):
    with pytest.raises(ValueError):
        extract_translation(raw, "Iron Ingot")


def test_preserves_multiline_escapes_quotes_numbers_and_markdown():
    candidate = '1. 使用 &a%s&r\n\n"第二行" \\n ${player} &amp; **保留**'
    assert extract_translation(f"<translation>\n{candidate}\n</translation>", "Use") == candidate


@pytest.mark.parametrize("source,target", [
    ("<textarea>Open</textarea>", "<textarea>打开</textarea>"),
    ("<translation>Open</translation>", "<translation>打开</translation>"),
])
def test_source_tags_are_payload_and_choose_collision_free_boundary(source, target):
    tag = response_tag(source)
    assert tag.startswith("mcpl_") and tag not in source
    assert tag in output_instruction(source)
    assert extract_translation(f"<{tag}>{target}</{tag}>", source) == target
    assert extract_translation(target, source) == target


def test_original_markdown_fence_is_preserved():
    source = "```text\nOpen\n```"
    target = "```text\n打开\n```"
    assert extract_translation(target, source) == target


def test_plain_placeholder_and_original_numbering_are_not_interpreted_as_protocol():
    assert extract_translation("{player}：你好", "{player}: Hello") == "{player}：你好"
    assert extract_translation("1. 铁锭", "1. Iron Ingot") == "1. 铁锭"


def test_json_already_present_in_source_remains_payload():
    source, target = '{"translation":"Iron Ingot"}', '{"translation":"铁锭"}'
    assert extract_translation(target, source) == target
    assert extract_translation(f"<translation>{target}</translation>", source) == target
