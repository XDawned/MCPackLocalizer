"""
路径配置与工作区目录管理

定义所有工作区相关路径常量，并提供确保目录存在的工具函数。
"""

import os
import sys
from pathlib import Path

# ── 项目根目录 ──────────────────────────────────────────────
# PyInstaller 打包后，sys._MEIPASS 指向临时解压目录，
# 而 sys.executable 指向实际的可执行文件路径。
# 我们需要使用可执行文件所在目录作为基准，而非临时解压目录。
def _get_app_root_dir() -> str:
    """获取应用根目录。

    - 开发模式：使用 src/ 的父目录（即 src/backend/）
    - PyInstaller 打包模式：使用可执行文件所在目录
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包模式：使用 .exe 所在目录
        return os.path.dirname(sys.executable)
    else:
        # 开发模式：__file__ 是 config/paths.py，其父目录是 src/config/，
        # 再上一级是 src/，再上一级是 backend 根目录
        _config_dir = os.path.dirname(os.path.abspath(__file__))
        _src_dir = os.path.dirname(_config_dir)
        return os.path.dirname(_src_dir)

_BACKEND_DIR = _get_app_root_dir()

# ── 工作区目录 ──────────────────────────────────────────────
WORKSPACE_DIR = os.path.join(_BACKEND_DIR, "workspace")
WORKSPACE_TEMP_DIR = os.path.join(WORKSPACE_DIR, "temp")
WORKSPACE_RESOURCEPACK_DIR = os.path.join(WORKSPACE_DIR, "resourcepacks")
WORKSPACE_BACKUP_DIR = os.path.join(WORKSPACE_DIR, "backups")
WORKSPACE_PATCH_DIR = os.path.join(WORKSPACE_DIR, "patches")
WORKSPACE_DOWNLOAD_CACHE_DIR = os.path.join(WORKSPACE_DIR, "downloads")


def ensure_workspace_dirs() -> None:
    """确保工作目录及其子目录存在。"""
    for path in (
        WORKSPACE_DIR,
        WORKSPACE_TEMP_DIR,
        WORKSPACE_RESOURCEPACK_DIR,
        WORKSPACE_BACKUP_DIR,
        WORKSPACE_PATCH_DIR,
        WORKSPACE_DOWNLOAD_CACHE_DIR,
    ):
        os.makedirs(path, exist_ok=True)