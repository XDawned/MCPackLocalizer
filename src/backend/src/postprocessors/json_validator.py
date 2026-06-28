import json
import logging
from typing import Dict

from .__init__ import BasePostprocessor

logger = logging.getLogger(__name__)


class JsonValidator(BasePostprocessor):
    """JSON 格式修复后处理器。"""

    def process(self, translation: str, original: str, metadata: Dict = None) -> str:
        if not translation.strip():
            return translation
        if translation.strip().startswith("{") or translation.strip().startswith("["):
            try:
                json.loads(translation)
            except json.JSONDecodeError:
                try:
                    import json_repair
                    return json_repair.repair_json(translation)
                except ImportError:
                    logger.debug("json_repair not available, skipping JSON repair")
        return translation
