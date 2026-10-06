# [Module: scripts.smoke_release] [Status: 已完成] [Brief: 使用包内解释器验证资源、扫描协议与本地推理 DLL]
from __future__ import annotations

import ast
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from mcpacklocalizer.application.config.settings import Settings
from mcpacklocalizer.paths import INSTALL_HOME, MODEL_HOME, RESOURCES
from mcpacklocalizer.runtime import inference_python, task_python


def check(directory: Path, backend: str):
    directory = directory.resolve()
    assert INSTALL_HOME == directory, "内置解释器未识别安装目录"
    assert MODEL_HOME == directory, "模型默认目录错误"
    assert (RESOURCES / "glossary/glossary_en_zh.json").is_file(), "术语资源缺失"
    assert (RESOURCES / "glossary/common_words_en.txt").is_file(), "排除词表缺失"
    assert (RESOURCES / "icon.ico").is_file(), "图标缺失"
    assert Settings.defaults().runtime_python == "", "自动运行时不应保存绝对路径"
    assert Path(task_python()) == Path(sys.executable), "任务解释器不是内置解释器"
    assert Path(inference_python()) == Path(sys.executable), "推理解释器不是内置解释器"
    assert (directory / "MCPackLocalizer.exe").is_file(), "桌面 EXE 缺失"
    assert (directory / "使用说明.html").is_file(), "离线使用说明缺失"
    with tempfile.TemporaryDirectory(prefix="mcpl-发布 验证-") as temporary:
        root = Path(temporary)
        lang = root / "整合包/kubejs/assets/example/lang/en_us.json"
        lang.parent.mkdir(parents=True)
        lang.write_text('{"item.example.iron": "Iron Ingot"}', encoding="utf-8")
        env = os.environ.copy()
        for key in list(env):
            if key.startswith(("MPLT_", "PYTHON")):
                env.pop(key)
        payload = {"operation": "scan", "root": str(root / "整合包"), "recognition_scope": "kubejs"}
        result = subprocess.run([task_python(), "-u", "-m", "mcpacklocalizer.application.tasks.worker"],
                                input=json.dumps(payload), text=True, encoding="utf-8", capture_output=True,
                                timeout=90, env=env, cwd=temporary, check=False)
        report = json.loads(result.stdout)
        assert result.returncode == 0 and "error" not in report, (report, result.stderr)
        assert report.get("entries", 0) > 0, report
        env["QT_QPA_PLATFORM"] = "offscreen"
        output = root / "桌面检查.json"
        desktop = subprocess.run([str(directory / "MCPackLocalizer.exe"), "--release-smoke-test", str(output),
                                  str(root / "整合包")], check=False, timeout=120, env=env, cwd=temporary,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        desktop_report = json.loads(output.read_text(encoding="utf-8"))
        assert desktop.returncode == 0 and desktop_report["code"] == 0, desktop_report
        assert desktop_report["result"].get("entries", 0) > 0, desktop_report
    # GPU 绑定直接依赖驱动 DLL，在无显卡的托管 runner 上只做静态检查。
    binding = importlib.util.find_spec("llama_cpp")
    assert binding and binding.origin, "推理绑定缺失"
    api = Path(binding.origin).parent / "llama_cpp.py"
    ast.parse(api.read_text(encoding="utf-8"))
    if backend == "cpu":
        from llama_cpp import llama_cpp

        assert callable(llama_cpp.llama_backend_init), "推理绑定入口缺失"
        llama_cpp.llama_backend_init()
        print(llama_cpp.llama_print_system_info().decode("utf-8", errors="replace"), flush=True)
        llama_cpp.llama_backend_free()
    print("内置运行时、资源、扫描协议和推理绑定检查通过", flush=True)


if __name__ == "__main__":
    check(Path(sys.argv[1]), sys.argv[2])
