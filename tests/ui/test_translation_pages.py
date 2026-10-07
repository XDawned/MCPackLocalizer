# [Module: tests.translation_pages] [Status: 已完成] [Brief: 翻译页面、接口管理与桌面工作流回归]
import json
from dataclasses import asdict
from pathlib import Path

import pytest
from PyQt6.QtCore import QEvent, QItemSelectionModel, Qt
from PyQt6.QtTest import QTest

from mcpacklocalizer.application.config.settings import Settings
from mcpacklocalizer.application.tasks.jobs import Job
from mcpacklocalizer.application.tasks.service import execute
from mcpacklocalizer.application.tasks.store import load_task
from mcpacklocalizer.core.pack.extraction import Document, digest
from mcpacklocalizer.core.pack.patch import validate_output
from mcpacklocalizer.core.pack.snapshots import Store
from mcpacklocalizer.core.translation.api import ApiProfile
from mcpacklocalizer.ui.view.api.dialogs import AddApiDialog, ApiEditDialog, ApiParametersDialog
from mcpacklocalizer.ui.view.api.page import BUILTIN_LOCAL, profile_group
from mcpacklocalizer.ui.view.tasks.polish_dialog import PolishResultsDialog
from mcpacklocalizer.ui.view.window import MainWindow


@pytest.fixture
def window(qt_app, mocker, tmp_path):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"GGUF")
    preferences = mocker.Mock()
    preferences.value.side_effect = lambda key, default="": (
        json.dumps(asdict(Settings(glossary="", model=str(model)))) if key == "settings" else default)
    widget = MainWindow(preferences)
    mocker.patch.object(widget, "notify")
    yield widget
    if widget.rules.loader:
        widget.rules.loader.wait(5000)
        qt_app.processEvents()
    widget.close()
    widget.deleteLater()
    qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qt_app.processEvents()


def test_new_pages_construct_and_complete_templates_are_available(window):
    assert window.settings.engine == "local"
    assert window.api.cards[BUILTIN_LOCAL].active
    assert window.playground.engine.text().endswith("HY-MT-2 · 本地 GGUF")
    assert "按请求指定的标签返回完整译文" in window.prompts.prompt.toPlainText()
    assert "{text}" in window.prompts.user_prompt.toPlainText()


def test_playground_switches_to_bound_template_and_preserves_global_selection(window, mocker):
    from copy import deepcopy

    profiles = [ApiProfile(id="small", name="Index 本地 API", model="Index-Translate-2B", prompt_mode="index"),
                ApiProfile(id="large", name="大模型", model="large", base_url="https://example.test/v1")]
    for profile in profiles:
        window.api.store_profile(profile)
    saved = deepcopy(asdict(window.settings))
    page = window.playground
    page.interface.setCurrentIndex(page.interface.findData("small"))
    assert page.template.currentData() == "index"
    page.template.setCurrentIndex(page.template.findData("mc"))
    page.source.setPlainText("Iron Ingot")
    calls = []
    mocker.patch.object(window, "run_job", side_effect=lambda factory, label: calls.append(factory()))
    page.start()
    job = calls[0]
    assert job.engine == "api" and job.api_model == "Index-Translate-2B"
    assert job.prompt_template_id == "mc" and job.model_family == "index"
    assert job.prompt_user == window.settings.templates()["mc"].user
    assert asdict(window.settings) == saved
    page.interface.setCurrentIndex(page.interface.findData("large"))
    assert page.template.currentData() == "mc" and not page.custom_template
    page.interface.setCurrentIndex(page.interface.findData("small"))
    assert page.template.currentData() == "index" and not page.custom_template


def test_playground_free_api_can_be_tested_without_saving_or_activating_it(window, mocker):
    from mcpacklocalizer.core.translation.api import INDEX_PROFILE_ID
    page = window.playground
    page.interface.setCurrentIndex(page.interface.findData(INDEX_PROFILE_ID))
    page.source.setPlainText("Iron Ingot")
    calls = []
    mocker.patch.object(window, "run_job", side_effect=lambda factory, label: calls.append(factory()))
    page.start()
    assert calls[0].api_model == "Index-Translate-35B-A3B" and calls[0].prompt_template_id == "index"
    assert window.settings.engine == "local" and window.settings.api_profiles == []


def test_playground_refresh_retains_manual_template_and_updates_saved_template_content(window):
    from dataclasses import replace
    window.api.store_profile(ApiProfile(id="large", model="large"))
    page = window.playground
    page.interface.setCurrentIndex(page.interface.findData("large"))
    page.template.setCurrentIndex(page.template.findData("index_plain"))
    template = replace(window.settings.templates()["index_plain"], user="对比模板：{text}")
    window.save_settings(window.settings.store_template(template))
    assert page.interface.currentData() == "large" and page.template.currentData() == "index_plain"
    assert page.test_options()["prompt_user"] == "对比模板：{text}"
    window.prompts.edit_template("mc")
    window.switchTo(page)
    assert page.template.currentData() == "index_plain"


def test_playground_returns_to_local_when_selected_interface_is_removed(window):
    from dataclasses import replace
    window.api.store_profile(ApiProfile(id="temporary", model="model"))
    page = window.playground
    page.interface.setCurrentIndex(page.interface.findData("temporary"))
    window.save_settings(replace(window.settings, api_profiles=[]))
    assert page.interface.currentData() == BUILTIN_LOCAL
    assert page.template.currentData() == window.settings.local_template_id


