<div align="center">
  <img width="115" height="115" src="https://i.postimg.cc/FzQGyDgr/logo.png">
</div>
<div align="center">
    <a href="LICENSE">
        <img src="https://img.shields.io/badge/license-GPL%203.0-yellow.svg" alt="license">
    </a>
    <a href="https://github.com/XDawned/MCPackLocalizer/releases/latest">
        <img src="https://img.shields.io/badge/releases-v2.0.0-blue.svg" alt="releases">
    </a>
    <a href="https://www.python.org/">
        <img src="https://img.shields.io/badge/python-3.12-blue.svg" alt="python">
    </a>
    <a href="https://github.com/zhiyiYo/PyQt-Fluent-Widgets">
        <img src="https://img.shields.io/badge/UI-PyQt6--Fluent--Widgets-brightgreen.svg" alt="ui">
    </a>

# MCPackLocalizer · 整合包本地化工具
</div>

使用本地 HY-MT-2 GGUF 或远程 / 本地 API 模型汉化 Minecraft 整合包的 PyQt6 Fluent 桌面工具。
覆盖“识别 → 翻译 → 校润 → 补丁”全流程，支持任务与语言资源扫描、术语注入、禁翻保护、
断点续跑、版本增量复用、人工审核及独立汉化补丁。旧 CLI 子项目已合并，产品入口统一为桌面端。

## 功能

### 双翻译引擎

- **本地 HY-MT-2 GGUF**：通过独立 Python 解释器调用 llama-cpp-python 推理，支持 auto / cpu / vulkan / cuda 后端；
  模型文件与推理解释器在设置页选择，项目会自动发现 `.tmp/vulkan-venv/`。
- **API 接口**：支持 OpenAI 兼容（`/chat/completions`）、Anthropic（`/messages`）、Gemini（`generateContent`）协议，
  可对接官方平台、第三方代理或无密钥的本地兼容服务。
- 每个接口独立保存并发数、token 预算、请求间隔、重试、超时、温度、输出 token 参数名、扩展请求体与密钥环境变量；
  本地 GGUF 与 API 的参数互不影响。
- 接口管理支持添加、试译、激活、编辑、复制与删除，按本地 / 官方 / 自定义自动分组，当前激活接口高亮显示。
- 密钥仅保存在本地设置或指定环境变量中，不写入任务快照与日志。

### 整合包翻译流程

- 三阶段工作台：**识别 → 翻译 → 校润**。识别阶段不调用模型，结果自动保存为可续跑任务。
- 识别页左侧按资源类型和文件展示待翻译内容，右侧可搜索并预览语言键、原文与背景。
- 翻译阶段显示条目统计（总数 / 完成 / 待翻译 / 失败）、实时进度与日志，支持暂停、续跑和限制本次翻译条数。
- 校润阶段可按状态筛选（未翻译 / 失败 / 已翻译 / 已复用 / 已审核）、搜索、人工修改并保存为已审核，
  质量提醒即时显示，可随时重新导出补丁。
- 原文与译文语言在设置中选择（16 种语言）；已有任务保留创建时的语言。
  HY-MT-2 固定模板输出简体中文，其它输出语言使用 API 的 MC 提示词模式。

### 识别范围（可多选）

- **任务与整合包语言资源**：FTB Quests（SNBT / JSON5 / NBT）及整合包自带语言文件。
- **KubeJS**：脚本显示文本、assets JSON 文本及语言文件，基于 tree-sitter 离线识别。
- **帕秋莉手册**：从整合包文件、启用的资源包与模组归档中读取手册内容。
- **模组缺失汉化**：只读扫描模组语言覆盖率，结合 CFPA 汉化包与共享译库进行复用与补充翻译（目前支持 en_us → zh_cn）。

### 断点续跑与复用

- 逐条 SQLite 检查点（`state.sqlite3`）加便携快照（`snapshot.json`），暂停后下次打开任务继续处理未完成条目。
- 版本升级可选择上一版本任务或快照，自动对比差异并复用已审核译文，变更 / 新增 / 删除 / 冲突数量一目了然。
- 模组共享译库支持“只复用已审核译文”“复用已审核译文和模型草稿”“关闭共享复用”三种策略，
  测试中的模型译文以草稿形式保存，可人工确认后再复用。

