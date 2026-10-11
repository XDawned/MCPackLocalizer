# [Module: tests.core.mods.cfpa_fallback] [Status: 已完成] [Brief: GitHub 超时回退、离线快照与完整性校验]
import hashlib
import http.client
import io
import json
import urllib.error
import zipfile

import pytest

from mcpacklocalizer.core.mods import scan


def archive_bytes(text):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("assets/example/lang/zh_cn.json", json.dumps({"key": text}, ensure_ascii=False))
    return stream.getvalue()


def write_pair(root, tag, asset, data):
    folder = scan.release_folder(root, tag)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / asset["filename"]).write_bytes(data)
    (folder / asset["md5Filename"]).write_text(hashlib.md5(data).hexdigest(), encoding="ascii")
    return folder / asset["filename"]


@pytest.fixture
def resources(tmp_path, monkeypatch):
    bundled = tmp_path / "resources" / "cfpa"
    bundled.mkdir(parents=True)
    monkeypatch.setattr(scan, "CFPA_RESOURCES", bundled)
    assets = [{"targetVersion": version, "loader": "Forge", "filename": version + ".zip",
               "md5Filename": version + ".md5"} for version in ("1.20", "1.19")]
    metadata = {"games": [{"gameVersions": "[1.20,1.20.1]", "convertFrom": ["1.20", "1.19"],
                           "packFormat": 15}], "assets": assets}
    (bundled / "i18nMetaData.json").write_text(json.dumps(metadata), encoding="utf-8")
    (bundled / "version-index.json").write_text('{"1.20":"snapshot"}', encoding="utf-8")
    for asset in assets:
        for tag in ("snapshot", "autobuild"):
            write_pair(bundled, tag, asset, archive_bytes("内置"))
    options = scan.ResourceOptions("1.20.1", "forge", tmp_path / "cache")
    return bundled, metadata, options


@pytest.mark.parametrize("error", [
    TimeoutError("超时"), urllib.error.URLError("连接失败"),
    urllib.error.HTTPError("url", 503, "不可用", {}, None), http.client.IncompleteRead(b"partial"),
])
def test_first_run_network_failure_uses_bundled_resources(resources, mocker, error):
    bundled, _metadata, options = resources
    fetch = mocker.patch.object(scan, "fetch", side_effect=error)
    packs = scan.get_cfpa(options)
    assert len(packs) == 2 and options.pack_metadata["packFormat"] == 15
    assert all(path.is_relative_to(bundled) and record["acquisition"] == "bundled" for path, record in packs)
    assert all("线上访问失败" in record["selection_note"] for _path, record in packs)
    # 元数据和首个发布请求失败后，同次任务不再逐个等待发布请求。
    assert fetch.call_count == 2
    assert not options.cache.exists()


def test_metadata_cache_precedes_bundle_and_corruption_is_skipped(resources, mocker):
    bundled, _metadata, options = resources
    mocker.patch.object(scan, "fetch", side_effect=TimeoutError)
    cache = options.cache / "version-index.json"
    cache.parent.mkdir()
    cache.write_text('{"1.20":"cached"}', encoding="utf-8")
    assert scan.cached_json(scan.INDEX_URL, cache, False) == {"1.20": "cached"}
    cache.write_text("broken", encoding="utf-8")
    assert scan.cached_json(scan.INDEX_URL, cache, False) == {"1.20": "snapshot"}
    cache.write_text("[]", encoding="utf-8")
    assert scan.cached_json(scan.INDEX_URL, cache, True) == {"1.20": "snapshot"}
    (bundled / "version-index.json").write_text("broken", encoding="utf-8")
    with pytest.raises(ValueError, match="离线元数据缺失或无效"):
        scan.cached_json(scan.INDEX_URL, cache, False)


def test_online_metadata_updates_cache_without_modifying_bundle(resources, mocker):
    bundled, _metadata, options = resources
    original = (bundled / "version-index.json").read_bytes()
    fresh = b'{"1.20":"new"}'
    mocker.patch.object(scan, "fetch", return_value=fresh)
    cache = options.cache / "version-index.json"
    assert scan.cached_json(scan.INDEX_URL, cache, False) == {"1.20": "new"}
    assert cache.read_bytes() == fresh
    assert (bundled / "version-index.json").read_bytes() == original