def test_playground_controls_are_locked_during_a_running_test(window):
    page = window.playground
    page.set_busy(True)
    assert not page.interface.isEnabled() and not page.template.isEnabled() and not page.translate.isEnabled()
    assert page.stop.isEnabled()
    page.set_busy(False)
    assert page.interface.isEnabled() and page.template.isEnabled() and page.translate.isEnabled()
    assert not page.stop.isEnabled()


def test_playground_result_identifies_the_tested_template_and_clears_failed_result(window, mocker):
    page = window.playground
    page.template.setCurrentIndex(page.template.findData("index_plain"))
    page.source.setPlainText("Iron Ingot")
    mocker.patch.object(window, "run_job", side_effect=lambda factory, label: factory())
    page.start()
    page.template.setCurrentIndex(page.template.findData("mc"))
    page.show_result({"translation": "铁锭"})
    assert "Index-Translate 默认翻译" in page.hints.text()
    assert page.translation.toPlainText() == "铁锭"
    page.show_result({"error": "连接失败"})
    assert not page.translation.toPlainText() and "连接失败" in page.hints.text()
    page.show_result({}, cancelled=True)
    assert "试译已暂停" in page.hints.text()
    assert page.hints.text().count("Index-Translate 默认翻译") == 1


def test_playground_preview_builds_real_terms_and_context_without_credentials(window, mocker):
    from dataclasses import replace
    window.api.store_profile(ApiProfile(id="preview", model="Index-Translate-2B", prompt_mode="index",
                                       api_key="private-key", key_env="UNSET_TEST_PREVIEW_KEY"))
    window.save_settings(replace(window.settings, glossary_inline='{"Iron Ingot":"铁锭"}'))
    page = window.playground
    page.interface.setCurrentIndex(page.interface.findData("preview"))
    page.source.setPlainText("Iron Ingot")
    page.context.setText("任务章节")
    calls = []
    mocker.patch.object(window, "run_job", side_effect=lambda factory, label: calls.append((factory(), label)))
    session = mocker.patch("mcpacklocalizer.core.translation.api.httpx.Client")
    page.start_preview()
    job, label = calls[0]
    assert job.operation == "preview-prompt" and label == "提示词预览"
    assert job.api_key_env == "" and "private-key" not in json.dumps(job.payload())
    result = execute(Job.from_payload(job.payload()))
    session.assert_not_called()
    page.show_preview(result)
    assert "Iron Ingot→铁锭" in page.prompt_preview.toPlainText()
    assert "任务章节" in page.prompt_preview.toPlainText()
    assert "{glossary}" not in page.prompt_preview.toPlainText() and "{text}" not in page.prompt_preview.toPlainText()
    assert "预算内术语 1 项" in page.preview_hint.text()
    page.source.setPlainText("Gold Ingot")
    assert not page.prompt_preview.toPlainText() and not page.preview_records


def test_playground_shows_actual_masked_attempt_and_marks_it_as_a_real_request(window):
    page = window.playground
    records = [
        {"attempt": 1, "messages": [{"role": "user", "content": "将 &bIron&r 翻译成中文"}], "terms": []},
        {"attempt": 2, "messages": [{"role": "system", "content": "保留占位符"},
                                    {"role": "user", "content": "将 {{0}}Iron{{1}} 翻译成中文"}],
         "terms": [{"source": "Iron", "translation": "铁"}]},
    ]
    page.show_result({"translation": "&b铁&r", "prompt_preview": records})
    assert "&bIron&r" in page.prompt_preview.toPlainText()
    page.preview_attempt.setCurrentIndex(1)
    assert "{{0}}Iron{{1}}" in page.prompt_preview.toPlainText()
    assert "保留占位符" in page.prompt_preview.toPlainText()
    assert "本次实际请求" in page.preview_hint.text() and "Iron → 铁" in page.preview_hint.text()


def test_playground_preview_errors_and_skipped_source_are_visible(window):
    page = window.playground
    page.show_preview({"error": "未找到 GGUF 模型"})
    assert "未找到 GGUF" in page.preview_hint.text()
    page.show_preview({"prompt_preview": [], "translation_skipped": True})
    assert "无需向模型发送" in page.preview_hint.text()
    page.show_preview({}, cancelled=True)
    assert "预览已暂停" in page.preview_hint.text()


def test_preview_job_result_is_routed_back_to_the_playground(window, mocker):
    window.pending_label = "提示词预览"
    callback = mocker.patch.object(window.playground, "show_preview")
    workspace_result = mocker.patch.object(window.workspace, "show_result")
    result = {"prompt_preview": [], "translation_skipped": True}
    window.job_done(0, result, False)
    callback.assert_called_once_with(result, False)
    workspace_result.assert_not_called()


def test_runtime_logs_retain_history_between_jobs_and_accept_plain_text(window, mocker):
    mocker.patch.object(window.runner, "start")
    window.log_store.append("上一次任务错误", "ERROR")
    window.runner.log.emit('<b>后台报错</b>')
    window.run_job(lambda: Job("doctor"), "运行时检查")
    window.log_store.flush()
    assert "上一次任务错误" in window.logs_page.text_edit.toPlainText()
    assert '<b>后台报错</b>' in window.logs_page.text_edit.toPlainText()
    window.runner.log.emit('<b>新报错</b>')
    assert '<b>新报错</b>' in window.workspace.logs.toPlainText()
    window.workspace.translation.open_logs.click()
    assert window.stackedWidget.currentWidget() is window.logs_page


