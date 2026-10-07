# [Module: tests.tasks] [Status: 已完成] [Brief: 结构化任务服务与核心功能回归]
import json
from pathlib import Path

import pytest

from mcpacklocalizer.application.tasks.jobs import Job
from mcpacklocalizer.application.tasks.service import config_for, run_translation
from mcpacklocalizer.application.tasks.worker import perform
from mcpacklocalizer.core.pack.extraction import Entry, Scan


def test_scan_json_has_no_progress_noise(mocker, capsys):
    mocker.patch('mcpacklocalizer.application.tasks.service.scan_pack', return_value=Scan('C:/pack', 'pack', 'en_us', 'zh_cn'))
    assert perform(Job('scan', root='C:/pack')) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)['entries'] == 0
    assert captured.err == ''

def test_runtime_error_has_nonzero_machine_readable_result(mocker, capsys):
    mocker.patch('mcpacklocalizer.application.tasks.service.scan_pack', side_effect=ValueError('Unsupported locale'))
    assert perform(Job('scan', root='C:/pack')) == 2
    assert json.loads(capsys.readouterr().out)['error'] == 'Unsupported locale'

def test_no_glossary_and_explicit_cpu_config():
    args = Job('translate', text='Hello', no_glossary=True, backend='cpu')
    config = config_for(args)
    assert config.glossary is None and config.backend == 'cpu'