def test_zip_timeout_preserves_old_pair_and_uses_its_own_checksum(resources, mocker):
    _bundled, metadata, options = resources
    options.metadata = options.cache.parent / "metadata.json"
    options.metadata.write_text(json.dumps(metadata), encoding="utf-8")
    old_data = archive_bytes("用户缓存")
    old_path = write_pair(options.cache, "autobuild", metadata["assets"][0], old_data)
    new_md5 = hashlib.md5(archive_bytes("新线上内容")).hexdigest().encode()
    fetch = mocker.patch.object(scan, "fetch", side_effect=[new_md5, TimeoutError("ZIP 超时")])
    packs = scan.get_cfpa(options)
    assert packs[0][0] == old_path and packs[0][1]["acquisition"] == "cache"
    assert packs[0][1]["md5"] == hashlib.md5(old_data).hexdigest()
    assert old_path.read_bytes() == old_data
    assert old_path.with_suffix(".md5").read_bytes() != new_md5
    assert packs[1][1]["acquisition"] == "bundled" and fetch.call_count == 2


def test_offline_uses_bundled_index_and_skips_corrupt_cache(resources, mocker):
    bundled, metadata, options = resources
    options.offline, options.release = True, "indexed"
    bad = write_pair(options.cache, "snapshot", metadata["assets"][0], archive_bytes("损坏前"))
    bad.write_bytes(b"broken")
    fetch = mocker.patch.object(scan, "fetch", side_effect=AssertionError("离线模式不应访问网络"))
    packs = scan.get_cfpa(options)
    assert all(path.is_relative_to(bundled) and record["release"] == "snapshot" for path, record in packs)
    assert bad.read_bytes() == b"broken"
    fetch.assert_not_called()


def test_new_index_release_falls_back_with_actual_tag_in_report(resources, mocker):
    _bundled, _metadata, options = resources
    options.release = "indexed"
    options.cache.mkdir()
    (options.cache / "version-index.json").write_text('{"1.20":"new-snapshot"}', encoding="utf-8")
    mocker.patch.object(scan, "fetch", side_effect=TimeoutError)
    packs = scan.get_cfpa(options)
    assert all(record["release"] == "autobuild" and "/autobuild/" in record["url"] for _, record in packs)
    assert all("new-snapshot" in record["selection_note"] for _, record in packs)


def test_online_checksum_failure_does_not_silently_use_bundle(resources, mocker):
    _bundled, metadata, options = resources
    options.metadata = options.cache.parent / "metadata.json"
    options.metadata.write_text(json.dumps(metadata), encoding="utf-8")
    mocker.patch.object(scan, "fetch", side_effect=[b"0" * 32, archive_bytes("错误下载")])
    with pytest.raises(ValueError, match="CFPA 校验和不匹配"):
        scan.get_cfpa(options)
    assert not options.cache.exists()


def test_missing_offline_pair_reports_failure(resources, mocker):
    bundled, metadata, options = resources
    for tag in ("autobuild", "snapshot"):
        (scan.release_folder(bundled, tag) / metadata["assets"][0]["md5Filename"]).unlink()
    mocker.patch.object(scan, "fetch", side_effect=TimeoutError)
    with pytest.raises(ValueError, match="离线资源包缺失或校验和不匹配"):
        scan.get_cfpa(options)


def test_source_metadata_mapping_is_available_without_downloads():
    root = scan.CFPA_RESOURCES
    metadata = json.loads((root / "i18nMetaData.json").read_bytes())
    index = json.loads((root / "version-index.json").read_bytes())
    assert scan.select_game(metadata, "1.20.1")["packFormat"] == 15
    assert scan.select_assets(metadata, "1.21.1", "fabric")
    assert index and all(isinstance(tag, str) for tag in index.values())