def test_recognition_rejects_screenshot_path_with_visible_suggestion(window, mocker):
    mocker.patch("pathlib.Path.is_dir", return_value=True)
    start = mocker.patch.object(window.runner, "start")
    page = window.workspace.recognition
    root = "D:/games/Forever Stranded"
    page.root.setText(root)
    page.output.setText(root + "/.mplt")
    assert "实例之外" in page.output_hint.text()
    assert not page.suggested_output.isHidden()
    window.workspace.start("extract")
    start.assert_not_called()
    assert "实例之外" in window.notify.call_args.args[0]
    page.suggested_output.click()
    validate_output(Path(root), Path(page.output.text()))
    assert page.suggested_output.isHidden()


def test_recognition_changes_automatic_output_when_game_conflicts_with_task_home(window):
    page = window.workspace.recognition
    home = Path("D:/games/Forever Stranded/.mplt")
    window.settings.output_home = str(home)
    page.new_output()
    assert Path(page.output.text()).is_relative_to(home)
    page.root.setText("D:/games/Forever Stranded")
    validate_output(Path(page.root.text()), Path(page.output.text()))
    assert not Path(page.output.text()).is_relative_to(home)


def test_recognition_keeps_manually_selected_external_output_when_root_changes(window):
    page = window.workspace.recognition
    page.output.setText("D:/translations/my-task")
    page.root.setText("D:/games/Forever Stranded")
    assert page.output.text() == "D:/translations/my-task"


def test_api_profile_save_updates_translation_engine_and_preserves_local_model(window):
    local_model = window.settings.model
    window.api.store_profile(ApiProfile(id="test", name="本地 API", model="small-model"))
    window.api.activate("test")
    assert window.settings.engine == "api"
    assert window.settings.selected_profile().model == "small-model"
    assert window.settings.model == local_model
    assert "small-model" in window.workspace.engine.text()
    assert window.settings_page.collect().api_profiles == window.settings.api_profiles


def test_index_official_api_is_available_without_manual_connection_setup(window, mocker):
    from mcpacklocalizer.core.translation.api import INDEX_PROFILE_ID
    assert INDEX_PROFILE_ID in window.api.cards
    start = mocker.patch.object(window.runner, "start")
    window.api.activate(INDEX_PROFILE_ID)
    assert window.settings.selected_profile().model == "Index-Translate-35B-A3B"
    assert window.settings.model_options()["api_prompt_mode"] == "index"
    assert window.settings.model_options()["concurrency"] == 3
    start.assert_not_called()


def test_interface_menu_opens_bound_template_and_custom_template_can_be_selected(window):
    from dataclasses import replace

    from mcpacklocalizer.core.translation.templates import BUILTIN_TEMPLATES
    custom = replace(BUILTIN_TEMPLATES["index"], id="my-index", name="我的 Index", user="专用：{text}")
    window.save_settings(window.settings.store_template(custom))
    profile = ApiProfile(id="index-local", model="Index-Translate-2B", prompt_mode="index", template_id=custom.id)
    window.api.store_profile(profile)
    window.api.cards[profile.id].actions["prompts"][0].trigger()
    assert window.stackedWidget.currentWidget() == window.prompts
    assert window.prompts.templates.currentData() == custom.id
    assert not window.prompts.user_prompt.isReadOnly()
    window.prompts.user_prompt.setPlainText("更新：{text} → {target_language}")
    window.prompts.save()
    window.api.activate(profile.id)
    assert window.settings.model_options()["prompt_user"] == "更新：{text} → {target_language}"
    dialog = AddApiDialog(window)
    dialog.select_platform("ollama")
    dialog.validate()
    dialog.details.kind.setCurrentIndex(dialog.details.kind.findData("translation"))
    assert dialog.details.template.findData(custom.id) >= 0
    assert dialog.details.template.findData("mc") == -1
    dialog.details.template.setCurrentIndex(dialog.details.template.findData(custom.id))
    dialog.details.model.setText("Index-Translate-2B")
    assert dialog.validate() and dialog.profile.template_id == custom.id
    assert dialog.profile.concurrency == 1
    dialog.deleteLater()


def test_prompt_template_copy_reset_and_bound_delete_guard(window):
    from mcpacklocalizer.ui.view.api.local import LocalEditDialog
    window.prompts.edit_template("hy_mt")
    window.prompts.duplicate()
    custom_id = window.prompts.templates.currentData()
    assert custom_id != "hy_mt"
    window.prompts.user_prompt.setPlainText("我的 HY：{text}")
    window.prompts.save()
    dialog = LocalEditDialog(window.settings.current_local_profile(), window)
    dialog.details.template.setCurrentIndex(dialog.details.template.findData(custom_id))
    assert dialog.validate()
    window.api.store_profile(dialog.profile)
    dialog.deleteLater()
    assert window.settings.model_options()["prompt_user"] == "我的 HY：{text}"
    window.prompts.remove()
    assert custom_id in window.settings.templates()
    window.save_settings(window.settings.bind_local_template("hy_mt"))
    window.prompts.remove()
    assert custom_id not in window.settings.templates()
    window.prompts.edit_template("hy_mt")
    window.prompts.user_prompt.setPlainText("修改预设：{text}")
    window.prompts.save()
    assert window.settings.templates()["hy_mt"].user == "修改预设：{text}"
    window.prompts.reset()
    assert "将以下文本翻译为{target_language}" in window.settings.templates()["hy_mt"].user


