# MCPackLocalizer

本地 HY-MT-2 GGUF 或远程 / 本地 API 驱动的 Minecraft 整合包汉化 PyQt6 桌面工具，
`core/`（无 Qt 引擎）+ `application/`（无 Qt 服务）+ `ui/`（Fluent 界面）同仓库。
根目录 `README.md` 是旧版 CLI 工具集说明，与当前代码不符；以本文件、`pyproject.toml` 和源码为准。

## 命令

Python 固定 3.12（`requires-python = ">=3.12,<3.13"`），`tool.uv.environments` 只解析 Windows AMD64。

```powershell
uv sync --python 3.12          # 安装依赖（含 dev 组）
uv run mcpl-desktop            # 启动桌面，等效 uv run python main.py
uv run pytest -q               # 全量；pythonpath 已由 pyproject 配置，无需手动设置
uv run pytest tests/core/pack/test_patch.py -q            # 单个文件
uv run pytest tests/core/pack/test_patch.py::test_xxx -q  # 单个用例
uv run ruff check src tests main.py                       # line-length 120 / py312
```

`main.py` 导入的是安装后的 `mcpacklocalizer`；未安装时直接 `python main.py` 会 ModuleNotFoundError，
用 `uv run` 或 `$env:PYTHONPATH='src'`。

## 架构边界

- `core/` 与 `application/` 不导入 PyQt6 / qfluentwidgets；Qt 只出现在 `ui/`。
- 长任务经子进程执行：`ui/process.py` 经 `runtime.task_python()` 选择解释器后启动
  `python -u -m mcpacklocalizer.application.tasks.worker`（发布版使用包内解释器），
  Job JSON 写 stdin（上限 16 MiB），结果 JSON 从 stdout 读回，进度行从 stderr 读（需含
  `completed` / `failed` / `remaining` 键）。退出码：0 成功、1 部分完成、2 失败或扫描未完成、130 暂停。
- 协议与入口：`application/tasks/jobs.py`（Job.payload/from_payload）、`tasks/requests.py`（界面意图→Job）、
  `tasks/service.py:execute`（实际执行）。
- `paths.py`：源码运行时 `WORKSPACE`=仓库根、资源取仓库 `resources/`；安装运行时资源在包内。
  `migrated_path()` 把 `cli/output`、`common`、`cache`、`save`、`work` 旧路径映射到新位置，改路径逻辑别绕过。
- 设置存于 `QSettings("MCPackLocalizer", "Desktop")`（Windows 注册表），不是 JSON 文件；测试可注入
  `MainWindow(preferences=...)`。

## 数据与运行

- 术语库 `resources/glossary/glossary_en_zh.json`，排除词表同目录 `common_words_en.txt`；用户覆盖项单独保存，不改预设文件。
- 新任务默认存 `%LOCALAPPDATA%/MCPackLocalizer/tasks`；仓库历史任务在 `data/tasks/`（均不入库）。
- 翻译产物始终写独立 `patch/` 目录，绝不改写整合包原文件。
- `.env.example` 不会自动加载；只读进程环境变量：`MPLT_MODEL_PATH`、`MPLT_RUNTIME_PYTHON`、
  `MPLT_GLOSSARY_PATH`、`MPLT_DATA_DIR`、`MPLT_CACHE_DIR`，API 密钥变量名在接口配置里指定。
- 本机若存在 `.tmp/vulkan-venv/Scripts/python.exe` 会自动作为默认推理解释器（backend=vulkan），可用
  `MPLT_RUNTIME_PYTHON` 覆盖。llama-cpp-python 不在主依赖，见 `requirements/inference.txt`；
  缺它时本地 GGUF 不可用，API 翻译可用。
- 发布目录包含桌面 EXE、`runtime/python.exe` 和 `runtime.json`；发布版解释器设置留空表示自动选择，
  不保存内置解释器的绝对路径。`paths.INSTALL_HOME` 用于定位发布目录与默认模型，用户数据仍独立存放。
- 打包与人工测试后发布见 `docs/BUILDING.md`；用户使用说明在 `docs/RELEASING.md`，
  构建时自动导出内嵌截图的 `使用说明.html`。固定后端 wheel 与 SHA256 在 `packaging/backends.json`，
  两个 GitHub 工作流分别负责构建和人工确认后发布，发布必须复用被测试的同次构建产物。

## 约定与产品约束

- 每个 `.py` 首行保留模块头注释 `# [Module: 名称] [Status: 已完成|开发中] [Brief: ...]`，新增文件照写。
- 界面文案、注释、异常消息用中文。
- 接口分为专用翻译模型与大模型，使用 `core/translation/templates.py` 的完整系统/用户模板；系统预设也可编辑，
  用户模板通过接口 `template_id` 绑定，本地模型绑定独立记忆。HY-MT-2 仍只支持中文，Index-Translate 支持其它目标语言。
  新任务保存模板快照，旧任务保留原有提示词行为；本地 API 默认并发 1，远端默认 3，已有显式值不能覆盖。
- 本地 GGUF 通过“添加接口”弹窗添加，配置在 `Settings.local_profiles` 中独立保存，`active_local` 选择当前本地接口。
  旧 `model` / `local_model_templates` 会迁移；模型身份与模板格式分别使用 `model_family` / `prompt_family`，不要用模板重命名模型。
- 占位符默认严格校验（`allow_missing_placeholders` 可放宽），保留“先直译、失败再掩码兜底”的两段策略。

## 测试注意

- 分组 `tests/core`、`tests/application`、`tests/ui` 与 `src/` 对应；UI 测试由 `tests/ui/conftest.py` 自动设
  `QT_QPA_PLATFORM=offscreen`，无需真实显示器。
- 测试不写真实磁盘：`tests/conftest.py` 的 `memory_files` fixture 在类级别 mock `pathlib.Path` 的方法，
  涉及文件系统的测试复用它或 `tmp_path`。
- 当前有 1 个已知失败，与接口和提示词模板重构无关：
  `tests/core/pack/test_kubejs.py::test_js_user_examples_and_language_keys`。

## 本机工具

- 占位符实验：`.tmp/placeholder_lab.py` + `.tmp/PLACEHOLDER_LAB.md`（不入库）。
- 许可证 GPL-3.0；界面基于 PyQt-Fluent-Widgets。
