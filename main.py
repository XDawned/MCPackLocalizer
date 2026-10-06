# [Module: project.main] [Status: 已完成] [Brief: 根目录入口转发至新版 PyQt6 桌面端]
import sys

if __name__ == "__main__":
    if sys.argv[1:2] == ["--release-smoke-test"]:
        import json
        import traceback
        from pathlib import Path

        try:
            from mcpacklocalizer.ui.smoke import main

            code = main()
        except Exception:  # noqa: BLE001 -- 自动检查入口记录启动异常，避免无控制台错误弹窗
            Path(sys.argv[2]).write_text(json.dumps({"code": 2, "result": {
                "error": traceback.format_exc()}}, ensure_ascii=False), encoding="utf-8")
            code = 2
        raise SystemExit(code)
    else:
        from mcpacklocalizer.ui.__main__ import main
    raise SystemExit(main())
