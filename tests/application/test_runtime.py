# [Module: tests.runtime] [Status: 已完成] [Brief: 发布目录移动、自动运行时与冻结进程的 DLL 隔离]
import sys
from pathlib import Path

import pytest

from mcpacklocalizer.application.config.settings import Settings
from mcpacklocalizer.core.translation.local import ModelConfig, WorkerClient
from mcpacklocalizer.runtime import (
    bundled_python,
    external_dll_search,
    inference_python,
    task_python,
    worker_environment,
)


def test_bundled_runtime_is_resolved_after_moving_directory(mocker, tmp_path, monkeypatch):
    monkeypatch.delenv("MPLT_RUNTIME_PYTHON", raising=False)
    for name in ("初始目录", "移动后的目录 with spaces"):
        directory = tmp_path / name
        python = directory / "runtime/python.exe"
        python.parent.mkdir(parents=True)
        python.touch()
        mocker.patch("mcpacklocalizer.runtime.INSTALL_HOME", directory)
        assert Settings.defaults().runtime_python == ""
        assert Path(task_python()) == python
        assert Path(WorkerClient(ModelConfig(), "").python) == python


def test_missing_bundled_python_never_falls_back_to_desktop_exe(mocker, tmp_path):
    mocker.patch("mcpacklocalizer.runtime.INSTALL_HOME", tmp_path)
    with pytest.raises(RuntimeError, match="重新解压"):
        bundled_python()


def test_explicit_runtime_and_environment_override_are_preserved(mocker, tmp_path, monkeypatch):
    mocker.patch("mcpacklocalizer.runtime.INSTALL_HOME", tmp_path)
    monkeypatch.setenv("MPLT_RUNTIME_PYTHON", "D:/custom/env/python.exe")
    assert inference_python() == "D:/custom/env/python.exe"
    assert inference_python("D:/explicit/python.exe") == "D:/explicit/python.exe"


def test_frozen_worker_environment_filters_only_internal_dll_paths(mocker, tmp_path, monkeypatch):
    internal = tmp_path / "_internal"
    mocker.patch.object(sys, "frozen", True, create=True)
    mocker.patch.object(sys, "_MEIPASS", str(internal), create=True)
    monkeypatch.setenv("PATH", f"{internal};{internal / 'Qt/bin'};C:/Windows/System32;{internal}other")
    monkeypatch.setenv("PYTHONHOME", "D:/developer-python")
    monkeypatch.setenv("MY_API_KEY", "private")
    env = worker_environment()
    assert env["PATH"] == f"C:/Windows/System32;{internal}other"
    assert "PYTHONHOME" not in env
    assert env["MY_API_KEY"] == "private"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PYTHONFAULTHANDLER"] == "1"


def test_windows_dll_directory_restored_even_when_spawn_fails(mocker):
    mocker.patch.object(sys, "frozen", True, create=True)
    kernel = mocker.Mock()

    def directory(size, buffer):
        if buffer is not None:
            buffer.value = "D:/app/_internal"
        return 16

    kernel.GetDllDirectoryW.side_effect = directory
    kernel.SetDllDirectoryW.return_value = 1
    mocker.patch("ctypes.WinDLL", return_value=kernel)
    with pytest.raises(OSError), external_dll_search():
        raise OSError("启动失败")
    assert kernel.SetDllDirectoryW.call_args_list == [mocker.call(None), mocker.call("D:/app/_internal")]