@pytest.mark.parametrize("platform,concurrency", [("ollama", 1), ("openai", 3), ("index", 3)])
def test_add_dialog_uses_deployment_concurrency_and_index_defaults(window, platform, concurrency):
    dialog = AddApiDialog(window)
    dialog.select_platform(platform)
    dialog.validate()
    if platform != "index":
        dialog.details.model.setText("model")
    assert dialog.validate()
    assert dialog.profile.concurrency == concurrency
    if platform == "index":
        assert dialog.profile.interface_type == "translation" and dialog.profile.template_id == "index"
        assert dialog.profile.model == "Index-Translate-35B-A3B" and not dialog.profile.api_key
    dialog.deleteLater()


def test_settings_save_preserves_api_prompt_and_rules(window):
    window.settings.system_prompt = "custom MC prompt"
    window.settings.non_translate = "Create"
    window.settings.glossary_inline = '{"Iron Ingot":"铁锭"}'
    assert window.settings_page.collect().system_prompt == "custom MC prompt"
    assert window.settings_page.collect().non_translate == "Create"
    assert window.settings_page.collect().glossary_inline == '{"Iron Ingot":"铁锭"}'


def test_settings_model_picker_uses_index_template_and_restores_previous_binding(window, tmp_path):
    previous = window.settings.model
    index_model = str(tmp_path / "Index-Translate-2B.Q4_K_M.gguf")
    window.settings_page.model.setPath(index_model)
    window.settings_page.save_timer.stop()
    window.settings_page.save()
    assert window.settings.local_template_id == "index"
    assert window.settings.download_variant == "index-2b"
    window.settings_page.model.setPath(previous)
    window.settings_page.save_timer.stop()
    window.settings_page.save()
    assert window.settings.local_template_id == "hy_mt"


def test_catalog_page_has_bounded_rows_and_keeps_edits_across_pages(window, qt_app, mocker):
    data = {f"Item {i}": f"物品{i}" for i in range(250)}
    # The UI requests only one page from the background catalog.
    window.settings.glossary_inline = json.dumps(data, ensure_ascii=False)
    window.rules.scope.setCurrentIndex(1)
    window.rules.timer.stop()
    window.rules.query()
    for _ in range(500):
        qt_app.processEvents()
        if window.rules.loader is None:
            break
        QTest.qWait(2)
    assert window.rules.table.rowCount() == 100
    assert window.rules.total == 250
    window.rules.table.item(0, 1).setText("自定义物品")
    window.rules.turn(1)
    for _ in range(500):
        qt_app.processEvents()
        if window.rules.loader is None:
            break
        QTest.qWait(2)
    assert window.rules.table.rowCount() == 100
    window.rules.save_terms()
    assert json.loads(window.settings.glossary_inline)["Item 0"] == "自定义物品"


def test_output_defaults_update_current_task_controls(window):
    window.settings_page.partial.setChecked(True)
    window.settings_page.replace_locale.setChecked(True)
    window.settings_page.save()
    assert window.workspace.partial.isChecked() and window.review.partial.isChecked()
    assert window.workspace.replace.isChecked()


def test_api_test_uses_selected_profile_without_changing_active_engine(window, mocker):
    profile = ApiProfile(id="draft", model="test-model")
    window.api.store_profile(profile)
    calls = []
    mocker.patch.object(window, "run_job", side_effect=lambda factory, label: calls.append((factory(), label)))
    window.api.test(profile.id)
    assert calls[0][0].engine == "api" and calls[0][1] == "接口试译"
    assert window.settings.engine == "local"


def test_add_dialog_has_two_steps_and_preserves_details_when_going_back(window):
    dialog = AddApiDialog(window)
    assert not dialog.validate()
    dialog.select_platform("ollama")
    dialog.name.setText("我的本地模型")
    assert not dialog.validate() and dialog.stack.currentIndex() == 1
    assert dialog.details.url.text() == "http://127.0.0.1:11434/v1"
    dialog.details.model.setText("local-model")
    dialog.details.key.setText("secret")
    dialog.previous_step()
    assert not dialog.validate()
    assert dialog.details.model.text() == "local-model" and dialog.details.key.text() == "secret"
    assert dialog.validate()
    assert dialog.profile.name == "我的本地模型" and dialog.profile.group == "local"
    dialog.deleteLater()


def test_cancelled_add_dialog_does_not_create_profile(window, mocker):
    mocker.patch.object(AddApiDialog, "exec", return_value=0)
    window.api.add_profile()
    assert window.settings.api_profiles == []


def test_connection_edit_preserves_generation_parameters(window):
    profile = ApiProfile(id="test", model="model", api_key="secret", send_temperature=False,
                         temperature=0.8, token_parameter="max_completion_tokens", extra_body='{"reasoning_effort":"low"}')
    dialog = ApiEditDialog(profile, window)
    dialog.details.name.setText("改名")
    assert dialog.validate()
    assert dialog.profile.name == "改名"
    assert dialog.profile.extra_body == profile.extra_body and dialog.profile.api_key == "secret"
    assert dialog.profile.temperature == 0.8 and not dialog.profile.send_temperature
    dialog.deleteLater()


def test_parameter_edit_preserves_credentials_and_validates_extra_json(window):
    profile = ApiProfile(id="test", model="model", api_key="secret", group="custom")
    dialog = ApiParametersDialog(profile, window)
    dialog.extra.setPlainText("invalid JSON")
    assert not dialog.validate() and dialog.profile is None
    dialog.extra.setPlainText('{"enable_thinking":false}')
    dialog.send_temperature.setChecked(False)
    assert dialog.validate()
    assert dialog.profile.api_key == "secret" and dialog.profile.base_url == profile.base_url
    assert not dialog.profile.send_temperature
    dialog.deleteLater()


