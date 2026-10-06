import json
from dataclasses import asdict, replace

import httpx

from mcpacklocalizer.application.config.settings import Settings
from mcpacklocalizer.application.tasks.requests import PackRequest, PatchOptions, pack_job, review_job, task_job
from mcpacklocalizer.application.tasks.resources import resource_groups
from mcpacklocalizer.application.tasks.service import execute
from mcpacklocalizer.application.tasks.store import load_task
from mcpacklocalizer.core.translation.api import ApiProfile


def test_recognition_translation_and_review_keep_original_language_pair(tmp_path, mocker):
    root = tmp_path / "game"
    source = root / "kubejs/assets/demo/lang/ja_jp.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"item.demo.sword": "鉄の剣"}), encoding="utf-8")
    # A different source locale must not enter this task.
    source.with_name("zh_cn.json").write_text('{"item.demo.sword":"铁剑"}', encoding="utf-8")
    profile = ApiProfile(id="remote", model="model", base_url="https://example.test/v1")
    settings = Settings(engine="api", active_api=profile.id, api_profiles=[asdict(profile)],
                        source_locale="ja_jp", target_locale="en_us", glossary_enabled=False)
    output = tmp_path / "task"
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Iron Sword"}, "finish_reason": "stop"}]})

    client = httpx.Client(transport=httpx.MockTransport(handle))
    mocker.patch("mcpacklocalizer.core.translation.api.httpx.Client", return_value=client)
    execute(pack_job("extract", PackRequest(str(root), str(output)), settings, PatchOptions()))
    assert requests == []  # Recognition never invokes a model.
    scan = load_task(str(output))
    assert [entry.source for entry in scan.entries] == ["鉄の剣"]
    assert resource_groups(scan) == {"KubeJS 语言文件": [("kubejs/assets/demo/lang/ja_jp.json", 1)]}
    current = replace(settings, source_locale="en_us", target_locale="zh_cn")
    execute(task_job("resume", str(output), current, PatchOptions(), override_model=True))
    scan = load_task(str(output))
    assert (scan.source_locale, scan.target_locale) == ("ja_jp", "en_us")
    assert scan.metadata["model_config"]["target_locale"] == "en_us"
    assert "English (en_us)" in json.loads(requests[0].content)["messages"][-1]["content"]
    execute(review_job(str(output), scan.entries[0].id, "Steel Sword"))
    execute(task_job("export", str(output), current, PatchOptions()))
    patch = output / "patch/kubejs/assets/demo/lang/en_us.json"
    assert json.loads(patch.read_text(encoding="utf-8"))["item.demo.sword"] == "Steel Sword"
    assert not (output / "patch/kubejs/assets/demo/lang/zh_cn.json").exists()
