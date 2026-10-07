# [Module: tests.translation.prompt_preview] [Status: 已完成] [Brief: 实际提示词、术语预算、禁翻和重试预览的一致性验证]
import json
from dataclasses import asdict

import httpx
import pytest

from mcpacklocalizer.application.config.settings import Settings
from mcpacklocalizer.application.tasks.jobs import Job
from mcpacklocalizer.application.tasks.service import config_for, execute
from mcpacklocalizer.core.translation.api import ApiProfile
from mcpacklocalizer.core.translation.local import LocalEngine, WorkerClient
from tests.core.translation.test_templates import configured_client
from tests.core.translation.test_translation import fake_llama


def api_settings(**kwargs):
    profile = ApiProfile(id="preview", model="model", base_url="https://example.test/v1", api_key="private-key", **kwargs)
    return Settings(engine="api", active_api=profile.id, api_profiles=[asdict(profile)], glossary="",
                    glossary_inline='{"Iron Ingot":"铁锭","Iron":"铁","Gold Ingot":"金锭","Create":"机械动力"}',
                    non_translate="Create")


def test_api_preview_matches_the_actual_message_and_never_sends_a_request(mocker):
    settings = api_settings()
    client, requests = configured_client(mocker, settings, [])
    client.config.capture_prompts = True
    source = "Use Iron Ingot for Create"
    body, kept = client.no_translate.mask(source)
    marker = next(iter(kept))
    preview = client.preview(source, "物品说明")
    assert requests == [] and client.usage_snapshot()["requests"] == 0
    first = preview["prompt_preview"][0]
    assert first["terms"] == [{"source": "Iron Ingot", "translation": "铁锭"}]
    text = "\n".join(message["content"] for message in first["messages"])
    assert "Iron Ingot 翻译成 铁锭" in text and "物品说明" in text
    assert body in text and marker in text and "Create 翻译成" not in text
    assert "{source_language}" not in text and "{text}" not in text
    request = mocker.patch.object(client, "_request", return_value="使用铁锭给 " + marker)
    assert client.translate(source, "物品说明") == "使用铁锭给 Create"
    user, system = request.call_args.args
    assert first["messages"] == [{"role": "system", "content": system}, {"role": "user", "content": user}]
    assert client.prompt_previews[0]["messages"] == first["messages"]


def test_api_preview_budget_excludes_terms_that_will_not_be_injected(mocker):
    budget = len("Iron Ingot = 铁锭\n".encode())
    settings = api_settings(term_tokens=budget)
    client, _ = configured_client(mocker, settings, [])
    record = client.preview("Iron Ingot and Gold Ingot")["prompt_preview"][0]
    assert record["terms"] == [{"source": "Iron Ingot", "translation": "铁锭"}]
    assert "Gold Ingot 翻译成 金锭" not in json.dumps(record, ensure_ascii=False)


def test_actual_preview_contains_the_masked_attempt_only_when_it_was_used(mocker):
    settings = api_settings()
    client, requests = configured_client(mocker, settings, ["葡萄", "{{0}}葡萄{{1}}"])
    client.config.capture_prompts = True
    expected = client.preview("&bGrapes&r")
    with client:
        assert client.translate("&bGrapes&r") == "&b葡萄&r"
    assert len(client.prompt_previews) == len(requests) == 2
    for record, request, predicted in zip(client.prompt_previews, requests, expected["prompt_preview"], strict=True):
        assert record["messages"] == json.loads(request.content)["messages"] == predicted["messages"]
    assert "{{0}}" in client.prompt_previews[1]["messages"][-1]["content"]


def test_local_preview_uses_real_token_budget_without_generation(mocker):
    model, _ = fake_llama(mocker)
    settings = Settings(glossary="", glossary_inline='{"Iron Ingot":"铁锭","Gold Ingot":"金锭"}',
                        term_tokens=len("Iron Ingot 翻译成 铁锭\n".encode()))
    cfg = config_for(Job("translate", text="Iron", capture_prompts=True, **settings.model_options()))
    engine = LocalEngine(cfg)
    try:
        record = engine.preview("Iron Ingot and Gold Ingot", "物品")["prompt_preview"][0]
        model.create_chat_completion.assert_not_called()
        assert record["terms"] == [{"source": "Iron Ingot", "translation": "铁锭"}]
        model.create_chat_completion.return_value = {"choices": [{"message": {"content": "铁锭和金锭"}}]}
        assert engine.translate("Iron Ingot and Gold Ingot", "物品") == "铁锭和金锭"
        assert record["messages"] == model.create_chat_completion.call_args.kwargs["messages"]
        assert engine.prompt_previews[0]["messages"] == record["messages"]
    finally:
        engine.close()


def test_preview_task_does_not_require_api_credentials_or_http_session(mocker):
    session = mocker.patch("mcpacklocalizer.core.translation.api.httpx.Client")
    job = Job("preview-prompt", engine="api", api_model="model", api_base_url="https://example.test/v1",
              api_key_env="UNSET_PREVIEW_SECRET", glossary_inline='{"Iron Ingot":"铁锭"}',
              no_glossary=False, glossary="", text="Iron Ingot")
    result = execute(Job.from_payload(job.payload()))
    session.assert_not_called()
    assert "铁锭" in json.dumps(result, ensure_ascii=False)
    assert "UNSET_PREVIEW_SECRET" not in json.dumps(result)


