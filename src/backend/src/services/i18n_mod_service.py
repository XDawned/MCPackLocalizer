import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

import httpx
from sqlalchemy.orm import Session

try:
    from ..config import WORKSPACE_DOWNLOAD_CACHE_DIR, ensure_workspace_dirs, settings
    from ..models.settings import Setting
    from ..models.translation import TranslationTask
except ImportError:
    from src.config import WORKSPACE_DOWNLOAD_CACHE_DIR, ensure_workspace_dirs, settings  # type: ignore
    from src.models.settings import Setting  # type: ignore
    from src.models.translation import TranslationTask  # type: ignore

logger = logging.getLogger(__name__)

I18N_MOD_PROJECT_SLUG = "i18nupdatemod"
I18N_MOD_SEARCH_NAME = "I18nUpdateMod"
I18N_MOD_FILE_PATTERN = re.compile(r"i18nupdatemod.*\.jar$", re.IGNORECASE)
MODRINTH_BASE_URL = "https://api.modrinth.com/v2"
CURSEFORGE_BASE_URL = "https://api.curseforge.com/v1"
DEFAULT_USER_AGENT = "MCPackLocalizer/2.0 (admin@example.com)"
DEFAULT_CACHE_DIR = os.path.join(WORKSPACE_DOWNLOAD_CACHE_DIR, "i18nupdatemod")
SETTING_INCLUDE_I18N_MOD = "include_i18n_update_mod"
SETTING_I18N_CACHE_DIR = "i18n_mod_cache_dir"
TRUTHY_VALUES = {"1", "true", "yes", "on"}
LOADER_SYNONYMS = {
    "neoforge": {"neoforge", "neo-forge", "neo_forge", "neoforged"},
    "forge": {"forge"},
    "fabric": {"fabric"},
    "quilt": {"quilt"},
}


@dataclass
class I18nTargetContext:
    mc_version: str
    loader: Optional[str]
    loader_version: Optional[str]
    instance_root: Optional[str]
    version_json_path: Optional[str]


