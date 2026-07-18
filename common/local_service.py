"""本地推理服务 HTTP 客户端

通过 HTTP 调用 inference_service/ 提供的 FastAPI 服务，避免主程序引入
transformers / torch / tokenizers 等大体积依赖。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import requests


class LocalInferenceClient:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> tuple[bool, str]:
        try:
            r = requests.get(f"{self.base_url}/health", timeout=3)
            r.raise_for_status()
            data = r.json()
            return bool(data.get("model_loaded")), data.get("load_error") or "ok"
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"

    def translate(self, text: str, keep_original: bool = False) -> str:
        r = requests.post(
            f"{self.base_url}/translate",
            json={"text": text, "keep_original": keep_original},
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("translation", text)


def get_local_client(base_url: Optional[str] = None) -> LocalInferenceClient:
    from common.config import cfg
    url = base_url or cfg.get(cfg.localServiceUrl)
    return LocalInferenceClient(url)


def try_auto_start_service() -> bool:
    """若用户启用自动启动，则尝试以独立 uv 环境拉起 inference_service。

    返回是否成功派生了子进程（不代表服务已就绪，启动是异步的）。
    """
    from common.config import cfg
    if not cfg.get(cfg.localServiceAutoStart):
        return False
    project_root = Path(__file__).resolve().parent.parent
    svc_dir = project_root / "inference_service"
    if not svc_dir.exists():
        return False
    if sys.platform == "win32":
        bat = project_root / "start_inference_service.bat"
        if bat.exists():
            subprocess.Popen(  # noqa: S603,S607
                ["cmd", "/c", str(bat)],
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                close_fds=True,
            )
            return True
    try:
        subprocess.Popen(  # noqa: S603,S607
            ["uv", "run", "python", "server.py"],
            cwd=str(svc_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        return True
    except Exception:  # noqa: BLE001
        return False