def test_interface_limits_save_test_and_duplicate_independently_of_gguf(window, mocker):
    profile = ApiProfile(id="cloud", model="large", base_url="https://example.test/v1")
    window.api.store_profile(profile)
    dialog = ApiParametersDialog(profile, window)
    dialog.numbers["context_size"].setValue(32768)
    dialog.numbers["max_tokens"].setValue(4096)
    dialog.numbers["concurrency"].setValue(6)
    dialog.numbers["timeout"].setValue(60)
    dialog.interval.setValue(0.5)
    assert dialog.validate()
    window.api.store_profile(dialog.profile)
    assert window.settings.max_tokens == 768 and window.settings.timeout == 300
    assert "concurrency" not in window.settings_page.numbers
    window.settings_page.numbers["max_tokens"].setValue(128)
    window.settings_page.save()
    window.api.activate("cloud")
    assert window.settings.model_options()["max_tokens"] == 4096
    calls = []
    mocker.patch.object(window, "run_job", side_effect=lambda factory, label: calls.append(factory()))
    window.api.test("cloud")
    assert (calls[0].max_tokens, calls[0].concurrency, calls[0].timeout) == (4096, 6, 60)
    window.api.duplicate("cloud")
    copied = window.settings.api_profiles[1]
    assert copied["max_tokens"] == 4096 and copied["request_interval"] == 0.5
    window.api.activate(BUILTIN_LOCAL)
    assert window.settings.model_options()["max_tokens"] == 128
    dialog.deleteLater()


def test_local_environment_check_uses_local_limits_with_api_active(window, mocker):
    window.api.store_profile(ApiProfile(id="cloud", model="large", max_tokens=2048))
    window.api.activate("cloud")
    calls = []
    mocker.patch.object(window, "run_job", side_effect=lambda factory, label: calls.append(factory()))
    window.settings_page.check(True)
    assert calls[0].engine == "local" and calls[0].max_tokens == window.settings.max_tokens


@pytest.mark.parametrize("url,expected", [
    ("http://localhost:1234/v1", "local"), ("http://[::1]:8080/v1", "local"),
    ("http://192.168.1.12/v1", "local"), ("https://api.openai.com/v1", "online"),
    ("https://api.deepseek.com/v1", "online"), ("https://opencode.ai/zen/v1", "online"),
    ("https://my-proxy.test/v1", "custom"),
])
def test_legacy_profiles_are_grouped_by_address(url, expected):
    assert profile_group(ApiProfile(base_url=url)) == expected


@pytest.mark.parametrize("platform,url", [
    ("deepseek", "https://api.deepseek.com/v1"), ("opencode", "https://opencode.ai/zen/v1"),
    ("opencode_go", "https://opencode.ai/zen/go/v1"),
])
def test_new_platform_can_be_created_activated_and_tested(window, mocker, platform, url):
    dialog = AddApiDialog(window)
    dialog.platform_buttons[platform].click()
    assert not dialog.validate()
    dialog.details.model.setText("service-model")
    dialog.details.key.setText("test-key")
    assert dialog.validate()
    window.api.store_profile(dialog.profile)
    window.api.activate(dialog.profile.id)
    assert window.api.cards[dialog.profile.id].active
    assert window.settings.selected_profile().group == "online"
    calls = []
    mocker.patch.object(window, "run_job", side_effect=lambda factory, label: calls.append(factory()))
    window.api.test(dialog.profile.id)
    assert calls[0].api_base_url == url and calls[0].api_protocol == "openai"
    assert calls[0].api_model == "service-model"
    dialog.deleteLater()


def test_activation_highlights_one_interface_and_switching_back_keeps_api_data(window):
    profile = ApiProfile(id="test", name="远程接口", model="model", group="online")
    window.api.store_profile(profile)
    window.api.activate("test")
    assert window.api.cards["test"].active and not window.api.cards[BUILTIN_LOCAL].active
    assert not window.api.cards["test"].actions["activate"][0].isEnabled()
    window.api.activate(BUILTIN_LOCAL)
    assert window.settings.engine == "local" and window.settings.api_profiles[0]["id"] == "test"
    assert window.api.cards[BUILTIN_LOCAL].active


def test_copy_creates_distinct_profile_and_menu_test_is_disabled_while_busy(window):
    window.api.store_profile(ApiProfile(id="test", model="model", api_key="secret"))
    window.api.duplicate("test")
    assert len(window.settings.api_profiles) == 2
    assert window.settings.api_profiles[0]["id"] != window.settings.api_profiles[1]["id"]
    window.api.set_busy(True)
    assert not window.api.cards["test"].actions["test"][0].isEnabled()


def test_deleting_active_interface_returns_to_local_and_keeps_other_profiles(window, mocker):
    window.api.store_profile(ApiProfile(id="one", model="model"))
    window.api.store_profile(ApiProfile(id="two", model="model"))
    window.api.activate("one")
    mocker.patch("mcpacklocalizer.ui.view.api.page.MessageBox.exec", return_value=1)
    window.api.remove("one")
    assert window.settings.engine == "local" and window.settings.active_api == ""
    assert [p["id"] for p in window.settings.api_profiles] == ["two"]


def load_workflow_task(window, tmp_path):
    root = tmp_path / "game"
    kube = root / "kubejs/assets/demo/lang/en_us.json"
    kube.parent.mkdir(parents=True)
    kube.write_text('{"item.demo.ingot":"Iron Ingot"}', encoding="utf-8")
    quest = root / "config/ftbquests/quests/chapters/first.snbt"
    quest.parent.mkdir(parents=True)
    quest.write_text('{id:"first", title:"First Steps"}', encoding="utf-8")
    path = tmp_path / "task"
    execute(Job("extract", root=root, output=path))
    window.review.load_generation = 1
    window.review.loaded(load_task(str(path)), str(path), 1)
    return root, path


