"""Smoke test: start the inference service, hit a few endpoints, then stop."""
import os
import subprocess
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SVC_DIR = ROOT / "inference_service"
PY = SVC_DIR / ".venv" / "Scripts" / "python.exe"
PORT = 8766
BASE = f"http://127.0.0.1:{PORT}"

env = os.environ.copy()
env["MCPACK_PORT"] = str(PORT)
proc = subprocess.Popen(
    [str(PY), "server.py"],
    cwd=str(SVC_DIR),
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)
try:
    last_err = None
    for _ in range(40):
        try:
            r = requests.get(f"{BASE}/health", timeout=1)
            if r.status_code == 200:
                break
        except Exception as exc:
            last_err = exc
            time.sleep(0.3)
    else:
        raise RuntimeError(f"service did not become ready: {last_err}")
    print("health:", r.json())

    r = requests.post(f"{BASE}/translate", json={"text": "a.jpg"}, timeout=2)
    print("image skip:", r.status_code, r.json())

    r = requests.post(f"{BASE}/translate", json={"text": "https://x.com"}, timeout=2)
    print("url skip:", r.status_code, r.json())

    r = requests.post(f"{BASE}/translate", json={"text": "&aHello&b"}, timeout=2)
    print("colour pre:", r.status_code, r.json())
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
