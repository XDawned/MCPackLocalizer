import hashlib
import io
import json
import zipfile

import pytest

from mcpacklocalizer.core.mods.scan import (
    ResourceOptions,
    detect,
    get_cfpa,
    parse_language,
    select_assets,
    write_report,
)


def zip_bytes(files):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value)
    return data.getvalue()


def write_zip(path, files):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(zip_bytes(files))
    return path


def mod_fixture(tmp_path, name="pack", version="1.0", english=None):
    root = tmp_path / name
    write_zip(root / "mods" / "example.jar", {
        "fabric.mod.json": {"id": "example", "version": version},
        "assets/example/lang/en_us.json": english or {"native": "Native", "community": "Community",
            "iron": "Iron %s", "old": "Old fallback", "brand": "Brand", "empty": "Hidden"},
        "assets/example/lang/zh_cn.json": {"native": "自带", "brand": "Brand", "empty": ""},
    })
    high = write_zip(tmp_path / "community.zip", {"assets/example/lang/zh_cn.json": {"community": "社区"}})
    low = write_zip(tmp_path / "old.zip", {"assets/example/lang/zh_cn.json": {"old": "旧版本"}})
    return root, [(high, {"kind": "local"}), (low, {"kind": "local"})]


def test_whole_file_fallback_and_native_chinese_and_reuse_provenance(tmp_path):
    root, sources = mod_fixture(tmp_path)
    report = detect(root, sources)
    assert {r["key"] for r in report["missing"]} == {"iron", "old"}
    assert report["totals"]["identical_keys"] == 1 and report["totals"]["empty_keys"] == 1
    assert all(row["provider_ids"] == ["example"] and row["reusable"] for row in report["missing"])
    assert report["missing"][0]["provider_versions"] == {"example": "1.0"}


def test_nested_jar_identity_is_used_instead_of_container_identity(tmp_path):
    root, sources = mod_fixture(tmp_path)
    child = zip_bytes({"fabric.mod.json": {"id": "child", "version": "2.0"},
                       "assets/child/lang/en_us.json": {"key": "Nested"}})
    write_zip(root / "mods/container.jar", {"fabric.mod.json": {"id": "container", "version": "1.0"},
                                           "META-INF/jars/child.jar": child})
    row = next(r for r in detect(root, sources)["missing"] if r["namespace"] == "child")
    assert row["provider_ids"] == ["child"]


def test_conflicting_mod_english_and_pack_overrides_do_not_enter_shared_memory(tmp_path):
    root, sources = mod_fixture(tmp_path)
    write_zip(root / "mods/z.jar", {"fabric.mod.json": {"id": "another", "version": "1.0"},
                                     "assets/example/lang/en_us.json": {"iron": "Different iron"}})
    report = detect(root, sources)
    assert not next(r for r in report["missing"] if r["key"] == "iron")["reusable"]
    path = root / "kubejs/assets/example/lang/en_us.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"old":"Pack-specific context"}', encoding="utf-8")
    report = detect(root, sources)
    assert not next(r for r in report["missing"] if r["key"] == "old")["reusable"]


def test_corrupt_chinese_file_is_uncertain_and_rich_values_preserve_structure(tmp_path):
    root, sources = mod_fixture(tmp_path)
    write_zip(root / "mods/broken.jar", {"fabric.mod.json": {"id": "broken"},
        "assets/broken/lang/en_us.json": {"key": "Unknown"}, "assets/broken/lang/zh_cn.json": '{"key":"x" "a":"b"}'})
    report = detect(root, sources)
    assert report["uncertain"][0]["namespace"] == "broken" and not report["scan_complete"]
    parsed = parse_language(b'{"rich":["Hi",{"text":" there","color":"red"}]}', "json")
    assert parsed["rich"] == "Hi there" and parsed["rich"].raw[1]["color"] == "red"


def test_lenient_comments_and_control_characters_preserve_literal_urls():
    warnings = []
    assert parse_language(b'{// comment\n"url":"https://x.test/", "k":"first\nsecond",}', "json", warnings) == {
        "url": "https://x.test/", "k": "first\nsecond"}
    assert warnings[0]["severity"] == "notice"


def test_offline_local_cfpa_uses_bundled_mapping_and_unknown_versions_fail(tmp_path):
    _root, sources = mod_fixture(tmp_path)
    args = ResourceOptions("1.20.1", "forge", tmp_path / "cache", True, [sources[0][0]])
    assert get_cfpa(args)[0][1]["sha256"]
    assert args.pack_metadata["packFormat"] == 15
    with pytest.raises(ValueError, match="映射"):
        get_cfpa(ResourceOptions("1.99", "forge", tmp_path / "cache", True, [sources[0][0]]))


def test_legacy_format_selection_and_quilt_neoforge_fallback(tmp_path):
    root, _ = mod_fixture(tmp_path)
    write_zip(root / "mods/legacy.jar", {"fabric.mod.json": {"id": "legacy"},
        "assets/legacy/lang/en_US.lang": "legacy.key=Hello=World\n",
        "assets/legacy/lang/en_us.json": {"wrong.format": "Ignore"}})
    report = detect(root, [], legacy=True)
    assert [r["key"] for r in report["missing"]] == ["legacy.key"]
    meta = {"games": [{"gameVersions": "[1.20,1.20.1]", "convertFrom": ["1.20"]}],
            "assets": [{"targetVersion": "1.20", "loader": "Forge"}, {"targetVersion": "1.20", "loader": "Fabric"}]}
    assert select_assets(meta, "1.20.1", "quilt")[0]["loader"] == "Fabric"
    assert select_assets(meta, "1.20.1", "neoforge")[0]["loader"] == "Forge"


