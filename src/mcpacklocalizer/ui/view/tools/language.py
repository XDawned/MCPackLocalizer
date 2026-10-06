# [Module: desktop.language_tools] [Status: 已完成] [Brief: 离线语言提取、回填及格式转换界面]
from qfluentwidgets import CheckBox, ComboBox, PrimaryPushButton

from ....application.tasks.requests import PatchOptions, language_job
from ...components.forms import FormLayout, Page, PathPicker


class LanguageToolsPage(Page):
    def __init__(self, window):
        super().__init__("language-tools", "任务提取工具", "无需加载模型即可导出语言文件、离线回填或转换格式。", window)
        self.window = window
        box = self.section("语言文件交换", "提取文件与 mapping.json 配套保存；回填使用新的补丁目录。")
        self.action = ComboBox()
        self.action.addItems(["提取待翻译语言文件", "回填已翻译语言文件", "转换语言文件格式"])
        self.root = PathPicker("游戏实例目录 / 提取目录 / 源语言文件")
        self.output = PathPicker("独立输出目录或转换后的文件路径")
        self.language = PathPicker("已翻译语言文件", "file", "语言文件 (*.json *.json5 *.snbt *.lang)")
        self.fmt = ComboBox()
        self.fmt.addItems(["json", "json5", "snbt", "lang"])
        self.partial = CheckBox("回填时允许缺少部分译文")
        self.replace = CheckBox("回填时允许替换已有 FTBQ 目标语言文件")
        form = FormLayout()
        for label, widget in (("操作", self.action), ("输入", self.root), ("输出", self.output),
                              ("译文文件", self.language), ("输出格式", self.fmt)):
            form.addRow(label, widget)
        box.addLayout(form)
        box.addWidget(self.partial)
        box.addWidget(self.replace)
        self.run = PrimaryPushButton("执行")
        self.run.clicked.connect(self.start)
        box.addWidget(self.run)
        self.action.currentIndexChanged.connect(self.update_action)
        self.update_action()
        self.body.addStretch()

    def update_action(self):
        index = self.action.currentIndex()
        self.root.mode = "file" if index == 2 else "directory"
        self.root.file_filter = "语言文件 (*.json *.json5 *.snbt *.lang)"
        self.output.mode = "save" if index == 2 else "directory"
        self.language.setEnabled(index == 1)
        self.fmt.setEnabled(index != 1)
        self.partial.setEnabled(index == 1)
        self.replace.setEnabled(index == 1)

    def start(self):
        action = ["extract-lang", "backfill", "convert-lang"][self.action.currentIndex()]
        patch = PatchOptions(self.partial.isChecked(), self.replace.isChecked())
        self.window.run_job(lambda: language_job(action, self.root.text(), self.output.text(),
                                                     self.language.text(), self.fmt.currentText(), patch,
                                                     source_locale=self.window.settings.source_locale,
                                                     target_locale=self.window.settings.target_locale),
                            self.action.currentText())

    def set_busy(self, busy):
        self.run.setEnabled(not busy)
