# [Module: desktop.playground] [Status: 已完成] [Brief: 单条本地翻译与质量提示查看]
from PyQt6.QtWidgets import QHBoxLayout
from qfluentwidgets import BodyLabel, LineEdit, PrimaryPushButton, PushButton, TextEdit

from mcpacklocalizer.core.translation.local import warning_text

from ....application.tasks.jobs import Job
from ....application.tasks.requests import required
from ...components.forms import Page


class PlaygroundPage(Page):
    def __init__(self, window):
        super().__init__("playground", "翻译测试", "用一段任务文本检查当前模型、提示词、术语、禁翻与颜色代码效果。", window)
        self.window = window
        source = self.section("原文")
        self.engine = BodyLabel("当前翻译引擎：" + window.settings.engine_label())
        self.engine.setWordWrap(True)
        source.addWidget(self.engine)
        self.source = TextEdit()
        self.source.setPlaceholderText("在这里输入英文；可包含 &6、§b、%s 等格式标识")
        self.source.setMinimumHeight(180)
        source.addWidget(self.source)
        self.context = LineEdit()
        self.context.setPlaceholderText("可选背景，例如：暮色森林任务章节")
        source.addWidget(self.context)
        row = QHBoxLayout()
        self.translate = PrimaryPushButton("使用当前模型翻译")
        self.translate.clicked.connect(self.start)
        stop = PushButton("暂停")
        stop.clicked.connect(window.runner.cancel)
        row.addWidget(self.translate)
        row.addWidget(stop)
        row.addStretch()
        source.addLayout(row)
        translated = self.section("译文")
        self.translation = TextEdit()
        self.translation.setReadOnly(True)
        self.translation.setMinimumHeight(180)
        self.hints = BodyLabel("使用已保存的模型设置")
        self.hints.setWordWrap(True)
        translated.addWidget(self.translation)
        translated.addWidget(self.hints)
        self.body.addStretch()

    def start(self):
        def arguments():
            text = required(self.source.toPlainText(), "待翻译原文")
            return Job("translate", text=text, context=self.context.text(),
                       **self.window.settings.model_options())
        self.window.run_job(arguments, "单条翻译")

    def show_result(self, result):
        if "translation" in result:
            self.translation.setPlainText(result["translation"])
            self.hints.setText("\n".join(warning_text(h) for h in result.get("quality_warnings", [])) or "格式校验通过")
            if usage := result.get("api_usage"):
                self.hints.setText(self.hints.text() + f"\nAPI 请求 {usage['requests']} · 输入 {usage['input_tokens']} / 输出 {usage['output_tokens']} token")
        elif "error" in result:
            self.hints.setText(result["error"])

    def set_busy(self, busy):
        self.translate.setEnabled(not busy)
