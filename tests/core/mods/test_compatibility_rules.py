# [Module: tests.core.mods.compatibility_rules] [Status: 已完成] [Brief: 可编辑正则规则、配置校验和导出保护]
import json
import zipfile

import pytest

from mcpacklocalizer import paths
from mcpacklocalizer.core.mods import tasks
from mcpacklocalizer.core.mods.compatibility import (
    RULES_RESOURCE,
    apply_language_rules,
    export_language_value,
    load_rules,
)
from mcpacklocalizer.core.mods.scan import ResourceOptions, detect
from mcpacklocalizer.core.mods.tasks import build_mod_patch, create_mod_scan
from tests.core.mods.test_mod_scan import mod_fixture, write_zip


def write_rules(path, rules):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "rules": rules}, ensure_ascii=False), encoding="utf-8")
    return path


def rule(**changes):
    return {"id": "example", "description": "示例模组名称修正", "namespace": "example(?:_addon)?",
            "key": r"item\.example\..*\.name", "replacements": [{"pattern": "旧称", "replacement": "新称"}],
            **changes}


def test_namespace_key_regex_and_ordered_replacements_with_backreferences(tmp_path):
    substitutions = [{"pattern": r"^旧称：(.*)$", "replacement": r"\g<1>"},
                     {"pattern": r"(\d+)x(\d+)", "replacement": r"\1×\2", "count": 1}]
    rules = load_rules(write_rules(tmp_path / "rules.json", [rule(replacements=substitutions)]))
    for namespace in ("example", "example_addon"):
        fixed, applied = apply_language_rules(namespace, "item.example.machine.name", "旧称：3x4 和 5x6",
                                             legacy=False, rules=rules)
        assert fixed == "3×4 和 5x6" and [r.id for r in applied] == ["example"]
    for namespace, key in (("prefix_example", "item.example.machine.name"),
                           ("example", "item.example.machine.name.suffix")):
        assert export_language_value(namespace, key, "旧称：3x4", legacy=False, rules=rules) == "旧称：3x4"


def test_rule_order_disabling_and_format_filter(tmp_path):
    rules = load_rules(write_rules(tmp_path / "rules.json", [
        rule(language_format="json"),
        rule(id="second", replacements=[{"pattern": "新称", "replacement": "最终名称"}]),
        rule(id="disabled", enabled=False, namespace="["),
    ]))
    fixed, applied = apply_language_rules("example", "item.example.a.name", "旧称", legacy=False, rules=rules)
    assert fixed == "最终名称" and [r.id for r in applied] == ["example", "second"]
    assert export_language_value("example", "item.example.a.name", "旧称", legacy=True, rules=rules) == "旧称"


@pytest.mark.parametrize("changes", [
    {"namespace": "["}, {"key": "["}, {"namespace": 42}, {"key": None},
    {"enabled": "false"}, {"description": []}, {"language_format": "other"},
    {"replacements": []}, {"replacements": [None]},
    {"replacements": [{"pattern": "[", "replacement": "x"}]},
    {"replacements": [{"pattern": "x", "replacement": r"\2"}]},
    {"replacements": [{"pattern": "x", "replacement": r"\g<missing>"}]},
    {"replacements": [{"pattern": "x", "replacement": "x", "count": -1}]},
    {"replacements": [{"pattern": "x", "replacement": "x", "count": True}]},
])
def test_invalid_rules_report_file_and_rule_position(tmp_path, changes):
    path = write_rules(tmp_path / "rules.json", [rule(**changes)])
    with pytest.raises(ValueError) as error:
        load_rules(path)
    assert str(path) in str(error.value) and "第 1 条规则" in str(error.value)


@pytest.mark.parametrize("content", ["broken", "[]", '{"schema_version":2,"rules":[]}',
                                     '{"schema_version":true,"rules":[]}', '{"schema_version":1,"rules":{}}'])
def test_invalid_config_is_not_silently_ignored(tmp_path, content):
    path = tmp_path / "rules.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="兼容配置"):
        load_rules(path)
    with pytest.raises(ValueError, match="无法读取"):
        load_rules(tmp_path / "missing.json")


def test_duplicate_rule_ids_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="重复"):
        load_rules(write_rules(tmp_path / "rules.json", [rule(), rule()]))


