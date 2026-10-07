# [Module: ui.translation.prompts] [Status: 已完成] [Brief: 专用翻译与大模型模板的编辑、复制、预览和接口绑定]
from dataclasses import replace
from uuid import uuid4

from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWidgets import QHBoxLayout, QStackedWidget
from qfluentwidgets import BodyLabel, ComboBox, LineEdit, PrimaryPushButton, PushButton, SegmentedWidget, TextEdit

from ....core.translation.templates import BUILTIN_TEMPLATES, PromptTemplate, render_template
from ...components.forms import FormLayout, Page


class PromptsPage(Page):
    def __init__(self, window):
        super().__init__("prompts", "提示词模板", "为专用翻译模型或大模型维护完整模板；修改后用于下一次翻译。", window)
        self.window = window
        selection = self.section("模板管理")
        row = QHBoxLayout()
        self.templates = ComboBox()
        self.templates.setMinimumWidth(320)
        row.addWidget(self.templates, 1)
        for label, callback in (("新建", self.create), ("复制", self.duplicate), ("删除", self.remove),
                                ("恢复系统预设", self.reset)):
            button = PushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        selection.addLayout(row)
        form = FormLayout()
        self.name = LineEdit()
        self.kind = ComboBox()
        self.kind.addItem("专用翻译模型", userData="translation")
        self.kind.addItem("大模型", userData="llm")
        self.family = ComboBox()
        for label, value in (("MC 大模型", "mc"), ("HY-MT-2（中文输出）", "hy_mt"),
                             ("Index-Translate", "index"), ("通用翻译", "generic")):
            self.family.addItem(label, userData=value)
        form.addRow("模板名称", self.name)
        form.addRow("接口类型", self.kind)
        form.addRow("模型格式", self.family)
        selection.addLayout(form)
        self.references = BodyLabel("")
        self.references.setWordWrap(True)
        selection.addWidget(self.references)
        editor = self.section("完整提示词",
                              "{text} 待翻译文本 · {source_language} 原文语言 · {target_language} 译文语言\n"
                              "{source_locale} / {target_locale} 语言代码 · {glossary} 命中术语 · {context} 背景\n"
                              "{preservation_rules} 掩码重试保留规则 · {output_tag} 安全译文标签\n"
                              "[[可选段落]] 内的占位符为空时，整段省略。其它花括号原样保留，插入的数据不会二次替换。")
        self.editor_tabs = SegmentedWidget()
        self.editor_stack = QStackedWidget()
        self.prompt = TextEdit()
        self.user_prompt = TextEdit()
        self.editor_stack.addWidget(self.user_prompt)
        self.editor_stack.addWidget(self.prompt)
        self.editor_stack.setMinimumHeight(280)
        self.editor_tabs.addItem(routeKey="user", text="用户提示词 · 待翻译文本", onClick=lambda: self.editor_stack.setCurrentIndex(0))
        self.editor_tabs.addItem(routeKey="system", text="系统提示词 · 可留空", onClick=lambda: self.editor_stack.setCurrentIndex(1))
        self.editor_tabs.setCurrentItem("user")
        editor.addWidget(self.editor_tabs)
        editor.addWidget(self.editor_stack)
        save = PrimaryPushButton("保存模板")
        save.clicked.connect(self.save)
        editor.addWidget(save)
        preview = self.section("请求预览", "使用 Iron Ingot、匹配术语和示例背景预览实际发送的内容。")
        self.preview = TextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(180)
        preview.addWidget(self.preview)
        self.templates.currentIndexChanged.connect(self.load)
        for widget in (self.prompt, self.user_prompt):
            widget.textChanged.connect(self.update_preview)
        self.family.currentIndexChanged.connect(self.update_preview)
        self.body.addStretch()
        self.refresh("mc")

    def refresh(self, selected=None):
        selected = selected or self.templates.currentData() or "mc"
        blocker = QSignalBlocker(self.templates)
        self.templates.clear()
        for template in self.window.settings.templates().values():
            suffix = " · 系统预设" if template.id in BUILTIN_TEMPLATES else ""
            self.templates.addItem(template.name + suffix, userData=template.id)
        self.templates.setCurrentIndex(max(0, self.templates.findData(selected)))
        del blocker
        self.load()

    def showEvent(self, event):
        super().showEvent(event)
        if set(self.window.settings.templates()) != {self.templates.itemData(i) for i in range(self.templates.count())}:
            self.refresh()

    def edit_template(self, template_id):
        self.refresh(template_id)
        self.window.switchTo(self)

    def load(self):
        template = self.window.settings.templates().get(self.templates.currentData())
        if template is None:
            return
        self.name.setText(template.name)
        self.kind.setCurrentIndex(self.kind.findData(template.interface_type))
        self.family.setCurrentIndex(self.family.findData(template.family))
        builtin = template.id in BUILTIN_TEMPLATES
        self.kind.setEnabled(not builtin)
        self.family.setEnabled(not builtin)
        self.prompt.setPlainText(template.system)
        self.user_prompt.setPlainText(template.user)
        self.editor_tabs.setCurrentItem("user")
        self.editor_stack.setCurrentIndex(0)
        settings = self.window.settings
        names = [p["name"] for p in settings.api_profiles if p.get("template_id") == template.id]
        names = [p.name for p in settings.local_interfaces() if p.template_id == template.id] + names
        self.references.setText("已绑定：" + "、".join(names) if names else "尚未绑定接口；保存后可在添加或编辑接口时选择。")
        self.update_preview()

    def collect(self):
        return PromptTemplate(self.templates.currentData() or "preview", self.name.text().strip(),
                              self.kind.currentData(), self.family.currentData(),
                              self.prompt.toPlainText(), self.user_prompt.toPlainText())

    def update_preview(self):
        try:
            user, system = render_template(self.collect(), "Iron Ingot", self.window.settings.source_locale,
                                           self.window.settings.target_locale, [("Iron Ingot", "铁锭")], "Minecraft 物品名称")
            self.preview.setPlainText(("系统：\n" + system + "\n\n" if system else "") + "用户：\n" + user)
        except ValueError as exc:
            self.preview.setPlainText(str(exc))

    def save(self):
        try:
            template = self.collect()
            self.window.save_settings(self.window.settings.store_template(template))
            self.refresh(template.id)
        except ValueError as exc:
            self.window.notify(str(exc), error=True)

    def create(self):
        template = replace(BUILTIN_TEMPLATES["translation" if self.kind.currentData() == "translation" else "mc"],
                           id=uuid4().hex, name="新模板")
        self.window.save_settings(self.window.settings.store_template(template))
        self.refresh(template.id)

    def duplicate(self):
        try:
            template = replace(self.collect(), id=uuid4().hex, name=self.name.text().strip() + " 副本")
            self.window.save_settings(self.window.settings.store_template(template))
            self.refresh(template.id)
        except ValueError as exc:
            self.window.notify(str(exc), error=True)

    def remove(self):
        template_id = self.templates.currentData()
        if template_id in BUILTIN_TEMPLATES:
            self.window.notify("系统预设请使用恢复功能；用户模板可以删除", warning=True)
            return
        settings = self.window.settings
        if (settings.local_template_id == template_id or template_id in settings.local_model_templates.values() or
                any(p.template_id == template_id for p in settings.local_interfaces()) or
                any(p.get("template_id") == template_id for p in settings.api_profiles)):
            self.window.notify("此模板仍绑定接口，请先为接口选择其它模板", warning=True)
            return
        self.window.save_settings(replace(settings, prompt_templates=[p for p in settings.prompt_templates if p["id"] != template_id]))
        self.refresh("mc")

    def reset(self):
        template_id = self.templates.currentData()
        if template_id not in BUILTIN_TEMPLATES:
            self.window.notify("当前是用户模板；请选择系统预设后恢复", warning=True)
            return
        self.window.save_settings(self.window.settings.store_template(BUILTIN_TEMPLATES[template_id]))
        self.refresh(template_id)
