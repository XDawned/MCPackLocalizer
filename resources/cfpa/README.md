# CFPA 离线资源

这里保存 GitHub 动态文件的离线快照，包括 I18nUpdateMod3 版本映射、CFPA 发布索引，以及映射所需的 Forge / Fabric 汉化 ZIP 和 MD5 文件。仓库只保留小体积元数据、索引、说明与许可证；`releases/` 和 `manifest.json` 由 `.gitignore` 排除，在打包时动态获取。发布包包含完整快照，首次使用且没有用户缓存时也能回退。

正常运行优先获取线上内容，并把成功下载且校验通过的文件保存到用户缓存。线上请求超时、连接失败或返回 HTTP 错误时，先读取用户缓存，再读取此目录。手动离线模式直接采用相同顺序，不发起网络请求。损坏的本地文件会跳过；线上校验失败仍报错，不会掩盖错误内容。

ZIP 与 MD5 始终作为同一份快照校验，不能把最新线上 MD5 与旧离线 ZIP 混用。发布目录按标签的 SHA256 前 16 位区分。索引指向的发布没有离线副本时，可回退到内置 `autobuild`，实际标签与回退原因会记入扫描报告。

正式构建执行 `uv run python scripts/build_release.py desktop` 时会自动下载、校验，再将同一份快照装入桌面 EXE 与运行时 wheel。获取失败会阻止打包，三个后端组装复用公共构建的文件；发布时核对资源完整性与批次。

源码开发需要离线资源或单独构建 wheel 时，使用 Python 3.12 在仓库根目录预先下载：

```powershell
uv run python scripts/update_cfpa_resources.py
```

脚本下载 `autobuild` 和索引所指发布的全部映射资源，完成 MD5 与 ZIP 完整性校验后写入。`manifest.json` 记录每个文件的原始 URL、大小、SHA256 和更新时间。下载内容无需提交 Git。未预先下载的源码环境只具有离线元数据映射；完整资源包离线回退由发布构建保证。软件运行期间只读取内置目录，线上更新写入用户缓存，不修改安装资源。

上游来源：[I18nUpdateMod3](https://github.com/CFPAOrg/I18nUpdateMod3)、[Minecraft-Mod-Language-Package](https://github.com/CFPAOrg/Minecraft-Mod-Language-Package)。上游内容的许可证见本目录的对应许可文件。
