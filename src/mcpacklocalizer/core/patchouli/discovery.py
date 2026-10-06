# [Module: core.patchouli.discovery] [Status: 已完成] [Brief: 帕秋莉资源识别、语言引用解析及未解析 key 拦截]
"""Read books from loose pack files, enabled resource packs and mod archives."""
from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from ..formats.documents import Parser, String
from ..pack.extraction import Document, Entry, digest
from .diagnostics import looks_like_language_key
from .schema import Templates, fields, get
from .text import TOOLTIP

BOOK = re.compile(r"^(assets|data)/([a-z0-9_.-]+)/patchouli_books/([a-z0-9_./-]+)/book\.json$")
CONTENT = re.compile(
    r"^(assets|data)/([a-z0-9_.-]+)/patchouli_books/([a-z0-9_./-]+)/"
    r"([a-z]{2,3}_[a-z]{2,4})/(categories|entries|templates)/(.+)\.json$", re.IGNORECASE)
LANG = re.compile(r"^assets/([a-z0-9_.-]+)/lang/([a-z]{2,3}_[a-z]{2,4})\.(json|json5|lang)$", re.IGNORECASE)
EXTERNAL = re.compile(r"^patchouli_books/([^/]+)/(?:book\.json|[a-z]{2,3}_[a-z]{2,4}/(?:categories|entries|templates)/.+\.json)$")
PACK_FOLDER = "resourcepacks/MCPackLocalizer-Patchouli"
MAX_MEMBER = 16 * 1024 * 1024
MAX_NESTED = 128 * 1024 * 1024


@dataclass
class Blob:
    container: str
    members: list[str]
    logical: str
    raw: bytes
    prefix: str = ""
    external: bool = False
    signed: bool = False

    @property
    def key(self):
        if not self.members:
            return self.container
        base = self.container if not Path(self.container).is_absolute() else "@patchouli/" + digest(self.container)[:16]
        return base + "!/" + "!/".join(self.members)

    def text(self):
        return self.raw.decode("utf-8-sig")

    def node(self):
        # Parser rejects duplicate keys and preserves source token locations.
        return Parser(self.text(), "json").parse()

    def resource(self, mode, target_member=""):
        return {"container": self.container, "members": self.members, "logical": self.logical,
                "output_mode": mode, "target_member": target_member}


def safe_member(name):
    return (bool(name) and not name.startswith(("/", "\\")) and "\\" not in name
            and ":" not in name and all(part not in {".", ".."} for part in name.split("/")))


def relevant(name):
    return safe_member(name) and bool(BOOK.fullmatch(name) or CONTENT.fullmatch(name)
                                    or LANG.fullmatch(name) or EXTERNAL.fullmatch(name))


