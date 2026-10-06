# [Module: tests.tasks] [Status: 已完成] [Brief: 结构化任务服务与核心功能回归]
import json
import zipfile

import pytest

from mcpacklocalizer.application.tasks.jobs import Job
from mcpacklocalizer.application.tasks.worker import perform
from mcpacklocalizer.core.mods.combined import mod_scan
from mcpacklocalizer.core.mods.library import ModLibrary, reuse_library
from mcpacklocalizer.core.mods.scan import ResourceOptions, detect
from mcpacklocalizer.core.mods.tasks import build_mod_patch, create_mod_scan, validate_mod_sources
from mcpacklocalizer.core.pack.extraction import Scan
from mcpacklocalizer.core.pack.snapshots import load_snapshot
from tests.core.mods.test_mod_scan import mod_fixture, write_zip


def call(capsys, arguments):
    status = perform(arguments)
    captured = capsys.readouterr()
    return (status, json.loads(captured.out))

def flags(tmp_path, sources, game='1.20.1'):
    return {'game_version': game, 'loader': 'forge', 'offline': True, 'cache': tmp_path / 'cache', 'cfpa_pack': [sources[0][0]], 'translation_library': tmp_path / 'shared.sqlite3'}


def test_manual_exclusions_apply_to_standalone_and_combined_mod_patches(tmp_path):
    root, sources = mod_fixture(tmp_path, english={"iron": "Iron"})
    options = ResourceOptions("1.20.1", "forge", tmp_path / "cache", True, [sources[0][0]])
    options.pack_metadata = {"packFormat": 15}
    scan = create_mod_scan(detect(root, sources), options, tmp_path / "library.sqlite3")
    assert scan.entries
    for entry in scan.entries:
        entry.translation = "铁"
    output = tmp_path / "task"
    manifest = build_mod_patch(scan, output)
    patch = output / "patch" / manifest["files"][0]["path"]
    with zipfile.ZipFile(patch) as archive:
        assert any(name.endswith("/zh_cn.json") for name in archive.namelist())
    excluded = [d.path for d in scan.documents]
    scan.metadata["manual_excluded_resources"] = excluded
    manifest = build_mod_patch(scan, output)
    assert manifest["pending_entries"] == 0 and manifest["excluded_resources"]
    with zipfile.ZipFile(patch) as archive:
        assert archive.namelist() == ["pack.mcmeta"]
    combined = Scan(str(root), scan.pack_id, "en_us", "zh_cn", scan.documents, scan.entries,
                    metadata={"mod_resources": scan.metadata, "manual_excluded_resources": excluded})
    assert mod_scan(combined).metadata["manual_excluded_resources"] == excluded

def test_review_then_cross_pack_cross_version_extract_and_sparse_zip_export(tmp_path, capsys):
    root, sources = mod_fixture(tmp_path, name='pack-a', english={'iron': 'Iron %s'})
    output = tmp_path / 'task-a'
    status, extracted = call(capsys, Job('extract-mods', root=str(root), output=str(output), **flags(tmp_path, sources)))
    assert status == 0 and extracted['pending_entries'] == 1
    entry = load_snapshot(output).entries[0]
    status, reviewed = call(capsys, Job('review', output=str(output), entry_id=entry.id, translation='铁 %s'))
    assert status == 0 and reviewed['library_publication']['published'] == 1
    other, sources = mod_fixture(tmp_path, name='pack-b', version='2.0', english={'iron': 'Iron %s'})
    second = tmp_path / 'task-b'
    status, result = call(capsys, Job('extract-mods', root=str(other), output=str(second), **flags(tmp_path, sources, '1.21.1')))
    assert status == 0 and result['reuse']['counts']['reused'] == 1 and (result['pending_entries'] == 0)
    status, exported = call(capsys, Job('export', output=str(second)))
    assert status == 0 and (not exported['partial'])
    with zipfile.ZipFile(second / 'patch/resourcepacks/MCPackLocalizer-Mod-Translations.zip') as archive:
        assert json.loads(archive.read('assets/example/lang/zh_cn.json')) == {'iron': '铁 %s'}
        assert json.loads(archive.read('pack.mcmeta'))['pack']['pack_format'] == 34
        assert len(archive.namelist()) == 2
    with ModLibrary(tmp_path / 'shared.sqlite3', readonly=True) as library:
        assert library.stats()['states']['reviewed'] == 1

