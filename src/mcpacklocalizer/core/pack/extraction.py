# [Module: mcpacklocalizer.core.pack.extraction] [Status: 开发中] [Brief: 新旧 FTBQ 与整合包语言文件扫描和稳定条目定位]
from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..formats.binary_nbt import parse_nbt
from ..formats.documents import Atom, Parser, String, strings

TEXT_FIELDS = {"title", "subtitle", "description", "text", "chapter_subtitle", "quest_subtitle", "quest_desc",
               "lock_message", "tooltip", "hover"}
OBJECT_COLLECTIONS = {"quests", "tasks", "rewards", "chapters", "chapter_groups", "images", "reward_tables"}
SUPPORTED = {".snbt", ".json5", ".json", ".lang"}
LOCALE = re.compile(r"^[a-z]{2,3}_[a-z]{2,4}$", re.IGNORECASE)


def digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def locale_name(value: str) -> str:
    if not LOCALE.fullmatch(value):
        raise ValueError("语言代码必须是安全的 language_region 名称，例如 en_us 或 zh_cn")
    return value.lower()


@dataclass
class Entry:
    id: str
    semantic_key: str
    document: str
    path: list
    source: str
    start: int
    end: int
    context: str
    translation: str | None = None
    status: str = "pending"
    origin: str = ""
    error: str = ""
    script: dict = field(default_factory=dict)
    patchouli: dict = field(default_factory=dict)


@dataclass
class Document:
    path: str
    target: str
    kind: str
    text: str
    source_hash: str
    encoding: str = "utf-8"
    resource: dict = field(default_factory=dict)