def test_translate_number_hint_keeps_success_exit_code(mocker, capsys):
    model = mocker.patch('mcpacklocalizer.application.tasks.service.WorkerClient').return_value.__enter__.return_value
    model.translate.return_value = '收集32个物品'
    model.info = {'backend': 'vulkan'}
    assert perform(Job('translate', text='Collect 64 items', no_glossary=True)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['translation'] == '收集32个物品'
    assert result['quality_warnings'][0]['missing'] == ['64']

def test_review_accepts_number_change_and_reports_hint(mocker, capsys):
    entry = Entry('one', 'ftb:key', 'a.snbt', ['key'], 'Collect 64 items', 1, 12, 'key')
    scan = Scan('C:/pack', 'pack', 'en_us', 'zh_cn', entries=[entry])
    store = mocker.patch('mcpacklocalizer.application.tasks.service.Store').return_value.__enter__.return_value
    store.load.return_value = scan
    assert perform(Job('review', output='C:/output', entry_id='one', translation='收集32个物品')) == 0
    result = json.loads(capsys.readouterr().out)
    assert entry.status == 'reviewed' and entry.error == ''
    assert result['quality_warnings'][0]['added'] == ['32']
    store.update.assert_called_once_with(entry)


@pytest.mark.parametrize("translation", ["&c铁&r和&b金&r", "铁和金", "&a铁和金&r"])
def test_review_accepts_manual_color_changes_with_advisory(mocker, capsys, translation):
    entry = Entry("one", "ftb:key", "a.snbt", ["key"], "&bGold&r and &cIron&r", 1, 12, "key")
    scan = Scan("C:/pack", "pack", "en_us", "zh_cn", entries=[entry])
    store = mocker.patch("mcpacklocalizer.application.tasks.service.Store").return_value.__enter__.return_value
    store.load.return_value = scan
    assert perform(Job("review", output="C:/output", entry_id="one", translation=translation)) == 0
    result = json.loads(capsys.readouterr().out)
    assert (entry.translation, entry.status, entry.origin) == (translation, "reviewed", "manual")
    assert result["quality_warnings"][0]["code"] == "protected_fragments_changed"

def test_resume_reuses_completed_duplicate_without_second_inference(mocker):
    scan = Scan('C:/pack', 'pack', 'en_us', 'zh_cn', entries=[Entry('one', 'ftb:key', 'a.snbt', ['key'], 'Iron Ingot', 1, 12, 'key', translation='铁锭'), Entry('two', 'ftb:key', 'b.snbt', ['key'], 'Iron Ingot', 1, 12, 'key')])
    store = mocker.Mock(output=Path('C:/output'))
    store.load.return_value = scan
    model = mocker.patch('mcpacklocalizer.application.tasks.service.WorkerClient').return_value.__enter__.return_value
    mocker.patch('mcpacklocalizer.application.tasks.service.validate_sources')
    mocker.patch('mcpacklocalizer.application.tasks.service.export_task', return_value={'partial': False})
    args = Job('resume', output='C:/output', no_glossary=True)
    result = run_translation(store, args)
    assert scan.entries[1].translation == '铁锭'
    assert result['translated_this_run'] == 1
    model.translate.assert_not_called()

def test_resume_skips_existing_resource_locale_in_old_task(memory_files, mocker):
    from mcpacklocalizer.core.pack.extraction import scan_pack
    root = 'C:/mcpl-tests/pack'
    memory_files[root + '/kubejs/assets/custom/lang/en_us.json'] = '{"item.custom.a":"English"}'
    scan = scan_pack(Path(root))
    memory_files[root + '/kubejs/assets/custom/lang/zh_cn.json'] = '{"item.custom.a":"已有译文"}'
    store = mocker.Mock(output=Path('C:/output'))
    store.load.return_value = scan
    worker = mocker.patch('mcpacklocalizer.application.tasks.service.WorkerClient')
    mocker.patch('mcpacklocalizer.application.tasks.service.export_task', return_value={'partial': False})
    args = Job('resume', output='C:/output', no_glossary=True)
    result = run_translation(store, args)
    assert result['translated_this_run'] == 0
    worker.assert_not_called()
    assert store.metadata.call_args.args[0].metadata['excluded_resources']

def test_placeholder_option_defaults_off_and_resume_preserves_or_overrides_saved_setting():
    from dataclasses import asdict

    from mcpacklocalizer.core.translation.local import ModelConfig
    args = Job('resume', output='C:/output')
    assert config_for(args).allow_missing_placeholders is False
    saved = asdict(ModelConfig(allow_missing_placeholders=True))
    assert config_for(args, saved).allow_missing_placeholders is True
    args = Job('resume', output='C:/output', allow_missing_placeholders=False)
    assert config_for(args, saved).allow_missing_placeholders is False
    assert saved['allow_missing_placeholders'] is True

def test_translate_missing_placeholder_warns_without_error_exit(mocker, capsys):
    model = mocker.patch('mcpacklocalizer.application.tasks.service.WorkerClient').return_value.__enter__.return_value
    model.translate.return_value, model.info = ('葡萄', {'backend': 'vulkan'})
    assert perform(Job('translate', text='&bGrapes&r', allow_missing_placeholders=True)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['quality_warnings'][0]['missing'] == ['&b', '&r']

def test_resume_relaxed_policy_accepts_fallback_and_emits_progress_warning(mocker, capsys):
    entry = Entry('one', 'ftb:key', 'a.snbt', ['key'], '&bGrapes&r', 1, 12, 'key')
    scan = Scan('C:/pack', 'pack', 'en_us', 'zh_cn', entries=[entry])
    store = mocker.Mock(output=Path('C:/output'))
    store.load.return_value = scan
    model = mocker.patch('mcpacklocalizer.application.tasks.service.WorkerClient').return_value.__enter__.return_value
    model.translate.return_value, model.info = ('葡萄', {'backend': 'vulkan'})
    mocker.patch('mcpacklocalizer.application.tasks.service.validate_sources')
    mocker.patch('mcpacklocalizer.application.tasks.service.export_task', return_value={'partial': False})
    result = run_translation(store, Job('resume', output='C:/output', allow_missing_placeholders=True))
    assert result['translated_this_run'] == 1 and result['failed_this_run'] == 0
    assert entry.status == 'translated' and entry.error == ''
    assert scan.metadata['model_config']['allow_missing_placeholders'] is True
    assert json.loads(capsys.readouterr().err)['quality_warnings'][0]['code'] == 'protected_fragments_changed'


def test_failed_translation_progress_includes_reason(mocker, capsys):
    entry = Entry('one', 'ftb:key', 'a.snbt', ['key'], 'Hello', 1, 12, 'key')
    scan = Scan('C:/pack', 'pack', 'en_us', 'zh_cn', entries=[entry])
    store = mocker.Mock(output=Path('C:/output'))
    store.load.return_value = scan
    model = mocker.patch('mcpacklocalizer.application.tasks.service.WorkerClient').return_value.__enter__.return_value
    model.translate.side_effect = RuntimeError('接口认证失败')
    mocker.patch('mcpacklocalizer.application.tasks.service.validate_sources')
    mocker.patch('mcpacklocalizer.application.tasks.service.export_task', return_value={'partial': True})
    result = run_translation(store, Job('resume', output='C:/output'))
    progress = json.loads(capsys.readouterr().err)
    assert progress['error'] == '接口认证失败' and progress['entry_id'] == 'one'
    assert progress['failed'] == result['failed_this_run'] == 1
