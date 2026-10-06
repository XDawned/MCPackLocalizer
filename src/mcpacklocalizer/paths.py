# [Module: paths] [Status: 已完成] [Brief: 开发目录、安装资源与用户数据路径]
from __future__ import annotations

import os
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
SOURCE_ROOT = PACKAGE.parent
WORKSPACE = SOURCE_ROOT.parent if SOURCE_ROOT.name == "src" and not getattr(sys, "frozen", False) else None
# 内置解释器与桌面 EXE 共享安装根目录，用户数据仍独立存放。
_executable = Path(sys.executable).resolve()
INSTALL_HOME = (_executable.parent if getattr(sys, "frozen", False) else
                _executable.parent.parent if _executable.parent.name == "runtime" and
                (_executable.parent.parent / "runtime.json").is_file() else None)
DATA_HOME = Path(os.getenv("MPLT_DATA_DIR") or
                 str(Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "MCPackLocalizer"))
PROJECT = WORKSPACE or DATA_HOME
MODEL_HOME = INSTALL_HOME or PROJECT
RESOURCES = WORKSPACE / "resources" if WORKSPACE else PACKAGE / "resources"


def migrated_path(value: str) -> str:
    """Resolve saved paths after the source-tree migration without rewriting tasks."""
    if not value or WORKSPACE is None:
        return value
    path = Path(value)
    for before, after in (("cli/output", "data/tasks"), ("common", "resources/glossary"),
                          ("cache", "data/legacy/cache"), ("save", "data/legacy/save"), ("work", "data/legacy/work")):
        try:
            suffix = path.resolve().relative_to((WORKSPACE / before).resolve())
        except ValueError:
            continue
        candidate = WORKSPACE / after / suffix
        if candidate.exists():
            return str(candidate)
    return value
