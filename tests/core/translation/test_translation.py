# [Module: tests.translation] [Status: 开发中] [Brief: 占位符/数字保护和 GPU 运行时能力检查]
import sys
from types import SimpleNamespace

import pytest

from mcpacklocalizer.core.translation.local import (
    NUMERIC,
    PROTECTED,
    LocalEngine,
    ModelConfig,
    number_warnings,
    placeholder_warnings,
    preservation_rules,
    protect,
    protect_braces,
    render_prompt,
    restore,
    restore_braces,
    validate,
)


def test_protect_restore_colors_ids_numbers_and_placeholders():
    source = "&aCollect 64 minecraft:iron_ingot for %1$s and ${player} at https://example.com/test"
    text, mapping = protect(source)
    assert restore(text.replace("Collect", "收集").replace(" for ", " 给 ").replace(" and ", " 和 ").replace(" at ", " 在 "), mapping).startswith("&a收集 64 minecraft:iron_ingot")
    validate(source, restore(text, mapping))


def test_reordered_duplicated_or_lost_markers_fail():
    text, mapping = protect("&aCollect 64 items for ${player}")
    first, second = mapping
    for bad in (text.replace(first, ""), text + first, text.replace(first, "TMP").replace(second, first).replace("TMP", second)):
        with pytest.raises(ValueError):
            restore(bad, mapping)


def test_changed_numbers_pass_validation_with_quality_hint():
    validate("Collect 64 items", "收集32个物品")
    hint, = number_warnings("Collect 64 items", "收集32个物品")
    assert hint["missing"] == ["64"] and hint["added"] == ["32"]


@pytest.mark.parametrize("candidate", [
    "请注意！发射火箭时燃料会耗尽，因此携带额外的燃料非常重要，这样你就能在发射后返回家中！6个桶应该足以前往『空间』并返回。",
    "请注意！发射火箭时燃料会耗尽，因此携带额外的燃料非常重要，这样你就能在发射后返回家中！6桶的燃料应该足以前往『空间』并返回。",
])
def test_rocket_translation_keeps_six_next_to_chinese(candidate):
    source = ("Please note! Fuel gets depleted when launching the rocket, so bringing extra fuel with you "
              "so you can get back home when you launch is extremely important! "
              "6 buckets should be enough to go to space and back")
    assert PROTECTED.findall(source) == PROTECTED.findall(candidate) == []
    assert number_warnings(source, candidate) == []
    validate(source, candidate)


@pytest.mark.parametrize("source,candidate,fragments", [
    ("Use 10% more power.", "使用10%更多能量。", ["10%"]),
    ("Collect 64 minecraft:iron_ingot", "收集64个minecraft:iron_ingot", ["64", "minecraft:iron_ingot"]),
    ("Use 1.5 units and 1,000 items.", "使用1.5单位和1,000个物品。", ["1.5", "1,000"]),
])
def test_chinese_adjacency_preserves_numbers_and_ids(source, candidate, fragments):
    assert number_warnings(source, candidate) == []
    assert NUMERIC.findall(PROTECTED.sub(" ", candidate)) == [f for f in fragments if ":" not in f]
    validate(source, candidate)
    masked, mapping = protect(candidate)
    assert list(mapping.values()) == [f for f in fragments if ":" in f]
    assert restore(masked, mapping) == candidate


@pytest.mark.parametrize("candidate", [
    "携带7桶燃料和10%额外能量。",  # changed
    "携带桶燃料和10%额外能量。",  # lost
    "携带6桶燃料和6桶备用燃料以及10%额外能量。",  # duplicated
])
def test_numeric_changes_are_advisory(candidate):
    source = "Bring 6 buckets of fuel and 10% extra power."
    validate(source, candidate)
    assert number_warnings(source, candidate)


def test_numeric_reordering_has_no_quality_hint():
    source = "Craft a tier 2 rocket like a tier 1 rocket."
    candidate = "像制作1级火箭那样制作2级火箭。"
    masked, mapping = protect(source)
    assert mapping == {} and masked == source
    validate(source, candidate)
    assert number_warnings(source, candidate) == []


