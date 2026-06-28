"""
应用配置类

从环境变量读取配置，支持 .env 文件加载。
所有运行时可配置的参数集中在此定义。
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# ── .env 文件加载 ──────────────────────────────────────────
# PyInstaller 打包后，__file__ 指向临时解压目录，需要使用 sys.executable 定位
if getattr(sys, 'frozen', False):
    _BACKEND_DIR = os.path.dirname(sys.executable)
else:
    _BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_env_candidates = [
    Path(_BACKEND_DIR) / ".env",          # src/backend/.env 或 .exe 同目录
    Path(_BACKEND_DIR).parent / ".env",    # 项目根目录 .env
]
for _env_path in _env_candidates:
    if _env_path.exists():
        load_dotenv(_env_path)
        break


class Settings:
    """全局配置类

    所有字段均从环境变量读取，提供合理的默认值。
    如需自定义，可通过 .env 文件或直接设置环境变量。
    """

    # ── CurseForge API 配置 ─────────────────────────────────
    CURSEFORGE_API_KEY: str = os.getenv("CURSEFORGE_API_KEY", "")

    # ── Modrinth API 配置（可选）────────────────────────────
    MODRINTH_API_KEY: str = os.getenv("MODRINTH_API_KEY", "")

    # ── 数据库配置 ──────────────────────────────────────────
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./mcpacks.db")

    # ── API 前缀 ────────────────────────────────────────────
    API_PREFIX: str = os.getenv("API_PREFIX", "/api/v1")

    # ── 服务端口 ────────────────────────────────────────────
    SERVER_HOST: str = os.getenv("SERVER_HOST", "127.0.0.1")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "25556"))

    # ── CORS 允许的来源 ────────────────────────────────────
    # 开发模式: http://localhost:5173 (Vite dev server)
    # 生产模式: http://127.0.0.1:25556 (直连后端) + null (file:// 协议的 origin)
    _default_cors = "http://localhost:5173,http://127.0.0.1:25556,null"
    CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS", _default_cors).split(",")

    # ── 平台权重（用于排序）─────────────────────────────────
    PLATFORM_WEIGHTS: dict[str, float] = {
        "curseforge": 1.2,
        "modrinth": 1.0,
    }

    # ── 去重相似度阈值 ──────────────────────────────────────
    DEDUP_SIMILARITY_THRESHOLD: float = 0.8

    # ── HTTP 请求超时（秒）──────────────────────────────────
    HTTP_TIMEOUT: int = 30

    # ── AI 翻译请求超时（秒）────────────────────────────────
    # 翻译请求通常耗时较长
    AI_TIMEOUT: int = 1800

    # ── AI 翻译请求最大重试次数 ─────────────────────────────
    AI_MAX_RETRIES: int = 3

    # ── AI 翻译请求重试初始间隔（秒），指数退避 ─────────────
    AI_RETRY_DELAY: float = 2.0


settings = Settings()