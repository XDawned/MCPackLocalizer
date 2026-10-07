# [Module: application.jobs] [Status: 已完成] [Brief: 结构化任务协议、默认配置及输入校验]
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from uuid import uuid4

from ...core.mods.scan import default_cache
from ...core.pack.scopes import recognition_scopes
from ...paths import migrated_path
from ...runtime import inference_python
from .models import model_spec

OPERATIONS = frozenset({"scan", "extract", "localize", "diff", "resume", "export", "review",
                        "doctor", "translate", "extract-lang", "backfill", "convert-lang",
                        "scan-mods", "extract-mods", "localize-mods", "mod-library", "download-model", "polish", "polish-accept",
                        "resource-exclusion", "preview-prompt"})
PATH_FIELDS = {"root", "output", "baseline", "source", "bundle", "lang", "cache", "translation_library",
               "i18n_jar", "i18n_metadata", "i18n_metadata_jar"}
PATH_LISTS = {"cfpa_pack", "resource_pack"}
BOOLEAN_FIELDS = {"probe", "no_glossary", "allow_partial", "replace_existing_locale", "include_i18n_mod",
                  "offline", "include_drafts", "allow_missing_placeholders", "api_send_temperature", "capture_prompts"}
INTEGER_FIELDS = {"threads", "gpu_layers", "context_size", "max_tokens", "term_tokens", "sample", "limit", "record_id",
                  "concurrency", "retries"}


