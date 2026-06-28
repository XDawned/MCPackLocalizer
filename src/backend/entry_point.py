import sys
import os

# 将 src/ 的父目录（即 src/backend/）加入 sys.path
# 这样 Python 就能找到 src 包及其所有子模块
_backend_dir = os.path.dirname(os.path.abspath(__file__))
_src_dir = os.path.join(_backend_dir, 'src')

if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

# 以模块方式导入 src.main，确保相对导入正常工作
from src.main import app  # noqa: E402

if __name__ == '__main__':
    import uvicorn
    from src.config import settings
    uvicorn.run(
        "src.main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=False,
    )