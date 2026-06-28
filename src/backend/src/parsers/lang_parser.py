import logging
from typing import Dict

from .base_parser import BaseParser

logger = logging.getLogger(__name__)


class LangParser(BaseParser):
    """解析 .lang 格式文件 (key=value 行格式，1.12 及以下版本常用)。"""

    def can_parse(self, file_path: str) -> bool:
        return file_path.lower().endswith(".lang")

    def extract(self, file_path: str) -> Dict[str, str]:
        result: Dict[str, str] = {}
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip()
                        value = value.replace("%n", "\n")
                        if key and value:
                            result[key] = value
        except Exception as e:
            logger.warning("Failed to parse lang file %s: %s", file_path, e)
        return result