@dataclass
class Job:
    operation: str
    root: Path | None = None
    output: Path | None = None
    baseline: Path | None = None
    source: Path | None = None
    bundle: Path | None = None
    lang: Path | None = None
    source_locale: str = "en_us"
    target_locale: str = "zh_cn"
    pack_id: str | None = None
    sample: int = 3
    limit: int | None = None
    model: str | None = None
    download_variant: str = "7b"
    backend: str | None = None
    runtime_python: str = field(default_factory=inference_python)
    threads: int | None = None
    gpu_layers: int | None = None
    context_size: int | None = None
    max_tokens: int | None = None
    term_tokens: int | None = None
    glossary: str | None = None
    glossary_overrides: str | None = None
    no_glossary: bool = False
    allow_missing_placeholders: bool | None = None
    engine: str | None = None
    api_profile_id: str | None = None
    api_protocol: str | None = None
    api_base_url: str | None = None
    api_model: str | None = None
    api_key_env: str | None = None
    api_prompt_mode: str | None = None
    api_temperature: float | None = None
    api_send_temperature: bool | None = None
    api_token_parameter: str | None = None
    api_extra_body: str | None = None
    system_prompt: str | None = None
    prompt_template_id: str | None = None
    prompt_family: str | None = None
    model_family: str | None = None
    capture_prompts: bool | None = None
    prompt_user: str | None = None
    glossary_inline: str | None = None
    non_translate: str | None = None
    concurrency: int | None = None
    retries: int | None = None
    request_interval: float | None = None
    request_timeout: float | None = None
    credentials: dict[str, str] = field(default_factory=dict, repr=False)
    timeout: float = 300
    allow_partial: bool = False
    replace_existing_locale: bool = False
    include_i18n_mod: bool = False
    i18n_jar: Path | None = None
    offline: bool = False
    game_version: str | None = None
    loader: str | None = None
    translation_library: Path | None = None
    reuse_policy: str | None = None
    cache: Path = field(default_factory=default_cache)
    cfpa_pack: list[Path] = field(default_factory=list)
    cfpa_release: str = "autobuild"
    coverage_mode: str = "effective"
    resource_pack: list[Path] = field(default_factory=list)
    i18n_metadata: Path | None = None
    i18n_metadata_jar: Path | None = None
    library_action: str | None = None
    include_drafts: bool = False
    record_id: int | None = None
    namespace: str | None = None
    key: str | None = None
    state: str | None = None
    entry_id: str | None = None
    entry_ids: list[str] | None = None
    polish_prompt: str = ""
    polish_mode: str = "correct"
    polish_run_id: str | None = None
    polish_updates: dict[str, str] | None = None
    translation: str | None = None
    probe: bool = False
    text: str = ""
    context: str = ""
    format: str | None = None
    recognition_scope: str | list[str] = "all"
    script_config: dict | None = None
    resource_paths: list[str] | None = None
    resource_action: str | None = None

    def __post_init__(self):
        if self.operation not in OPERATIONS:
            raise ValueError("未知任务操作")
        for item in fields(self):
            name, value = item.name, getattr(self, item.name)
            if value is None:
                if item.default is not None:
                    raise ValueError(f"{name} 不能为空")
                continue
            if name in PATH_FIELDS:
                if not isinstance(value, (str, Path)) or not str(value).strip():
                    raise ValueError(f"{name} 必须是非空路径")
                setattr(self, name, Path(migrated_path(str(value))))
            elif name in PATH_LISTS:
                if not isinstance(value, list) or any(not isinstance(p, (str, Path)) or not str(p) for p in value):
                    raise ValueError(f"{name} 必须是路径列表")
                setattr(self, name, [Path(migrated_path(str(p))) for p in value])
            elif name in BOOLEAN_FIELDS:
                if type(value) is not bool:
                    raise ValueError(f"{name} 必须是布尔值")
            elif name in INTEGER_FIELDS:
                if type(value) is not int:
                    raise ValueError(f"{name} 必须是整数")
            elif name == "polish_updates":
                if (not isinstance(value, dict) or not value or
                        any(not isinstance(key, str) or not key.strip() or not isinstance(text, str) or not text.strip()
                            for key, text in value.items())):
                    raise ValueError("接受修润结果需要非空的条目 ID 到译文映射")
            elif name in {"entry_ids", "resource_paths"}:
                if (not isinstance(value, list) or not value or
                        any(not isinstance(item, str) or not item.strip() for item in value) or len(set(value)) != len(value)):
                    raise ValueError(f"{name} 必须是非空且不重复的字符串列表")
            elif name == "script_config":
                from ...core.translation.local import ModelConfig
                if not isinstance(value, dict) or set(value) - {f.name for f in fields(ModelConfig)}:
                    raise ValueError("script_config 只能包含模型配置字段")
            elif name == "recognition_scope":
                recognition_scopes(value)
            elif name == "credentials":
                if not isinstance(value, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
                    raise ValueError("credentials 必须是接口标识到密钥的映射")
            elif name in {"api_temperature", "request_interval"}:
                import math
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError(f"{name} 必须是有限数值")
            elif name in {"timeout", "request_timeout"}:
                if type(value) not in (int, float) or not 0 < value <= 86400:
                    raise ValueError(f"{name} 必须为正数且不超过 86400")
            elif not isinstance(value, str):
                raise ValueError(f"{name} 必须是文本")
        for name, allowed in {"backend": {"auto", "cpu", "cuda", "vulkan"},
                              "engine": {"local", "api"},
                              "loader": {"forge", "neoforge", "quilt", "fabric"},
                              "reuse_policy": {"reviewed", "all", "off"},
                              "format": {"json", "json5", "snbt", "lang"},
                              "cfpa_release": {"autobuild", "indexed"},
                              "coverage_mode": {"effective", "i18n"},
                              "state": {"draft", "reviewed", "rejected", "superseded"}}.items():
            if getattr(self, name) is not None and getattr(self, name) not in allowed:
                raise ValueError(f"{name} 无效")
        if self.limit is not None and self.limit < 0:
            raise ValueError("limit 不能为负数")
        required = []
        if self.operation in {"scan", "extract", "localize", "diff", "extract-lang", "scan-mods", "extract-mods", "localize-mods"}:
            required.append("root")
        if self.operation in {"extract", "localize", "extract-lang", "extract-mods", "localize-mods", "resume", "export", "review", "backfill", "convert-lang", "polish", "polish-accept"}:
            required.append("output")
        if self.operation == "diff":
            required.append("baseline")
        if self.operation == "download-model":
            model_spec(self.download_variant)
            required.append("output")
        if self.operation == "backfill":
            required.extend(["bundle", "lang"])
        if self.operation == "convert-lang":
            required.append("source")
        if self.operation == "review":
            required.extend(["entry_id", "translation"])
        if self.operation == "polish":
            self.polish_run_id = self.polish_run_id or uuid4().hex
            if self.engine != "api" or self.api_prompt_mode != "custom":
                raise ValueError("批量修润需要配置为 MC 提示词模式的 API 接口")
            if self.polish_mode not in {"correct", "polish"} or not self.polish_prompt.strip():
                raise ValueError("请选择修润模式并填写专用提示词")
        if self.operation == "polish-accept":
            required.extend(["polish_run_id", "polish_updates"])
        if self.operation == "resource-exclusion":
            required.extend(["output", "resource_paths", "resource_action"])
            if self.resource_action not in {"exclude", "restore"}:
                raise ValueError("资源操作只能是排除或恢复")
        if self.operation == "mod-library":
            if self.library_action not in {"stats", "list", "import", "export", "resolve", "reject"}:
                raise ValueError("未知译库操作")
            self.translation_library = self.translation_library or default_cache() / "mod-translations.sqlite3"
            if self.library_action in {"import", "export"}:
                required.append("source" if self.library_action == "import" else "output")
            if self.library_action in {"resolve", "reject"}:
                required.append("record_id")
            if self.library_action == "list" and self.limit is None:
                self.limit = 20
        for name in required:
            if getattr(self, name) is None or getattr(self, name) == "":
                raise ValueError(f"任务缺少必填项：{name}")
        if self.operation == "extract-lang" and self.format is None:
            self.format = "json"

    def payload(self) -> dict:
        result = asdict(self)
        for name in PATH_FIELDS:
            result[name] = str(result[name]) if result[name] is not None else None
        for name in PATH_LISTS:
            result[name] = [str(p) for p in result[name]]
        return result

    @classmethod
    def from_payload(cls, payload: dict) -> Job:
        if not isinstance(payload, dict) or set(payload) - {f.name for f in fields(cls)}:
            raise ValueError("任务必须是包含已知字段的对象")
        if "operation" not in payload:
            raise ValueError("任务缺少必填项：operation")
        return cls(**payload)
