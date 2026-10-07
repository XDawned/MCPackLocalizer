# [Module: config.interfaces] [Status: 已完成] [Brief: 独立本地 GGUF 接口、模型身份和推理参数校验]
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from ...core.translation.templates import detect_model_family
from ..tasks.models import MODEL_VARIANTS, model_spec

LEGACY_LOCAL_ID = "__hy_mt_gguf__"
LOCAL_PARAMETERS = ("runtime_python", "backend", "threads", "gpu_layers", "context_size", "max_tokens", "term_tokens", "timeout")


@dataclass
class LocalProfile:
    id: str
    name: str
    model: str
    template_id: str = "hy_mt"
    download_variant: str = "7b"
    model_family: str = "hy_mt"
    parameters: dict = field(default_factory=dict)
    download_enabled: bool = True

    def validate(self):
        for name in ("id", "name", "model", "template_id", "download_variant", "model_family"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError("本地接口字段必须是非空文本")
        if Path(self.model).suffix.lower() != ".gguf":
            raise ValueError("本地模型路径必须以 .gguf 结尾")
        if type(self.download_enabled) is not bool:
            raise ValueError("本地模型下载开关必须是布尔值")
        model_spec(self.download_variant)
        if self.model_family not in {"hy_mt", "index", "generic"}:
            raise ValueError("请选择有效的本地模型类型")
        if not isinstance(self.parameters, dict) or set(self.parameters) - set(LOCAL_PARAMETERS):
            raise ValueError("本地接口只能保存本地推理参数")
        for name in ("runtime_python", "backend"):
            if name in self.parameters and not isinstance(self.parameters[name], str):
                raise ValueError("本地运行时和后端参数必须是文本")
        if self.parameters.get("backend", "auto") not in {"auto", "cpu", "cuda", "vulkan"}:
            raise ValueError("请选择有效的本地推理后端")
        for name, low, high in (("threads", 0, 1024), ("gpu_layers", -1, 999), ("context_size", 256, 131072),
                                ("max_tokens", 1, 32768), ("term_tokens", 0, 32768), ("timeout", 1, 86400)):
            if name in self.parameters and (type(self.parameters[name]) is not int or not low <= self.parameters[name] <= high):
                raise ValueError(f"本地接口 {name} 必须在 {low} 至 {high} 之间")
        if self.parameters.get("max_tokens", 768) >= self.parameters.get("context_size", 4096):
            raise ValueError("本地接口输出 token 上限必须小于上下文长度")


def profile_for_model(model, template_id="hy_mt", variant="7b", *, profile_id="", parameters=None):
    model = str(Path(model))
    variant = next((key for key, spec in MODEL_VARIANTS.items() if Path(model).name.casefold() == spec.filename.casefold()), variant)
    spec = model_spec(variant)
    family = detect_model_family(model, spec.template_id)
    known = Path(model).name.casefold() == spec.filename.casefold()
    label = spec.name if known else {"hy_mt": "HY-MT-2", "index": "Index-Translate", "generic": "本地模型"}[family]
    identity = profile_id or "local_" + hashlib.sha256(model.casefold().encode()).hexdigest()[:16]
    return LocalProfile(identity, label + " · 本地 GGUF", model, template_id, variant, family,
                        dict(parameters or {}), known)