def test_polishing_selection_and_all_scope_use_configured_api_with_saved_prompt(window, tmp_path, mocker):
    _, path = load_workflow_task(window, tmp_path)
    page = window.review
    assert not page.polish_selected.isEnabled() and not page.polish_all.isEnabled()
    window.api.store_profile(ApiProfile(id="polisher", name="修润", model="large", api_key="private-secret"))
    window.api.store_profile(ApiProfile(id="fixed", name="固定", model="small", prompt_mode="hy_mt"))
    assert page.polish_api.findData("fixed") == -1
    page.polish_api.setCurrentIndex(page.polish_api.findData("polisher"))
    page.polish_prompt.setPlainText("对照 {source} 修正 {translation}，保留格式。")
    page.polish_mode.setCurrentIndex(1)
    flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    page.table.selectionModel().select(page.proxy.index(0, 0), flags)
    page.table.selectionModel().select(page.proxy.index(1, 0), flags)
    assert len(page.table.selectionModel().selectedRows()) == 2 and page.polish_selected.isEnabled()
    calls = []
    mocker.patch.object(window, "run_job", side_effect=lambda factory, label, task="": calls.append((factory(), label, task)))
    page.start_polishing()
    args, label, task = calls[0]
    assert args.operation == "polish" and len(args.entry_ids) == 2 and args.polish_mode == "polish"
    assert args.api_model == "large" and args.polish_prompt == page.polish_prompt.toPlainText()
    assert label == "API 批量修润" and task == str(path.resolve())
    assert window.settings.engine == "local" and window.settings.polish_api == "polisher"
    assert window.settings.polish_prompt == args.polish_prompt
    page.search.setText("Iron Ingot")
    assert page.proxy.rowCount() == 1
    page.select_all.click()
    assert len(page.table.selectionModel().selectedRows()) == 1
    page.start_polishing()
    assert len(calls[-1][0].entry_ids) == 1
    page.start_polishing(True)
    assert calls[-1][0].entry_ids is None


def test_deleting_polish_api_disables_batch_actions_and_keeps_prompt(window, tmp_path, mocker):
    load_workflow_task(window, tmp_path)
    page = window.review
    window.api.store_profile(ApiProfile(id="polisher", name="修润", model="large"))
    page.polish_api.setCurrentIndex(page.polish_api.findData("polisher"))
    page.polish_prompt.setPlainText("我自己的修润规则")
    page.save_polish_settings()
    assert page.polish_all.isEnabled()
    mocker.patch("mcpacklocalizer.ui.view.api.page.MessageBox.exec", return_value=1)
    window.api.remove("polisher")
    assert window.settings.polish_api == "" and window.settings.polish_prompt == "我自己的修润规则"
    assert not page.polish_all.isEnabled()


def test_previous_polish_translation_can_be_loaded_without_writing_checkpoint(window, tmp_path):
    _, path = load_workflow_task(window, tmp_path)
    page = window.review
    current = page.scan.entries[0]
    page.scan.metadata["polish_runs"] = [{"previous": {current.id: {"translation": "修润前译文"}}}]
    page.table.setCurrentIndex(page.proxy.mapFromSource(page.model.index(0, 0)))
    assert page.restore_polish.isEnabled()
    page.restore_polish.click()
    assert page.translation.toPlainText() == "修润前译文" and page.translation.document().isModified()
    assert load_task(str(path)).entries[0].translation is None
    page.translation.document().setModified(False)


@pytest.mark.parametrize("cancelled", [False, True])
def test_polish_completion_or_pause_automatically_opens_preview(window, tmp_path, mocker, qt_app, cancelled):
    _, path = load_workflow_task(window, tmp_path)
    with Store(path) as store:
        scan = store.load()
        first = scan.entries[0]
        run = {"id": "draft", "preview_only": True, "previous": {first.id: {"translation": first.translation}},
               "results": {first.id: {"translation": "候选译文", "raw_response": "候选译文", "error": "守卫拦截原因"}}}
        scan.metadata["polish_runs"] = [run]
        store.metadata(scan)
    window.pending_task, window.pending_label, window.pending_polish_run_id = str(path), "API 批量修润", "draft"
    show = mocker.patch.object(PolishResultsDialog, "exec", return_value=0)
    window.job_done(130 if cancelled else 1, {"error": "已暂停"} if cancelled else {
        "operation": "polish", "run_id": "draft", "partial": True, "polished_this_run": 0, "failed_this_run": 1}, cancelled)
    for _ in range(300):
        qt_app.processEvents()
        if show.called and not window.review.loaders:
            break
        QTest.qWait(5)
    show.assert_called_once()
    assert load_task(str(path)).entries[0].translation == first.translation
    window.review.filter.setCurrentIndex(6)
    assert window.review.proxy.rowCount() == 1


def test_accepting_preview_dispatches_only_checked_edits(window, tmp_path, mocker):
    _, path = load_workflow_task(window, tmp_path)
    page = window.review
    first = page.scan.entries[0]
    run = {"id": "draft", "preview_only": True, "previous": {first.id: {"translation": first.translation}},
           "results": {first.id: {"translation": "API 候选", "raw_response": "API 候选", "error": ""}}}
    page.scan.metadata["polish_runs"] = [run]

    def accept(dialog):
        dialog.updates = {first.id: "人工修复后的译文"}
        return 1

    mocker.patch.object(PolishResultsDialog, "exec", new=accept)
    calls = []
    mocker.patch.object(window, "run_job", side_effect=lambda factory, label, task="": calls.append((factory(), label, task)))
    page.show_polish_results("draft")
    args, label, task = calls[0]
    assert args.operation == "polish-accept" and args.polish_updates == {first.id: "人工修复后的译文"}
    assert args.polish_run_id == "draft" and label == "接受修润结果" and task == str(path.resolve())


