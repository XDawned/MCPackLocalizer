# [Module: tests.tasks_polishing] [Status: 已完成] [Brief: 修润任务协议、接口隔离、部分失败与检查点修订记录]
import json
from dataclasses import asdict

import httpx
import pytest

from mcpacklocalizer.application.config.settings import Settings
from mcpacklocalizer.application.tasks.jobs import Job
from mcpacklocalizer.application.tasks.requests import polish_job
from mcpacklocalizer.application.tasks.service import execute
from mcpacklocalizer.application.tasks.store import load_task
from mcpacklocalizer.application.tasks.worker import perform
from mcpacklocalizer.core.pack.extraction import Entry, Scan
from mcpacklocalizer.core.pack.snapshots import Store
from mcpacklocalizer.core.translation.api import ApiProfile


def preferences():
    profile = ApiProfile(id="polisher", name="修润接口", model="large", base_url="https://example.test/v1",
                         api_key="private-secret", concurrency=2, request_interval=0.0)
    return Settings(engine="local", polish_api=profile.id, api_profiles=[asdict(profile)], glossary_enabled=False)


def create_task(tmp_path, entries, **options):
    output = tmp_path / "task"
    scan = Scan(str(tmp_path / "game"), "pack", options.get("source_locale", "en_us"),
                options.get("target_locale", "zh_cn"), entries=entries,
                metadata={"model_config": {"engine": "local", "allow_missing_placeholders": True}})
    with Store(output, create=True) as store:
        store.create(scan)
    return output


def entry(key, source="Iron Ingot", translation="旧译文", **options):
    return Entry(key, key, "a.json", [key], source, 0, 1, key, translation=translation, **options)


def mock_api(mocker, callback):
    def handle(request):
        user = json.loads(json.loads(request.content)["messages"][-1]["content"])
        assert request.headers["Authorization"] == "Bearer private-secret"
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(callback(user))},
                                                     "finish_reason": "stop"}],
                                       "usage": {"prompt_tokens": 20, "completion_tokens": 5}})

    client = httpx.Client(transport=httpx.MockTransport(handle))
    mocker.patch("mcpacklocalizer.core.translation.api.httpx.Client", return_value=client)


def test_job_roundtrip_uses_independent_api_and_validates_selection():
    prefs = preferences()
    args = polish_job("D:/task", ["one", "two"], prefs, "polish")
    assert args.engine == "api" and args.api_model == "large" and args.concurrency == 2
    assert args.credentials == {"polisher": "private-secret"}
    assert args.polish_prompt == prefs.polish_prompt
    assert prefs.engine == "local"
    assert Job.from_payload(args.payload()) == args
    assert Settings.from_dict(asdict(prefs)) == prefs
    for ids in ([], ["one", "one"], [1], "one"):
        with pytest.raises(ValueError):
            polish_job("D:/task", ids, prefs)
    prefs.api_profiles[0].update(prompt_mode="hy_mt", interface_type="translation", template_id="hy_mt")
    with pytest.raises(ValueError, match="大模型"):
        polish_job("D:/task", None, prefs)


def test_selected_polishing_preserves_failed_translation_and_records_previous_values(tmp_path, mocker, capsys):
    output = create_task(tmp_path, [entry("one", "&bGrapes&r", "&b旧葡萄&r", status="reviewed", origin="manual"),
                                   entry("two", "Keep ${player}", "保留${player}", status="reviewed", origin="manual"),
                                   entry("three", translation="不要修改")])
    mock_api(mocker, lambda user: {"translation": "&b葡萄&r" if user["context"] == "one" else "已损坏"})
    result = execute(polish_job(str(output), ["one", "two"], preferences()))
    assert (result["polished_this_run"], result["failed_this_run"], result["partial"]) == (1, 1, True)
    scan = load_task(str(output))
    one, two, three = scan.entries
    assert (one.translation, one.status, one.origin) == ("&b旧葡萄&r", "reviewed", "manual")
    assert (two.translation, two.status, two.origin) == ("保留${player}", "reviewed", "manual")
    assert two.error == "" and three.translation == "不要修改"
    run = scan.metadata["polish_runs"][-1]
    assert run["previous"]["one"]["translation"] == "&b旧葡萄&r"
    assert run["previous"]["one"]["status"] == "reviewed"
    assert run["results"]["one"]["translation"] == "&b葡萄&r"
    assert run["results"]["two"]["translation"] == "已损坏"
    assert "${player}" in run["results"]["two"]["error"]
    assert json.loads(run["results"]["two"]["raw_response"])["translation"] == "已损坏"
    assert run["api_usage"] == {"requests": 2, "input_tokens": 40, "output_tokens": 10}
    assert scan.metadata["model_config"] == {"engine": "local", "allow_missing_placeholders": True}
    assert "private-secret" not in json.dumps(scan.to_dict())
    progress = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert len(progress) == 2 and progress[-1]["remaining"] == 0
    assert progress[-1]["completed"] == 1 and progress[-1]["failed"] == 1


