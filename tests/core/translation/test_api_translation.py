# [Module: tests.translation.api] [Status: 已完成] [Brief: API 协议、译文提取与有限重试回归]
import json
from dataclasses import asdict

import httpx
import pytest

from mcpacklocalizer.core.translation.api import ApiClient, ApiProfile, endpoint, extra_parameters
from mcpacklocalizer.core.translation.local import DEFAULT_SYSTEM_PROMPT, ModelConfig, render_prompt


def completion(text="铁锭", reason="stop", **extra):
    return {"choices": [{"message": {"content": text}, "finish_reason": reason}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3}, **extra}


def api(mocker, responses, *, base_url="https://example.test/v1", **options):
    cfg = ModelConfig(engine="api", api_profile_id="test", api_base_url=base_url, api_model="test-model",
                      glossary=None, **options)
    requests = []
    iterator = iter(responses)

    def handle(request):
        requests.append(request)
        result = next(iterator)
        return result if isinstance(result, httpx.Response) else httpx.Response(200, json=result)

    transport = httpx.Client(transport=httpx.MockTransport(handle))
    mocker.patch("mcpacklocalizer.core.translation.api.httpx.Client", return_value=transport)
    mocker.patch("mcpacklocalizer.core.translation.api.time.sleep")
    return ApiClient(cfg, {"test": "secret-key"}), requests


@pytest.mark.parametrize("url,protocol,model,expected", [
    ("http://localhost:1234", "openai", "", "http://localhost:1234/v1/chat/completions"),
    ("https://example.test/api/v1/", "openai", "", "https://example.test/api/v1/chat/completions"),
    ("https://example.test/v1/chat/completions", "openai", "", "https://example.test/v1/chat/completions"),
    ("https://example.test", "anthropic", "", "https://example.test/v1/messages"),
    ("https://example.test/v1/messages/", "anthropic", "", "https://example.test/v1/messages"),
    ("https://example.test", "gemini", "models/test", "https://example.test/v1beta/models/test:generateContent"),
    ("https://example.test/v1beta/models/old:generateContent", "gemini", "new", "https://example.test/v1beta/models/new:generateContent"),
])
def test_endpoint_normalization(url, protocol, model, expected):
    assert endpoint(url, protocol, model) == expected


@pytest.mark.parametrize("url", ["", "file:///etc/config", "https://key@example.test", "https://example.test?key=secret", "https://example.test/#token"])
def test_unsafe_or_invalid_url_is_rejected(url):
    with pytest.raises(ValueError):
        endpoint(url, "openai")


def test_openai_custom_system_terms_auth_and_usage(mocker):
    client, requests = api(mocker, [completion()], system_prompt="MC system", glossary_inline='{"Iron Ingot":"铁锭"}')
    with client:
        assert client.translate("Iron Ingot", "任务章节") == "铁锭"
    request = requests[0]
    data = json.loads(request.content)
    assert request.headers["authorization"] == "Bearer secret-key"
    assert data["messages"][0] == {"role": "system", "content": "MC system"}
    assert "Iron Ingot 翻译成 铁锭" in data["messages"][1]["content"]
    assert "任务章节" in data["messages"][1]["content"]
    assert client.usage_snapshot() == {"requests": 1, "input_tokens": 12, "output_tokens": 3}
    assert "secret-key" not in json.dumps(asdict(client.config))


def test_api_hy_mt_keeps_existing_template_and_single_user_message(mocker):
    client, requests = api(mocker, [completion()], api_prompt_mode="hy_mt", system_prompt="must not be sent")
    with client:
        client.translate("Iron Ingot")
    messages = json.loads(requests[0].content)["messages"]
    assert messages == [{"role": "user", "content": render_prompt("Iron Ingot")}]


