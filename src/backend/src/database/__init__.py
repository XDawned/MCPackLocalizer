"""
数据库引擎、会话管理和迁移

从子模块重新导出所有公共 API，保持向后兼容。

使用方式：
    from ..database import engine, SessionLocal, Base, get_db, init_db
    from ..database.engine import engine          # 单独引用引擎
    from ..database.migration import init_db      # 单独引用迁移
"""

try:
    from .engine import Base, SessionLocal, engine, get_db  # noqa: F401
    from .migration import init_db  # noqa: F401
except ImportError:
    from src.database.engine import Base, SessionLocal, engine, get_db  # type: ignore  # noqa: F401
    from src.database.migration import init_db  # type: ignore  # noqa: F401
