# [Module: desktop.settings_page] [Status: 已完成] [Brief: 分组设置卡片、主题色与关于信息]
from dataclasses import replace
from pathlib import Path

from PyQt6.QtCore import QSignalBlocker, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from qfluentwidgets import (
    FluentIcon as FIF,
)
from qfluentwidgets import (
    HyperlinkCard,
    MessageBox,
    PrimaryPushSettingCard,
    PushSettingCard,
    SettingCardGroup,
    SwitchSettingCard,
    Theme,
    TransparentToolButton,
    setTheme,
    setThemeColor,
)

from ... import __version__
from ...application.tasks.jobs import Job
from ...application.tasks.models import MODEL_VARIANTS
from ...core.translation.locales import LANGUAGES
from ..components.forms import ComboSettingCard, Page, PaletteSettingCard, PathSettingCard, SpinSettingCard

REPOSITORY = "https://github.com/XDawned/MCPackLocalizer"
THEMES = ["system", "light", "dark"]


class SettingsPage(Page):
    def __init__(self, window):
        super().__init__("settings", "设置", "翻译引擎、推理环境、术语与输出选项；修改后自动保存，下一次翻译使用新设置。", window)
        self.window = window
        self._loading = True
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(500)
        self.save_timer.timeout.connect(self.save)
        self.body.setSpacing(26)

        def group(title):
            widget = SettingCardGroup(title, self.content)
            self.body.addWidget(widget)
            return widget

        engine_group = group("翻译引擎")
        self.engine = ComboSettingCard(
            FIF.ROBOT, "翻译引擎", "本地和 API 均使用接口绑定的模板；在“接口管理”中添加和选择。", engine_group)
        self.engine.addItem("本地专用翻译 GGUF", "local")
        self.engine.addItem("API 接口（远程 / 本地服务）", "api")
        engine_group.addSettingCard(self.engine)

        language_group = group("翻译语言")
        self.source_language = ComboSettingCard(
            FIF.LANGUAGE, "原文语言", "新任务按所选语言识别；已有任务保留创建时的语言。", language_group)
        self.target_language = ComboSettingCard(
            FIF.LANGUAGE, "译文语言", "HY-MT-2 输出中文；Index-Translate 与大模型可选择其它语言。", language_group)
        for code, label, _ in LANGUAGES:
            for card in (self.source_language, self.target_language):
                card.addItem(f"{label} · {code}", code)
        language_group.addSettingCards([self.source_language, self.target_language])

        runtime_group = group("本地推理")
        self.model = PathSettingCard("选择文件", FIF.DOCUMENT, "专用翻译 GGUF 模型", mode="file",
                                     file_filter="GGUF 模型 (*.gguf)", placeholder="未选择模型文件", parent=runtime_group)
        self.runtime = PathSettingCard("选择解释器", FIF.DEVELOPER_TOOLS, "推理解释器",
                                       "留空自动使用内置运行时，也可选择外部 Python 3.12 解释器", mode="file",
                                       file_filter="解释器 (*.exe);;所有文件 (*)", placeholder="自动使用内置运行时",
                                       parent=runtime_group)
        self.runtime_auto = TransparentToolButton(FIF.SYNC, self.runtime)
        self.runtime_auto.setToolTip("恢复自动选择推理运行时")
        self.runtime_auto.clicked.connect(lambda: self.runtime.setPath(""))
        self.runtime.hBoxLayout.addWidget(self.runtime_auto)
        self.backend = ComboSettingCard(FIF.CONNECT, "推理后端", "auto 使用当前运行时可用的 GPU 后端，失败时尝试 CPU。",
                                        runtime_group)
        self.backend.addItems(["auto", "vulkan", "cuda", "cpu"])
        self.doctor = PushSettingCard("运行检查", FIF.DEVELOPER_TOOLS, "检查推理环境",
                                      "验证解释器、模型文件与推理后端是否可用。", runtime_group)
        self.doctor.clicked.connect(lambda: self.check(False))
        self.probe = PushSettingCard("加载并试译", FIF.PLAY, "模型试译",
                                     "加载模型并翻译一条示例文本，确认推理链路正常。", runtime_group)
        self.probe.clicked.connect(lambda: self.check(True))
        runtime_group.addSettingCards([self.model, self.runtime, self.backend, self.doctor, self.probe])

        tuning_group = group("本地 GGUF 推理参数")
        self.numbers = {}
        for key, icon, label, content, low, high in (
            ("threads", FIF.SPEED_HIGH, "CPU 线程数", "0 表示自动。", 0, 1024),
            ("gpu_layers", FIF.IOT, "GPU 层数", "-1 表示尽量卸载到 GPU。", -1, 999),
            ("context_size", FIF.TILES, "上下文 token", "单次请求的上下文长度。", 256, 131072),
            ("max_tokens", FIF.EDIT, "输出 token 上限", "必须小于上下文长度。", 1, 32768),
            ("term_tokens", FIF.DICTIONARY, "术语 token 预算", "注入术语表预留的 token。", 0, 32768),
            ("timeout", FIF.HISTORY, "本地推理超时（秒）", "单次推理的最长等待时间。", 1, 86400),
        ):
            card = SpinSettingCard(icon, label, content, low, high, tuning_group)
            self.numbers[key] = card
            tuning_group.addSettingCard(card)

        glossary_group = group("术语与格式")
        self.glossary_enabled = SwitchSettingCard(
            FIF.DICTIONARY, "开启术语注入", "翻译时向提示词注入术语表，保持专有名词一致。", parent=glossary_group)
        self.glossary = PathSettingCard("选择文件", FIF.DOCUMENT, "术语库 JSON", mode="file",
                                        file_filter="JSON (*.json)", placeholder="未选择术语库", parent=glossary_group)
        self.overrides = PathSettingCard("选择文件", FIF.DOCUMENT, "整合包术语覆盖",
                                         "可选；仅对当前整合包生效的补充术语。", mode="file",
                                         file_filter="JSON (*.json)", placeholder="未选择（可选）", parent=glossary_group)
        self.missing = SwitchSettingCard(
            FIF.CHECKBOX, "允许保留符缺失或换序", "校验失败时仍采用译文，并在质量列提醒。", parent=glossary_group)
        glossary_group.addSettingCards([self.glossary_enabled, self.glossary, self.overrides, self.missing])

        output_group = group("输出设置")
        self.partial = SwitchSettingCard(
            FIF.CERTIFICATE, "允许存在未处理项", "未完成项保留原文，其余照常输出。", parent=output_group)
        self.replace_locale = SwitchSettingCard(
            FIF.SYNC, "默认替换现有 FTBQ 目标语言文件", "关闭时仅生成独立补丁。", parent=output_group)
        self.include_i18n = SwitchSettingCard(
            FIF.ADD, "默认加入 I18nUpdateMod", "将 I18nUpdateMod 一并加入补丁。", parent=output_group)
        self.output_home = PathSettingCard("选择目录", FIF.FOLDER, "任务根目录", "新任务的默认保存位置。",
                                           mode="directory", placeholder="未选择目录", parent=output_group)
        output_group.addSettingCards([self.partial, self.replace_locale, self.include_i18n, self.output_home])

        appearance_group = group("外观")
        self.theme = ComboSettingCard(FIF.BRUSH, "应用主题", "切换浅色、深色或跟随系统。", appearance_group)
        self.theme.addItems(["跟随系统", "浅色", "深色"])
        self.theme.combo.currentIndexChanged.connect(self.preview_theme)
        self.theme_color = PaletteSettingCard(FIF.PALETTE, "主题色", "调整导航高亮、按钮与状态标签的强调色。",
                                              window.settings.theme_color, appearance_group)
        self.theme_color.colorChanged.connect(self.preview_color)
        appearance_group.addSettingCards([self.theme, self.theme_color])

        about_group = group("关于")
        repository = HyperlinkCard(REPOSITORY, "打开 GitHub", FIF.GITHUB, "项目主页",
                                   "MCPackLocalizer · 本地与 API 模型驱动的 Minecraft 整合包汉化工具。", about_group)
        feedback = HyperlinkCard(REPOSITORY + "/issues", "提交问题", FIF.FEEDBACK, "问题反馈",
                                 "报告缺陷、提出功能建议或查看已知问题。", about_group)
        self.about = PrimaryPushSettingCard("查看详情", FIF.INFO, "关于 MCPackLocalizer",
                                            f"版本 {__version__} · © XDawned · GPL-3.0", about_group)
        self.about.clicked.connect(self.show_about)
        about_group.addSettingCards([repository, feedback, self.about])

        self.body.addStretch(1)
        for card in (self.engine, self.source_language, self.target_language, self.backend, self.theme,
                     self.model, self.runtime, self.glossary, self.overrides, self.output_home, *self.numbers.values()):
            card.valueChanged.connect(self.schedule_save)
        for card in (self.glossary_enabled, self.missing, self.partial, self.replace_locale, self.include_i18n):
            card.checkedChanged.connect(self.schedule_save)
        self.theme_color.colorChanged.connect(self.schedule_save)
        self.restore(window.settings)

    def restore(self, settings):
        self._loading = True
        try:
            self.engine.setCurrentIndex(max(0, self.engine.findData(settings.engine)))
            for card, value in ((self.source_language, settings.source_locale), (self.target_language, settings.target_locale)):
                if card.findData(value) < 0:
                    card.addItem(value, value)
                card.setCurrentIndex(card.findData(value))
            self.model.setPath(settings.model)
            self.runtime.setPath(settings.runtime_python)
            self.backend.setCurrentText(settings.backend)
            self.glossary_enabled.setChecked(settings.glossary_enabled)
            self.glossary.setPath(settings.glossary)
            self.overrides.setPath(settings.overrides)
            self.missing.setChecked(settings.allow_missing_placeholders)
            for key, card in self.numbers.items():
                card.setValue(getattr(settings, key))
            self.partial.setChecked(settings.output_allow_partial)
            self.replace_locale.setChecked(settings.output_replace_locale)
            self.include_i18n.setChecked(settings.output_include_i18n)
            self.output_home.setPath(settings.output_home)
            self.theme.setCurrentIndex(THEMES.index(settings.theme))
            self.theme_color.setColor(settings.theme_color)
        finally:
            self.save_timer.stop()
            self._loading = False

    def collect(self):
        base = self.window.settings
        if self.model.text() != base.model:
            variant = next((key for key, spec in MODEL_VARIANTS.items() if Path(self.model.text()).name == spec.filename),
                           base.download_variant)
            base = base.select_local_model(self.model.text(), variant)
        settings = replace(base, model=self.model.text(), runtime_python=self.runtime.text(),
                           backend=self.backend.currentText(), glossary=self.glossary.text(),
                           overrides=self.overrides.text(), glossary_enabled=self.glossary_enabled.isChecked(),
                           allow_missing_placeholders=self.missing.isChecked(),
                           theme=THEMES[self.theme.currentIndex()], theme_color=self.theme_color.color(),
                           output_home=self.output_home.text(), engine=self.engine.currentData() or "local",
                           source_locale=self.source_language.currentData(), target_locale=self.target_language.currentData(),
                           output_allow_partial=self.partial.isChecked(),
                           output_replace_locale=self.replace_locale.isChecked(), output_include_i18n=self.include_i18n.isChecked(),
                           **{key: card.value() for key, card in self.numbers.items()})
        settings = settings.sync_local_parameters()
        settings.validate()
        return settings

    def save(self):
        try:
            self.window.save_settings(self.collect())
        except ValueError as exc:
            self.window.notify(str(exc), error=True)

    def schedule_save(self):
        if not self._loading:
            self.save_timer.start()

    def sync_engine(self, engine):
        blocker = QSignalBlocker(self.engine.combo)
        self.engine.setCurrentIndex(max(0, self.engine.findData(engine)))
        del blocker

    def preview_theme(self):
        setTheme([Theme.AUTO, Theme.LIGHT, Theme.DARK][self.theme.currentIndex()])

    def preview_color(self, color):
        setThemeColor(color)

    def show_about(self):
        dialog = MessageBox("关于 MCPackLocalizer",
                            f"MCPackLocalizer {__version__}\n\n"
                            "本地与 API 模型驱动的 Minecraft 整合包汉化工具。\n\n"
                            f"GitHub：{REPOSITORY}\n许可：GPL-3.0", self.window)
        dialog.yesButton.setText("打开 GitHub")
        dialog.cancelButton.setText("关闭")
        if dialog.exec():
            QDesktopServices.openUrl(QUrl(REPOSITORY))

    def check(self, probe):
        self.window.run_job(lambda: Job("doctor", probe=probe,
                                       **replace(self.collect(), engine="local").model_options()), "推理检查")

    def set_busy(self, busy):
        self.doctor.setEnabled(not busy)
        self.probe.setEnabled(not busy)
