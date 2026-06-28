"""
应用配置管理

从子模块重新导出所有公共配置，保持向后兼容。

使用方式：
    from ..config import settings                    # Settings 实例
    from ..config import WORKSPACE_DIR               # 路径常量
    from ..config import ensure_workspace_dirs        # 工具函数
    from ..config.settings import Settings            # Settings 类本身（如需）
    from ..config.paths import WORKSPACE_TEMP_DIR     # 单独引用路径常量
"""

from .paths import (  # noqa: F401
    WORKSPACE_DIR,
    WORKSPACE_TEMP_DIR,
    WORKSPACE_RESOURCEPACK_DIR,
    WORKSPACE_BACKUP_DIR,
    WORKSPACE_PATCH_DIR,
    WORKSPACE_DOWNLOAD_CACHE_DIR,
    ensure_workspace_dirs,
)
from .settings import settings  # noqa: F401