@pytest.mark.parametrize("protocol", ["openai", "anthropic", "gemini"])
@pytest.mark.parametrize("source_locale,target_locale,source,target", [
    ("en_us", "zh_cn", "英语（美国）", "简体中文"),
    ("ja_jp", "en_us", "日语", "英语（美国）"),
])
def test_system_language_markers_are_rendered_before_request(mocker, protocol, source_locale, target_locale, source, target):
    template = '把{source_language}文本翻译成{target_language}。保留{player}；示例：{"text":"value"}。'
    client, _ = api(mocker, [], api_protocol=protocol, system_prompt=template,
                    source_locale=source_locale, target_locale=target_locale)
    request = mocker.patch.object(client, "_request", return_value="译文")
    with client:
        client.translate("Iron Ingot")
    user, system = request.call_args.args
    assert system == f'把{source}文本翻译成{target}。保留{{player}}；示例：{{"text":"value"}}。'
    _, payload = client._payload(user, system)
    if protocol == "openai":
        assert payload["messages"][0]["content"] == system
    elif protocol == "anthropic":
        assert payload["system"] == system
    else:
        assert payload["systemInstruction"]["parts"][0]["text"] == system
    assert client.config.system_prompt == template


def test_default_system_prompt_uses_selected_languages_on_both_attempts(mocker):
    client, requests = api(mocker, [completion("Sword"), completion("{{0}}Sword{{1}}")],
                           source_locale="ja_jp", target_locale="en_us")
    with client:
        assert client.translate("&b剣&r") == "&bSword&r"
    assert len(requests) == 2
    for request in requests:
        system = json.loads(request.content)["messages"][0]["content"]
        assert "将日语的任务、物品、方块、界面和模组说明翻译成英语（美国）" in system
        assert "{source_language}" not in system and "{target_language}" not in system
    assert client.config.system_prompt == DEFAULT_SYSTEM_PROMPT


@pytest.mark.parametrize("template,placed_terms,placed_context", [
    (DEFAULT_SYSTEM_PROMPT, True, True),
    ("背景先放：{context}\n术语后放：{glossary}", True, True),
    ("术语放这里：{glossary}", True, False),
    ("背景放这里：{context}", False, True),
    ("旧提示词", False, False),
])
def test_reference_markers_control_placement_without_duplicate_injection(mocker, template, placed_terms, placed_context):
    client, requests = api(mocker, [completion()], system_prompt=template,
                           glossary_inline='{"Iron Ingot":"铁锭"}')
    with client:
        client.translate("Iron Ingot", "任务章节")
    system, user = [message["content"] for message in json.loads(requests[0].content)["messages"]]
    assert ("Iron Ingot 翻译成 铁锭" in system) == placed_terms
    assert ("Iron Ingot 翻译成 铁锭" in user) != placed_terms
    assert ("任务章节" in system) == placed_context
    assert ("任务章节" in user) != placed_context
    assert user.endswith("Iron Ingot")
    if template.startswith("背景先放"):
        assert system.index("任务章节") < system.index("Iron Ingot 翻译成 铁锭")
    assert client.config.system_prompt == template


def test_reference_data_is_not_expanded_as_template_markers(mocker):
    client, requests = api(mocker, [completion()], system_prompt="{glossary}\n{context}\n{context}",
                           glossary_inline='{"Iron Ingot":"{context}"}')
    with client:
        client.translate("Iron Ingot", "保留 {source_language} 和 {glossary}")
    system = json.loads(requests[0].content)["messages"][0]["content"]
    assert system == ("Iron Ingot 翻译成 {context}\n"
                      "保留 {source_language} 和 {glossary}\n"
                      "保留 {source_language} 和 {glossary}")


def test_empty_reference_markers_render_to_empty_text(mocker):
    client, requests = api(mocker, [completion()], system_prompt="开始{glossary}{context}结束")
    with client:
        client.translate("Iron Ingot")
    assert json.loads(requests[0].content)["messages"][0]["content"] == "开始结束"


def test_opencode_go_keeps_session_on_retry_and_identifies_translation_client(mocker):
    client, requests = api(mocker, [httpx.Response(429), completion()], base_url="https://opencode.ai/zen/go/v1")
    with client:
        assert client.translate("Iron Ingot") == "铁锭"
    assert len(requests) == 2
    assert requests[0].url.path == "/zen/go/v1/chat/completions"
    assert requests[0].headers["x-opencode-session"] == requests[1].headers["x-opencode-session"]
    assert requests[0].headers["x-opencode-session"]
    assert requests[0].headers["user-agent"].startswith("MCPackLocalizer/")


