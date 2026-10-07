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
from mcpacklocalizer.core.translation.templates import detect_model_family, legacy_mc_template, template_catalog

from ...paths import PROJECT, migrated_path
from ...runtime import bundled_python
from ..tasks.models import model_spec
from .interfaces import LEGACY_LOCAL_ID, LOCAL_PARAMETERS, LocalProfile, profile_for_model


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
    prompt_templates: list[dict] = field(default_factory=list)
    local_template_id: str = "hy_mt"
    local_model_templates: dict[str, str] = field(default_factory=dict)
    local_profiles: list[dict] = field(default_factory=list)
    active_local: str = ""
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
        # 旧版共享参数只迁移一次；已有接口的显式参数保留。
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
            try:
                migrated_profiles.append(asdict(ApiProfile(**profile)))
            except (TypeError, ValueError):
                return cls.defaults()
        values["api_profiles"] = migrated_profiles
        if "prompt_templates" not in data and values["system_prompt"] != DEFAULT_SYSTEM_PROMPT:
            values["prompt_templates"] = [asdict(legacy_mc_template(values["system_prompt"]))]
        result = cls(**values)
        result.glossary = migrated_path(result.glossary)
        result.overrides = migrated_path(result.overrides)
        result.output_home = migrated_path(result.output_home)
        try:
            if "local_profiles" not in data:
                entries = []
                parameters = {key: getattr(result, key) for key in LOCAL_PARAMETERS}
                if result.model and (data.get("model") or Path(result.model).is_file()):
                    entries.append(profile_for_model(result.model, result.local_template_id, result.download_variant,
                                                     profile_id=LEGACY_LOCAL_ID, parameters=parameters))
                for model, template_id in result.local_model_templates.items():
                    if not any(Path(p.model) == Path(model) for p in entries):
                        entries.append(profile_for_model(model, template_id, result.download_variant, parameters=parameters))
                result.local_profiles = [asdict(p) for p in entries]
                result.active_local = entries[0].id if entries else ""
            result.validate()
        except (ValueError, TypeError):
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
        catalog = self.templates()
        local_template = catalog.get(self.local_template_id)
        if local_template is None or local_template.interface_type != "translation":
            raise ValueError("本地 GGUF 请选择专用翻译模型模板")
        for model, template_id in self.local_model_templates.items():
            if not isinstance(model, str) or not model or not isinstance(template_id, str):
                raise ValueError("本地模型模板绑定字段无效")
            template = catalog.get(template_id)
            if template is None or template.interface_type != "translation":
                raise ValueError("本地模型绑定的专用翻译模板不存在")
        local_ids = set()
        for profile in self.local_interfaces():
            profile.validate()
            if profile.id in local_ids:
                raise ValueError("本地接口标识重复")
            local_ids.add(profile.id)
            template = catalog.get(profile.template_id)
            if template is None or template.interface_type != "translation":
                raise ValueError("本地接口绑定的专用翻译模板不存在")
        if self.active_local and self.active_local not in local_ids:
            raise ValueError("当前本地接口不存在")
        for data in self.api_profiles:
            try:
                profile = ApiProfile(**data)
            except TypeError:
                raise ValueError("接口配置字段无效") from None
            profile.validate(require_model=False)
            template = catalog.get(profile.template_id)
            if template is None or template.interface_type != profile.interface_type:
                raise ValueError("接口绑定的翻译模板不存在或类型不匹配")
            if template.family in {"hy_mt", "index"} and profile.protocol != "openai":
                raise ValueError("HY-MT-2 和 Index-Translate 模板使用 OpenAI 兼容协议")
            if profile.id in ids:
                raise ValueError("接口标识重复")
            ids.add(profile.id)
            if profile.id in local_ids:
                raise ValueError("本地与 API 接口标识不能重复")
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
        args.update(engine=self.engine, non_translate=self.non_translate,
                    source_locale=self.source_locale, target_locale=self.target_locale,
                    glossary_inline=self.glossary_inline)
        if self.engine == "api":
            profile = self.selected_profile()
            profile.validate()
            template = self.templates()[profile.template_id]
            args.update({key: getattr(profile, key) for key in (
                "context_size", "max_tokens", "term_tokens", "timeout", "concurrency", "retries", "request_interval")})
            args["request_timeout"] = profile.timeout
            args.update(api_profile_id=profile.id, api_protocol=profile.protocol, api_base_url=profile.base_url,
                        api_model=profile.model, api_key_env=profile.key_env,
                        api_prompt_mode="custom" if profile.interface_type == "llm" else
                        template.family if template.family in {"hy_mt", "index"} else "translation",
                        api_temperature=float(profile.temperature), api_send_temperature=profile.send_temperature,
                        api_token_parameter=profile.token_parameter, api_extra_body=profile.extra_body,
                        credentials={profile.id: profile.resolved_key()})
        else:
            local = self.current_local_profile()
            template = self.templates()[local.template_id if local else self.local_template_id]
            if local:
                args.update(local.parameters)
                args["model"] = local.model
            elif self.model:
                args["model"] = self.model
        args.update(system_prompt=template.system, prompt_user=template.user,
                    prompt_family=template.family, prompt_template_id=template.id,
                    model_family=detect_model_family(profile.model, template.family) if self.engine == "api" else
                    local.model_family if local else detect_model_family(self.model, template.family))
        if not self.glossary_enabled:
            args["no_glossary"] = True
            args["glossary_inline"] = "{}"
        else:
            args["glossary"] = self.glossary
            args["glossary_overrides"] = self.overrides
        return args

    def templates(self):
        return template_catalog(self.prompt_templates)

    def store_template(self, template):
        template.validate()
        overrides = [dict(p) for p in self.prompt_templates if p["id"] != template.id]
        overrides.append(asdict(template))
        return replace(self, prompt_templates=overrides,
                       system_prompt=template.system if template.id == "mc" else self.system_prompt)

    def bind_local_template(self, template_id):
        bindings = dict(self.local_model_templates)
        if self.model:
            bindings[str(Path(self.model))] = template_id
        current = self.current_local_profile()
        profiles = self.local_profiles
        if current:
            profiles = [asdict(replace(p, template_id=template_id)) if p.id == current.id else asdict(p)
                        for p in self.local_interfaces()]
        return replace(self, local_template_id=template_id, local_model_templates=bindings, local_profiles=profiles)

    def local_interfaces(self):
        parameters = {key: getattr(self, key) for key in LOCAL_PARAMETERS}
        if self.local_profiles:
            try:
                profiles = [LocalProfile(**data) for data in self.local_profiles]
                return [replace(p, parameters=parameters | p.parameters) if isinstance(p.parameters, dict) else p
                        for p in profiles]
            except (TypeError, AttributeError):
                raise ValueError("本地接口配置字段无效") from None
        if self.model and Path(self.model).is_file():
            return [profile_for_model(self.model, self.local_template_id, self.download_variant,
                                      profile_id=LEGACY_LOCAL_ID, parameters=parameters)]
        return []

    def current_local_profile(self):
        profiles = self.local_interfaces()
        return next((p for p in profiles if p.id == self.active_local), None) or next(
            (p for p in profiles if Path(p.model) == Path(self.model)), None)

    def use_local_profile(self, profile_id):
        profile = next((p for p in self.local_interfaces() if p.id == profile_id), None)
        if profile is None:
            raise ValueError("本地接口不存在，请重新添加")
        return replace(self, model=profile.model, engine="local", active_local=profile.id,
                       local_profiles=[asdict(p) for p in self.local_interfaces()],
                       local_template_id=profile.template_id, download_variant=profile.download_variant,
                       **profile.parameters)

    def store_local_profile(self, profile):
        profile = replace(profile, parameters={key: getattr(self, key) for key in LOCAL_PARAMETERS} | profile.parameters)
        profile.validate()
        profiles = self.local_interfaces()
        updated = [asdict(profile) if p.id == profile.id else asdict(p) for p in profiles]
        if not any(p.id == profile.id for p in profiles):
            updated.append(asdict(profile))
        result = replace(self, local_profiles=updated)
        current = self.current_local_profile()
        if current and current.id == profile.id:
            result = replace(result.use_local_profile(profile.id), engine=self.engine)
        return result

    def sync_local_parameters(self):
        current = self.current_local_profile()
        if not current or not self.local_profiles:
            return self
        profile = replace(current, parameters={key: getattr(self, key) for key in LOCAL_PARAMETERS})
        return self.store_local_profile(profile)

    def select_local_model(self, model, variant):
        model = str(Path(model)) if model else ""
        bindings = dict(self.local_model_templates)
        if self.model:
            bindings[str(Path(self.model))] = self.local_template_id
        template_id = bindings.get(model, model_spec(variant).template_id)
        if "index-translate" in Path(model).name.lower() and model not in bindings:
            template_id = "index"
        elif "hy-mt2" in Path(model).name.lower() and model not in bindings:
            template_id = "hy_mt"
        if model:
            bindings[model] = template_id
        if not model:
            return replace(self, model="", active_local="", engine="local")
        current = self.current_local_profile()
        profile = next((p for p in self.local_interfaces() if Path(p.model) == Path(model)), None)
        if current and Path(current.model) == Path(model):
            profile = current
        if profile is None:
            profile = profile_for_model(model, template_id, variant,
                                        parameters={key: getattr(self, key) for key in LOCAL_PARAMETERS})
        result = self.store_local_profile(profile).use_local_profile(profile.id)
        return replace(result, local_model_templates=bindings)

    def selected_profile(self):
        profile = next((data for data in self.api_profiles if data.get("id") == self.active_api), None)
        if profile is None:
            raise ValueError("请先在接口管理中添加并选择一个 API 接口")
        return ApiProfile(**profile)

    def interface_ready(self):
        if self.engine == "local":
            profile = self.current_local_profile()
            return bool(profile and Path(profile.model).is_file())
        try:
            self.selected_profile().validate()
        except ValueError:
            return False
        return True

    def script_options(self):
        if not self.script_api:
            return {}
        selected = replace(self, engine="api", active_api=self.script_api)
        if selected.selected_profile().interface_type != "llm":
            raise ValueError("KubeJS 脚本翻译请选择大模型接口")
        from ...core.translation.local import ModelConfig
        options = selected.model_options()
        config = {key: value for key, value in options.items() if key in {f.name for f in fields(ModelConfig)}}
        config.update(engine="api", api_prompt_mode="custom", allow_missing_placeholders=False)
        # 脚本翻译使用自己的结构化提示词，不套用普通条目的用户模板。
        config.update(prompt_user="", prompt_family="mc")
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
            profile = self.current_local_profile()
            if profile:
                return profile.name
            name = {"index": "Index-Translate", "hy_mt": "HY-MT-2"}.get(
                detect_model_family(self.model, "hy_mt"), "专用翻译模型")
            return f"{name} · 本地 GGUF"
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