def test_duplicated_number_is_detected_using_counts():
    hint, = number_warnings("Make 1 rocket with 2 pads", "用2个平台制作1个火箭，再加1个火箭")
    assert hint["added"] == ["1"] and hint["missing"] == []


def test_chinese_number_spelling_is_accepted_with_nonblocking_hint():
    validate("Bring 6 buckets", "带上六桶")
    assert number_warnings("Bring 6 buckets", "带上六桶")[0]["severity"] == "info"


def test_program_numbers_do_not_pollute_quality_hints():
    source = "&aBring 6 minecraft:item_64 for %1$s and ${player2} at https://example.com/3x3"
    candidate = "&a带上6个minecraft:item_64，交给%1$s和${player2}，地址https://example.com/3x3"
    assert number_warnings(source, candidate) == []
    assert list(protect(source)[1].values()) == ["&a", "minecraft:item_64", "%1$s", "${player2}", "https://example.com/3x3"]


@pytest.mark.parametrize("source,candidate", [
    ("Use %1$s", "使用%2$s"), ("Use minecraft:item_64", "使用minecraft:item_32"),
    ("Use ${player2}", "使用${player3}"), ("&aCollect 6", "&c收集6"),
])
def test_program_fragments_remain_blocking(source, candidate):
    with pytest.raises(ValueError, match="保留符"):
        validate(source, candidate)


def test_chinese_adjacent_changed_id_is_still_rejected():
    with pytest.raises(ValueError, match="保留符"):
        validate("Collect 64 minecraft:iron_ingot", "收集64个minecraft:gold_ingot")


def test_numbers_embedded_in_ascii_words_are_not_standalone_fragments():
    assert NUMERIC.findall("tier6 6buckets v1.5 item_64") == []


@pytest.mark.parametrize("source,candidate", [
    ("Build a 3x3 square.", "搭建一个3×3的方形。"),
    ("Build a 3x3 square.", "搭建一个3x3的方形。"),
    ("Build a 2 X 3 x 4 frame.", "搭建一个2×3×4的框架。"),
    ("Use a 1.5x2.5 panel.", "使用1.5 × 2.5的面板。"),
    ("Build a 3×3 square.", "搭建一个3 x 3的方形。"),
])
def test_dimensions_allow_equivalent_separator_and_spacing(source, candidate):
    validate(source, candidate)
    assert number_warnings(source, candidate) == []
    masked, mapping = protect(source)
    assert mapping == {} and masked == source
    assert restore(masked, mapping) == source


@pytest.mark.parametrize("candidate", [
    "搭建3×4的方形。", "搭建方形。", "搭建3×3和3×3的方形。", "搭建3+3的方形。",
])
def test_dimension_changes_are_advisory(candidate):
    source = "Build a 3x3 square."
    validate(source, candidate)
    assert number_warnings(source, candidate)


def test_dimension_axes_change_warns_but_expression_reordering_does_not():
    source = "Build a 2x3 frame with 5 items."
    assert number_warnings(source, "搭建3×2的框架，使用5个物品。")
    assert number_warnings(source, "使用5个物品，搭建2×3的框架。") == []


@pytest.mark.parametrize("source,candidate", [
    ("Use mod:3x3", "使用mod:3×3"),
    ("Open https://example.com/3x3", "打开https://example.com/3×3"),
    ("Use ${3x3}", "使用${3×3}"),
])
def test_dimension_equivalence_does_not_change_ids_urls_or_variables(source, candidate):
    with pytest.raises(ValueError, match="保留符"):
        validate(source, candidate)


def test_direct_prompt_uses_short_template_without_format_constraints():
    source = "&bGrapes&r &bPot&r &6jumping and walking&r"
    prompt = render_prompt(source, [("Grapes", "葡萄")], "游戏任务")
    assert "标记：" not in prompt and "代码：" not in prompt
    assert "结束标记" not in prompt
    assert prompt.endswith(source)
    assert prompt.index("Grapes 翻译成 葡萄") < prompt.index("将以下文本翻译为中文")


def test_masked_prompt_lists_every_marker_and_requires_phrase_boundaries():
    source = "&bGrapes&r &bPot&r &6jumping and walking&r"
    masked, mapping = protect_braces(source)
    prompt = render_prompt(masked, markers=list(mapping))
    assert "标记：" + " ".join(mapping) in prompt
    assert "结束标记不可遗漏" in prompt
    assert prompt.endswith(masked)
    assert list(mapping.values()) == ["&b", "&r", "&b", "&r", "&6", "&r"]