def test_local_preview_task_uses_the_resident_model_worker(mocker):
    factory = mocker.patch("mcpacklocalizer.application.tasks.service.WorkerClient")
    client = factory.return_value.__enter__.return_value
    client.preview.return_value = {"prompt_preview": [], "translation_skipped": True}
    result = execute(Job("preview-prompt", text="123", no_glossary=True))
    client.preview.assert_called_once_with("123", "")
    client.translate.assert_not_called()
    assert result["translation_skipped"]


def test_failed_translation_still_returns_the_prompts_used_for_review(mocker):
    factory = mocker.patch("mcpacklocalizer.application.tasks.service.translation_client")
    client = factory.return_value.__enter__.return_value
    client.translate.side_effect = ValueError("译文修改了保留符")
    client.prompt_previews = [{"attempt": 1, "messages": [{"role": "user", "content": "原文"}], "terms": []}]
    job = Job("translate", text="Iron", capture_prompts=True, no_glossary=True)
    result = execute(job)
    assert result["error"] == "译文修改了保留符" and result["prompt_preview"] == client.prompt_previews
    with pytest.raises(ValueError):
        execute(Job("translate", text="Iron", no_glossary=True))


def test_entirely_protected_source_does_not_fabricate_a_model_prompt(mocker):
    settings = api_settings()
    client, _ = configured_client(mocker, settings, [])
    assert client.preview("Create") == {"prompt_preview": [], "translation_skipped": True}


def test_preview_reports_excessive_context_without_truncating_source(mocker):
    settings = api_settings()
    client, _ = configured_client(mocker, settings, [])
    client.config.context_size = 256
    source = "Iron Ingot " * 100
    record = client.preview(source)["prompt_preview"][0]
    assert record["within_budget"] is False
    assert source in record["messages"][-1]["content"]


def test_api_trial_returns_rejected_translation_and_restores_known_markers(mocker):
    settings = api_settings()
    client, requests = configured_client(mocker, settings, ["葡萄", "{{0}}葡萄"])
    client.config.capture_prompts = True
    mocker.patch("mcpacklocalizer.application.tasks.service.translation_client", return_value=client)
    result = execute(Job("translate", text="&bGrapes&r", capture_prompts=True, **settings.model_options()))
    assert result["translation"] == "&b葡萄" and "保留符" in result["guard_warning"]
    assert result["quality_warnings"][0]["missing"] == ["&r"]
    assert len(requests) == len(result["prompt_preview"]) == 2


@pytest.mark.parametrize("protocol", ["openai", "anthropic", "gemini"])
def test_api_trial_keeps_truncated_provider_content_with_warning(mocker, protocol):
    settings = api_settings(protocol=protocol)
    raw = '<translation>铁'
    data = ({"choices": [{"message": {"content": raw}, "finish_reason": "length"}]} if protocol == "openai" else
            {"content": [{"type": "text", "text": raw}], "stop_reason": "max_tokens"} if protocol == "anthropic" else
            {"candidates": [{"content": {"parts": [{"text": raw}]}, "finishReason": "MAX_TOKENS"}]})
    transport = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data)))
    mocker.patch("mcpacklocalizer.core.translation.api.httpx.Client", return_value=transport)
    result = execute(Job("translate", text="Iron", capture_prompts=True, **settings.model_options()))
    assert result["translation"] == raw and result["guard_warning"] and "error" not in result


def test_local_trial_preserves_rejected_translation_and_strict_calls_still_fail(mocker):
    settings = Settings(glossary_enabled=False)
    model, _ = fake_llama(mocker)
    model.create_chat_completion.side_effect = [
        {"choices": [{"message": {"content": "葡萄"}, "finish_reason": "stop"}]},
        {"choices": [{"message": {"content": "{{1}}葡萄{{0}}"}, "finish_reason": "stop"}]}]
    args = Job("translate", text="&bGrapes&r", capture_prompts=True, **settings.model_options())
    engine = LocalEngine(config_for(args))
    factory = mocker.patch("mcpacklocalizer.application.tasks.service.translation_client")
    factory.return_value.__enter__.return_value = engine
    result = execute(args)
    assert result["translation"] == "&r葡萄&b" and "保留符" in result["guard_warning"]
    assert result["quality_warnings"][0]["reordered"]
    model.create_chat_completion.side_effect = None
    model.create_chat_completion.return_value = {"choices": [{"message": {"content": "葡萄"}, "finish_reason": "stop"}]}
    with pytest.raises(ValueError, match="保留符"):
        execute(Job("translate", text="&bGrapes&r", **settings.model_options()))


def test_local_worker_keeps_diagnostic_candidate_on_error():
    client = WorkerClient(config_for(Job("translate", text="Iron", no_glossary=True)))
    client.messages.put({"error": "译文修改了保留符", "rejected_translation": "葡萄", "prompt_preview": []})
    with pytest.raises(RuntimeError, match="保留符"):
        client._receive()
    assert client.rejected_translation == "葡萄"


def test_api_trial_network_error_has_no_model_content_or_credentials(mocker):
    settings = api_settings()
    transport = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401, text="private-key")))
    mocker.patch("mcpacklocalizer.core.translation.api.httpx.Client", return_value=transport)
    result = execute(Job("translate", text="Iron", capture_prompts=True, **settings.model_options()))
    assert "401" in result["error"] and "translation" not in result
    assert "private-key" not in json.dumps(result)
