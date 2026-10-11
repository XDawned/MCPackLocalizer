# [Module: tests.application.cfpa_build] [Status: 已完成] [Brief: 打包动态获取离线资源、失败阻断与快照校验]
import hashlib
import io
import json
import zipfile

import pytest

from mcpacklocalizer.core.mods.scan import (
    INDEX_URL,
    META_URL,
    cfpa_snapshot_assets,
    release_folder,
    validate_cfpa_snapshot,
)
from scripts import build_release, update_cfpa_resources


@pytest.fixture
def downloads(mocker):
    metadata = {"games": [{"gameVersions": "[1.20,1.20.1]", "packFormat": 15, "convertFrom": ["1.20"]}],
                "assets": [{"targetVersion": "1.20", "loader": "Forge", "filename": "test.zip",
                            "md5Filename": "test.md5"}]}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("assets/example/lang/zh_cn.json", '{"key":"中文"}')
    data = stream.getvalue()

    def fetch(url, limit=None):
        if url == META_URL:
            return json.dumps(metadata).encode()
        if url == INDEX_URL:
            return b'{"1.20":"snapshot"}'
        return hashlib.md5(data).hexdigest().encode() if url.endswith(".md5") else data

    return mocker.patch.object(update_cfpa_resources, "fetch", side_effect=fetch)


def test_build_downloads_both_releases_and_generates_valid_manifest(tmp_path, downloads):
    destination = tmp_path / "resources/cfpa"
    update_cfpa_resources.update_resources(destination)
    validate_cfpa_snapshot(destination)
    manifest = json.loads((destination / "manifest.json").read_bytes())
    assert len(manifest["files"]) == 6 and downloads.call_count == 6
    assert (release_folder(destination, "autobuild") / "test.zip").is_file()
    assert (release_folder(destination, "snapshot") / "test.zip").is_file()


@pytest.mark.parametrize("failure", [TimeoutError("超时"), ValueError("校验失败")])
def test_failed_refresh_preserves_existing_files(tmp_path, mocker, failure):
    destination = tmp_path / "cfpa"
    destination.mkdir()
    old_manifest = destination / "manifest.json"
    old_manifest.write_bytes(b"previous manifest")
    mocker.patch.object(update_cfpa_resources, "fetch", side_effect=failure)
    with pytest.raises(type(failure)):
        update_cfpa_resources.update_resources(destination)
    assert old_manifest.read_bytes() == b"previous manifest"
    assert list(destination.iterdir()) == [old_manifest]


def test_snapshot_validation_rejects_changed_or_missing_archive(tmp_path, downloads):
    update_cfpa_resources.update_resources(tmp_path)
    archive = release_folder(tmp_path, "autobuild") / "test.zip"
    archive.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="离线快照文件校验失败"):
        validate_cfpa_snapshot(tmp_path)
    archive.unlink()
    with pytest.raises(FileNotFoundError):
        validate_cfpa_snapshot(tmp_path)


def test_manifest_cannot_omit_required_archive(tmp_path, downloads):
    update_cfpa_resources.update_resources(tmp_path)
    path = tmp_path / "manifest.json"
    manifest = json.loads(path.read_bytes())
    name = (release_folder(tmp_path, "snapshot") / "test.zip").relative_to(tmp_path).as_posix()
    del manifest["files"][name]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="离线快照清单缺少资源"):
        validate_cfpa_snapshot(tmp_path)


def test_snapshot_includes_older_conversion_assets_in_selected_release():
    metadata = {"games": [{"gameVersions": "[1.20,1.20.1]", "convertFrom": ["1.20", "1.19"]}],
                "assets": [{"targetVersion": version, "loader": "Forge", "filename": version + ".zip"}
                           for version in ("1.20", "1.19")]}
    pairs = {(tag, asset["filename"]) for tag, asset in cfpa_snapshot_assets(
        metadata, {"1.20": "new", "1.19": "old"})}
    assert ("new", "1.19.zip") in pairs
    assert ("old", "1.20.zip") not in pairs
    assert ("autobuild", "1.20.zip") in pairs and ("autobuild", "1.19.zip") in pairs


@pytest.fixture
def build_environment(tmp_path, monkeypatch, mocker):
    monkeypatch.setattr(build_release, "BUILD", tmp_path / "build")
    monkeypatch.setenv("SystemRoot", str(tmp_path / "Windows"))
    mocker.patch.object(build_release, "project_version", return_value="2.0.0")
    mocker.patch.object(build_release, "source_commit", return_value="a" * 40)
    return tmp_path


def test_desktop_fetches_resources_before_building_wheel_and_exe(build_environment, mocker):
    def run(*args, **kwargs):
        if "PyInstaller" in args:
            (build_release.BUILD / "desktop").mkdir()

    commands = mocker.patch.object(build_release, "run", side_effect=run)
    build_release.desktop()
    calls = [call.args for call in commands.call_args_list]
    assert calls[0] == (build_release.sys.executable, str(build_release.ROOT / "scripts/update_cfpa_resources.py"))
    assert calls[1][:3] == ("uv", "build", "--wheel")
    assert "PyInstaller" in calls[2]


def test_download_failure_prevents_packaging(build_environment, mocker):
    commands = mocker.patch.object(build_release, "run", side_effect=RuntimeError("资源下载失败"))
    with pytest.raises(RuntimeError, match="资源下载失败"):
        build_release.desktop()
    assert commands.call_count == 1
    assert not (build_release.BUILD / "desktop").exists()
