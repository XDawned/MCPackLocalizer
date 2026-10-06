# [Module: tests.glossary] [Status: 开发中] [Brief: 最长优先、单词边界、多译法和覆盖词典]
import json
from pathlib import Path

import pytest

from mcpacklocalizer.core.translation.glossary import (
    Glossary,
    clean_term,
    is_generic_term,
    load_common_words,
    normalize,
)


def test_longest_overlap_boundaries_short_terms_and_distinct_occurrences(mocker):
    mocker.patch.object(Path, "read_text", return_value=json.dumps({"Iron": "铁", "Iron Ingot": "铁锭", "Tin": "锡", "AE": "应用能源"}))
    glossary = Glossary(Path("glossary.json"))
    assert glossary._automaton is None
    assert glossary.find("&aIron Ingot, Iron, Tinker and Tin AE") == [("Iron Ingot", "铁锭"), ("Iron", "铁"), ("Tin", "锡"), ("AE", "应用能源")]


def test_ambiguous_terms_are_skipped_until_overridden(mocker):
    mocker.patch.object(Path, "read_text", side_effect=[json.dumps({"Back": ["后", "返回"], "Iron": "铁"}),
                                                      json.dumps({"back": "返回"})])
    glossary = Glossary(Path("builtin.json"), Path("project.json"))
    assert glossary.find("Back and Iron") == [("back", "返回"), ("Iron", "铁")]


def test_colors_are_cleaned_on_both_sides_before_deduplication(mocker):
    mocker.patch.object(Path, "read_text", return_value=json.dumps({
        "§5The End": ["§5末地", "&6末地", "末地"],
        "&6The End": "&r末地", "The End": "末地", ":": "：", "§r": "&a", "Empty": "§r"}))
    glossary = Glossary(Path("glossary.json"))
    assert glossary.find("&6The End: The End") == [("The End", "末地")]
    assert glossary.find("The End:") == [("The End", "末地")]
    assert glossary.stats == {"terms": 1, "ambiguous": 0}


def test_rgb_and_embedded_format_codes_are_removed_without_splitting_words(mocker):
    for value in ("§x§a§b§c§d§e§fThe End§r", "&x&a&b&c&d&e&fThe End&r",
                  "&#AbC123The End", "§#123abcThe End", "&lThe &oEnd&r"):
        assert clean_term(value) == "The End"
    assert clean_term("Ir§aon &rIngot") == "Iron Ingot"
    mocker.patch.object(Path, "read_text", return_value=json.dumps({
        "§x§a§b§c§d§e§fThe End§r": "§x§0§1§2§3§4§5末地§r"}))
    assert Glossary(Path("glossary.json")).find("The End") == [("The End", "末地")]


def test_cleaned_conflicts_are_ambiguous_until_explicit_override(mocker):
    builtin = {"§5The End": "§5末地", "&6the end": "终点"}
    mocker.patch.object(Path, "read_text", return_value=json.dumps(builtin))
    glossary = Glossary(Path("builtin.json"))
    assert glossary.find("The End") == []
    assert glossary.stats["ambiguous"] == 1
    mocker.patch.object(Path, "read_text", side_effect=[json.dumps(builtin), json.dumps({"&aThe End": "&a末地"})])
    assert Glossary(Path("builtin.json"), Path("overrides.json")).find("The End") == [("The End", "末地")]


def test_cleanup_preserves_meaningful_punctuation_and_syntax(mocker):
    data = {"C++": "C++", "minecraft:the_end": "minecraft:the_end", "${player}": "${player}"}
    mocker.patch.object(Path, "read_text", return_value=json.dumps(data))
    glossary = Glossary(Path("glossary.json"))
    assert dict(glossary.find("C++ minecraft:the_end ${player}")) == data
    assert clean_term("A&V §q") == "A&V §q"  # Unsupported/non-format characters remain literal.


def test_common_words_config_supports_comments_blank_lines_and_phrases(mocker):
    path = Path("common_words_en.txt")
    mocker.patch.object(Path, "is_file", return_value=True)
    mocker.patch.object(Path, "read_text", return_value="# comment\n\nWith\nOut of Order\n  Iron  \n")
    assert load_common_words(path) == frozenset({"with", "out of order", "iron"})


