import logging
from typing import Dict

from .__init__ import BasePostprocessor

logger = logging.getLogger(__name__)


class GlossaryChecker(BasePostprocessor):
    """术语一致性校验后处理器。"""

    def __init__(self):
        self._glossary = {}

    def set_glossary(self, glossary_entries: Dict[str, str]):
        self._glossary = glossary_entries

    def process(self, translation: str, original: str, metadata: Dict = None) -> str:
        for source_term, target_term in self._glossary.items():
            if source_term.lower() in original.lower() and target_term.lower() not in translation.lower():
                logger.debug(
                    "Glossary term '%s' -> '%s' not found in translation",
                    source_term, target_term,
                )
        return translation
