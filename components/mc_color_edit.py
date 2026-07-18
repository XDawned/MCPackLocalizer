import re
import sys

from qfluentwidgets import TextEdit
from PyQt6.QtCore import QRegularExpression  # noqa: F401  # placeholder if needed later
from PyQt6.QtGui import (QColor, QFont, QSyntaxHighlighter, QTextCharFormat,  # noqa: F401
                          QTextCursor, QTextDocument)


class MinecraftTextFormat:
    SPEC_KEY = ("&", "§")
    TAG = {
        "0": {
            "name": "black",
            "hex": "#000000",
            "tag": "font"
        },
        "1": {
            "name": "dark_blue",
            "hex": "#0000AA",
            "tag": "font"
        },
        "2": {
            "name": "dark_green",
            "hex": "#00AA00",
            "tag": "font"
        },
        "3": {
            "name": "dark_aqua",
            "hex": "#00AAAA",
            "tag": "font"
        },
        "4": {
            "name": "dark_red",
            "hex": "#0000AA",
            "tag": "font"
        },
        "5": {
            "name": "dark_purple",
            "hex": "#AA00AA",
            "tag": "font"
        },
        "6": {
            "name": "gold",
            "hex": "#FFAA00",
            "tag": "font"
        },
        "7": {
            "name": "gray",
            "hex": "#AAAAAA",
            "tag": "font"
        },
        "8": {
            "name": "dark_gray",
            "hex": "#555555",
            "tag": "font"
        },
        "9": {
            "name": "blue",
            "hex": "#5555FF",
            "tag": "font"
        },
        "a": {
            "name": "green",
            "hex": "#55FF55",
            "tag": "font"
        },
        "b": {
            "name": "aqua",
            "hex": "#55FFFF",
            "tag": "font"
        },
        "c": {
            "name": "red",
            "hex": "#FF5555",
            "tag": "font"
        },
        "d": {
            "name": "light_purple",
            "hex": "#FF55FF",
            "tag": "font"
        },
        "e": {
            "name": "yellow",
            "hex": "#FFFF55",
            "tag": "font"
        },
        "f": {
            "name": "white",
            "hex": "#FFFFFF",
            "tag": "font"
        },
        "l": {
            "name": "Bold",
            "tag": "b"
        },
        "m": {
            "name": "",
            "tag": "em"
        },
        "n": {
            "name": "Underline",
            "tag": "u"
        },
        "o": {
            "name": "Italic",
            "tag": "s"
        },
        "r": {
            "name": "Reset",
            "hex": "#000000",
            "tag": "font"
        }
    }

    def trans_html(self, text: str) -> str:
        res = ''
        length = len(text)
        current_index = 0
        end_tag = ''
        while current_index < length:
            s = text[current_index]
            if s in self.SPEC_KEY and current_index != length - 1:
                s_n = text[current_index + 1].lower()
                if self.TAG.get(s_n):
                    tag = self.TAG[s_n]
                    if tag.get('hex'):
                        res += end_tag
                        end_tag = f"</{tag['tag']}>"
                        res += f"<font color=\"{tag['hex']}\">"
                    else:
                        end_tag += f"</{tag['tag']}>"
                        res += f"<{tag['tag']}>"
            res += s
            current_index += 1
        res += end_tag
        return res


class McColorEdit(TextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mc_text_format = MinecraftTextFormat()
        self.color_format = True

    def keyReleaseEvent(self, event):
        self.fresh_color()

    def fresh_color(self):
        if self.color_format:
            cursor = self.textCursor()
            position = cursor.position()
            self.setHtml(self.mc_text_format.trans_html((self.toPlainText())))
            cursor.setPosition(position)
            self.setTextCursor(cursor)