def collect(root, explicit=()):
    """Produce an ordered resource view and a complete hash inventory of consulted inputs."""
    blobs, inputs, warnings = [], {}, []
    root = Path(root).resolve()

    def identity(path):
        path = path.resolve()
        return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)

    def remember(path):
        raw = path.read_bytes()
        inputs[identity(path)] = digest(raw)
        return raw

    def archive(raw, container, chain=(), depth=0, parent_signed=False):
        with zipfile.ZipFile(io.BytesIO(raw)) as pack:
            members = pack.namelist()
            if len(members) != len(set(members)):
                raise ValueError("归档中存在重复路径")
            signed = parent_signed or any(re.fullmatch(r"META-INF/[^/]+\.(?:SF|RSA|DSA|EC)", n, re.IGNORECASE)
                                         for n in members)
            for item in pack.infolist():
                name = item.filename
                nested = (name.startswith(("META-INF/jars/", "META-INF/jarjar/")) and name.endswith(".jar")
                          and safe_member(name))
                if nested:
                    if depth >= 3 or item.file_size > MAX_NESTED:
                        warnings.append(f"未扫描帕秋莉嵌套归档：{container}!/{name}")
                        continue
                    archive(pack.read(item), container, (*chain, name), depth + 1, signed)
                elif relevant(name):
                    if item.file_size > MAX_MEMBER:
                        warnings.append(f"帕秋莉资源过大：{container}!/{name}")
                        continue
                    blobs.append(Blob(container, [*chain, name], name, pack.read(item), signed=signed))

    def directory(folder, prefix="", external=False):
        folder = folder.resolve()
        if not folder.is_dir():
            return
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            logical = path.relative_to(folder).as_posix()
            if not relevant(logical):
                continue
            if not path.resolve().is_relative_to(folder):
                warnings.append(f"帕秋莉符号链接指向资源根目录之外：{path}")
                continue
            blobs.append(Blob(identity(path), [], logical, remember(path), prefix, external))

    for jar in sorted((root / "mods").glob("*.jar")):
        if not jar.resolve().is_relative_to(root):
            warnings.append(f"帕秋莉模组符号链接指向实例之外：{jar.name}")
            continue
        try:
            archive(remember(jar), identity(jar))
        except (ValueError, OSError, zipfile.BadZipFile, RuntimeError) as exc:
            warnings.append(f"无法读取帕秋莉归档 {jar.name}：{exc}")
    options = root / "options.txt"
    if options.is_file():
        remember(options)
    # Reuse enabled-pack parsing without downloading community resources.
    from ..mods.scan import enabled_packs
    pack_warnings, skipped = [], []
    packs = enabled_packs(root, pack_warnings, skipped) if options.is_file() else []
    warnings.extend(str(w.get("message", w)) for w in pack_warnings)
    for path in [*packs, *map(Path, explicit)]:
        try:
            if path.is_dir():
                prefix = identity(path) + "/" if path.resolve().is_relative_to(root) else ""
                directory(path, prefix)
            elif path.is_file():
                archive(remember(path), identity(path))
            else:
                warnings.append(f"帕秋莉资源包缺失：{path}")
        except (ValueError, OSError, zipfile.BadZipFile, RuntimeError) as exc:
            warnings.append(f"无法读取帕秋莉资源包 {path}：{exc}")
    for folder in ("resources", "kubejs"):
        directory(root / folder, folder + "/")
    # External books reside immediately below the game root.
    for book in sorted((root / "patchouli_books").glob("*")):
        if book.is_dir():
            for path in sorted(book.rglob("*.json")):
                if path.resolve().is_relative_to(root):
                    logical = path.relative_to(root).as_posix()
                    if EXTERNAL.fullmatch(logical):
                        blobs.append(Blob(identity(path), [], logical, remember(path), external=True))
    return blobs, inputs, warnings


def book_identity(blob):
    if blob.external:
        return "patchouli:" + blob.logical.split("/")[1]
    match = BOOK.fullmatch(blob.logical) or CONTENT.fullmatch(blob.logical)
    return match[2] + ":" + match[3] if match else None


def content_identity(blob):
    if blob.external:
        parts = blob.logical.split("/")
        if len(parts) < 5:
            return None
        return book_identity(blob), parts[2].lower(), parts[3], "/".join(parts[4:])
    match = CONTENT.fullmatch(blob.logical)
    return (book_identity(blob), match[4].lower(), match[5], match[6] + ".json") if match else None


def destination(blob, logical, declaration=False, legacy=False):
    if blob.members:
        mode = "archive" if declaration or legacy else "resourcepack"
        target = blob.container if mode == "archive" else PACK_FOLDER + "/" + logical
    else:
        mode = "file" if blob.external or blob.prefix else "resourcepack"
        target = blob.prefix + logical if mode == "file" else PACK_FOLDER + "/" + logical
    return target, blob.resource(mode, logical)


def target_language(blobs, target):
    existing = next((b for b in reversed(blobs) if b.key == target), None)
    if existing is None:
        return {}
    suffix = Path(existing.logical).suffix.lower()[1:]
    if suffix == "lang":
        from ..pack.extraction import _lang_lines
        return {p[0]: s.value for p, s, _, _ in _lang_lines(existing.text())}
    node = Parser(existing.text(), suffix).parse()
    if not isinstance(node, dict) or any(not isinstance(s, String) for s in node.values()):
        raise TypeError("帕秋莉目标语言必须全部为字符串值")
    return {k: s.value for k, s in node.items()}


