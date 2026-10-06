# [Module: tests.pack.patchouli] [Status: 已完成] [Brief: 帕秋莉引用解析、未解析 key 拦截与独立补丁回归]
import io
import json
import zipfile

import pytest

from mcpacklocalizer.core.formats.rendering import render_document
from mcpacklocalizer.core.pack.extraction import Scan, scan_pack
from mcpacklocalizer.core.pack.patch import build_patch, validate_sources
from mcpacklocalizer.core.patchouli.diagnostics import resource_warnings
from mcpacklocalizer.core.patchouli.discovery import PACK_FOLDER
from mcpacklocalizer.core.patchouli.text import translate_text
from mcpacklocalizer.core.translation.local import validate_entry
from mcpacklocalizer.paths import RESOURCES


def put(root, relative, data):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False) if not isinstance(data, str) else data, encoding="utf-8")
    return path


def zip_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data if isinstance(data, (str, bytes)) else json.dumps(data))
    return buffer.getvalue()


def mod(root, files):
    path = root / "mods/demo.jar"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(zip_bytes(files))
    return path


def book_files(*, declaration=None, pages=None):
    return {
        "data/demo/patchouli_books/guide/book.json": declaration or {
            "name": "Guide", "landing_text": "Welcome", "use_resource_pack": True},
        "assets/demo/patchouli_books/guide/en_us/categories/basics.json": {
            "name": "Basics", "description": "Start here", "icon": "minecraft:book"},
        "assets/demo/patchouli_books/guide/en_us/entries/start.json": {
            "name": "First Steps", "category": "demo:basics", "icon": "minecraft:book",
            "pages": pages or [{"type": "patchouli:text", "text": "Read the guide"}]}}


def scan(root, scope="patchouli"):
    return scan_pack(root, scope=scope, game_version="1.20.1")


def translated(scan):
    for entry in scan.entries:
        entry.translation = entry.source.replace("Guide", "指南").replace("Read", "阅读") + "汉化"


def test_builtin_fields_and_short_pages_preserve_structural_data(tmp_path):
    root = tmp_path / "game"
    pages = ["First page", {"type": "patchouli:crafting", "title": "Crafting", "text": "Craft this",
             "recipe": "demo:starter", "recipe2": "demo:other", "anchor": "craft"},
             {"type": "patchouli:multiblock", "name": "Structure", "text": "Place blocks",
              "multiblock": {"mapping": {"A": "demo:stone"}, "pattern": [["AAA"]]}},
             {"type": "patchouli:link", "url": "https://example.com", "link_text": "Open site", "text": "Details"},
             {"type": "patchouli:entity", "name": "Mob", "entity": "minecraft:chicken", "text": "Look"}]
    original = book_files(pages=pages)
    mod(root, original)
    result = scan(root)
    assert {"First page", "Crafting", "Structure", "Open site", "Mob"}.issubset(e.source for e in result.entries)
    assert not any(e.source in {"demo:starter", "craft", "AAA", "minecraft:chicken"} for e in result.entries)
    document = next(d for d in result.documents if d.kind == "patchouli-entries")
    entries = [e for e in result.entries if e.document == document.path]
    translated(result)
    rendered = json.loads(render_document(document, entries))
    assert rendered["pages"][1]["recipe"] == "demo:starter"
    assert rendered["pages"][1]["anchor"] == "craft"
    assert rendered["pages"][2]["multiblock"] == pages[2]["multiblock"]
    assert rendered["category"] == "demo:basics"
    assert Scan.from_dict(result.to_dict()).to_dict() == result.to_dict()


