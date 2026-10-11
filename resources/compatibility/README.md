# 模组语言资源兼容规则

编辑同目录的 `mod_language_rules.json` 即可添加、修改或禁用适配规则，无需修改 Python 代码。

源码运行时读取仓库的 `resources/compatibility/`。Windows 发布包中，该目录位于
`MCPackLocalizer.exe` 旁，桌面与内置后台解释器优先读取这里的文件；文件缺失时使用包内预设。
通过 wheel 单独安装时，预设位于包内的 `mcpacklocalizer/resources/compatibility/`。
每次导出补丁都会重新读取规则，修改后重新导出即可生效；已经生成或安装的资源包需要重新复制。

## 配置格式

顶层 `schema_version` 固定为 `1`，`rules` 是规则数组。规则及其 `replacements`
均按数组顺序执行，后面的规则处理前面规则替换后的结果。

| 字段 | 含义 |
| --- | --- |
| `id` | 必填，规则的唯一标识，不能留空或重复；用于导出清单追踪 |
| `description` | 规则说明，显示在审核报告中；省略时使用 `id` |
| `enabled` | 是否启用，默认 `true`；设为 `false` 可禁用该规则 |
| `namespace` | 必填，模组资源代码域的正则表达式，如 `assets/projecte/` 中的 `projecte`，不等同于模组显示名称或 JAR 文件名 |
| `key` | 必填，语言 key 的正则表达式 |
| `language_format` | 可选，`lang` 仅适用于旧版 `.lang`，`json` 仅适用于现代 JSON，`any` 适用于全部格式；默认 `any` |
| `replacements` | 必填，非空正则替换数组，每项包含 `pattern` 和 `replacement` |
| `replacements[].count` | 可选，最多替换多少次；默认 `0` 表示替换全部匹配 |

`namespace` 和 `key` 均使用 Python 正则的**完整匹配**，匹配部分内容时应显式写 `.*`。
正则默认区分大小写，可使用 `(?i)` 等内联标志。
替换中的 `pattern` 搜索语言值内部的匹配，`replacement` 支持分组引用，如 `\1` 或 `\g<name>`。
JSON 字符串内的正则反斜杠需要双写；配置使用标准 JSON，不支持注释或尾随逗号。

例如，以下规则匹配 `example` 或 `example_addon` 的物品名称，删除开头的“旧称：”，
再把 `3x4` 这类尺寸改为 `3×4`：

```json
{
  "schema_version": 1,
  "rules": [
    {
      "id": "example-item-names",
      "description": "修正示例模组物品名称的前缀和尺寸符号",
      "namespace": "example(?:_addon)?",
      "key": "item\\.example\\..*\\.name",
      "replacements": [
        {"pattern": "^旧称：(.*)$", "replacement": "\\g<1>"},
        {"pattern": "([0-9]+)x([0-9]+)", "replacement": "\\1×\\2"}
      ]
    }
  ]
}
```

`rules: []` 可关闭所有适配。若只想关闭一项，把对应规则的 `enabled` 设为 `false`。
无效的 JSON、正则或替换分组会使导出停止，错误信息包含配置路径和规则位置。

适配仅作用于导出资源包的语言值，任务和共享译库中的译文保持原样。
适配结果继续遵守原有占位符校验和 `.lang` 禁止字面换行的要求。
导出的 `manifest.json` 中，`compatibility_adjustments` 记录实际修改的语言 key、规则 ID 和说明。

## 默认 ProjectE 规则

旧版 ProjectE 的 `ManualFontRenderer` 在普通空格处断行却不消费该空格。
若下一行在遇到其它空格前超宽，会返回断点 0，反复处理同一段文本，最终栈溢出。
默认规则只匹配旧版 ProjectE 的手册正文，将普通空格替换为不换行空格 `\u00a0`，
保留可见间距，让手册按字符宽度继续换行；标题、图片路径和命令不参与适配。