def scan_patchouli(scan, explicit=()):
    blobs, inputs, warnings = collect(scan.root, explicit)
    scan.warnings.extend(warnings)
    if not any(book_identity(blob) for blob in blobs):
        return
    metadata = scan.metadata["patchouli"] = {"inputs": inputs, "explicit_packs": [str(p) for p in explicit],
                                            "books": [], "preserved": [], "complete": not warnings}
    declarations, contents, languages, target_keys = {}, {}, {}, set()
    nodes = {}

    def warn(message):
        scan.warnings.append(message)
        metadata["complete"] = False

    for blob in blobs:
        if blob.external and blob.logical.endswith("/book.json") or BOOK.fullmatch(blob.logical):
            identifier = book_identity(blob)
            if not blob.external and not (blob.members and blob.container.startswith("mods/")):
                warn(f"模组 JAR 之外的帕秋莉声明未注册；内容将单独扫描：{blob.key}")
                continue
            if identifier in declarations:
                warn(f"存在多个帕秋莉书籍声明；已保留：{identifier}")
                declarations[identifier] = None
            else:
                declarations[identifier] = blob
        elif key := content_identity(blob):
            previous = contents.get(key)
            if previous and previous.raw != blob.raw:
                metadata.setdefault("overrides", []).append({"resource": blob.logical, "source": blob.key})
            contents[key] = blob
        elif match := LANG.fullmatch(blob.logical):
            try:
                if match[3].lower() == "lang":
                    from ..pack.extraction import _lang_lines
                    items = [(p[0], s) for p, s, _, _ in _lang_lines(blob.text())]
                else:
                    node = Parser(blob.text(), match[3].lower()).parse()
                    items = list(node.items()) if isinstance(node, dict) else []
                for key, string in items:
                    if not isinstance(string, String):
                        continue
                    if match[2].lower() == scan.source_locale:
                        previous = languages.get(key)
                        if previous and previous[1].value != string.value:
                            warn(f"帕秋莉语言键冲突；已选择最新资源：{key}")
                        languages[key] = blob, string
                    elif match[2].lower() == scan.target_locale:
                        target_keys.add(key)
            except (ValueError, UnicodeError, RecursionError) as exc:
                warn(f"无法解析帕秋莉语言资源 {blob.key}：{exc}")

    books = set(declarations) | {key[0] for key in contents}
    documents = {d.path: d for d in scan.documents}
    seen = {e.id for e in scan.entries}

    def annotate(entry, macros):
        previous = entry.patchouli
        entry.patchouli = {"macros": sorted(set(previous.get("macros", ())) | set(macros))}
        if previous:
            return
        for index, match in enumerate(TOOLTIP.finditer(entry.source)):
            if not match[1].strip():
                continue
            subkey = entry.semantic_key + f"/@tooltip/{index}"
            scan.entries.append(Entry(digest(subkey), subkey, entry.document, entry.path.copy(), match[1],
                entry.start, entry.end, entry.context + "; tooltip", patchouli={"role": "tooltip", "index": index,
                    "parent_source": entry.source, "macros": list(macros)}))

    def ensure_document(blob, target, kind, resource):
        document = documents.get(blob.key)
        if document is None:
            document = Document(blob.key, target, kind, blob.text(), digest(blob.raw),
                                "utf-8-sig" if blob.raw.startswith(b"\xef\xbb\xbf") else "utf-8", resource)
            scan.documents.append(document)
            documents[blob.key] = document
        return document

    def add(blob, path, string, target, kind, resource, book, macros=()):
        if not string.value.strip():
            return
        semantic = "patchouli:" + book + "/" + blob.logical + "/" + json.dumps(path, ensure_ascii=False)
        identifier = digest(semantic)
        if identifier in seen:
            return
        seen.add(identifier)
        ensure_document(blob, target, kind, resource)
        entry = Entry(identifier, semantic, blob.key, list(path), string.value, string.start, string.end,
                      f"Patchouli {book}; {'/'.join(map(str, path))}")
        scan.entries.append(entry)
        # Tooltip arguments are translated separately; the main text keeps controls intact.
        annotate(entry, macros)

    def reference(key, book, macros):
        if key in target_keys:
            metadata["preserved"].append({"book": book, "language_key": key, "reason": "existing-translation"})
            return
        blob, string = languages[key]
        existing = next((e for e in scan.entries if e.document == blob.key and e.path == [key]), None)
        if existing:
            annotate(existing, macros)
            return
        match = LANG.fullmatch(blob.logical)
        logical = f"assets/{match[1]}/lang/{scan.target_locale}.{match[3]}"
        target, resource = destination(blob, logical)
        resource.update(sparse_language=True)
        # Loose targets replace an entire file, so retain its existing keys.
        if resource["output_mode"] == "file":
            resource["target_language"] = target_language(blobs, target)
        add(blob, (key,), string, target, "patchouli-lang", resource, "lang:" + match[1], macros)

    for book in sorted(books):
        declaration = declarations.get(book)
        if book in declarations and declaration is None:
            continue
        try:
            config = declaration.node() if declaration else {}
            if not isinstance(config, dict):
                raise TypeError("帕秋莉书籍声明必须是对象")
            data = json.loads(declaration.text()) if declaration else {}
            i18n = data.get("i18n") is True
            macros = (*tuple(data.get("macros", {})), "/$", "<br>") if isinstance(
                data.get("macros", {}), dict) else ("/$", "<br>")
            legacy = declaration is not None and not declaration.external and data.get("use_resource_pack") is not True
            metadata["books"].append({"id": book, "i18n": i18n, "legacy": legacy})
            selected = {}
            for (identifier, locale, role, relative), blob in contents.items():
                if identifier == book and locale == "en_us":
                    selected[role, relative] = contents.get((book, scan.source_locale, role, relative), blob)
            # External files are registered from their en_us basis too.
            template_nodes = {}
            for (role, relative), blob in selected.items():
                node = blob.node()
                nodes[blob.key] = node
                if not isinstance(node, dict):
                    raise TypeError(f"帕秋莉 {role} 必须是对象：{blob.key}")
                if role == "templates":
                    template_nodes[book.split(":", 1)[0] + ":" + relative[:-5]] = node
            templates = Templates(template_nodes, book.split(":", 1)[0], warn)

            def emit(blob, path, string, target, kind, resource, lookup, book=book, macros=macros):
                if lookup and string.value in languages:
                    reference(string.value, book, macros)
                elif lookup and string.value in target_keys:
                    metadata["preserved"].append({"book": book, "language_key": string.value,
                                                  "reason": "existing-translation"})
                elif lookup and looks_like_language_key(string.value):
                    message = f"疑似未解析的帕秋莉语言 key：{string.value}；已拦截，未作为正文提取（{blob.key}:{path}）"
                    document = ensure_document(blob, target, kind, resource)
                    document.resource.setdefault("recognition_warnings", []).append(message)
                    metadata.setdefault("diagnostics", []).append({"source": blob.key, "path": list(path),
                        "value": string.value, "reason": "unresolved-language-key", "message": message})
                    warn(message)
                else:
                    add(blob, path, string, target, kind, resource, book, macros)

            if declaration:
                target, resource = destination(declaration, declaration.logical, declaration=True)
                for path, string in fields(config, ("name", "landing_text", "subtitle")):
                    if path == ("subtitle",) and str(data.get("version", "0")) != "0":
                        continue
                    if declaration.signed and string.value not in languages:
                        warn(f"已签名的帕秋莉 JAR 声明无法修改：{declaration.key}:{path[0]}")
                        continue
                    emit(declaration, path, string, target, "patchouli-book", resource, True)
                macro_values = data.get("macros", {})
                if isinstance(macro_values, dict) and any(
                        isinstance(v, str) and re.search(r"[A-Za-z]{2,}", re.sub(r"\$\([^)]*\)", "", v))
                        for v in macro_values.values()):
                    warn(f"帕秋莉宏包含正文文本时需要适配器：{book}")
            for (role, relative), blob in sorted(selected.items()):
                actual = content_identity(blob)
                logical = re.sub("/" + actual[1] + "/", "/" + scan.target_locale + "/",
                                 blob.logical, count=1, flags=re.IGNORECASE)
                target_blob = contents.get((book, scan.target_locale, role, relative))
                if target_blob:
                    metadata["preserved"].append({"book": book, "source": blob.key, "target": target_blob.key,
                                                 "reason": "existing-target-file"})
                    continue
                target, resource = destination(blob, logical, legacy=legacy)
                if blob.signed and resource["output_mode"] == "archive":
                    warn(f"已签名的旧版帕秋莉 JAR 内容无法修改：{blob.key}")
                    continue
                node = nodes[blob.key]
                candidates = []
                if role == "categories":
                    candidates.extend(fields(node, ("name", "description")))
                elif role == "entries":
                    candidates.extend(fields(node, ("name",)))
                    for index, page in enumerate(node.get("pages", [])):
                        if isinstance(page, String):
                            candidates.append((("pages", index), page))
                        elif isinstance(page, dict):
                            try:
                                candidates.extend(templates.page_fields(page, ("pages", index)))
                            except (ValueError, TypeError) as exc:
                                warn(str(exc) + f"（{blob.key}）")
                elif role == "templates":
                    try:
                        _, paths = templates.analyze(book.split(":", 1)[0] + ":" + relative[:-5])
                        candidates.extend((path, get(node, path)) for path in paths)
                    except (ValueError, TypeError) as exc:
                        warn(str(exc) + f"（{blob.key}）")
                for path, string in candidates:
                    emit(blob, path, string, target, "patchouli-" + role, resource, i18n and role != "templates")
        except (ValueError, UnicodeError, RecursionError, KeyError, TypeError) as exc:
            warn(f"无法处理帕秋莉书籍 {book}：{exc}")
    if any(d.resource.get("output_mode") == "archive" for d in scan.documents):
        scan.warnings.append("帕秋莉声明/旧版书籍直接替换生成独立 JAR 补丁；声明中的直写中文对所有游戏语言生效。")
    if metadata.get("overrides"):
        scan.warnings.append("帕秋莉资源按模组、已启用资源包、显式资源包、resources、kubejs 顺序覆盖；加载器实际顺序可能不同。")


