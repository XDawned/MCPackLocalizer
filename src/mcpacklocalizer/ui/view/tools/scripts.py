# [Module: desktop.script_assistant] [Status: 已完成] [Brief: KubeJS 文本识别入口说明]
from qfluentwidgets import BodyLabel, PrimaryPushButton

from ...components.forms import Page


class ScriptAssistantPage(Page):
    def __init__(self, window):
        super().__init__("script-assistant", "KubeJS 脚本辅助", "已接入整合包翻译的识别、翻译与校润流程", window)
        box = self.section("脚本中的可翻译文本", "整合包翻译中选择“所有”或“kubejs”开始识别。")
        label = BodyLabel("本地识别脚本显示文本、JSON 文本及语言文件，不调用模型。\n"
                          "在翻译阶段单独选择 KubeJS 脚本大模型接口；变量与代码结构保持原样。\n"
                          "校润后导出独立补丁，无法确定的表达式保留原文并显示诊断。")
        label.setWordWrap(True)
        box.addWidget(label)
        button = PrimaryPushButton("进入整合包翻译")
        button.clicked.connect(lambda: window.switchTo(window.workspace))
        box.addWidget(button)
        self.body.addStretch()
