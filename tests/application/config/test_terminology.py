import json
from types import SimpleNamespace

import pytest

from mcpacklocalizer.application.config.terminology import GlossaryCatalog


def preset(mocker, memory_files):
    mocker.patch("pathlib.Path.stat", return_value=SimpleNamespace(st_mtime_ns=1, st_size=100))
    data = {f"Item {i}": [f"物品{i}"] for i in range(1050)}
    memory_files["C:/preset.json"] = json.dumps(data)
    return GlossaryCatalog()


def test_only_requested_page_is_returned_and_catalog_is_cached(mocker, memory_files):
    catalog = preset(mocker, memory_files)
    first = catalog.query("C:/preset.json", "", "{}", page=0, size=100)
    assert len(first["rows"]) == 100 and first["total"] == 1050
    read = mocker.patch("pathlib.Path.read_text", side_effect=AssertionError("unexpected reread"))
    last = catalog.query("C:/preset.json", "", "{}", page=10, size=100)
    assert len(last["rows"]) == 50 and last["rows"][0][0] == "Item 1000"
    read.assert_not_called()


def test_search_and_pagination_include_effective_overrides(mocker, memory_files):
    catalog = preset(mocker, memory_files)
    result = catalog.query("C:/preset.json", "", '{"Item 1":"自定义名称"}', search="自定义", size=50)
    assert result["rows"] == [("Item 1", "自定义名称")]
    result = catalog.query("C:/preset.json", "", '{"Item 1":"", "New":"新词"}', custom=True)
    assert result["total"] == 2 and result["rows"] == [("Item 1", ""), ("New", "新词")]


def test_custom_only_query_never_loads_large_preset(mocker):
    mocker.patch("pathlib.Path.stat", side_effect=AssertionError("must not load preset"))
    assert GlossaryCatalog().query("C:/huge.json", "", '{"New":"新词"}', custom=True)["rows"] == [("New", "新词")]


def test_bad_page_size_is_rejected():
    with pytest.raises(ValueError):
        GlossaryCatalog().query("", "", "{}", size=100000)


def test_legacy_preset_empty_keys_do_not_reject_whole_catalog(mocker, memory_files):
    mocker.patch("pathlib.Path.stat", return_value=SimpleNamespace(st_mtime_ns=1, st_size=100))
    memory_files["C:/preset.json"] = '{"\\n": ["空键"], "Iron Ingot": ["铁锭"], "bad": 42}'
    result = GlossaryCatalog().query("C:/preset.json", "", "{}")
    assert result["total"] == 1 and result["rows"] == [("Iron Ingot", "铁锭")]
