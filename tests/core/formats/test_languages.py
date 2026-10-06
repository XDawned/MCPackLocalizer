# [Module: tests.tasks] [Status: 已完成] [Brief: 结构化任务服务与核心功能回归]
import json
from pathlib import Path

import pytest

from mcpacklocalizer.application.tasks.jobs import Job
from mcpacklocalizer.application.tasks.worker import perform
from mcpacklocalizer.core.formats.languages import (
    FORMATS,
    backfill_language,
    convert_language,
    dumps_language,
    extract_language,
    language_bindings,
    loads_language,
)
from mcpacklocalizer.core.pack.extraction import scan_pack

ROOT = 'C:/mcpl-tests/pack'
FILE = ROOT + '/config/ftbquests/quests/chapters/a.snbt'
BUNDLE = Path('C:/mcpl-tests/language-bundle')
OUTPUT = Path('C:/mcpl-tests/filled')

@pytest.fixture
def bundle_files(memory_files, mocker):

    def write(path, content):
        memory_files[path.as_posix()] = content
    mocker.patch('mcpacklocalizer.core.formats.languages.atomic_write', side_effect=write)
    mocker.patch('mcpacklocalizer.core.pack.patch.atomic_write', side_effect=write)
    return memory_files

@pytest.mark.parametrize('format', FORMATS)
def test_language_codecs_roundtrip_unicode_multiline_and_equals(format):
    data = {'key': '  中文 &a%s "quote" \\ = equals\nline 2😀  ', 'empty': ''}
    assert loads_language(dumps_language(data, format), format) == data

@pytest.mark.parametrize('format,text', [('json', '{"key": "first", "key": "second"}'), ('json5', "{key: 'one', key: 'two'}"), ('snbt', '{key: "one" key: "two"}'), ('lang', 'key=one\nkey=two'), ('lang', 'no separator'), ('json', '{"key": 1}'), ('snbt', '{key: ["nested"]}')])
def test_ambiguous_or_nonflat_language_inputs_fail(format, text):
    with pytest.raises(ValueError):
        loads_language(text, format)

def test_lang_rejects_unrepresentable_literal_percent_n_and_keys():
    for data in ({'#key': 'value'}, {'a=b': 'value'}, {'key': 'literal %n'}):
        with pytest.raises(ValueError):
            dumps_language(data, 'lang')

@pytest.mark.parametrize('format', FORMATS)
def test_extract_edit_backfill_escapes_and_preserves_gameplay(bundle_files, format):
    source = '{id:"Q" title:"Title" description:["Line 1\\nLine 2"] count:32L // untouched\n}'
    bundle_files[FILE] = source
    result = extract_language(Path(ROOT), BUNDLE, format)
    language = Path(result['language'])
    data = loads_language(bundle_files[language.as_posix()], format)
    for key, value in data.items():
        data[key] = '译文 " \\ =\n' + value
    bundle_files[language.as_posix()] = dumps_language(data, format)
    result = backfill_language(BUNDLE, language, OUTPUT)
    assert not result['partial'] and result['files'] == 1
    patch = bundle_files[(OUTPUT / 'patch/config/ftbquests/quests/chapters/a.snbt').as_posix()].decode()
    assert 'count:32L // untouched' in patch and '译文 \\" \\\\ =\\nTitle' in patch
    assert bundle_files[FILE] == source
    assert json.loads(bundle_files[(OUTPUT / 'snapshot.json').as_posix()])['entries'][0]['origin'] == 'manual'

def test_duplicate_keys_across_files_are_not_overwritten(bundle_files):
    bundle_files[ROOT + '/kubejs/assets/a/lang/en_us.json'] = '{"same.key":"First"}'
    bundle_files[ROOT + '/kubejs/assets/b/lang/en_us.json'] = '{"same.key":"Second", "unique.key":"Third"}'
    first = language_bindings(scan_pack(Path(ROOT)))
    second = language_bindings(scan_pack(Path(ROOT)))
    assert first == second and len(first) == 3
    assert 'unique.key' in first and 'same.key' not in first
    result = extract_language(Path(ROOT), BUNDLE)
    assert len(json.loads(bundle_files[Path(result['language']).as_posix()])) == 3