class I18nModService:
    """为补丁目录/实例应用准备 I18nUpdateMod.jar。"""

    async def resolve_mod_file(
        self,
        db: Session,
        task: TranslationTask,
        local_root: Optional[str] = None,
    ) -> dict:
        options = self._load_options(db)
        include_enabled = self._as_bool(options.get(SETTING_INCLUDE_I18N_MOD), default=False)
        cache_dir = str(options.get(SETTING_I18N_CACHE_DIR) or DEFAULT_CACHE_DIR).strip() or DEFAULT_CACHE_DIR
        ensure_workspace_dirs()
        os.makedirs(cache_dir, exist_ok=True)

        if not include_enabled:
            return {
                "enabled": False,
                "status": "skipped_disabled",
                "source": "disabled",
                "message": "未启用附带 I18nUpdateMod",
                "file_path": None,
                "filename": None,
            }

        context = self._build_context(task, local_root)
        if not context.mc_version:
            return {
                "enabled": True,
                "status": "skipped_missing_context",
                "source": "unresolved",
                "message": "无法识别目标实例的 Minecraft 版本，已跳过 I18nUpdateMod",
                "file_path": None,
                "filename": None,
                "loader": context.loader,
                "mc_version": context.mc_version,
            }

        local_existing = self._find_local_existing(context.instance_root)
        if local_existing:
            return {
                "enabled": True,
                "status": "reused_local",
                "source": "local",
                "message": "复用目标实例中已有的 I18nUpdateMod",
                "file_path": local_existing,
                "filename": os.path.basename(local_existing),
                "loader": context.loader,
                "loader_version": context.loader_version,
                "mc_version": context.mc_version,
            }

        cached = self._find_cached_file(cache_dir, context.mc_version, context.loader)
        if cached:
            return {
                "enabled": True,
                "status": "reused_cache",
                "source": "cache",
                "message": "复用本地缓存的 I18nUpdateMod",
                "file_path": cached,
                "filename": os.path.basename(cached),
                "loader": context.loader,
                "loader_version": context.loader_version,
                "mc_version": context.mc_version,
            }

        downloaded = await self._download_from_modrinth(context, cache_dir)
        if downloaded:
            return downloaded

        downloaded = await self._download_from_curseforge(context, cache_dir)
        if downloaded:
            return downloaded

        return {
            "enabled": True,
            "status": "unavailable",
            "source": "none",
            "message": "未找到匹配版本的 I18nUpdateMod，已降级跳过",
            "file_path": None,
            "filename": None,
            "loader": context.loader,
            "loader_version": context.loader_version,
            "mc_version": context.mc_version,
        }

    def _load_options(self, db: Session) -> dict:
        keys = {SETTING_INCLUDE_I18N_MOD, SETTING_I18N_CACHE_DIR}
        rows = db.query(Setting).filter(Setting.key.in_(keys)).all()
        values = {row.key: row.value for row in rows}
        values.setdefault(SETTING_INCLUDE_I18N_MOD, "false")
        values.setdefault(SETTING_I18N_CACHE_DIR, DEFAULT_CACHE_DIR)
        return values

    def _build_context(self, task: TranslationTask, local_root: Optional[str]) -> I18nTargetContext:
        scan_result = self._load_json_dict(task.scan_result_json)
        task_config = self._load_json_dict(task.config_json)

        version_json_candidates = [
            scan_result.get("version_json_path"),
        ]
        selected_version_root = str(scan_result.get("selected_version_root") or "").strip()
        game_name = str(scan_result.get("game_name") or "").strip()
        if selected_version_root and game_name:
            version_json_candidates.append(os.path.join(selected_version_root, f"{game_name}.json"))

        for candidate in [local_root, scan_result.get("work_root"), scan_result.get("minecraft_root"), task.local_path, task_config.get("local_path")]:
            value = str(candidate or "").strip()
            if not value:
                continue
            abs_value = os.path.abspath(value)
            if os.path.isdir(abs_value):
                version_json_candidates.append(os.path.join(abs_value, f"{os.path.basename(abs_value)}.json"))

        version_json_path = next(
            (os.path.abspath(path) for path in version_json_candidates if path and os.path.isfile(os.path.abspath(path))),
            None,
        )

        mc_version = str(scan_result.get("mc_version") or task_config.get("mc_version") or "").strip()
        loader = self._normalize_loader(scan_result.get("loader") or task_config.get("loader"))
        loader_version = str(scan_result.get("loader_version") or task_config.get("loader_version") or "").strip() or None
        if version_json_path:
            parsed_mc, parsed_loader, parsed_loader_version = self._parse_version_json(version_json_path)
            if not mc_version:
                mc_version = parsed_mc
            if not loader:
                loader = parsed_loader
            if not loader_version:
                loader_version = parsed_loader_version

        instance_root = None
        for candidate in [local_root, scan_result.get("work_root"), task.local_path, task_config.get("local_path")]:
            value = str(candidate or "").strip()
            if value and os.path.isdir(os.path.abspath(value)):
                instance_root = os.path.abspath(value)
                break

        return I18nTargetContext(
            mc_version=mc_version,
            loader=loader,
            loader_version=loader_version,
            instance_root=instance_root,
            version_json_path=version_json_path,
        )

    def _parse_version_json(self, version_json_path: str) -> tuple[str, Optional[str], Optional[str]]:
        try:
            with open(version_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            logger.warning("Failed to read version json %s: %s", version_json_path, exc)
            return "", None, None

        arguments = data.get("arguments", {}) if isinstance(data, dict) else {}
        game_args = arguments.get("game", []) if isinstance(arguments, dict) else []
        mc_version = ""
        loader = None
        loader_version = None
        if isinstance(game_args, list):
            for index, arg in enumerate(game_args):
                if arg == "--fml.mcVersion" and index + 1 < len(game_args):
                    mc_version = str(game_args[index + 1] or "").strip() or mc_version
                elif arg == "--fml.neoForgeVersion" and index + 1 < len(game_args):
                    loader = "neoforge"
                    loader_version = str(game_args[index + 1] or "").strip() or loader_version
                elif arg == "--fml.forgeVersion" and index + 1 < len(game_args):
                    loader = "forge"
                    loader_version = str(game_args[index + 1] or "").strip() or loader_version
                elif arg == "--launchTarget" and index + 1 < len(game_args):
                    target = str(game_args[index + 1] or "").strip().lower()
                    if not loader and "neoforge" in target:
                        loader = "neoforge"
                    elif not loader and "forge" in target:
                        loader = "forge"
        libraries = data.get("libraries", []) if isinstance(data, dict) else []
        if not loader and isinstance(libraries, list):
            for library in libraries:
                if not isinstance(library, dict):
                    continue
                name = str(library.get("name") or "").lower()
                if name.startswith("net.neoforged:"):
                    return mc_version, "neoforge", _extract_maven_version(name)
                if name.startswith("net.minecraftforge:"):
                    return mc_version, "forge", _extract_maven_version(name)
                if name.startswith("net.fabricmc:"):
                    return mc_version, "fabric", _extract_maven_version(name)
                if name.startswith("org.quiltmc:"):
                    return mc_version, "quilt", _extract_maven_version(name)
        return mc_version, loader, loader_version

    def _find_local_existing(self, instance_root: Optional[str]) -> Optional[str]:
        if not instance_root:
            return None
        mods_dir = os.path.join(instance_root, "mods")
        if not os.path.isdir(mods_dir):
            return None
        for filename in sorted(os.listdir(mods_dir)):
            if I18N_MOD_FILE_PATTERN.search(filename or ""):
                candidate = os.path.join(mods_dir, filename)
                if os.path.isfile(candidate):
                    return candidate
        return None

    def _find_cached_file(self, cache_dir: str, mc_version: str, loader: Optional[str]) -> Optional[str]:
        preferred_loaders = [loader] if loader else []
        preferred_loaders.extend([name for name in LOADER_SYNONYMS if name not in preferred_loaders])
        for loader_name in preferred_loaders:
            candidate_dir = os.path.join(cache_dir, loader_name or "unknown", mc_version)
            if not os.path.isdir(candidate_dir):
                continue
            for filename in sorted(os.listdir(candidate_dir)):
                if filename.lower().endswith(".jar"):
                    candidate = os.path.join(candidate_dir, filename)
                    if os.path.isfile(candidate):
                        return candidate
        return None

    async def _download_from_modrinth(self, context: I18nTargetContext, cache_dir: str) -> Optional[dict]:
        params = {
            "loaders": json.dumps([context.loader] if context.loader else []),
            "game_versions": json.dumps([context.mc_version]),
        }
        headers = {"Accept": "application/json", "User-Agent": DEFAULT_USER_AGENT}
        url = f"{MODRINTH_BASE_URL}/project/{I18N_MOD_PROJECT_SLUG}/version"
        try:
            async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                items = response.json()
            if not isinstance(items, list):
                items = []
            for version in items:
                file_info = self._pick_modrinth_file(version)
                if not file_info:
                    continue
                saved_path = await self._download_file(
                    url=file_info["url"],
                    filename=file_info["filename"],
                    cache_dir=cache_dir,
                    loader=context.loader,
                    mc_version=context.mc_version,
                )
                if saved_path:
                    return {
                        "enabled": True,
                        "status": "downloaded_modrinth",
                        "source": "modrinth",
                        "message": "已从 Modrinth 下载匹配的 I18nUpdateMod",
                        "file_path": saved_path,
                        "filename": os.path.basename(saved_path),
                        "loader": context.loader,
                        "loader_version": context.loader_version,
                        "mc_version": context.mc_version,
                        "version_id": str(version.get("id") or ""),
                    }
        except Exception as exc:
            logger.warning(
                "Failed to download I18nUpdateMod from Modrinth for mc=%s loader=%s: %s",
                context.mc_version,
                context.loader,
                exc,
            )
        return None

    async def _download_from_curseforge(self, context: I18nTargetContext, cache_dir: str) -> Optional[dict]:
        api_key = str(getattr(settings, "CURSEFORGE_API_KEY", "") or "").strip()
        if not api_key:
            return None
        headers = {"Accept": "application/json", "x-api-key": api_key}
        try:
            async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
                search_resp = await client.get(
                    f"{CURSEFORGE_BASE_URL}/mods/search",
                    params={"gameId": 432, "searchFilter": I18N_MOD_SEARCH_NAME, "pageSize": 10},
                    headers=headers,
                )
                search_resp.raise_for_status()
                search_items = (search_resp.json() or {}).get("data", [])
                project = self._pick_curseforge_project(search_items)
                if not project:
                    return None

                files_resp = await client.get(
                    f"{CURSEFORGE_BASE_URL}/mods/{project['id']}/files",
                    params={"pageSize": 200},
                    headers=headers,
                )
                files_resp.raise_for_status()
                file_items = (files_resp.json() or {}).get("data", [])

            file_info = self._pick_curseforge_file(file_items, context.mc_version, context.loader)
            if not file_info:
                return None
            download_url = str(file_info.get("downloadUrl") or "").strip()
            filename = str(file_info.get("fileName") or "I18nUpdateMod.jar").strip() or "I18nUpdateMod.jar"
            if not download_url:
                return None
            saved_path = await self._download_file(
                url=download_url,
                filename=filename,
                cache_dir=cache_dir,
                loader=context.loader,
                mc_version=context.mc_version,
            )
            if not saved_path:
                return None
            return {
                "enabled": True,
                "status": "downloaded_curseforge",
                "source": "curseforge",
                "message": "已从 CurseForge 下载匹配的 I18nUpdateMod",
                "file_path": saved_path,
                "filename": os.path.basename(saved_path),
                "loader": context.loader,
                "loader_version": context.loader_version,
                "mc_version": context.mc_version,
                "version_id": str(file_info.get("id") or ""),
            }
        except Exception as exc:
            logger.warning(
                "Failed to download I18nUpdateMod from CurseForge for mc=%s loader=%s: %s",
                context.mc_version,
                context.loader,
                exc,
            )
            return None

    def _pick_modrinth_file(self, version: dict) -> Optional[dict]:
        files = version.get("files", []) if isinstance(version, dict) else []
        for file_info in files:
            if not isinstance(file_info, dict):
                continue
            filename = str(file_info.get("filename") or "").strip()
            url = str(file_info.get("url") or "").strip()
            if filename.lower().endswith(".jar") and url:
                return {"filename": filename, "url": url}
        return None

    def _pick_curseforge_project(self, items: list) -> Optional[dict]:
        if not isinstance(items, list):
            return None
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip().lower()
            slug = str(item.get("slug") or "").strip().lower()
            if name == I18N_MOD_SEARCH_NAME.lower() or I18N_MOD_PROJECT_SLUG in slug:
                return item
        return items[0] if items else None

    def _pick_curseforge_file(self, items: list, mc_version: str, loader: Optional[str]) -> Optional[dict]:
        if not isinstance(items, list):
            return None
        exact_matches = []
        loose_matches = []
        for item in items:
            if not isinstance(item, dict):
                continue
            filename = str(item.get("fileName") or "").strip().lower()
            if not filename.endswith(".jar"):
                continue
            game_versions = item.get("gameVersions", []) or []
            normalized_versions = {_normalize_token(value) for value in game_versions if str(value).strip()}
            if mc_version and _normalize_token(mc_version) not in normalized_versions:
                continue
            if loader and self._has_loader_tokens(normalized_versions):
                if not self._loader_matches_tokens(loader, normalized_versions):
                    continue
                exact_matches.append(item)
            else:
                loose_matches.append(item)
        if exact_matches:
            return exact_matches[0]
        if loose_matches:
            return loose_matches[0]
        return None

    async def _download_file(self, url: str, filename: str, cache_dir: str, loader: Optional[str], mc_version: str) -> Optional[str]:
        target_dir = os.path.join(cache_dir, loader or "unknown", mc_version)
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, filename)
        if os.path.isfile(target_path):
            return target_path

        try:
            async with httpx.AsyncClient(timeout=max(settings.HTTP_TIMEOUT, 120), follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                with open(target_path, "wb") as f:
                    f.write(response.content)
            return target_path
        except Exception as exc:
            logger.warning("Failed to download %s to %s: %s", url, target_path, exc)
            try:
                if os.path.isfile(target_path):
                    os.remove(target_path)
            except Exception:
                pass
            return None

    def _load_json_dict(self, raw: Optional[str]) -> dict:
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _normalize_loader(self, value) -> Optional[str]:
        normalized = _normalize_token(value)
        for loader, synonyms in LOADER_SYNONYMS.items():
            if normalized in {_normalize_token(name) for name in synonyms}:
                return loader
        return normalized or None

    def _as_bool(self, value, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        if not normalized:
            return default
        return normalized in TRUTHY_VALUES

    def _has_loader_tokens(self, values: set[str]) -> bool:
        known = {token for synonyms in LOADER_SYNONYMS.values() for token in {_normalize_token(v) for v in synonyms}}
        return any(value in known for value in values)

    def _loader_matches_tokens(self, loader: str, values: set[str]) -> bool:
        synonyms = {_normalize_token(value) for value in LOADER_SYNONYMS.get(loader, {loader})}
        return any(value in synonyms for value in values)



def _normalize_token(value) -> str:
    return str(value or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")



def _extract_maven_version(name: str) -> Optional[str]:
    parts = str(name or "").split(":")
    if len(parts) >= 3:
        version = parts[2].strip()
        return version or None
    return None
