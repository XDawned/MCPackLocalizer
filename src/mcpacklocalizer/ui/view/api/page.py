# [Module: desktop.api_page] [Status: 已完成] [Brief: 接口激活、首次配置引导与本地模型下载]
from dataclasses import asdict, replace
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from PyQt6.QtCore import QSignalBlocker, Qt
from PyQt6.QtWidgets import QFileDialog, QFrame, QHBoxLayout
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    ComboBox,
    FluentIcon,
    IconWidget,
    MessageBox,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    StrongBodyLabel,
    TitleLabel,
    TransparentToolButton,
    themeColor,
)

from ....application.tasks.jobs import Job
from ....application.tasks.models import MODEL_VARIANTS, model_spec
from ....core.translation.api import ApiProfile
from ...components.forms import Page
from .cards import ApiItemCard, ApiTypeCard
from .dialogs import AddApiDialog, ApiEditDialog, ApiParametersDialog

BUILTIN_LOCAL = "__hy_mt_gguf__"
OFFICIAL_HOSTS = {"api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com", "api.deepseek.com", "opencode.ai"}


def profile_group(profile):
    if profile.group != "auto":
        return profile.group
    hostname = (urlsplit(profile.base_url).hostname or "").lower()
    if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
        return "local"
    try:
        address = ip_address(hostname)
        if address.is_private or address.is_loopback:
            return "local"
    except ValueError:
        pass
    return "online" if hostname in OFFICIAL_HOSTS else "custom"


