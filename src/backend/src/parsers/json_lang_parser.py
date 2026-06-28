import json
import logging
from typing import Any, Dict

from .base_parser import BaseParser

logger = logging.getLogger(__name__)


class JsonLangParser(BaseParser):
    """解析 JSON 语言文件 (assets/<modid>/lang/*.json)。"""

    def can_parse(self, file_path: str) -> bool:
        return file_path.lower().endswith(".json")

    def extract(self, file_path: str) -> Dict[str, str]:
        result: Dict[str, str] = {}
        try:
            with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._flatten(data, "", result)
        except Exception as e:
            logger.warning("Failed to parse JSON lang file %s: %s", file_path, e)
        return result

    def _flatten(self, obj: Any, prefix: str, result: Dict[str, str]) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                new_key = f"{prefix}.{k}" if prefix else k
                self._flatten(v, new_key, result)
        elif isinstance(obj, str):
            result[prefix] = obj
