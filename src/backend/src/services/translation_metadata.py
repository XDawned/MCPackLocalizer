import json
import os
import re
from typing import Any, Dict, Iterable, List


ENGLISH_LANG_CODES = ("en_us", "en_ud")
I18N_LIKE_KEY_PATTERN = re.compile(r"^[a-z0-9_]+(?:[./:-][a-z0-9_]+)+$", re.IGNORECASE)


def normalize_relative_path(path: str) -> str:
    return str(path or "").replace("\\", "/").strip("/")


def is_probably_i18n_key(value: str) -> bool:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) < 3:
        return False
    if " " in normalized or "\n" in normalized:
        return False
    return bool(I18N_LIKE_KEY_PATTERN.fullmatch(normalized))


def build_mod_lang_metadata(source_file: str, source_path: str, key: str, original_text: str | None = None) -> dict:
    source_path_normalized = normalize_relative_path(source_path)
    modid = _infer_modid(source_file, source_path_normalized)
    actual_translation_key = _strip_modid_prefix(key, modid)
    target_relative_path = f"assets/{modid}/lang/zh_cn.json"
    return _build_metadata(
        area_type="mod_lang",
        target_strategy="resourcepack",
        target_relative_path=target_relative_path,
        source_relative_path=source_path_normalized,
        target_locator={
            "modid": modid,
            "translation_key": actual_translation_key,
            "source_key": key,
            "original_text": original_text or "",
        },
    )


def build_ftb_quests_metadata(
    source_path: str,
    source_file: str,
    key: str,
    local_root: str | None = None,
    original_text: str | None = None,
) -> dict:
    normalized_source_path = normalize_relative_path(source_path)
    relative_target = _relativize_local_file(normalized_source_path, local_root) or normalized_source_path
    target_strategy = "nbt_rewrite" if normalized_source_path.lower().endswith(".nbt") else "snbt_rewrite"
    return _build_metadata(
        area_type="ftb_quests",
        target_strategy=target_strategy,
        target_relative_path=relative_target,
        source_relative_path=relative_target,
        target_locator={
            "entry_key": key,
            "source_file": source_file,
            "original_text": original_text or "",
        },
    )


def build_ftbquests_lang_metadata(
    source_path: str,
    source_file: str,
    key: str,
    local_root: str | None = None,
    original_text: str | None = None,
) -> dict:
    normalized_source_path = normalize_relative_path(source_path)
    source_relative_path = _relativize_local_file(normalized_source_path, local_root) or normalized_source_path
    target_relative_path = _localize_language_path(source_relative_path, target_locale="zh_cn")
    return _build_metadata(
        area_type="ftbquests_lang",
        target_strategy="ftbquests_lang_file",
        target_relative_path=target_relative_path,
        source_relative_path=source_relative_path,
        target_locator={
            "entry_key": key,
            "source_file": source_file,
            "original_text": original_text or "",
        },
    )


def build_better_questing_metadata(
    source_path: str,
    source_file: str,
    key: str,
    local_root: str | None = None,
    original_text: str | None = None,
) -> dict:
    normalized_source_path = normalize_relative_path(source_path)
    relative_target = _relativize_local_file(normalized_source_path, local_root) or normalized_source_path
    return _build_metadata(
        area_type="better_questing",
        target_strategy="betterquesting_rewrite",
        target_relative_path=relative_target,
        source_relative_path=relative_target,
        target_locator={
            "entry_key": key,
            "source_file": source_file,
            "original_text": original_text or "",
        },
    )


def build_kubejs_json_metadata(
    source_path: str,
    source_file: str,
    key: str,
    local_root: str | None = None,
    original_text: str | None = None,
) -> dict:
    normalized_source_path = normalize_relative_path(source_path)
    source_relative_path = _relativize_local_file(normalized_source_path, local_root) or normalized_source_path
    is_localized_lang = _is_localizable_language_file(source_relative_path)
    target_relative_path = (
        _localize_language_path(source_relative_path, target_locale="zh_cn")
        if is_localized_lang
        else source_relative_path
    )
    target_strategy = "json_lang_file" if is_localized_lang else "json_rewrite"
    return _build_metadata(
        area_type="kubejs_json",
        target_strategy=target_strategy,
        target_relative_path=target_relative_path,
        source_relative_path=source_relative_path,
        target_locator={
            "entry_key": key,
            "source_file": source_file,
            "original_text": original_text or "",
        },
    )


