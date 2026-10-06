"""Desktop requests must retain CLI baseline and shared-library behavior."""
import json
from dataclasses import replace

import pytest

from mcpacklocalizer.application.config.settings import Settings
from mcpacklocalizer.application.tasks.jobs import Job
from mcpacklocalizer.application.tasks.requests import PackRequest, PatchOptions, pack_job
from mcpacklocalizer.application.tasks.service import execute
from mcpacklocalizer.application.tasks.store import load_task, result_summary
from mcpacklocalizer.core.mods.library import ModLibrary
from mcpacklocalizer.core.pack.snapshots import Store, load_snapshot
from tests.core.mods.test_mod_scan import mod_fixture


def language_source(root, values):
    path = root / "kubejs/assets/demo/lang/en_us.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(values), encoding="utf-8")
    return path


def test_upgrade_inherits_identity_and_latest_checkpoint_then_exports_new_sources(tmp_path):
    old_root, new_root = tmp_path / "pack-v1", tmp_path / "pack-v2"
    language_source(old_root, {"iron": "Iron Ingot", "gold": "Gold Ingot", "removed": "Removed"})
    language_source(new_root, {"iron": "Iron Ingot", "gold": "Gold Nugget", "added": "Added"})
    old_output, output = tmp_path / "old", tmp_path / "new"
    settings = Settings()
    execute(pack_job("extract", PackRequest(str(old_root), str(old_output)), settings, PatchOptions()))
    with Store(old_output) as store:
        # Simulate a paused run: committed translation newer than snapshot.json.
        for entry in store.load().entries:
            if entry.path[0] == "iron":
                store.update(replace(entry, translation="铁锭", status="reviewed", origin="manual"))
    assert load_snapshot(old_output / "snapshot.json").entries[0].translation is None
    request = PackRequest(str(new_root), str(output), baseline=str(old_output))
    result = execute(pack_job("extract", request, settings, PatchOptions()))
    scan = load_task(str(output))
    entries = {entry.path[0]: entry for entry in scan.entries}
    assert scan.pack_id == "pack-v1"
    assert entries["iron"].translation == "铁锭" and entries["iron"].origin == "manual"
    assert entries["gold"].translation is None and entries["added"].translation is None
    assert scan.metadata["delta"] == {"unchanged": 1, "changed": 1, "added": 1, "moved": 0,
                                      "reused": 1, "ambiguous": 0, "removed": 1}
    assert "上一版本复用 1" in result_summary(result)
    execute(Job("export", output=output, allow_partial=True))
    patch = json.loads((output / "patch/kubejs/assets/demo/lang/zh_cn.json").read_text(encoding="utf-8"))
    assert patch == {"iron": "铁锭", "gold": "Gold Nugget", "added": "Added"}
    with pytest.raises(ValueError, match="其他整合包"):
        execute(pack_job("diff", replace(request, pack_id="different"), settings, PatchOptions()))


def test_explicit_snapshot_is_supported_and_relaxed_reuse_can_export_before_translation(tmp_path):
    old_root, new_root = tmp_path / "old-game", tmp_path / "new-game"
    for root in (old_root, new_root):
        language_source(root, {"grapes": "&bGrapes&r"})
    old_output = tmp_path / "old-task"
    execute(Job("extract", root=old_root, output=old_output))
    with Store(old_output) as store:
        store.update(replace(store.load().entries[0], translation="葡萄", origin="manual", status="reviewed"))
        store.export()
    request = PackRequest(str(new_root), str(tmp_path / "new-task"), baseline=str(old_output / "snapshot.json"))
    strict = execute(pack_job("diff", request, Settings(), PatchOptions()))
    assert strict["metadata"]["delta"]["reused"] == 0
    execute(pack_job("extract", request, Settings(allow_missing_placeholders=True), PatchOptions()))
    assert load_task(request.output).entries[0].translation == "葡萄"
    execute(Job("export", output=request.output))


@pytest.mark.parametrize("scopes", [["mods"], ["kubejs", "mods"]])
@pytest.mark.parametrize("policy,reused", [("reviewed", 0), ("all", 1), ("off", 0)])
def test_desktop_shared_drafts_across_pack_version_and_loader(tmp_path, scopes, policy, reused):
    root, sources = mod_fixture(tmp_path, name="new-pack", version="2.0", english={"iron": "Iron %s"})
    library_path = tmp_path / "shared.sqlite3"
    with ModLibrary(library_path) as library:
        library.add({"provider_ids": ["example"], "namespace": "example", "key": "iron",
                     "source": "Iron %s", "translation": "铁 %s", "source_locale": "en_us",
                     "target_locale": "zh_cn"}, "draft", {"pack_id": "old-pack", "minecraft_version": "1.20.1"})
    request = PackRequest(str(root), str(tmp_path / "task"), offline=True, cfpa_pack=str(sources[0][0]),
                          game_version="1.21.1", loader="neoforge", mods=scopes == ["mods"],
                          recognition_scope=scopes, translation_library=str(library_path), reuse_policy=policy)
    job = pack_job("extract", request, Settings(), PatchOptions())
    job.cache = tmp_path / "cache"
    result = execute(job)
    scan = load_task(request.output)
    assert sum(entry.translation is not None for entry in scan.entries) == reused
    assert scan.pack_id == "new-pack"
    metadata = scan.metadata.get("mod_resources", scan.metadata)
    assert metadata["mod_library"]["policy"] == policy
    assert metadata["mod_library"]["path"] == str(library_path.resolve())
    assert f"共享译库复用 {reused}" in result_summary(result)
    if policy == "reviewed":
        assert "仅有草稿 1" in result_summary(result)
    if reused:
        execute(Job("export", output=request.output))
