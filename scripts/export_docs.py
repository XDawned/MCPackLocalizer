# [Module: scripts.export_docs] [Status: 已完成] [Brief: 导出内嵌截图和样式的离线使用说明]
from __future__ import annotations

import argparse
import base64
import sys
from html import escape
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/RELEASING.md"
MIME_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".webp": "image/webp", ".svg": "image/svg+xml", ".bmp": "image/bmp",
}
STYLE = """
:root { color-scheme: light; font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
        color: #243047; background: #f3f6fa; line-height: 1.8; }
* { box-sizing: border-box; }
body { margin: 0; }
main { max-width: 1000px; margin: 32px auto; padding: 36px 48px; background: white;
       border: 1px solid #e0e6ef; border-radius: 16px; }
h1, h2, h3 { line-height: 1.4; color: #17233a; scroll-margin-top: 24px; }
h1 { font-size: 2rem; margin-top: 0; }
h2 { margin-top: 2.5rem; padding-bottom: 8px; border-bottom: 1px solid #e0e6ef; }
h3 { margin-top: 1.8rem; }
a { color: #0067b8; text-underline-offset: 3px; overflow-wrap: anywhere; }
nav { padding: 16px 24px; background: #f3f6fa; border-radius: 10px; margin: 24px 0; }
nav ul { list-style: none; padding: 0; margin: 8px 0 0; }
nav li.subsection { padding-left: 20px; }
blockquote { margin: 20px 0; padding: 1px 20px; border-left: 4px solid #0067b8; background: #eef6ff; }
img { display: block; max-width: 100%; height: auto; margin: 20px 0;
      border: 1px solid #e0e6ef; border-radius: 8px; }
code { font-family: Consolas, monospace; background: #eef1f6; border-radius: 4px; padding: 2px 5px; }
pre { padding: 16px; background: #eef1f6; overflow-x: auto; border-radius: 8px; }
pre code { padding: 0; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 8px 12px; border: 1px solid #e0e6ef; text-align: left; }
footer { margin-top: 40px; padding-top: 16px; border-top: 1px solid #e0e6ef; color: #68758a; font-size: .9rem; }
@media (max-width: 640px) { main { margin: 0; padding: 24px 18px; border: 0; border-radius: 0; } }
@media print { :root { background: white; } main { margin: 0; padding: 0; border: 0; }
               nav { display: none; } img { break-inside: avoid; } }
"""


def image_data(source: Path, reference: str) -> str:
    """图片必须来自文档目录，缺图时阻止生成不完整的发行说明。"""
    url = urlsplit(reference)
    if url.scheme or url.netloc or url.query or url.fragment:
        raise ValueError(f"离线说明仅支持本地图片：{reference}")
    path = (source.parent / unquote(url.path)).resolve()
    if not path.is_relative_to(source.parent.resolve()):
        raise ValueError(f"图片必须位于文档目录内：{reference}")
    mime = MIME_TYPES.get(path.suffix.lower())
    if not mime:
        raise ValueError(f"不支持的图片格式：{reference}")
    if not path.is_file():
        raise ValueError(f"使用说明缺少图片：{reference}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def export_document(source: Path, destination: Path) -> Path:
    parser = MarkdownIt("js-default")
    tokens = parser.parse(source.read_text(encoding="utf-8-sig"))
    contents = []
    for index, token in enumerate(tokens):
        if token.type == "heading_open" and token.tag in {"h2", "h3"}:
            anchor = f"section-{len(contents) + 1}"
            token.attrSet("id", anchor)
            title = tokens[index + 1].content
            css_class = ' class="subsection"' if token.tag == "h3" else ""
            contents.append(f'<li{css_class}><a href="#{anchor}">{escape(title)}</a></li>')

    def embed_images(items):
        for token in items:
            if token.type == "image":
                token.attrSet("src", image_data(source, token.attrGet("src") or ""))
            if token.children:
                embed_images(token.children)

    embed_images(tokens)
    body = parser.renderer.render(tokens, parser.options, {})
    navigation = '<nav aria-label="目录"><strong>目录</strong><ul>' + "".join(contents) + "</ul></nav>"
    # 目录紧跟标题，保留 Markdown 中其它内容的顺序。
    body = body.replace("</h1>", "</h1>\n" + navigation, 1)
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MCPackLocalizer · 使用说明</title>
<style>{STYLE}</style>
</head>
<body><main>
{body}
<footer>MCPackLocalizer 使用说明</footer>
</main></body>
</html>
"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(page, encoding="utf-8")
    return destination


def main():
    # Windows 的重定向输出可能使用 cp1252，中文日志统一写为 UTF-8。
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="将使用说明与截图导出为单文件离线 HTML")
    parser.add_argument("--source", type=Path, default=SOURCE, help="Markdown 源文档")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/使用说明.html", help="HTML 输出路径")
    args = parser.parse_args()
    export_document(args.source, args.output)
    print(f"已生成离线使用说明：{args.output}", flush=True)


if __name__ == "__main__":
    main()
