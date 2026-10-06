# [Module: core.mods.combined] [Status: 已完成] [Brief: 多范围任务合并与模组排除设置传递]
"""Embed the existing mod-language task in a multiple-scope pack task."""
from ..pack.extraction import Scan


def mod_scan(scan):
    if scan.metadata.get("task_kind") == "mod-languages":
        return scan
    metadata = scan.metadata.get("mod_resources")
    if metadata is None:
        return None
    if "model_config" in scan.metadata:
        metadata["model_config"] = scan.metadata["model_config"]
    metadata["manual_excluded_resources"] = scan.metadata.get("manual_excluded_resources", []).copy()
    return Scan(scan.root, scan.pack_id, scan.source_locale, scan.target_locale,
                [d for d in scan.documents if d.kind == "mod-lang"],
                [e for e in scan.entries if e.semantic_key.startswith("mod:")], scan.warnings, metadata)


def merge_mod_scan(scan, mods):
    """Keep shared mod identities instead of translating a lang reference twice."""
    references = {(e.document.split("/")[1], e.path[0], e.source): e for e in mods.entries}
    lang_documents = {d.path: d for d in scan.documents if d.kind == "patchouli-lang"}
    removed, delegated = set(), set()
    tooltip_paths = {(e.document, tuple(e.path)) for e in scan.entries if e.patchouli.get("role") == "tooltip"}
    for entry in scan.entries:
        if entry.document not in lang_documents or entry.patchouli.get("role") == "tooltip":
            continue
        identity = (lang_documents[entry.document].resource["logical"].split("/")[1], entry.path[0], entry.source)
        if identity not in references:
            continue
        if (entry.document, tuple(entry.path)) in tooltip_paths:
            # Keep these composite values in the book renderer, with no duplicate
            # key in the mod ZIP or incompatible shared-library record.
            delegated.add(references[identity].id)
        else:
            removed.add((entry.document, tuple(entry.path)))
            references[identity].patchouli = entry.patchouli.copy()
    scan.entries = [e for e in scan.entries if (e.document, tuple(e.path)) not in removed]
    used = {e.document for e in scan.entries}
    scan.documents = [d for d in scan.documents if d.path in used or d.resource.get("recognition_warnings")]
    scan.entries.extend(e for e in mods.entries if e.id not in delegated)
    scan.documents.extend(mods.documents)
    used = {e.document for e in scan.entries}
    scan.documents = [d for d in scan.documents if d.path in used or d.resource.get("recognition_warnings")]
    scan.warnings.extend(mods.warnings)
    scan.metadata["mod_resources"] = mods.metadata
    if scan.documents:
        scan.warnings = [w for w in scan.warnings if w != "No supported translation targets found"]