def validate_sources(scan):
    metadata = scan.metadata.get("patchouli")
    if metadata is None:
        return
    blobs, inputs, _ = collect(scan.root, metadata["explicit_packs"])
    if inputs != metadata["inputs"]:
        raise ValueError("帕秋莉来源或已启用资源清单已变更；请重新提取任务")
    actual = {blob.key: blob for blob in blobs}
    for document in scan.documents:
        if not document.kind.startswith("patchouli-"):
            continue
        blob = actual.get(document.path)
        if not blob or digest(blob.raw) != document.source_hash or blob.text() != document.text:
            raise ValueError(f"帕秋莉快照与源文件不一致：{document.path}")
        resource = document.resource
        if (resource.get("container"), resource.get("members"), resource.get("logical")) != (
                blob.container, blob.members, blob.logical):
            raise ValueError(f"帕秋莉资源来源信息无效：{document.path}")
        if resource["output_mode"] == "archive" and (blob.signed or not resource["container"].startswith("mods/")):
            raise ValueError("无法修改已签名或非模组归档中的声明")
        logical = blob.logical
        declaration = document.kind == "patchouli-book"
        legacy = False
        if document.kind == "patchouli-lang":
            match = LANG.fullmatch(logical)
            if not match or not resource.get("sparse_language"):
                raise ValueError("帕秋莉语言资源来源信息无效")
            logical = f"assets/{match[1]}/lang/{scan.target_locale}.{match[3]}"
        elif identity := content_identity(blob):
            logical = re.sub("/" + identity[1] + "/", "/" + scan.target_locale + "/",
                             logical, count=1, flags=re.IGNORECASE)
            declarations = [b for b in blobs if book_identity(b) == identity[0]
                            and b.logical.endswith("/book.json") and b.members
                            and b.container.startswith("mods/")]
            if len(declarations) == 1:
                legacy = json.loads(declarations[0].text()).get("use_resource_pack") is not True
        elif not declaration:
            raise ValueError("帕秋莉文档类型无效")
        target, expected = destination(blob, logical, declaration, legacy)
        if document.target != target or any(resource.get(k) != v for k, v in expected.items()):
            raise ValueError("帕秋莉输出目标来源信息无效")
        if (document.kind == "patchouli-lang" and resource["output_mode"] == "file"
                and resource.get("target_language") != target_language(blobs, target)):
            raise ValueError("帕秋莉保留语言值无效")