### 术语与质量校验

- 预设术语库（i18n-dict）与常用词排除列表随程序分发，按 50 / 100 / 200 条分页搜索与编辑，修改以用户覆盖项保存，
  支持导入 / 导出覆盖 JSON、清空译文禁用预设词条。
- 禁翻表保护不应翻译的专有名词与符号；术语注入可开关，并预留术语 token 预算。
- 默认严格校验占位符、颜色与格式代码、URL、资源 ID、printf 格式、转义换行等；可开启“允许保留符缺失或换序”，
  失败项仍采用译文并在质量列提醒；保留“先直译再掩码兜底”策略。
- 数字与维度变动只做质量提示，不阻断输出。
- “翻译测试”页可用一段文本检查当前模型、提示词、术语、禁翻与颜色代码效果，并显示 API token 用量。

### 补丁与审核

- 翻译始终输出到任务目录下的独立 `patch/`，不会原地修改游戏文件；附带 `manifest.json` 覆盖清单与 `report.html` 审核报告。
- 可选替换已有 FTBQ 目标语言文件、加入对应版本的 I18nUpdateMod（在线按版本下载或使用本地 JAR）。
- KubeJS 无法确定的表达式保留原文并输出诊断；被排除的资源记录原因并保留原文件。
- 补丁导出后由用户复制到游戏目录，覆盖前请自行备份。

### 辅助工具

- **任务提取**：无需模型即可提取待翻译语言文件（输出语言文件加 `mapping.json`）、回填已翻译文件生成补丁，
  以及 json / json5 / snbt / lang 格式互转，二进制 NBT 仅替换文本字节。
- **KubeJS 脚本翻译**：在翻译阶段单独选择大模型 API，仅替换脚本中的显示文本并保留代码结构；
  未配置脚本接口时仍可识别与校润。
- **帕秋莉手册**：翻译结果导出为目标语言资源包；模组中直写的书名与首页说明生成独立 JAR 补丁。
- **模组译库**：只读覆盖率报告、CFPA 汉化包获取（在线 / 离线缓存）与 I18nUpdateMod 元数据校验。

## 安装与启动

