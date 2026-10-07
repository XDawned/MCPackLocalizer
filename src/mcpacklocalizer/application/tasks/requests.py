# [Module: application.requests] [Status: 已完成] [Brief: 将界面意图转换为结构化任务请求]
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from ...core.pack.patch import validate_output
from ...core.pack.scopes import recognition_scopes
from ...core.translation.locales import validate_pair
from ...paths import DATA_HOME, PROJECT, migrated_path
from ..config.settings import Settings
from .jobs import Job


@dataclass
class PackRequest:
    root: str
    output: str = ""
    pack_id: str = ""
    baseline: str = ""
    mods: bool = False
    offline: bool = False
    cfpa_pack: str = ""
    game_version: str = ""
    loader: str = ""
    recognition_scope: str | list[str] = "all"
    translation_library: str = ""
    reuse_policy: str = "reviewed"


@dataclass
class PatchOptions:
    allow_partial: bool = False
    replace_existing_locale: bool = False
    include_i18n_mod: bool = True
    i18n_jar: str = ""
    offline: bool = False
    game_version: str = ""
    loader: str = ""

    def options(self):
        return {key: value for key, value in asdict(self).items() if type(value) is bool or value}


def required(value, label):
    if not value.strip():
        raise ValueError(f"请填写{label}")
    return value.strip()


def output_for(root, output):
    output = required(output, "输出目录")
    validate_output(Path(root), Path(output))
    return output


def new_task_output(root: str, output_home: str) -> str:
    """Suggest a fresh output without creating directories or changing user settings."""
    stamp = datetime.now(UTC).astimezone().strftime("task-%Y%m%d-%H%M%S-%f")
    game = Path(root).resolve() if root.strip() else None
    homes = [Path(migrated_path(output_home))] if output_home.strip() else []
    homes.extend([DATA_HOME / "tasks", Path.home() / "MCPackLocalizer/tasks", PROJECT / "data/tasks"])
    for home in homes:
        target = home / stamp
        if game is not None:
            try:
                validate_output(game, target)
            except ValueError:
                continue
        return str(target)
    raise ValueError("无法生成实例外的任务目录，请在设置中选择其它位置")


def pack_job(action: str, request: PackRequest, settings: Settings, patch: PatchOptions, limit=0):
    if action not in {"scan", "extract", "localize", "diff"}:
        raise ValueError("未知任务操作")
    root = required(request.root, "整合包目录")
    if not Path(root).is_dir():
        raise ValueError("整合包目录不存在")
    scopes = ["mods"] if request.mods else recognition_scopes(request.recognition_scope)
    with_mods = "mods" in scopes
    if request.mods and action == "diff":
        raise ValueError("模组任务通过共享译库复用；版本对比用于整合包文本")
    settings.validate()
    if with_mods and (settings.source_locale, settings.target_locale) != ("en_us", "zh_cn"):
        raise ValueError("模组共享译库目前仅支持英语 en_us → 简体中文 zh_cn；其它语言请使用整合包语言资源范围")
    options = {"root": root, "source_locale": settings.source_locale, "target_locale": settings.target_locale}
    options["allow_missing_placeholders"] = settings.allow_missing_placeholders
    if not request.mods:
        options["recognition_scope"] = request.recognition_scope
    if action in {"extract", "localize"}:
        options["output"] = output_for(root, request.output)
    if request.pack_id:
        options["pack_id"] = request.pack_id
    options.update({name: getattr(request, name) for name in ("game_version", "loader")
                    if getattr(request, name)})
    if action == "diff":
        options["baseline"] = migrated_path(required(request.baseline, "上一版本任务目录或快照"))
    elif request.baseline and not request.mods and action in {"extract", "localize"}:
        options["baseline"] = migrated_path(request.baseline)
    if with_mods:
        options["reuse_policy"] = request.reuse_policy
        if request.translation_library:
            options["translation_library"] = migrated_path(request.translation_library)
        if request.cfpa_pack:
            options["cfpa_pack"] = [request.cfpa_pack]
        if action != "localize":
            options.update({name: getattr(request, name) for name in ("game_version", "loader")
                            if getattr(request, name)})
            options["offline"] = request.offline
    if action == "localize":
        options.update(settings.model_options())
        options.update(script_config=settings.script_options(), credentials=settings.credentials())
        options.update(patch.options())
        if limit > 0:
            options["limit"] = limit
    return Job(action + "-mods" if request.mods else action, **options)


def task_job(action, output, settings, patch, limit=0, override_model=False):
    if action not in {"resume", "export"}:
        raise ValueError("未知任务操作")
    options = {"output": migrated_path(required(output, "任务目录")), **patch.options()}
    if action == "resume":
        if override_model:
            options.update(settings.model_options())
            options.update(script_config=settings.script_options(), credentials=settings.credentials())
        else:
            options.update(runtime_python=settings.runtime_python, timeout=settings.timeout,
                           credentials=settings.credentials())
        if limit > 0:
            options["limit"] = limit
    return Job(action, **options)


def review_job(output, entry_id, translation):
    if not translation.strip():
        raise ValueError("译文不能为空")
    return Job("review", output=migrated_path(required(output, "任务目录")), entry_id=entry_id,
               translation=translation)


def polish_job(output, entry_ids, settings, mode="correct"):
    from dataclasses import replace

    if not settings.polish_api:
        raise ValueError("请先配置并选择修润 API 接口")
    selected = replace(settings, engine="api", active_api=settings.polish_api)
    options = selected.model_options()
    if options["api_prompt_mode"] != "custom":
        raise ValueError("修润 API 请选择大模型接口；专用翻译模型用于普通翻译")
    return Job("polish", output=migrated_path(required(output, "任务目录")), entry_ids=entry_ids,
               polish_prompt=settings.polish_prompt, polish_mode=mode, **options)


def language_job(action, root, output, language="", fmt="json", patch=None, *,
                 source_locale="en_us", target_locale="zh_cn"):
    if action not in {"extract-lang", "backfill", "convert-lang"}:
        raise ValueError("未知语言文件操作")
    source = required(root, "源目录或文件")
    options = {"output": required(output, "输出目录或文件")}
    if action == "extract-lang":
        validate_pair(source_locale, target_locale)
        output_for(root, output)
        options.update(root=source, format=fmt, source_locale=source_locale, target_locale=target_locale)
    elif action == "backfill":
        options.update(bundle=migrated_path(source), lang=required(language, "已翻译语言文件"))
        if patch:
            options.update(allow_partial=patch.allow_partial, replace_existing_locale=patch.replace_existing_locale)
    else:
        options.update(source=source, format=fmt)
    return Job(action, **options)