@dataclass
class Scan:
    root: str
    pack_id: str
    source_locale: str
    target_locale: str
    documents: list[Document] = field(default_factory=list)
    entries: list[Entry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def summary(self):
        counts = {}
        for document in self.documents:
            counts[document.kind] = counts.get(document.kind, 0) + 1
        return {"root": self.root, "pack_id": self.pack_id, "source_locale": self.source_locale,
                "target_locale": self.target_locale, "files": len(self.documents), "entries": len(self.entries),
                "formats": counts, "metadata": self.metadata, "warnings": self.warnings}

    def to_dict(self):
        version = 3 if any(d.resource for d in self.documents) or any(e.patchouli for e in self.entries) else (
            2 if any(e.script for e in self.entries) else 1)
        return {**asdict(self), "schema_version": version}

    @classmethod
    def from_dict(cls, data):
        if data.get("schema_version", 1) not in {1, 2, 3}:
            raise ValueError("不支持的快照数据版本")
        return cls(data["root"], data["pack_id"], locale_name(data["source_locale"]),
                   locale_name(data["target_locale"]), [Document(**d) for d in data["documents"]],
                   [Entry(**e) for e in data["entries"]], data.get("warnings", []), data.get("metadata", {}))


def pack_resource_exclusion(scan: Scan, document: Document):
    """Prefer pack-authored locales and never translate locale descriptor overrides."""
    if document.kind != "pack-lang":
        return None
    root = Path(scan.root).resolve()
    source = root / document.path
    if not source.resolve().is_relative_to(root):
        raise ValueError("资源源文件超出所选整合包范围")
    for candidate in sorted(source.parent.glob("*")):
        if (candidate.is_file() and candidate.stem.casefold() == scan.target_locale.casefold()
                and candidate.suffix.lower() in {".json", ".json5", ".lang"}):
            return {"source": document.path, "target": candidate.relative_to(root).as_posix(),
                    "reason": "existing-target-locale"}
    if "language.code" in document.text:
        if source.suffix.lower() == ".lang":
            node = {path[0]: value for path, value, _, _ in _lang_lines(document.text)}
        else:
            node = Parser(document.text, source.suffix.lower()[1:]).parse()
        if isinstance(node, dict) and "language.code" in node and ("language.name" in node or "language.region" in node):
            return {"source": document.path, "target": document.target, "reason": "locale-descriptor"}
    return None


def resource_exclusions(scan: Scan) -> set[str]:
    # Recheck old snapshots on resume/export; keep scan-time records whose sources
    # were never added as documents. Excluded translations remain in the checkpoint.
    documents = {d.path for d in scan.documents}
    records = {r["source"]: r for r in scan.metadata.get("excluded_resources", []) if r["source"] not in documents}
    from ..patchouli.diagnostics import unresolved_key_documents
    blocked_keys = unresolved_key_documents(scan)
    manual = set(scan.metadata.get("manual_excluded_resources", []))
    for document in scan.documents:
        record = pack_resource_exclusion(scan, document)
        if document.path in blocked_keys:
            record = {"source": document.path, "target": document.target, "reason": "unresolved-language-key"}
        elif document.path in manual:
            record = {"source": document.path, "target": document.target, "reason": "manual"}
        if record:
            records[document.path] = record
    if records or "excluded_resources" in scan.metadata:
        scan.metadata["excluded_resources"] = [records[key] for key in sorted(records)]
    return set(records)


def read_text(path: Path):
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            text = raw.decode(encoding)
            if encoding == "utf-8-sig":
                original_encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
            else:
                original_encoding = ("utf-16-be" if raw.startswith(b"\xfe\xff") else
                                     "utf-16" if raw.startswith(b"\xff\xfe") else "utf-16-le")
            return text, original_encoding, digest(raw)
        except UnicodeError:
            pass
    raise ValueError("不支持该文件编码（应为 UTF-8 或 UTF-16）")


def legacy_strings(node, path=(), owner="file", owner_title=""):
    """Visit quest objects, not arbitrary nested item NBT, commands or configuration."""
    if not isinstance(node, dict):
        return
    identity = node.get("id", node.get("uid"))
    if isinstance(identity, (String, Atom)):
        owner = identity.value if isinstance(identity, String) else identity.raw
    title = node.get("title")
    if isinstance(title, String):
        owner_title = title.value
    for key, value in node.items():
        if key in TEXT_FIELDS:
            for suffix, string in strings(value):
                # Components/objects are not raw text: defer rather than translate their tags.
                if any(isinstance(part, str) for part in suffix):
                    continue
                semantic = f"{owner}/{key}/" + "/".join(map(str, suffix))
                context = f"{owner}/{key}|title={owner_title}"
                yield path + (key,) + suffix, string, semantic, context
        elif key in OBJECT_COLLECTIONS and isinstance(value, list):
            for index, child in enumerate(value):
                yield from legacy_strings(child, path + (key, index), f"{owner}/{key}/{index}", owner_title)


def betterquesting_strings(node):
    """Only BQ's own display properties, never addon commands or nested item NBT."""
    def lookup(obj, key, tag):
        if not isinstance(obj, dict):
            return None, None
        for candidate in (f"{key}:{tag}", key):
            if candidate in obj:
                return candidate, obj[candidate]
        return None, None

    def properties(obj, path, owner):
        prop_key, props = lookup(obj, "properties", 10)
        namespace, display = lookup(props, "betterquesting", 10)
        if not isinstance(display, dict):
            return
        _, title = lookup(display, "name", 8)
        title = title.value if isinstance(title, String) else ""
        for name in ("name", "desc"):
            field_key, text = lookup(display, name, 8)
            if isinstance(text, String):
                yield path + (prop_key, namespace, field_key), text, f"{owner}/{name}", f"{owner}/{name}|title={title}"

    yield from properties(node, (), "settings")
    for name, id_field in (("questDatabase", "questID"), ("questLines", "lineID")):
        key, collection = lookup(node, name, 9)
        if not isinstance(collection, (list, dict)):
            continue
        members = enumerate(collection) if isinstance(collection, list) else collection.items()
        seen = set()
        for index, child in members:
            if not isinstance(child, dict):
                continue
            _, identity = lookup(child, id_field, 3)
            if identity is None:
                _, identity = lookup(child, "id", 3)
            identifier = identity.value if isinstance(identity, String) else identity.raw if isinstance(identity, Atom) else str(index)
            owner = f"{name}/{identifier}"
            if owner in seen:
                raise ValueError(f"Better Questing 标识重复：{owner}")
            seen.add(owner)
            yield from properties(child, (key, index), owner)


def _lang_lines(text):
    offset = 0
    seen = set()
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        if content.strip() and not content.lstrip().startswith(("#", "!")) and "=" in content:
            key, value = content.split("=", 1)
            if key in seen:
                raise ValueError(f"语言键重复：{key}")
            seen.add(key)
            start = offset + len(key) + 1
            yield (key,), String(value, start, start + len(value)), key, key
        offset += len(line)


def _add_document(scan, path, target, kind, language_keys=frozenset()):
    root = Path(scan.root)
    if not path.resolve().is_relative_to(root):
        raise ValueError("输入符号链接超出所选整合包范围")
    rel = path.relative_to(root).as_posix()
    if kind == "ftb-nbt":
        raw = path.read_bytes()
        text, encoding, source_hash = base64.b64encode(raw).decode("ascii"), "base64", digest(raw)
    else:
        text, encoding, source_hash = read_text(path)
    document = Document(rel, target, kind, text, source_hash, encoding)
    exclusion = pack_resource_exclusion(scan, document)
    if exclusion:
        scan.metadata.setdefault("excluded_resources", []).append(exclusion)
        return
    if path.suffix.lower() == ".lang":
        candidates = _lang_lines(text)
    else:
        node = parse_nbt(raw) if kind == "ftb-nbt" else Parser(text, path.suffix.lower()[1:]).parse()
        if not isinstance(node, dict):
            raise ValueError("语言/任务文档必须是对象")
        if kind in {"ftb-inline", "ftb-nbt"}:
            candidates = legacy_strings(node, owner=rel)
        elif kind == "betterquesting":
            candidates = betterquesting_strings(node)
        else:
            candidates = ((p, s, "/".join(map(str, p)), "/".join(map(str, p[:1]))) for p, s in strings(node))
    entries = []
    for keypath, node, semantic, context in candidates:
        if not node.value.strip():
            continue
        if kind == "pack-lang" and (keypath[0] in {"language.name", "language.region", "language.code"}
                                     or not (re.search(r"[A-Za-z]", node.value) if scan.source_locale.startswith("en_")
                                             else any(c.isalpha() for c in node.value))):
            continue  # Locale identifiers, glyph overrides and existing Chinese are not English prose.
        # FTB image/page directives are presentation metadata, not unsupported prose.
        if re.fullmatch(r"\s*\{(?:image|item|icon|@?pagebreak)[^{}]*\}\s*", node.value):
            scan.metadata["preserved_directives"] = scan.metadata.get("preserved_directives", 0) + 1
            continue
        if (kind in {"ftb-inline", "ftb-nbt"} and re.fullmatch(r"\{[\w.:/-]+\}", node.value)
                or kind == "betterquesting" and (node.value in language_keys
                    or re.fullmatch(r"(?:bq|betterquesting|untitled)\.[\w.-]+", node.value))):
            scan.metadata["preserved_language_references"] = scan.metadata.get("preserved_language_references", 0) + 1
            if kind == "betterquesting" and node.value not in language_keys:
                scan.warnings.append(f"未解析的 BQ 语言键已保持原样：{rel}:{node.value}")
            continue
        if node.value.lstrip().startswith(("{", "[")):
            try:
                component = json.loads(node.value)
            except ValueError:
                component = None
            if isinstance(component, (dict, list)):
                scan.warnings.append(f"结构化文本保持原样：{rel}:{semantic}")
                continue
        semantic = ("ftb:" if kind.startswith("ftb") else "bq:" if kind == "betterquesting" else "lang:") + semantic
        entries.append(Entry(digest(rel + "\0" + semantic), semantic, rel, list(keypath), node.value,
                             node.start, node.end, context))
    if entries:
        identities = [entry.id for entry in entries]
        if len(set(identities)) != len(identities):
            raise ValueError("文档中存在重复的任务语义标识")
        scan.documents.append(document)
        scan.entries.extend(entries)


def scan_pack(root: Path, source_locale="en_us", target_locale="zh_cn", pack_id=None, scope="all", *,
              resource_packs=(), game_version=None, loader=None) -> Scan:
    from .scopes import recognition_scopes
    scopes = recognition_scopes(scope)
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("整合包根路径必须是目录")
    source_locale, target_locale = locale_name(source_locale), locale_name(target_locale)
    if source_locale == target_locale:
        raise ValueError("源语言代码与目标语言代码不能相同")
    scan = Scan(str(root), pack_id or root.name, source_locale, target_locale)
    scan.metadata["recognition_scope"] = scope
    scan.metadata["recognition_scopes"] = scopes
    for version in root.glob("*.json"):
        try:
            data = json.loads(version.read_text(encoding="utf-8-sig"))
            if "libraries" in data or "inheritsFrom" in data:
                game_args = data.get("arguments", {}).get("game", [])
                candidates = [data.get("clientVersion"), data.get("minecraftVersion"), data.get("inheritsFrom"), data.get("id")]
                if "--fml.mcVersion" in game_args:
                    index = game_args.index("--fml.mcVersion")
                    if index + 1 < len(game_args):
                        candidates.insert(0, game_args[index + 1])
                scan.metadata["minecraft_version"] = next((v for v in candidates if isinstance(v, str)
                    and re.fullmatch(r"\d+\.\d+(?:\.\d+)?", v)), "unknown")
                libraries = " ".join(str(v.get("name", "")) for v in data.get("libraries", []) if isinstance(v, dict))
                scan.metadata["loader"] = next((v for v, token in (("neoforge", "net.neoforged"),
                    ("forge", "net.minecraftforge"), ("fabric", "net.fabricmc"), ("quilt", "org.quiltmc"))
                    if token in libraries), "unknown")
                break
        except (OSError, ValueError, AttributeError):
            continue
    candidates = []
    if game_version:
        scan.metadata["minecraft_version"] = game_version
    if loader:
        scan.metadata["loader"] = loader
    ftb_root = root / "config" / "ftbquests"
    # 1.12 uses ftbquests/<packmode>/chapters/<chapter>/<quest>.{snbt,nbt}.
    quest_roots = [ftb_root, ftb_root / "quests"]
    for mode in sorted(ftb_root.glob("*")):
        if (mode.is_dir() and mode.name.casefold() not in {"quests", "chapters", "reward_tables", "lang",
                "backup", "backups", "recovery"} and (mode / "chapters").is_dir()):
            quest_roots.append(mode)
    for quests in quest_roots:
        if not quests.is_dir():
            continue
        for path in sorted(quests.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(quests)
            parts = list(relative.parts)
            if quests == ftb_root and (parts[0].lower() == "quests" or
                    (len(parts) > 1 and parts[0].lower() not in {"chapters", "reward_tables", "lang"})):
                continue
            if path.suffix.lower() not in (SUPPORTED - {".lang"}) | {".nbt"}:
                continue
            if parts[0].lower() == "lang":
                if path.suffix.lower() == ".nbt":
                    continue
                if len(parts) == 2 and path.stem.lower() == source_locale:
                    target = path.with_name(target_locale + path.suffix)
                elif len(parts) >= 3 and parts[1].lower() == source_locale:
                    target = quests / parts[0] / target_locale / Path(*parts[2:])
                else:
                    continue  # Other languages, recovery files and backups are not sources.
                kind = "ftb-lang-" + path.suffix.lower()[1:]
            else:
                target, kind = path, "ftb-nbt" if path.suffix.lower() == ".nbt" else "ftb-inline"
            candidates.append((path, target.relative_to(root).as_posix(), kind))
    # Only the default database is distributable; do not translate player progress or backups.
    bq_root = root / "config" / "betterquesting"
    for path in sorted(bq_root.glob("*")):
        if path.is_file() and path.stem.casefold() == "defaultquests" and path.suffix.lower() in {".json", ".json5"}:
            candidates.append((path, path.relative_to(root).as_posix(), "betterquesting"))
    # Only pack-provided language assets: never enumerate mods/*.jar.
    for assets in (root / "kubejs" / "assets", root / "resources" / "assets"):
        if assets.is_dir():
            for path in sorted(assets.rglob("*")):
                if path.is_file() and path.parent.name == "lang" and path.stem.lower() == source_locale and path.suffix.lower() in SUPPORTED - {".snbt"}:
                    candidates.append((path, path.with_name(target_locale + path.suffix).relative_to(root).as_posix(), "pack-lang"))
    candidates = [candidate for candidate in candidates if "resources" in scopes or (
        "kubejs" in scopes and candidate[0].relative_to(root).as_posix().startswith("kubejs/"))]
    # BQ display properties can contain native locale keys instead of prose.
    # Keep those references even if a pack-authored target locale excludes the resource.
    language_keys = set()
    for path, _, kind in candidates:
        if kind != "pack-lang" or not path.resolve().is_relative_to(root):
            continue
        try:
            text, _, _ = read_text(path)
            if path.suffix.lower() == ".lang":
                language_keys.update(p[0] for p, _, _, _ in _lang_lines(text))
            else:
                node = Parser(text, path.suffix.lower()[1:]).parse()
                if isinstance(node, dict):
                    language_keys.update(node)
        except (ValueError, OSError, RecursionError):
            pass  # Normal document processing reports invalid resources below.
    seen_targets = set()
    for path, target, kind in candidates:
        try:
            if target.lower() in seen_targets:
                raise ValueError(f"多个源文件映射到同一目标：{target}")
            _add_document(scan, path, target, kind, language_keys)
            seen_targets.add(target.lower())
        except (ValueError, OSError, RecursionError) as exc:
            scan.warnings.append(f"无法处理 {path.relative_to(root).as_posix()}：{exc}")
    if "kubejs" in scopes:
        from ..kubejs.discovery import scan_kubejs
        scan_kubejs(scan)
    if "patchouli" in scopes:
        from ..patchouli.discovery import scan_patchouli
        scan_patchouli(scan, resource_packs)
    if not scan.documents:
        scan.warnings.append("未找到支持的翻译目标")
    return scan
