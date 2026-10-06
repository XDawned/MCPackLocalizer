# [Module: core.patchouli.rendering] [Status: 已完成] [Brief: 帕秋莉文本回写与携带图标的独立资源包及 JAR 补丁]
"""Render complete books and separate resource-pack/JAR patch outputs."""
import io
import json
import zipfile
from collections import defaultdict
from pathlib import Path

from ...paths import RESOURCES
from ..formats.documents import Parser, encode_text, replace_strings, strings
from ..pack.extraction import digest
from .discovery import PACK_FOLDER, safe_member
from .text import TOOLTIP, validate_text


def render(document, entries):
    if document.resource.get("sparse_language"):
        if Path(document.path).suffix.lower() == ".lang":
            from ..pack.extraction import _lang_lines
            original = {p: s for p, s, _, _ in _lang_lines(document.text)}
        else:
            original = dict(strings(Parser(document.text, Path(document.path).suffix.lower()[1:]).parse()))
        values = document.resource.get("target_language", {}).copy()
        for entry in entries:
            if entry.patchouli.get("role") == "tooltip":
                continue
            string = original.get(tuple(entry.path))
            if not string or (string.start, string.end, string.value) != (entry.start, entry.end, entry.source):
                raise ValueError("帕秋莉语言快照与条目不一致")
            values[entry.path[0]] = compose(string.value, [e for e in entries if e.path == entry.path])
        if document.target.endswith(".lang"):
            if any("\n" in v or "\r" in v for v in values.values()):
                raise ValueError("旧版语言值不能包含换行符")
            return ("\n".join(k + "=" + v for k, v in values.items()) + "\n").encode("utf-8")
        return (json.dumps(values, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    original = dict(strings(Parser(document.text, "json").parse()))
    groups = defaultdict(list)
    for entry in entries:
        string = original.get(tuple(entry.path))
        if not string or (string.start, string.end) != (entry.start, entry.end):
            raise ValueError("帕秋莉快照范围/路径与条目不一致")
        if entry.patchouli.get("role") == "tooltip":
            matches = list(TOOLTIP.finditer(string.value))
            index = entry.patchouli["index"]
            if (not 0 <= index < len(matches) or matches[index][1] != entry.source
                    or entry.patchouli.get("parent_source") != string.value):
                raise ValueError("帕秋莉悬浮提示快照与条目不一致")
        elif string.value != entry.source:
            raise ValueError("帕秋莉快照文本与条目不一致")
        groups[tuple(entry.path)].append(entry)
    updates = [(original[path], compose(original[path].value, group)) for path, group in groups.items()]
    text = replace_strings(document.text, updates)
    Parser(text, "json").parse()
    return encode_text(text, document.encoding)


def compose(source, entries):
    primary = [e for e in entries if e.patchouli.get("role") != "tooltip"]
    if len(primary) > 1:
        raise ValueError("帕秋莉文本替换重复")
    text = primary[0].translation if primary else source
    if text is None:
        text = source
    validate_text(source, text, primary[0].patchouli.get("macros", ()) if primary else ())
    matches = list(TOOLTIP.finditer(text))
    for entry in sorted((e for e in entries if e.patchouli.get("role") == "tooltip"),
                        key=lambda e: e.patchouli["index"], reverse=True):
        originals = list(TOOLTIP.finditer(source))
        index = entry.patchouli["index"]
        if (not 0 <= index < len(originals) or originals[index][1] != entry.source
                or entry.patchouli.get("parent_source") != source):
            raise ValueError("帕秋莉悬浮提示快照与条目不一致")
        if entry.translation is None:
            continue
        if ")" in entry.translation:
            raise ValueError("帕秋莉悬浮提示不能包含结束格式标记的右括号")
        match = matches[entry.patchouli["index"]]
        text = text[:match.start(1)] + entry.translation + text[match.end(1):]
    return text


def rewrite_archive(raw, replacements):
    direct, nested = {}, defaultdict(dict)
    for chain, content in replacements.items():
        if not chain or not all(safe_member(member) for member in chain):
            raise ValueError("不安全的帕秋莉归档替换")
        if len(chain) == 1:
            direct[chain[0]] = content
        else:
            nested[chain[0]][chain[1:]] = content
    result = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as source, zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as target:
        names = source.namelist()
        if len(names) != len(set(names)):
            raise ValueError("归档中存在重复路径")
        for member, edits in nested.items():
            direct[member] = rewrite_archive(source.read(member), edits)
        for info in source.infolist():
            target.writestr(info, direct.pop(info.filename) if info.filename in direct else source.read(info))
        for name, content in sorted(direct.items()):
            target.writestr(name, content)
        target.comment = source.comment
    return result.getvalue()


def pack_metadata(scan):
    from ..mods.scan import select_game
    data = json.loads(Path(__file__).parents[1].joinpath("mods/data/i18n_metadata.json").read_bytes())
    try:
        game = select_game(data, scan.metadata.get("minecraft_version", "unknown"))
    except ValueError as exc:
        raise ValueError("帕秋莉资源包需要准确 MC 版本；请在识别选项填写版本后重新识别") from exc
    pack = {"description": "MCPackLocalizer 帕秋莉手册汉化"}
    if "packFormat" in game:
        pack["pack_format"] = game["packFormat"]
    else:
        pack.update(min_format=game["minFormat"], max_format=game["maxFormat"])
    return json.dumps({"pack": pack}, ensure_ascii=False, indent=2).encode("utf-8")


def prepare_outputs(scan, by_document):
    """Prepare all bytes before writing; several book edits share one outer JAR."""
    from ..pack.patch import safe_path
    prepared, archives = [], defaultdict(dict)
    archive_entries = defaultdict(int)
    needs_pack = False
    for document in scan.documents:
        if not document.kind.startswith("patchouli-"):
            continue
        entries = by_document.get(document.path, [])
        if not entries:
            continue
        raw = render(document, entries)
        resource = document.resource
        if resource["output_mode"] == "archive":
            chain = (*resource["members"][:-1], resource["target_member"])
            if chain in archives[resource["container"]]:
                raise ValueError("帕秋莉归档目标重复")
            archives[resource["container"]][chain] = raw
            archive_entries[resource["container"]] += len(entries)
        else:
            needs_pack |= resource["output_mode"] == "resourcepack"
            prepared.append((document.target, raw, {"path": document.target, "source": document.path,
                "source_sha256": document.source_hash, "sha256": digest(raw), "translated_entries": len(entries)}))
    for container, edits in archives.items():
        source = safe_path(Path(scan.root), container)
        original = source.read_bytes()
        raw = rewrite_archive(original, edits)
        prepared.append((container, raw, {"path": container, "kind": "patchouli-mod-archive",
            "source": container, "source_sha256": digest(original), "expected_target_sha256": digest(original),
            "sha256": digest(raw), "translated_entries": archive_entries[container]}))
    if needs_pack:
        raw = pack_metadata(scan)
        relative = PACK_FOLDER + "/pack.mcmeta"
        prepared.append((relative, raw, {"path": relative, "kind": "patchouli-resourcepack",
                                       "sha256": digest(raw), "translated_entries": 0}))
        raw = (RESOURCES / "pack.png").read_bytes()
        relative = PACK_FOLDER + "/pack.png"
        prepared.append((relative, raw, {"path": relative, "kind": "patchouli-resourcepack-icon",
                                       "sha256": digest(raw), "translated_entries": 0}))
    return prepared
