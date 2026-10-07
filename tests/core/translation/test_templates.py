# [Module: tests.translation.templates] [Status: 已完成] [Brief: 完整模板渲染、接口消息、索引模型协议与任务快照回归]
import json
import sys
from dataclasses import asdict, replace
from types import SimpleNamespace

import httpx
import pytest

from mcpacklocalizer.application.config.settings import Settings
from mcpacklocalizer.application.tasks.jobs import Job
from mcpacklocalizer.application.tasks.service import config_for
from mcpacklocalizer.core.translation.api import ApiClient, ApiProfile, index_profile
from mcpacklocalizer.core.translation.local import LocalEngine, ModelConfig, render_prompt
from mcpacklocalizer.core.translation.templates import BUILTIN_TEMPLATES, PromptTemplate, render_template
from tests.core.translation.test_translation import fake_llama


def test_source_and_reference_data_are_expanded_once():
    template = PromptTemplate("test", "测试", system="{source_language}→{target_language}\n{glossary}\n{context}",
                              user='{text}\n示例：{"text":"value"}；保留 {player}')
    user, system = render_template(template, "Use {target_language} [[literal]]", "en_us", "ja_jp",
                                   [("Use", "{context}")], "保留 {source_language}")
    assert user == 'Use {target_language} [[literal]]\n示例：{"text":"value"}；保留 {player}'
    assert system == "英语（美国）→日语\nUse 翻译成 {context}\n保留 {source_language}"


def test_hy_preset_keeps_official_direct_and_masked_prompts():
    for markers in ((), ("{{0}}", "{{1}}")):
        from mcpacklocalizer.core.translation.local import preservation_rules
        text = "{{0}}Iron{{1}}" if markers else "Iron"
        user, system = render_template(BUILTIN_TEMPLATES["hy_mt"], text, "en_us", "zh_cn",
                                       [("Iron", "铁")], "物品", preservation_rules(text, markers) if markers else "")
        assert user == render_prompt(text, [("Iron", "铁")], "物品", markers=markers)
        assert not system and "[[" not in user


@pytest.mark.parametrize("terms,context,preservation", [
    ([], "", ""), ([("Iron Ingot", "铁锭")], "", ""),
    ([], "物品", ""), ([], "", "标记：{{0}}\n数量和顺序不变。"),
    ([("Iron Ingot", "铁锭")], "物品", "标记：{{0}}"),
])
def test_index_single_line_optional_blocks_keep_rendered_request(terms, context, preservation):
    template = BUILTIN_TEMPLATES["index"]
    previous = replace(template, user=template.user.replace("}]]\n", "}\n]]"))
    current = render_template(template, "Iron Ingot", "en_us", "zh_cn", terms, context, preservation)
    assert current == render_template(previous, "Iron Ingot", "en_us", "zh_cn", terms, context, preservation)
    assert "[[" not in current[0] and "]]" not in current[0]


def test_empty_inline_optional_block_keeps_the_surrounding_line_break():
    template = PromptTemplate("test", "测试", user="参考[[：{glossary}]]\n{text}")
    user, _ = render_template(template, "Iron Ingot", "en_us", "zh_cn")
    assert user == "参考\nIron Ingot"


@pytest.mark.parametrize("user", ["只有指令", "[[{context}{text}]]", "{text}[[未关闭"])
def test_invalid_template_cannot_drop_source(user):
    with pytest.raises(ValueError):
        PromptTemplate("test", "测试", user=user).validate()


@pytest.mark.parametrize("url,group,expected", [
    ("http://127.0.0.1:1234/v1", "auto", 1), ("http://localhost:8080/v1", "auto", 1),
    ("http://192.168.1.10:8080/v1", "auto", 1), ("http://[::1]:8080/v1", "auto", 1),
    ("https://example.test/v1", "auto", 3), ("https://example.test/v1", "local", 1),
])
def test_api_default_concurrency_follows_deployment(url, group, expected):
    assert ApiProfile(id="test", base_url=url, group=group).concurrency == expected


def test_explicit_concurrency_survives_configuration_roundtrip():
    profile = ApiProfile(id="test", model="model", concurrency=5)
    settings = Settings(api_profiles=[asdict(profile)])
    assert Settings.from_dict(asdict(settings)).api_profiles[0]["concurrency"] == 5


