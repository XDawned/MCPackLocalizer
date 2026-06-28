import io
import logging
import re
from typing import Any, Dict, Iterable, List

import snbtlib

try:
    from nbt import nbt as python_nbt
except ImportError:
    python_nbt = None

from .base_parser import BaseParser

logger = logging.getLogger(__name__)

TRANSLATABLE_KEYS = {"title", "subtitle", "description", "text", "hover", "lore", "name", "desc"}
SKIP_SUBSTRINGS = ("{@pagebreak}", "{image:", "{@img")
URL_PATTERN = re.compile(r"https?://", re.IGNORECASE)
IMAGE_HINT_PATTERN = re.compile(r"\.(?:png|jpg|jpeg|gif|webp)\b", re.IGNORECASE)
SPECIAL_EVENT_PATTERN = re.compile(r'\{\\"')
RESOURCE_ID_PATTERN = re.compile(r"^#?[a-z0-9_.-]+:[a-z0-9_./-]+$", re.IGNORECASE)
LEGACY_COMPACT_PATTERN = re.compile(r'\",$', re.MULTILINE)
FTBQ_LANG_KEY_PATTERN = re.compile(
    r"^(?:quest|chapter|chapter_group|reward_table|file)\.[0-9A-F]{8,32}(?:\.[A-Za-z0-9_]+)+$",
    re.IGNORECASE,
)
GENERIC_DOTTED_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_:-]+(?:\.[A-Za-z0-9_:-]+){2,}$")
LIST_ANCHOR_CANDIDATES = (
    (("id",), "id"),
    (("filename",), "filename"),
    (("entity",), "entity"),
    (("advancement",), "advancement"),
    (("item", "id"), "item"),
    (("icon", "id"), "icon"),
    (("fluid", "id"), "fluid"),
)
SCALAR_VALUE_TYPES = (str, int, float)


def normalize_snbt_path(file_path: str | None) -> str:
    return str(file_path or "").replace("\\", "/").lower()


def is_ftb_lang_path(file_path: str | None) -> bool:
    normalized = normalize_snbt_path(file_path)
    wrapped = f"/{normalized}"
    return normalized.endswith(".snbt") and "/ftbquests/" in wrapped and "/lang/" in wrapped


def is_ftb_quest_nbt_path(file_path: str | None) -> bool:
    normalized = normalize_snbt_path(file_path)
    wrapped = f"/{normalized}"
    return normalized.endswith(".nbt") and "/ftbquests/" in wrapped and "/quests/" in wrapped


def detect_snbt_compact_format(content: str) -> bool:
    return bool(LEGACY_COMPACT_PATTERN.search(content or ""))


