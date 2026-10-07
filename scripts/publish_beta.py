# [Module: scripts.publish_beta] [Status: 已完成] [Brief: 校验同次三后端产物后更新固定 Beta 预发布入口]
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
from pathlib import Path
from urllib.parse import quote

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_release import project_version
from scripts.publish_release import api, tag_commit, validate_assets


def release_for(tag: str):
    try:
        return api(f"releases/tags/{tag}")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        return None


def commit_history(ref: str):
    page = 1
    while True:
        commits = api(f"commits?sha={quote(ref, safe='')}&per_page=100&page={page}")
        yield from commits
        if len(commits) < 100:
            return
        page += 1


def beta_notes(commit: str) -> str:
    """使用 GitHub 生成 PR 记录，并补充仅直接提交的版本与首次贡献者。"""
    repo = os.environ["GITHUB_REPOSITORY"]
    base_url = f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/{repo}"
    try:
        previous = api("releases/latest")["tag_name"]
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        previous = None
    # 用构建提交作为目标，避免尚未移动的 Beta 标签让生成结果落后一个构建。
    payload = {"tag_name": commit, "target_commitish": commit}
    if previous:
        payload["previous_tag_name"] = previous
    body = api("releases/generate-notes", payload)["body"].strip()
    if previous:
        comparison = f"compare/{quote(previous, safe='')}...{commit}"
        first = api(f"{comparison}?per_page=100&page=1")
        commits = first["commits"]
        for page in range(2, (first["total_commits"] + 99) // 100 + 1):
            commits.extend(api(f"{comparison}?per_page=100&page={page}")["commits"])
    else:
        commits = list(reversed(list(commit_history(commit))))
    if "## What's Changed" not in body:
        changes = []
        for item in commits:
            title = item["commit"]["message"].splitlines()[0]
            login = (item.get("author") or {}).get("login")
            author = f" by @{login}" if login else ""
            changes.append(f"* {title}{author} in [{item['sha'][:7]}]({base_url}/commit/{item['sha']})")
        body = "## What's Changed\n" + ("\n".join(changes) or "* 本次没有新增提交。") + "\n\n" + body
    if "## New Contributors" not in body:
        authors = {}
        for item in commits:
            login = (item.get("author") or {}).get("login")
            if login:
                authors.setdefault(login, item["sha"])
        new = set(authors)
        if previous:
            for item in commit_history(previous):
                new.discard((item.get("author") or {}).get("login"))
                if not new:
                    break
        contributors = [f"* @{login} made their first contribution in {base_url}/commit/{sha}"
                        for login, sha in authors.items() if login in new]
        section = "## New Contributors\n" + ("\n".join(contributors) or "* 本次暂无新贡献者。") + "\n\n"
        marker = "**Full Changelog**:"
        if marker in body:
            body = body.replace(marker, section + marker, 1)
        else:
            body += "\n\n" + section
    # 固定页面使用 Beta 比较链接，临时草稿标签不出现在公开说明中。
    if previous:
        body = body.replace(f"{base_url}/compare/{previous}...{commit}",
                            f"{base_url}/compare/{previous}...Beta")
    if "**Full Changelog**:" not in body:
        target = f"compare/{quote(previous, safe='')}...Beta" if previous else "commits/Beta"
        body += f"\n\n**Full Changelog**: {base_url}/{target}"
    return "MCPackLocalizer Beta 开发测试版本，由最新源码自动打包。\n\n" + body.strip() + "\n"


def publish_beta(directory: Path):
    repo = os.environ["GITHUB_REPOSITORY"]
    commit = os.environ["GITHUB_SHA"]
    run_id, attempt = os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_RUN_ATTEMPT"]
    if (os.environ.get("GITHUB_REF") != "refs/heads/v2.0.0" or
            os.environ.get("GITHUB_EVENT_NAME") not in {"push", "workflow_dispatch"} or
            not re.fullmatch(r"[0-9a-f]{40}", commit) or
            not all(re.fullmatch(r"[1-9]\d*", value) for value in (run_id, attempt))):
        raise ValueError("Beta 只能来自 v2.0.0 分支上的构建运行")
    run_url = f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/{repo}/actions/runs/{run_id}"
    run = {"head_sha": commit, "id": run_id, "run_attempt": attempt, "html_url": run_url}
    version = project_version()
    assets, _ = validate_assets(directory, run, f"v{version}")
    if api("git/ref/heads/v2.0.0")["object"]["sha"] != commit:
        print("分支已有较新提交，跳过旧构建的 Beta 发布", flush=True)
        return
    beta = release_for("Beta")
    beta_commit = tag_commit("Beta")
    if beta and not beta["prerelease"]:
        raise ValueError("Beta 已被用于正式版本，拒绝替换")
    if beta is None and beta_commit is not None:
        raise ValueError("Beta 标签已有其它用途，拒绝移动")
    staging = f"beta-build-{run_id}-{attempt}"
    draft = release_for(staging)
    if draft and not draft["draft"]:
        raise ValueError("临时构建版本已公开，拒绝覆盖")
    staged_commit = tag_commit(staging)
    if staged_commit is not None and staged_commit != commit:
        raise ValueError("临时构建标签指向其它提交，拒绝覆盖")
    body = beta_notes(commit)
    with tempfile.TemporaryDirectory() as temporary:
        notes = Path(temporary) / "beta.md"
        notes.write_text(body, encoding="utf-8")

        def gh(*args):
            subprocess.run(["gh", *args, "--repo", repo], check=True)

        gh("release", "edit" if draft else "create", staging, "--target", commit,
           "--title", "MCPackLocalizer Beta 开发测试版", "--notes-file", str(notes), "--draft", "--prerelease")
        # 新包全部上传成功后才替换旧 Beta，上传失败保留原来的下载入口与本次草稿。
        gh("release", "upload", staging, "--clobber", *map(str, assets))
        current = release_for("Beta")
        if (any((current or {}).get(key) != (beta or {}).get(key)
                for key in ("id", "draft", "prerelease", "tag_name", "updated_at")) or
                tag_commit("Beta") != beta_commit):
            raise ValueError("上传期间 Beta 已被其它操作修改，请检查后重试")
        if api("git/ref/heads/v2.0.0")["object"]["sha"] != commit:
            print("上传期间分支已有较新提交，保留草稿并跳过 Beta 更新", flush=True)
            return
        if beta:
            gh("release", "delete", "Beta", "--yes")
        if beta_commit is None:
            subprocess.run(["gh", "api", "--method", "POST", f"repos/{repo}/git/refs",
                            "-f", "ref=refs/tags/Beta", "-f", f"sha={commit}"], check=True)
        else:
            subprocess.run(["gh", "api", "--method", "PATCH", f"repos/{repo}/git/refs/tags/Beta",
                            "-f", f"sha={commit}", "-F", "force=true"], check=True)
        gh("release", "edit", staging, "--tag", "Beta", "--target", commit,
           "--draft=false", "--prerelease", "--latest=false")
    print(f"Beta 测试版已更新：https://github.com/{repo}/releases/tag/Beta", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="发布本次构建的 Beta 测试包")
    parser.add_argument("--directory", type=Path, default=Path("artifacts"))
    publish_beta(parser.parse_args().directory)