def build_kubejs_lang_metadata(
    source_path: str,
    source_file: str,
    key: str,
    local_root: str | None = None,
    original_text: str | None = None,
) -> dict:
    normalized_source_path = normalize_relative_path(source_path)
    source_relative_path = _relativize_local_file(normalized_source_path, local_root) or normalized_source_path
    target_relative_path = _localize_language_path(source_relative_path, target_locale="zh_cn")
    return _build_metadata(
        area_type="kubejs_lang",
        target_strategy="lang_file",
        target_relative_path=target_relative_path,
        source_relative_path=source_relative_path,
        target_locator={
            "entry_key": key,
            "source_file": source_file,
            "original_text": original_text or "",
        },
    )


def build_kubejs_js_metadata(
    source_path: str,
    source_file: str,
    key: str,
    local_root: str | None = None,
    original_text: str | None = None,
) -> dict:
    normalized_source_path = normalize_relative_path(source_path)
    source_relative_path = _relativize_local_file(normalized_source_path, local_root) or normalized_source_path
    return _build_metadata(
        area_type="kubejs_js",
        target_strategy="js_text_rewrite",
        target_relative_path=source_relative_path,
        source_relative_path=source_relative_path,
        target_locator={
            "entry_key": key,
            "source_file": source_file,
            "original_text": original_text or "",
        },
    )


def build_apply_metadata(
    area_type: str,
    source_file: str,
    source_path: str,
    key: str,
    local_root: str | None = None,
    original_text: str | None = None,
) -> dict:
    if area_type == "mod_lang":
        return build_mod_lang_metadata(
            source_file=source_file,
            source_path=source_path,
            key=key,
            original_text=original_text,
        )
    if area_type == "ftb_quests":
        return build_ftb_quests_metadata(
            source_path=source_path,
            source_file=source_file,
            key=key,
            local_root=local_root,
            original_text=original_text,
        )
    if area_type == "ftbquests_lang":
        return build_ftbquests_lang_metadata(
            source_path=source_path,
            source_file=source_file,
            key=key,
            local_root=local_root,
            original_text=original_text,
        )
    if area_type == "better_questing":
        return build_better_questing_metadata(
            source_path=source_path,
            source_file=source_file,
            key=key,
            local_root=local_root,
            original_text=original_text,
        )
    if area_type == "kubejs_json":
        return build_kubejs_json_metadata(
            source_path=source_path,
            source_file=source_file,
            key=key,
            local_root=local_root,
            original_text=original_text,
        )
    if area_type == "kubejs_lang":
        return build_kubejs_lang_metadata(
            source_path=source_path,
            source_file=source_file,
            key=key,
            local_root=local_root,
            original_text=original_text,
        )
    if area_type == "kubejs_js":
        return build_kubejs_js_metadata(
            source_path=source_path,
            source_file=source_file,
            key=key,
            local_root=local_root,
            original_text=original_text,
        )
    normalized_source_path = normalize_relative_path(source_path or source_file)
    return _build_metadata(
        area_type=area_type or "unknown",
        target_strategy="unknown",
        target_relative_path=normalized_source_path,
        source_relative_path=normalized_source_path,
        target_locator={
            "entry_key": key,
            "original_text": original_text or "",
        },
    )


def serialize_metadata(metadata: dict | None) -> str | None:
    if not metadata:
        return None
    return json.dumps(metadata, ensure_ascii=False)


