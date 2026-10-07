# [Module: application.models] [Status: 已完成] [Brief: 专用翻译模型流式下载、断点续传与完整性校验]
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from ...paths import MODEL_HOME

CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class ModelDownload:
    label: str
    repository: str
    filename: str
    size: int
    sha256: str
    owner: str = "tencent"
    template_id: str = "hy_mt"

    @property
    def name(self) -> str:
        return ("Index-Translate " if self.template_id == "index" else "HY-MT-2 ") + self.label

    @property
    def path(self) -> Path:
        return MODEL_HOME / "models" / self.repository / self.filename

    @property
    def urls(self) -> tuple[str, ...]:
        return tuple(f"https://{host}/{self.owner}/{self.repository}/resolve/main/{self.filename}"
                     for host in ("huggingface.co", "hf-mirror.com"))


MODEL_VARIANTS = {
    "7b": ModelDownload("7B", "Hy-MT2-7B-GGUF", "Hy-MT2-7B-Q4_K_M.gguf", 4624648896,
                        "9f96256500f3fc1ab4d64336b58f52a949a95ad7516b0c229476eef782f9f77b"),
    "1.8b": ModelDownload("1.8B", "Hy-MT2-1.8B-GGUF", "Hy-MT2-1.8B-Q4_K_M.gguf", 1133080448,
                          "dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699"),
    "index-9b": ModelDownload("9B", "Index-Translate-9B-GGUF", "Index-Translate-9B.Q4_K_M.gguf", 5780090304,
                              "9cc6758b0007f4cbf42ea3400768cbff91ae74ef8d640e467158348426d33713", "IndexTeam", "index"),
    "index-2b": ModelDownload("2B", "Index-Translate-2B-GGUF", "Index-Translate-2B.Q4_K_M.gguf", 1312164352,
                              "044b313d29342bd3b2c77cbb64023ca0d209bd9b3247763f9d162767ef2d746a", "IndexTeam", "index"),
}


def model_spec(variant: str) -> ModelDownload:
    if variant not in MODEL_VARIANTS:
        raise ValueError("请选择 HY-MT-2 7B 或 1.8B，或 Index-Translate 9B / 2B 模型")
    return MODEL_VARIANTS[variant]


def model_progress(completed: int, phase: str, variant: str, spec: ModelDownload):
    print(json.dumps({"operation": "download-model", "completed": completed, "failed": 0,
                      "remaining": max(0, spec.size - completed), "total": spec.size,
                      "download_variant": variant, "phase": f"{spec.name} · {phase}"},
                     ensure_ascii=False), file=sys.stderr, flush=True)


def download_model(target: Path, variant: str = "7b") -> dict:
    spec = model_spec(variant)
    target = Path(target)
    if target.suffix.lower() != ".gguf":
        raise ValueError("模型下载路径必须以 .gguf 结尾")
    if target.exists():
        raise ValueError("模型文件已存在，请选择已有模型；下载不会覆盖文件")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    errors = []
    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60, connect=15)) as client:
        for url in spec.urls:
            try:
                offset = partial.stat().st_size if partial.exists() else 0
                if offset > spec.size:
                    partial.unlink()
                    offset = 0
                digest = hashlib.sha256()
                if offset:
                    model_progress(offset, "检查已下载内容", variant, spec)
                    with partial.open("rb") as stream:
                        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
                            digest.update(chunk)
                if offset < spec.size:
                    headers = {"Accept-Encoding": "identity"}
                    if offset:
                        headers["Range"] = f"bytes={offset}-"
                    model_progress(offset, "正在下载模型", variant, spec)
                    with client.stream("GET", url, headers=headers) as response:
                        response.raise_for_status()
                        if response.status_code == 206:
                            expected = f"bytes {offset}-{spec.size - 1}/{spec.size}"
                            if response.headers.get("Content-Range") != expected:
                                raise ValueError("下载服务器返回的断点范围不匹配")
                        elif response.status_code == 200:
                            offset, digest = 0, hashlib.sha256()
                        else:
                            raise ValueError("下载服务器返回了不支持的响应")
                        length = response.headers.get("Content-Length")
                        if length and (not re.fullmatch(r"\d+", length) or int(length) != spec.size - offset):
                            raise ValueError("下载服务器返回的模型大小不匹配")
                        if response.headers.get("Content-Encoding", "identity") != "identity":
                            raise ValueError("下载服务器返回了不支持的压缩内容")
                        last_progress = 0.0
                        with partial.open("ab" if offset else "wb") as stream:
                            for chunk in response.iter_bytes(CHUNK_SIZE):
                                if offset + len(chunk) > spec.size:
                                    raise ValueError("下载内容超过预期模型大小")
                                stream.write(chunk)
                                digest.update(chunk)
                                offset += len(chunk)
                                now = time.monotonic()
                                if now - last_progress >= 0.25:
                                    model_progress(offset, "正在下载模型", variant, spec)
                                    last_progress = now
                if offset != spec.size:
                    raise ValueError("模型尚未下载完整；重试将继续下载")
                model_progress(offset, "正在校验模型", variant, spec)
                if digest.hexdigest() != spec.sha256:
                    partial.unlink()
                    raise ValueError("模型 SHA256 校验失败，已移除损坏的下载文件")
                with partial.open("rb") as stream:
                    valid_header = stream.read(4) == b"GGUF"
                if not valid_header:
                    partial.unlink()
                    raise ValueError("下载文件不是有效的 GGUF 模型")
                # rename 在 Windows 上不会覆盖期间由用户放入的同名模型。
                partial.rename(target)
                model_progress(offset, "模型下载完成", variant, spec)
                return {"operation": "download-model", "model": str(target), "sha256": spec.sha256,
                        "size": offset, "download_variant": variant}
            except (httpx.HTTPError, ValueError) as exc:
                errors.append(str(exc))
    raise ValueError("模型下载失败，请检查网络后重试，或选择已有 GGUF 文件。已下载内容会保留。\n" + "\n".join(errors))