def test_all_scope_includes_untranslated_and_keeps_checkpoint_language_pair(tmp_path, mocker):
    output = create_task(tmp_path, [entry("one", "鉄の剣", None), entry("two", "鉄の剣", "Wrong Sword")],
                         source_locale="ja_jp", target_locale="en_us")
    calls = []

    def reply(user):
        calls.append(user)
        return {"translation": "Iron Sword"}

    mock_api(mocker, reply)
    result = execute(polish_job(str(output), None, preferences(), "polish"))
    assert result["polished_this_run"] == 2 and not result["partial"]
    assert [item.translation for item in load_task(str(output)).entries] == [None, "Wrong Sword"]
    accepted = execute(Job("polish-accept", output=output, polish_run_id=result["run_id"],
                           polish_updates={"one": "Iron Sword", "two": "Iron Sword"}))
    assert accepted["accepted"] == 2
    assert all(item.translation == "Iron Sword" for item in load_task(str(output)).entries)
    assert len(calls) == 2 and {call["translation"] for call in calls} == {"", "Wrong Sword"}
    assert all(call["target_language"] == "英语（美国）" for call in calls)


def test_unknown_selection_is_rejected_before_api_or_changes(tmp_path, mocker):
    output = create_task(tmp_path, [entry("one")])
    client = mocker.patch("mcpacklocalizer.application.tasks.polishing.PolishApiClient")
    with pytest.raises(ValueError, match="不存在"):
        execute(polish_job(str(output), ["missing"], preferences()))
    client.assert_not_called()
    assert "polish_runs" not in load_task(str(output)).metadata


def test_script_and_patchouli_results_are_validated_before_commit(tmp_path, mocker):
    marker = "{{MCPL_123456abcdef_0}}"
    output = create_task(tmp_path, [entry("script", "§aYou got " + marker + " items", "§a得到 " + marker + " 件",
                                         script={"line": 1}),
                                   entry("book", "$(l:entry)Iron$(/l)", "$(l:entry)旧铁$(/l)",
                                         patchouli={"role": "text", "macros": []})])

    def reply(user):
        return {"slots": ["§a获得 ", " 件物品"]} if user["context"] == "script" else {"translation": "$(l:entry)铁"}

    mock_api(mocker, reply)
    result = execute(polish_job(str(output), None, preferences()))
    assert result["polished_this_run"] == 1 and result["failed_this_run"] == 1
    script, book = load_task(str(output)).entries
    assert script.translation == "§a得到 " + marker + " 件"
    assert book.translation == "$(l:entry)旧铁$(/l)" and book.error == ""
    run = load_task(str(output)).metadata["polish_runs"][-1]
    assert run["results"]["script"]["translation"] == "§a获得 " + marker + " 件物品"
    assert "帕秋莉" in run["results"]["book"]["error"]
    assert run["results"]["book"]["translation"] == "$(l:entry)铁"


def test_pausing_preserves_committed_results_and_exports_checkpoint(tmp_path, mocker, capsys):
    output = create_task(tmp_path, [entry("one"), entry("two")])
    prefs = preferences()
    prefs.api_profiles[0]["concurrency"] = 1
    model = mocker.patch("mcpacklocalizer.application.tasks.polishing.PolishApiClient").return_value.__enter__.return_value
    model.propose.side_effect = [{"translation": "铁锭", "raw_response": '{"translation":"铁锭"}', "error": ""}, KeyboardInterrupt()]
    model.usage_snapshot.return_value = {"requests": 1, "input_tokens": 20, "output_tokens": 5}
    assert perform(polish_job(str(output), None, prefs)) == 130
    one, two = load_task(str(output)).entries
    assert one.translation == "旧译文" and two.translation == "旧译文"
    assert load_task(str(output)).metadata["polish_runs"][-1]["results"]["one"]["translation"] == "铁锭"
    assert (output / "snapshot.json").is_file()
    assert json.loads(capsys.readouterr().out)["error"].startswith("任务已暂停")


