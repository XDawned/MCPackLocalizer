import re
import logging
from typing import Dict

from .__init__ import BasePostprocessor

logger = logging.getLogger(__name__)

PLACEHOLDER_PATTERNS = [
    (r"%[sd]", r"%[sd]"),
    (r"%\d+\$[sd]", r"%\d+\$[sd]"),
    (r"\{\d+\}", r"\{\d+\}"),
    (r"%%[sd]", r"%%[sd]"),
]


class PlaceholderChecker(BasePostprocessor):
    """占位符完整性检查后处理器。"""

    def process(self, translation: str, original: str, metadata: Dict = None) -> str:
        for pattern_str, _ in PLACEHOLDER_PATTERNS:
            original_matches = re.findall(pattern_str, original)
            translated_matches = re.findall(pattern_str, translation)
            if len(original_matches) != len(translated_matches):
                logger.debug(
                    "Placeholder mismatch: original has %d %ss, translated has %d",
                    len(original_matches), pattern_str, len(translated_matches),
                )
        return translation
