# Windows 构建与发布

用户使用说明与截图位于 `docs/RELEASING.md` 和 `docs/assets/`，构建时会导出成单文件 `使用说明.html`，放进每个后端软件 ZIP 的根目录。样式和图片全部内嵌，离线也能正常查看，不依赖 Markdown 阅读器或旁边的图片目录。

## GitHub Actions

1. 把源码、`uv.lock`、`docs/`、`packaging/`、`scripts/` 和 `.github/workflows/` 推送到默认分支，并启用仓库的 Actions。本地未提交的改动不会进入云端构建。
2. 在 Actions 页选择“构建 Windows 测试包”，点“Run workflow”，选默认分支启动，不用填参数。`main` / `master` 分支推送相关文件时也会自动构建。
3. 从同一次成功运行中下载 `release-cpu`、`release-vulkan`、`release-cuda`。解压 artifact 后里面还有一层软件 ZIP，需要再解压；`desktop-common` 是中间产物，不用管。
4. 在对应硬件上完成下方人工测试，记录 Run URL / ID、系统、硬件、驱动、模型和结果。
5. 在默认分支运行“发布已验证的版本”，填写 `source_run_id`、与包版本匹配的 `tag`、`test_notes`，勾选 `tested`，需要预览版再勾 `prerelease`。

发布流程只接受默认分支上的成功构建，会校验三个后端包的 SHA256、版本、提交和构建批次，然后直接上传那次构建的产物，不重新编译，也用不上额外的 PAT，仓库自带的 `GITHUB_TOKEN` 足够。标签不存在时新建并指向构建提交，已存在则必须指向同一提交；已经公开的同名 Release 不能替换，上传失败会保留草稿，用相同输入重试即可。

测试包保存 30 天，过期后只能重新构建并测试。重跑失败的构建时选“Re-run all jobs”，避免混入不同 Run Attempt 的产物。

## 本地构建

Windows x64、Python 3.12 环境下，在仓库根目录执行：

```powershell
uv sync --frozen --python 3.12 --group release
uv run --no-sync python scripts/release_tests.py
uv run --no-sync ruff check src tests scripts main.py
uv run --no-sync python scripts/build_release.py desktop
uv run --no-sync python scripts/build_release.py assemble --backend cpu
uv run --no-sync python scripts/build_release.py assemble --backend vulkan
uv run --no-sync python scripts/build_release.py assemble --backend cuda
```

可以只组装需要的后端。产物在 `dist/release/`，中间文件在 `build/release/`，下载缓存放 `build/downloads/`。重复组装前要自己清理对应后端的构建目录，脚本不会自动删。本地包只用于开发测试，正式发布只认 Actions 构建。

想单独预览使用说明：

```powershell
uv run --group release python scripts/export_docs.py
```

输出 `docs/使用说明.html`，生成文件不入库，平时维护 Markdown 和截图即可。图片缺失、格式不支持或引用远程图片时，导出会直接报错，免得发出去的说明缺图。

## 后端与版本

- CPU 包给没有可用独显的设备用，需要验证目标 CPU 指令集。
- Vulkan 包推荐 AMD 使用，其它支持 Vulkan 的显卡也能验证。
- CUDA 包基于 CUDA 12.4，适用于驱动兼容的 NVIDIA 显卡。

Python、后端 wheel、CUDA 运行库的版本、下载地址和 SHA256 都固定在 `packaging/backends.json`。构建不安装 CUDA Toolkit 或 Vulkan SDK，下载校验失败会直接停止，不会改用其它后端或退回源码编译。GGUF 模型单独准备，不随包分发；发布包携带 Python 运行时、VC++ Runtime、OpenMP DLL 和许可证。

改版本号时，`pyproject.toml` 与 `src/mcpacklocalizer/__init__.py` 要一起改，然后跑 `uv lock`。`2.0.0` 对应标签 `v2.0.0`，`2.0.0rc1` 对应 `v2.0.0rc1` 并勾选预览版本。

## 自动检查与人工测试

构建会执行 Ruff、全量 pytest、运行时与 DLL 校验，以及冻结 EXE 的 offscreen 后台扫描。`scripts/release_tests.py` 只把 AGENTS.md 记录的三个重构基线失败标为 xfail，其它失败一律中断构建。托管 runner 没有测试 GPU 和 GGUF 模型，CI 通过后仍要到实机试译。

每个后端至少完成以下测试，优先用没有开发 Python 环境的机器：

- 解压到含中文与空格的路径，启动 EXE，检查图标、术语、设置和界面。
- 双击 `使用说明.html`，断网查看全部截图；移动目录后再次打开。
- 移动软件目录后启动，在设置页恢复自动解释器选择，验证内置运行时。
- 扫描并提取示例整合包，验证语言 JSON、KubeJS、帕秋莉和独立 `patch/` 导出。
- 使用 GGUF 执行“检查推理环境”和“加载并试译”，确认实际后端；GPU 包的 CPU 回退不算通过。
- 验证本地批量翻译、暂停、继续及子进程退出后的显存释放。
- 验证 API 翻译、占位符保护和失败报告。
- 校验 ZIP 的 `.sha256`，记录设备、驱动、模型与结果，并核对依赖和运行库再分发许可。
