# [Module: scripts.publish_release] [Status: 已完成] [Brief: 人工确认后发布同一次成功构建的原始产物]
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


def api(path: str):
    base = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    request = urllib.request.Request(f"{base}/repos/{os.environ['GITHUB_REPOSITORY']}/{path}", headers={
        "Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "MCPackLocalizer-release",
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def checked_run(run_id: str):
    if not re.fullmatch(r"[1-9]\d*", run_id):
        raise ValueError("构建 Run ID 必须为正整数")
    if os.environ.get("TESTED") != "true":
        raise ValueError("必须先确认 CPU、Vulkan、CUDA 包均已完成人工测试")
    repo = api("")
    run = api(f"actions/runs/{run_id}")
    workflow = api("actions/workflows/build-release.yml")
    if (run["workflow_id"] != workflow["id"] or run["conclusion"] != "success" or
            run["status"] != "completed" or run["event"] not in {"push", "workflow_dispatch"} or
            run["head_repository"]["id"] != repo["id"] or run["head_branch"] != repo["default_branch"]):
        raise ValueError("只能发布本仓库默认分支上成功完成的 build-release.yml 构建")
    artifacts = api(f"actions/runs/{run_id}/artifacts?per_page=100")["artifacts"]
    expected = {"release-cpu", "release-vulkan", "release-cuda"}
    selected = [a for a in artifacts if a["name"] in expected]
    if len(selected) != 3 or {a["name"] for a in selected} != expected or any(a["expired"] for a in selected):
        raise ValueError("构建必须包含三个未过期的后端产物")
    return run


def digest(path: Path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def validate_assets(directory: Path, run: dict, tag: str):
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?", tag):
        raise ValueError("标签必须采用 v2.0.0 或 v2.0.0rc1 等格式")
    assets, manifests = [], []
    for backend in ("cpu", "vulkan", "cuda"):
        stem = f"MCPackLocalizer-{tag[1:]}-win-x64-{backend}"
        paths = [directory / f"{stem}{suffix}" for suffix in (".zip", ".sha256", ".json")]
        if not all(p.is_file() for p in paths):
            raise ValueError(f"缺少 {backend} 发布文件，版本标签必须匹配构建版本")
        archive, checksum, manifest_path = paths
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (manifest["version"] != tag[1:] or manifest["backend"] != backend or
                manifest["commit"] != run["head_sha"] or str(manifest["run_id"]) != str(run["id"]) or
                str(manifest["run_attempt"]) != str(run["run_attempt"])):
            raise ValueError("产物提交、版本或构建批次不一致；请重新运行完整构建")
        expected = f"{digest(archive)}  {archive.name}"
        if checksum.read_text(encoding="ascii").strip() != expected:
            raise ValueError(f"发布包校验失败：{archive.name}")
        assets.extend(paths)
        manifests.append(manifest)
    if {p.name for p in directory.iterdir()} != {p.name for p in assets}:
        raise ValueError("下载目录包含额外文件，请检查构建产物")
    return assets, manifests


def tag_commit(tag: str) -> str | None:
    try:
        obj = api(f"git/ref/tags/{tag}")["object"]
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    for _ in range(8):
        if obj["type"] == "commit":
            return obj["sha"]
        if obj["type"] != "tag":
            break
        obj = api(f"git/tags/{obj['sha']}")["object"]
    raise ValueError("发布标签未指向有效提交")


def publish(directory: Path, run: dict, tag: str, prerelease: bool):
    assets, manifests = validate_assets(directory, run, tag)
    if re.search(r"(?:a|b|rc)\d+$", tag) and not prerelease:
        raise ValueError("预览版本标签必须选择 prerelease")
    notes = os.environ.get("TEST_NOTES", "").strip()
    if not notes:
        raise ValueError("请记录人工测试设备与结果")
    existing_commit = tag_commit(tag)
    if existing_commit is not None and existing_commit != run["head_sha"]:
        raise ValueError("已有标签指向其它提交，不能覆盖")
    try:
        release = api(f"releases/tags/{tag}")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        release = None
    if release is not None and not release["draft"]:
        raise ValueError("该版本已经发布，不能替换已公开的资产")
    body = (f"构建提交：`{run['head_sha']}`\n\n"
            f"测试与发布使用相同产物：[构建记录]({run['html_url']})。\n\n"
            "解压完整目录后运行 `MCPackLocalizer.exe`，无需安装 Python。GGUF 模型需单独准备。\n\n" +
            "\n".join(f"- **{m['backend']}**：{m['requirements']}" for m in manifests) +
            f"\n\n人工测试记录：\n\n{notes}\n\n资产包含 ZIP、SHA256 与构建清单。")
    repo = os.environ["GITHUB_REPOSITORY"]
    with tempfile.TemporaryDirectory() as temporary:
        body_file = Path(temporary) / "release.md"
        body_file.write_text(body, encoding="utf-8")
        if release is None:
            subprocess.run(["gh", "release", "create", tag, "--repo", repo, "--target", run["head_sha"],
                            "--title", f"MCPackLocalizer {tag}", "--notes-file", str(body_file), "--draft"], check=True)
        else:
            subprocess.run(["gh", "release", "edit", tag, "--repo", repo, "--target", run["head_sha"],
                            "--title", f"MCPackLocalizer {tag}", "--notes-file", str(body_file)], check=True)
        # 上传失败保留草稿；只有尚未公开的草稿允许重试上传。
        subprocess.run(["gh", "release", "upload", tag, "--repo", repo, "--clobber", *map(str, assets)], check=True)
        subprocess.run(["gh", "release", "edit", tag, "--repo", repo, "--draft=false",
                        f"--prerelease={str(prerelease).lower()}"], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="发布已人工验证的构建产物")
    parser.add_argument("stage", choices=["check", "publish"])
    parser.add_argument("--directory", type=Path, default=Path("artifacts"))
    args = parser.parse_args()
    source_run = checked_run(os.environ.get("SOURCE_RUN_ID", ""))
    if args.stage == "publish":
        publish(args.directory, source_run, os.environ.get("RELEASE_TAG", ""), os.getenv("PRERELEASE") == "true")
    else:
        print(f"已确认构建：{source_run['html_url']}，提交：{source_run['head_sha']}")
