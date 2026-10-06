# [Module: tests.release] [Status: 已完成] [Brief: 发布时拒绝错误来源、混合批次与被修改的构建产物]
import json
import urllib.error
import zipfile

import pytest

from scripts.build_release import native_runtime
from scripts.publish_release import checked_run, digest, publish, validate_assets


@pytest.fixture
def release_assets(tmp_path):
    run = {"head_sha": "a" * 40, "id": 123, "run_attempt": 1, "html_url": "https://example.test/actions/runs/123"}
    for backend in ("cpu", "vulkan", "cuda"):
        stem = f"MCPackLocalizer-2.0.0-win-x64-{backend}"
        archive = tmp_path / f"{stem}.zip"
        archive.write_bytes(b"tested artifact")
        (tmp_path / f"{stem}.sha256").write_text(f"{digest(archive)}  {archive.name}\n", encoding="ascii")
        (tmp_path / f"{stem}.json").write_text(json.dumps({
            "version": "2.0.0", "backend": backend, "commit": run["head_sha"], "run_id": 123, "run_attempt": 1,
            "requirements": "实机验证驱动",
        }), encoding="utf-8")
    return tmp_path, run


def test_release_uses_exact_tested_bytes_and_version(release_assets):
    directory, run = release_assets
    assets, manifests = validate_assets(directory, run, "v2.0.0")
    assert len(assets) == 9 and len(manifests) == 3
    with pytest.raises(ValueError, match="缺少"):
        validate_assets(directory, run, "v2.0.1")


def test_tampered_zip_is_rejected(release_assets):
    directory, run = release_assets
    next(directory.glob("*.zip")).write_bytes(b"changed after testing")
    with pytest.raises(ValueError, match="校验失败"):
        validate_assets(directory, run, "v2.0.0")


@pytest.mark.parametrize("field,value", [("commit", "b" * 40), ("run_id", 124), ("run_attempt", 2)])
def test_mixed_build_artifacts_are_rejected(release_assets, field, value):
    directory, run = release_assets
    manifest = next(directory.glob("*.json"))
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data[field] = value
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="批次不一致"):
        validate_assets(directory, run, "v2.0.0")


def test_manual_confirmation_required_before_api_calls(monkeypatch, mocker):
    monkeypatch.setenv("TESTED", "false")
    request = mocker.patch("scripts.publish_release.api")
    with pytest.raises(ValueError, match="人工测试"):
        checked_run("123")
    request.assert_not_called()


@pytest.mark.parametrize("field,value", [("head_branch", "feature"), ("conclusion", "failure"),
                                         ("event", "pull_request"), ("workflow_id", 99),
                                         ("head_repository", {"id": 999})])
def test_wrong_source_run_cannot_be_published(monkeypatch, mocker, field, value):
    monkeypatch.setenv("TESTED", "true")
    run = {"workflow_id": 1, "conclusion": "success", "status": "completed", "event": "push",
           "head_repository": {"id": 2}, "head_branch": "main"}
    run[field] = value
    mocker.patch("scripts.publish_release.api", side_effect=[{"id": 2, "default_branch": "main"}, run, {"id": 1}])
    with pytest.raises(ValueError, match="默认分支"):
        checked_run("123")


def test_public_release_never_overwrites_assets(release_assets, monkeypatch, mocker):
    directory, run = release_assets
    monkeypatch.setenv("TEST_NOTES", "三个后端实机检查通过")
    mocker.patch("scripts.publish_release.tag_commit", return_value=run["head_sha"])
    mocker.patch("scripts.publish_release.api", return_value={"draft": False})
    upload = mocker.patch("scripts.publish_release.subprocess.run")
    with pytest.raises(ValueError, match="已经发布"):
        publish(directory, run, "v2.0.0", False)
    upload.assert_not_called()


def test_publish_uploads_validated_files_then_makes_draft_public(release_assets, monkeypatch, mocker):
    directory, run = release_assets
    monkeypatch.setenv("TEST_NOTES", "三个后端实机检查通过")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    mocker.patch("scripts.publish_release.tag_commit", return_value=None)
    mocker.patch("scripts.publish_release.api", side_effect=urllib.error.HTTPError("url", 404, "missing", {}, None))
    commands = mocker.patch("scripts.publish_release.subprocess.run")
    publish(directory, run, "v2.0.0", False)
    create, upload, release = [call.args[0] for call in commands.call_args_list]
    assert "--draft" in create and create[create.index("--target") + 1] == run["head_sha"]
    assert upload[:3] == ["gh", "release", "upload"]
    assert set(upload[7:]) == {str(path) for path in directory.iterdir()}
    assert "--draft=false" in release


def test_draft_retry_updates_target_to_tested_commit(release_assets, monkeypatch, mocker):
    directory, run = release_assets
    monkeypatch.setenv("TEST_NOTES", "已测试")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    mocker.patch("scripts.publish_release.tag_commit", return_value=None)
    mocker.patch("scripts.publish_release.api", return_value={"draft": True})
    commands = mocker.patch("scripts.publish_release.subprocess.run")
    publish(directory, run, "v2.0.0", False)
    edit = commands.call_args_list[0].args[0]
    assert edit[:3] == ["gh", "release", "edit"]
    assert edit[edit.index("--target") + 1] == run["head_sha"]


def test_vendor_runtime_extracts_dlls_and_licenses_without_path_escape(tmp_path, mocker):
    archive = tmp_path / "vendor.whl"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("nvidia/component/bin/runtime.dll", b"native")
        bundle.writestr("vendor.dist-info/licenses/LICENSE", b"license")
        bundle.writestr("nvidia/component/include/runtime.h", b"header")
        bundle.writestr("../escaped.dll", b"invalid")
    mocker.patch("scripts.build_release.download", return_value=archive)
    config = {"runtime_wheels": [{"name": "vendor", "url": "url", "sha256": "hash"}],
              "runtime_dlls": ["runtime.dll"]}
    directory = tmp_path / "package"
    libraries = directory / "runtime/lib"
    native_runtime("cuda", config, directory, libraries)
    assert (libraries / "runtime.dll").read_bytes() == b"native"
    assert (directory / "licenses/vendor/vendor.dist-info/licenses/LICENSE").read_bytes() == b"license"
    assert not (tmp_path / "escaped.dll").exists()
    assert not list(directory.rglob("*.h"))