def test_download_checksum_cache_offline_and_index_fallback(tmp_path, monkeypatch):
    metadata = {"games": [{"gameVersions": "[1.20,1.20.1]", "convertFrom": ["1.20"], "packFormat": 15}],
                "assets": [{"targetVersion": "1.20", "loader": "Fabric", "filename": "test.zip", "md5Filename": "test.md5"}]}
    payload = zip_bytes({"assets/example/lang/zh_cn.json": {"iron": "铁 %s"}})
    md5 = hashlib.md5(payload).hexdigest().encode()
    calls = []

    def fetch(url, limit=None):
        calls.append(url)
        return md5 if url.endswith(".md5") else json.dumps({}).encode() if url.endswith("version-index.json") else payload

    monkeypatch.setattr("mcpacklocalizer.core.mods.scan.fetch", fetch)
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps(metadata), encoding="utf-8")
    options = ResourceOptions("1.20.1", "quilt", tmp_path / "cache", metadata=meta, release="indexed")
    packs = get_cfpa(options)
    assert packs[0][1]["release"] == "autobuild" and packs[0][1]["selection_note"]
    assert len(calls) == 3
    options.offline = True
    assert get_cfpa(options)[0][1]["sha256"] == packs[0][1]["sha256"] and len(calls) == 3
    packs[0][0].write_bytes(b"corrupted cache")
    with pytest.raises(ValueError, match="校验和不匹配"):
        get_cfpa(options)
    options.offline = False
    monkeypatch.setattr("mcpacklocalizer.core.mods.scan.fetch", lambda url, *args: b"0" * 32 if url.endswith(".md5") else payload)
    options.release = "autobuild"
    with pytest.raises(ValueError, match="校验和不匹配"):
        get_cfpa(options)
    assert packs[0][0].read_bytes() == b"corrupted cache"


def test_enabled_paxi_packs_require_active_mod_and_ignore_inactive_files(tmp_path):
    root, sources = mod_fixture(tmp_path)
    write_zip(root / "mods/paxi-forge.jar", {})
    write_zip(root / "config/paxi/resourcepacks/enabled.zip", {"assets/example/lang/zh_cn.json": {"iron": "补充 %s"}})
    write_zip(root / "config/paxi/resourcepacks/inactive.zip", {"assets/example/lang/zh_cn.json": {"old": "未启用"}})
    (root / "options.txt").write_text('resourcePacks:["vanilla","mod_resources","enabled.zip"]', encoding="utf-8")
    report = detect(root, sources)
    assert report["scan_complete"] and [r["key"] for r in report["missing"]] == ["old"]
    (root / "mods/paxi-forge.jar").rename(root / "mods/paxi-forge.jar.disabled")
    assert not detect(root, sources)["scan_complete"]


def test_quilt_and_legacy_forge_providers_and_invalid_metadata_fall_back(tmp_path):
    root, sources = mod_fixture(tmp_path)
    write_zip(root / "mods/quilt.jar", {"quilt.mod.json": {"quilt_loader": {"id": "quilt_example", "version": "1.2"}},
                                       "assets/quilt_example/lang/en_us.json": {"key": "Quilt"}})
    write_zip(root / "mods/legacy.jar", {"mcmod.info": '[{"modid":"oldforge","version":"1.0"}]',
                                        "assets/oldforge/lang/en_US.lang": "key=Old Forge\n"})
    write_zip(root / "mods/unknown.jar", {"fabric.mod.json": "[]", "assets/unknown/lang/en_us.json": {"key": "Unknown"}})
    report = detect(root, sources)
    row = next(r for r in report["missing"] if r["namespace"] == "quilt_example")
    assert row["provider_ids"] == ["quilt_example"] and row["provider_versions"] == {"quilt_example": "1.2"}
    assert not next(r for r in report["missing"] if r["namespace"] == "unknown")["reusable"]
    assert detect(root, [], legacy=True)["missing"][0]["provider_ids"] == ["oldforge"]


def test_report_escapes_untrusted_content_and_namespace_cannot_escape_output(tmp_path):
    root, sources = mod_fixture(tmp_path, english={"key": "</script><img src=x> __DATA__ &"})
    write_zip(root / "mods/unsafe.jar", {"assets/../lang/en_us.json": {"bad": "Unsafe"}})
    report = detect(root, sources)
    assert not report["scan_complete"] and len(report["missing"]) == 1
    output = tmp_path / "report"
    write_report(report, output)
    page = (output / "report.html").read_text(encoding="utf-8")
    assert "</script><img" not in page and "\\u003c/script" in page
    assert "__DATA__" in page and "复用状态" in page
    assert json.loads((output / "missing-languages/example/en_us.json").read_bytes())["key"].startswith("</script>")
