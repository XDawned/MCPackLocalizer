# [Module: tests.models] [Status: 已完成] [Brief: 模型下载协议、断点续传及失败时的文件保护]
import hashlib
import json
from dataclasses import replace

import httpx
import pytest

from mcpacklocalizer.application.tasks import models
from mcpacklocalizer.application.tasks.jobs import Job
from mcpacklocalizer.application.tasks.worker import perform


@pytest.fixture(params=["7b", "1.8b"])
def model_download(tmp_path, monkeypatch, request):
    variant = request.param
    content = b"GGUF" + (variant + "-model-data").encode() * 2
    spec = replace(models.model_spec(variant), size=len(content), sha256=hashlib.sha256(content).hexdigest())
    monkeypatch.setitem(models.MODEL_VARIANTS, variant, spec)
    monkeypatch.setattr(models, "CHUNK_SIZE", 4)
    target = tmp_path / "models/test.gguf"
    return target, content, variant


def network(monkeypatch, handler):
    client_type = httpx.Client
    monkeypatch.setattr(models.httpx, "Client", lambda **kwargs: client_type(
        transport=httpx.MockTransport(handler), **kwargs))


def partial_path(target, data):
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    partial.write_bytes(data)
    return partial


def test_download_worker_validates_before_publishing_and_emits_progress(model_download, monkeypatch, capsys):
    target, content, variant = model_download
    network(monkeypatch, lambda request: httpx.Response(200, content=content))
    job = Job.from_payload(Job("download-model", output=target, download_variant=variant).payload())
    assert perform(job) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["model"] == str(target) and result["sha256"] == models.model_spec(variant).sha256
    assert result["download_variant"] == variant
    assert target.read_bytes() == content
    assert not target.with_name(target.name + ".part").exists()
    progress = [json.loads(line) for line in captured.err.splitlines()]
    assert all({"completed", "failed", "remaining"} <= p.keys() for p in progress)
    assert progress[-1]["completed"] == len(content) and progress[-1]["remaining"] == 0
    assert all(p["download_variant"] == variant for p in progress)


@pytest.mark.parametrize("supports_range", [True, False])
def test_resume_handles_range_and_servers_that_restart_download(model_download, monkeypatch, supports_range):
    target, content, variant = model_download
    partial_path(target, content[:8])

    def handler(request):
        assert request.headers["Range"] == "bytes=8-"
        assert request.headers["Accept-Encoding"] == "identity"
        if supports_range:
            return httpx.Response(206, content=content[8:], headers={
                "Content-Range": f"bytes 8-{len(content) - 1}/{len(content)}"})
        return httpx.Response(200, content=content)

    network(monkeypatch, handler)
    models.download_model(target, variant)
    assert target.read_bytes() == content


def test_completed_partial_is_verified_without_network(model_download, monkeypatch):
    target, content, variant = model_download
    partial_path(target, content)
    network(monkeypatch, lambda request: pytest.fail("完整的临时模型不应再次下载"))
    models.download_model(target, variant)
    assert target.read_bytes() == content


def test_connection_interruption_resumes_from_mirror(model_download, monkeypatch):
    target, content, variant = model_download
    requests = []

    class Interrupted(httpx.SyncByteStream):
        def __iter__(self):
            yield content[:8]
            raise httpx.ReadError("连接中断")

    def handler(request):
        requests.append(request)
        if request.url.host == "huggingface.co":
            return httpx.Response(200, stream=Interrupted())
        assert request.headers["Range"] == "bytes=8-"
        return httpx.Response(206, content=content[8:], headers={
            "Content-Range": f"bytes 8-{len(content) - 1}/{len(content)}"})

    network(monkeypatch, handler)
    models.download_model(target, variant)
    assert target.read_bytes() == content and len(requests) == 2


def test_network_failure_keeps_partial_and_returns_worker_error(model_download, monkeypatch, capsys):
    target, content, variant = model_download
    partial = partial_path(target, content[:8])

    def handler(request):
        raise httpx.ConnectError("连接失败", request=request)

    network(monkeypatch, handler)
    assert perform(Job("download-model", output=target, download_variant=variant)) == 2
    assert "模型下载失败" in json.loads(capsys.readouterr().out)["error"]
    assert partial.read_bytes() == content[:8] and not target.exists()


