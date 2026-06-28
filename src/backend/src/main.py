"""
MCPackLocalizer 后端应用入口

FastAPI 应用主文件：注册路由、配置 CORS、初始化数据库。

运行方式：
  开发: python -m src.main     (在 src/backend/ 目录下)
  或:   uvicorn src.main:app --host 127.0.0.1 --port 25556
"""

import logging
import sys
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .config import ensure_workspace_dirs, settings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理。

    启动时：初始化数据库表结构。
    关闭时：清理资源。
    """
    from .database import init_db
    logger.info("Starting MCPackLocalizer backend...")
    # 确保数据库目录存在
    if settings.DATABASE_URL.startswith("sqlite:///"):
        db_path = settings.DATABASE_URL.replace("sqlite:///", "")
        if db_path.startswith("./"):
            db_path = db_path[2:]
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

    # 确保工作区目录存在
    ensure_workspace_dirs()

    # 初始化数据库表
    init_db()
    logger.info("Database initialized successfully.")

    yield

    logger.info("Shutting down MCPackLocalizer backend...")


# 创建 FastAPI 应用
app = FastAPI(
    title="MCPackLocalizer",
    description="Minecraft 整合包本地化工具后端 API",
    version="2.0.0",
    lifespan=lifespan,
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
from .routers.search import router as search_router
from .routers.translate import router as translate_router
from .routers.apply import router as apply_router
from .routers.feedback import router as feedback_router
from .routers.glossary import router as glossary_router
from .routers.settings import router as settings_router
from .routers.workflow import router as workflow_router
from .routers.pack_scan import router as pack_scan_router

app.include_router(search_router)
app.include_router(translate_router)
app.include_router(apply_router)
app.include_router(feedback_router)
app.include_router(glossary_router)
app.include_router(settings_router)
app.include_router(workflow_router)
app.include_router(pack_scan_router)


# ==================== 基础端点 ====================


@app.get("/")
async def root():
    """根路径：如果前端静态文件存在则返回 index.html，否则返回 API 信息"""
    frontend_dir = _get_frontend_dir()
    if frontend_dir:
        index_path = os.path.join(frontend_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
    return {
        "name": "MCPackLocalizer API",
        "version": "2.0.0",
        "docs": "/docs",
    }


def _get_frontend_dir():
    """获取前端静态文件目录。

    PyInstaller 打包模式：可执行文件同目录下的 frontend/ 子目录
    开发模式：项目根目录下的 build/frontend/ 目录
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包模式：可执行文件同目录
        base_dir = os.path.dirname(sys.executable)
    else:
        # 开发模式：src/backend/ 的上级目录（项目根目录）
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    candidates = [
        os.path.join(base_dir, "frontend"),      # 打包模式: exe 同目录/frontend
        os.path.join(base_dir, "build", "frontend"),  # 开发模式: 项目根/build/frontend
    ]
    for d in candidates:
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "index.html")):
            return d
    return None


# 挂载前端静态文件（必须在所有 API 路由之后）
_frontend_dir = _get_frontend_dir()
if _frontend_dir:
    # 挂载静态资源目录（assets 等）
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dir, "assets")), name="static_assets")
    logger.info(f"Frontend static files mounted from: {_frontend_dir}")
else:
    logger.info("No frontend static files found, running in API-only mode.")


@app.get("/health")
async def health():
    """健康检查端点"""
    return {"status": "ok"}


# ==================== 启动入口 ====================

if __name__ == "__main__":
    import uvicorn

    # 确保 src/backend/ 目录在 Python 路径中，使 "src.main" 可被导入
    sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..")))

    uvicorn.run(
        "src.main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=False,
    )


