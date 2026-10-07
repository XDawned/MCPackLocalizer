# [Module: ui.api.local] [Status: 已完成] [Brief: 添加与编辑独立本地 GGUF 接口及推理参数]
from dataclasses import replace
from pathlib import Path

from PyQt6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, ComboBox, LineEdit, SpinBox

from ....application.config.interfaces import LOCAL_PARAMETERS
from ....application.tasks.models import MODEL_VARIANTS, model_spec
from ....core.translation.templates import detect_model_family
from ...components.forms import PathPicker
from .dialogs import DialogBase, setting_row


class LocalDetailsForm(QWidget):
    def __init__(self, profile, settings, parent=None):
        super().__init__(parent)
        self.original = profile
        self.updating = False
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 8, 0, 8)
        box.setSpacing(10)
        self.name = LineEdit(self)
        self.name.setText(profile.name)
        self.source = ComboBox(self)
        self.source.addItem("选择已有 GGUF", userData="existing")
        self.source.addItem("下载预设 GGUF", userData="preset")
        self.source.setCurrentIndex(0 if Path(profile.model).is_file() else 1)
        self.variant = ComboBox(self)
        for key, spec in MODEL_VARIANTS.items():
            self.variant.addItem(f"{spec.name} · Q4_K_M · 约 {spec.size / 1e9:.2f} GB", userData=key)
        self.variant.setCurrentIndex(self.variant.findData(profile.download_variant))
        self.model = PathPicker("选择模型文件或下载保存位置", "file", "GGUF 模型 (*.gguf)", self)
        self.model.setText(profile.model)
        self.template = ComboBox(self)
        for template in settings.templates().values():
            if template.interface_type == "translation":
                self.template.addItem(template.name, userData=template.id)
        self.template.setCurrentIndex(self.template.findData(profile.template_id))
        for title, description, widget in (
            ("接口名称", "独立保存，切换模板不会更改模型名称", self.name),
            ("模型来源", "使用已有文件，或下载经过大小与哈希校验的预设模型", self.source),
            ("模型预设", "HY-MT-2 与 Index-Translate 使用各自的默认模板", self.variant),
            ("GGUF 路径", "模型独立保存，已有文件不会被下载覆盖", self.model),
            ("翻译模板", "选择系统预设或已创建的专用翻译模板", self.template),
        ):
            setting_row(box, title, description, widget)
        hint = BodyLabel("本地接口默认并发 1；推理参数可在接口菜单中分别调整。", self)
        hint.setWordWrap(True)
        box.addWidget(hint)
        box.addStretch()
        self.source.currentIndexChanged.connect(self.change_source)
        self.variant.currentIndexChanged.connect(self.change_variant)
        self.model.textChanged.connect(self.recognize_model)
        self.model.mode = "file" if self.source.currentData() == "existing" else "save"
        self.update_variant_state()

    def update_variant_state(self):
        known = any(Path(self.model.text()).name.casefold() == spec.filename.casefold() for spec in MODEL_VARIANTS.values())
        self.variant.setEnabled(self.source.currentData() == "preset" or not known)

    def change_source(self):
        self.model.mode = "file" if self.source.currentData() == "existing" else "save"
        self.update_variant_state()
        if self.source.currentData() == "preset":
            self.change_variant()

    def change_variant(self):
        if self.updating:
            return
        spec = model_spec(self.variant.currentData())
        self.updating = True
        try:
            generated = {p.name + " · 本地 GGUF" for p in MODEL_VARIANTS.values()} | {"本地 GGUF", "本地模型"}
            if self.name.text() in generated:
                self.name.setText(spec.name + " · 本地 GGUF")
            self.template.setCurrentIndex(self.template.findData(spec.template_id))
            if self.source.currentData() == "preset":
                self.model.setText(str(spec.path))
        finally:
            self.updating = False

    def recognize_model(self):
        if self.updating or self.source.currentData() == "preset":
            return
        self.update_variant_state()
        variant = next((key for key, spec in MODEL_VARIANTS.items()
                        if Path(self.model.text()).name.casefold() == spec.filename.casefold()), None)
        if variant:
            self.updating = True
            self.variant.setCurrentIndex(self.variant.findData(variant))
            self.updating = False
            self.change_variant()

    def collect(self, require_file=False):
        model = self.model.text()
        if not model:
            raise ValueError("请选择模型文件或下载保存路径")
        if require_file and self.source.currentData() == "existing" and not Path(model).is_file():
            raise ValueError("请选择存在的 GGUF 模型文件")
        if Path(model).exists() and not Path(model).is_file():
            raise ValueError("GGUF 路径必须指向文件，不能是文件夹")
        variant = self.variant.currentData()
        family = model_spec(variant).template_id if self.source.currentData() == "preset" else detect_model_family(
            model, model_spec(variant).template_id)
        return replace(self.original, name=self.name.text().strip(), model=model,
                       download_variant=variant, template_id=self.template.currentData(), model_family=family,
                       download_enabled=self.source.currentData() == "preset" or
                       Path(model).name.casefold() == model_spec(variant).filename.casefold())


class LocalEditDialog(DialogBase):
    def __init__(self, profile, parent):
        super().__init__("编辑本地接口 · " + profile.name, "保存此模型的路径和模板；缺失的预设模型可在激活时下载。", parent)
        self.details = LocalDetailsForm(profile, parent.settings, self.widget)
        self.add_scroller(self.details)

    def validate(self):
        try:
            return self.accept_profile(self.details.collect())
        except ValueError as exc:
            self.error.setText(str(exc))
            return False


class LocalParametersDialog(DialogBase):
    def __init__(self, profile, parent):
        super().__init__("调整参数 · " + profile.name, "参数只用于此本地接口；其它模型和 API 接口分别保存。", parent)
        self.original = profile
        parameters = {key: getattr(parent.settings, key) for key in LOCAL_PARAMETERS} | profile.parameters
        content = QWidget(self.widget)
        box = QVBoxLayout(content)
        box.setContentsMargins(0, 8, 0, 8)
        self.runtime = PathPicker("留空自动选择运行时", "file", "Python 解释器 (*.exe)", content)
        self.runtime.setText(parameters["runtime_python"])
        setting_row(box, "推理解释器", "发布版留空使用内置解释器", self.runtime)
        self.backend = ComboBox(content)
        self.backend.addItems(["auto", "cpu", "vulkan", "cuda"])
        self.backend.setCurrentText(parameters["backend"])
        setting_row(box, "推理后端", "使用当前推理运行时支持的后端", self.backend)
        self.numbers = {}
        for key, title, low, high in (
            ("threads", "CPU 线程数", 0, 1024), ("gpu_layers", "GPU 层数", -1, 999),
            ("context_size", "上下文 token", 256, 131072), ("max_tokens", "输出 token 上限", 1, 32768),
            ("term_tokens", "术语 token 预算", 0, 32768), ("timeout", "响应超时（秒）", 1, 86400),
        ):
            control = SpinBox(content)
            control.setRange(low, high)
            control.setValue(parameters[key])
            self.numbers[key] = control
            setting_row(box, title, "独立保存到此接口", control)
        self.add_scroller(content)

    def validate(self):
        parameters = {key: control.value() for key, control in self.numbers.items()}
        parameters.update(runtime_python=self.runtime.text(), backend=self.backend.currentText())
        return self.accept_profile(replace(self.original, parameters=parameters))