def test_recognized_resources_filter_text_and_translation_resumes_same_checkpoint(window, tmp_path, mocker):
    _, path = load_workflow_task(window, tmp_path)
    recognition = window.workspace.recognition
    assert window.workspace.stack.count() == 3
    assert not recognition.input_card.isVisible()
    tree = recognition.tree
    kube = next(tree.topLevelItem(i) for i in range(tree.topLevelItemCount()) if "KubeJS" in tree.topLevelItem(i).text(0))
    tree.setCurrentItem(kube)
    assert recognition.proxy.rowCount() == 1
    assert recognition.proxy.index(0, 2).data() == "Iron Ingot"
    calls = []
    mocker.patch.object(window, "run_job", side_effect=lambda factory, label, task="": calls.append((factory(), label, task)))
    window.workspace.start_translation()
    assert window.workspace.current_stage == "translation"
    assert calls[0][0].operation == "resume" and calls[0][0].output == path
    assert calls[0][0].engine == window.settings.engine


def tree_items(tree):
    def descend(item):
        yield item
        for index in range(item.childCount()):
            yield from descend(item.child(index))
    for index in range(tree.topLevelItemCount()):
        yield from descend(tree.topLevelItem(index))


def test_recognition_warns_on_blocked_book_file_with_no_entries(window, tmp_path):
    _, path = load_workflow_task(window, tmp_path)
    scan = window.workspace.task_scan
    name = "mods/Apotheosis.jar!/data/apotheosis/patchouli_books/apoth_chronicle/book.json"
    warning = "疑似未解析的帕秋莉语言 key：book.apotheosis.name；已拦截"
    scan.documents.append(Document(name, "mods/Apotheosis.jar", "patchouli-book", "{}", digest("{}"),
                                   resource={"recognition_warnings": [warning]}))
    page = window.workspace.recognition
    page.bind_scan(scan, str(path))
    item = next(item for item in tree_items(page.tree)
                if item.data(0, Qt.ItemDataRole.UserRole) == [name] and item.childCount() == 0)
    assert item.text(0).startswith("book.json") and not item.icon(0).isNull()
    assert "book.apotheosis.name" in item.toolTip(0)
    assert item.parent().isExpanded()
    page.tree.setCurrentItem(item)
    assert page.proxy.rowCount() == 0
    assert warning in page.source.toPlainText()


def test_directory_context_menu_submits_exact_subtree_and_disables_while_busy(window, tmp_path, mocker):
    _, path = load_workflow_task(window, tmp_path)
    page = window.workspace.recognition
    folder = next(item for item in tree_items(page.tree)
                  if item.data(0, Qt.ItemDataRole.UserRole + 1) == {"kind": "directory", "path": "config"})
    expected = ["config/ftbquests/quests/chapters/first.snbt"]
    assert folder.data(0, Qt.ItemDataRole.UserRole) == expected
    page.tree.setCurrentItem(folder)
    assert page.proxy.rowCount() == 1
    calls = []
    mocker.patch.object(window, "run_job", side_effect=lambda factory, label, task="": calls.append((factory(), label, task)))
    menu = page.resource_menu(folder)
    exclude, restore = menu.actions()
    assert exclude.text() == "排除此目录" and exclude.isEnabled() and not restore.isEnabled()
    exclude.trigger()
    job, label, task = calls[0]
    assert job.operation == "resource-exclusion" and job.resource_paths == expected
    assert job.resource_action == "exclude" and label == "排除资源" and task == str(path.resolve())
    window.runner.busy = True
    busy_menu = page.resource_menu(folder)
    assert all(not action.isEnabled() for action in busy_menu.actions())
    window.runner.busy = False
    menu.deleteLater()
    busy_menu.deleteLater()


def test_excluded_directory_stays_visible_and_can_be_restored_after_loading(window, tmp_path, mocker):
    _, path = load_workflow_task(window, tmp_path)
    document = "config/ftbquests/quests/chapters/first.snbt"
    execute(Job("resource-exclusion", output=path, resource_paths=[document], resource_action="exclude"))
    window.review.loaded(load_task(str(path)), str(path), 1)
    page = window.workspace.recognition
    folder = next(item for item in tree_items(page.tree)
                  if item.data(0, Qt.ItemDataRole.UserRole + 1) == {"kind": "directory", "path": "config"})
    assert "已排除" in folder.text(0)
    page.tree.setCurrentItem(folder)
    assert page.proxy.index(0, 0).data() == "已排除"
    assert "待翻译 1 条" in page.summary_text.text()
    calls = []
    mocker.patch.object(window, "run_job", side_effect=lambda factory, label, task="": calls.append((factory(), label, task)))
    menu = page.resource_menu(folder)
    exclude, restore = menu.actions()
    assert not exclude.isEnabled() and restore.isEnabled()
    restore.trigger()
    assert calls[0][0].resource_action == "restore"
    menu.deleteLater()


