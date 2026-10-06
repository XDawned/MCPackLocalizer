# [Module: tests.i18n] [Status: 开发中] [Brief: 兼容发布选择、离线禁网和下载哈希校验]
import hashlib
from pathlib import Path

import pytest

from mcpacklocalizer.core.mods.i18n import attach_i18n, select_release


def releases(data=b"jar"):
    return [{"id": "release", "version_type": "release", "date_published": "2026-01-01",
        "game_versions": ["1.19.2", "1.21.1"], "loaders": ["fabric", "neoforge"],
        "files": [{"filename": "I18nUpdateMod.jar", "url": "https://cdn.modrinth.com/file.jar", "primary": True,
                   "size": len(data), "hashes": {"sha512": hashlib.sha512(data).hexdigest()}}]}]


def test_universal_release_uses_compatibility_metadata():
    assert select_release(releases(), "1.19.2", "fabric")[0]["id"] == "release"
    with pytest.raises(ValueError):
        select_release(releases(), "1.12.2", "forge")


def test_offline_never_opens_network(mocker):
    client = mocker.patch("httpx.Client")
    with pytest.raises(ValueError, match="离线模式"):
        attach_i18n(Path("C:/mcpl-tests/output"), "1.19.2", "fabric", offline=True)
    client.assert_not_called()


def test_bad_download_hash_never_written(mocker):
    client = mocker.patch("httpx.Client").return_value.__enter__.return_value
    metadata = mocker.Mock()
    metadata.json.return_value = releases()
    download = mocker.Mock(content=b"bad")
    client.get.side_effect = [metadata, download]
    write = mocker.patch("mcpacklocalizer.core.mods.i18n.atomic_write")
    with pytest.raises(ValueError, match="校验和"):
        attach_i18n(Path("C:/mcpl-tests/output"), "1.19.2", "fabric")
    write.assert_not_called()
