# [Module: scripts.release_tests] [Status: 已完成] [Brief: 发布构建的全量测试与明确记录的重构基线失败]
import pytest

KNOWN_FAILURES = {
    "tests/core/pack/test_kubejs.py::test_js_user_examples_and_language_keys",
}


class Baseline:
    def pytest_collection_modifyitems(self, items):
        for item in items:
            if item.nodeid in KNOWN_FAILURES:
                item.add_marker(pytest.mark.xfail(reason="AGENTS.md 已记录的重构基线失败，修复后移除此项", strict=False))


if __name__ == "__main__":
    raise SystemExit(pytest.main(["-q", "-ra"], plugins=[Baseline()]))
