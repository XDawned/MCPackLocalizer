# [Module: tests.release_docs] [Status: 已完成] [Brief: 验证离线说明的截图完整性与缺图构建失败]
import base64
from html.parser import HTMLParser

import pytest

from scripts.export_docs import SOURCE, export_document


class Images(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.sources.append(dict(attrs)["src"])


def test_user_guide_embeds_all_screenshots_with_original_bytes(tmp_path):
    destination = export_document(SOURCE, tmp_path / "移动后的软件目录/使用说明.html")
    page = destination.read_text(encoding="utf-8")
    images = Images()
    images.feed(page)
    expected = {path.read_bytes() for path in (SOURCE.parent / "assets").glob("*.png")}
    assert images.sources
    assert all(source.startswith("data:image/png;base64,") for source in images.sources)
    assert {base64.b64decode(source.split(",", 1)[1], validate=True) for source in images.sources} == expected
    assert '<html lang="zh-CN">' in page
    assert '<meta charset="utf-8">' in page
    assert 'href="#section-1"' in page and 'id="section-1"' in page
    assert "<script" not in page and '<link ' not in page
    assert list(destination.parent.iterdir()) == [destination]


def test_export_preserves_markdown_and_images_inside_ordered_lists(tmp_path):
    source = tmp_path / "使用说明.md"
    image = tmp_path / "中文 截图.png"
    image.write_bytes(b"example screenshot")
    source.write_text(
        '# 使用说明\n\n## 接口\n\n1. 点击 **添加**，选择 `API`。\n\n'
        '   ![截图](中文%20截图.png)\n\n> 注意\n\n```text\n![示例](不存在.png)\n```\n', encoding="utf-8",
    )
    destination = export_document(source, tmp_path / "输出/使用说明.html")
    page = destination.read_text(encoding="utf-8")
    assert "<ol>" in page and "<strong>添加</strong>" in page and "<code>API</code>" in page
    assert "<blockquote>" in page and "![示例](不存在.png)" in page
    images = Images()
    images.feed(page)
    assert len(images.sources) == 1
    assert base64.b64decode(images.sources[0].split(",", 1)[1]) == image.read_bytes()


@pytest.mark.parametrize("reference, message", [
    ("assets/missing.png", "缺少图片"),
    ("https://example.test/image.png", "仅支持本地图片"),
    ("../outside.png", "必须位于文档目录内"),
])
def test_incomplete_offline_guide_stops_export(tmp_path, reference, message):
    source = tmp_path / "说明.md"
    source.write_text(f"# 使用说明\n\n![截图]({reference})\n", encoding="utf-8")
    destination = tmp_path / "使用说明.html"
    with pytest.raises(ValueError, match=message):
        export_document(source, destination)
    assert not destination.exists()