def test_mod_declaration_direct_replacement_and_resource_pack_export(tmp_path):
    root = tmp_path / "game"
    jar = mod(root, {**book_files(), "demo.class": b"unchanged class", "META-INF/mods.toml": "mod metadata"})
    before = jar.read_bytes()
    result = scan(root)
    translated(result)
    manifest = build_patch(result, tmp_path / "task")
    assert jar.read_bytes() == before
    with zipfile.ZipFile(tmp_path / "task/patch/mods/demo.jar") as archive:
        declaration = json.loads(archive.read("data/demo/patchouli_books/guide/book.json"))
        assert declaration["name"] == "指南汉化"
        assert "i18n" not in declaration
        assert archive.read("demo.class") == b"unchanged class"
        assert json.loads(archive.read("assets/demo/patchouli_books/guide/en_us/entries/start.json"))["name"] == "First Steps"
    patch = tmp_path / "task/patch" / PACK_FOLDER
    assert (patch / "assets/demo/patchouli_books/guide/zh_cn/entries/start.json").is_file()
    assert json.loads((patch / "pack.mcmeta").read_bytes())["pack"]["pack_format"] == 15
    icon = (patch / "pack.png").read_bytes()
    assert icon == (RESOURCES / "pack.png").read_bytes()
    assert icon.startswith(b"\x89PNG\r\n\x1a\n")
    assert any(f["path"] == PACK_FOLDER + "/pack.png" and f["kind"] == "patchouli-resourcepack-icon"
               for f in manifest["files"])
    assert any(f.get("kind") == "patchouli-mod-archive" for f in manifest["files"])


def test_existing_language_keys_are_reused_without_new_keys(tmp_path):
    root = tmp_path / "game"
    files = book_files(declaration={"name": "demo.guide.name", "landing_text": "demo.guide.landing",
        "use_resource_pack": True, "i18n": True}, pages=[{"type": "patchouli:text", "text": "demo.guide.body"}])
    files["assets/demo/lang/en_us.json"] = {"demo.guide.name": "Book title", "demo.guide.landing": "Landing",
                                          "demo.guide.body": "Read body", "unrelated": "Unused"}
    files["assets/demo/lang/zh_cn.json"] = {"demo.guide.name": "已有书名"}
    mod(root, files)
    result = scan(root)
    refs = [e for e in result.entries if e.document.endswith("/en_us.json")]
    assert {e.source for e in refs} == {"Landing", "Read body"}
    assert not any(e.source.startswith("demo.guide.") for e in result.entries)
    assert not any(d.kind == "patchouli-book" for d in result.documents)
    translated(result)
    build_patch(result, tmp_path / "task")
    output = tmp_path / "task/patch" / PACK_FOLDER / "assets/demo/lang/zh_cn.json"
    assert set(json.loads(output.read_bytes())) == {"demo.guide.landing", "demo.guide.body"}
    entry = tmp_path / "task/patch" / PACK_FOLDER / "assets/demo/patchouli_books/guide/zh_cn/entries/start.json"
    assert json.loads(entry.read_bytes())["pages"][0]["text"] == "demo.guide.body"


def test_unresolved_book_key_is_blocked_and_document_remains_visible(tmp_path):
    root = tmp_path / "game"
    files = book_files(declaration={"name": "book.apotheosis.name", "landing_text": "Welcome",
                                   "use_resource_pack": True})
    files["assets/demo/lang/en_us.json"] = '{"#comment":"a","#comment":"b","book.apotheosis.name":"Chronicle"}'
    mod(root, files)
    result = scan(root)
    assert "book.apotheosis.name" not in {e.source for e in result.entries}
    document = next(d for d in result.documents if d.kind == "patchouli-book")
    assert any("book.apotheosis.name" in message for message in resource_warnings(result)[document.path])
    assert result.metadata["patchouli"]["diagnostics"][0]["reason"] == "unresolved-language-key"
    translated(result)
    build_patch(result, tmp_path / "task")
    with zipfile.ZipFile(tmp_path / "task/patch/mods/demo.jar") as archive:
        data = json.loads(archive.read("data/demo/patchouli_books/guide/book.json"))
        assert data["name"] == "book.apotheosis.name"
        assert data["landing_text"] != "Welcome"


def test_book_with_only_unresolved_keys_has_visible_zero_entry_document(tmp_path):
    root = tmp_path / "game"
    mod(root, {"data/demo/patchouli_books/guide/book.json": {"name": "book.demo.name", "use_resource_pack": True}})
    result = scan(root)
    assert len(result.documents) == 1 and not result.entries
    assert resource_warnings(result)