def test_desktop_and_worker_share_editable_rules_and_reload_changes(tmp_path, monkeypatch):
    installation = tmp_path / "发布目录"
    external = installation / "resources" / RULES_RESOURCE
    monkeypatch.setattr(paths, "INSTALL_HOME", installation)
    for resources in (installation / "_internal/mcpacklocalizer/resources",
                      installation / "runtime/app/mcpacklocalizer/resources"):
        monkeypatch.setattr(paths, "RESOURCES", resources)
        write_rules(resources / RULES_RESOURCE, [rule(replacements=[{"pattern": "旧称", "replacement": "内置"}])])
        write_rules(external, [rule()])
        assert paths.editable_resource_path(RULES_RESOURCE) == external
        assert export_language_value("example", "item.example.a.name", "旧称", legacy=False) == "新称"
        write_rules(external, [rule(replacements=[{"pattern": "旧称", "replacement": "已修改"}])])
        assert export_language_value("example", "item.example.a.name", "旧称", legacy=False) == "已修改"
        write_rules(external, [])
        assert export_language_value("example", "item.example.a.name", "旧称", legacy=False) == "旧称"
        external.write_text("broken", encoding="utf-8")
        with pytest.raises(ValueError, match="无法读取"):
            export_language_value("example", "item.example.a.name", "旧称", legacy=False)
        external.unlink()
        assert export_language_value("example", "item.example.a.name", "旧称", legacy=False) == "内置"


def test_generic_export_records_rules_and_reads_config_once(tmp_path, monkeypatch, mocker):
    root, sources = mod_fixture(tmp_path, english={"iron": "Iron", "gold": "Gold"})
    options = ResourceOptions("1.20.1", "forge", tmp_path / "cache", offline=True)
    options.pack_metadata = {"packFormat": 15}
    scan = create_mod_scan(detect(root, sources), options, tmp_path / "memory.sqlite3")
    resources = tmp_path / "resources"
    monkeypatch.setattr(paths, "INSTALL_HOME", None)
    monkeypatch.setattr(paths, "RESOURCES", resources)
    write_rules(resources / RULES_RESOURCE, [rule(key=".*", replacements=[{"pattern": "旧称", "replacement": "新称"}])])
    for entry in scan.entries:
        entry.translation = "旧称"
    reads = mocker.spy(tasks, "load_rules")
    output = tmp_path / "task"
    manifest = build_mod_patch(scan, output)
    assert reads.call_count == 1
    with zipfile.ZipFile(output / "patch/resourcepacks/MCPackLocalizer-Mod-Translations.zip") as archive:
        assert json.loads(archive.read("assets/example/lang/zh_cn.json")) == {"gold": "新称", "iron": "新称"}
    assert all(record["rules"] == ["example"] for record in manifest["compatibility_adjustments"])
    assert all(record["reason"] == "示例模组名称修正" for record in manifest["compatibility_adjustments"])
    assert "ProjectE" not in (output / "report.html").read_text(encoding="utf-8")
    assert all(entry.translation == "旧称" for entry in scan.entries)


@pytest.mark.parametrize("replacement", ["", "\n"])
def test_configured_replacements_cannot_break_placeholders_or_lang_format(tmp_path, monkeypatch, replacement):
    root, _ = mod_fixture(tmp_path)
    write_zip(root / "mods/legacy.jar", {"fabric.mod.json": {"id": "legacy", "version": "1"},
                                       "assets/legacy/lang/en_us.lang": "key=Text %s\n"})
    options = ResourceOptions("1.12.2", "forge", tmp_path / "cache", offline=True)
    options.pack_metadata = {"packFormat": 3}
    scan = create_mod_scan(detect(root, [], legacy=True), options, tmp_path / "memory.sqlite3")
    scan.entries[0].translation = "文本 %s"
    resources = tmp_path / "resources"
    monkeypatch.setattr(paths, "INSTALL_HOME", None)
    monkeypatch.setattr(paths, "RESOURCES", resources)
    write_rules(resources / RULES_RESOURCE, [rule(namespace="legacy", key="key", replacements=[
        {"pattern": "%s" if replacement == "" else " ", "replacement": replacement}])])
    output = tmp_path / "task"
    with pytest.raises(ValueError):
        build_mod_patch(scan, output)
    assert not (output / "patch").exists()
