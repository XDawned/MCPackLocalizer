@echo off
REM 启动本地推理服务（独立 uv 环境）
setlocal
cd /d "%~dp0inference_service"
if not exist ".venv" (
    echo [MCPackLocalizer] 首次运行：创建独立 uv 环境并安装依赖（包含 transformers/torch，可能耗时较长）...
    uv sync
)
echo [MCPackLocalizer] 启动本地推理服务（端口 8765），关闭窗口或按 Ctrl+C 可停止...
uv run python server.py
endlocal