def test_unresolved_old_task_declaration_is_not_exported(tmp_path):
    from mcpacklocalizer.core.pack.extraction import resource_exclusions
    root = tmp_path / "game"
    mod(root, book_files())
    result = scan(root)
    document = next(d for d in result.documents if d.kind == "patchouli-book")
    entry = next(e for e in result.entries if e.document == document.path)
    entry.source = "book.apotheosis.name"
    translated(result)
    assert document.path in resource_exclusions(result)
    build_patch(result, tmp_path / "task")
    assert not (tmp_path / "task/patch/mods/demo.jar").exists()


def test_manual_exclusion_rebuilds_shared_archive_without_excluded_translation(tmp_path):
    root = tmp_path / "game"
    files = book_files(declaration={"name": "Guide", "use_resource_pack": False})
    original = mod(root, files).read_bytes()
    result = scan(root)
    translated(result)
    task = tmp_path / "task"
    build_patch(result, task)
    book = next(d for d in result.documents if d.kind == "patchouli-book")
    result.metadata["manual_excluded_resources"] = [book.path]
    build_patch(result, task)
    with zipfile.ZipFile(task / "patch/mods/demo.jar") as archive:
        assert json.loads(archive.read("data/demo/patchouli_books/guide/book.json"))["name"] == "Guide"
        assert json.loads(archive.read("assets/demo/patchouli_books/guide/zh_cn/entries/start.json"))["name"] != "First Steps"
    result.metadata["manual_excluded_resources"] = [d.path for d in result.documents]
    build_patch(result, task)
    assert not (task / "patch/mods/demo.jar").exists()
    assert (root / "mods/demo.jar").read_bytes() == original


def test_target_book_files_are_preserved_and_added_targets_invalidate_snapshot(tmp_path):
    root = tmp_path / "game"
    files = book_files()
    existing = "assets/demo/patchouli_books/guide/zh_cn/entries/start.json"
    files[existing] = {"name": "已有中文", "pages": []}
    mod(root, files)
    result = scan(root)
    assert "First Steps" not in {e.source for e in result.entries}
    assert result.metadata["patchouli"]["preserved"]
    put(root, "resources/" + existing, {"name": "新覆盖"})
    with pytest.raises(ValueError, match="清单已变更"):
        validate_sources(result)


def test_external_books_have_direct_targets_and_no_archive_changes(tmp_path):
    root = tmp_path / "game"
    original = '{\n "name": "Book", "icon": "minecraft:book", "pages": ["Hello"]\n}\n'
    put(root, "patchouli_books/guide/book.json", {"name": "Book", "landing_text": "Welcome"})
    put(root, "patchouli_books/guide/en_us/entries/a.json", original)
    result = scan(root)
    translated(result)
    build_patch(result, tmp_path / "task")
    out = tmp_path / "task/patch/patchouli_books/guide/zh_cn/entries/a.json"
    assert '"icon": "minecraft:book"' in out.read_text(encoding="utf-8")
    assert not (tmp_path / "task/patch/resourcepacks").exists()
    assert (root / "patchouli_books/guide/en_us/entries/a.json").read_text(encoding="utf-8") == original


def test_templates_follow_text_bindings_and_preserve_resource_and_derived_inputs(tmp_path):
    root = tmp_path / "game"
    files = book_files(pages=[{"type": "demo:machine", "headline": "Machine", "body": "Use power",
                              "ingredient": "demo:machine", "shared": "Shared ID", "included.message": "Nested text"}])
    base = "assets/demo/patchouli_books/guide/en_us/templates/"
    files[base + "machine.json"] = {"components": [
        {"type": "patchouli:header", "text": "#headline"}, {"type": "patchouli:text", "text": "#body"},
        {"type": "patchouli:text", "text": "Produces #ingredient->iname#."},
        {"type": "patchouli:text", "text": "#shared"}, {"type": "patchouli:item", "item": "#shared"}],
        "include": [{"template": "demo:child", "as": "included"}]}
    files[base + "child.json"] = {"components": [{"type": "patchouli:text", "text": "#message"},
        {"type": "patchouli:tooltip", "tooltip": ["Static hint"]}]}
    mod(root, files)
    result = scan(root)
    sources = {e.source for e in result.entries}
    assert {"Machine", "Use power", "Nested text", "Static hint", "Produces #ingredient->iname#."}.issubset(sources)
    assert not {"#body", "#headline", "demo:machine", "Shared ID"}.intersection(sources)
    assert any("非文本" in w for w in result.warnings)


