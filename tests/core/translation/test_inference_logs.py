# [Module: tests.inference_logs] [Status: 已完成] [Brief: 真实推理子进程的标准错误转发与尾部排空]
import subprocess
import sys

import pytest

from mcpacklocalizer.core.translation.local import ModelConfig, WorkerClient


@pytest.mark.parametrize("save_log", [True, False])
def test_inference_stderr_reaches_parent_and_task_file(tmp_path, mocker, capsys, save_log):
    # 用轻量协议进程模拟原生推理库，不需要 GGUF 或 GPU。
    script = '''
import json, sys
sys.stdin.readline()
print("原生模型诊断", file=sys.stderr, flush=True)
print(json.dumps({"ready": {"backend": "test"}}), flush=True)
for line in sys.stdin:
    print("Traceback (most recent call last):", file=sys.stderr, flush=True)
    print("  模型内部调用", file=sys.stderr, flush=True)
    print("RuntimeError: 推理失败", file=sys.stderr, flush=True)
    print(json.dumps({"translation": "译文"}), flush=True)
'''
    real_popen = subprocess.Popen
    popen = mocker.patch("mcpacklocalizer.core.translation.local.subprocess.Popen",
                         side_effect=lambda args, **kwargs: real_popen([sys.executable, "-u", "-c", script], **kwargs))
    path = tmp_path / "inference.log"
    with WorkerClient(ModelConfig(), python=sys.executable, timeout=10, log_path=path if save_log else None) as client:
        assert client.translate("Source") == "译文"
    assert popen.call_args.kwargs["stderr"] == subprocess.PIPE
    captured = capsys.readouterr().err
    for fragment in ("原生模型诊断", "模型内部调用", "RuntimeError: 推理失败"):
        assert fragment in captured
        if save_log:
            assert fragment in path.read_text(encoding="utf-8")
    assert path.exists() == save_log
    assert not client.error_reader.is_alive()
