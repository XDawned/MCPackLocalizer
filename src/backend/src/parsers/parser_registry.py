import logging
from typing import Dict, List, Optional

from .base_parser import BaseParser
from .bq_parser import BqParser
from .ftb_lang_snbt_parser import FtbLangSnbtParser
from .ftb_quest_nbt_parser import FtbQuestNbtParser
from .jar_parser import JarParser
from .json_lang_parser import JsonLangParser
from .kubejs_js_parser import KubejsJsParser
from .lang_parser import LangParser
from .snbt_parser import SnbtParser

logger = logging.getLogger(__name__)


class ParserRegistry:
    """解析器注册表：按文件扩展名/路径模式自动匹配合适的解析器。"""

    def __init__(self):
        self._parsers: List[BaseParser] = [
            BqParser(),
            FtbLangSnbtParser(),
            FtbQuestNbtParser(),
            SnbtParser(),
            KubejsJsParser(),
            JarParser(),
            LangParser(),
            JsonLangParser(),
        ]

    def get_parser(self, file_path: str) -> Optional[BaseParser]:
        for parser in self._parsers:
            if parser.can_parse(file_path):
                return parser
        return None

    def extract(self, file_path: str) -> Dict[str, str]:
        parser = self.get_parser(file_path)
        if parser is None:
            logger.debug("No parser found for file: %s", file_path)
            return {}
        return parser.extract(file_path)

    def extract_all(self, file_paths: List[str]) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for fp in file_paths:
            try:
                parsed = self.extract(fp)
                result.update(parsed)
            except Exception as e:
                logger.warning("Failed to extract %s: %s", fp, e)
        return result
