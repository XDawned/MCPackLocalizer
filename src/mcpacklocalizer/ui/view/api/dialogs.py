"""Two-step creation, connection editing and separate model parameter dialogs."""
from dataclasses import replace
from uuid import uuid4

from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    DoubleSpinBox,
    FlowLayout,
    LineEdit,
    MessageBoxBase,
    PillPushButton,
    PushButton,
    ScrollArea,
    SpinBox,
    StrongBodyLabel,
    SubtitleLabel,
    TextEdit,
)

from ....core.translation.api import ApiProfile

# Connection defaults only; model availability remains service-controlled.
PLATFORM_PRESETS = (
    ("lm_studio", "LM Studio", "local", "openai", "http://127.0.0.1:1234/v1"),
    ("ollama", "Ollama", "local", "openai", "http://127.0.0.1:11434/v1"),
    ("llama_server", "llama-server", "local", "openai", "http://127.0.0.1:8080/v1"),
    ("openai", "OpenAI", "online", "openai", "https://api.openai.com/v1"),
    ("anthropic", "Anthropic", "online", "anthropic", "https://api.anthropic.com/v1"),
    ("gemini", "Gemini", "online", "gemini", "https://generativelanguage.googleapis.com/v1beta"),
    ("deepseek", "DeepSeek", "online", "openai", "https://api.deepseek.com/v1"),
    ("opencode", "OpenCode Zen", "online", "openai", "https://opencode.ai/zen/v1"),
    ("opencode_go", "OpenCode Go", "online", "openai", "https://opencode.ai/zen/go/v1"),
    ("custom", "自定义接口", "custom", "openai", ""),
)


def setting_row(box, title, description, control):
    card = CardWidget()
    row = QHBoxLayout(card)
    row.setContentsMargins(18, 14, 18, 14)
    row.setSpacing(24)
    labels = QVBoxLayout()
    labels.setSpacing(4)
    labels.addWidget(StrongBodyLabel(title, card))
    text = CaptionLabel(description, card)
    text.setWordWrap(True)
    labels.addWidget(text)
    row.addLayout(labels, 1)
    control.setMinimumWidth(260)
    row.addWidget(control, 1)
    box.addWidget(card)
    return card


