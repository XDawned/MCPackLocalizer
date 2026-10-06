# [Module: tests.patch] [Status: 开发中] [Brief: 补丁覆盖边界、源文件变化和不完整产物控制]
from pathlib import Path

import pytest

from mcpacklocalizer.core.pack.extraction import scan_pack
from mcpacklocalizer.core.pack.patch import build_patch, safe_path, validate_output

ROOT = "C:/mcpl-tests/pack"
FILE = ROOT + "/config/ftbquests/quests/chapters/a.snbt"


def test_export_changes_only_text_in_new_source_version(memory_files, mocker):
    memory_files[FILE] = '{id:"A" title:"Iron Ingot" reward_count: 32L // new gameplay\n}'
    scan = scan_pack(Path(ROOT))
    scan.entries[0].translation = "铁锭"
    write = mocker.patch("mcpacklocalizer.core.pack.patch.atomic_write")
    manifest = build_patch(scan, Path("C:/mcpl-tests/output"))
    raw = write.call_args_list[0].args[1].decode()
    assert 'title:"铁锭"' in raw and "reward_count: 32L // new gameplay" in raw
    assert len(manifest["files"]) == 1 and manifest["partial"] is False


def test_numeric_hint_is_exported_without_marking_patch_partial(memory_files, mocker):
    memory_files[FILE] = '{title:"Collect 64 items" reward_count:32L}'
    scan = scan_pack(Path(ROOT))
    entry = scan.entries[0]
    entry.translation, entry.status = "收集32个物品", "translated"
    write = mocker.patch("mcpacklocalizer.core.pack.patch.atomic_write")
    manifest = build_patch(scan, Path("C:/mcpl-tests/output"))
    assert not manifest["partial"] and manifest["pending_entries"] == 0
    hint, = manifest["quality_warnings"]
    assert hint["entry_id"] == entry.id and hint["added"] == ["32"]
    assert scan.metadata["quality_warnings"] == manifest["quality_warnings"]
    report = next(call.args[1] for call in write.call_args_list if call.args[0].name == "report.html")
    assert "质量提示（不阻断）" in report and "原文数字" in report
    patch = next(call.args[1].decode() for call in write.call_args_list if call.args[0].name == "a.snbt")
    assert 'title:"收集32个物品"' in patch and "reward_count:32L" in patch
    entry.translation = "收集64个物品"
    manifest = build_patch(scan, Path("C:/mcpl-tests/output"))
    assert manifest["quality_warnings"] == scan.metadata["quality_warnings"] == []


def test_saved_relaxed_policy_exports_missing_placeholders_and_refreshes_warnings(memory_files, mocker):
    memory_files[FILE] = '{title:"&bGrapes&r"}'
    scan = scan_pack(Path(ROOT))
    entry = scan.entries[0]
    entry.translation, entry.status = "葡萄", "translated"
    write = mocker.patch("mcpacklocalizer.core.pack.patch.atomic_write")
    with pytest.raises(ValueError, match="保留符"):
        build_patch(scan, Path("C:/mcpl-tests/output"))
    write.assert_not_called()
    scan.metadata["model_config"] = {"allow_missing_placeholders": True}
    manifest = build_patch(scan, Path("C:/mcpl-tests/output"))
    assert not manifest["partial"] and manifest["pending_entries"] == 0
    hint, = manifest["quality_warnings"]
    assert hint["missing"] == ["&b", "&r"] and hint["entry_id"] == entry.id
    report = next(call.args[1] for call in write.call_args_list if call.args[0].name == "report.html")
    assert "缺失保留符" in report
    entry.translation = "&b葡萄&r"
    assert build_patch(scan, Path("C:/mcpl-tests/output"))["quality_warnings"] == []


def test_changed_source_and_incomplete_translation_refuse_export(memory_files, mocker):
    memory_files[FILE] = '{title:"Iron Ingot"}'
    scan = scan_pack(Path(ROOT))
    write = mocker.patch("mcpacklocalizer.core.pack.patch.atomic_write")
    with pytest.raises(ValueError, match="尚无译文"):
        build_patch(scan, Path("C:/mcpl-tests/output"))
    memory_files[FILE] = '{title:"Gold Ingot"}'
    with pytest.raises(ValueError, match="源文件在识别后已变化"):
        build_patch(scan, Path("C:/mcpl-tests/output"), allow_partial=True)
    write.assert_not_called()


@pytest.mark.parametrize("relative", ["../outside", "C:/outside", "..\\outside", "/outside"])
def test_output_path_traversal_is_rejected(relative):
    with pytest.raises(ValueError):
        safe_path(Path("C:/mcpl-tests/patch"), relative)


def test_game_directory_cannot_be_used_as_output():
    with pytest.raises(ValueError):
        validate_output(Path(ROOT), Path(ROOT + "/patch"))


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16", "utf-16-be"])
def test_patch_preserves_bom_byte_order_and_crlf(memory_files, mocker, encoding):
    from mcpacklocalizer.core.formats.documents import encode_text
    source = '{\r\n title:"Title" count:32L\r\n}'
    memory_files[FILE] = encode_text(source, encoding)
    scan = scan_pack(Path(ROOT))
    scan.entries[0].translation = "标题"
    write = mocker.patch("mcpacklocalizer.core.pack.patch.atomic_write")
    build_patch(scan, Path("C:/mcpl-tests/output"))
    expected = source.replace('"Title"', '"标题"')
    assert write.call_args_list[0].args[1] == encode_text(expected, encoding)


