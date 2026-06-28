import logging
from typing import Dict

from .snbt_parser import SnbtParser, dump_nbt_content, is_ftb_quest_nbt_path, read_nbt_file

logger = logging.getLogger(__name__)


class FtbQuestNbtParser(SnbtParser):
    """解析 FTB Quests 的 NBT 任务文件，复用结构化递归提取与稳定 key 逻辑。"""

    def can_parse(self, file_path: str) -> bool:
        return is_ftb_quest_nbt_path(file_path)

    def extract(self, file_path: str) -> Dict[str, str]:
        result: Dict[str, str] = {}
        try:
            data = read_nbt_file(file_path)
            for node in self._collect_translatable_nodes(data):
                result[node["entry_key"]] = node["value"]
        except Exception as exc:
            logger.warning("Failed to parse FTB quest NBT file %s: %s", file_path, exc)
        return result

    def render(self, file_path: str, translations: Dict[str, str], original_texts: Dict[str, str] | None = None) -> bytes:
        original_texts = original_texts or {}
        data = read_nbt_file(file_path)
        nodes = self._collect_translatable_nodes(data)
        matched_keys: set[str] = set()

        for node in nodes:
            translated = self._resolve_translation(node, translations, original_texts, matched_keys)
            if translated is None or translated == node["value"]:
                continue
            self._assign_node_value(node, translated)

        return dump_nbt_content(data)