class DialogBase(MessageBoxBase):
    def __init__(self, title, description, parent):
        super().__init__(parent)
        self.widget.setFixedSize(min(860, max(580, parent.width() - 100)), min(760, max(480, parent.height() - 80)))
        self.viewLayout.addWidget(SubtitleLabel(title, self.widget))
        summary = BodyLabel(description, self.widget)
        summary.setWordWrap(True)
        self.viewLayout.addWidget(summary)
        self.error = BodyLabel("", self.widget)
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #c43b34;")
        self.yesButton.setText("保存")
        self.cancelButton.setText("取消")
        self.profile = None

    def _create_scroller(self, content, parent):
        scroll = ScrollArea(parent)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(ScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setWidget(content)
        # QScrollArea.setWidget() enables a palette background, even in dark mode.
        content.setAutoFillBackground(False)
        return scroll

    def add_scroller(self, content):
        scroll = self._create_scroller(content, self.widget)
        self.viewLayout.addWidget(scroll, 1)
        self.viewLayout.addWidget(self.error)
        return scroll

    def accept_profile(self, profile):
        try:
            profile.validate()
        except ValueError as exc:
            self.error.setText(str(exc))
            return False
        self.profile = profile
        self.error.clear()
        return True


class ApiDetailsForm(QWidget):
    def __init__(self, profile, parent=None):
        super().__init__(parent)
        self.original = profile
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 8, 0, 8)
        box.setSpacing(10)
        self.platform_hint = CaptionLabel("", self)
        self.platform_hint.setWordWrap(True)
        self.platform_hint.hide()
        box.addWidget(self.platform_hint)
        self.name, self.url, self.model, self.key, self.key_env = (LineEdit(self) for _ in range(5))
        self.name.setText(profile.name)
        self.url.setText(profile.base_url)
        self.url.setPlaceholderText("服务地址 /v1 或完整请求地址")
        self.model.setText(profile.model)
        self.model.setPlaceholderText("填写服务支持的模型名称")
        self.key.setText(profile.api_key)
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("本地无鉴权服务可留空")
        self.key_env.setText(profile.key_env)
        self.key_env.setPlaceholderText("可选，例如 OPENAI_API_KEY")
        self.protocol = ComboBox(self)
        for label, value in (("OpenAI 兼容", "openai"), ("Anthropic", "anthropic"), ("Gemini", "gemini")):
            self.protocol.addItem(label, userData=value)
        self.protocol.setCurrentIndex(self.protocol.findData(profile.protocol))
        self.group = ComboBox(self)
        for label, value in (("按地址自动识别", "auto"), ("本地接口", "local"), ("官方接口", "online"), ("自定义接口", "custom")):
            self.group.addItem(label, userData=value)
        self.group.setCurrentIndex(self.group.findData(profile.group))
        for title, description, widget in (
            ("接口名称", "在接口列表中显示的名称", self.name),
            ("接口分组", "本地部署、官方服务或自定义服务", self.group),
            ("接口格式", "使用服务支持的请求协议", self.protocol),
            ("接口地址", "保留代理的版本路径；主机地址会补全默认路径", self.url),
            ("模型名称", "需与服务提供的模型标识一致", self.model),
            ("接口密钥", "遮蔽显示；直接输入的密钥保存在本机设置", self.key),
            ("密钥环境变量", "设置后优先读取进程环境，不必保存明文密钥", self.key_env),
        ):
            setting_row(box, title, description, widget)
        box.addStretch()

    def collect(self):
        return replace(self.original, name=self.name.text().strip(), base_url=self.url.text().strip(),
                       model=self.model.text().strip(), api_key=self.key.text().strip(), key_env=self.key_env.text().strip(),
                       protocol=self.protocol.currentData(), group=self.group.currentData())


class ApiEditDialog(DialogBase):
    def __init__(self, profile, parent):
        super().__init__("编辑接口 · " + profile.name, "修改连接信息；模型生成参数在“调整参数”中设置。", parent)
        self.details = ApiDetailsForm(profile, self.widget)
        self.add_scroller(self.details)

    def validate(self):
        return self.accept_profile(self.details.collect())