class ApiPage(Page):
    def __init__(self, window):
        super().__init__("api", "接口管理", "激活一个翻译接口；通过接口菜单测试、编辑连接信息或调整参数。", window)
        self.window = window
        self.cards = {}
        self.dialog = None
        self.test_name = ""
        self.body.takeAt(0).widget().deleteLater()
        header = CardWidget(self.content)
        row = QHBoxLayout(header)
        row.setContentsMargins(22, 20, 22, 20)
        row.setSpacing(14)
        icon = IconWidget(FluentIcon.CLOUD, header)
        icon.setFixedSize(26, 26)
        row.addWidget(icon)
        row.addWidget(TitleLabel("接口管理", header))
        row.addStretch(1)
        self.status_pill = QFrame(header)
        self.status_pill.setObjectName("apiStatusPill")
        pill = QHBoxLayout(self.status_pill)
        pill.setContentsMargins(14, 7, 14, 7)
        pill.setSpacing(8)
        self.status_icon = IconWidget(FluentIcon.ROBOT, self.status_pill)
        self.status_icon.setFixedSize(16, 16)
        pill.addWidget(self.status_icon)
        self.status = StrongBodyLabel("", self.status_pill)
        pill.addWidget(self.status)
        row.addWidget(self.status_pill)
        row.addStretch(1)
        settings = TransparentToolButton(FluentIcon.DEVELOPER_TOOLS, header)
        settings.setToolTip("任务与输出设置")
        settings.clicked.connect(lambda: window.switchTo(window.settings_page))
        row.addWidget(settings)
        self.add_button = PrimaryPushButton("添加接口", header)
        self.add_button.setIcon(FluentIcon.ADD)
        self.add_button.clicked.connect(self.add_profile)
        row.addWidget(self.add_button)
        self.body.insertWidget(0, header)
        local_setup = self.section("开始使用", "请先激活本地或远端模型。本地 HY-MT-2 可选 7B 或 1.8B，均使用 Q4_K_M；"
                                   "使用远端 API 无需下载模型。")
        selection = QHBoxLayout()
        selection.addWidget(BodyLabel("下载模型", self.content))
        self.model_variant = ComboBox(self.content)
        for variant, spec in MODEL_VARIANTS.items():
            self.model_variant.addItem(f"{spec.label} · Q4_K_M · 约 {spec.size / 1e9:.2f} GB", userData=variant)
        self.model_variant.setCurrentIndex(self.model_variant.findData(window.settings.download_variant))
        self.model_variant.currentIndexChanged.connect(self.select_variant)
        selection.addWidget(self.model_variant)
        selection.addStretch()
        local_setup.addLayout(selection)
        self.model_status = BodyLabel("", self.content)
        self.model_status.setWordWrap(True)
        local_setup.addWidget(self.model_status)
        self.download_progress = ProgressBar(self.content)
        self.download_progress.setRange(0, 100)
        self.download_progress.hide()
        local_setup.addWidget(self.download_progress)
        actions = QHBoxLayout()
        self.local_button = PrimaryPushButton("下载并激活本地模型", self.content)
        self.local_button.clicked.connect(self.activate_selected_model)
        self.choose_model = PushButton("选择已有 GGUF", self.content)
        self.choose_model.clicked.connect(self.select_model)
        self.pause_download = PushButton("暂停下载", self.content)
        self.pause_download.clicked.connect(window.runner.cancel)
        self.pause_download.hide()
        for button in (self.local_button, self.choose_model, self.pause_download):
            actions.addWidget(button)
        actions.addStretch()
        local_setup.addLayout(actions)
        self.groups = {}
        for key, title, description, group_icon in (
            ("local", "本地接口", "本地 HY-MT-2 GGUF 和本地部署的 API 模型", FluentIcon.CONNECT),
            ("online", "官方接口", "官方平台提供的远程模型接口", FluentIcon.CLOUD),
            ("custom", "自定义接口", "第三方、代理或自行配置的模型服务", FluentIcon.ASTERISK),
        ):
            group = ApiTypeCard(title, description, group_icon, self.content)
            self.groups[key] = group
            self.body.addWidget(group)
        self.empty = BodyLabel("尚未添加 API 接口。点击顶部“添加接口”配置远端或本地 API，也可下载或选择本地 GGUF。", self.content)
        self.empty.setWordWrap(True)
        self.body.addWidget(self.empty)
        result = self.section("接口测试", "测试会发送 Iron Ingot，并使用该接口保存的配置。")
        self.result = BodyLabel("选择接口菜单中的“测试接口”查看连接和试译结果。", self.content)
        self.result.setWordWrap(True)
        result.addWidget(self.result)
        self.body.addStretch()
        self.refresh()

    def get_profile(self, profile_id):
        data = next((p for p in self.window.settings.api_profiles if p["id"] == profile_id), None)
        if data is None:
            raise ValueError("接口不存在，请刷新列表")
        return ApiProfile(**data)

    def refresh(self):
        for group in self.groups.values():
            group.clear()
        self.cards.clear()
        local = ApiItemCard(BUILTIN_LOCAL, "HY-MT-2 · GGUF", "激活时自动下载缺失模型；也可选择已有 GGUF，推理参数在设置页配置。",
                            builtin=True, parent=self.groups["local"].container)
        self.add_card(local, "local")
        for data in sorted(self.window.settings.api_profiles, key=lambda p: p["name"].casefold()):
            profile = ApiProfile(**data)
            group = profile_group(profile)
            card = ApiItemCard(profile.id, profile.name, f"{profile.protocol} · {profile.model or '未填写模型'}\n{profile.base_url}",
                               parent=self.groups[group].container)
            self.add_card(card, group)
        for group in self.groups.values():
            group.setVisible(group.flow.count() > 0)
        self.empty.setVisible(not self.window.settings.api_profiles)
        self.sync_active()
        self.set_busy(self.window.runner.busy)

    def add_card(self, card, group):
        card.activateClicked.connect(self.activate)
        card.testClicked.connect(self.test)
        card.editClicked.connect(self.edit)
        card.argsClicked.connect(self.edit_parameters)
        card.copyClicked.connect(self.duplicate)
        card.deleteClicked.connect(self.remove)
        self.cards[card.profile_id] = card
        self.groups[group].add(card)

    def sync_active(self):
        settings = self.window.settings
        ready = settings.interface_ready()
        selected = (BUILTIN_LOCAL if settings.engine == "local" else settings.active_api) if ready else ""
        name = "HY-MT-2 · GGUF"
        if settings.engine == "api":
            try:
                name = settings.selected_profile().name
            except ValueError:
                name = "尚未选择接口"
        text = "已激活：" + name if selected in self.cards else "尚未激活模型"
        self.status.setText(self.status.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, 240))
        self.status_pill.setToolTip("当前翻译引擎：" + settings.engine_label())
        color = themeColor()
        self.status_pill.setStyleSheet(f"QFrame#apiStatusPill {{ background: rgba({color.red()}, {color.green()}, {color.blue()}, 24); "
                                      f"border: 1px solid rgba({color.red()}, {color.green()}, {color.blue()}, 65); border-radius: 16px; }}")
        for profile_id, card in self.cards.items():
            card.set_active(profile_id == selected)
        local_exists = bool(settings.model and Path(settings.model).is_file())
        blocker = QSignalBlocker(self.model_variant)
        self.model_variant.setCurrentIndex(self.model_variant.findData(settings.download_variant))
        del blocker
        spec = model_spec(settings.download_variant)
        selected_exists = self.selected_model_path(spec).is_file()
        self.local_button.setText(("激活" if selected_exists else "下载并激活") + spec.label + " 模型")
        if not self.downloading():
            self.model_status.setText("本地模型：" + settings.model if local_exists else
                                      "本地模型尚未就绪，请下载或选择已有 GGUF，或添加并激活 API 接口。")

    def showEvent(self, event):
        super().showEvent(event)
        self.sync_active()

    def store_profile(self, profile):
        profile.validate(require_model=False)
        profiles = [dict(p) for p in self.window.settings.api_profiles]
        position = next((i for i, p in enumerate(profiles) if p["id"] == profile.id), None)
        if position is None:
            profiles.append(asdict(profile))
        else:
            profiles[position] = asdict(profile)
        self.window.save_settings(replace(self.window.settings, api_profiles=profiles))
        self.refresh()

    def run_editor(self, dialog):
        self.dialog = dialog
        try:
            if dialog.exec() and dialog.profile is not None:
                self.store_profile(dialog.profile)
        finally:
            self.dialog = None
            dialog.deleteLater()

    def add_profile(self):
        self.run_editor(AddApiDialog(self.window))

    def edit(self, profile_id):
        if profile_id == BUILTIN_LOCAL:
            self.window.switchTo(self.window.settings_page)
            return
        self.run_editor(ApiEditDialog(self.get_profile(profile_id), self.window))

    def edit_parameters(self, profile_id):
        self.run_editor(ApiParametersDialog(self.get_profile(profile_id), self.window))

    def activate(self, profile_id):
        if self.window.runner.busy:
            self.window.notify("已有操作正在运行，请完成或暂停后再激活接口", warning=True)
            return
        try:
            settings = self.window.settings
            if profile_id == BUILTIN_LOCAL:
                if not settings.model or not Path(settings.model).is_file():
                    return self.activate_selected_model()
                settings = replace(settings, engine="local")
            else:
                self.get_profile(profile_id).validate()
                settings = replace(settings, engine="api", active_api=profile_id)
            self.window.save_settings(settings)
            self.sync_active()
        except ValueError as exc:
            self.window.notify(str(exc), error=True)

    def select_variant(self):
        variant = self.model_variant.currentData()
        self.window.save_settings(replace(self.window.settings, download_variant=variant))

    def selected_model_path(self, spec):
        current = Path(self.window.settings.model) if self.window.settings.model else None
        if current and current.name == spec.filename and current.is_file():
            return current
        return spec.path

    def activate_selected_model(self):
        if self.window.runner.busy:
            self.window.notify("已有操作正在运行，请完成或暂停后再激活接口", warning=True)
            return
        variant = self.model_variant.currentData()
        spec = model_spec(variant)
        target = self.selected_model_path(spec)
        if target.is_file():
            self.window.settings_page.model.setPath(str(target))
            self.window.settings_page.save_timer.stop()
            self.window.save_settings(replace(self.window.settings, model=str(target), engine="local"))
            return

        def job():
            self.download_progress.setValue(0)
            self.download_progress.show()
            self.model_status.setText(f"正在准备下载 HY-MT-2 {spec.label}；暂停或失败后可重试继续下载。")
            return Job("download-model", output=target, download_variant=variant)

        self.window.run_job(job, "模型下载")

    def select_model(self):
        if self.window.runner.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self.window, "选择 HY-MT-2 GGUF 模型", "", "GGUF 模型 (*.gguf)")
        if not path:
            return
        if not Path(path).is_file():
            self.window.notify("模型文件不存在，请重新选择", error=True)
            return
        self.window.settings_page.model.setPath(path)
        self.window.settings_page.save_timer.stop()
        try:
            variant = next((key for key, spec in MODEL_VARIANTS.items() if Path(path).name == spec.filename),
                           self.window.settings.download_variant)
            self.window.save_settings(replace(self.window.settings_page.collect(), engine="local",
                                              download_variant=variant))
        except ValueError as exc:
            self.window.notify(str(exc), error=True)

    def downloading(self):
        return self.window.runner.busy and self.window.pending_label == "模型下载"

    def update_progress(self, payload):
        if payload.get("operation") != "download-model":
            return
        done, total = payload["completed"], payload["total"]
        self.download_progress.setValue(int(done * 100 / max(1, total)))
        self.model_status.setText(f"{payload['phase']} · {done / 1e9:.2f} / {total / 1e9:.2f} GB")

    def download_finished(self, code, result, cancelled):
        self.pause_download.hide()
        self.sync_active()
        if cancelled:
            self.model_status.setText("下载已暂停，已下载内容保留；保持模型选择，点击下载按钮继续。")
            return
        if code != 0 or "error" in result:
            message = result.get("error", "模型下载失败，请重试或选择已有 GGUF")
            self.model_status.setText(message)
            self.window.notify(message, error=True)
            return
        path = result.get("model", "")
        if not path or not Path(path).is_file():
            self.model_status.setText("下载结果中未找到模型文件，请重试。")
            return
        self.window.settings_page.model.setPath(path)
        self.window.settings_page.save_timer.stop()
        self.window.save_settings(replace(self.window.settings, model=path, engine="local",
                                          download_variant=result.get("download_variant",
                                                                      self.window.settings.download_variant)))
        self.model_status.setText("模型已下载、校验并激活，可开始翻译；建议先在接口菜单中测试接口。")

    def duplicate(self, profile_id):
        source = self.get_profile(profile_id)
        self.store_profile(replace(source, id=uuid4().hex, name=source.name + " 副本"))

    def remove(self, profile_id):
        profile = self.get_profile(profile_id)
        dialog = MessageBox("删除接口", f"删除“{profile.name}”？已有任务的检查点会保留；使用此接口续跑时需要重新配置凭据。", self.window)
        dialog.yesButton.setText("删除")
        dialog.cancelButton.setText("取消")
        if not dialog.exec():
            return
        settings = self.window.settings
        profiles = [dict(p) for p in settings.api_profiles if p["id"] != profile_id]
        removing_active = settings.active_api == profile_id
        self.window.save_settings(replace(settings, api_profiles=profiles,
                                          active_api="" if removing_active else settings.active_api,
                                          script_api="" if settings.script_api == profile_id else settings.script_api,
                                          polish_api="" if settings.polish_api == profile_id else settings.polish_api,
                                          engine="local" if removing_active else settings.engine))
        self.refresh()

    def test(self, profile_id):
        def job():
            settings = self.window.settings
            if profile_id == BUILTIN_LOCAL:
                settings = replace(settings, engine="local")
                self.test_name = "HY-MT-2 · GGUF"
            else:
                profile = self.get_profile(profile_id)
                settings = replace(settings, engine="api", active_api=profile_id)
                self.test_name = profile.name
            options = settings.model_options()
            self.result.setText(self.test_name + " · 正在连接并试译…")
            return Job("doctor", probe=True, **options)
        self.window.run_job(job, "接口试译")

    def show_result(self, result):
        message = result.get("error") or "试译结果：" + result.get("probe_translation", "无译文")
        self.result.setText(self.test_name + " · " + message)

    def set_busy(self, busy):
        self.model_variant.setEnabled(not busy)
        self.local_button.setEnabled(not busy)
        self.choose_model.setEnabled(not busy)
        self.pause_download.setVisible(self.downloading())
        for card in self.cards.values():
            card.set_busy(busy)
