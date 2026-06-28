import logging
import re
from typing import Dict, List

from .base_parser import BaseParser

try:
    from ..services.translation_metadata import is_probably_i18n_key
except ImportError:
    from src.services.translation_metadata import is_probably_i18n_key  # type: ignore

logger = logging.getLogger(__name__)
TEXT_CALL_PATTERN = re.compile(
    r"\bText\.(?P<method>[A-Za-z_][A-Za-z0-9_]*)\s*\(\s*(?P<quoted>\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')",
    re.MULTILINE,
)
NON_LITERAL_METHODS = {"translate", "translatable", "keybind"}


class KubejsJsParser(BaseParser):
    """提取 KubeJS 脚本中的 `Text.xxx("...")` 文本字面量。"""

    def can_parse(self, file_path: str) -> bool:
        normalized = file_path.replace("\\", "/").lower()
        return normalized.endswith(".js") and "/kubejs/" in f"/{normalized}"

    def has_candidates(self, file_path: str) -> bool:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return bool(TEXT_CALL_PATTERN.search(f.read()))
        except Exception:
            return False

    def extract(self, file_path: str) -> Dict[str, str]:
        result: Dict[str, str] = {}
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            for entry in self._collect_entries(content):
                result[entry["entry_key"]] = entry["value"]
        except Exception as exc:
            logger.warning("Failed to parse KubeJS file %s: %s", file_path, exc)
        return result

    def render(self, file_path: str, translations: Dict[str, str], original_texts: Dict[str, str] | None = None) -> str:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return self.render_content(content, translations, original_texts or {})

    def render_content(self, content: str, translations: Dict[str, str], original_texts: Dict[str, str] | None = None) -> str:
        original_texts = original_texts or {}
        entries = self._collect_entries(content)
        replacements: List[tuple[tuple[int, int], str]] = []
        matched_keys: set[str] = set()

        for entry in entries:
            translated = self._resolve_translation(entry, translations, original_texts, matched_keys)
            if translated is None or translated == entry["value"]:
                continue
            replacements.append((entry["value_span"], self._quote_value(entry["quote_char"], translated)))

        rendered = content
        for span, replacement in reversed(replacements):
            start, end = span
            rendered = rendered[:start] + replacement + rendered[end:]
        return rendered

    def _collect_entries(self, content: str) -> List[dict]:
        entries: List[dict] = []
        accepted_index = 0
        for match in TEXT_CALL_PATTERN.finditer(content):
            if self._is_line_comment(content, match.start()):
                continue
            method = str(match.group("method") or "").strip()
            if method.lower() in NON_LITERAL_METHODS:
                continue
            quoted_value = match.group("quoted")
            value = self._unescape_value(quoted_value)
            if not value or is_probably_i18n_key(value):
                continue
            entries.append(
                {
                    "entry_key": f"{accepted_index:06d}:Text.{method}",
                    "value": value,
                    "value_span": match.span("quoted"),
                    "quote_char": quoted_value[0],
                }
            )
            accepted_index += 1
        return entries

    def _resolve_translation(
        self,
        entry: dict,
        translations: Dict[str, str],
        original_texts: Dict[str, str],
        matched_keys: set[str],
    ) -> str | None:
        entry_key = entry["entry_key"]
        if entry_key in translations:
            matched_keys.add(entry_key)
            return translations[entry_key]

        for key, original_text in original_texts.items():
            if key in matched_keys:
                continue
            if original_text == entry["value"] and key in translations:
                matched_keys.add(key)
                return translations[key]
        return None

    def _is_line_comment(self, content: str, index: int) -> bool:
        line_start = content.rfind("\n", 0, index) + 1
        prefix = content[line_start:index]
        return "//" in prefix

    def _unescape_value(self, quoted_value: str) -> str:
        value = quoted_value[1:-1]
        value = value.replace("\\n", "\n")
        value = value.replace("\\r", "\r")
        value = value.replace("\\t", "\t")
        value = value.replace('\\"', '"').replace("\\'", "'")
        value = value.replace("\\\\", "\\")
        return value

    def _quote_value(self, quote_char: str, value: str) -> str:
        escaped = value.replace("\\", "\\\\")
        escaped = escaped.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        if quote_char == '"':
            escaped = escaped.replace('"', '\\"')
        else:
            escaped = escaped.replace("'", "\\'")
        return f"{quote_char}{escaped}{quote_char}"