def test_plain_text_has_no_spurious_formatting_instructions():
    assert preservation_rules("Iron Ingot") == ""
    assert "Required color codes" not in render_prompt("Iron Ingot")


def test_brace_mask_skips_existing_numbers_and_restores_variables_in_one_pass():
    source = "&aBring {{0}} for {{player}} and ${name}"
    masked, mapping = protect_braces(source)
    assert all(marker not in source for marker in mapping)
    assert list(mapping.values()) == ["&a", "{{0}}", "{{player}}", "${name}"]
    candidate = restore_braces(masked.replace("Bring", "带来"), mapping)
    assert candidate == source.replace("Bring", "带来")
    validate(source, candidate)


def test_brace_restore_rejects_lost_duplicate_reordered_or_invented_markers():
    masked, mapping = protect_braces("&aBring ${player}")
    first, second = mapping
    reordered = masked.replace(first, "TEMP").replace(second, first).replace("TEMP", second)
    for candidate in (masked.replace(first, ""), masked + first, reordered, masked + "{{99}}"):
        with pytest.raises(ValueError):
            restore_braces(candidate, mapping)


def test_complete_double_brace_variable_is_strict():
    with pytest.raises(ValueError):
        validate("Bring {{player}}", "带上{player}")


def fake_llama(mocker, gpu=False, info=b"CPU AVX2"):
    model = mocker.Mock()
    model.metadata = {"tokenizer.chat_template": "template"}
    model.chat_format = "chat_template.default"
    model.n_ctx.return_value = 4096
    model.tokenize.side_effect = lambda text, **kwargs: list(text)
    api = SimpleNamespace(llama_backend_init=lambda: None,
                          llama_print_system_info=lambda: info, llama_supports_gpu_offload=lambda: gpu)
    constructor = mocker.Mock(return_value=model)
    mocker.patch.dict(sys.modules, {"llama_cpp": SimpleNamespace(Llama=constructor, llama_cpp=api)})
    mocker.patch("mcpacklocalizer.core.translation.local.Path.is_file", return_value=True)
    return model, constructor


def test_cpu_runtime_does_not_claim_cuda(mocker):
    _, constructor = fake_llama(mocker)
    with pytest.raises(ValueError, match="无法使用 cuda"):
        LocalEngine(ModelConfig(backend="cuda", glossary=None))
    constructor.assert_not_called()


def test_vulkan_library_is_detected_when_system_info_only_lists_cpu(mocker):
    _, constructor = fake_llama(mocker, gpu=True)
    sys.modules["llama_cpp"].llama_cpp.__file__ = "runtime/llama_cpp/llama_cpp.py"
    from pathlib import Path
    mocker.patch("mcpacklocalizer.core.translation.local.Path.glob", return_value=[Path("ggml-vulkan.dll"), Path("ggml-cpu.dll")])
    engine = LocalEngine(ModelConfig(backend="vulkan", glossary=None))
    assert engine.info["backend"] == "vulkan"
    assert constructor.call_args.kwargs["n_gpu_layers"] == -1


def test_gpu_library_without_device_falls_back_to_cpu(mocker):
    _, constructor = fake_llama(mocker, gpu=False, info=b"VULKAN CPU")
    engine = LocalEngine(ModelConfig(glossary=None))
    assert engine.info["backend"] == "cpu"
    assert constructor.call_args.kwargs["n_gpu_layers"] == 0


def test_auto_cpu_uses_gguf_template_and_official_sampling(mocker):
    model, constructor = fake_llama(mocker)
    model.create_chat_completion.return_value = {"choices": [{"message": {"content": "铁锭"}, "finish_reason": "stop"}]}
    engine = LocalEngine(ModelConfig(glossary=None, max_tokens=64))
    assert constructor.call_args.kwargs["n_gpu_layers"] == 0
    assert engine.translate("Iron Ingot") == "铁锭"
    call = model.create_chat_completion.call_args.kwargs
    assert [m["role"] for m in call["messages"]] == ["user"]
    assert call["top_k"] == 20 and call["repeat_penalty"] == 1.05