def read_snbt_file(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def read_nbt_file(file_path: str) -> Any:
    if python_nbt is None:
        raise RuntimeError("NBT is required for NBT parsing. Please install backend dependencies first.")
    return python_nbt.NBTFile(filename=file_path)


def parse_snbt_content(content: str) -> Any:
    if snbtlib is None:
        raise RuntimeError("snbtlib is required for SNBT parsing. Please install backend dependencies first.")
    return snbtlib.loads(content)


def dump_snbt_content(data: Any, *, compact: bool) -> str:
    if snbtlib is None:
        raise RuntimeError("snbtlib is required for SNBT serialization. Please install backend dependencies first.")
    return snbtlib.dumps(data, compact=compact)


def dump_nbt_content(data: Any) -> bytes:
    if python_nbt is None:
        raise RuntimeError("NBT is required for NBT serialization. Please install backend dependencies first.")
    buffer = io.BytesIO()
    data.write_file(fileobj=buffer)
    return buffer.getvalue()


def is_string_array(value: Any) -> bool:
    if isinstance(value, list):
        return all(isinstance(item, str) for item in value)
    if python_nbt is not None and isinstance(value, python_nbt.TAG_List):
        return all(isinstance(item, python_nbt.TAG_String) for item in value)
    if isinstance(value, (str, bytes, bytearray, dict)):
        return False
    if hasattr(value, "__iter__") and hasattr(value, "__len__") and hasattr(value, "__getitem__"):
        try:
            return all(isinstance(item, str) for item in value)
        except TypeError:
            return False
    return False


def looks_like_ftb_lang_snbt_payload(data: Any, file_path: str | None = None) -> bool:
    if not isinstance(data, dict) or not data:
        return False

    keys = list(data.keys())
    values = list(data.values())
    if not all(isinstance(key, str) and "." in key for key in keys):
        return False
    if not all(isinstance(value, str) or is_string_array(value) for value in values):
        return False

    pattern_matches = sum(1 for key in keys if FTBQ_LANG_KEY_PATTERN.fullmatch(key))
    dotted_matches = sum(1 for key in keys if GENERIC_DOTTED_KEY_PATTERN.fullmatch(key))
    key_count = len(keys)
    normalized_path = normalize_snbt_path(file_path)
    ftb_path_hint = is_ftb_lang_path(file_path) or "/ftbquests/" in f"/{normalized_path}"

    if pattern_matches == key_count:
        return True
    if dotted_matches != key_count:
        return False

    if ftb_path_hint:
        relaxed_threshold = max(1, (key_count * 3 + 4) // 5)
        return pattern_matches >= relaxed_threshold

    strict_threshold = key_count if key_count <= 3 else (key_count * 4 + 4) // 5
    return pattern_matches >= strict_threshold


class SnbtParser(BaseParser):
    """解析并重写普通 SNBT 任务文件，并复用结构化递归逻辑处理 FTBQ 树。"""

    def can_parse(self, file_path: str) -> bool:
        return file_path.lower().endswith(".snbt")

    def extract(self, file_path: str) -> Dict[str, str]:
        result: Dict[str, str] = {}
        try:
            content = read_snbt_file(file_path)
            data = parse_snbt_content(content)
            for node in self._collect_translatable_nodes(data):
                result[node["entry_key"]] = node["value"]
        except Exception as exc:
            logger.warning("Failed to parse SNBT file %s: %s", file_path, exc)
        return result

    def render(self, file_path: str, translations: Dict[str, str], original_texts: Dict[str, str] | None = None) -> str:
        content = read_snbt_file(file_path)
        return self.render_content(content, translations, original_texts or {})

    def render_content(self, content: str, translations: Dict[str, str], original_texts: Dict[str, str] | None = None) -> str:
        original_texts = original_texts or {}
        compact = detect_snbt_compact_format(content)
        data = parse_snbt_content(content)
        nodes = self._collect_translatable_nodes(data)
        matched_keys: set[str] = set()

        for node in nodes:
            translated = self._resolve_translation(node, translations, original_texts, matched_keys)
            if translated is None or translated == node["value"]:
                continue
            self._assign_node_value(node, translated)

        return dump_snbt_content(data, compact=compact)

    def _collect_translatable_nodes(self, data: Any) -> List[dict]:
        nodes: List[dict] = []
        self._walk(value=data, path=[], nodes=nodes, parent=None, field=None, owner_key=None)
        return nodes

    def _walk(
        self,
        *,
        value: Any,
        path: List[str],
        nodes: List[dict],
        parent: Any,
        field: Any,
        owner_key: str | None,
    ) -> None:
        if self._is_compound(value):
            for key, child in self._iter_compound_items(value):
                child_path = [*path, self._escape_path_segment(str(key))]
                self._walk(
                    value=child,
                    path=child_path,
                    nodes=nodes,
                    parent=value,
                    field=key,
                    owner_key=str(key),
                )
            return

        if self._is_translatable_string_list(value, owner_key):
            self._collect_string_list_nodes(value=value, path=path, nodes=nodes, owner_key=owner_key)
            return

        if self._is_list(value):
            list_owner_key = owner_key
            for index, child in self._iter_list_items(value):
                child_path = [*path, self._build_list_selector(child, index)]
                self._walk(
                    value=child,
                    path=child_path,
                    nodes=nodes,
                    parent=value,
                    field=index,
                    owner_key=list_owner_key,
                )
            return

        if self._is_string_node(value):
            string_value = self._get_string_value(value)
            field_name = str(owner_key or "")
            if self._is_translatable_field(field_name) and not self._should_skip(string_value):
                nodes.append(
                    self._make_node(
                        parent=parent,
                        field=field,
                        path=path,
                        field_name=field_name,
                        value=string_value,
                        accepted_index=len(nodes),
                    )
                )

    def _collect_string_list_nodes(
        self,
        *,
        value: Any,
        path: List[str],
        nodes: List[dict],
        owner_key: str | None,
    ) -> None:
        field_name = str(owner_key or "")
        for index, child in self._iter_list_items(value):
            string_value = self._get_string_value(child)
            if self._should_skip(string_value):
                continue
            child_path = [*path, self._build_list_selector(child, index)]
            nodes.append(
                self._make_node(
                    parent=value,
                    field=index,
                    path=child_path,
                    field_name=field_name,
                    value=string_value,
                    accepted_index=len(nodes),
                )
            )

    def _make_node(
        self,
        *,
        parent: Any,
        field: Any,
        path: List[str],
        field_name: str,
        value: str,
        accepted_index: int,
    ) -> dict:
        normalized_field = field_name.lower()
        entry_key = "/".join(path) if path else f"entry/{accepted_index}"
        legacy_seq_key = f"{accepted_index:06d}:{normalized_field}"
        legacy_value_key = self._build_legacy_value_key(normalized_field, value)
        return {
            "parent": parent,
            "field": field,
            "field_name": normalized_field,
            "entry_key": entry_key,
            "legacy_keys": [legacy_seq_key, legacy_value_key],
            "value": value,
        }

    def _resolve_translation(
        self,
        node: dict,
        translations: Dict[str, str],
        original_texts: Dict[str, str],
        matched_keys: set[str],
    ) -> str | None:
        candidate_keys = [node["entry_key"], *node.get("legacy_keys", [])]
        for key in candidate_keys:
            if key in translations:
                matched_keys.add(key)
                return translations[key]

        for key, original_text in original_texts.items():
            if key in matched_keys:
                continue
            if original_text == node["value"] and key in translations:
                matched_keys.add(key)
                return translations[key]
        return None

    def _assign_node_value(self, node: dict, translated: str) -> None:
        parent = node.get("parent")
        field = node.get("field")

        if isinstance(parent, dict):
            parent[field] = translated
            return

        if isinstance(parent, list) and isinstance(field, int):
            parent[field] = translated
            return

        if self._is_nbt_compound(parent):
            target = parent[field]
            if self._is_nbt_string(target):
                target.value = translated
                return

        if self._is_nbt_list(parent) and isinstance(field, int):
            target = parent[field]
            if self._is_nbt_string(target):
                target.value = translated
                return

        raise TypeError(f"Unsupported node assignment target: parent={type(parent)!r}, field={field!r}")

    def _is_translatable_field(self, field_name: str) -> bool:
        normalized = str(field_name or "").split(":")[-1].strip().lower()
        return normalized in TRANSLATABLE_KEYS

    def _should_skip(self, value: str) -> bool:
        normalized = str(value or "").strip()
        if not normalized:
            return True
        if normalized.startswith("{") and normalized.endswith("}"):
            return True
        if any(marker in normalized for marker in SKIP_SUBSTRINGS):
            return True
        if URL_PATTERN.search(normalized):
            return True
        if IMAGE_HINT_PATTERN.search(normalized):
            return True
        if SPECIAL_EVENT_PATTERN.search(normalized) or normalized.startswith('{"'):
            return True
        if RESOURCE_ID_PATTERN.fullmatch(normalized):
            return True
        return False

    def _build_list_selector(self, item: Any, index: int) -> str:
        anchor = self._extract_list_anchor(item)
        if anchor:
            return f"[{anchor}]"
        return f"[{index}]"

    def _extract_list_anchor(self, item: Any) -> str | None:
        if not (isinstance(item, dict) or self._is_nbt_compound(item)):
            return None

        for path, label in LIST_ANCHOR_CANDIDATES:
            value = self._get_nested_scalar(item, path)
            normalized = self._normalize_anchor_value(value)
            if normalized:
                return f"{label}={normalized}"
        return None

    def _get_nested_scalar(self, item: Any, path: tuple[str, ...]) -> Any:
        current: Any = item
        for segment in path:
            if isinstance(current, dict):
                if segment not in current:
                    return None
                current = current[segment]
                continue

            if self._is_nbt_compound(current):
                try:
                    current = current[segment]
                except Exception:
                    return None
                continue

            return None
        return self._extract_scalar_value(current)

    def _extract_scalar_value(self, value: Any) -> Any:
        if isinstance(value, SCALAR_VALUE_TYPES):
            return value
        raw_value = getattr(value, "value", None)
        if isinstance(raw_value, SCALAR_VALUE_TYPES):
            return raw_value
        return None

    def _normalize_anchor_value(self, value: Any) -> str:
        if value is None:
            return ""
        normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value).strip())
        return normalized[:80].strip("_")

    def _escape_path_segment(self, segment: str) -> str:
        return str(segment).replace("\\", "\\\\").replace("/", "\\/")

    def _build_legacy_value_key(self, field_name: str, value: str) -> str:
        return f"{field_name}.{value[:40]}"

    def _is_compound(self, value: Any) -> bool:
        return isinstance(value, dict) or self._is_nbt_compound(value)

    def _iter_compound_items(self, value: Any) -> Iterable[tuple[Any, Any]]:
        if isinstance(value, dict):
            return value.items()
        if self._is_nbt_compound(value):
            return value.items()
        return ()

    def _iter_list_items(self, value: Any) -> Iterable[tuple[int, Any]]:
        if self._is_list(value):
            return enumerate(value)
        return ()

    def _is_list(self, value: Any) -> bool:
        if isinstance(value, list) or self._is_nbt_list(value):
            return True
        return (
            not isinstance(value, (str, bytes, bytearray, dict))
            and not self._is_nbt_compound(value)
            and hasattr(value, "__iter__")
            and hasattr(value, "__len__")
            and hasattr(value, "__getitem__")
        )

    def _is_string_node(self, value: Any) -> bool:
        return isinstance(value, str) or self._is_nbt_string(value)

    def _get_string_value(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if self._is_nbt_string(value):
            return str(value.value or "")
        raise TypeError(f"Unsupported string node type: {type(value)!r}")

    def _is_translatable_string_list(self, value: Any, owner_key: str | None) -> bool:
        if not self._is_translatable_field(str(owner_key or "")):
            return False
        if not self._is_list(value):
            return False

        has_items = False
        for _, child in self._iter_list_items(value):
            has_items = True
            if not self._is_string_node(child):
                return False
        return has_items

    def _is_nbt_compound(self, value: Any) -> bool:
        if python_nbt is None:
            return False
        return isinstance(value, (python_nbt.TAG_Compound, python_nbt.NBTFile))

    def _is_nbt_list(self, value: Any) -> bool:
        return python_nbt is not None and isinstance(value, python_nbt.TAG_List)

    def _is_nbt_string(self, value: Any) -> bool:
        return python_nbt is not None and isinstance(value, python_nbt.TAG_String)
