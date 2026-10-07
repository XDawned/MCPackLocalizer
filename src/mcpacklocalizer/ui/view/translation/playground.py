# [Module: desktop.playground] [Status: 已完成] [Brief: 独立选择测试接口与模板的单条试译和质量提示]
from dataclasses import asdict, replace

from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWidgets import QApplication, QHBoxLayout
from qfluentwidgets import BodyLabel, ComboBox, LineEdit, PrimaryPushButton, PushButton, TextEdit

from ....application.tasks.jobs import Job
from ....application.tasks.requests import required
from ....core.translation.api import INDEX_PROFILE_ID, ApiProfile, index_profile
from ....core.translation.local import warning_text
from ....core.translation.locales import language_name
from ...components.forms import FormLayout, Page


class PlaygroundPage(Page):
    def __init__(self, window):
        super().__init__("playground", "翻译测试", "选择接口与模板，用同一段文本比较翻译效果。", window)
        self.window = window
        self.profiles = {}
        self.local_profiles = {}
        self.bound_template_id = ""
        self.custom_template = False
        self.result_selection = ""
        self.preview_records = []
        self.preview_actual = False
        options = self.section("测试配置", "选择接口会自动使用它绑定的模板；也可临时选择其它模板进行对比。")
        form = FormLayout()
        self.interface = ComboBox()
        self.interface.setMinimumWidth(300)
        self.template = ComboBox()
        self.template.setMinimumWidth(300)
        form.addRow("测试接口", self.interface)
        template_row = QHBoxLayout()
        template_row.addWidget(self.template, 1)
        edit = PushButton("编辑模板")
        edit.clicked.connect(lambda: window.prompts.edit_template(self.template.currentData()))
        template_row.addWidget(edit)
        form.addRow("翻译模板", template_row)
        options.addLayout(form)
        self.engine = BodyLabel("")
        self.engine.setWordWrap(True)
        options.addWidget(self.engine)
        self.selection_hint = BodyLabel("")
        self.selection_hint.setWordWrap(True)
        options.addWidget(self.selection_hint)
        source = self.section("原文")
        self.source = TextEdit()
        self.source.setPlaceholderText("输入待翻译文本；可包含 &6、§b、%s 等格式标识")
        self.source.setMinimumHeight(160)
        source.addWidget(self.source)
        self.context = LineEdit()
        self.context.setPlaceholderText("可选背景，例如：暮色森林任务章节")
        source.addWidget(self.context)
        row = QHBoxLayout()
        self.translate = PrimaryPushButton("开始试译")
        self.translate.clicked.connect(self.start)
        self.stop = PushButton("暂停")
        self.stop.clicked.connect(window.runner.cancel)
        row.addWidget(self.translate)
        self.preview_button = PushButton("预览提示词")
        self.preview_button.clicked.connect(self.start_preview)
        row.addWidget(self.preview_button)
        row.addWidget(self.stop)
        row.addStretch()
        source.addLayout(row)
        preview = self.section("拼接后的提示词", "展示已替换原文、语言、术语和背景的消息内容。预览不发起翻译请求；本地预览需加载模型。")
        preview_actions = QHBoxLayout()
        self.preview_attempt = ComboBox()
        self.preview_attempt.setMinimumWidth(280)
        preview_actions.addWidget(self.preview_attempt, 1)
        copy = PushButton("复制提示词")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.prompt_preview.toPlainText()))
        preview_actions.addWidget(copy)
        preview.addLayout(preview_actions)
        self.prompt_preview = TextEdit()
        self.prompt_preview.setReadOnly(True)
        self.prompt_preview.setMinimumHeight(220)
        self.prompt_preview.setPlaceholderText("点击“预览提示词”，或开始试译后查看本次实际使用的提示词。")
        preview.addWidget(self.prompt_preview)
        self.preview_hint = BodyLabel("尚未生成提示词预览")
        self.preview_hint.setWordWrap(True)
        preview.addWidget(self.preview_hint)
        translated = self.section("译文")
        self.translation = TextEdit()
        self.translation.setReadOnly(True)
        self.translation.setMinimumHeight(160)
        self.hints = BodyLabel("试译使用所选接口的参数和当前术语、禁翻设置。")
        self.hints.setWordWrap(True)
        translated.addWidget(self.translation)
        translated.addWidget(self.hints)
        self.body.addStretch()
        self.interface.currentIndexChanged.connect(self.select_interface)
        self.template.currentIndexChanged.connect(self.select_template)
        self.preview_attempt.currentIndexChanged.connect(self.render_preview)
        self.source.textChanged.connect(self.invalidate_preview)
        self.context.textChanged.connect(self.invalidate_preview)
        self.refresh()

    def refresh(self):
        settings = self.window.settings
        previous_interface, previous_template = self.interface.currentData(), self.template.currentData()
        self.profiles = {p["id"]: ApiProfile(**p) for p in settings.api_profiles}
        self.profiles.setdefault(INDEX_PROFILE_ID, index_profile())
        self.local_profiles = {p.id: p for p in settings.local_interfaces()}
        blocker = QSignalBlocker(self.interface)
        self.interface.clear()
        for profile in self.local_profiles.values():
            self.interface.addItem(profile.name, userData=profile.id)
        for profile in self.profiles.values():
            self.interface.addItem(f"{profile.name} · {profile.model or '未填写模型'}", userData=profile.id)
        current = settings.current_local_profile()
        preferred = previous_interface or (settings.active_api if settings.engine == "api" else current.id if current else "")
        self.interface.setCurrentIndex(max(0, self.interface.findData(preferred)))
        del blocker
        retained = previous_interface == self.interface.currentData() and self.custom_template
        self.select_interface(previous_template if retained else None)
        self.set_busy(self.window.runner.busy)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def select_interface(self, preferred_template=None):
        # Qt 的索引信号传入整数；只有刷新时才传递需要保留的模板标识。
        if not isinstance(preferred_template, str):
            preferred_template = None
        settings = self.window.settings
        interface_id = self.interface.currentData()
        profile = self.local_profiles.get(interface_id) or self.profiles.get(interface_id)
        self.bound_template_id = profile.template_id if profile else settings.local_template_id
        blocker = QSignalBlocker(self.template)
        self.template.clear()
        for template in settings.templates().values():
            kind = "专用翻译" if template.interface_type == "translation" else "大模型"
            self.template.addItem(f"{template.name} · {kind}", userData=template.id)
        chosen = preferred_template if preferred_template in settings.templates() else self.bound_template_id
        self.template.setCurrentIndex(max(0, self.template.findData(chosen)))
        del blocker
        name = profile.name if interface_id in self.local_profiles else f"{profile.name} · {profile.model or '未填写模型'}"
        self.engine.setText("测试接口：" + name)
        self.select_template()

    def select_template(self):
        self.custom_template = self.template.currentData() != self.bound_template_id
        mode = "临时替换模板" if self.custom_template else "使用接口配套模板"
        settings = self.window.settings
        self.selection_hint.setText(f"{mode} · {language_name(settings.source_locale)} → {language_name(settings.target_locale)}")
        self.invalidate_preview()

    def test_options(self, resolve_credentials=True):
        settings = self.window.settings
        interface_id = self.interface.currentData()
        if interface_id in self.local_profiles:
            selected = settings.use_local_profile(interface_id)
        else:
            profile = self.profiles.get(interface_id)
            if profile is None:
                raise ValueError("测试接口不存在，请重新选择")
            profiles = list(settings.api_profiles)
            if not any(p["id"] == profile.id for p in profiles):
                profiles.append(asdict(profile))
            selected = replace(settings, engine="api", active_api=profile.id, api_profiles=profiles)
            if not resolve_credentials:
                selected = replace(selected, api_profiles=[
                    {**p, "api_key": "", "key_env": ""} if p["id"] == profile.id else p for p in profiles])
        options = selected.model_options()
        template = settings.templates().get(self.template.currentData())
        if template is None:
            raise ValueError("测试模板不存在，请重新选择")
        # 临时模板只覆盖提示词快照，模型的采样和关闭思考行为继续沿用所选接口。
        options.update(system_prompt=template.system, prompt_user=template.user,
                       prompt_family=template.family, prompt_template_id=template.id)
        return options

    def start(self):
        def arguments():
            text = required(self.source.toPlainText(), "待翻译原文")
            arguments = Job("translate", text=text, context=self.context.text(), capture_prompts=True, **self.test_options())
            template = self.window.settings.templates()[self.template.currentData()]
            self.result_selection = f"{self.interface.currentText()} · 模板：{template.name}"
            self.translation.clear()
            self.hints.setText(self.result_selection + "\n正在试译…")
            self.invalidate_preview()
            return arguments
        self.window.run_job(arguments, "单条翻译")

    def start_preview(self):
        def arguments():
            text = required(self.source.toPlainText(), "待翻译原文")
            arguments = Job("preview-prompt", text=text, context=self.context.text(),
                            **self.test_options(resolve_credentials=False))
            self.preview_hint.setText("正在拼接提示词…")
            return arguments
        self.window.run_job(arguments, "提示词预览")

    def invalidate_preview(self):
        self.preview_records = []
        blocker = QSignalBlocker(self.preview_attempt)
        self.preview_attempt.clear()
        del blocker
        self.prompt_preview.clear()
        self.preview_hint.setText("原文或配置已更新，点击“预览提示词”查看最新内容。")

    def show_preview(self, result, cancelled=False, actual=False):
        self.preview_records = result.get("prompt_preview", [])
        self.preview_actual = actual
        blocker = QSignalBlocker(self.preview_attempt)
        self.preview_attempt.clear()
        for record in self.preview_records:
            self.preview_attempt.addItem("首轮直译" if record["attempt"] == 1 else "掩码重试（首轮校验失败时使用）")
        self.preview_attempt.setCurrentIndex(0)
        del blocker
        if self.preview_records:
            self.render_preview()
            if not actual:
                self.ensureWidgetVisible(self.prompt_preview)
        else:
            self.prompt_preview.clear()
            skipped = result.get("translation_skipped") or actual
            if cancelled:
                hint = "预览已暂停"
            elif result.get("error"):
                hint = result["error"]
            else:
                hint = "此原文无需向模型发送提示词。" if skipped else "未能生成提示词预览。"
            self.preview_hint.setText(hint)

    def render_preview(self):
        index = self.preview_attempt.currentIndex()
        if not 0 <= index < len(self.preview_records):
            return
        record = self.preview_records[index]
        self.prompt_preview.setPlainText("\n\n".join(
            ("【系统消息】\n" if message["role"] == "system" else "【用户消息】\n") + message["content"]
            for message in record["messages"]))
        terms = record.get("terms", [])
        selected = "、".join(f"{term['source']} → {term['translation']}" for term in terms)
        status = "本次实际请求" if self.preview_actual else "拼接预览"
        if record.get("within_budget") is False:
            status += " · 超过当前上下文预算"
        self.preview_hint.setText(f"{status} · 预算内术语 {len(terms)} 项" + ("：" + selected if selected else ""))

    def show_result(self, result, cancelled=False):
        if "prompt_preview" in result:
            self.show_preview(result, actual=True)
        if cancelled:
            self.hints.setText("试译已暂停")
        elif "translation" in result:
            self.translation.setPlainText(result["translation"])
            self.hints.setText("\n".join(warning_text(h) for h in result.get("quality_warnings", [])) or "格式校验通过")
            if usage := result.get("api_usage"):
                self.hints.setText(self.hints.text() + f"\nAPI 请求 {usage['requests']} · 输入 {usage['input_tokens']} / 输出 {usage['output_tokens']} token")
        elif "error" in result:
            self.translation.clear()
            self.hints.setText(result["error"])
        else:
            self.hints.setText("接口未返回译文")
        if self.result_selection:
            self.hints.setText(self.result_selection + "\n" + self.hints.text())
        self.ensureWidgetVisible(self.translation)

    def set_busy(self, busy):
        self.translate.setEnabled(not busy)
        self.interface.setEnabled(not busy)
        self.template.setEnabled(not busy)
        self.preview_button.setEnabled(not busy)
        self.source.setEnabled(not busy)
        self.context.setEnabled(not busy)
        self.stop.setEnabled(busy)
