import logging
import re
from typing import Dict

from .__init__ import BasePostprocessor

logger = logging.getLogger(__name__)
PLACEHOLDER_PATTERN = re.compile(r"(?<!\{)\{[^{}]+\}(?!\})")


class SnbtValidator(BasePostprocessor):
    """SNBT 相关翻译结果的轻量校验后处理器。"""

    def process(self, translation: str, original: str, metadata: Dict = None) -> str:
        metadata = metadata or {}
        area_type = str(metadata.get("area_type") or "")
        target_strategy = str(metadata.get("target_strategy") or "")

        if area_type not in {"ftb_quests", "ftbquests_lang"} and target_strategy not in {"snbt_rewrite", "nbt_rewrite", "ftbquests_lang_file"}:
            return translation

        bracket_diff = translation.count("{") - translation.count("}")
        if bracket_diff != 0:
            logger.debug(
                "SNBT-like translation bracket mismatch: { = %d, } = %d (diff=%d)",
                translation.count("{"),
                translation.count("}"),
                bracket_diff,
            )

        original_placeholders = PLACEHOLDER_PATTERN.findall(original or "")
        translated_placeholders = PLACEHOLDER_PATTERN.findall(translation or "")
        if original_placeholders and original_placeholders != translated_placeholders:
            logger.debug(
                "SNBT-like translation placeholder mismatch, preserving original translation text. original=%s translated=%s",
                original_placeholders,
                translated_placeholders,
            )
            return original
        return translation