def test_tampered_snapshot_document_fails_before_output(memory_files, mocker):
    memory_files[FILE] = '{title:"Title" count:32L}'
    scan = scan_pack(Path(ROOT))
    scan.documents[0].text = scan.documents[0].text.replace("32L", "64L")
    scan.entries[0].translation = "标题"
    write = mocker.patch("mcpacklocalizer.core.pack.patch.atomic_write")
    with pytest.raises(ValueError, match="快照文档"):
        build_patch(scan, Path("C:/mcpl-tests/output"))
    write.assert_not_called()


def test_existing_locale_is_not_silently_overwritten(memory_files, mocker):
    memory_files[ROOT + "/config/ftbquests/quests/lang/en_us.snbt"] = '{quest.A.title:"Iron Ingot"}'
    memory_files[ROOT + "/config/ftbquests/quests/lang/zh_cn.snbt"] = '{quest.A.title:"人工译文"}'
    scan = scan_pack(Path(ROOT))
    scan.entries[0].translation = "铁锭"
    write = mocker.patch("mcpacklocalizer.core.pack.patch.atomic_write")
    with pytest.raises(ValueError, match="已存在目标语言文件"):
        build_patch(scan, Path("C:/mcpl-tests/output"))
    write.assert_not_called()


def test_untranslated_existing_locale_does_not_block_unrelated_partial_patch(memory_files, mocker):
    memory_files[FILE] = '{title:"Iron Ingot"}'
    memory_files[ROOT + "/kubejs/assets/minecraft/lang/en_us.json"] = '{"item.pack.test":"Gold Ingot"}'
    memory_files[ROOT + "/kubejs/assets/minecraft/lang/zh_cn.json"] = '{"item.pack.test":"已有译文"}'
    scan = scan_pack(Path(ROOT))
    scan.entries[0].translation = "铁锭"
    mocker.patch("mcpacklocalizer.core.pack.patch.atomic_write")
    manifest = build_patch(scan, Path("C:/mcpl-tests/output"), allow_partial=True)
    assert len(manifest["files"]) == 1
    assert manifest["partial"] is False
    assert manifest["excluded_resources"][0]["reason"] == "existing-target-locale"


def test_reexport_keeps_verified_mod_in_manifest(memory_files, mocker):
    from mcpacklocalizer.core.pack.extraction import digest
    memory_files[FILE] = '{title:"Iron Ingot"}'
    memory_files["C:/mcpl-tests/output/patch/mods/i18n.jar"] = "mock jar"
    scan = scan_pack(Path(ROOT))
    scan.entries[0].translation = "铁锭"
    scan.metadata["i18n_mod"] = {"status": "downloaded", "path": "mods/i18n.jar", "sha256": digest("mock jar")}
    mocker.patch("mcpacklocalizer.core.pack.patch.atomic_write")
    manifest = build_patch(scan, Path("C:/mcpl-tests/output"))
    assert manifest["files"][-1]["kind"] == "i18n-mod"


def test_old_snapshot_cannot_overwrite_existing_resource_even_with_replace_flag(memory_files, mocker):
    source = ROOT + "/kubejs/assets/minecraft/lang/en_us.json"
    target = ROOT + "/kubejs/assets/minecraft/lang/zh_cn.json"
    memory_files[source] = '{"item.minecraft.stone":"Custom Stone"}'
    scan = scan_pack(Path(ROOT))
    scan.entries[0].translation = "错误的旧译文"
    memory_files[target] = '{"item.minecraft.stone":"整合包已有译文"}'
    write = mocker.patch("mcpacklocalizer.core.pack.patch.atomic_write")
    manifest = build_patch(scan, Path("C:/mcpl-tests/output"), replace_existing_locale=True)
    assert manifest["files"] == [] and manifest["pending_entries"] == 0
    assert all("patch" not in call.args[0].parts for call in write.call_args_list)
    assert scan.entries[0].translation == "错误的旧译文"  # Checkpoint retained for recovery.


def test_previously_generated_excluded_patch_is_backed_up_before_removal(memory_files, mocker):
    import json
    memory_files[ROOT + "/kubejs/assets/custom/lang/en_us.json"] = '{"item.custom.a":"English"}'
    scan = scan_pack(Path(ROOT))
    scan.entries[0].translation = "错误译文"
    memory_files[ROOT + "/kubejs/assets/custom/lang/zh_cn.json"] = '{"item.custom.a":"已有译文"}'
    relative = "kubejs/assets/custom/lang/zh_cn.json"
    memory_files["C:/mcpl-tests/output/patch/" + relative] = '{"item.custom.a":"错误译文"}'
    memory_files["C:/mcpl-tests/output/manifest.json"] = json.dumps({"files": [
        {"source": "kubejs/assets/custom/lang/en_us.json", "path": relative}]})
    write = mocker.patch("mcpacklocalizer.core.pack.patch.atomic_write")
    remove = mocker.patch.object(Path, "unlink")
    manifest = build_patch(scan, Path("C:/mcpl-tests/output"))
    assert manifest["files"] == []
    assert "excluded-resources" in write.call_args_list[0].args[0].parts
    assert write.call_args_list[0].args[1] == '{"item.custom.a":"错误译文"}'.encode()
    remove.assert_called_once_with()
    assert manifest["excluded_resource_backups"][0]["path"] == relative
