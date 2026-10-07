# [Module: tests.polishing] [Status: 已完成] [Brief: 修润提示词、三协议请求、槽位保护和响应校验]
import json

import httpx
import pytest

from mcpacklocalizer.core.translation.local import ModelConfig
from mcpacklocalizer.core.translation.polishing import DEFAULT_POLISH_PROMPT, PolishApiClient


def client(**options):
    return PolishApiClient(ModelConfig(engine="api", api_profile_id="remote", api_model="large",
                                      api_base_url="https://example.test/v1", glossary=None,
                                      context_size=65536, max_tokens=2048, **options), {"remote": "secret"})


@pytest.mark.parametrize("protocol", ["openai", "anthropic", "gemini"])
def test_polishing_sends_original_and_current_translation_in_each_protocol(mocker, protocol):
    requests = []

    def handle(request):
        requests.append(request)
        text = '{"translation":"Iron Sword"}'
        data = ({"choices": [{"message": {"content": text}, "finish_reason": "stop"}]} if protocol == "openai" else
                {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"} if protocol == "anthropic" else
                {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]})
        return httpx.Response(200, json=data)

    transport = httpx.Client(transport=httpx.MockTransport(handle))
    mocker.patch("mcpacklocalizer.core.translation.api.httpx.Client", return_value=transport)
    with client(api_protocol=protocol, source_locale="ja_jp", target_locale="en_us") as model:
        assert model.polish("鉄の剣", "wrong sword", "任务", DEFAULT_POLISH_PROMPT, "polish") == "Iron Sword"
    payload = json.loads(requests[0].content)
    user = (payload["contents"][0]["parts"][0]["text"] if protocol == "gemini" else payload["messages"][-1]["content"])
    data = json.loads(user)
    assert (data["source"], data["translation"], data["context"]) == ("鉄の剣", "wrong sword", "任务")
    assert data["target_language"] == "英语（美国）"
    assert "改善表达" in data["mode"]


def test_custom_prompt_expands_once_without_changing_inserted_braces(mocker):
    model = client()
    request = mocker.patch.object(model, "_request", return_value='{"translation":"{context} 铁锭"}')
    result = model.polish("{context} Iron Ingot", "旧译文", "含 {source} 的背景",
                          "原文 {source}；译文 {translation}；背景 {context}", "correct")
    assert result == "{context} 铁锭"
    system = request.call_args.args[1]
    assert "原文 {context} Iron Ingot" in system
    assert "译文 旧译文" in system and "含 {source} 的背景" in system


@pytest.mark.parametrize("reply", ['{"translation":"葡萄"}', '{"translation":null}',
                                  '葡萄', '{"translation":"&b葡萄&r","code":"bad"}'])
def test_invalid_or_format_damaging_response_is_rejected(mocker, reply):
    model = client()
    mocker.patch.object(model, "_request", return_value=reply)
    with pytest.raises(ValueError):
        model.polish("&bGrapes&r", "旧葡萄", "", DEFAULT_POLISH_PROMPT, "correct")


def test_script_polishing_only_rebuilds_ordered_text_slots(mocker):
    model = client()
    request = mocker.patch.object(model, "_request", return_value='{"slots":["§a获得 "," 件物品"]}')
    marker = "{{MCPL_123456abcdef_0}}"
    source = "§aYou got " + marker + " items"
    translation = "§a你得到了 " + marker + " 个项目"
    assert model.polish(source, translation, "player.tell", DEFAULT_POLISH_PROMPT, "polish", script=True) == (
        "§a获得 " + marker + " 件物品")
    data = json.loads(request.call_args.args[0])
    assert data["source_slots"] == ["§aYou got ", " items"]
    assert data["translation_slots"] == ["§a你得到了 ", " 个项目"]
    request.return_value = '{"slots":["坏译文"],"code":"player.tell(123)"}'
    with pytest.raises(ValueError, match="槽位"):
        model.polish(source, translation, "", DEFAULT_POLISH_PROMPT, "polish", script=True)


def test_over_budget_request_does_not_send_or_truncate_text(mocker):
    model = client()
    request = mocker.patch.object(model, "_request")
    with pytest.raises(ValueError, match="上下文"):
        model.polish("A" * 65536, "旧译文", "", DEFAULT_POLISH_PROMPT, "correct")
    request.assert_not_called()


@pytest.mark.parametrize("reply", ['{"translation":"葡萄"}', '葡萄', '{"translation":"葡萄","extra":true}'])
def test_failed_proposal_retains_visible_content_and_response(mocker, reply):
    model = client()
    mocker.patch.object(model, "_request", return_value=reply)
    proposal = model.propose("&bGrapes&r", "&b旧葡萄&r", "", DEFAULT_POLISH_PROMPT, "correct")
    assert proposal["raw_response"] == reply and proposal["translation"] == "葡萄" and proposal["error"]


def test_truncated_model_response_is_kept_for_manual_repair(mocker):
    transport = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
        "choices": [{"message": {"content": '{"translation":"铁'}, "finish_reason": "length"}]})))
    mocker.patch("mcpacklocalizer.core.translation.api.httpx.Client", return_value=transport)
    with client() as model:
        proposal = model.propose("Iron Ingot", "旧译文", "", DEFAULT_POLISH_PROMPT, "correct")
    assert "截断" in proposal["error"] and proposal["raw_response"] == '{"translation":"铁'
    assert proposal["translation"] == '{"translation":"铁'


def test_fenced_candidate_is_visible_even_when_json_protocol_guard_fails(mocker):
    model = client()
    raw = '```json\n{"translation":"葡萄"}\n```'
    mocker.patch.object(model, "_request", return_value=raw)
    proposal = model.propose("&bGrapes&r", "旧葡萄", "", DEFAULT_POLISH_PROMPT, "correct")
    assert proposal["translation"] == "葡萄" and proposal["raw_response"] == raw and proposal["error"]


def test_authentication_error_does_not_expose_http_body_or_key(mocker):
    transport = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401, text="secret-provider-body")))
    mocker.patch("mcpacklocalizer.core.translation.api.httpx.Client", return_value=transport)
    with client() as model:
        proposal = model.propose("Iron Ingot", "旧译文", "", DEFAULT_POLISH_PROMPT, "correct")
    assert "401" in proposal["error"] and proposal["raw_response"] == ""
    assert "secret" not in json.dumps(proposal)
