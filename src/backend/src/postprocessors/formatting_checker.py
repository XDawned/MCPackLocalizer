import re
import logging
from typing import Dict

from .__init__ import BasePostprocessor

logger = logging.getLogger(__name__)

COLOR_PATTERNS = [
    r"§[0-9a-fA-Fk-or]",
    r"&[0-9a-fA-Fk-or]",
]

NEWLINE_PATTERN = r"\\n"


class FormattingChecker(BasePostprocessor):
    """颜色代码和换行保留检查后处理器。"""

    def process(self, translation: str, original: str, metadata: Dict = None) -> str:
        for pattern in COLOR_PATTERNS:
            original_colors = re.findall(pattern, original)
            translated_colors = re.findall(pattern, translation)
            if len(original_colors) != len(translated_colors):
                logger.debug(
                    "Color code mismatch for %s: original=%d, translated=%d",
                    pattern, len(original_colors), len(translated_colors),
                )

        original_newlines = len(re.findall(NEWLINE_PATTERN, original))
        translated_newlines = len(re.findall(NEWLINE_PATTERN, translation))
        if original_newlines != translated_newlines:
            logger.debug(
                "Newline mismatch: original=%d, translated=%d",
                original_newlines, translated_newlines,
            )
        return translation
