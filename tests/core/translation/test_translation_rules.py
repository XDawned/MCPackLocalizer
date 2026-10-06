import json

import pytest

from mcpacklocalizer.core.translation.glossary import Glossary
from mcpacklocalizer.core.translation.rules import NoTranslate


def test_longest_literal_terms_case_and_boundaries():
    rule = NoTranslate("Create\nCreate Crafts\nC++\nCreate")
    masked, mapping = rule.mask("Create Crafts, Create, CreateCraft, create and C++")
    assert list(mapping.values()) == ["Create Crafts", "Create", "C++"]
    assert "CreateCraft, create" in masked
    assert rule.restore(masked, mapping) == "Create Crafts, Create, CreateCraft, create and C++"


def test_no_translate_does_not_mask_inside_resource_ids_variables_or_urls():
    source = "Use minecraft:Create and ${Create} at https://example.test/Create then Create"
    masked, mapping = NoTranslate("Create").mask(source)
    assert len(mapping) == 1
    assert "minecraft:Create" in masked and "${Create}" in masked and "https://example.test/Create" in masked


def test_missing_or_duplicated_no_translate_marker_is_rejected():
    rule = NoTranslate("Create")
    masked, mapping = rule.mask("Use Create")
    marker = next(iter(mapping))
    for bad in (masked.replace(marker, "创造"), masked + marker):
        with pytest.raises(ValueError):
            rule.restore(bad, mapping)
    with pytest.raises(ValueError):
        rule.validate("Use Create", "使用创造")


def test_inline_overrides_replace_ambiguous_preset_and_can_disable(memory_files):
    from pathlib import Path
    memory_files["C:/preset.json"] = json.dumps({"Iron Ingot": ["铁锭", "铁铸锭"], "Gold Ingot": ["金锭"]})
    glossary = Glossary(Path("C:/preset.json"), inline='{"Iron Ingot":"铁锭", "Gold Ingot":[]}')
    assert glossary.find("Iron Ingot and Gold Ingot") == [("Iron Ingot", "铁锭")]
