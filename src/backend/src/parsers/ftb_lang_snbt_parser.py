import logging
from typing import Any, Dict, List

from .base_parser import BaseParser
from .snbt_parser import (
    detect_snbt_compact_format,
    dump_snbt_content,
    is_ftb_lang_path,
    is_string_array,
    looks_like_ftb_lang_snbt_payload,
    parse_snbt_content,
    read_snbt_file,
)

logger = logging.getLogger(__name__)


class FtbLangSnbtParser(BaseParser):
    """解析 FTB Quests 语言型 SNBT，支持高版本扁平字典与字符串数组。"""

    def can_parse(self, file_path: str) -> bool:
        if not file_path.lower().endswith(".snbt"):
            return False
        if is_ftb_lang_path(file_path):
            return True
        try:
            data = parse_snbt_content(read_snbt_file(file_path))
        except Exception:
            return False
        return looks_like_ftb_lang_snbt_payload(data, file_path)

    def extract(self, file_path: str) -> Dict[str, str]:
        result: Dict[str, str] = {}
        try:
            content = read_snbt_file(file_path)
            data = self._load_lang_payload(content, file_path=file_path)
            for entry in self._collect_entries(data):
                result[entry["entry_key"]] = entry["value"]
        except Exception as exc:
            logger.warning("Failed to parse FTB lang SNBT file %s: %s", file_path, exc)
        return result

    def render(self, file_path: str, translations: Dict[str, str], original_texts: Dict[str, str] | None = None) -> str:
        content = read_snbt_file(file_path)
        return self.render_content(content, translations, original_texts or {}, file_path=file_path)

    def render_content(
        self,
        content: str,
        translations: Dict[str, str],
        original_texts: Dict[str, str] | None = None,
        *,
        file_path: str | None = None,
    ) -> str:
        original_texts = original_texts or {}
        compact = detect_snbt_compact_format(content)
        data = self._load_lang_payload(content, file_path=file_path)
        entries = self._collect_entries(data)
        matched_keys: set[str] = set()

        for entry in entries:
            translated = self._resolve_translation(entry, translations, original_texts, matched_keys)
            if translated is None or translated == entry["value"]:
                continue
            if entry["value_type"] == "scalar":
                data[entry["base_key"]] = translated
            else:
                data[entry["base_key"]][entry["index"]] = translated

        return dump_snbt_content(data, compact=compact)

    def _load_lang_payload(self, content: str, *, file_path: str | None = None) -> dict:
        data = parse_snbt_content(content)
        if not looks_like_ftb_lang_snbt_payload(data, file_path):
            raise ValueError("SNBT payload is not recognized as FTBQ language-type SNBT")
        return data

    def _collect_entries(self, data: dict) -> List[dict]:
        entries: List[dict] = []
        for key, value in data.items():
            if isinstance(value, str):
                if self._should_skip_value(value):
                    continue
                entries.append(
                    {
                        "entry_key": key,
                        "base_key": key,
                        "value_type": "scalar",
                        "index": None,
                        "value": value,
                    }
                )
                continue

            if is_string_array(value):
                for index, item in enumerate(value):
                    if self._should_skip_value(item):
                        continue
                    entries.append(
                        {
                            "entry_key": f"{key}[{index}]",
                            "base_key": key,
                            "value_type": "array",
                            "index": index,
                            "value": item,
                        }
                    )
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

    def _should_skip_value(self, value: Any) -> bool:
        return not isinstance(value, str) or not value.strip()
