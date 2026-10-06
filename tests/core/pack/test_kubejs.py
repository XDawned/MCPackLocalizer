import json

import pytest

from mcpacklocalizer.core.formats.rendering import render_document
from mcpacklocalizer.core.kubejs.javascript import MARKER, decode_js, encode_js, parse_script, split_translation
from mcpacklocalizer.core.pack.extraction import scan_pack


def pack_file(root, relative, text):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")
    return path


def script_scan(root, text):
    pack_file(root, "kubejs/server_scripts/text.js", text)
    return scan_pack(root, scope="kubejs")


def test_js_user_examples_and_language_keys(tmp_path):
    source = '''
Text.of("§7Rarely spawns on kill");
event.server.tell(Text.red('This box will be removed'));
event.player.setStatusMessage(Text.red("You cannot use this item!"));
player.sendSystemMessage(Text.literal("Only works in the overworld").red(), true);
StartupEvents.registry("item", allthemods => {
  allthemods.create("ritual_dummy/honeycomb", "occultism:ritual_dummy")
    .pentacleType("craft").displayName("Ritual: Craft Honeycombs")
    .ritualTooltip("A Foliot will act as a bee.");
  allthemods.create("shard").unstackable().texture("kubejs:item/shard")
    .tooltip("Eat to increase spell power.").tooltip("§8Does not stack.").rarity("rare");
});
ItemEvents.tooltip(e => {
  e.add(['mod:engine'], '§4Disabled item');
  e.add(['mod:blade'], ['Upgradeable sword', Text.gold('Additional information')]);
});
RecipeViewerEvents.addInformation('fluid', e => e.add('mod:fluid', ['Made in the end.']));
RecipeViewerEvents.addInformation('item', e => e.add('sfm:xp_shard', [Text.translate('ftb.jei.info.sfm.xp_shard')]));
src.player.tell("Unable to resolve your dimension.");
if (src.sendFailure) src.sendFailure(Text.red("Failed to find dimension."));
'''
    scan = script_scan(tmp_path, source)
    assert not scan.warnings
    values = {entry.source for entry in scan.entries}
    assert len(values) == 14
    assert {"§7Rarely spawns on kill", "Ritual: Craft Honeycombs", "A Foliot will act as a bee.",
            "Eat to increase spell power.", "Upgradeable sword", "Made in the end."}.issubset(values)
    assert not any("ftb.jei" in value or "mod:fluid" in value or value == "rare" for value in values)
    assert scan.to_dict()["schema_version"] >= 2


def test_legacy_new_tooltips_and_receivers(tmp_path):
    scan = script_scan(tmp_path, '''
onEvent('client.item_tooltip', renamed => renamed.add("Old tooltip"));
onEvent('item.tooltip', renamed => renamed.addToAll("All tooltip"));
ItemEvents.modifyTooltips(e => {
 e.add('mod:a', {shift: true}, 'Shift tooltip');
 e.modify('mod:a', b => { b.add('Builder tooltip'); b.insert(0, 'Inserted text'); b.removeText('Do not translate'); });
});
ItemEvents.dynamicTooltips('mod:dynamic', renamed => renamed.add('Dynamic tooltip'));
ItemEvents.tooltip(e => e.addAdvanced('mod:a', (stack, advanced, text) => text.add(1, 'Advanced tooltip')));
REIEvents.information(e => e.addItem('mod:a', 'Information title', ['Information description']));
const p = event.player; p.tell('Alias message');
''')
    assert {entry.source for entry in scan.entries} == {
        "Old tooltip", "All tooltip", "Shift tooltip", "Builder tooltip", "Inserted text",
        "Dynamic tooltip", "Advanced tooltip", "Information title", "Information description", "Alias message"}


def test_nontext_api_shadowing_and_mixed_use_constants_are_preserved(tmp_path):
    scan = script_scan(tmp_path, '''
const msg = "Open";
player.tell(msg);
if (mode === msg) console.log('debug');
ServerEvents.recipes(e => e.add('mod:item', 'Not display text'));
function custom(Text) { Text.of('Custom API'); }
function Text() {} Text.of('Shadowed global');
const mutable = 'Start'; mutable = 'Stop'; player.tell(mutable);
''')
    assert not scan.entries
    diagnostics = scan.metadata["kubejs"]["diagnostics"]
    assert any("共享文本变量" in record["reason"] for record in diagnostics)
    assert any("不可变文本" in record["reason"] for record in diagnostics)


