import json
from dataclasses import asdict
from pathlib import Path

import pytest

from mcpacklocalizer.application.config.settings import Settings
from mcpacklocalizer.application.tasks.jobs import Job
from mcpacklocalizer.application.tasks.requests import PatchOptions, task_job
from mcpacklocalizer.application.tasks.service import run_translation
from mcpacklocalizer.core.pack.extraction import Entry, Scan
from mcpacklocalizer.core.translation.api import ApiProfile
from mcpacklocalizer.core.translation.local import ModelConfig
from mcpacklocalizer.core.translation.script import ScriptApiClient


def prefs():
    profiles = [ApiProfile(id="ordinary", name="普通", model="small", api_key="ordinary-secret"),
                ApiProfile(id="scripts", name="脚本", model="large", api_key="script-secret")]
    return Settings(engine="api", active_api="ordinary", script_api="scripts", glossary="",
                    api_profiles=[asdict(profile) for profile in profiles])


def test_independent_script_profile_and_credentials_survive_request_roundtrip():
    settings = prefs()
    args = task_job("resume", "D:/task", settings, PatchOptions(), override_model=True)
    assert args.api_model == "small"
    assert args.script_config["api_model"] == "large"
    assert args.script_config["allow_missing_placeholders"] is False
    assert args.credentials == {"ordinary": "ordinary-secret", "scripts": "script-secret"}
    assert "secret" not in json.dumps(args.script_config)
    assert Job.from_payload(args.payload()) == args


def test_slot_protocol_preserves_spaces_and_rejects_arbitrary_code(mocker):
    config = ModelConfig(engine="api", api_model="large", api_base_url="http://localhost:1234/v1", glossary=None)
    client = ScriptApiClient(config)
    marker = "{{MCPL_123456abcdef_0}}"
    source = "§7You got " + marker + " items"
    request = mocker.patch.object(client, "_request", return_value=json.dumps({"slots": ["§7你获得了 ", " 件物品"]}))
    result = client.translate(source, "player.tell with count")
    assert result == "§7你获得了 " + marker + " 件物品"
    sent = json.loads(request.call_args.args[0])
    assert sent["slots"] == ["§7You got ", " items"]
    request.return_value = '{"slots":["Bad"],"code":"player.tell(123)"}'
    with pytest.raises(ValueError, match="JSON"):
        client.translate(source)


def test_mixed_task_routes_scripts_to_saved_large_model(mocker):
    settings = prefs()
    settings.api_profiles[0].update(timeout=45, max_tokens=1024, concurrency=2)
    settings.api_profiles[1].update(timeout=90, max_tokens=2048, concurrency=4)
    ordinary = Entry("normal", "lang:name", "lang.json", ["name"], "Iron Ingot", 1, 2, "name")
    script = Entry("script", "kubejs:message", "kubejs/server_scripts/a.js", ["tell", 0], "Hello", 1, 2,
                   "tell", script={"line": 1})
    scan = Scan("D:/pack", "pack", "en_us", "zh_cn", entries=[ordinary, script])
    store = mocker.Mock(output=Path("D:/task"))
    store.load.return_value = scan
    mocker.patch("mcpacklocalizer.application.tasks.service.validate_sources")
    mocker.patch("mcpacklocalizer.application.tasks.service.export_task", return_value={})
    normal_factory = mocker.patch("mcpacklocalizer.application.tasks.service.ApiClient")
    script_factory = mocker.patch("mcpacklocalizer.application.tasks.service.ScriptApiClient")
    normal = normal_factory.return_value.__enter__.return_value
    large = script_factory.return_value.__enter__.return_value
    normal.translate.return_value, large.translate.return_value = "铁锭", "你好"
    for client in (normal, large):
        client.info = {"backend": "api"}
        client.usage_snapshot.return_value = {"requests": 1, "input_tokens": 12, "output_tokens": 4}
    result = run_translation(store, task_job("resume", "D:/task", settings, PatchOptions(), override_model=True))
    assert result["translated_this_run"] == 2
    assert normal_factory.call_args.args[0].api_model == "small"
    assert script_factory.call_args.args[0].api_model == "large"
    assert normal_factory.call_args.args[2] == 45 and script_factory.call_args.args[2] == 90
    assert normal_factory.call_args.args[0].max_tokens == 1024
    assert script_factory.call_args.args[0].max_tokens == 2048
    assert script_factory.call_args.args[0].concurrency == 4
    assert result["api_usage"]["requests"] == 2
    assert "secret" not in json.dumps(scan.metadata)
    assert [entry.translation for entry in scan.entries] == ["铁锭", "你好"]


def test_missing_script_profile_marks_scripts_failed_without_loading_local_model(mocker):
    entry = Entry("script", "kubejs:message", "a.js", [], "Hello", 1, 2, "tell", script={"line": 1})
    scan = Scan("D:/pack", "pack", "en_us", "zh_cn", entries=[entry])
    store = mocker.Mock(output=Path("D:/task"))
    store.load.return_value = scan
    mocker.patch("mcpacklocalizer.application.tasks.service.validate_sources")
    mocker.patch("mcpacklocalizer.application.tasks.service.export_task", return_value={})
    worker = mocker.patch("mcpacklocalizer.application.tasks.service.WorkerClient")
    result = run_translation(store, Job("resume", output="D:/task"))
    assert result["failed_this_run"] == 1 and entry.status == "failed"
    assert "大模型接口" in entry.error
    worker.assert_not_called()