def deserialize_metadata(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def group_items_by_target(items: Iterable[Any]) -> Dict[str, List[Any]]:
    grouped: Dict[str, List[Any]] = {}
    for item in items:
        metadata = get_item_metadata(item)
        relative_path = normalize_relative_path(
            str(
                metadata.get("target_relative_path")
                or metadata.get("target_path")
                or item.source_path
                or item.source_file
                or ""
            )
        )
        if not relative_path:
            continue
        grouped.setdefault(relative_path, []).append(item)
    return grouped


def get_item_metadata(item: Any) -> dict:
    getter = getattr(item, "get_apply_metadata", None)
    if callable(getter):
        metadata = getter()
        if isinstance(metadata, dict) and metadata:
            _normalize_metadata_shape(metadata)
            return metadata

    raw = getattr(item, "apply_metadata_json", None)
    metadata = deserialize_metadata(raw)
    if metadata:
        _normalize_metadata_shape(metadata)
        return metadata

    source_file = getattr(item, "source_file", "") or ""
    source_path = getattr(item, "source_path", "") or ""
    original_text = getattr(item, "original_text", "") or ""
    area_type = _infer_area_type(source_path)

    return build_apply_metadata(
        area_type=area_type,
        source_file=source_file,
        source_path=source_path,
        key="",
        local_root=None,
        original_text=original_text,
    )


def _infer_area_type(source_path: str) -> str:
    normalized = normalize_relative_path(source_path).lower()
    normalized_wrapped = f"/{normalized}"
    if normalized.endswith(".snbt") and "/ftbquests/" in normalized_wrapped and "/lang/" in normalized_wrapped:
        return "ftbquests_lang"
    if normalized.endswith((".snbt", ".nbt")) and "/ftbquests/quests/" in normalized_wrapped:
        return "ftb_quests"
    if normalized.endswith("defaultquests.json") and "/betterquesting/" in normalized_wrapped:
        return "better_questing"
    if normalized.endswith(".js") and "/kubejs/" in normalized_wrapped:
        return "kubejs_js"
    if normalized.endswith(".lang") and "/kubejs/" in normalized_wrapped:
        return "kubejs_lang"
    if normalized.endswith(".json") and "/kubejs/" in normalized_wrapped:
        return "kubejs_json"
    return "mod_lang"


def _relativize_local_file(path: str, local_root: str | None) -> str:
    normalized_path = os.path.abspath(path) if path else ""
    normalized_root = os.path.abspath(local_root) if local_root else ""
    if normalized_path and normalized_root:
        try:
            relative = os.path.relpath(normalized_path, normalized_root)
            if not relative.startswith(".."):
                return normalize_relative_path(relative)
        except Exception:
            pass
    return normalize_relative_path(path)


def _infer_modid(source_file: str, source_path: str) -> str:
    path = normalize_relative_path(source_path)
    parts = path.split("/") if path else []
    if "assets" in parts:
        idx = parts.index("assets")
        if idx + 1 < len(parts):
            return parts[idx + 1]

    filename = os.path.basename(source_file or source_path or "")
    if filename.endswith(".jar"):
        name = filename.rsplit(".jar", 1)[0]
        jar_parts = name.split("-")
        for i in range(len(jar_parts) - 1, 0, -1):
            candidate = "-".join(jar_parts[:i])
            if not candidate.replace(".", "").replace("_", "").isdigit():
                return candidate
        return name
    return "mcpacklocalizer"


def _strip_modid_prefix(key: str, modid: str) -> str:
    normalized_key = str(key or "").strip()
    prefix = f"{modid}."
    if normalized_key.startswith(prefix):
        return normalized_key[len(prefix):]
    return normalized_key


def _build_metadata(
    *,
    area_type: str,
    target_strategy: str,
    target_relative_path: str,
    source_relative_path: str,
    target_locator: dict,
) -> dict:
    normalized_target = normalize_relative_path(target_relative_path)
    normalized_source = normalize_relative_path(source_relative_path)
    return {
        "area_type": area_type,
        "target_strategy": target_strategy,
        "target_relative_path": normalized_target,
        "target_path": normalized_target,
        "source_relative_path": normalized_source,
        "target_locator": target_locator,
    }


def _normalize_metadata_shape(metadata: dict) -> None:
    target_path = normalize_relative_path(
        str(metadata.get("target_relative_path") or metadata.get("target_path") or "")
    )
    if target_path:
        metadata["target_relative_path"] = target_path
        metadata["target_path"] = target_path
    source_relative_path = normalize_relative_path(str(metadata.get("source_relative_path") or ""))
    if source_relative_path:
        metadata["source_relative_path"] = source_relative_path


def _localize_language_path(path: str, target_locale: str = "zh_cn") -> str:
    normalized = normalize_relative_path(path)
    parts = normalized.split("/") if normalized else []
    if not parts:
        return normalized

    file_name = parts[-1]
    stem, ext = os.path.splitext(file_name)
    lowered_stem = stem.lower()
    if lowered_stem in ENGLISH_LANG_CODES:
        parts[-1] = f"{target_locale}{ext.lower()}"
        return normalize_relative_path("/".join(parts))

    for index, part in enumerate(parts):
        if part.lower() in ENGLISH_LANG_CODES:
            parts[index] = target_locale
            return normalize_relative_path("/".join(parts))

    return normalized


def _is_localizable_language_file(path: str) -> bool:
    normalized = normalize_relative_path(path).lower()
    if "/lang/" not in f"/{normalized}":
        return False
    file_name = os.path.basename(normalized)
    stem, ext = os.path.splitext(file_name)
    if ext not in {".json", ".lang", ".snbt"}:
        return False
    if stem in ENGLISH_LANG_CODES:
        return True
    parts = normalized.split("/")
    return any(part in ENGLISH_LANG_CODES for part in parts)
