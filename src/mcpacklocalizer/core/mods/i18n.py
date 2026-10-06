# [Module: mcpacklocalizer.core.mods.i18n] [Status: 开发中] [Brief: 按发布兼容元数据校验并附带可选 I18nUpdateMod]
from __future__ import annotations

import hashlib
from pathlib import Path

from ..pack.patch import safe_path
from ..pack.snapshots import atomic_write

PROJECT_SLUG = "i18nupdatemod"


def select_release(releases, game_version, loader):
    matches = [r for r in releases if r.get("version_type") == "release"
               and game_version in r.get("game_versions", []) and loader in r.get("loaders", [])]
    for release in sorted(matches, key=lambda r: r.get("date_published", ""), reverse=True):
        files = [f for f in release.get("files", []) if f.get("filename", "").lower().endswith(".jar")]
        files.sort(key=lambda f: not f.get("primary", False))
        for file in files:
            hashes = file.get("hashes", {})
            if hashes.get("sha512") or hashes.get("sha1"):
                return release, file
    raise ValueError("未找到校验通过的兼容版本；补丁可在不含 I18nUpdateMod 的情况下导出")


def attach_i18n(output: Path, game_version: str, loader: str, offline=False):
    import httpx
    if not game_version or loader not in {"fabric", "forge", "neoforge", "quilt"}:
        raise ValueError("I18nUpdateMod 需要明确的 --game-version 和 --loader")
    if offline:
        raise ValueError("离线模式不会下载 I18nUpdateMod；请改用 --i18n-jar 提供")
    headers = {"User-Agent": "MCPackLocalizer/0.1 (localization tool)"}
    with httpx.Client(timeout=30, follow_redirects=True, headers=headers) as client:
        response = client.get(f"https://api.modrinth.com/v2/project/{PROJECT_SLUG}/version")
        response.raise_for_status()
        release, file = select_release(response.json(), game_version, loader)
        url = file.get("url", "")
        if not url.startswith("https://cdn.modrinth.com/"):
            raise ValueError("模组下载主机不符合预期")
        response = client.get(url, timeout=120)
        response.raise_for_status()
        data = response.content
    algorithm = "sha512" if file["hashes"].get("sha512") else "sha1"
    if hashlib.new(algorithm, data).hexdigest() != file["hashes"][algorithm]:
        raise ValueError("下载的 I18nUpdateMod 校验和不匹配")
    if file.get("size") is not None and len(data) != file["size"]:
        raise ValueError("下载的 I18nUpdateMod 大小不匹配")
    target = safe_path(output / "patch" / "mods", file["filename"])
    if Path(file["filename"]).name != file["filename"]:
        raise ValueError("模组文件名无效")
    atomic_write(target, data)
    return {"status": "downloaded", "path": "mods/" + file["filename"], "version_id": release["id"],
            "sha256": hashlib.sha256(data).hexdigest(), "game_version": game_version, "loader": loader,
            "note": "Community language resources may require a download when Minecraft starts"}


def attach_local(output: Path, jar: Path):
    import io
    import zipfile
    data = jar.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        if not any("i18nupdate" in name.lower() for name in names):
            raise ValueError("JAR 中似乎不包含 I18nUpdateMod")
    filename = jar.name
    if jar.suffix.lower() != ".jar":
        raise ValueError("需要 .jar 文件")
    atomic_write(safe_path(output / "patch" / "mods", filename), data)
    return {"status": "provided_local", "path": "mods/" + filename, "sha256": hashlib.sha256(data).hexdigest(),
            "note": "User-provided JAR: compatibility must be checked by the user"}
