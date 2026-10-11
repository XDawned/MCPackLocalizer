# [Module: scripts.update_cfpa_resources] [Status: 已完成] [Brief: 下载并校验 GitHub 社区汉化资源的内置离线快照]
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from mcpacklocalizer.core.mods.scan import (
    CFPA_RESOURCES,
    INDEX_URL,
    META_URL,
    RELEASE_ROOT,
    cfpa_snapshot_assets,
    fetch,
    json_bytes,
    release_folder,
    validate_cfpa,
    validate_cfpa_snapshot,
)
from mcpacklocalizer.core.pack.snapshots import atomic_write


def update_resources(destination: Path):
    metadata_data = fetch(META_URL, 2 * 1024 * 1024)
    index_data = fetch(INDEX_URL, 2 * 1024 * 1024)
    metadata, index = json.loads(metadata_data), json.loads(index_data)
    # 完成全部下载与校验后才更新副本，避免下载失败覆盖现有快照。
    files = {"i18nMetaData.json": (META_URL, metadata_data), "version-index.json": (INDEX_URL, index_data)}
    for tag, asset in cfpa_snapshot_assets(metadata, index):
        for name in (asset["filename"], asset["md5Filename"]):
            if Path(name).name != name:
                raise ValueError("元数据中的资源文件名无效")
        base = RELEASE_ROOT + quote(tag, safe="") + "/"
        md5_url, zip_url = base + quote(asset["md5Filename"]), base + quote(asset["filename"])
        print(f"下载离线快照：{tag} / {asset['filename']}", flush=True)
        md5_data = fetch(md5_url, 1024)
        data = fetch(zip_url)
        validate_cfpa(data, md5_data.decode("ascii").strip(), asset["filename"])
        folder = release_folder(Path(), tag)
        files[(folder / asset["filename"]).as_posix()] = (zip_url, data)
        files[(folder / asset["md5Filename"]).as_posix()] = (md5_url, md5_data)
    manifest = {"updated_at": datetime.now(UTC).isoformat(), "files": {
        name: {"url": url, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        for name, (url, data) in files.items()
    }}
    for name, (_url, data) in files.items():
        atomic_write(destination / name, data)
    atomic_write(destination / "manifest.json", json_bytes(manifest))
    validate_cfpa_snapshot(destination)
    print(f"已保存 {len(files)} 个离线文件：{destination}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="刷新内置 CFPA 离线资源，不依赖用户缓存")
    parser.add_argument("--output", type=Path, default=CFPA_RESOURCES, help="离线资源目录")
    update_resources(parser.parse_args().output)
