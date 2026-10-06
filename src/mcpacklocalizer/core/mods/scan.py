"""Read-only mod language coverage, CFPA acquisition, and portable reports."""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..pack.snapshots import atomic_write


def default_cache():
    override = os.getenv("MPLT_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    base = Path(os.getenv("LOCALAPPDATA", str(Path.home() / ".cache")))
    return base / "MCPackLocalizer" / "cache"


@dataclass
class ResourceOptions:
    game_version: str
    loader: str
    cache: Path = field(default_factory=default_cache)
    offline: bool = False
    cfpa_pack: list[Path] = field(default_factory=list)
    metadata: Path | None = None
    i18n_jar: Path | None = None
    release: str = "autobuild"
    pack_metadata: dict = field(default_factory=dict, init=False)

META_URL = "https://raw.githubusercontent.com/CFPAOrg/I18nUpdateMod3/main/src/main/resources/i18nMetaData.json"
INDEX_URL = "https://raw.githubusercontent.com/CFPAOrg/Minecraft-Mod-Language-Package/refs/heads/index/version-index.json"
RELEASE_ROOT = "https://github.com/CFPAOrg/Minecraft-Mod-Language-Package/releases/download/"
LANG_PATH = re.compile(r"^assets/([a-z0-9_.-]+)/lang/(en_us|zh_cn)\.(json|lang|json5)$", re.IGNORECASE)
MAX_ENTRY = 32 * 1024 * 1024
MAX_DOWNLOAD = 256 * 1024 * 1024


def progress(message):
    print(message, file=sys.stderr, flush=True)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def fetch(url, limit=MAX_DOWNLOAD):
    request = urllib.request.Request(url, headers={"User-Agent": "MCPackLocalizer/0.1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"下载内容过大：{url}")
    return data


def cached_json(url, path, offline):
    if not offline:
        progress(f"获取元数据: {url}")
        data = fetch(url, 2 * 1024 * 1024)
        value = json.loads(data)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, data)
        return value
    if not path.is_file():
        raise ValueError(f"离线元数据缓存缺失：{path}")
    return json.loads(path.read_bytes())


def version_tuple(value):
    if not re.fullmatch(r"\d+(?:\.\d+){1,2}", value):
        raise ValueError(f"仅支持稳定的数字版 Minecraft 版本：{value}")
    parts = tuple(map(int, value.split(".")))
    return parts + (0,) * (3 - len(parts))


def select_game(metadata, game_version):
    version = version_tuple(game_version)
    game = next((g for g in metadata["games"]
                 if version_tuple(g["gameVersions"][1:-1].split(",")[0]) <= version
                 <= version_tuple(g["gameVersions"][1:-1].split(",")[1])), None)
    if game is None:
        raise ValueError(f"没有适用于 Minecraft {game_version} 的 I18n 元数据映射；请使用 --metadata 或 --i18n-jar")
    return game


def select_assets(metadata, game_version, loader):
    game = select_game(metadata, game_version)
    # Quilt uses Fabric's assets; NeoForge falls back to Forge when no variant exists.
    normalized = {"quilt": "fabric", "neoforge": "forge"}.get(loader, loader)
    selected = []
    for target in game["convertFrom"]:
        choices = [a for a in metadata["assets"] if a["targetVersion"] == target]
        if not choices:
            raise ValueError(f"没有 {target} 的资源映射")
        selected.append(next((a for a in choices if a["loader"].lower() == normalized), choices[0]))
    return selected


def load_metadata(args):
    cache = args.cache.resolve()
    if args.i18n_jar:
        with zipfile.ZipFile(args.i18n_jar) as archive:
            metadata = json.loads(archive.read("i18nMetaData.json"))
    elif args.metadata:
        metadata = json.loads(args.metadata.read_bytes())
    elif (args.offline or args.cfpa_pack) and not (cache / "i18nMetaData.json").is_file():
        metadata = json.loads(Path(__file__).with_name("data").joinpath("i18n_metadata.json").read_bytes())
    else:
        metadata = cached_json(META_URL, cache / "i18nMetaData.json", args.offline or bool(args.cfpa_pack))
    args.pack_metadata = select_game(metadata, args.game_version)
    return metadata


def file_digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(data)
    return hasher.hexdigest()


def get_cfpa(args):
    metadata = load_metadata(args)
    if args.cfpa_pack:
        return [(p.resolve(), {"kind": "local_cfpa", "path": str(p.resolve()),
                              "sha256": file_digest(p) if p.is_file() else None}) for p in args.cfpa_pack]
    cache = args.cache.resolve()
    selected = select_assets(metadata, args.game_version, args.loader)
    index = cached_json(INDEX_URL, cache / "version-index.json", args.offline) if args.release == "indexed" else {}
    # Follow I18nConfig: resolve a single release tag using the first resource version.
    first = selected[0]
    index_key = first["targetVersion"] + ("-fabric" if args.loader in {"fabric", "quilt"} else "")
    tag = index.get(index_key) if args.release == "indexed" else "autobuild"
    selection_note = ""
    if not tag:
        tag = "autobuild"
        selection_note = f"Index lacks {index_key}; used official rolling autobuild release"
        progress(f"索引缺少 {index_key}，改用官方 autobuild 发布包（报告记录此回退）")
    packs = []
    for asset in selected:
        filename = asset["filename"]
        if Path(filename).name != filename or Path(asset["md5Filename"]).name != asset["md5Filename"]:
            raise ValueError("元数据中的资源文件名无效")
        folder = cache / "releases" / hashlib.sha256(tag.encode()).hexdigest()[:16]
        path = folder / filename
        md5_path = folder / asset["md5Filename"]
        base = RELEASE_ROOT + urllib.parse.quote(tag, safe="") + "/"
        if not args.offline:
            progress(f"检查 CFPA {asset['targetVersion']} ({asset['loader']}): {tag}")
            md5_data = fetch(base + urllib.parse.quote(asset["md5Filename"]), 1024)
            expected = md5_data.decode("ascii").strip()
        else:
            if not md5_path.is_file():
                raise ValueError(f"离线校验和缓存缺失：{md5_path}")
            expected = md5_path.read_text(encoding="ascii").strip()
            md5_data = expected.encode("ascii")
        if not re.fullmatch(r"[0-9a-fA-F]{32}", expected):
            raise ValueError(f"MD5 元数据无效：{filename}")
        data = path.read_bytes() if path.is_file() else None
        if data is None or hashlib.md5(data).hexdigest().lower() != expected.lower():
            if args.offline:
                raise ValueError(f"离线资源包缺失或校验和不匹配：{path}")
            progress(f"下载 {filename}")
            data = fetch(base + urllib.parse.quote(filename))
            if hashlib.md5(data).hexdigest().lower() != expected.lower():
                raise ValueError(f"CFPA 校验和不匹配：{filename}；请重新运行以重试")
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if archive.testzip():
                    raise ValueError(f"ZIP 文件无效：{filename}")
            folder.mkdir(parents=True, exist_ok=True)
            atomic_write(path, data)
        md5_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(md5_path, md5_data)
        packs.append((path, {"kind": "downloaded_cfpa", "target_version": asset["targetVersion"],
                            "loader_variant": asset["loader"], "release": tag, "url": base + filename,
                            "requested_release": args.release, "selection_note": selection_note,
                            "md5": expected, "sha256": hashlib.sha256(data).hexdigest(), "path": str(path)}))
    return packs


class RichLanguageValue(str):
    def __new__(cls, raw):
        def text(value):
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                return "".join(text(item) for item in value)
            if isinstance(value, dict):
                main = value.get("text", "")
                if "index" in value:
                    main += "{index:" + str(value["index"]) + "}"
                for name in ("translate", "keybind", "selector", "nbt", "score"):
                    if name in value:
                        main += "{" + name + ":" + str(value[name]) + "}"
                return main + text(value.get("extra", []))
            return str(value)
        result = super().__new__(cls, text(raw))
        result.raw = raw
        return result


def parse_language(data, suffix, warnings=None, source=""):
    text = data.decode("utf-8-sig")
    if suffix.lower() == "lang":
        values = {}
        for line in text.splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
        return values
    if suffix.lower() == "json5":
        try:
            import json5
        except ImportError as exc:
            raise ValueError("JSON5 解析需要 json5 库") from exc
        values = json5.loads(text)
    else:
        try:
            values = json.loads(text)
        except json.JSONDecodeError:
            # Keep quoted text intact; permit Gson-style comments and trailing commas.
            tokens = r'"(?:\\.|[^"\\])*"|//[^\r\n]*|/\*.*?\*/'
            cleaned = re.sub(tokens, lambda m: m.group() if m.group().startswith('"') else
                             "".join("\n" if c == "\n" else " " for c in m.group()), text, flags=re.DOTALL)
            cleaned = re.sub(r'"(?:\\.|[^"\\])*"|,(?=\s*[}\]])',
                             lambda m: m.group() if m.group().startswith('"') else " ", cleaned, flags=re.DOTALL)
            values = json.loads(cleaned, strict=False)
            if warnings is not None:
                warnings.append({"severity": "notice", "source": source,
                                 "message": "使用宽松解码读取了含注释、尾随逗号或字面控制字符的 JSON"})
    if not isinstance(values, dict):
        raise ValueError("语言文件必须是一个对象")  # noqa: TRY004 - Malformed input is a validation error.
    result = {}
    rich_keys = []
    for key, value in values.items():
        if isinstance(value, str):
            result[key] = value
        elif isinstance(value, (list, dict)):
            result[key] = RichLanguageValue(value)
            rich_keys.append(key)
        elif isinstance(value, (int, float, bool)):
            result[key] = json.dumps(value)
        else:
            raise ValueError(f"不支持的语言值 {key}：{type(value).__name__}")  # noqa: TRY004
    if rich_keys and warnings is not None:
        warnings.append({"severity": "notice", "source": source, "keys": rich_keys,
                         "message": "富文本值按语言键计数；原始结构保留，供日后单独翻译"})
    return result


def archive_identity(archive):
    for name in ("fabric.mod.json", "quilt.mod.json", "mcmod.info", "META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
        if name in archive.namelist() and archive.getinfo(name).file_size > 1024 * 1024:
            raise ValueError("模组身份元数据超出大小限制")
    if "quilt.mod.json" in archive.namelist():
        data = json.loads(archive.read("quilt.mod.json"))["quilt_loader"]
        mods = [(data.get("id", ""), data.get("version", ""))]
    elif "fabric.mod.json" in archive.namelist():
        data = json.loads(archive.read("fabric.mod.json"))
        mods = [(data.get("id", ""), data.get("version", ""))]
    else:
        metadata = next((name for name in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml")
                         if name in archive.namelist()), None)
        mods = [(mod.get("modId", ""), mod.get("version", ""))
                for mod in tomllib.loads(archive.read(metadata).decode("utf-8-sig")).get("mods", [])] if metadata else []
        if not metadata and "mcmod.info" in archive.namelist():
            data = json.loads(archive.read("mcmod.info"))
            mods = [(mod.get("modid", ""), mod.get("version", "")) for mod in data]
    mods = [(name, str(version)) for name, version in mods
            if isinstance(name, str) and re.fullmatch(r"[a-z][a-z0-9_.-]*", name)]
    return {"ids": sorted({name for name, _ in mods}), "versions": dict(mods)}


def read_languages(path, warnings, nested=False, legacy=False, namespaces=None, first_files=None, identities=None):
    """Yield original path, namespace, locale, parsed values, and full source."""
    def entries(archive, label, depth):
        if identities is not None:
            try:
                identities[label] = archive_identity(archive)
            except (ValueError, UnicodeError, KeyError, TypeError, AttributeError) as exc:
                identities[label] = {"ids": [], "versions": {}}
                warnings.append({"severity": "notice", "source": label,
                                 "message": f"无法验证用于共享复用的模组身份：{exc}"})
        for info in sorted(archive.infolist(), key=lambda i: i.filename):
            name = info.filename
            match = LANG_PATH.fullmatch(name)
            if match and match.group(1) in {".", ".."}:
                warnings.append({"severity": "error", "source": label + "!" + name, "message": "不安全的命名空间"})
                continue
            if match and ((match.group(3).lower() == "lang") != legacy):
                continue
            if match and namespaces is not None and match.group(1).lower() not in namespaces:
                continue
            if match and first_files is not None:
                if name in first_files:
                    continue
                first_files.add(name)
            is_nested = nested and name.lower().endswith(".jar") and name.startswith(("META-INF/jars/", "META-INF/jarjar/"))
            if is_nested and depth >= 3:
                warnings.append({"severity": "error", "source": label + "!" + name,
                                 "message": "嵌套 JAR 深度超出静态扫描上限（3）"})
                continue
            if not match and not is_nested:
                continue
            try:
                if info.file_size > MAX_ENTRY:
                    raise ValueError("条目超出大小限制")
                data = archive.read(info)
                if is_nested:
                    with zipfile.ZipFile(io.BytesIO(data)) as child:
                        yield from entries(child, label + "!" + name, depth + 1)
                else:
                    ns, locale, suffix = match.groups()
                    yield name, ns.lower(), locale.lower(), parse_language(data, suffix, warnings, label + "!" + name), label + "!" + name
            except (ValueError, OSError, UnicodeError, zipfile.BadZipFile, RuntimeError) as exc:
                warnings.append({"severity": "error", "source": label + "!" + name, "message": str(exc),
                                 **({"namespace": match.group(1).lower(), "locale": match.group(2).lower()} if match else {})})
    if path.is_dir():
        for file in sorted((path / "assets").glob("*/lang/*")):
            if not file.is_file():
                continue
            relative = file.relative_to(path).as_posix()
            match = LANG_PATH.fullmatch(relative)
            if match and match.group(1) in {".", ".."}:
                warnings.append({"severity": "error", "source": str(file), "message": "不安全的命名空间"})
                continue
            if match and ((match.group(3).lower() == "lang") != legacy):
                continue
            if match and namespaces is not None and match.group(1).lower() not in namespaces:
                continue
            if match and first_files is not None:
                if relative in first_files:
                    continue
                first_files.add(relative)
            if match:
                try:
                    if file.stat().st_size > MAX_ENTRY:
                        raise ValueError("语言文件超出大小限制")
                    ns, locale, suffix = match.groups()
                    yield relative, ns.lower(), locale.lower(), parse_language(file.read_bytes(), suffix, warnings, str(file)), str(file)
                except (ValueError, OSError, UnicodeError) as exc:
                    warnings.append({"severity": "error", "source": str(file), "message": str(exc),
                                     "namespace": match.group(1).lower(), "locale": match.group(2).lower()})
    else:
        try:
            with zipfile.ZipFile(path) as archive:
                yield from entries(archive, str(path), 0)
        except (OSError, zipfile.BadZipFile) as exc:
            warnings.append({"severity": "error", "source": str(path), "message": str(exc)})


def enabled_packs(root, warnings, skipped):
    options = root / "options.txt"
    if not options.is_file():
        return []
    try:
        line = next((s for s in options.read_text(encoding="utf-8-sig").splitlines()
                     if s.startswith("resourcePacks:")), None)
        names = json.loads(line.split(":", 1)[1]) if line else []
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise ValueError("resourcePacks 必须是字符串数组")
    except (OSError, ValueError, UnicodeError) as exc:
        warnings.append({"severity": "error", "source": str(options), "message": str(exc)})
        return []
    result = []
    base = (root / "resourcepacks").resolve()
    paxi_base = (root / "config" / "paxi" / "resourcepacks").resolve()
    has_paxi = any(p.is_file() and p.suffix.lower() == ".jar" and p.name.lower().startswith("paxi")
                   for p in (root / "mods").iterdir())
    for name in names:
        if name == "vanilla":
            continue
        if name == "mod_resources":
            skipped.append({"resource_pack": name, "reason": "Forge 模组资源已从已安装的 JAR 中读取"})
            continue
        filename = name.removeprefix("file/")
        if filename.startswith("Minecraft-Mod-Language-Modpack"):
            skipped.append({"resource_pack": name, "reason": "已被本次扫描选定的 CFPA 源替代"})
            continue
        path = (base / filename).resolve()
        if not path.is_relative_to(base):
            warnings.append({"severity": "error", "source": name, "message": "资源包路径超出 resourcepacks 目录"})
        elif path.exists():
            result.append(path)
        elif has_paxi and (paxi_base / filename).resolve().is_relative_to(paxi_base) and (paxi_base / filename).exists():
            result.append((paxi_base / filename).resolve())
        else:
            warnings.append({"severity": "error", "source": name,
                             "message": "启用的资源包不可用（可能是模组内置资源包）"})
    return result


def detect(root, cfpa, mode="effective", extra_packs=(), legacy=False):
    warnings, skipped = [], []
    english, builtin, community, effective = {}, {}, {}, {}
    namespace_jars = defaultdict(set)
    conflicts = []
    identities, source_conflicts = {}, set()
    jars = sorted(p for p in (root / "mods").iterdir() if p.is_file() and p.suffix.lower() == ".jar")
    if not jars:
        raise ValueError(f"{root / 'mods'} 中没有可用的 *.jar 文件")

    def overlay(destination, ns, values, source, kind, track_conflicts=False, locale=""):
        for key, value in values.items():
            identifier = (ns, key)
            if track_conflicts and identifier in destination and destination[identifier]["value"] != value:
                conflicts.append({"namespace": ns, "key": key, "previous": destination[identifier]["source"],
                                  "selected": source, "kind": kind, "locale": locale})
                if locale == "en_us":
                    source_conflicts.add(identifier)
            destination[identifier] = {"value": value, "source": source, "kind": kind}
            if isinstance(value, RichLanguageValue):
                destination[identifier]["raw"] = value.raw

    for jar in jars:
        progress(f"扫描 {jar.name}")
        for _, ns, locale, values, source in read_languages(jar, warnings, nested=True, legacy=legacy, identities=identities):
            namespace_jars[ns].add(jar.name)
            overlay(english if locale == "en_us" else builtin, ns, values, source, "mod", True, locale)
    # The official converter chooses the first complete file at an identical ZIP path.
    seen_files = set()
    for path, _ in cfpa:
        for _, ns, locale, values, source in read_languages(path, warnings, legacy=legacy,
                                                           namespaces=namespace_jars, first_files=seen_files):
            if locale == "zh_cn":
                overlay(community, ns, values, source, "cfpa")
    effective.update(builtin)
    effective.update(community)
    before_custom = dict(effective)
    custom_sources = []
    if mode == "effective":
        # options.txt stores enabled packs from low to high priority.
        custom_sources.extend((p, "resourcepack") for p in enabled_packs(root, warnings, skipped))
        for folder in (root / "resources", root / "kubejs"):
            if (folder / "assets").is_dir():
                custom_sources.append((folder, "pack_assets"))
        if any(kind == "pack_assets" for _, kind in custom_sources):
            warnings.append({"severity": "notice", "source": str(root),
                             "message": "静态扫描假定 resources/assets 与 kubejs/assets 均具有最高优先级；实际加载器/配置可能不同"})
    custom_sources.extend((p.resolve(), "explicit_resourcepack") for p in extra_packs)
    for path, kind in custom_sources:
        for _, ns, locale, values, source in read_languages(path, warnings, legacy=legacy):
            if locale == "en_us":
                overlay(english, ns, values, source, kind)
            else:
                overlay(effective, ns, values, source, kind)
    # Only namespaces actually supplied by installed mod JARs are in scope.
    english = {k: v for k, v in english.items() if k[0] in namespace_jars and k[0] != "minecraft"}
    missing, uncertain, identical, empty = [], [], [], []
    summary = []
    keys_by_namespace = defaultdict(list)
    for ns, key in english:
        keys_by_namespace[ns].append(key)
    community_namespaces = {ns for ns, _ in community}
    invalid_chinese = defaultdict(list)
    for warning in warnings:
        if warning["severity"] == "error" and warning.get("locale") == "zh_cn":
            invalid_chinese[warning["namespace"]].append(warning["source"])
    for ns in sorted(keys_by_namespace):
        keys = sorted(keys_by_namespace[ns])
        counts = defaultdict(int)
        for key in keys:
            identifier = (ns, key)
            source = english[identifier]
            translation = effective.get(identifier)
            record = {"namespace": ns, "key": key, "english": source["value"],
                      "english_source": source["source"], "mod_jars": sorted(namespace_jars[ns])}
            provider = identities.get(source["source"].rsplit("!", 1)[0], {"ids": [], "versions": {}})
            record |= {"provider_ids": provider["ids"], "provider_versions": provider["versions"],
                       "source_kind": source["kind"], "english_sha256": hashlib.sha256(source["value"].encode()).hexdigest(),
                       "reusable": source["kind"] == "mod" and bool(provider["ids"])
                                   and identifier not in source_conflicts and "raw" not in source}
            if "raw" in source:
                record |= {"english_raw": source["raw"], "requires_structured_translation": True}
            counts["cfpa_covered_keys"] += identifier in community
            counts["builtin_covered_keys"] += identifier in builtin
            counts["missing_before_custom"] += identifier not in before_custom
            if translation is None:
                if ns in invalid_chinese:
                    uncertain.append(record | {"reason": "unreadable_chinese_source", "unreadable_sources": invalid_chinese[ns]})
                    counts["uncertain_keys"] += 1
                else:
                    missing.append(record | {"reason": "namespace_absent_from_cfpa" if ns not in community_namespaces
                                             else "key_absent_from_all_chinese_sources"})
                    counts["missing_keys"] += 1
            else:
                counts["covered_keys"] += 1
                counts["covered_by_" + translation["kind"]] += 1
                record |= {"chinese": translation["value"], "chinese_source": translation["source"]}
                if "raw" in translation:
                    record["chinese_raw"] = translation["raw"]
                if not translation["value"].strip():
                    empty.append(record)
                    counts["empty_keys"] += 1
                elif translation.get("raw", translation["value"]) == source.get("raw", source["value"]):
                    identical.append(record)
                    counts["identical_keys"] += 1
        summary.append({"namespace": ns, "mod_jars": sorted(namespace_jars[ns]), "english_keys": len(keys),
                        **{key: counts[key] for key in ("cfpa_covered_keys", "builtin_covered_keys", "missing_before_custom",
                            "covered_keys", "missing_keys", "uncertain_keys", "identical_keys", "empty_keys")},
                        "effective_providers": {k.removeprefix("covered_by_"): v for k, v in counts.items()
                                                if k.startswith("covered_by_")}})
    if conflicts:
        warnings.append({"severity": "notice", "source": "mods",
                         "message": "冲突的语言键在本次静态扫描中按 JAR 字母顺序处理；实际加载器优先级可能不同"})
    if not english:
        warnings.append({"severity": "error", "source": str(root / "mods"),
                         "message": "未找到可读取的模组英文语言键"})
    return {"schema_version": 1, "generated_at": datetime.now(UTC).isoformat(),
            "instance": str(root), "mode": mode, "scan_complete": not any(w["severity"] == "error" for w in warnings),
            "totals": {"mod_jars": len(jars), "namespaces": len(summary), "english_keys": len(english),
                       "missing_keys": len(missing), "uncertain_keys": len(uncertain),
                       "covered_keys": len(english) - len(missing) - len(uncertain),
                       "identical_keys": len(identical), "empty_keys": len(empty)},
            "namespaces": summary, "missing": missing, "uncertain": uncertain, "identical": identical, "empty": empty,
            "cfpa_sources": [record for _, record in cfpa],
            "custom_sources": [{"path": str(p), "kind": k} for p, k in custom_sources],
            "conflicts": conflicts, "skipped_resourcepacks": skipped, "warnings": warnings,
            "mod_identities": identities}


def write_report(report, output):
    output.mkdir(parents=True, exist_ok=True)
    atomic_write(output / "report.json", json_bytes(report))
    atomic_write(output / "uncertain.json", json_bytes(report["uncertain"]))
    with (output / "missing.tsv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(["namespace", "key", "english", "mod_jars", "english_source", "reason", "provider_ids",
                         "reusable", "entry_id", "library_status", "reused_translation"])
        for row in report["missing"]:
            writer.writerow([row["namespace"], row["key"], row["english"], ", ".join(row["mod_jars"]),
                             row["english_source"], row["reason"], ", ".join(row.get("provider_ids", [])),
                             row.get("reusable", False), row.get("entry_id", ""),
                             row.get("library_match", {}).get("status", ""), row.get("reused_translation", "")])
    languages = defaultdict(dict)
    for row in report["missing"]:
        languages[row["namespace"]][row["key"]] = row.get("english_raw", row["english"])
    for ns, values in languages.items():
        folder = output / "missing-languages" / ns
        folder.mkdir(parents=True, exist_ok=True)
        atomic_write(folder / "en_us.json", json_bytes(values))
    esc = lambda value: html.escape(str(value))
    rows = "".join(f"<tr><td>{esc(n['namespace'])}</td><td>{n['english_keys']}</td>"
                   f"<td>{n['cfpa_covered_keys']}</td><td>{n['builtin_covered_keys']}</td>"
                   f"<td>{n['missing_before_custom']}</td><td>{n['missing_keys']}</td>"
                   f"<td>{n['uncertain_keys']}</td>"
                   f"<td>{n['identical_keys']}</td><td>{n['empty_keys']}</td>"
                   f"<td>{esc(', '.join(n['mod_jars']))}</td></tr>" for n in report["namespaces"])
    warning_html = "".join(f"<li>{esc(w['severity'])}: {esc(w['source'])} — {esc(w['message'])}</li>"
                           for w in report["warnings"])
    data = json.dumps(report["missing"], ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    page = r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>I18n 缺失汉化检测</title>
<style>body{font:15px system-ui;margin:30px;color:#202d3a;background:#f8fafc}h1{font-size:25px}
table{border-collapse:collapse;width:100%;background:white}td,th{padding:9px;border-bottom:1px solid #dde4ea;text-align:left}
th{background:#e8eef4}input,select{padding:10px;margin:12px 8px 12px 0}pre{white-space:pre-wrap;margin:0}
.note{padding:14px;background:#fff2cd;border-radius:8px}td{vertical-align:top}small{color:#526273}</style>
<h1>I18n 缺失汉化检测</h1><p>__INSTANCE__</p><p>__TOTALS__</p>
<p class="note">__STATUS__。缺失 = 已读取的源中没有对应中文语言键；同英文、留空单独列出。CFPA 与模组自带覆盖数可能重叠。
无法读取的动态或内置资源包可能提供更多中文，所以不完整扫描的缺失仅作为静态候选。
这是静态检测，条件注册资源、运行时生成文本和加载器特殊资源优先级需要游戏验证。共享译库默认只复用已审核且英文完全一致的译文。游戏目录只读。</p>
<details><summary>警告与限制</summary><ul>__WARNINGS__</ul></details>
<h2>命名空间汇总</h2><table><thead><tr><th>命名空间</th><th>英文键</th><th>CFPA 已有</th><th>模组自带</th>
<th>自定义包补充前未覆盖</th><th>可读取源中缺失</th><th>无法确认</th><th>同英文</th><th>留空</th><th>JAR</th></tr></thead><tbody>__ROWS__</tbody></table>
<h2>缺失条目与共享译库</h2><input id="query" placeholder="搜索命名空间、键、英文、译文" size="45"><select id="namespace"><option value="">全部命名空间</option></select>
<select id="reuse"><option value="">全部复用状态</option><option value="reused">已复用</option><option value="source_changed">英文已变化</option><option value="conflict">译库冲突</option><option value="draft_only">只有草稿</option><option value="ineligible">仅本任务</option><option value="pending">待翻译</option><option value="deferred">延期处理</option></select>
<button id="previous">上一页</button> <button id="next">下一页</button><p id="count"></p>
<table><thead><tr><th>命名空间</th><th>语言键</th><th>英文</th><th>来源模组</th><th>复用状态 / 条目 ID</th><th>译文 / 参考候选</th></tr></thead><tbody id="missing"></tbody></table>
<p><small>report.json 保存全部数据；missing.tsv 可用于表格查看；missing-languages/ 中是缺失英文交换文件，不能直接作为汉化资源包安装。</small></p>
<p><small>坏中文文件涉及的未覆盖条目列入 uncertain.json，不计入确定缺失。富文本的原始结构保存在 JSON 中。</small></p>
<script id="data" type="application/json">__DATA__</script><script>
const data=JSON.parse(document.querySelector('#data').textContent), size=100;let page=0;
const select=document.querySelector('#namespace');for(const n of [...new Set(data.map(x=>x.namespace))]){const o=document.createElement('option');o.value=n;o.textContent=n;select.append(o);}
const labels={reused:'已复用',source_changed:'英文已变化，仅参考',conflict:'冲突，需选择译文',draft_only:'只有草稿',ineligible:'仅本任务',pending:'待翻译',deferred:'延期：富文本或空英文',invalid:'译库格式无效',disabled:'复用已关闭'};
function status(x){return x.library_match?.status || (x.requires_structured_translation||!x.english.trim()?'deferred':!x.reusable?'ineligible':'pending');}
function render(){const q=document.querySelector('#query').value.toLowerCase(),n=select.value,r=document.querySelector('#reuse').value;
const filtered=data.filter(x=>(!n||x.namespace===n)&&(!r||status(x)===r)&&[x.namespace,x.key,x.english,x.reused_translation||''].join(' ').toLowerCase().includes(q));
const max=Math.max(0,Math.ceil(filtered.length/size)-1);page=Math.min(Math.max(0,page),max);
document.querySelector('#count').textContent=`匹配 ${filtered.length} 条，第 ${page+1}/${max+1} 页`;
const body=document.querySelector('#missing');body.replaceChildren();for(const x of filtered.slice(page*size,(page+1)*size)){
const refs=(x.library_match?.candidates||[]).map(c=>`#${c.id||c.record_id} [${c.state}] ${c.source||''} → ${c.translation}`).join('\n');
const tr=document.createElement('tr');for(const v of [x.namespace,x.key,x.english,(x.provider_ids||[]).join(', ')+'\n'+x.mod_jars.join(', '),(labels[status(x)]||status(x))+'\n'+(x.entry_id||''),x.reused_translation||refs]){const td=document.createElement('td'),p=document.createElement('pre');p.textContent=v;td.append(p);tr.append(td);}body.append(tr);}}
document.querySelector('#query').oninput=()=>{page=0;render();};select.onchange=()=>{page=0;render();};
document.querySelector('#reuse').onchange=()=>{page=0;render();};
document.querySelector('#previous').onclick=()=>{page--;render();};document.querySelector('#next').onclick=()=>{page++;render();};render();</script></html>"""
    total = report["totals"]
    totals_text = (f"{total['mod_jars']} 个 JAR · {total['namespaces']} 个命名空间 · {total['english_keys']} 个英文键 · "
                   f"{total['covered_keys']} 个已有中文键 · {total['missing_keys']} 个缺失键 · "
                   f"{total['uncertain_keys']} 个无法确认 · "
                   f"{total['identical_keys']} 个同英文 · {total['empty_keys']} 个留空")
    if "library_reused_keys" in total:
        totals_text += (f" · 共享译库复用 {total['library_reused_keys']} 键 · 待翻译 {total['translation_pending_keys']} 键"
                        f" · 延期 {total['deferred_keys']} 键")
    replacements = {"__INSTANCE__": esc(report["instance"]), "__TOTALS__": esc(totals_text),
                    "__STATUS__": "扫描完整" if report["scan_complete"] else "扫描不完整，请检查解析错误",
                    "__WARNINGS__": warning_html, "__ROWS__": rows, "__DATA__": data}
    # Substitute once, so text from mods cannot act as a template placeholder.
    page = re.sub(r"__[A-Z]+__", lambda m: replacements[m.group()], page)
    atomic_write(output / "report.html", page)

