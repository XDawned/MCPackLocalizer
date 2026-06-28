"""
资源包生成服务

仅导出应进入资源包的 [`mod_lang`](src/backend/src/services/pack_scanner.py:514) 译文，
不再将任务/配置类内容压平成 lang JSON。
"""

import json
import logging
import os
import shutil
import tempfile
import uuid
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

try:
    from ..config import WORKSPACE_RESOURCEPACK_DIR, WORKSPACE_TEMP_DIR, ensure_workspace_dirs
    from ..models.translation import TranslationTask, TranslateItem
    from .translation_metadata import get_item_metadata, group_items_by_target, normalize_relative_path
except ImportError:
    from src.config import WORKSPACE_RESOURCEPACK_DIR, WORKSPACE_TEMP_DIR, ensure_workspace_dirs  # type: ignore
    from src.models.translation import TranslationTask, TranslateItem  # type: ignore
    from src.services.translation_metadata import get_item_metadata, group_items_by_target, normalize_relative_path  # type: ignore

logger = logging.getLogger(__name__)

PACK_FORMAT_MAP = {
    "1.6": 1, "1.7": 1, "1.8": 1,
    "1.9": 2, "1.10": 2,
    "1.11": 3, "1.12": 3,
    "1.13": 4, "1.14": 4,
    "1.15": 5, "1.16.1": 5,
    "1.16": 6,
    "1.17": 7,
    "1.18": 8,
    "1.19.1": 9, "1.19.2": 9,
    "1.19.3": 12, "1.19.4": 13,
    "1.20": 15, "1.20.1": 15, "1.20.2": 18, "1.20.3": 22, "1.20.4": 22, "1.20.5": 32,
    "1.21": 34, "1.21.1": 34,
}


def _detect_pack_format(mc_version: str) -> int:
    if not mc_version:
        return 15
    parts = mc_version.split(".")
    for check_ver in sorted(PACK_FORMAT_MAP.keys(), reverse=True):
        check_parts = check_ver.split(".")
        match = True
        for i, cp in enumerate(check_parts):
            if i >= len(parts) or parts[i] != cp:
                match = False
                break
        if match:
            return PACK_FORMAT_MAP[check_ver]
    return 15


def _generate_resourcepack_id() -> str:
    today = date.today().strftime("%Y%m%d")
    short_id = uuid.uuid4().hex[:8]
    return f"rp_{today}_{short_id}"


class ResourcePackService:
    """资源包生成服务。"""

    def __init__(self, output_dir: Optional[str] = None):
        ensure_workspace_dirs()
        self.output_dir = output_dir or WORKSPACE_RESOURCEPACK_DIR
        self.temp_root_dir = WORKSPACE_TEMP_DIR
        self._generated_files: Dict[int, dict] = {}

    def get_cached_result(self, task_id: int) -> Optional[dict]:
        cached = self._generated_files.get(task_id)
        if not cached:
            return None

        file_path = cached.get("file_path", "")
        if not file_path or not os.path.isfile(file_path):
            self._generated_files.pop(task_id, None)
            return None

        return dict(cached)

    def generate(self, db: Session, task_id: int, config: dict) -> dict:
        task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
        if not task:
            raise ValueError(f"TranslationTask id={task_id} not found")

        items: List[TranslateItem] = (
            db.query(TranslateItem)
            .filter(TranslateItem.task_id == task_id, TranslateItem.status == "completed")
            .all()
        )
        if not items:
            raise ValueError("No completed translation items found")

        mod_lang_items = [item for item in items if get_item_metadata(item).get("area_type") == "mod_lang"]
        if not mod_lang_items:
            raise ValueError("No completed mod_lang translation items found")

        task_config = json.loads(task.config_json) if task.config_json else {}
        mc_version = config.get("mc_version", task_config.get("mc_version", ""))
        pack_format = config.get("pack_format") or _detect_pack_format(mc_version)
        description = config.get("description", "MCPackLocalizer 汉化资源包")
        rp_name = config.get("name") or f"MCPackLocalizer_{task_id}"

        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.temp_root_dir, exist_ok=True)
        temp_dir = tempfile.mkdtemp(prefix="mcpacks_rp_", dir=self.temp_root_dir)
        try:
            pack_dir = os.path.join(temp_dir, rp_name)
            os.makedirs(pack_dir, exist_ok=True)

            self._write_pack_mcmeta(pack_dir, pack_format, description)
            exported_files = self._write_translations(pack_dir, mod_lang_items)

            archive_base_name = os.path.join(self.output_dir, f"{rp_name}-v1")
            zip_path = shutil.make_archive(
                archive_base_name,
                "zip",
                temp_dir,
                rp_name,
            )
            zip_filename = os.path.basename(zip_path)
            file_size = os.path.getsize(zip_path)
            rp_id = _generate_resourcepack_id()

            result = {
                "resourcepack_id": rp_id,
                "filename": zip_filename,
                "file_path": zip_path,
                "file_size": file_size,
                "pack_format": pack_format,
                "item_count": len(mod_lang_items),
                "file_count": len(exported_files),
                "export_mode": "resourcepack_only",
            }
            self._generated_files[task_id] = dict(result)
            return result
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _write_pack_mcmeta(self, pack_dir: str, pack_format: int, description: str):
        mcmeta = {
            "pack": {
                "pack_format": pack_format,
                "description": description,
            }
        }
        mcmeta_path = os.path.join(pack_dir, "pack.mcmeta")
        with open(mcmeta_path, "w", encoding="utf-8") as f:
            json.dump(mcmeta, f, ensure_ascii=False, indent=2)

    def _write_translations(self, pack_dir: str, items: List[TranslateItem]) -> List[str]:
        grouped = group_items_by_target(items)
        written_files: List[str] = []

        for relative_path, group in grouped.items():
            translations: Dict[str, str] = {}
            for item in group:
                metadata = get_item_metadata(item)
                if metadata.get("area_type") != "mod_lang":
                    continue
                locator = metadata.get("target_locator") or {}
                translation_key = str(locator.get("translation_key") or "").strip()
                if not translation_key:
                    continue
                translations[translation_key] = item.translated_text or item.original_text or ""

            if not translations:
                continue

            target_path = os.path.join(pack_dir, *normalize_relative_path(relative_path).split("/"))
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(translations, f, ensure_ascii=False, indent=2)
            written_files.append(normalize_relative_path(relative_path))

        return written_files
