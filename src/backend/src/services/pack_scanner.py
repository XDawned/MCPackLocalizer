"""
本地整合包扫描服务

提供本地整合包目录的格式检测、内容发现、Mod 清单扫描和待翻译区域识别。
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

try:
    from ..models.local_modpack import LocalModpack
    from ..parsers.ftb_lang_snbt_parser import FtbLangSnbtParser
    from ..parsers.ftb_quest_nbt_parser import FtbQuestNbtParser
    from ..parsers.parser_registry import ParserRegistry
    from .translation_metadata import build_apply_metadata, is_probably_i18n_key
except ImportError:
    from src.models.local_modpack import LocalModpack  # type: ignore
    from src.parsers.ftb_lang_snbt_parser import FtbLangSnbtParser  # type: ignore
    from src.parsers.ftb_quest_nbt_parser import FtbQuestNbtParser  # type: ignore
    from src.parsers.parser_registry import ParserRegistry  # type: ignore
    from src.services.translation_metadata import build_apply_metadata, is_probably_i18n_key  # type: ignore

logger = logging.getLogger(__name__)

LANGUAGE_AREA_TYPES = {
    "ftbquests_lang",
    "kubejs_json",
    "kubejs_lang",
    "kubejs_js",
}
AREA_LABELS = {
    "mod_lang": "模组语言文件",
    "ftb_quests": "FTB 任务原文",
    "ftbquests_lang": "FTB Quests 语言树",
    "better_questing": "Better Questing 任务",
    "kubejs_json": "KubeJS JSON",
    "kubejs_lang": "KubeJS Lang",
    "kubejs_js": "KubeJS JS 文本",
}
ENGLISH_LANG_CODES = {"en_us", "en_ud"}
SUPPORTED_FTB_LANG_SUFFIXES = {".json", ".lang", ".snbt"}
SUPPORTED_FTB_QUEST_SUFFIXES = {".snbt", ".nbt"}
SUPPORTED_KUBEJS_SUFFIXES = {".json", ".lang", ".js"}


class PackScanError(ValueError):
    """可预期的整合包扫描业务错误。"""


@dataclass
class VersionCandidateInfo:
    game_name: str
    version_root: str
    mc_version: str
    source_field: Optional[str]
    has_version_work_root: bool
    version_work_root: Optional[str]
    fallback_minecraft_root_usable: bool
    loader: Optional[str] = None
    loader_version: Optional[str] = None
    version_json_path: Optional[str] = None


@dataclass
class PathResolution:
    input_path: str
    minecraft_root: str
    selected_version_root: Optional[str]
    work_root: str
    work_root_source: str
    game_name: Optional[str]
    mc_version: str
    version_resolution_source: Optional[str]
    candidates: List[VersionCandidateInfo]
    has_versions_structure: bool
    fallback_minecraft_root_usable: bool
    loader: Optional[str] = None
    loader_version: Optional[str] = None
    version_json_path: Optional[str] = None


@dataclass
class LegacyVersionInfo:
    mc_version: str
    source: Optional[str]
    loader: Optional[str] = None
    loader_version: Optional[str] = None
    version_json_path: Optional[str] = None


PACK_TYPE_DETECTORS = {
    "curseforge": ["manifest.json"],
    "hmcl": ["modpack.json"],
    "multimc": ["mmc-pack.json"],
    "modrinth": ["modrinth.index.json"],
    "mcbbs": ["manifest.json"],
}



def _generate_scan_id() -> str:
    today = date.today().strftime("%Y%m%d")
    short_id = uuid.uuid4().hex[:8]
    return f"scan_{today}_{short_id}"


class PackScannerService:
    """本地整合包扫描服务。"""

    def __init__(self):
        self.registry = ParserRegistry()
        self._ftb_lang_snbt_parser = FtbLangSnbtParser()
        self._ftb_quest_nbt_parser = FtbQuestNbtParser()
        self._scan_cache: Dict[str, dict] = {}

    def _has_work_markers(self, path: str) -> bool:
        return any(os.path.isdir(os.path.join(path, name)) for name in ["mods", "config", "kubejs"])

    def _get_minecraft_root(self, local_path: str) -> str:
        normalized = os.path.abspath(local_path)
        version_path = os.path.join(normalized, "versions")
        dot_minecraft = os.path.join(normalized, ".minecraft")
        parent_dir = os.path.dirname(normalized)
        grandparent_dir = os.path.dirname(parent_dir)
        if os.path.isdir(version_path):
            return normalized
        if os.path.isfile(os.path.join(normalized, f"{os.path.basename(normalized)}.json")) and os.path.basename(parent_dir).lower() == "versions":
            return grandparent_dir
        if os.path.isdir(dot_minecraft):
            return dot_minecraft
        return normalized

    def detect_pack_type(self, local_path: str) -> str:
        """检测整合包格式类型。"""
        if not os.path.isdir(local_path):
            return "unknown"

        if os.path.isfile(os.path.join(local_path, "modrinth.index.json")):
            return "modrinth"

        manifest_path = os.path.join(local_path, "manifest.json")
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "addons" in data:
                    return "mcbbs"
                return "curseforge"
            except Exception:
                return "curseforge"

        if os.path.isfile(os.path.join(local_path, "modpack.json")):
            return "hmcl"

        if os.path.isfile(os.path.join(local_path, "mmc-pack.json")):
            return "multimc"

        real_path = self._get_minecraft_root(local_path)
        if real_path != os.path.abspath(local_path):
            return "standard"
        if self._has_work_markers(real_path) or os.path.isdir(os.path.join(real_path, "versions")):
            return "standard"

        return "unknown"

    def _read_json_file(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _resolve_version_json(self, version_root: str, game_name: str) -> LegacyVersionInfo:
        version_json = os.path.join(version_root, f"{game_name}.json")
        if not os.path.isfile(version_json):
            return LegacyVersionInfo(mc_version="", source=None, version_json_path=None)

        try:
            data = self._read_json_file(version_json)
        except Exception as exc:
            logger.warning("Failed to read version json %s: %s", version_json, exc)
            return LegacyVersionInfo(mc_version="", source=None, version_json_path=version_json)

        inherits_from = data.get("inheritsFrom")
        client_version = data.get("clientVersion")
        if isinstance(inherits_from, str) and inherits_from.strip():
            mc_version = inherits_from.strip()
            source = "inheritsFrom"
        elif isinstance(client_version, str) and client_version.strip():
            mc_version = client_version.strip()
            source = "clientVersion"
        else:
            mc_version = self._extract_mc_version_from_version_json_data(data)
            source = "clientVersion" if mc_version else None

        loader, loader_version = self._extract_loader_from_version_json_data(data)
        return LegacyVersionInfo(
            mc_version=mc_version,
            source=source,
            loader=loader,
            loader_version=loader_version,
            version_json_path=version_json,
        )

    def _extract_mc_version_from_version_json_data(self, data: dict) -> str:
        arguments = data.get("arguments", {}) if isinstance(data, dict) else {}
        game_args = arguments.get("game", []) if isinstance(arguments, dict) else []
        if isinstance(game_args, list):
            for index, arg in enumerate(game_args):
                if arg == "--fml.mcVersion" and index + 1 < len(game_args):
                    next_value = game_args[index + 1]
                    if isinstance(next_value, str) and next_value.strip():
                        return next_value.strip()
        return ""

    def _extract_loader_from_version_json_data(self, data: dict) -> tuple[Optional[str], Optional[str]]:
        arguments = data.get("arguments", {}) if isinstance(data, dict) else {}
        game_args = arguments.get("game", []) if isinstance(arguments, dict) else []
        libraries = data.get("libraries", []) if isinstance(data, dict) else []
        launch_target = ""
        if isinstance(game_args, list):
            for index, arg in enumerate(game_args):
                if arg == "--fml.neoForgeVersion" and index + 1 < len(game_args):
                    version = str(game_args[index + 1] or "").strip()
                    return "neoforge", version or None
                if arg == "--fml.forgeVersion" and index + 1 < len(game_args):
                    version = str(game_args[index + 1] or "").strip()
                    return "forge", version or None
                if arg == "--launchTarget" and index + 1 < len(game_args):
                    launch_target = str(game_args[index + 1] or "").strip().lower()
        if "neoforge" in launch_target:
            return "neoforge", None
        if "forge" in launch_target:
            return "forge", None

        if isinstance(libraries, list):
            for library in libraries:
                if not isinstance(library, dict):
                    continue
                name = str(library.get("name") or "").lower()
                if name.startswith("net.neoforged:"):
                    return "neoforge", _extract_maven_version(name)
                if name.startswith("net.minecraftforge:"):
                    return "forge", _extract_maven_version(name)
                if name.startswith("net.fabricmc:"):
                    return "fabric", _extract_maven_version(name)
                if name.startswith("org.quiltmc:"):
                    return "quilt", _extract_maven_version(name)
        return None, None

    def _discover_version_candidates(self, minecraft_root: str) -> List[VersionCandidateInfo]:
        versions_dir = os.path.join(minecraft_root, "versions")
        if not os.path.isdir(versions_dir):
            return []

        candidates: List[VersionCandidateInfo] = []
        fallback_usable = self._has_work_markers(minecraft_root)
        for entry in sorted(os.listdir(versions_dir)):
            version_root = os.path.join(versions_dir, entry)
            if not os.path.isdir(version_root):
                continue

            version_info = self._resolve_version_json(version_root, entry)
            has_version_work_root = self._has_work_markers(version_root)
            candidates.append(
                VersionCandidateInfo(
                    game_name=entry,
                    version_root=version_root,
                    mc_version=version_info.mc_version,
                    source_field=version_info.source,
                    has_version_work_root=has_version_work_root,
                    version_work_root=version_root if has_version_work_root else None,
                    fallback_minecraft_root_usable=fallback_usable,
                    loader=version_info.loader,
                    loader_version=version_info.loader_version,
                    version_json_path=version_info.version_json_path,
                )
            )
        return candidates

    def discover_directory(self, local_path: str) -> dict:
        """发现本地目录中的版本候选与扫描根信息。"""
        if not local_path or not os.path.isdir(local_path):
            raise PackScanError("指定路径不存在或不是目录")

        input_path = os.path.abspath(local_path)
        minecraft_root = self._get_minecraft_root(input_path)
        pack_type = self.detect_pack_type(input_path)
        candidates = self._discover_version_candidates(minecraft_root)
        fallback_usable = self._has_work_markers(minecraft_root)
        has_versions_structure = os.path.isdir(os.path.join(minecraft_root, "versions"))
        direct_scan_compatible = not candidates and fallback_usable
        recommended_action = "select_game_name" if candidates else "scan_direct"

        return {
            "input_path": input_path,
            "minecraft_root": minecraft_root,
            "pack_type": pack_type,
            "candidates": [
                {
                    "game_name": candidate.game_name,
                    "version_root": candidate.version_root,
                    "mc_version": candidate.mc_version,
                    "source_field": candidate.source_field,
                    "has_version_work_root": candidate.has_version_work_root,
                    "version_work_root": candidate.version_work_root,
                    "fallback_minecraft_root_usable": candidate.fallback_minecraft_root_usable,
                    "loader": candidate.loader,
                    "loader_version": candidate.loader_version,
                    "version_json_path": candidate.version_json_path,
                }
                for candidate in candidates
            ],
            "has_versions_structure": has_versions_structure,
            "fallback_minecraft_root_usable": fallback_usable,
            "direct_scan_compatible": direct_scan_compatible,
            "recommended_action": recommended_action,
        }

    def _infer_mc_version_from_metadata(self, local_path: str, pack_type: str) -> LegacyVersionInfo:
        try:
            if pack_type in ("curseforge", "mcbbs"):
                manifest_path = os.path.join(local_path, "manifest.json")
                if os.path.isfile(manifest_path):
                    data = self._read_json_file(manifest_path)
                    version = data.get("minecraft", {}).get("version", "")
                    if isinstance(version, str) and version.strip():
                        return LegacyVersionInfo(mc_version=version.strip(), source="legacy")
            elif pack_type == "modrinth":
                mr_path = os.path.join(local_path, "modrinth.index.json")
                if os.path.isfile(mr_path):
                    data = self._read_json_file(mr_path)
                    version = data.get("dependencies", {}).get("minecraft", "")
                    if isinstance(version, str) and version.strip():
                        return LegacyVersionInfo(mc_version=version.strip(), source="legacy")
        except Exception as exc:
            logger.warning("Failed to infer version from metadata for %s: %s", local_path, exc)
        return LegacyVersionInfo(mc_version="", source=None)

    def _infer_name(self, local_path: str, pack_type: str) -> str:
        """尝试获取整合包名称"""
        try:
            if pack_type in ("curseforge", "mcbbs"):
                manifest_path = os.path.join(local_path, "manifest.json")
                if os.path.isfile(manifest_path):
                    data = self._read_json_file(manifest_path)
                    return data.get("name", "")
        except Exception:
            pass
        return os.path.basename(os.path.abspath(local_path))

    def _resolve_scan_paths(self, local_path: str, game_name: Optional[str]) -> PathResolution:
        if not local_path or not os.path.isdir(local_path):
            raise PackScanError("指定路径不存在或不是目录")

        input_path = os.path.abspath(local_path)
        minecraft_root = self._get_minecraft_root(input_path)
        candidates = self._discover_version_candidates(minecraft_root)
        fallback_usable = self._has_work_markers(minecraft_root)
        has_versions_structure = os.path.isdir(os.path.join(minecraft_root, "versions"))

        if candidates:
            selected: Optional[VersionCandidateInfo] = None
            requested_game_name = game_name
            if not requested_game_name and os.path.basename(os.path.dirname(input_path)).lower() == "versions":
                requested_game_name = os.path.basename(input_path)

            if requested_game_name:
                for candidate in candidates:
                    if candidate.game_name == requested_game_name:
                        selected = candidate
                        break
                if selected is None:
                    raise PackScanError(f"未找到指定的 game_name: {requested_game_name}")
            elif len(candidates) == 1:
                selected = candidates[0]
            else:
                names = ", ".join(candidate.game_name for candidate in candidates)
                raise PackScanError(f"检测到多个游戏实例，请先选择 game_name: {names}")

            if selected.has_version_work_root:
                work_root = selected.version_work_root or selected.version_root
                work_root_source = "version"
            elif fallback_usable:
                work_root = minecraft_root
                work_root_source = "minecraft_root"
            else:
                raise PackScanError("所选版本目录和 .minecraft 根目录均不存在可用的 mods/config/kubejs，无法扫描")

            return PathResolution(
                input_path=input_path,
                minecraft_root=minecraft_root,
                selected_version_root=selected.version_root,
                work_root=work_root,
                work_root_source=work_root_source,
                game_name=selected.game_name,
                mc_version=selected.mc_version,
                version_resolution_source=selected.source_field,
                candidates=candidates,
                has_versions_structure=has_versions_structure,
                fallback_minecraft_root_usable=fallback_usable,
                loader=selected.loader,
                loader_version=selected.loader_version,
                version_json_path=selected.version_json_path,
            )

        if fallback_usable:
            return PathResolution(
                input_path=input_path,
                minecraft_root=minecraft_root,
                selected_version_root=None,
                work_root=minecraft_root,
                work_root_source="minecraft_root",
                game_name=game_name,
                mc_version="",
                version_resolution_source=None,
                candidates=candidates,
                has_versions_structure=has_versions_structure,
                fallback_minecraft_root_usable=fallback_usable,
                loader=None,
                loader_version=None,
                version_json_path=None,
            )

        if has_versions_structure:
            raise PackScanError("未发现可用版本候选，且 .minecraft 根目录不存在可用的 mods/config/kubejs，无法扫描")
        raise PackScanError("指定目录中未找到可扫描的 mods/config/kubejs 或可用 versions 候选")

    def _scan_mod_list(self, work_root: str) -> List[dict]:
        """在工作根下扫描 Mods"""
        mods_dir = os.path.join(work_root, "mods")
        mod_list = []
        if os.path.isdir(mods_dir):
            for filename in os.listdir(mods_dir):
                if filename.lower().endswith(".jar"):
                    name = filename.rsplit(".jar", 1)[0]
                    mod_list.append(
                        {
                            "name": name,
                            "file": filename,
                            "path": os.path.join(mods_dir, filename),
                        }
                    )
        return mod_list

    def _scan_mod_lang_area(self, work_root: str) -> dict:
        mods = self._scan_mod_list(work_root)
        items = []
        for mod in mods:
            jar_path = mod["path"]
            try:
                entries = self.registry.extract(jar_path)
                if entries:
                    items.append(
                        {
                            "mod_name": mod["name"],
                            "file": jar_path,
                            "path": jar_path,
                            "entry_count": len(entries),
                            "entries": entries,
                            **self._preview_target_info("mod_lang", jar_path, jar_path, entries, work_root),
                        }
                    )
            except Exception:
                pass
        return {"items": items, "count": len(items)}

    def _scan_ftb_quests_area(self, work_root: str) -> dict:
        """从工作根寻找 FTB Quests 原始任务文件。"""
        quests_dir = os.path.join(work_root, "config", "ftbquests", "quests")
        items = []
        if os.path.isdir(quests_dir):
            for root, dirs, files in os.walk(quests_dir):
                dirs[:] = [directory for directory in dirs if directory.lower() != "lang"]
                for filename in files:
                    if os.path.splitext(filename)[1].lower() not in SUPPORTED_FTB_QUEST_SUFFIXES:
                        continue
                    filepath = os.path.join(root, filename)
                    try:
                        if filename.lower().endswith(".snbt") and self._ftb_lang_snbt_parser.can_parse(filepath):
                            continue
                        if filename.lower().endswith(".nbt") and not self._ftb_quest_nbt_parser.can_parse(filepath):
                            continue
                        entries = self.registry.extract(filepath)
                        direct_entries = {
                            key: value
                            for key, value in entries.items()
                            if not is_probably_i18n_key(value)
                        }
                        skipped_i18n = len(entries) - len(direct_entries)
                        if direct_entries:
                            items.append(
                                {
                                    "file": os.path.relpath(filepath, quests_dir),
                                    "path": filepath,
                                    "entry_count": len(direct_entries),
                                    "skipped_i18n_keys": skipped_i18n,
                                    "entries": direct_entries,
                                    **self._preview_target_info("ftb_quests", filename, filepath, direct_entries, work_root),
                                }
                            )
                    except Exception:
                        pass
        return {"items": items, "count": len(items)}

    def _scan_ftb_quests_lang_area(self, work_root: str) -> dict:
        ftb_root = os.path.join(work_root, "config", "ftbquests")
        items = []
        if not os.path.isdir(ftb_root):
            return {"items": items, "count": 0}

        for root, _, files in os.walk(ftb_root):
            for filename in files:
                filepath = os.path.join(root, filename)
                suffix = os.path.splitext(filename)[1].lower()
                if suffix == ".snbt":
                    if not (self._is_english_locale_file(filepath) or self._ftb_lang_snbt_parser.can_parse(filepath)):
                        continue
                elif not self._is_english_locale_file(filepath):
                    continue
                try:
                    entries = self.registry.extract(filepath)
                    if entries:
                        items.append(
                            {
                                "file": os.path.relpath(filepath, ftb_root),
                                "path": filepath,
                                "entry_count": len(entries),
                                "entries": entries,
                                **self._preview_target_info("ftbquests_lang", filename, filepath, entries, work_root),
                            }
                        )
                except Exception:
                    pass
        return {"items": items, "count": len(items)}

    def _scan_bq_area(self, work_root: str) -> dict:
        """从工作根寻找 BetterQuesting"""
        bq_path = os.path.join(work_root, "config", "betterquesting", "DefaultQuests.json")
        items = []
        if os.path.isfile(bq_path):
            try:
                entries = self.registry.extract(bq_path)
                if entries:
                    items.append(
                        {
                            "file": "DefaultQuests.json",
                            "path": bq_path,
                            "entry_count": len(entries),
                            "entries": entries,
                            **self._preview_target_info("better_questing", "DefaultQuests.json", bq_path, entries, work_root),
                        }
                    )
            except Exception:
                pass
        return {"items": items, "count": len(items)}

    def _scan_kubejs_areas(self, work_root: str) -> dict:
        kubejs_root = os.path.join(work_root, "kubejs")
        result = {
            "kubejs_json": {"items": [], "count": 0},
            "kubejs_lang": {"items": [], "count": 0},
            "kubejs_js": {"items": [], "count": 0},
        }
        if not os.path.isdir(kubejs_root):
            return result

        for root, _, files in os.walk(kubejs_root):
            for filename in files:
                suffix = os.path.splitext(filename)[1].lower()
                if suffix not in SUPPORTED_KUBEJS_SUFFIXES:
                    continue
                filepath = os.path.join(root, filename)
                area_type = self._resolve_kubejs_area_type(filepath)
                if not area_type:
                    continue
                try:
                    entries = self.registry.extract(filepath)
                    if not entries:
                        continue
                    result[area_type]["items"].append(
                        {
                            "file": os.path.relpath(filepath, kubejs_root),
                            "path": filepath,
                            "entry_count": len(entries),
                            "entries": entries,
                            **self._preview_target_info(area_type, filename, filepath, entries, work_root),
                        }
                    )
                except Exception:
                    pass

        for area_type in result:
            result[area_type]["count"] = len(result[area_type]["items"])
        return result

    def _resolve_kubejs_area_type(self, file_path: str) -> Optional[str]:
        lowered = file_path.replace("\\", "/").lower()
        if lowered.endswith(".lang"):
            if self._is_non_english_lang_directory_file(lowered):
                return None
            return "kubejs_lang"
        if lowered.endswith(".json"):
            if self._is_non_english_lang_directory_file(lowered):
                return None
            return "kubejs_json"
        if lowered.endswith(".js"):
            return "kubejs_js"
        return None

    def _is_non_english_lang_directory_file(self, normalized_path: str) -> bool:
        normalized = normalized_path.replace("\\", "/").lower()
        if "/lang/" not in f"/{normalized}":
            return False
        file_stem = os.path.splitext(os.path.basename(normalized))[0]
        if file_stem in ENGLISH_LANG_CODES:
            return False
        if file_stem and len(file_stem) == 5 and "_" in file_stem:
            return True
        return False

    def _is_english_locale_file(self, file_path: str) -> bool:
        normalized = file_path.replace("\\", "/").lower()
        suffix = os.path.splitext(normalized)[1]
        if suffix not in SUPPORTED_FTB_LANG_SUFFIXES:
            return False
        parts = normalized.split("/")
        file_stem = os.path.splitext(os.path.basename(normalized))[0]
        return file_stem in ENGLISH_LANG_CODES or any(part in ENGLISH_LANG_CODES for part in parts)

    def _preview_target_info(
        self,
        area_type: str,
        source_file: str,
        source_path: str,
        entries: dict,
        work_root: str,
    ) -> dict:
        if not entries:
            return {"target_strategy": None, "target_path": None}
        first_key, first_value = next(iter(entries.items()))
        metadata = build_apply_metadata(
            area_type=area_type,
            source_file=source_file,
            source_path=source_path,
            key=first_key,
            local_root=work_root,
            original_text=first_value,
        )
        return {
            "target_strategy": metadata.get("target_strategy"),
            "target_path": metadata.get("target_path") or metadata.get("target_relative_path"),
        }

    def _build_areas(self, *area_entries: tuple[str, dict]) -> List[dict]:
        areas: List[dict] = []
        for area_type, area_data in area_entries:
            if area_data.get("count", 0) <= 0:
                continue
            areas.append(
                {
                    "type": area_type,
                    "label": AREA_LABELS.get(area_type, area_type),
                    "count": area_data["count"],
                    "items": [self._build_area_item_summary(area_type, item) for item in area_data.get("items", [])],
                }
            )
        return areas

    def _build_area_item_summary(self, area_type: str, item: dict) -> dict:
        data = {
            "file": item.get("file") or item.get("path") or "",
            "entry_count": item.get("entry_count", 0),
            "target_strategy": item.get("target_strategy"),
            "target_path": item.get("target_path"),
        }
        if area_type == "mod_lang":
            data["mod_name"] = item.get("mod_name", "")
        if area_type == "ftb_quests" and item.get("skipped_i18n_keys"):
            data["skipped_i18n_keys"] = item.get("skipped_i18n_keys")
        return data

    def scan_directory(self, local_path: str, game_name: Optional[str] = None) -> dict:
        """主扫描入口。"""
        resolution = self._resolve_scan_paths(local_path, game_name)
        pack_type = self.detect_pack_type(resolution.input_path)
        metadata_version = self._infer_mc_version_from_metadata(resolution.input_path, pack_type)
        mc_version = resolution.mc_version or metadata_version.mc_version
        version_resolution_source = resolution.version_resolution_source or metadata_version.source
        loader = resolution.loader or metadata_version.loader
        loader_version = resolution.loader_version or metadata_version.loader_version
        version_json_path = resolution.version_json_path or metadata_version.version_json_path
        name = self._infer_name(resolution.input_path, pack_type)

        mod_lang = self._scan_mod_lang_area(resolution.work_root)
        ftb_quests = self._scan_ftb_quests_area(resolution.work_root)
        ftbquests_lang = self._scan_ftb_quests_lang_area(resolution.work_root)
        bq = self._scan_bq_area(resolution.work_root)
        kubejs_areas = self._scan_kubejs_areas(resolution.work_root)
        mod_list = self._scan_mod_list(resolution.work_root)
        areas = self._build_areas(
            ("mod_lang", mod_lang),
            ("ftb_quests", ftb_quests),
            ("ftbquests_lang", ftbquests_lang),
            ("better_questing", bq),
            ("kubejs_json", kubejs_areas["kubejs_json"]),
            ("kubejs_lang", kubejs_areas["kubejs_lang"]),
            ("kubejs_js", kubejs_areas["kubejs_js"]),
        )

        scan_id = _generate_scan_id()
        result = {
            "scan_id": scan_id,
            "pack_type": pack_type,
            "mc_version": mc_version,
            "loader": loader,
            "loader_version": loader_version,
            "name": name,
            "game_name": resolution.game_name,
            "mod_count": len(mod_list),
            "minecraft_root": resolution.minecraft_root,
            "selected_version_root": resolution.selected_version_root,
            "version_json_path": version_json_path,
            "work_root": resolution.work_root,
            "work_root_source": resolution.work_root_source,
            "version_resolution_source": version_resolution_source,
            "real_path": resolution.work_root,
            "areas": areas,
        }

        self._scan_cache[scan_id] = {
            "status": "completed",
            "result": result,
            "raw": {
                "mod_lang": mod_lang,
                "ftb_quests": ftb_quests,
                "ftbquests_lang": ftbquests_lang,
                "better_questing": bq,
                "kubejs_json": kubejs_areas["kubejs_json"],
                "kubejs_lang": kubejs_areas["kubejs_lang"],
                "kubejs_js": kubejs_areas["kubejs_js"],
            },
        }
        return result

    def get_status(self, scan_id: str) -> Optional[dict]:
        cache = self._scan_cache.get(scan_id)
        if cache is None:
            return None
        result = cache.get("result", {})
        return {
            "scan_id": scan_id,
            "status": cache.get("status", "completed"),
            "pack_type": result.get("pack_type"),
            "mc_version": result.get("mc_version"),
            "name": result.get("name"),
            "progress": 100.0,
            "error": cache.get("error"),
        }

    def extract_content(self, scan_id: str, selected_areas: Optional[List[str]] = None) -> List[dict]:
        cache = self._scan_cache.get(scan_id)
        if cache is None:
            raise PackScanError(f"Scan {scan_id} not found")

        raw = cache.get("raw", {})
        scan_result = cache.get("result", {}) or {}
        apply_root = (
            scan_result.get("work_root")
            or scan_result.get("minecraft_root")
            or scan_result.get("real_path")
            or ""
        )

        tasks: List[dict] = []
        area_map = {
            "mod_lang": raw.get("mod_lang", {}).get("items", []),
            "ftb_quests": raw.get("ftb_quests", {}).get("items", []),
            "ftbquests_lang": raw.get("ftbquests_lang", {}).get("items", []),
            "better_questing": raw.get("better_questing", {}).get("items", []),
            "kubejs_json": raw.get("kubejs_json", {}).get("items", []),
            "kubejs_lang": raw.get("kubejs_lang", {}).get("items", []),
            "kubejs_js": raw.get("kubejs_js", {}).get("items", []),
        }

        target_areas = selected_areas or list(area_map.keys())
        for area_type in target_areas:
            for item in area_map.get(area_type, []):
                source_file = item.get("file") or item.get("path") or ""
                source_path = item.get("path") or item.get("file") or ""
                entries = item.get("entries", {}) or {}
                for key, original_text in entries.items():
                    tasks.append(
                        {
                            "area_type": area_type,
                            "source_file": source_file,
                            "source_path": source_path,
                            "key": key,
                            "original_text": original_text,
                            "apply_metadata": build_apply_metadata(
                                area_type=area_type,
                                source_file=source_file,
                                source_path=source_path,
                                key=key,
                                local_root=apply_root,
                                original_text=original_text,
                            ),
                        }
                    )
        return tasks

    def save_to_db(self, db: Session, local_path: str, result: dict) -> LocalModpack:
        modpack = LocalModpack(
            name=result.get("name") or os.path.basename(os.path.abspath(local_path)),
            local_path=local_path,
            pack_type=result.get("pack_type"),
            mc_version=result.get("mc_version"),
        )
        modpack.mod_list = self._scan_mod_list(result.get("work_root", result.get("real_path", local_path)))
        db.add(modpack)
        db.commit()
        db.refresh(modpack)
        return modpack



def _extract_maven_version(name: str) -> Optional[str]:
    parts = str(name or "").split(":")
    if len(parts) >= 3:
        version = parts[2].strip()
        return version or None
    return None