class AddApiDialog(DialogBase):
    def __init__(self, parent):
        super().__init__("添加接口", "选择平台，再填写模型、接口地址和密钥。", parent)
        self.selected_preset = None
        self.platform_buttons = {}
        self.steps = StrongBodyLabel("1 · 选择平台", self.widget)
        self.viewLayout.addWidget(self.steps)
        self.stack = QStackedWidget(self.widget)
        self.viewLayout.addWidget(self.stack, 1)
        self.viewLayout.addWidget(self.error)
        basic = QWidget(self.stack)
        basic_box = QVBoxLayout(basic)
        basic_box.setContentsMargins(0, 8, 0, 0)
        basic_box.addWidget(StrongBodyLabel("接口名称", basic))
        self.name = LineEdit(basic)
        self.name.setPlaceholderText("例如：我的远程接口")
        basic_box.addWidget(self.name)
        for group, title in (("local", "本地接口"), ("online", "官方接口"), ("custom", "自定义接口")):
            card = CardWidget(basic)
            box = QVBoxLayout(card)
            box.setContentsMargins(18, 14, 18, 18)
            box.addWidget(StrongBodyLabel(title, card))
            choices = QWidget(card)
            flow = FlowLayout(choices, needAni=False)
            flow.setContentsMargins(0, 4, 0, 0)
            flow.setHorizontalSpacing(10)
            flow.setVerticalSpacing(10)
            for preset in PLATFORM_PRESETS:
                if preset[2] != group:
                    continue
                button = PillPushButton(preset[1], choices)
                button.setCheckable(True)
                button.setFixedWidth(160)
                button.clicked.connect(lambda checked=False, key=preset[0]: self.select_platform(key))
                self.platform_buttons[preset[0]] = button
                flow.addWidget(button)
            box.addWidget(choices)
            basic_box.addWidget(card)
        basic_box.addStretch()
        self.platform_scroll = self._create_scroller(basic, self.stack)
        self.stack.addWidget(self.platform_scroll)
        self.details = ApiDetailsForm(ApiProfile(id=uuid4().hex), self.widget)
        scroll = self._create_scroller(self.details, self.stack)
        self.stack.addWidget(scroll)
        self.back = PushButton("上一步", self.buttonGroup)
        self.back.clicked.connect(self.previous_step)
        self.buttonLayout.insertWidget(0, self.back)
        self.back.hide()
        self.yesButton.setText("下一步")

    def select_platform(self, key):
        self.selected_preset = next(p for p in PLATFORM_PRESETS if p[0] == key)
        for name, button in self.platform_buttons.items():
            button.setChecked(name == key)
        hint = {
            "deepseek": "填写 DeepSeek 平台的模型名称和 API Key。",
            "opencode": "OpenCode Zen 按模型使用不同协议：默认 OpenAI 兼容，Claude 选择 Anthropic；暂不支持 Responses 协议。模型名无需 opencode/ 前缀。",
            "opencode_go": "OpenCode Go / Go Plus 使用套餐专用地址和 API Key，模型名无需 opencode-go/ 前缀。按模型选择 OpenAI 兼容或 Anthropic；暂不支持 Responses。官方 Go 面向编程代理，批量翻译适用性须向服务方确认。",
        }.get(key, "填写服务支持的模型名称")
        placeholder = {"opencode": "填写 Zen 模型 ID，无需 opencode/ 前缀",
                       "opencode_go": "填写 Go 模型 ID，无需 opencode-go/ 前缀"}
        self.details.model.setPlaceholderText(placeholder.get(key, "填写服务支持的模型名称"))
        self.details.model.setToolTip(hint)
        self.details.platform_hint.setText(hint)
        self.details.platform_hint.setVisible(key in {"deepseek", "opencode", "opencode_go"})
        if not self.name.text().strip() or self.name.text() in {p[1] for p in PLATFORM_PRESETS}:
            self.name.setText(self.selected_preset[1])
        self.error.clear()

    def previous_step(self):
        self.name.setText(self.details.name.text())
        self.stack.setCurrentIndex(0)
        self.steps.setText("1 · 选择平台")
        self.yesButton.setText("下一步")
        self.back.hide()
        self.error.clear()

    def validate(self):
        if self.stack.currentIndex() == 0:
            if not self.name.text().strip() or self.selected_preset is None:
                self.error.setText("请填写接口名称并选择一个平台")
                return False
            _, _, group, protocol, url = self.selected_preset
            # Preserve entered credentials/model when going back to the same platform.
            if getattr(self, "details_preset", None) != self.selected_preset[0]:
                self.details.url.setText(url)
                self.details.model.clear()
                self.details.key.clear()
                self.details.key_env.clear()
                self.details.protocol.setCurrentIndex(self.details.protocol.findData(protocol))
                self.details.group.setCurrentIndex(self.details.group.findData(group))
                self.details_preset = self.selected_preset[0]
            self.details.name.setText(self.name.text().strip())
            self.stack.setCurrentIndex(1)
            self.steps.setText("2 · 填写连接信息")
            self.yesButton.setText("添加接口")
            self.back.show()
            self.error.clear()
            return False
        return self.accept_profile(self.details.collect())