def test_changing_source_directory_invalidates_recognition_without_deleting_checkpoint(window, tmp_path):
    _, path = load_workflow_task(window, tmp_path)
    window.workspace.root.setText(str(tmp_path / "other-game"))
    assert not window.workspace.task_path
    assert window.workspace.recognition.model.rowCount() == 0
    assert not window.workspace.translate.isEnabled()
    assert (path / "state.sqlite3").is_file()
    assert window.workspace.output.text() != str(path)


@pytest.mark.parametrize("option", ["baseline", "pack_id", "translation_library", "reuse_policy"])
def test_changing_reuse_options_requires_new_recognition(window, tmp_path, option):
    _, path = load_workflow_task(window, tmp_path)
    page = window.workspace.recognition
    if option == "reuse_policy":
        page.reuse_policy.setCurrentIndex(1)
    else:
        getattr(page, option).setText(str(tmp_path / "different"))
    assert not window.workspace.task_path
    assert (path / "state.sqlite3").is_file()
    assert window.workspace.output.text() != str(path)


def test_recognition_forwards_shared_library_and_draft_policy(window, tmp_path, mocker):
    root = tmp_path / "game"
    root.mkdir()
    page = window.workspace.recognition
    page.root.setText(str(root))
    page.mode.setSelectedData(["mods"])
    page.translation_library.setText(str(tmp_path / "shared.sqlite3"))
    page.reuse_policy.setCurrentIndex(page.reuse_policy.findData("all"))
    calls = []
    mocker.patch.object(window, "run_job", side_effect=lambda factory, label, task="": calls.append(factory()))
    window.workspace.start("extract")
    assert calls[0].operation == "extract-mods"
    assert calls[0].translation_library == tmp_path / "shared.sqlite3"
    assert calls[0].reuse_policy == "all"


def test_baseline_format_policy_does_not_hide_current_model_selection(window, tmp_path, mocker):
    _, path = load_workflow_task(window, tmp_path)
    scan = load_task(str(path))
    scan.metadata["model_config"] = {"allow_missing_placeholders": True}
    window.workspace.bind_task(scan, str(path))
    calls = []
    mocker.patch.object(window, "run_job", side_effect=lambda factory, label, task="": calls.append(factory()))
    window.workspace.start_translation()
    assert calls[0].engine == window.settings.engine


def test_proofreading_stage_preserves_unsaved_translation_on_cancel(window, tmp_path, mocker):
    load_workflow_task(window, tmp_path)
    window.workspace.set_stage("proofreading")
    window.review.translation.setPlainText("未保存译文")
    window.review.translation.document().setModified(True)
    mocker.patch("mcpacklocalizer.ui.view.tasks.review.MessageBox.exec", return_value=0)
    window.workspace.set_stage("recognition")
    assert window.workspace.current_stage == "proofreading"
    assert window.review.translation.toPlainText() == "未保存译文"
    window.review.translation.document().setModified(False)


def test_settings_language_selection_persists_and_updates_new_task_direction(window):
    page = window.settings_page
    page.source_language.setCurrentIndex(page.source_language.findData("ja_jp"))
    page.target_language.setCurrentIndex(page.target_language.findData("en_us"))
    page.save()
    assert window.settings.source_locale == "ja_jp" and window.settings.target_locale == "en_us"
    assert "ja_jp" in window.workspace.recognition.languages.text()
    assert "en_us" in window.workspace.recognition.languages.text()


def test_settings_reject_equal_source_and_target_languages(window):
    page = window.settings_page
    page.target_language.setCurrentIndex(page.target_language.findData("en_us"))
    with pytest.raises(ValueError, match="不能相同"):
        page.collect()


def test_settings_theme_color_persists_and_resets(window):
    page = window.settings_page
    assert page.theme_color.color() == window.settings.theme_color
    page.theme_color.setColor("#ff5500")
    page.save()
    assert window.settings.theme_color == "#ff5500"
    page.theme_color.resetButton.click()
    assert page.theme_color.color() == "#3268c8"


def test_settings_changes_autosave_and_notify(window, qt_app):
    page = window.settings_page
    window.notify.reset_mock()
    page.partial.setChecked(not window.settings.output_allow_partial)
    QTest.qWait(700)
    qt_app.processEvents()
    assert window.settings.output_allow_partial is page.partial.isChecked()
    assert window.notify.called


def wait_for_workflow_job(window, qt_app):
    for _ in range(1500):
        qt_app.processEvents()
        if not window.runner.busy and not window.review.loaders and window.workspace.task_path:
            return
        QTest.qWait(5)
    pytest.fail("工作流后台操作或检查点加载未完成")


def test_recognition_and_manual_proofreading_use_real_background_jobs(window, tmp_path, qt_app):
    root = tmp_path / "game"
    language = root / "kubejs/assets/demo/lang/en_us.json"
    language.parent.mkdir(parents=True)
    language.write_text('{"item.demo.ingot":"Iron Ingot"}', encoding="utf-8")
    task = tmp_path / "task"
    window.workspace.root.setText(str(root))
    window.workspace.output.setText(str(task))
    window.workspace.recognition.identify.click()
    wait_for_workflow_job(window, qt_app)
    assert window.workspace.current_stage == "recognition"
    assert window.workspace.recognition.model.rowCount() == 1
    assert window.workspace.translate.isEnabled()
    window.workspace.set_stage("proofreading")
    window.review.table.setCurrentIndex(window.review.proxy.index(0, 0))
    window.review.translation.setPlainText("铁锭")
    window.review.save.click()
    wait_for_workflow_job(window, qt_app)
    assert window.workspace.current_stage == "proofreading"
    assert load_task(str(task)).entries[0].status == "reviewed"
    assert load_task(str(task)).entries[0].translation == "铁锭"