def test_changed_english_gets_reference_not_automatic_translation(tmp_path, capsys):
    root, sources = mod_fixture(tmp_path, english={'iron': 'Gold %s'})
    with ModLibrary(tmp_path / 'shared.sqlite3') as library:
        library.add({'provider_ids': ['example'], 'namespace': 'example', 'key': 'iron', 'source': 'Iron %s', 'translation': '铁 %s', 'source_locale': 'en_us', 'target_locale': 'zh_cn'}, 'reviewed')
    output = tmp_path / 'task'
    status, result = call(capsys, Job('extract-mods', root=str(root), output=str(output), **flags(tmp_path, sources)))
    assert status == 0 and result['reuse']['counts']['source_changed'] == 1
    assert load_snapshot(output).entries[0].translation is None
    report = json.loads((output / 'report.json').read_bytes())
    assert report['missing'][0]['library_match']['status'] == 'source_changed'

def test_model_drafts_resume_and_review_promotes_without_loading_model_for_reused_keys(tmp_path, capsys, monkeypatch):
    root, sources = mod_fixture(tmp_path, english={'iron': 'Iron %s', 'gold': 'Gold %s'})
    calls = []

    class Worker:

        def __init__(self, *args, **kwargs):
            self.info = {'backend': 'test'}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def translate(self, source, context):
            calls.append(source)
            return '铁 %s' if source.startswith('Iron') else '金 %s'
    monkeypatch.setattr('mcpacklocalizer.application.tasks.service.WorkerClient', Worker)
    output = tmp_path / 'task'
    status, result = call(capsys, Job('localize-mods', root=str(root), output=str(output), **flags(tmp_path, sources), limit=int('1'), allow_partial=True, no_glossary=True))
    assert status == 1 and result['translated_this_run'] == 1
    with ModLibrary(tmp_path / 'shared.sqlite3', readonly=True) as library:
        assert library.stats()['states']['draft'] == 1
    status, result = call(capsys, Job('resume', output=str(output), no_glossary=True))
    assert status == 0 and result['translated_this_run'] == 1 and (len(calls) == 2)
    other, sources = mod_fixture(tmp_path, name='other', english={'iron': 'Iron %s', 'gold': 'Gold %s'})
    status, result = call(capsys, Job('scan-mods', root=str(other), **flags(tmp_path, sources)))
    assert status == 0 and result['reuse']['counts']['draft_only'] == 2
    reused = tmp_path / 'reused-task'
    status, result = call(capsys, Job('localize-mods', root=str(other), output=str(reused), **flags(tmp_path, sources), reuse_policy='all', no_glossary=True))
    assert status == 0 and result['translated_this_run'] == 0 and (len(calls) == 2)
    entry = load_snapshot(output).entries[0]
    status, _ = call(capsys, Job('review', output=str(output), entry_id=entry.id, translation=entry.translation))
    assert status == 0
    with ModLibrary(tmp_path / 'shared.sqlite3', readonly=True) as library:
        assert library.stats()['states']['reviewed'] == 1

def test_source_inventory_prevents_resume_after_jar_or_new_locale_changes(tmp_path):
    root, sources = mod_fixture(tmp_path)
    options = ResourceOptions('1.20.1', 'forge', tmp_path / 'cache', True, [sources[0][0]])
    options.pack_metadata = {'packFormat': 15}
    scan = create_mod_scan(detect(root, sources), options, tmp_path / 'memory.sqlite3')
    validate_mod_sources(scan)
    locale = root / 'kubejs/assets/example/lang/zh_cn.json'
    locale.parent.mkdir(parents=True)
    locale.write_text('{"iron":"后来补充"}', encoding='utf-8')
    with pytest.raises(ValueError, match='清单'):
        validate_mod_sources(scan)
    locale.unlink()
    (root / 'mods/example.jar').write_bytes(b'changed')
    with pytest.raises(ValueError, match='已变化'):
        validate_mod_sources(scan)

def test_legacy_reuse_rejects_modern_literal_newlines(tmp_path):
    root, _ = mod_fixture(tmp_path)
    write_zip(root / 'mods/legacy.jar', {'fabric.mod.json': {'id': 'legacy', 'version': '1'}, 'assets/legacy/lang/en_us.lang': 'key=Iron Ingot\n'})
    options = ResourceOptions('1.12.2', 'forge', tmp_path / 'cache')
    options.pack_metadata = {'packFormat': 3}
    library_path = tmp_path / 'memory.sqlite3'
    with ModLibrary(library_path) as library:
        library.add({'provider_ids': ['legacy'], 'namespace': 'legacy', 'key': 'key', 'source': 'Iron Ingot', 'translation': '铁\n锭', 'source_locale': 'en_us', 'target_locale': 'zh_cn'}, 'reviewed')
    scan = create_mod_scan(detect(root, [], legacy=True), options, library_path)
    assert scan.entries[0].translation is None and scan.metadata['mod_library']['counts']['invalid'] == 1
    assert reuse_library(scan, library_path)['invalid'] == 1