def test_backfill_unknown_missing_changed_source_and_existing_output_fail_before_writes(bundle_files):
    bundle_files[FILE] = '{title:"Title" description:["Description"]}'
    result = extract_language(Path(ROOT), BUNDLE)
    lang = Path(result['language'])
    language = json.loads(bundle_files[lang.as_posix()])
    bundle_files[lang.as_posix()] = '{"unknown":"中文"}'
    with pytest.raises(ValueError, match='未知语言键'):
        backfill_language(BUNDLE, lang, OUTPUT)
    bundle_files[lang.as_posix()] = json.dumps({next(iter(language)): '中文'})
    with pytest.raises(ValueError, match='尚无译文'):
        backfill_language(BUNDLE, lang, OUTPUT)
    assert not any(key.startswith(OUTPUT.as_posix()) for key in bundle_files)
    assert backfill_language(BUNDLE, lang, OUTPUT, allow_partial=True)['partial']
    with pytest.raises(ValueError, match='非空'):
        backfill_language(BUNDLE, lang, OUTPUT)
    bundle_files[FILE] = '{title:"Changed"}'
    with pytest.raises(ValueError, match='源文件在识别后已变化'):
        backfill_language(BUNDLE, lang, Path('C:/mcpl-tests/another'), allow_partial=True)

def test_backfill_validates_colors_and_placeholders(bundle_files):
    bundle_files[FILE] = '{title:"&aHello %s"}'
    result = extract_language(Path(ROOT), BUNDLE)
    lang = Path(result['language'])
    data = json.loads(bundle_files[lang.as_posix()])
    bundle_files[lang.as_posix()] = json.dumps({key: '你好' for key in data})
    with pytest.raises(ValueError, match='保留符'):
        backfill_language(BUNDLE, lang, OUTPUT)
    assert not any(key.startswith(OUTPUT.as_posix()) for key in bundle_files)

@pytest.mark.parametrize('format', FORMATS)
def test_old_lang_percent_n_backfills_without_literal_newlines(bundle_files, format):
    source = ROOT + '/resources/assets/custom/lang/en_us.lang'
    bundle_files[source] = '# untouched\r\nkey=Line%nMore\r\nempty=\r\n'
    result = extract_language(Path(ROOT), BUNDLE, format)
    language = Path(result['language'])
    data = loads_language(bundle_files[language.as_posix()], format)
    assert data == {'key': 'Line\nMore'}
    bundle_files[language.as_posix()] = dumps_language({'key': '第一行\n第二行'}, format)
    backfill_language(BUNDLE, language, OUTPUT)
    target = (OUTPUT / 'patch/resources/assets/custom/lang/zh_cn.lang').as_posix()
    assert bundle_files[target].decode() == '# untouched\r\nkey=第一行%n第二行\r\nempty=\r\n'

def test_convert_preserves_empty_values_and_is_not_in_place(bundle_files):
    source = Path('C:/mcpl-tests/en_us.lang')
    output = Path('C:/mcpl-tests/en_us.json5')
    bundle_files[source.as_posix()] = '# comment\none=a=b%nc\nempty=\n'
    assert convert_language(source, output)['entries'] == 2
    assert loads_language(bundle_files[output.as_posix()], 'json5') == {'one': 'a=b\nc', 'empty': ''}
    with pytest.raises(ValueError, match='已存在'):
        convert_language(source, output)
    with pytest.raises(ValueError, match='不能与输入文件相同'):
        convert_language(source, source)

def test_offline_cli_commands_emit_json_without_model(bundle_files, mocker, capsys):
    worker = mocker.patch('mcpacklocalizer.application.tasks.service.WorkerClient')
    bundle_files[FILE] = '{title:"Title"}'
    assert perform(Job('extract-lang', root=ROOT, output=str(BUNDLE), format='json5')) == 0
    extraction = json.loads(capsys.readouterr().out)
    language = extraction['language']
    data = loads_language(bundle_files[Path(language).as_posix()], 'json5')
    bundle_files[Path(language).as_posix()] = dumps_language({key: '标题' for key in data}, 'json5')
    assert perform(Job('backfill', bundle=str(BUNDLE), lang=language, output=str(OUTPUT))) == 0
    assert not json.loads(capsys.readouterr().out)['partial']
    assert perform(Job('convert-lang', source=language, output='C:/mcpl-tests/converted.lang')) == 0
    assert json.loads(capsys.readouterr().out)['format'] == 'lang'
    worker.assert_not_called()