def test_unknown_page_does_not_prevent_builtin_pages_and_reports_incomplete(tmp_path):
    root = tmp_path / "game"
    mod(root, book_files(pages=[{"type": "demo:java_page", "text": "Unknown semantics"}, "Known text"]))
    result = scan(root)
    assert "Known text" in {e.source for e in result.entries}
    assert "Unknown semantics" not in {e.source for e in result.entries}
    assert not result.metadata["patchouli"]["complete"]


def test_tooltip_text_is_extracted_separately_and_composed_without_corrupting_controls(tmp_path):
    root = tmp_path / "game"
    text = "$(t:Useful hint)Hover here$(/t)$(br2)$(l:demo:start)Read$(/l)$()"
    mod(root, book_files(pages=[{"type": "patchouli:text", "text": text}]))
    result = scan(root)
    entry = next(e for e in result.entries if e.source == text)
    tooltip = next(e for e in result.entries if e.source == "Useful hint")
    entry.translation = text.replace("Hover here", "鼠标悬停").replace("Read", "阅读")
    tooltip.translation = "有用提示"
    document = next(d for d in result.documents if d.path == entry.document)
    output = json.loads(render_document(document, [entry, tooltip]))["pages"][0]["text"]
    assert "$(t:有用提示)鼠标悬停$(/t)" in output
    assert "$(l:demo:start)阅读$(/l)$()" in output
    with pytest.raises(ValueError):
        validate_entry(entry, "丢失格式", True)
    with pytest.raises(ValueError, match="右括号"):
        validate_entry(tooltip, "提示)注入")


def test_control_masking_uses_existing_translator_and_restores_custom_macros():
    class Model:
        def translate(self, source, context):
            assert "$(" not in source and "<strong>" not in source
            return source.replace("Read", "阅读")

    source = "<strong>Read$()$(br2)#item->iname#"
    assert translate_text(Model(), source, "context", ["<strong>"]) == source.replace("Read", "阅读")


def test_nested_jar_export_and_signed_declaration_are_handled(tmp_path):
    root = tmp_path / "game"
    mod(root, {"META-INF/jarjar/core.jar": zip_bytes(book_files()), "outer.class": b"outer"})
    result = scan(root)
    translated(result)
    build_patch(result, tmp_path / "task")
    with zipfile.ZipFile(tmp_path / "task/patch/mods/demo.jar") as outer:
        assert outer.read("outer.class") == b"outer"
        with zipfile.ZipFile(io.BytesIO(outer.read("META-INF/jarjar/core.jar"))) as inner:
            assert json.loads(inner.read("data/demo/patchouli_books/guide/book.json"))["name"] == "指南汉化"
    mod(root, {**book_files(), "META-INF/DEMO.SF": "signature"})
    result = scan(root)
    assert not any(d.kind == "patchouli-book" for d in result.documents)
    assert any("已签名" in warning for warning in result.warnings)


def test_scopes_are_combined_without_duplicate_kubejs_patchouli_text(tmp_path):
    root = tmp_path / "game"
    put(root, "config/ftbquests/quests/chapters/a.snbt", '{id:"a",title:"Quest"}')
    put(root, "kubejs/assets/demo/custom/a.json", {"text": "Kube text"})
    for name, data in book_files().items():
        put(root, "kubejs/" + name, data)
    assert {e.source for e in scan(root, ["resources"]).entries} == {"Quest"}
    assert "Kube text" in {e.source for e in scan(root, ["kubejs"]).entries}
    result = scan(root, ["resources", "kubejs", "patchouli"])
    assert len({d.path for d in result.documents}) == len(result.documents)
    assert {"Quest", "Kube text", "First Steps"}.issubset(e.source for e in result.entries)
    assert not any(d.kind == "kubejs-asset-text" and "patchouli_books" in d.path for d in result.documents)


