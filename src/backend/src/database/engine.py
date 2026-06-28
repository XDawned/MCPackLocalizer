"""
数据库引擎和会话管理

使用 SQLAlchemy 同步引擎 + SQLite，通过依赖注入提供数据库会话。
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

try:
    from ..config import settings
except ImportError:
    from src.config import settings  # type: ignore

# ── 创建引擎 ──────────────────────────────────────────────
# SQLite 需要 check_same_thread=False 以支持多线程
_connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    echo=False,  # 生产环境关闭 SQL 日志
)

# ── 创建会话工厂 ──────────────────────────────────────────
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ── 声明式基类 ────────────────────────────────────────────
Base = declarative_base()


def get_db():
    """
    FastAPI 依赖注入：获取数据库会话。

    用法：
        @app.get("/items")
        def read_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()