def test_wrong_range_never_appends_to_partial(model_download, monkeypatch):
    target, content, variant = model_download
    partial = partial_path(target, content[:8])
    network(monkeypatch, lambda request: httpx.Response(206, content=content, headers={
        "Content-Range": f"bytes 0-{len(content) - 1}/{len(content)}"}))
    with pytest.raises(ValueError, match="断点范围"):
        models.download_model(target, variant)
    assert partial.read_bytes() == content[:8] and not target.exists()


def test_corrupt_download_is_removed_and_never_published(model_download, monkeypatch):
    target, content, variant = model_download
    network(monkeypatch, lambda request: httpx.Response(200, content=b"x" * len(content)))
    with pytest.raises(ValueError, match="SHA256"):
        models.download_model(target, variant)
    assert not target.exists() and not target.with_name(target.name + ".part").exists()


def test_truncated_download_remains_resumable(model_download, monkeypatch):
    target, content, variant = model_download

    class Truncated(httpx.SyncByteStream):
        def __iter__(self):
            yield content[:8]

    network(monkeypatch, lambda request: httpx.Response(200, stream=Truncated()))
    with pytest.raises(ValueError, match="未下载完整"):
        models.download_model(target, variant)
    assert target.with_name(target.name + ".part").read_bytes() == content[:8]
    assert not target.exists()


def test_existing_model_is_never_overwritten(model_download, monkeypatch):
    target, _, variant = model_download
    target.parent.mkdir(parents=True)
    target.write_bytes(b"user-model")
    network(monkeypatch, lambda request: pytest.fail("已有模型不应再次下载"))
    with pytest.raises(ValueError, match="不会覆盖"):
        models.download_model(target, variant)
    assert target.read_bytes() == b"user-model"


def test_download_job_requires_destination():
    with pytest.raises(ValueError, match="output"):
        Job("download-model")


def test_unknown_variant_is_rejected_before_download(mocker, tmp_path):
    client = mocker.patch.object(models.httpx, "Client")
    with pytest.raises(ValueError, match="7B 或 1.8B"):
        Job("download-model", output=tmp_path / "model.gguf", download_variant="invalid")
    client.assert_not_called()


def test_switching_variants_keeps_independent_partials_and_checksums(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "MODEL_HOME", tmp_path)
    contents = {"7b": b"GGUF-large-test-model", "1.8b": b"GGUF-small-test-model"}
    for variant, content in contents.items():
        monkeypatch.setitem(models.MODEL_VARIANTS, variant, replace(
            models.model_spec(variant), size=len(content), sha256=hashlib.sha256(content).hexdigest()))
    large, small = models.model_spec("7b").path, models.model_spec("1.8b").path
    partial = partial_path(large, contents["7b"][:8])

    def handler(request):
        if "1.8B" in request.url.path:
            assert "Range" not in request.headers
            return httpx.Response(200, content=contents["1.8b"])
        assert request.headers["Range"] == "bytes=8-"
        content = contents["7b"]
        return httpx.Response(206, content=content[8:], headers={
            "Content-Range": f"bytes 8-{len(content) - 1}/{len(content)}"})

    network(monkeypatch, handler)
    models.download_model(small, "1.8b")
    assert partial.read_bytes() == contents["7b"][:8]
    assert small.read_bytes() == contents["1.8b"] and not large.exists()
    models.download_model(large, "7b")
    assert large.read_bytes() == contents["7b"]


@pytest.mark.parametrize("variant", ["7b", "1.8b"])
def test_default_download_stays_in_program_directory_when_worker_changes_cwd(tmp_path, monkeypatch, variant):
    program = tmp_path / "程序目录 with spaces"
    worker_directory = tmp_path / "后台工作目录"
    worker_directory.mkdir()
    monkeypatch.chdir(worker_directory)
    monkeypatch.setattr(models, "MODEL_HOME", program)
    spec = models.model_spec(variant)
    assert spec.path == program / "models" / spec.repository / spec.filename
    assert not spec.path.is_relative_to(worker_directory)


def test_default_download_matches_local_inference_model_path(monkeypatch):
    from mcpacklocalizer.application.config.settings import Settings

    monkeypatch.delenv("MPLT_MODEL_PATH", raising=False)
    assert str(models.model_spec("7b").path) == Settings.defaults().model