def test_numeric_change_does_not_retry_or_mask_model_input(mocker):
    model, _ = fake_llama(mocker)
    model.create_chat_completion.return_value = {"choices": [{"message": {"content": "收集32个物品"}, "finish_reason": "stop"}]}
    assert LocalEngine(ModelConfig(glossary=None, max_tokens=64)).translate("Collect 64 items") == "收集32个物品"
    model.create_chat_completion.assert_called_once()
    assert model.create_chat_completion.call_args.kwargs["messages"][0]["content"].endswith("Collect 64 items")


def test_successful_direct_translation_never_prepares_fallback(mocker):
    model, _ = fake_llama(mocker)
    model.create_chat_completion.return_value = {"choices": [{"message": {"content": "&b葡萄&r"}, "finish_reason": "stop"}]}
    prepare = mocker.patch("mcpacklocalizer.core.translation.local.protect_braces", side_effect=AssertionError("unused fallback"))
    assert LocalEngine(ModelConfig(glossary=None, max_tokens=64)).translate("&bGrapes&r") == "&b葡萄&r"
    prepare.assert_not_called()
    model.create_chat_completion.assert_called_once()
    prompt = model.create_chat_completion.call_args.kwargs["messages"][0]["content"]
    assert prompt.endswith("&bGrapes&r") and "标记：" not in prompt


def test_local_response_extracts_translation_without_changing_fixed_prompt(mocker):
    model, _ = fake_llama(mocker)
    model.create_chat_completion.return_value = {"choices": [{
        "message": {"content": "<think>选择游戏术语</think>```text\n铁锭\n```"}, "finish_reason": "stop"}]}
    engine = LocalEngine(ModelConfig(glossary=None, max_tokens=64))
    assert engine.translate("Iron Ingot") == "铁锭"
    model.create_chat_completion.assert_called_once()
    assert model.create_chat_completion.call_args.kwargs["messages"] == [
        {"role": "user", "content": render_prompt("Iron Ingot")}]


def test_failed_direct_translation_uses_brace_fallback_with_same_terms_and_sampling(mocker):
    model, _ = fake_llama(mocker)
    model.create_chat_completion.side_effect = [
        {"choices": [{"message": {"content": "葡萄"}, "finish_reason": "stop"}]},
        {"choices": [{"message": {"content": "{{0}}葡萄{{1}}"}, "finish_reason": "stop"}]}]
    engine = LocalEngine(ModelConfig(max_tokens=64))
    find = mocker.patch.object(engine.glossary, "find", return_value=[("Grapes", "葡萄")])
    assert engine.translate("&bGrapes&r", "游戏任务") == "&b葡萄&r"
    assert model.create_chat_completion.call_count == 2
    direct, fallback = [call.kwargs for call in model.create_chat_completion.call_args_list]
    assert direct["messages"][0]["content"].endswith("&bGrapes&r")
    assert fallback["messages"][0]["content"].endswith("{{0}}Grapes{{1}}")
    assert "标记：{{0}} {{1}}" in fallback["messages"][0]["content"]
    assert all("Grapes 翻译成 葡萄" in call["messages"][0]["content"] for call in (direct, fallback))
    assert direct["temperature"] == fallback["temperature"] == 0.7
    assert direct["seed"] == fallback["seed"] == 42
    find.assert_called_once()


def test_failed_fallback_is_not_adopted_and_does_not_generate_a_third_time(mocker):
    model, _ = fake_llama(mocker)
    model.create_chat_completion.side_effect = [
        {"choices": [{"message": {"content": "葡萄"}, "finish_reason": "stop"}]},
        {"choices": [{"message": {"content": "{{0}}葡萄"}, "finish_reason": "stop"}]}]
    with pytest.raises(ValueError, match="保留符丢失、重复"):
        LocalEngine(ModelConfig(glossary=None, max_tokens=64)).translate("&bGrapes&r")
    assert model.create_chat_completion.call_count == 2


def test_truncated_translation_not_accepted(mocker):
    model, _ = fake_llama(mocker)
    model.create_chat_completion.return_value = {"choices": [{"message": {"content": "铁"}, "finish_reason": "length"}]}
    with pytest.raises(ValueError, match="被截断"):
        LocalEngine(ModelConfig(glossary=None, max_tokens=64)).translate("Iron Ingot")


