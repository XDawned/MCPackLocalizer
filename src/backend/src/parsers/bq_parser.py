import json
import logging
import re
from typing import Any, Dict, List

from .base_parser import BaseParser

logger = logging.getLogger(__name__)
TOKEN_SPLIT_PATTERN = re.compile(r"(?<!\\)\.(?![^\[]*\])")
INDEX_PATTERN = re.compile(r"^(?P<name>[^\[]+)?\[(?P<index>\d+)\]$")


class BqParser(BaseParser):
    """解析并最小回写 BetterQuesting DefaultQuests.json。"""

    def can_parse(self, file_path: str) -> bool:
        return "DefaultQuests" in file_path and file_path.lower().endswith(".json")

    def extract(self, file_path: str) -> Dict[str, str]:
        result: Dict[str, str] = {}
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)

            version = self._infer_version(data)
            if version == 3:
                self._traverse_v3(data, "", result)
            elif version == 2:
                self._traverse_v2(data, "", result)
            else:
                self._traverse_v1(data, "", result)
        except Exception as e:
            logger.warning("Failed to parse BQ file %s: %s", file_path, e)
        return result

    def render(self, file_path: str, translations: Dict[str, str], original_texts: Dict[str, str] | None = None) -> str:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        rendered_data = self.render_data(data, translations, original_texts or {})
        return json.dumps(rendered_data, ensure_ascii=False, indent=2)

    def render_data(self, data: Any, translations: Dict[str, str], original_texts: Dict[str, str] | None = None) -> Any:
        original_texts = original_texts or {}
        mutable = json.loads(json.dumps(data, ensure_ascii=False))
        visited = self._collect_translatable_nodes(mutable)
        used_keys: set[str] = set()

        for node in visited:
            translated = self._resolve_translation(node, translations, original_texts, used_keys)
            if translated is None:
                continue
            parent = node["parent"]
            key = node["field"]
            if isinstance(parent, dict):
                parent[key] = translated
            elif isinstance(parent, list) and isinstance(key, int):
                parent[key] = translated
        return mutable

    def _infer_version(self, data: Any) -> int:
        if isinstance(data, dict) and "questDatabase" in data:
            return 3
        if isinstance(data, dict) and "questLines" in data:
            return 2
        return 1

    def _traverse_v3(self, data: Any, prefix: str, result: Dict[str, str]) -> None:
        if not isinstance(data, dict):
            return
        quest_db = data.get("questDatabase", {})
        if isinstance(quest_db, dict):
            for qid, quest in quest_db.items():
                if isinstance(quest, dict):
                    props = quest.get("properties", quest.get("props", quest))
                    better = props.get("betterquesting", props)
                    if isinstance(better, dict):
                        name = better.get("name", "")
                        desc = better.get("desc", better.get("description", ""))
                        if name:
                            result[f"bq.quest.{qid}.name"] = name
                        if desc:
                            result[f"bq.quest.{qid}.desc"] = desc

    def _traverse_v2(self, data: Any, prefix: str, result: Dict[str, str]) -> None:
        if isinstance(data, dict):
            for k, v in data.items():
                if k in ("name", "desc", "description") and isinstance(v, str) and v:
                    result[f"{prefix}.{k}" if prefix else k] = v
                elif isinstance(v, (dict, list)):
                    self._traverse_v2(v, f"{prefix}.{k}" if prefix else k, result)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                self._traverse_v2(item, f"{prefix}[{i}]" if prefix else f"[{i}]", result)

    def _traverse_v1(self, data: Any, prefix: str, result: Dict[str, str]) -> None:
        self._traverse_v2(data, prefix, result)

    def _collect_translatable_nodes(self, data: Any) -> List[dict]:
        version = self._infer_version(data)
        if version == 3:
            return self._collect_v3_nodes(data)
        return self._collect_generic_nodes(data)

    def _collect_v3_nodes(self, data: Any) -> List[dict]:
        nodes: List[dict] = []
        if not isinstance(data, dict):
            return nodes
        quest_db = data.get("questDatabase", {})
        if not isinstance(quest_db, dict):
            return nodes

        for qid, quest in quest_db.items():
            if not isinstance(quest, dict):
                continue
            props = quest.get("properties")
            if isinstance(props, dict) and isinstance(props.get("betterquesting"), dict):
                better = props["betterquesting"]
                if isinstance(better.get("name"), str) and better.get("name"):
                    nodes.append(self._make_node(better, "name", f"bq.quest.{qid}.name"))
                if isinstance(better.get("desc"), str) and better.get("desc"):
                    nodes.append(self._make_node(better, "desc", f"bq.quest.{qid}.desc"))
                elif isinstance(better.get("description"), str) and better.get("description"):
                    nodes.append(self._make_node(better, "description", f"bq.quest.{qid}.desc"))
                continue

            if isinstance(props, dict):
                nodes.extend(self._collect_generic_nodes(props, prefix=f"questDatabase.{qid}.properties"))
            else:
                nodes.extend(self._collect_generic_nodes(quest, prefix=f"questDatabase.{qid}"))
        return nodes

    def _collect_generic_nodes(self, data: Any, prefix: str = "") -> List[dict]:
        nodes: List[dict] = []
        if isinstance(data, dict):
            for key, value in data.items():
                current = f"{prefix}.{key}" if prefix else key
                if key in ("name", "desc", "description") and isinstance(value, str) and value:
                    nodes.append(self._make_node(data, key, current))
                elif isinstance(value, (dict, list)):
                    nodes.extend(self._collect_generic_nodes(value, current))
        elif isinstance(data, list):
            for index, item in enumerate(data):
                current = f"{prefix}[{index}]" if prefix else f"[{index}]"
                nodes.extend(self._collect_generic_nodes(item, current))
        return nodes

    def _make_node(self, parent: Any, field: Any, entry_key: str) -> dict:
        value = parent[field] if isinstance(parent, (dict, list)) else ""
        return {
            "parent": parent,
            "field": field,
            "entry_key": entry_key,
            "value": value,
        }

    def _resolve_translation(
        self,
        node: dict,
        translations: Dict[str, str],
        original_texts: Dict[str, str],
        used_keys: set[str],
    ) -> str | None:
        entry_key = node["entry_key"]
        if entry_key in translations:
            used_keys.add(entry_key)
            return translations[entry_key]

        for key, original_text in original_texts.items():
            if key in used_keys:
                continue
            if original_text == node["value"] and key in translations:
                used_keys.add(key)
                return translations[key]
        return None