class ApiParametersDialog(DialogBase):
    def __init__(self, profile, parent):
        super().__init__("调整参数 · " + profile.name, "仅用于此接口；本地 GGUF 和其它 API 接口的参数分别保存。输出默认选项在应用设置中调整。", parent)
        self.original = profile
        content = QWidget(self.widget)
        box = QVBoxLayout(content)
        box.setContentsMargins(0, 8, 0, 8)
        box.setSpacing(10)
        self.prompt = ComboBox(content)
        self.prompt.addItems(["MC 翻译提示词（可编辑）", "HY-MT-2 固定模板"])
        self.prompt.setCurrentIndex(1 if profile.prompt_mode == "hy_mt" else 0)
        self.temperature = DoubleSpinBox(content)
        self.temperature.setRange(0, 1 if profile.protocol == "anthropic" else 2)
        self.temperature.setSingleStep(0.1)
        self.temperature.setValue(profile.temperature)
        self.send_temperature = CheckBox("发送温度参数", content)
        self.send_temperature.setChecked(profile.send_temperature)
        self.token_parameter = ComboBox(content)
        self.token_parameter.addItems(["max_tokens", "max_completion_tokens"])
        self.token_parameter.setCurrentText(profile.token_parameter)
        self.token_parameter.setEnabled(profile.protocol == "openai")
        for title, description, widget in (
            ("提示词模式", "HY-MT-2 模式使用固定模板，支持 OpenAI 兼容协议", self.prompt),
            ("采样温度", "较低值通常使输出更稳定", self.temperature),
            ("温度开关", "模型不支持温度参数时关闭", self.send_temperature),
            ("输出上限参数", "OpenAI 兼容服务的输出 token 参数名称", self.token_parameter),
        ):
            setting_row(box, title, description, widget)
        self.numbers = {}
        for key, title, description, low, high in (
            ("context_size", "上下文 token", "原文和提示词按 UTF-8 字节保守估计；原文不截断", 256, 131072),
            ("max_tokens", "输出 token 上限", "单次请求的输出上限，须小于上下文长度", 1, 32768),
            ("term_tokens", "术语 token 预算", "仅注入命中术语，按 UTF-8 字节保守估计；0 表示关闭注入", 0, 32768),
            ("timeout", "请求超时（秒）", "每次 HTTP 请求的等待时间", 1, 86400),
            ("concurrency", "并发请求数", "按此服务的承载能力或限流要求设置", 1, 32),
            ("retries", "网络 / 限流重试次数", "连接超时、限流和部分服务错误的有限重试", 0, 10),
        ):
            widget = SpinBox(content)
            widget.setRange(low, high)
            widget.setValue(getattr(profile, key))
            self.numbers[key] = widget
            setting_row(box, title, description, widget)
        self.interval = DoubleSpinBox(content)
        self.interval.setRange(0, 60)
        self.interval.setSingleStep(0.1)
        self.interval.setValue(profile.request_interval)
        setting_row(box, "请求最小间隔（秒）", "约束此接口的所有请求，包含重试", self.interval)
        extra = CardWidget(content)
        extra_box = QVBoxLayout(extra)
        extra_box.setContentsMargins(18, 14, 18, 18)
        extra_box.addWidget(StrongBodyLabel("扩展请求参数", extra))
        hint = CaptionLabel('JSON 对象，例如 {"enable_thinking": false}；按服务支持的参数填写。', extra)
        hint.setWordWrap(True)
        extra_box.addWidget(hint)
        self.extra = TextEdit(extra)
        self.extra.setMinimumHeight(120)
        self.extra.setPlainText(profile.extra_body)
        extra_box.addWidget(self.extra)
        box.addWidget(extra)
        box.addStretch()
        self.add_scroller(content)

    def validate(self):
        profile = replace(self.original, prompt_mode="hy_mt" if self.prompt.currentIndex() else "custom",
                          temperature=self.temperature.value(), send_temperature=self.send_temperature.isChecked(),
                          token_parameter=self.token_parameter.currentText(), extra_body=self.extra.toPlainText(),
                          request_interval=self.interval.value(), **{key: w.value() for key, w in self.numbers.items()})
        return self.accept_profile(profile)
