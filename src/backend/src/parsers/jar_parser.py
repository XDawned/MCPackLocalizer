import logging
import os
import tempfile
import zipfile
from typing import Dict

from .base_parser import BaseParser
from .lang_parser import LangParser
from .json_lang_parser import JsonLangParser

logger = logging.getLogger(__name__)


class JarParser(BaseParser):
    """解析 JAR 文件中的语言文件 (assets/*/lang/en_us.*)。"""

    def __init__(self):
        self.lang_parser = LangParser()
        self.json_parser = JsonLangParser()

    def can_parse(self, file_path: str) -> bool:
        return file_path.lower().endswith(".jar")

    def extract(self, file_path: str) -> Dict[str, str]:
        from ..config import WORKSPACE_TEMP_DIR, ensure_workspace_dirs
        result: Dict[str, str] = {}
        ensure_workspace_dirs()
        os.makedirs(WORKSPACE_TEMP_DIR, exist_ok=True)
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                for entry in zf.namelist():
                    if not self._is_english_lang_entry(entry):
                        continue
                    tmp_path = ""
                    try:
                        with tempfile.NamedTemporaryFile(
                            suffix=os.path.splitext(entry)[1] or ".tmp",
                            dir=WORKSPACE_TEMP_DIR,
                            delete=False,
                        ) as tmp:
                            tmp.write(zf.read(entry))
                            tmp_path = tmp.name
                        if entry.endswith(".lang"):
                            parsed = self.lang_parser.extract(tmp_path)
                        else:
                            parsed = self.json_parser.extract(tmp_path)
                        for k, v in parsed.items():
                            modid = self._extract_modid(entry)
                            full_key = f"{modid}.{k}"
                            result[full_key] = v
                    except Exception as e:
                        logger.debug("Failed to extract %s from jar %s: %s", entry, file_path, e)
                    finally:
                        if tmp_path and os.path.exists(tmp_path):
                            os.unlink(tmp_path)
        except Exception as e:
            logger.warning("Failed to parse JAR file %s: %s", file_path, e)
        return result

    def _is_english_lang_entry(self, entry_path: str) -> bool:
        entry_lower = entry_path.lower()
        if not entry_lower.startswith("assets/"):
            return False
        if "/lang/" not in entry_lower:
            return False
        basename = os.path.basename(entry_path).lower()
        return basename.startswith("en_us") or basename.startswith("en_ud") or basename == "en_us.lang"

    def _extract_modid(self, entry_path: str) -> str:
        parts = entry_path.replace("\\", "/").split("/")
        if len(parts) >= 2 and parts[0].lower() == "assets":
            return parts[1]
        return "unknown"