@pytest.mark.parametrize("raw,expected,missing,reordered", [
    ("{{0}}葡萄", "&b葡萄", ["&r"], False),
    ("葡萄", "葡萄", ["&b", "&r"], False),
    ("{{1}}葡萄{{0}}", "&r葡萄&b", [], True),
])
def test_relaxed_fallback_accepts_missing_or_reordered_markers_with_warning(mocker, raw, expected, missing, reordered):
    model, _ = fake_llama(mocker)
    model.create_chat_completion.side_effect = [
        {"choices": [{"message": {"content": "葡萄"}, "finish_reason": "stop"}]},
        {"choices": [{"message": {"content": raw}, "finish_reason": "stop"}]}]
    engine = LocalEngine(ModelConfig(glossary=None, max_tokens=64, allow_missing_placeholders=True))
    translated = engine.translate("&bGrapes&r")
    assert translated == expected and model.create_chat_completion.call_count == 2
    hint, = placeholder_warnings("&bGrapes&r", translated)
    assert hint["missing"] == missing and hint["reordered"] == reordered
    validate("&bGrapes&r", translated, True)
    with pytest.raises(ValueError):
        validate("&bGrapes&r", translated)


def test_user_pendant_example_reorders_all_four_markers(mocker):
    source = "Can be &6filled&r in the &bPotion Workshop&r with one effect up to Level III."
    raw = "可以在{{2}}药剂工坊{{3}}中最多{{0}}填充{{1}}一种效果，最高可达三级。"
    _, mapping = protect_braces(source)
    translated = restore_braces(raw, mapping, True)
    assert translated == "可以在&b药剂工坊&r中最多&6填充&r一种效果，最高可达三级。"
    hint, = placeholder_warnings(source, translated)
    assert hint["missing"] == [] and hint["reordered"] is True


@pytest.mark.parametrize("raw", ["{{0}}葡萄{{0}}", "{{99}}葡萄", "{{ 0 }}葡萄", "{{0葡萄", "", "  "])
def test_relaxed_restore_still_rejects_duplicate_unknown_malformed_or_empty(raw):
    _, mapping = protect_braces("&bGrapes&r")
    with pytest.raises(ValueError):
        candidate = restore_braces(raw, mapping, True)
        validate("&bGrapes&r", candidate, True)


@pytest.mark.parametrize("candidate", ["&c葡萄", "&b葡萄&r&r", "葡萄${invented}"])
def test_relaxed_validation_rejects_added_or_changed_fragments(candidate):
    with pytest.raises(ValueError):
        validate("&bGrapes&r", candidate, True)


def test_missing_repeated_reset_is_not_misreported_as_reordering():
    hint, = placeholder_warnings("&bGrapes&r and &bPot&r", "&b葡萄&r和&b锅")
    assert hint["missing"] == ["&r"] and hint["reordered"] is False


def test_relaxed_fallback_still_rejects_truncation(mocker):
    model, _ = fake_llama(mocker)
    model.create_chat_completion.return_value = {"choices": [{"message": {"content": "葡萄"}, "finish_reason": "length"}]}
    with pytest.raises(ValueError, match="被截断"):
        LocalEngine(ModelConfig(glossary=None, max_tokens=64, allow_missing_placeholders=True)).translate("&bGrapes&r")
    assert model.create_chat_completion.call_count == 2


def test_local_hy_mt_preserves_no_translate_terms_without_custom_system_prompt(mocker):
    model, _ = fake_llama(mocker)
    def completion(**kwargs):
        messages = kwargs["messages"]
        assert len(messages) == 1 and messages[0]["role"] == "user"
        prompt = messages[0]["content"]
        assert "custom system" not in prompt
        source = prompt.split("：\n\n")[-1]
        return {"choices": [{"message": {"content": source.replace("Use", "使用")}, "finish_reason": "stop"}]}
    model.create_chat_completion.side_effect = completion
    engine = LocalEngine(ModelConfig(glossary=None, max_tokens=64, non_translate="Create", system_prompt="custom system"))
    assert engine.translate("Use Create") == "使用 Create"