def test_missing_common_words_config_fails_fast(mocker):
    mocker.patch.object(Path, "is_file", return_value=False)
    with pytest.raises(FileNotFoundError):
        load_common_words(Path("missing.txt"))


@pytest.mark.parametrize("term", ["4", "§64", "10%", "1.5", "1,000", "3x3", "2×2", "2 x 3 x 4", "1/2", "1-3",
                                  "with", "the", "IT", "&6Once", "Squares", "You", "and"])
def test_generic_words_and_numeric_expressions_are_filtered(term):
    assert is_generic_term(normalize(term))


@pytest.mark.parametrize("term", ["Twilight Forest", "The End", "Out of Order", "Tier 2 Rocket", "AE2",
                                  "Applied Energistics 2", "Iron Ingot", "Water", "C++", "minecraft:item_4"])
def test_complete_names_and_materials_are_not_filtered(term):
    assert not is_generic_term(normalize(term))


def test_portal_query_excludes_numeric_and_generic_injection(mocker):
    mocker.patch.object(Path, "read_text", return_value=json.dumps({
        "Twilight Forest": "暮色森林", "Squares": "方格", "with": "使用", "the": "The", "IT": "小丑·它",
        "4": "0", "2x2": "错误尺寸", "Water": "水"}))
    glossary = Glossary(Path("glossary.json"))
    assert glossary.find("&6Make a 2x2 pool (4 squares) of Water with plants for the Twilight Forest. IT") == [
        ("Twilight Forest", "暮色森林"), ("Water", "水")]


def test_filtered_terms_do_not_occupy_result_limit(mocker):
    mocker.patch.object(Path, "read_text", return_value=json.dumps({
        "the": "The", "Once": "1次", "4": "0", "Tin": "锡"}))
    glossary = Glossary(Path("glossary.json"))
    assert glossary.find("Once the 4 Tin", limit=1) == [("Tin", "锡")]


def test_filtered_terms_cannot_return_via_case_format_variants_or_overrides(mocker):
    mocker.patch.object(Path, "read_text", side_effect=[
        json.dumps({"IT": "小丑·它", "4": "0", "&6The End": "终点"}),
        json.dumps({"&aIt": "小丑", "§64": "错误数字", "The End": "末地"})])
    assert Glossary(Path("builtin.json"), Path("overrides.json")).find("it 4 The End") == [("The End", "末地")]


@pytest.mark.parametrize("term", ["them.", "THEM...", "&7&othem.&r", "it!", "with,", '"them."',
                                  "(them.)", "‘them.’", "them。", "4.", "10%!"])
def test_punctuation_variants_are_filtered_only_as_source_terms(term):
    assert clean_term(term, filter_generic=True) == ""
    assert is_generic_term(normalize(term))


@pytest.mark.parametrize("term", ["C++", "C#", "minecraft:the_end", "${them}", "The End:", "Dr.", "U.S."])
def test_valid_names_keep_their_punctuation(term):
    assert clean_term(term, filter_generic=True) == term


def test_wooly_pig_query_does_not_inject_them_sentence(mocker):
    mocker.patch.object(Path, "read_text", return_value=json.dumps({
        "Egg Laying": "产卵", "Manifest": "奥术清单", "Wooly": "羊毛", "Pig": "猪",
        "them.": "生活方式真的很吸引人。", "&7&othem.&r": "错误注入", "THEM!": "另一个错误注入"}))
    glossary = Glossary(Path("glossary.json"))
    source = "\t&6Craft&r and &6manifest&r the memory of an &bEgg Laying Wooly Pig&r. &7&oYou will probably want two of them.&r"
    result = glossary.find(source)
    assert ("Egg Laying", "产卵") in result and ("Pig", "猪") in result
    assert all("them" not in normalize(term) for term, _ in result)
    assert all("生活方式" not in translation for _, translation in result)


def test_translation_punctuation_and_configured_phrase_filter_are_preserved(mocker):
    assert clean_term("§a末地。&r") == "末地。"
    assert clean_term("them.") == "them."  # Generic filtering is opt-in for source entries only.
    mocker.patch("mcpacklocalizer.core.translation.glossary.COMMON_WORDS", frozenset({"out of"}))
    assert clean_term('"Out of."', filter_generic=True) == ""
    assert clean_term("Out of Order", filter_generic=True) == "Out of Order"
