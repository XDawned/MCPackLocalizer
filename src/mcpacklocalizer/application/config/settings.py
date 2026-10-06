# [Module: desktop.settings] [Status: 已完成] [Brief: 不依赖 Qt 的设置数据与本地运行时发现]
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path

from mcpacklocalizer.core.translation.api import ApiProfile
from mcpacklocalizer.core.translation.local import DEFAULT_GLOSSARY, DEFAULT_MODEL, DEFAULT_SYSTEM_PROMPT
from mcpacklocalizer.core.translation.locales import validate_pair
from mcpacklocalizer.core.translation.polishing import DEFAULT_POLISH_PROMPT

from ...paths import PROJECT, migrated_path
from ...runtime import bundled_python
from ..tasks.models import model_spec


@dataclass
class Settings:
    model: str = str(DEFAULT_MODEL)
    download_variant: str = "7b"
    runtime_python: str = field(default_factory=lambda: "" if bundled_python() else sys.executable)
    backend: str = "auto"
    glossary: str = str(DEFAULT_GLOSSARY)
    overrides: str = ""
    glossary_enabled: bool = True
    allow_missing_placeholders: bool = False
    threads: int = 0
    gpu_layers: int = -1
    context_size: int = 4096
    max_tokens: int = 768
    term_tokens: int = 512
    timeout: int = 300
    theme: str = "system"
    theme_color: str = "#3268c8"
    output_home: str = ""
    engine: str = "local"
    active_api: str = ""
    api_profiles: list[dict] = field(default_factory=list, repr=False)
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    glossary_inline: str = "{}"
    non_translate: str = ""
    output_allow_partial: bool = False
    output_replace_locale: bool = False
    output_include_i18n: bool = True
    source_locale: str = "en_us"
    target_locale: str = "zh_cn"
    script_api: str = ""
    polish_api: str = ""
    polish_prompt: str = DEFAULT_POLISH_PROMPT

    @classmethod
    def defaults(cls):
        runtime = PROJECT / ".tmp/vulkan-venv/Scripts/python.exe"
        data_home = Path(os.getenv("MPLT_DATA_DIR") or
                         str(Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "MCPackLocalizer"))
        return cls(
            model=os.getenv("MPLT_MODEL_PATH") or str(DEFAULT_MODEL),
            glossary=os.getenv("MPLT_GLOSSARY_PATH") or str(DEFAULT_GLOSSARY),
            runtime_python=os.getenv("MPLT_RUNTIME_PYTHON") or
            ("" if bundled_python() else str(runtime) if runtime.is_file() else sys.executable),
            backend="vulkan" if not bundled_python() and runtime.is_file() and
            not os.getenv("MPLT_RUNTIME_PYTHON") else "auto",
            output_home=str(data_home / "tasks"),
        )

    @classmethod
    def from_dict(cls, data):
        values = asdict(cls.defaults())
        for item in fields(cls):
            value = data.get(item.name)
            if type(value) is type(values[item.name]):
                values[item.name] = value
        # Old releases shared local budgets and API limits. Seed missing profile
        # fields once; later saves and newly added interfaces are independent.
        migrated_profiles = []
        profile_defaults = asdict(ApiProfile())
        for profile in values["api_profiles"]:
            if not isinstance(profile, dict):
                return cls.defaults()
            profile = dict(profile)
            for name in ("context_size", "max_tokens", "term_tokens", "timeout",
                         "concurrency", "retries", "request_interval"):
                if name not in profile and type(data.get(name)) is type(profile_defaults[name]):
                    profile[name] = data[name]
            migrated_profiles.append(profile)
        values["api_profiles"] = migrated_profiles
        result = cls(**values)
        result.glossary = migrated_path(result.glossary)
        result.overrides = migrated_path(result.overrides)
        result.output_home = migrated_path(result.output_home)
        try:
            result.validate()
        except ValueError:
            return cls.defaults()
        return result

    def validate(self):
        model_spec(self.download_variant)
        validate_pair(self.source_locale, self.target_locale)
        if self.backend not in {"auto", "cpu", "vulkan", "cuda"}:
            raise ValueError("请选择有效的推理后端")
        if self.theme not in {"system", "light", "dark"}:
            raise ValueError("请选择有效的主题")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", self.theme_color or ""):
            raise ValueError("请选择有效的主题色")
        if self.engine not in {"local", "api"}:
            raise ValueError("请选择本地 GGUF 或 API 翻译")
        ids = set()
        for data in self.api_profiles:
            try:
                profile = ApiProfile(**data)
            except TypeError:
                raise ValueError("接口配置字段无效") from None
            profile.validate(require_model=False)
            if profile.id in ids:
                raise ValueError("接口标识重复")
            ids.add(profile.id)
        if self.active_api and self.active_api not in ids:
            raise ValueError("当前接口不存在")
        if self.script_api and self.script_api not in ids:
            raise ValueError("脚本翻译接口不存在")
        if self.polish_api and self.polish_api not in ids:
            raise ValueError("修润接口不存在")
        if not isinstance(self.polish_prompt, str) or not self.polish_prompt.strip():
            raise ValueError("修润提示词不能为空")
        validate_glossary(self.glossary_inline)
        for name, minimum, maximum in (
            ("threads", 0, 1024), ("gpu_layers", -1, 999), ("context_size", 256, 131072),
            ("max_tokens", 1, 32768), ("term_tokens", 0, 32768), ("timeout", 1, 86400),
        ):
            if type(getattr(self, name)) is not int or not minimum <= getattr(self, name) <= maximum:
                raise ValueError(f"{name} 必须在 {minimum} 至 {maximum} 之间")
        if self.max_tokens >= self.context_size:
            raise ValueError("输出 token 上限必须小于上下文长度")

    def model_options(self):
        self.validate()
        args = {key: getattr(self, key) for key in (
            "backend", "runtime_python", "threads", "gpu_layers", "context_size", "max_tokens",
            "term_tokens", "timeout", "allow_missing_placeholders")}
        args.update(engine=self.engine, system_prompt=self.system_prompt, non_translate=self.non_translate,
                    source_locale=self.source_locale, target_locale=self.target_locale,
                    glossary_inline=self.glossary_inline)
        if self.engine == "api":
            profile = self.selected_profile()
            profile.validate()
            args.update({key: getattr(profile, key) for key in (
                "context_size", "max_tokens", "term_tokens", "timeout", "concurrency", "retries", "request_interval")})
            args["request_timeout"] = profile.timeout
            args.update(api_profile_id=profile.id, api_protocol=profile.protocol, api_base_url=profile.base_url,
                        api_model=profile.model, api_key_env=profile.key_env, api_prompt_mode=profile.prompt_mode,
                        api_temperature=float(profile.temperature), api_send_temperature=profile.send_temperature,
                        api_token_parameter=profile.token_parameter, api_extra_body=profile.extra_body,
                        credentials={profile.id: profile.resolved_key()})
        elif self.model:
            args["model"] = self.model
        if not self.glossary_enabled:
            args["no_glossary"] = True
            args["glossary_inline"] = "{}"
        else:
            args["glossary"] = self.glossary
            args["glossary_overrides"] = self.overrides
        return args

    def selected_profile(self):
        profile = next((data for data in self.api_profiles if data.get("id") == self.active_api), None)
        if profile is None:
            raise ValueError("请先在接口管理中添加并选择一个 API 接口")
        return ApiProfile(**profile)

    def interface_ready(self):
        if self.engine == "local":
            return bool(self.model and Path(self.model).is_file())
        try:
            self.selected_profile().validate()
        except ValueError:
            return False
        return True

    def script_options(self):
        if not self.script_api:
            return {}
        from ...core.translation.local import ModelConfig
        options = replace(self, engine="api", active_api=self.script_api).model_options()
        config = {key: value for key, value in options.items() if key in {f.name for f in fields(ModelConfig)}}
        config.update(engine="api", api_prompt_mode="custom", allow_missing_placeholders=False)
        if "glossary_overrides" in options:
            config["overrides"] = options["glossary_overrides"]
        if options.get("no_glossary"):
            config.update(glossary=None, overrides=None, glossary_inline="{}")
        return config

    def credentials(self):
        # Resume may use a different profile from the currently selected one.
        return {data["id"]: data.get("api_key", "").strip() for data in self.api_profiles}

    def engine_label(self):
        if self.engine == "local":
            return "HY-MT-2 · 本地 GGUF"
        try:
            profile = self.selected_profile()
            return f"{profile.name} · {profile.model or '未选择模型'}"
        except ValueError:
            return "API · 尚未选择接口"


def validate_glossary(text):
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        raise ValueError("术语覆盖必须是 JSON 对象") from None
    if not isinstance(data, dict) or any(not isinstance(key, str) or not key.strip()
            or not (isinstance(value, str) or isinstance(value, list) and all(isinstance(v, str) for v in value))
            for key, value in data.items()):
        raise ValueError("术语覆盖应为原文到译文的映射；空译文或空列表可禁用预设词条")
    return data
