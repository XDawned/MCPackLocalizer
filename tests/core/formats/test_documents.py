# [Module: tests.documents] [Status: 开发中] [Brief: FTB SNBT/JSON5 无损文本替换和语法拒绝]
import json

import pytest

from mcpacklocalizer.core.formats.documents import Atom, ParseError, Parser, replace_strings, strings


def test_preserves_comments_typed_arrays_numbers_and_keys():
    text = '{\n// keep me\n id: "ABC"\n x: 1.0d\n ids: [L; 1L, 2L]\n title: "Iron Ingot"\n description: ["one" "two"]\n}'
    tree = Parser(text).parse()
    assert tree["x"] == Atom("1.0d")
    node = tree["title"]
    changed = replace_strings(text, [(node, '铁锭 "测试"')])
    assert changed == text[:node.start] + '"铁锭 \\"测试\\""' + text[node.end:]
    assert Parser(changed).parse()["title"].value == '铁锭 "测试"'
    assert len(list(strings(tree["description"]))) == 2


def test_json5_single_quotes_comments_trailing_comma_and_line_continuation():
    text = "{ // test\n 'quest.A.title': 'Iron Ingot', count: +2, lines: ['one', 'two',], }"
    parsed = Parser(text, "json5").parse()
    result = replace_strings(text, [(parsed["quest.A.title"], "铁锭")])
    assert "// test" in result and "count: +2" in result
    assert Parser(result, "json5").parse()["quest.A.title"].value == "铁锭"


@pytest.mark.parametrize("text", ['{title: "oops}', '{title: "a" title: "b"}', '{title: "a"} garbage', '{title: ["a"]'])
def test_malformed_snbt_is_rejected(text):
    with pytest.raises(ParseError):
        Parser(text).parse()


def test_json5_requires_commas():
    with pytest.raises(ValueError):
        Parser('{"a": "b" "c": "d"}', "json5").parse()


def test_large_json_language_file_preserves_unicode_escapes_and_spans(mocker):
    json5_decode = mocker.patch("json5.loads", side_effect=AssertionError("严格 JSON 不应调用 JSON5 解析器"))
    values = {f"key.{index}": '说明与换行\n引号"反斜杠\\😀' * 20 for index in range(200)}
    text = json.dumps(values, ensure_ascii=True)
    parsed = Parser(text, "json").parse()
    assert {key: node.value for key, node in parsed.items()} == values
    for key, node in parsed.items():
        assert json.loads(text[node.start:node.end]) == values[key]
    json5_decode.assert_not_called()


def test_json_duplicate_keys_are_still_rejected():
    with pytest.raises(ParseError, match="键重复"):
        Parser('{"name": "first", "name": "second"}', "json").parse()
