"""
翻译应用服务

支持两类后端落地输出：
- 直接应用到目标实例目录（保留备份）
- 生成贴近示例结构的补丁目录（config / kubejs / mods / 空 resourcepacks）
"""

import json
import logging
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

try:
    from ..config import (
        WORKSPACE_BACKUP_DIR,
        WORKSPACE_PATCH_DIR,
        ensure_workspace_dirs,
    )
    from ..models.backup import BackupRecord
    from ..models.settings import Setting
    from ..models.translation import TranslationTask, TranslateItem
    from ..parsers.bq_parser import BqParser
    from ..parsers.ftb_lang_snbt_parser import FtbLangSnbtParser
    from ..parsers.ftb_quest_nbt_parser import FtbQuestNbtParser
    from ..parsers.kubejs_js_parser import KubejsJsParser
    from ..parsers.snbt_parser import SnbtParser
    from .i18n_mod_service import I18nModService
    from .translation_metadata import get_item_metadata, group_items_by_target, normalize_relative_path
except ImportError:
    from src.config import WORKSPACE_BACKUP_DIR, WORKSPACE_PATCH_DIR, ensure_workspace_dirs  # type: ignore
    from src.models.backup import BackupRecord  # type: ignore
    from src.models.settings import Setting  # type: ignore
    from src.models.translation import TranslationTask, TranslateItem  # type: ignore
    from src.parsers.bq_parser import BqParser  # type: ignore
    from src.parsers.ftb_lang_snbt_parser import FtbLangSnbtParser  # type: ignore
    from src.parsers.ftb_quest_nbt_parser import FtbQuestNbtParser  # type: ignore
    from src.parsers.kubejs_js_parser import KubejsJsParser  # type: ignore
    from src.parsers.snbt_parser import SnbtParser  # type: ignore
    from src.services.i18n_mod_service import I18nModService  # type: ignore
    from src.services.translation_metadata import get_item_metadata, group_items_by_target, normalize_relative_path  # type: ignore

logger = logging.getLogger(__name__)

LOCAL_PATH_SETTING_KEYS = (
    "target_minecraft_root",
    "minecraft_path",
    "minecraft_root",
    "minecraft_dir",
    "game_path",
    "game_dir",
    "install_path",
    "local_path",
)
PATCH_OUTPUT_SETTING_KEYS = (
    "patch_output_dir",
    "patch_dir",
    "patch_root",
)
RESOURCEPACK_FOLDER_NAME = "MCPackLocalizer"
PATCH_PLACEHOLDER_DIRS = ("config", "kubejs", "mods", "resourcepacks")
PATCH_MANIFEST_NAME = "patch_manifest.json"
LANG_LINE_PATTERN = re.compile(r"^(?P<prefix>\s*)(?P<key>[^#!\s][^=]*?)\s*=(?P<value>.*)$")