def test_template_concat_constants_and_exact_rewrite(tmp_path):
    source = '''// 中文 emoji 🐝\r\nconst msg = "Do not use this item";\r\nplayer.tell(msg);\r\nplayer.tell(`You received ${count} items from ${sender.name}.`);\r\nplayer.tell("You got " + count + " items");\r\n'''
    scan = script_scan(tmp_path, source)
    assert len(scan.entries) == 3
    for entry in scan.entries:
        slots = entry.script["slots"]
        markers = entry.script["markers"]
        translations = [f"译文{index}" if slot["value"].strip() else slot["value"] for index, slot in enumerate(slots)]
        entry.translation = "".join(value + (markers[index] if index < len(markers) else "")
                                    for index, value in enumerate(translations))
    output = render_document(scan.documents[0], scan.entries).decode("utf-8")
    assert "${count}" in output and "${sender.name}" in output
    assert ' + count + ' in output
    assert "player.tell(msg)" in output and "// 中文 emoji 🐝\r\n" in output
    parse_script(output)
    scan.entries[1].translation = scan.entries[1].translation.replace(scan.entries[1].script["markers"][0], "")
    with pytest.raises(ValueError, match="占位符"):
        render_document(scan.documents[0], scan.entries)


def test_translate_keys_fallback_and_component_object(tmp_path):
    scan = script_scan(tmp_path, '''
Text.translate('key.only');
Text.translatable('key.with', Text.of('Visible argument'));
Text.translateWithFallback('key.fallback', 'Fallback text');
Text.of({text:'Object text', extra:[{translate:'key.extra'}, {text:'Extra text'}], clickEvent:{action:'run_command',value:'say English'}});
''')
    assert {e.source for e in scan.entries} == {"Visible argument", "Fallback text", "Object text", "Extra text"}


def test_json_components_language_files_and_scope(tmp_path):
    pack_file(tmp_path, "config/ftbquests/quests/chapters/a.snbt", '{id:"chapter",title:"Chapter"}')
    pack_file(tmp_path, "kubejs/assets/test/lang/en_us.json", '{"key":"Language text"}')
    pack_file(tmp_path, "kubejs/assets/test/tips/a.json", json.dumps({
        "tip": {"text": "Tip text"}, "description": {"text": "Description"}, "name": {"text": "Name"},
        "texture": "mod:texture", "conditions": [{"text": "Not a component"}],
        "component": {"translate": "key", "extra": [{"text": "Extra"}],
                      "clickEvent": {"action": "run_command", "value": "say Hello"}}}))
    scan = scan_pack(tmp_path, scope="kubejs")
    assert {e.source for e in scan.entries} == {"Language text", "Tip text", "Description", "Name", "Extra"}
    assert {d.kind for d in scan.documents} == {"pack-lang", "kubejs-asset-text"}
    assert "Chapter" in {e.source for e in scan_pack(tmp_path).entries}
    assert {e.source for e in scan_pack(tmp_path, scope="resources").entries} == {"Chapter", "Language text"}


def test_rewrite_escapes_template_injection_and_snapshot_tampering(tmp_path):
    scan = script_scan(tmp_path, "player.tell(`Original \\${danger()}`); player.tell('Second');")
    scan.entries[0].translation = "引用` ${danger()} \\ 🐝"
    scan.entries[1].translation = "引号'与换行\n下一行"
    output = render_document(scan.documents[0], scan.entries).decode("utf-8")
    assert "\\${danger()}" in output and "\\`" in output
    parse_script(output)
    scan.entries[0].script["slots"][0]["start"] += 1
    with pytest.raises(ValueError, match="快照"):
        render_document(scan.documents[0], scan.entries)


def test_syntax_error_and_target_language_do_not_trigger_translation(tmp_path):
    scan = script_scan(tmp_path, 'player.tell("Already Chinese 中文");')
    assert scan.entries
    scan = script_scan(tmp_path, 'player.tell("已汉化文字");')
    assert not scan.entries
    scan = script_scan(tmp_path, 'player.tell("broken);')
    assert not scan.entries and any("语法错误" in warning for warning in scan.warnings)


def test_slot_order_and_protected_codes_are_strict():
    marker = "{{MCPL_123456abcdef_0}}"
    assert MARKER.fullmatch(marker)
    assert split_translation("§7Hello " + marker + " world", "§7你好 " + marker + " 世界") == ["§7你好 ", " 世界"]
    with pytest.raises(ValueError):
        split_translation("§7Hello " + marker + " world", "你好 " + marker + " 世界")
    with pytest.raises(ValueError):
        split_translation("Hello " + marker + " world", "你好 世界")


def test_js_string_encoding_roundtrip_preserves_escapes_and_unicode():
    value = "中文 🐝 引号'\" 反斜杠\\ 换行\n${name}`"
    for quote in ('"', "'", "`"):
        encoded = encode_js(value, quote)
        body = encoded if quote == "`" else encoded[1:-1]
        assert decode_js(body) == value
    assert decode_js(r"\uD83D\uDC1D") == "🐝"
    assert decode_js(r"\xA7aHello") == "§aHello"
    with pytest.raises(ValueError):
        decode_js(r"\012")