def test_loose_language_targets_keep_existing_keys_and_translate_tooltips(tmp_path):
    root = tmp_path / "game"
    mod(root, book_files(declaration={"name": "demo.name", "landing_text": "Welcome",
                                    "use_resource_pack": True, "i18n": True}))
    put(root, "kubejs/assets/demo/lang/en_us.json", {"demo.name": "$(t:Book hint)Book$(/t)", "unused": "Unused"})
    put(root, "kubejs/assets/demo/lang/zh_cn.json", {"existing": "已有中文"})
    result = scan(root)
    translated(result)
    tip = next(e for e in result.entries if e.patchouli.get("role") == "tooltip")
    tip.translation = "手册提示"
    build_patch(result, tmp_path / "task")
    values = json.loads((tmp_path / "task/patch/kubejs/assets/demo/lang/zh_cn.json").read_bytes())
    assert values["existing"] == "已有中文"
    assert "$(t:手册提示)" in values["demo.name"]
    assert "unused" not in values


def test_enabled_resource_pack_overrides_and_case_insensitive_source_locale(tmp_path):
    root = tmp_path / "game"
    mod(root, book_files())
    path = "assets/demo/patchouli_books/guide/EN_US/entries/start.json"
    put(root, "resourcepacks/custom/" + path, {"name": "Overridden", "pages": ["Overridden text"]})
    put(root, "options.txt", 'resourcePacks:["vanilla","file/custom"]')
    result = scan(root)
    assert "Overridden text" in {e.source for e in result.entries}
    assert "Read the guide" not in {e.source for e in result.entries}
    translated(result)
    build_patch(result, tmp_path / "task")
    assert (tmp_path / "task/patch/resourcepacks/custom/assets/demo/patchouli_books/guide/zh_cn/entries/start.json").is_file()


def test_archive_target_tampering_is_rejected_before_export(tmp_path):
    root = tmp_path / "game"
    mod(root, book_files())
    result = scan(root)
    translated(result)
    document = next(d for d in result.documents if d.kind == "patchouli-book")
    document.resource["target_member"] = "demo.class"
    with pytest.raises(ValueError, match="来源信息"):
        build_patch(result, tmp_path / "task")
    assert not (tmp_path / "task/patch").exists()


@pytest.mark.parametrize("suffix", ["json", "lang"])
def test_existing_pack_language_entry_gets_book_control_and_tooltip_protection(tmp_path, suffix):
    root = tmp_path / "game"
    mod(root, book_files(declaration={"name": "demo.name", "landing_text": "Welcome", "use_resource_pack": True}))
    source = "$(t:Hint)Book$(/t)$(br2)"
    data = {"demo.name": source, "unused": "Other"} if suffix == "json" else "demo.name=" + source + "\nunused=Other\n"
    put(root, "kubejs/assets/demo/lang/en_us." + suffix, data)
    result = scan(root, ["resources", "patchouli"])
    primary = [e for e in result.entries if e.source == source]
    assert len(primary) == 1 and primary[0].patchouli
    translated(result)
    next(e for e in result.entries if e.source == "Hint").translation = "提示"
    build_patch(result, tmp_path / "task")
    output = (tmp_path / ("task/patch/kubejs/assets/demo/lang/zh_cn." + suffix)).read_text(encoding="utf-8")
    assert "$(t:提示)Book$(/t)$(br2)汉化" in output
    assert "Other汉化" in output


def test_legacy_book_content_is_written_inside_jar_and_uses_selected_source_locale(tmp_path):
    root = tmp_path / "game"
    files = {name.replace("assets/", "data/"): data for name, data in book_files(
        declaration={"name": "Guide", "landing_text": "Welcome", "use_resource_pack": False}).items()}
    files["data/demo/patchouli_books/guide/ja_jp/entries/start.json"] = {"name": "入門", "pages": ["日本語の本文"]}
    jar = mod(root, files)
    original = jar.read_bytes()
    result = scan_pack(root, source_locale="ja_jp", scope=["patchouli"], game_version="1.16.5")
    assert "日本語の本文" in {e.source for e in result.entries}
    assert "Read the guide" not in {e.source for e in result.entries}
    translated(result)
    build_patch(result, tmp_path / "task")
    with zipfile.ZipFile(tmp_path / "task/patch/mods/demo.jar") as archive:
        body = json.loads(archive.read("data/demo/patchouli_books/guide/zh_cn/entries/start.json"))
        assert body["pages"] == ["日本語の本文汉化"]
    assert not (tmp_path / "task/patch/resourcepacks").exists()
    assert jar.read_bytes() == original