class ApplyService:
    def __init__(self):
        self._snbt_parser = SnbtParser()
        self._bq_parser = BqParser()
        self._ftb_lang_snbt_parser = FtbLangSnbtParser()
        self._ftb_quest_nbt_parser = FtbQuestNbtParser()
        self._kubejs_js_parser = KubejsJsParser()
        self._i18n_mod_service = I18nModService()
        self._generated_patches: Dict[int, dict] = {}

    async def apply_translation(
        self,
        db: Session,
        task_id: int,
        local_path: Optional[str] = None,
    ) -> BackupRecord:
        task = self._get_task(db, task_id)
        resolved_local_path = self._resolve_local_path(db, task, local_path)
        items = self._load_completed_items(db, task_id)
        backup_root = self._create_backup_root(task_id)

        backed_files: List[str] = []
        added_files: List[str] = []

        try:
            grouped = group_items_by_target(items)
            for relative_path, target_items in grouped.items():
                metadata = get_item_metadata(target_items[0])
                target_strategy = str(metadata.get("target_strategy") or "")
                target_path = self._resolve_apply_target_path(resolved_local_path, relative_path, target_strategy)
                source_path = self._resolve_source_path(target_items)
                target_exists = os.path.isfile(target_path)

                if target_exists:
                    self._backup_file(backup_root, relative_path, target_path)
                    backed_files.append(relative_path)
                else:
                    added_files.append(relative_path)

                rendered_content = self._render_target_content(
                    target_strategy=target_strategy,
                    target_path=target_path,
                    source_path=source_path,
                    items=target_items,
                    target_exists=target_exists,
                )
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                write_mode = "wb" if isinstance(rendered_content, bytes) else "w"
                open_kwargs = {} if isinstance(rendered_content, bytes) else {"encoding": "utf-8"}
                with open(target_path, write_mode, **open_kwargs) as f:
                    f.write(rendered_content)

            mod_result = await self._i18n_mod_service.resolve_mod_file(db=db, task=task, local_root=resolved_local_path)
            self._apply_i18n_mod_to_instance(
                mod_result=mod_result,
                local_root=resolved_local_path,
                backup_root=backup_root,
                backed_files=backed_files,
                added_files=added_files,
            )

            backed_files = sorted(set(backed_files))
            added_files = sorted(set(added_files))
            self._write_backup_manifest(
                backup_root=backup_root,
                task_id=task_id,
                local_path=resolved_local_path,
                backed_files=backed_files,
                added_files=added_files,
                extra={"i18n_mod": mod_result},
            )

            record = BackupRecord(
                modpack_version_id=task.modpack_version_id,
                backup_path=backup_root,
                backed_files_json=json.dumps(backed_files, ensure_ascii=False),
                added_files_json=json.dumps(added_files, ensure_ascii=False),
                status="active",
            )
            db.add(record)

            task.status = "applied"
            task.finished_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(record)

            logger.info(
                "Translation applied: task_id=%d, backup_id=%d, path=%s, files=%d",
                task_id,
                record.id,
                resolved_local_path,
                len(backed_files) + len(added_files),
            )
            return record
        except Exception:
            db.rollback()
            shutil.rmtree(backup_root, ignore_errors=True)
            raise

    async def generate_patch_package(
        self,
        db: Session,
        task_id: int,
        config: Optional[dict] = None,
    ) -> dict:
        task = self._get_task(db, task_id)
        source_root = self._resolve_local_path(db, task, None)
        items = self._load_completed_items(db, task_id)
        patch_output_dir = self._resolve_patch_output_dir(db, config or {})
        patch_root = self._create_patch_root(task, patch_output_dir, config or {})
        written_files: List[str] = []
        placeholder_dirs = self._ensure_patch_placeholders(patch_root)
        skipped_resourcepack_targets: List[str] = []

        grouped = group_items_by_target(items)
        for relative_path, target_items in grouped.items():
            metadata = get_item_metadata(target_items[0])
            target_strategy = str(metadata.get("target_strategy") or "")
            if target_strategy == "resourcepack":
                skipped_resourcepack_targets.append(relative_path)
                continue

            target_path = self._resolve_patch_target_path(patch_root, relative_path)
            source_path = self._resolve_source_path(target_items)
            rendered_content = self._render_target_content(
                target_strategy=target_strategy,
                target_path=target_path,
                source_path=source_path,
                items=target_items,
                target_exists=os.path.isfile(target_path),
            )
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            write_mode = "wb" if isinstance(rendered_content, bytes) else "w"
            open_kwargs = {} if isinstance(rendered_content, bytes) else {"encoding": "utf-8"}
            with open(target_path, write_mode, **open_kwargs) as f:
                f.write(rendered_content)
            written_files.append(normalize_relative_path(os.path.relpath(target_path, patch_root)))

        mod_result = await self._i18n_mod_service.resolve_mod_file(db=db, task=task, local_root=source_root)
        mod_relative_path = self._copy_i18n_mod_to_patch(mod_result, patch_root)
        if mod_relative_path:
            written_files.append(mod_relative_path)

        manifest = {
            "task_id": task_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_root": source_root,
            "patch_root": patch_root,
            "written_files": sorted(set(written_files)),
            "placeholder_directories": placeholder_dirs,
            "skipped_resourcepack_targets": sorted(set(skipped_resourcepack_targets)),
            "i18n_mod": mod_result,
        }
        manifest_path = os.path.join(patch_root, PATCH_MANIFEST_NAME)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        result = {
            "patch_id": os.path.basename(patch_root),
            "patch_path": patch_root,
            "written_files": sorted(set(written_files)),
            "file_count": len(sorted(set(written_files))),
            "placeholder_directories": placeholder_dirs,
            "skipped_resourcepack_targets": sorted(set(skipped_resourcepack_targets)),
            "resourcepacks_reserved_only": True,
            "i18n_mod": mod_result,
        }
        self._generated_patches[task_id] = dict(result)
        return result

    async def restore_translation(self, db: Session, backup_id: int) -> dict:
        record = db.query(BackupRecord).filter(BackupRecord.id == backup_id).first()
        if not record:
            raise ValueError(f"BackupRecord id={backup_id} not found")

        backed_files = self._parse_json_list(record.backed_files_json)
        added_files = self._parse_json_list(record.added_files_json)
        manifest = self._load_backup_manifest(record.backup_path)
        target_root = self._resolve_restore_target_root(record, manifest)

        restored_files: List[str] = []
        removed_files: List[str] = []

        if target_root:
            for relative_path in backed_files:
                target_path = self._resolve_restore_target_path(target_root, relative_path)
                if manifest and record.backup_path:
                    backup_file_path = os.path.join(record.backup_path, relative_path.replace("/", os.sep))
                    if os.path.isfile(backup_file_path):
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        shutil.copy2(backup_file_path, target_path)
                restored_files.append(relative_path)

            for relative_path in added_files:
                target_path = self._resolve_restore_target_path(target_root, relative_path)
                if os.path.isfile(target_path):
                    os.remove(target_path)
                    self._cleanup_empty_dirs(os.path.dirname(target_path), self._cleanup_root_for(relative_path, target_root))
                removed_files.append(relative_path)
        else:
            restored_files = list(backed_files)
            removed_files = list(added_files)

        record.status = "restored"
        db.commit()

        logger.info(
            "Restored from backup id=%d: restored=%d files, removed=%d files",
            backup_id,
            len(restored_files),
            len(removed_files),
        )
        return {
            "backup_id": backup_id,
            "restored_files": restored_files,
            "removed_files": removed_files,
        }

    async def restore_translation_for_task(self, db: Session, task_id: int) -> dict:
        record = self._find_backup_for_task(db, task_id)
        return await self.restore_translation(db=db, backup_id=record.id)

    async def list_backups(
        self,
        db: Session,
        modpack_version_id: int | None = None,
    ) -> list[BackupRecord]:
        query = db.query(BackupRecord)
        if modpack_version_id is not None:
            query = query.filter(BackupRecord.modpack_version_id == modpack_version_id)
        return query.order_by(BackupRecord.created_at.desc(), BackupRecord.id.desc()).all()

    async def delete_backup(self, db: Session, backup_id: int) -> bool:
        record = db.query(BackupRecord).filter(BackupRecord.id == backup_id).first()
        if not record:
            raise ValueError(f"BackupRecord id={backup_id} not found")

        backup_path = record.backup_path or ""
        has_manifest = self._load_backup_manifest(backup_path) is not None

        db.delete(record)
        db.commit()

        if has_manifest and backup_path and os.path.isdir(backup_path):
            shutil.rmtree(backup_path, ignore_errors=True)

        logger.info("Deleted backup record id=%d", backup_id)
        return True

    def serialize_backup_record(self, record: BackupRecord) -> dict:
        return {
            "id": record.id,
            "modpack_version_id": record.modpack_version_id,
            "backup_path": record.backup_path or "",
            "backed_files": self._parse_json_list(record.backed_files_json),
            "added_files": self._parse_json_list(record.added_files_json),
            "status": record.status or "active",
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }

    def get_cached_patch_result(self, task_id: int) -> Optional[dict]:
        cached = self._generated_patches.get(task_id)
        if not cached:
            return None
        patch_path = str(cached.get("patch_path") or "")
        if not patch_path or not os.path.isdir(patch_path):
            self._generated_patches.pop(task_id, None)
            return None
        return dict(cached)

    def _get_task(self, db: Session, task_id: int) -> TranslationTask:
        task = db.query(TranslationTask).filter(TranslationTask.id == task_id).first()
        if not task:
            raise ValueError(f"TranslationTask id={task_id} not found")
        return task

    def _load_completed_items(self, db: Session, task_id: int) -> List[TranslateItem]:
        items: List[TranslateItem] = (
            db.query(TranslateItem)
            .filter(TranslateItem.task_id == task_id, TranslateItem.status == "completed")
            .all()
        )
        if not items:
            raise ValueError("No completed translation items found")
        return items

    def _resolve_local_path(
        self,
        db: Session,
        task: TranslationTask,
        local_path: Optional[str],
        validate_exists: bool = True,
    ) -> str:
        task_config = json.loads(task.config_json) if task.config_json else {}
        scan_result = json.loads(task.scan_result_json) if task.scan_result_json else {}
        candidates = [
            local_path,
            scan_result.get("work_root") if isinstance(scan_result, dict) else None,
            task_config.get("local_path") if isinstance(task_config, dict) else None,
            task.local_path,
            scan_result.get("minecraft_root") if isinstance(scan_result, dict) else None,
        ]

        for key in LOCAL_PATH_SETTING_KEYS:
            setting = db.query(Setting).filter(Setting.key == key).first()
            if setting and setting.value:
                candidates.append(setting.value)

        for candidate in candidates:
            value = str(candidate or "").strip()
            if not value:
                continue
            normalized = os.path.abspath(value)
            if validate_exists and not os.path.isdir(normalized):
                continue
            return normalized

        raise ValueError("Local modpack path not configured or does not exist")

    def _resolve_patch_output_dir(self, db: Session, config: dict) -> str:
        candidates = [config.get("output_dir") if isinstance(config, dict) else None]
        for key in PATCH_OUTPUT_SETTING_KEYS:
            setting = db.query(Setting).filter(Setting.key == key).first()
            if setting and setting.value:
                candidates.append(setting.value)
        candidates.append(WORKSPACE_PATCH_DIR)

        for candidate in candidates:
            value = str(candidate or "").strip()
            if not value:
                continue
            normalized = os.path.abspath(value)
            os.makedirs(normalized, exist_ok=True)
            return normalized
        os.makedirs(WORKSPACE_PATCH_DIR, exist_ok=True)
        return WORKSPACE_PATCH_DIR

    def _resolve_apply_target_path(self, local_root: str, relative_path: str, target_strategy: str) -> str:
        normalized = normalize_relative_path(relative_path)
        parts = normalized.split("/") if normalized else []
        if target_strategy == "resourcepack":
            return os.path.join(local_root, "resourcepacks", RESOURCEPACK_FOLDER_NAME, *parts)
        return os.path.join(local_root, *parts)

    def _resolve_patch_target_path(self, patch_root: str, relative_path: str) -> str:
        normalized = normalize_relative_path(relative_path)
        return os.path.join(patch_root, *normalized.split("/")) if normalized else patch_root

    def _resolve_restore_target_path(self, local_root: str, relative_path: str) -> str:
        normalized = normalize_relative_path(relative_path)
        if normalized.startswith("assets/"):
            return os.path.join(local_root, "resourcepacks", RESOURCEPACK_FOLDER_NAME, *normalized.split("/"))
        return os.path.join(local_root, *normalized.split("/"))

    def _cleanup_root_for(self, relative_path: str, local_root: str) -> str:
        normalized = normalize_relative_path(relative_path)
        if normalized.startswith("assets/"):
            return os.path.join(local_root, "resourcepacks", RESOURCEPACK_FOLDER_NAME)
        return local_root

    def _render_target_content(
        self,
        target_strategy: str,
        target_path: str,
        source_path: str,
        items: List[TranslateItem],
        target_exists: bool,
    ) -> str | bytes:
        if target_strategy == "resourcepack":
            existing = self._load_translation_file(target_path) if target_exists else {}
            for item in items:
                metadata = get_item_metadata(item)
                locator = metadata.get("target_locator") or {}
                translation_key = str(locator.get("translation_key") or "").strip()
                if not translation_key:
                    continue
                existing[translation_key] = item.translated_text or item.original_text or ""
            return json.dumps(existing, ensure_ascii=False, indent=2)

        translations, original_texts = self._build_rewrite_maps(items)
        base_path = target_path if target_exists else source_path
        if not base_path:
            raise ValueError(f"Missing source path for target strategy: {target_strategy}")

        if target_strategy == "snbt_rewrite":
            if not os.path.isfile(base_path):
                raise ValueError(f"FTB Quests source file not found: {base_path}")
            return self._snbt_parser.render(base_path, translations, original_texts)

        if target_strategy == "nbt_rewrite":
            if not os.path.isfile(base_path):
                raise ValueError(f"FTB Quests NBT source file not found: {base_path}")
            return self._ftb_quest_nbt_parser.render(base_path, translations, original_texts)

        if target_strategy == "ftbquests_lang_file":
            return self._render_by_extension(base_path, translations, original_texts)

        if target_strategy == "betterquesting_rewrite":
            if not os.path.isfile(base_path):
                raise ValueError(f"BetterQuesting source file not found: {base_path}")
            return self._bq_parser.render(base_path, translations, original_texts)

        if target_strategy == "json_rewrite":
            return self._render_json_file(base_path, translations, flat_keys=False)

        if target_strategy == "json_lang_file":
            return self._render_json_file(base_path, translations, flat_keys=True)

        if target_strategy == "lang_file":
            return self._render_lang_file(base_path, translations)

        if target_strategy == "js_text_rewrite":
            if not os.path.isfile(base_path):
                raise ValueError(f"KubeJS source file not found: {base_path}")
            return self._kubejs_js_parser.render(base_path, translations, original_texts)

        raise ValueError(f"Unsupported apply target strategy: {target_strategy}")

    def _render_by_extension(self, base_path: str, translations: Dict[str, str], original_texts: Dict[str, str]) -> str:
        lowered = base_path.lower()
        if lowered.endswith(".snbt"):
            return self._ftb_lang_snbt_parser.render(base_path, translations, original_texts)
        if lowered.endswith(".json"):
            return self._render_json_file(base_path, translations)
        if lowered.endswith(".lang"):
            return self._render_lang_file(base_path, translations)
        raise ValueError(f"Unsupported language file extension: {base_path}")

    def _render_json_file(self, base_path: str, translations: Dict[str, str], *, flat_keys: bool) -> str:
        data = {}
        if os.path.isfile(base_path):
            try:
                with open(base_path, "r", encoding="utf-8-sig") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    data = raw
            except Exception as exc:
                logger.warning("Failed to read JSON source %s: %s", base_path, exc)
        mutable = json.loads(json.dumps(data, ensure_ascii=False)) if data else {}
        for flat_key, translated in translations.items():
            if flat_keys:
                mutable[str(flat_key)] = translated
            else:
                self._set_json_value(mutable, flat_key, translated)
        return json.dumps(mutable, ensure_ascii=False, indent=2)

    def _set_json_value(self, data: dict, flat_key: str, value: str) -> None:
        if not isinstance(data, dict):
            return
        parts = [part for part in str(flat_key or "").split(".") if part]
        if not parts:
            return
        current = data
        for part in parts[:-1]:
            next_value = current.get(part)
            if not isinstance(next_value, dict):
                next_value = {}
                current[part] = next_value
            current = next_value
        current[parts[-1]] = value

    def _render_lang_file(self, base_path: str, translations: Dict[str, str]) -> str:
        lines: List[str] = []
        if os.path.isfile(base_path):
            with open(base_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        if not lines:
            return "\n".join(f"{key}={value}" for key, value in translations.items()) + ("\n" if translations else "")

        remaining = dict(translations)
        rendered_lines: List[str] = []
        for line in lines:
            match = LANG_LINE_PATTERN.match(line)
            if not match:
                rendered_lines.append(line)
                continue
            key = str(match.group("key") or "").strip()
            if key in remaining:
                rendered_lines.append(f"{match.group('prefix')}{key}={remaining.pop(key)}")
            else:
                rendered_lines.append(line)
        for key, value in remaining.items():
            rendered_lines.append(f"{key}={value}")
        return "\n".join(rendered_lines) + "\n"

    def _build_rewrite_maps(self, items: List[TranslateItem]) -> tuple[Dict[str, str], Dict[str, str]]:
        translations: Dict[str, str] = {}
        original_texts: Dict[str, str] = {}
        for item in items:
            metadata = get_item_metadata(item)
            locator = metadata.get("target_locator") or {}
            entry_key = str(locator.get("entry_key") or locator.get("translation_key") or "").strip()
            original_text = str(locator.get("original_text") or item.original_text or "")
            translated_text = str(item.translated_text or item.original_text or "")
            if entry_key:
                translations[entry_key] = translated_text
                original_texts[entry_key] = original_text
        return translations, original_texts

    def _resolve_source_path(self, items: List[TranslateItem]) -> str:
        metadata = get_item_metadata(items[0])
        source_relative_path = str(metadata.get("source_relative_path") or "").strip()
        if source_relative_path and os.path.isfile(source_relative_path):
            return source_relative_path
        first_item_path = str(items[0].source_path or "").strip()
        if first_item_path and os.path.isfile(first_item_path):
            return os.path.abspath(first_item_path)
        return first_item_path

    def _apply_i18n_mod_to_instance(
        self,
        mod_result: dict,
        local_root: str,
        backup_root: str,
        backed_files: List[str],
        added_files: List[str],
    ) -> None:
        file_path = str(mod_result.get("file_path") or "").strip()
        filename = str(mod_result.get("filename") or "").strip()
        if not file_path or not filename or not os.path.isfile(file_path):
            return
        target_relative = normalize_relative_path(f"mods/{filename}")
        target_path = os.path.join(local_root, "mods", filename)
        if os.path.abspath(file_path) == os.path.abspath(target_path):
            return
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        if os.path.isfile(target_path):
            self._backup_file(backup_root, target_relative, target_path)
            backed_files.append(target_relative)
        else:
            added_files.append(target_relative)
        shutil.copy2(file_path, target_path)

    def _copy_i18n_mod_to_patch(self, mod_result: dict, patch_root: str) -> Optional[str]:
        file_path = str(mod_result.get("file_path") or "").strip()
        filename = str(mod_result.get("filename") or "").strip()
        if not file_path or not filename or not os.path.isfile(file_path):
            return None
        target_relative = normalize_relative_path(f"mods/{filename}")
        target_path = os.path.join(patch_root, "mods", filename)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        shutil.copy2(file_path, target_path)
        return target_relative

    def _backup_file(self, backup_root: str, relative_path: str, target_path: str) -> None:
        backup_target_path = os.path.join(backup_root, relative_path.replace("/", os.sep))
        os.makedirs(os.path.dirname(backup_target_path), exist_ok=True)
        shutil.copy2(target_path, backup_target_path)

    def _create_backup_root(self, task_id: int) -> str:
        ensure_workspace_dirs()
        backup_id = uuid.uuid4().hex[:8]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        backup_root = os.path.join(WORKSPACE_BACKUP_DIR, f"task_{task_id}_{timestamp}_{backup_id}")
        os.makedirs(backup_root, exist_ok=True)
        return backup_root

    def _create_patch_root(self, task: TranslationTask, output_dir: str, config: dict) -> str:
        ensure_workspace_dirs()
        patch_name = self._build_patch_name(task, config)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        patch_id = uuid.uuid4().hex[:8]
        patch_root = os.path.join(output_dir, f"{patch_name}_{timestamp}_{patch_id}")
        os.makedirs(patch_root, exist_ok=True)
        return patch_root

    def _build_patch_name(self, task: TranslationTask, config: dict) -> str:
        desired = str((config or {}).get("name") or "").strip()
        if desired:
            return self._sanitize_path_component(desired)

        scan_result = json.loads(task.scan_result_json) if task.scan_result_json else {}
        if isinstance(scan_result, dict):
            name = str(scan_result.get("name") or "").strip()
            if name:
                return self._sanitize_path_component(f"{name}-汉化补丁")
        return f"MCPackLocalizer_task_{task.id}_patch"

    def _ensure_patch_placeholders(self, patch_root: str) -> List[str]:
        created: List[str] = []
        for directory in PATCH_PLACEHOLDER_DIRS:
            path = os.path.join(patch_root, directory)
            os.makedirs(path, exist_ok=True)
            created.append(directory)
        return created

    def _sanitize_path_component(self, value: str) -> str:
        cleaned = re.sub(r'[\\/:*?"<>|]+', "_", value.strip())
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
        return cleaned or "MCPackLocalizer_patch"

    def _write_backup_manifest(
        self,
        backup_root: str,
        task_id: int,
        local_path: str,
        backed_files: List[str],
        added_files: List[str],
        extra: Optional[dict] = None,
    ) -> None:
        manifest_path = os.path.join(backup_root, "manifest.json")
        manifest = {
            "task_id": task_id,
            "local_path": local_path,
            "backed_files": backed_files,
            "added_files": added_files,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            manifest.update(extra)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    def _load_backup_manifest(self, backup_path: Optional[str]) -> Optional[dict]:
        if not backup_path:
            return None

        manifest_path = os.path.join(backup_path, "manifest.json")
        if not os.path.isfile(manifest_path):
            return None

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception as exc:
            logger.warning("Failed to read backup manifest %s: %s", manifest_path, exc)
        return None

    def _resolve_restore_target_root(self, record: BackupRecord, manifest: Optional[dict]) -> Optional[str]:
        if manifest:
            local_path = str(manifest.get("local_path") or "").strip()
            if local_path:
                return os.path.abspath(local_path)

        legacy_path = str(record.backup_path or "").strip()
        if legacy_path and os.path.isdir(legacy_path):
            return os.path.abspath(legacy_path)
        return None

    def _cleanup_empty_dirs(self, current_dir: str, stop_dir: str) -> None:
        stop_dir_abs = os.path.abspath(stop_dir)
        current_dir_abs = os.path.abspath(current_dir)

        while current_dir_abs.startswith(stop_dir_abs) and current_dir_abs != stop_dir_abs:
            if not os.path.isdir(current_dir_abs):
                break
            if os.listdir(current_dir_abs):
                break
            os.rmdir(current_dir_abs)
            current_dir_abs = os.path.abspath(os.path.dirname(current_dir_abs))

    def _find_backup_for_task(self, db: Session, task_id: int) -> BackupRecord:
        task = self._get_task(db, task_id)
        query = db.query(BackupRecord).order_by(BackupRecord.created_at.desc(), BackupRecord.id.desc())

        if task.modpack_version_id is not None:
            record = (
                query.filter(
                    BackupRecord.modpack_version_id == task.modpack_version_id,
                    BackupRecord.status == "active",
                )
                .first()
            )
            if record:
                return record

            record = query.filter(BackupRecord.modpack_version_id == task.modpack_version_id).first()
            if record:
                return record

        task_local_path = self._resolve_local_path(db, task, None, validate_exists=False)
        for record in query.all():
            manifest = self._load_backup_manifest(record.backup_path)
            manifest_local_path = str((manifest or {}).get("local_path") or "").strip()
            if manifest_local_path and os.path.abspath(manifest_local_path) == task_local_path:
                return record

            legacy_path = str(record.backup_path or "").strip()
            if not manifest and legacy_path and os.path.abspath(legacy_path) == task_local_path:
                return record

        raise ValueError(f"No backup record found for TranslationTask id={task_id}")

    def _load_translation_file(self, path: str) -> Dict[str, str]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except Exception as exc:
            logger.warning("Failed to read existing translation file %s: %s", path, exc)
        return {}

    def _parse_json_list(self, raw: Optional[str]) -> List[str]:
        if not raw:
            return []
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(item) for item in data if str(item).strip()]
        except Exception as exc:
            logger.warning("Failed to parse backup file list: %s", exc)
        return []