def test_legacy_prompt_and_profile_migrate_to_complete_editable_template():
    settings = Settings.from_dict({"system_prompt": "旧系统提示词：{context}",
                                   "api_profiles": [{"id": "old", "model": "model"}], "active_api": "old", "engine": "api"})
    assert settings.selected_profile().template_id == "mc"
    cfg = config_for(Job("translate", text="Iron", **settings.model_options()))
    assert cfg.system_prompt == "旧系统提示词：{context}"
    assert "{text}" in cfg.prompt_user and "{target_language}" in cfg.prompt_user
    assert "{glossary}" in cfg.prompt_user and "{context}" not in cfg.prompt_user
    assert Settings.from_dict(asdict(settings)) == settings


def test_saved_job_contains_template_snapshot_after_template_is_edited():
    profile = index_profile()
    settings = Settings(engine="api", active_api=profile.id, api_profiles=[asdict(profile)])
    job = Job.from_payload(Job("translate", text="Iron Ingot", **settings.model_options()).payload())
    changed = settings.store_template(replace(settings.templates()["index"], user="新模板：{text}"))
    cfg = config_for(Job.from_payload(job.payload()))
    assert cfg.prompt_user != changed.model_options()["prompt_user"]
    restored = config_for(Job("resume", output="D:/tasks/checkpoint"), asdict(cfg))
    assert restored.prompt_user == cfg.prompt_user and restored.prompt_template_id == "index"


def test_local_model_binding_is_restored_when_switching_models():
    template = replace(BUILTIN_TEMPLATES["index"], id="my-index", name="我的 Index", user="自定义：{text}")
    settings = Settings(model="D:/models/hy.gguf").store_template(template)
    settings = settings.select_local_model("D:/models/Index-Translate-2B.Q4_K_M.gguf", "index-2b")
    settings = settings.bind_local_template(template.id)
    settings = settings.select_local_model("D:/models/hy.gguf", "7b")
    assert settings.local_template_id == "hy_mt"
    settings = settings.select_local_model("D:/models/Index-Translate-2B.Q4_K_M.gguf", "index-2b")
    assert settings.local_template_id == template.id
    assert Settings.from_dict(asdict(settings)).local_template_id == template.id


def configured_client(mocker, settings, responses):
    captured = []
    results = iter(responses)
    def handle(request):
        captured.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": next(results)}, "finish_reason": "stop"}]})
    transport = httpx.Client(transport=httpx.MockTransport(handle))
    mocker.patch("mcpacklocalizer.core.translation.api.httpx.Client", return_value=transport)
    options = settings.model_options()
    cfg = config_for(Job("translate", text="Iron", **options))
    return ApiClient(cfg, options["credentials"]), captured


def test_api_sends_exact_custom_template_without_hidden_translation_instruction(mocker):
    template = PromptTemplate("specific", "特定模型", system="{source_language}到{target_language}", user="正文：{text}")
    profile = ApiProfile(id="test", model="model", template_id=template.id)
    settings = Settings(engine="api", active_api="test", api_profiles=[asdict(profile)]).store_template(template)
    client, requests = configured_client(mocker, settings, ["铁锭"])
    with client:
        assert client.translate("Iron Ingot") == "铁锭"
    assert json.loads(requests[0].content)["messages"] == [
        {"role": "system", "content": "英语（美国）到简体中文"}, {"role": "user", "content": "正文：Iron Ingot"}]


def test_official_index_api_uses_local_template_and_disables_thinking(mocker):
    profile = index_profile()
    settings = Settings(engine="api", active_api=profile.id, api_profiles=[asdict(profile)],
                        glossary_enabled=False, source_locale="en_us", target_locale="ja_jp")
    client, requests = configured_client(mocker, settings, ["鉄インゴット"])
    with client:
        assert client.translate("Iron Ingot") == "鉄インゴット"
    payload = json.loads(requests[0].content)
    expected, _ = render_template(settings.templates()["index"], "Iron Ingot", "en_us", "ja_jp")
    assert payload["messages"] == [{"role": "user", "content": expected}]
    assert str(requests[0].url) == "https://index-translate.bilibili.com/v1/chat/completions"
    assert "authorization" not in requests[0].headers
    assert requests[0].headers["user-agent"] == "Index-Translate-Client/1.0"
    assert payload["chat_template_kwargs"]["enable_thinking"] is False