需要 Windows 10/11、Python 3.12 与 [uv](https://github.com/astral-sh/uv)。在项目根目录执行：

```powershell
uv sync --python 3.12
uv run mcpl-desktop
# 也可以
uv run python main.py
```

桌面依赖不强制编译推理后端；只使用 API 翻译时无需安装 llama-cpp-python。

### 本地推理环境（可选）

本地 GGUF 需要一个安装了 llama-cpp-python 的 Python 3.12 解释器，按需构建 CPU / Vulkan / CUDA 后端：

```powershell
py -3.12 -m venv .runtime
.runtime/Scripts/python.exe -m pip install -r requirements/inference.txt
```

将 GGUF 模型放入 `models/`（默认 `models/Hy-MT2-7B-GGUF/Hy-MT2-7B-Q4_K_M.gguf`，也可使用 1.8B 小模型），
然后在“设置 → 本地推理”选择模型文件与解释器，并通过“检查推理环境”“模型试译”确认链路正常。

## 使用流程

1. **选择引擎**：在“设置”选择本地 HY-MT-2 GGUF 或 API 接口；使用 API 时先在“接口管理”添加并激活接口，
   从接口卡片菜单执行“测试接口”和“调整参数”。
2. **识别资源**：进入“整合包”，选择包含 `config`、`kubejs`、`mods` 的实例目录与实例外的任务目录，
   勾选识别范围后开始识别；识别不调用模型，可预览原文，也可与上一版本对比。
3. **翻译与校润**：识别完成后进入翻译阶段，可暂停续跑；校润阶段修改译文并保存为已审核。
4. **导出补丁**：导出独立 `patch/`，查看 `report.html` 后复制到游戏目录；新增和修改的文本会随补丁生效。

“术语库”“提示词”“翻译测试”“任务提取”可随时调整翻译配置，保存后下一次翻译生效。

## 环境变量

变量均在进程环境中读取，[.env.example](.env.example) 只是模板，应用不会自动加载：

| 变量 | 用途 |
| --- | --- |
| `MPLT_MODEL_PATH` | 默认 GGUF 模型路径 |
| `MPLT_RUNTIME_PYTHON` | 默认推理解释器路径 |
| `MPLT_GLOSSARY_PATH` | 默认术语库 JSON 路径 |
| `MPLT_DATA_DIR` | 任务根目录初始位置 |
| `MPLT_CACHE_DIR` | CFPA 元数据与下载缓存位置 |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` | 接口配置中可引用的密钥变量名示例 |

## 目录结构

```text
src/mcpacklocalizer/
  core/
    translation/        本地推理、API、术语检索与禁翻规则
    pack/               整合包扫描、检查点与补丁
    mods/               模组扫描、共享译库与 I18nUpdateMod
    formats/            SNBT、JSON5、NBT 与语言格式处理
    kubejs/             KubeJS 脚本与 JSON 文本发现
    patchouli/          帕秋莉手册发现与渲染
  application/
    tasks/              结构化任务、请求、后台服务与任务读取
    config/             设置及分页术语目录
  ui/
    view/api/           接口页、连接与参数弹窗、接口卡片
    view/tasks/         三阶段工作台、资源导航、校润页与条目表格
    view/translation/   翻译提示词、术语禁翻和翻译测试
    view/tools/         语言文件提取、回填与格式转换
    components/         通用表单组件
    process.py          后台进程与任务读取适配
tests/                  对应功能模块的分组测试
resources/              图标、术语库及常用词过滤表
requirements/           独立推理环境依赖
config/                 QFluentWidgets 界面配置
data/                   本仓库已有任务及历史数据（不入库）
models/                 本地 GGUF 模型（不入库）
.tmp/                   推理环境、占位符实验与源码备份（不入库）
main.py                 桌面启动入口
pyproject.toml / uv.lock 唯一的项目依赖配置
```

新任务默认保存至 `%LOCALAPPDATA%/MCPackLocalizer/tasks/`，可在设置里修改；
任务或补丁目录必须位于游戏实例之外。
用户使用说明见 [docs/RELEASING.md](docs/RELEASING.md)，构建与发布流程见
[docs/BUILDING.md](docs/BUILDING.md)。发布包附带内嵌截图的 `使用说明.html`，双击即可离线查看。

## 开发与测试

```powershell
$env:PYTHONPATH = 'src;.'
.venv/Scripts/python.exe -m pytest -v --tb=short -p no:cacheprovider tests/core tests/application tests/ui
.venv/Scripts/python.exe -m ruff check src tests main.py
```

核心库不依赖 Qt，可单独调用；桌面端通过后台进程执行结构化任务，界面与引擎解耦。
`requirements/inference.txt` 为独立推理环境依赖，主环境仅包含桌面与核心库依赖。

## 说明

- 请使用“暂停翻译”或正常退出中断任务，已提交条目会保留，下次可继续翻译。
- 为维护生态，建议不要直接发布未经人工校润的机翻。

## 致谢

- [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)——界面实现
- [AiNiee](https://github.com/NEKOparapa/AiNiee)——部分功能参考
- [HY-MT-2](https://huggingface.co/collections/tencent/hy-mt2)（腾讯混元）——本地与 API 翻译模型
- [llama-cpp-python](https://github.com/abetlen/llama-cpp-python)——本地 GGUF 推理
- [tree-sitter](https://github.com/tree-sitter/tree-sitter) 与 [tree-sitter-javascript](https://github.com/tree-sitter/tree-sitter-javascript)——KubeJS 脚本解析
- [i18n-dict](https://github.com/CFPATools/i18n-dict)——术语资源
- [中英术语库](https://github.com/VM-Chinese-translate-group/i18n-Dict-Extender)——i18n-Dict-Extender
- [CFPA 全体成员](https://cfpa.site/)——I18nUpdateMod

## 许可证

[GPL-3.0](LICENSE)