def test_japanese_source_uses_english_target_prompt_and_is_not_skipped(mocker):
    client, requests = api(mocker, [completion("Iron Sword")], source_locale="ja_jp", target_locale="en_us")
    with client:
        assert client.translate("鉄の剣") == "Iron Sword"
    messages = json.loads(requests[0].content)["messages"]
    assert "Japanese (ja_jp)" in messages[-1]["content"]
    assert "English (en_us)" in messages[-1]["content"]
    assert "into Chinese" not in messages[-1]["content"]
    assert "翻译成简体中文" not in messages[0]["content"]


def test_api_hy_mt_rejects_other_output_languages(mocker):
    with pytest.raises(ValueError, match="输出中文"):
        api(mocker, [], api_prompt_mode="hy_mt", target_locale="ja_jp")


def test_reasoning_model_can_omit_temperature_and_use_completion_limit(mocker):
    client, requests = api(mocker, [completion()], api_send_temperature=False, api_token_parameter="max_completion_tokens",
                           api_extra_body='{"reasoning_effort":"low"}')
    with client:
        client.translate("Iron Ingot")
    payload = json.loads(requests[0].content)
    assert "temperature" not in payload and "max_tokens" not in payload
    assert payload["max_completion_tokens"] == 768
    assert payload["reasoning_effort"] == "low"


def test_anthropic_protocol(mocker):
    result = {"content": [{"type": "thinking", "thinking": "hidden"}, {"type": "text", "text": "铁锭"}],
              "stop_reason": "end_turn", "usage": {"input_tokens": 10, "output_tokens": 2}}
    client, requests = api(mocker, [result], api_protocol="anthropic")
    with client:
        assert client.translate("Iron Ingot") == "铁锭"
    request = requests[0]
    assert request.url.path == "/v1/messages"
    assert request.headers["x-api-key"] == "secret-key"
    assert request.headers["anthropic-version"] == "2023-06-01"
    assert "system" in json.loads(request.content)


def test_gemini_protocol_does_not_return_thought_parts(mocker):
    result = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
        {"text": "hidden", "thought": True}, {"text": "铁锭"}]}}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 2, "thoughtsTokenCount": 5}}
    client, requests = api(mocker, [result], api_protocol="gemini", api_extra_body='{"thinkingConfig":{"thinkingBudget":0}}')
    with client:
        assert client.translate("Iron Ingot") == "铁锭"
    request = requests[0]
    assert request.headers["x-goog-api-key"] == "secret-key"
    assert "key=" not in str(request.url)
    assert json.loads(request.content)["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}
    assert client.usage_snapshot()["output_tokens"] == 7


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504, 529])
def test_transient_http_failures_retry(mocker, status):
    client, requests = api(mocker, [httpx.Response(status, headers={"Retry-After": "2"}), completion()])
    with client:
        assert client.translate("Iron Ingot") == "铁锭"
    assert len(requests) == 2
    assert client.usage_snapshot()["requests"] == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_permanent_failure_is_not_retried_or_echoed(mocker, status):
    client, requests = api(mocker, [httpx.Response(status, text="your secret-key is bad")])
    with client, pytest.raises(RuntimeError) as error:
        client.translate("Iron Ingot")
    assert str(status) in str(error.value) and "secret-key" not in str(error.value)
    assert len(requests) == 1


def test_retry_count_is_bounded(mocker):
    client, requests = api(mocker, [httpx.Response(429)] * 3, retries=2)
    with client, pytest.raises(RuntimeError, match="429"):
        client.translate("Iron Ingot")
    assert len(requests) == 3


def test_invalid_direct_output_uses_existing_masked_fallback(mocker):
    client, requests = api(mocker, [completion("葡萄"), completion("{{0}}葡萄{{1}}")])
    with client:
        assert client.translate("&bGrapes&r") == "&b葡萄&r"
    assert len(requests) == 2
    assert "标记：{{0}} {{1}}" in json.loads(requests[1].content)["messages"][-1]["content"]