def test_custom_hy_local_template_is_used_on_direct_and_masked_attempts(mocker):
    model, _ = fake_llama(mocker)
    model.create_chat_completion.side_effect = [
        {"choices": [{"message": {"content": "铁"}}]},
        {"choices": [{"message": {"content": "{{0}}铁{{1}}"}}]},
    ]
    template = replace(BUILTIN_TEMPLATES["hy_mt"], user="我的模型：{text}\n{preservation_rules}")
    settings = Settings(glossary_enabled=False).store_template(template)
    cfg = config_for(Job("translate", text="Iron", **settings.model_options()))
    engine = LocalEngine(cfg)
    try:
        assert engine.translate("&bIron&r") == "&b铁&r"
        calls = model.create_chat_completion.call_args_list
        assert calls[0].kwargs["messages"][0]["content"].startswith("我的模型：&bIron&r")
        assert calls[1].kwargs["messages"][0]["content"].startswith("我的模型：{{0}}Iron{{1}}")
        assert "占位符须原样保留" in calls[1].kwargs["messages"][0]["content"]
    finally:
        engine.close()


def test_index_local_installs_embedded_chat_template_with_thinking_off(mocker):
    model, _ = fake_llama(mocker)
    model.detokenize.return_value = b"<eos>"
    formatter = mocker.Mock()
    constructor = mocker.Mock(return_value=formatter)
    mocker.patch.dict(sys.modules, {"llama_cpp.llama_chat_format": SimpleNamespace(Jinja2ChatFormatter=constructor)})
    cfg = ModelConfig(prompt_family="index", prompt_user=BUILTIN_TEMPLATES["index"].user,
                      system_prompt="", target_locale="ja_jp", glossary=None)
    engine = LocalEngine(cfg)
    try:
        assert constructor.call_args.kwargs["template"].startswith("{% set enable_thinking = false %}")
        assert model.chat_handler == formatter.to_chat_handler.return_value
    finally:
        engine.close()


def test_index_runtime_keeps_thinking_off_when_testing_a_large_model_template(mocker):
    profile = index_profile()
    settings = Settings(engine="api", active_api=profile.id, api_profiles=[asdict(profile)], glossary_enabled=False)
    options = settings.model_options()
    template = settings.templates()["mc"]
    options.update(prompt_family=template.family, prompt_template_id=template.id,
                   system_prompt=template.system, prompt_user=template.user, api_extra_body="{}")
    cfg = config_for(Job("translate", text="Iron Ingot", **options))
    client = ApiClient(cfg)
    user, system = render_template(template, "Iron Ingot", "en_us", "zh_cn")
    _, body = client._payload(user, system)
    assert body["chat_template_kwargs"]["enable_thinking"] is False
    assert body["messages"][-1]["content"] == user
    assert body["messages"][0]["content"] == system


def test_hy_model_language_limit_remains_when_testing_another_template():
    settings = Settings(model="D:/models/Hy-MT2-7B-Q4_K_M.gguf", source_locale="ja_jp", target_locale="en_us")
    options = settings.model_options()
    template = settings.templates()["mc"]
    options.update(prompt_family=template.family, prompt_template_id=template.id,
                   system_prompt=template.system, prompt_user=template.user)
    with pytest.raises(ValueError, match="HY-MT-2 输出中文"):
        config_for(Job("translate", text="剣", **options))


def test_local_index_keeps_its_generation_parameters_with_a_temporary_mc_template(mocker):
    model, _ = fake_llama(mocker)
    model.detokenize.return_value = b"<eos>"
    model.create_chat_completion.return_value = {"choices": [{"message": {"content": "铁锭"}}]}
    formatter = mocker.Mock()
    constructor = mocker.Mock(return_value=formatter)
    mocker.patch.dict(sys.modules, {"llama_cpp.llama_chat_format": SimpleNamespace(Jinja2ChatFormatter=constructor)})
    template = BUILTIN_TEMPLATES["mc"]
    cfg = ModelConfig(model_family="index", prompt_family="mc", prompt_user=template.user,
                      system_prompt=template.system, glossary=None)
    engine = LocalEngine(cfg)
    try:
        assert engine.translate("Iron Ingot") == "铁锭"
        assert constructor.call_args.kwargs["template"].startswith("{% set enable_thinking = false %}")
        request = model.create_chat_completion.call_args.kwargs
        assert request["temperature"] == 0.0
        assert request["messages"][0]["role"] == "system"
        assert "Minecraft 整合包翻译者" in request["messages"][0]["content"]
    finally:
        engine.close()
