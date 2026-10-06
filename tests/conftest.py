# [Module: tests.fixtures] [Status: 开发中] [Brief: 所有文件写入/数据库/网络测试均使用替身]
from pathlib import Path

import pytest


@pytest.fixture
def memory_files(mocker):
    files = {}

    def norm(path):
        return str(path).replace("\\", "/").rstrip("/")

    def is_dir(path):
        key = norm(path) + "/"
        return any(name.startswith(key) for name in files)

    def descendants(path, pattern="*"):
        key = norm(path) + "/"
        result = [Path(name) for name in files if name.startswith(key)]
        return result if pattern == "*" else [p for p in result if p.match(pattern)]

    def children(path, pattern="*"):
        key = norm(path) + "/"
        result = {Path(key + name[len(key):].split("/")[0]) for name in files if name.startswith(key)}
        return sorted(p for p in result if pattern == "*" or p.match(pattern))

    mocker.patch.object(Path, "resolve", lambda path, strict=False: path.absolute())
    mocker.patch.object(Path, "is_file", lambda path: norm(path) in files)
    mocker.patch.object(Path, "is_dir", is_dir)
    mocker.patch.object(Path, "exists", lambda path: norm(path) in files or is_dir(path))
    mocker.patch.object(Path, "rglob", descendants)
    mocker.patch.object(Path, "glob", children)
    mocker.patch.object(Path, "iterdir", children)
    mocker.patch.object(Path, "read_bytes", lambda path: files[norm(path)] if isinstance(files[norm(path)], bytes)
                       else files[norm(path)].encode("utf-8"))
    mocker.patch.object(Path, "read_text", lambda path, **kwargs: files[norm(path)].decode(kwargs.get("encoding", "utf-8"))
                       if isinstance(files[norm(path)], bytes) else files[norm(path)])
    return files