def test_library_portable_cli_and_default_game_detection(tmp_path, capsys):
    root, sources = mod_fixture(tmp_path)
    (root / 'version.json').write_text(json.dumps({'clientVersion': '1.20.1', 'libraries': [{'name': 'net.minecraftforge:fmlloader:1.20.1-47.4.0'}]}), encoding='utf-8')
    library = tmp_path / 'shared.sqlite3'
    status, result = call(capsys, Job('scan-mods', root=str(root), offline=True, cache=str(tmp_path / 'cache'), cfpa_pack=[str(sources[0][0])], translation_library=str(library)))
    assert status == 0 and result['minecraft_version'] == '1.20.1' and (result['loader'] == 'forge')
    assert not library.exists()
    status, result = call(capsys, Job('mod-library', library_action='stats', translation_library=str(library)))
    assert status == 0 and result['records'] == 0

def test_task_import_checks_snapshot_and_portable_import_retains_conflicts(tmp_path, capsys):
    root, sources = mod_fixture(tmp_path, english={'iron': 'Iron %s'})
    task = tmp_path / 'task'
    assert call(capsys, Job('extract-mods', root=str(root), output=str(task), **flags(tmp_path, sources)))[0] == 0
    scan = load_snapshot(task)
    scan.entries[0].translation = '铁 %s'
    scan.entries[0].origin = 'manual'
    snapshot = tmp_path / 'portable-task.json'
    snapshot.write_text(json.dumps(scan.to_dict()), encoding='utf-8')
    target = tmp_path / 'imported.sqlite3'
    args = {'translation_library': target}
    status, result = call(capsys, Job('mod-library', library_action='import', source=str(snapshot), **args))
    assert status == 0 and result['published'] == 1
    with ModLibrary(target) as library:
        record = library.list_records()[0]
        second = library.add(record | {'translation': '铁制 %s'}, 'reviewed')
    exported = tmp_path / 'library.json'
    assert call(capsys, Job('mod-library', library_action='export', output=str(exported), **args))[0] == 0
    assert call(capsys, Job('mod-library', library_action='import', source=str(exported), translation_library=str(tmp_path / 'copy.sqlite3')))[0] == 0
    assert call(capsys, Job('mod-library', library_action='resolve', record_id=int(str(second)), **args))[0] == 0
    assert call(capsys, Job('mod-library', library_action='reject', record_id=int(str(second)), **args))[0] == 0
    status, result = call(capsys, Job('mod-library', library_action='list', state='rejected', **args))
    assert status == 0 and len(result['records']) == 1
    scan.entries[0].source = 'Changed English %s'
    snapshot.write_text(json.dumps(scan.to_dict()), encoding='utf-8')
    assert call(capsys, Job('mod-library', library_action='import', source=str(snapshot), **args))[0] == 2

def test_structured_sources_deferred_and_incomplete_coverage_cannot_claim_complete(tmp_path, capsys):
    root, sources = mod_fixture(tmp_path, english={'rich': ['Hi', {'text': ' there'}], 'blank': ''})
    task = tmp_path / 'task'
    status, result = call(capsys, Job('extract-mods', root=str(root), output=str(task), **flags(tmp_path, sources)))
    assert status == 0 and result['pending_entries'] == 0 and (result['totals']['deferred_keys'] == 2)
    assert call(capsys, Job('export', output=str(task)))[0] == 2
    status, result = call(capsys, Job('export', output=str(task), allow_partial=True))
    assert status == 1 and result['deferred_entries'] == 2
    other, sources = mod_fixture(tmp_path, name='incomplete', english={'community': 'Community'})
    (other / 'options.txt').write_text('resourcePacks:["generated/dynamic"]', encoding='utf-8')
    incomplete = tmp_path / 'incomplete-task'
    assert call(capsys, Job('extract-mods', root=str(other), output=str(incomplete), **flags(tmp_path, sources)))[0] == 2
    status, result = call(capsys, Job('export', output=str(incomplete)))
    assert status == 1 and result['partial'] and (not result['coverage_complete'])
