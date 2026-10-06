# [Module: runtime] [Status: 已完成] [Brief: 内置解释器定位与冻结程序的子进程隔离]
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path

from .paths import INSTALL_HOME, SOURCE_ROOT


def bundled_python() -> Path | None:
    """发布目录缺少运行时应明确报错，避免把桌面 EXE 当作解释器。"""
    if INSTALL_HOME is None:
        return None
    python = INSTALL_HOME / "runtime/python.exe"
    if not python.is_file():
        raise RuntimeError("发布目录缺少 runtime/python.exe，请重新解压完整的软件包")
    return python


def task_python() -> str:
    return str(bundled_python() or sys.executable)


def inference_python(preference: str = "") -> str:
    return preference or os.getenv("MPLT_RUNTIME_PYTHON") or task_python()


def worker_environment() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # 在导入后台模块前启用原生崩溃堆栈，非法指令等错误无法由 Python 的 except 捕获。
    env["PYTHONFAULTHANDLER"] = "1"
    modules = INSTALL_HOME / "runtime/app" if INSTALL_HOME else SOURCE_ROOT
    env["PYTHONPATH"] = str(modules) + os.pathsep + env.get("PYTHONPATH", "")
    if getattr(sys, "frozen", False):
        # 外部解释器不应继承打包器指向其内部 DLL 的搜索路径。
        internal = str(Path(sys._MEIPASS).resolve()).casefold()
        env["PATH"] = os.pathsep.join(
            part for part in env.get("PATH", "").split(os.pathsep)
            if part and not (str(Path(part).resolve()).casefold() == internal or
                             str(Path(part).resolve()).casefold().startswith(internal + os.sep))
        )
        env.pop("PYTHONHOME", None)
    return env


@contextmanager
def external_dll_search():
    """仅在创建外部进程时恢复 Windows 默认 DLL 搜索，随后恢复桌面环境。"""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        yield
        return
    import ctypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetDllDirectoryW.argtypes = [ctypes.c_uint32, ctypes.c_wchar_p]
    kernel.GetDllDirectoryW.restype = ctypes.c_uint32
    kernel.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
    kernel.SetDllDirectoryW.restype = ctypes.c_int
    size = kernel.GetDllDirectoryW(0, None)
    buffer = ctypes.create_unicode_buffer(size + 1)
    kernel.GetDllDirectoryW(len(buffer), buffer)
    previous = buffer.value or None
    if not kernel.SetDllDirectoryW(None):
        raise RuntimeError("无法为后台任务恢复 DLL 搜索路径")
    try:
        yield
    finally:
        kernel.SetDllDirectoryW(previous)
