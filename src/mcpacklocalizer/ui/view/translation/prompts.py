# [Module: ui.translation.prompts] [Status: 已完成] [Brief: MC 系统提示词编辑与固定 HY-MT-2 模板展示]
from dataclasses import replace

from qfluentwidgets import PrimaryPushButton, PushButton, TextEdit

from ....core.translation.local import DEFAULT_SYSTEM_PROMPT, render_prompt
from ...components.forms import Page


class PromptsPage(Page):
    def __init__(self, window):
        super().__init__("prompts", "翻译提示词", "面向 MC 的任务、物品、方块、界面和模组说明，不引入角色介绍或人物提取。", window)
        api = self.section("系统提示词",
                           "仅用于 API 的“MC 翻译提示词”模式；请求自动附加译文标签要求，标签外的说明不会写入译文。\n"
                           "兼容完整代码围栏、译文 JSON 与纯译文；本地和 API 的 HY-MT2 模式使用固定模板。\n"
                           "- {source_language} 原文语言 \n"
                           "- {target_language} 译文语言\n"
                           "- {context} 背景信息\n"
                           "- {glossary} 原文匹配的术语表")
        self.prompt = TextEdit()
        self.prompt.setMinimumHeight(240)
        self.prompt.setPlainText(window.settings.system_prompt)
        api.addWidget(self.prompt)
        save = PrimaryPushButton("保存提示词")
        save.clicked.connect(lambda: window.save_settings(replace(window.settings, system_prompt=self.prompt.toPlainText())))
        reset = PushButton("载入 MC 默认提示词")
        reset.clicked.connect(lambda: self.prompt.setPlainText(DEFAULT_SYSTEM_PROMPT))
        api.addWidget(save)
        api.addWidget(reset)
        local = self.section("HY-MT-2 固定模板", "本地 GGUF 和 API 的 HY-MT-2 模式仅支持简体中文输出，术语和背景按需注入。"
                             "此模板不可编辑；翻译成其它语言请使用 API 的“MC 翻译提示词”模式。")
        template = TextEdit()
        template.setReadOnly(True)
        template.setPlainText(render_prompt("<待翻译文本>", [("<匹配术语>", "<中文译名>")], "<可选背景>"))
        template.setMinimumHeight(200)
        local.addWidget(template)
        self.body.addStretch()