def test_accepting_manually_repaired_failure_rechecks_and_preserves_raw_response(tmp_path, mocker):
    output = create_task(tmp_path, [entry("one", "&bGrapes&r", "&b旧葡萄&r"), entry("two", "Keep ${player}", "保留${player}")])
    mock_api(mocker, lambda user: {"translation": "葡萄" if user["context"] == "one" else "已损坏"})
    result = execute(polish_job(str(output), None, preferences()))
    scan = load_task(str(output))
    assert result["failed_this_run"] == 2
    with pytest.raises(ValueError, match="非空"):
        execute(Job("polish-accept", output=output, polish_run_id=result["run_id"],
                    polish_updates={"one": "&b葡萄&r", "two": ""}))
    assert [item.translation for item in load_task(str(output)).entries] == ["&b旧葡萄&r", "保留${player}"]
    execute(Job("polish-accept", output=output, polish_run_id=result["run_id"], polish_updates={"one": "&b葡萄&r"}))
    accepted = load_task(str(output))
    assert accepted.entries[0].translation == "&b葡萄&r" and accepted.entries[0].status == "reviewed"
    assert accepted.entries[1].translation == "保留${player}"
    proposal = accepted.metadata["polish_runs"][-1]["results"]["one"]
    assert proposal["accepted"] and proposal["edited"] and proposal["translation"] == "葡萄"
    assert proposal["raw_response"] == scan.metadata["polish_runs"][-1]["results"]["one"]["raw_response"]


def test_accepting_guard_warning_keeps_candidate_and_marks_manual_reviewed(tmp_path, mocker):
    output = create_task(tmp_path, [entry("one", "&bGrapes&r", "&b旧葡萄&r")])
    mock_api(mocker, lambda user: {"translation": "葡萄"})
    result = execute(polish_job(str(output), None, preferences()))
    execute(Job("polish-accept", output=output, polish_run_id=result["run_id"], polish_updates={"one": "葡萄"}))
    scan = load_task(str(output))
    saved = scan.entries[0]
    assert (saved.translation, saved.status, saved.origin, saved.error) == ("葡萄", "reviewed", "manual", "")
    proposal = scan.metadata["polish_runs"][-1]["results"]["one"]
    assert proposal["accepted"] and proposal["error"] and not proposal["edited"]


def test_accepting_stale_proposal_does_not_overwrite_new_manual_edit(tmp_path, mocker):
    output = create_task(tmp_path, [entry("one")])
    mock_api(mocker, lambda user: {"translation": "铁锭"})
    result = execute(polish_job(str(output), None, preferences()))
    execute(Job("review", output=output, entry_id="one", translation="人工的新译文"))
    with pytest.raises(ValueError, match="已被修改"):
        execute(Job("polish-accept", output=output, polish_run_id=result["run_id"], polish_updates={"one": "铁锭"}))
    assert load_task(str(output)).entries[0].translation == "人工的新译文"


def test_accepting_bad_script_structure_is_atomic(tmp_path, mocker):
    marker = "{{MCPL_123456abcdef_0}}"
    output = create_task(tmp_path, [entry("one"), entry("two", "Hello " + marker, "你好 " + marker, script={"line": 1})])
    mock_api(mocker, lambda user: {"translation": "铁锭"} if user["context"] == "one" else {"slots": ["您好 ", ""]})
    result = execute(polish_job(str(output), None, preferences()))
    with pytest.raises(ValueError, match="表达式占位符"):
        execute(Job("polish-accept", output=output, polish_run_id=result["run_id"],
                    polish_updates={"one": "铁锭", "two": "没有表达式"}))
    assert [item.translation for item in load_task(str(output)).entries] == ["旧译文", "你好 " + marker]