@pytest.mark.parametrize("protocol", ["openai", "anthropic", "gemini"])
def test_wrapped_translation_excludes_explanation_on_every_protocol(mocker, protocol):
    raw = "说明：保留格式。\n<translation>&b葡萄&r</translation>\n翻译结束。"
    result = (completion(raw) if protocol == "openai" else
              {"content": [{"type": "text", "text": raw}], "stop_reason": "end_turn"} if protocol == "anthropic" else
              {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": raw}]}}]})
    client, requests = api(mocker, [result], api_protocol=protocol)
    with client:
        assert client.translate("&bGrapes&r") == "&b葡萄&r"
    assert len(requests) == 1


def test_format_error_retries_only_failed_entry_once(mocker):
    client, requests = api(mocker, [completion("<translation>铁锭"),
                                   completion("<translation>铁锭</translation>")])
    with client:
        assert client.translate("Iron Ingot") == "铁锭"
    assert len(requests) == 2


def test_wrapped_fallback_restores_protected_fragments(mocker):
    client, requests = api(mocker, [completion("<translation>葡萄</translation>"),
                                   completion("说明\n<translation>{{0}}葡萄{{1}}</translation>\n结束")])
    with client:
        assert client.translate("&bGrapes&r") == "&b葡萄&r"
    assert len(requests) == 2


def test_custom_user_prompt_uses_envelope_without_hy_mt_only_output_instruction(mocker):
    client, requests = api(mocker, [completion("<translation>铁锭</translation>")], system_prompt="旧提示词")
    with client:
        assert client.translate("Iron Ingot") == "铁锭"
    prompt = json.loads(requests[0].content)["messages"][-1]["content"]
    assert "<translation>" in prompt and "只需要输出" not in prompt


def test_ambiguous_response_cannot_be_adopted_after_fallback(mocker):
    raw = "<translation>铁锭</translation><translation>金锭</translation>"
    client, requests = api(mocker, [completion(raw)] * 2)
    with client, pytest.raises(ValueError, match="多个结果"):
        client.translate("Iron Ingot")
    assert len(requests) == 2


def test_no_translate_terms_are_masked_and_whole_entry_can_skip_request(mocker):
    client, requests = api(mocker, [], non_translate="Create")
    with client:
        assert client.translate("Create") == "Create"
    assert requests == []
    client, requests = api(mocker, [completion()], non_translate="Create")
    mocker.patch.object(client, "_request", side_effect=lambda user, system: user.split("：\n\n")[-1].replace("Use", "使用"))
    with client:
        assert client.translate("Use Create") == "使用 Create"


@pytest.mark.parametrize("result", [completion(reason="length"), completion(reason="content_filter"), {},
                                    completion(""), completion("<think>unfinished")])
def test_invalid_response_is_not_adopted(mocker, result):
    client, _ = api(mocker, [result])
    with client, pytest.raises(ValueError):
        client.translate("Iron Ingot")


def test_truncated_response_still_counts_usage(mocker):
    client, _ = api(mocker, [completion(reason="length")])
    with client, pytest.raises(ValueError):
        client.translate("Iron Ingot")
    assert client.usage_snapshot()["output_tokens"] == 3


def test_env_key_resolution_and_missing_env(mocker, monkeypatch):
    monkeypatch.setenv("MCPL_TEST_KEY", "env-secret")
    client, requests = api(mocker, [completion()], api_key_env="MCPL_TEST_KEY")
    with client:
        client.translate("Iron Ingot")
    assert requests[0].headers["authorization"] == "Bearer env-secret"
    monkeypatch.delenv("MCPL_TEST_KEY")
    with pytest.raises(ValueError, match="未设置"):
        ApiClient(client.config)


def test_local_unauthenticated_service_can_have_empty_key(mocker):
    client, requests = api(mocker, [completion()])
    client.key = ""
    with client:
        client.translate("Iron Ingot")
    assert "authorization" not in requests[0].headers


@pytest.mark.parametrize("text", ['[]', '{"stream":true}', '{"model":"bad"}', '{"messages":[]}', '{"max_tokens":1}'])
def test_structural_extra_parameters_are_rejected(text):
    with pytest.raises(ValueError):
        extra_parameters(text)


def test_context_budget_never_sends_a_truncated_source(mocker):
    client, requests = api(mocker, [], context_size=800)
    with client, pytest.raises(ValueError, match="不会截断"):
        client.translate("A very long entry" * 100)
    assert not requests


def test_profile_repr_hides_key():
    assert "secret" not in repr(ApiProfile(id="test", api_key="secret"))
