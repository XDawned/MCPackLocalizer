# [Module: desktop.api_page] [Status: 已完成] [Brief: 独立本地与 API 接口管理、激活和模型下载]
from dataclasses import asdict, replace
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
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

from ....application.config.interfaces import LEGACY_LOCAL_ID, LocalProfile
from ....application.tasks.jobs import Job
from ....core.translation.api import INDEX_PROFILE_ID, ApiProfile, index_profile
from ...components.forms import Page
from .cards import ApiItemCard, ApiTypeCard
from .dialogs import AddApiDialog, ApiEditDialog, ApiParametersDialog
from .local import LocalEditDialog, LocalParametersDialog

BUILTIN_LOCAL = LEGACY_LOCAL_ID
OFFICIAL_HOSTS = {"api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com", "api.deepseek.com", "opencode.ai",
                  "index-translate.bilibili.com"}


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
        super().__init__("api", "接口管理", "通过“添加接口”配置本地 GGUF 或 API；每个接口分别保存模型与模板。", window)
        self.window = window
        self.cards = {}
        self.dialog = None
        self.test_name = ""
        self.pending_local = None
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
        status_icon = IconWidget(FluentIcon.ROBOT, self.status_pill)
        status_icon.setFixedSize(16, 16)
        pill.addWidget(status_icon)
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
        self.groups = {}
        for key, title, description, group_icon in (
            ("translation", "专用翻译模型接口", "本地 GGUF 与专用翻译 API，分别保存模型与模板", FluentIcon.LANGUAGE),
            ("llm", "大模型接口", "通用大模型，可用于翻译、脚本与修润", FluentIcon.CLOUD),
        ):
            group = ApiTypeCard(title, description, group_icon, self.content)
            self.groups[key] = group
            self.body.addWidget(group)
        self.empty = BodyLabel("点击“添加接口”配置本地模型或 API，也可直接使用内置的 Index 官方免费 API。", self.content)
        self.empty.setWordWrap(True)
        self.body.addWidget(self.empty)
        progress = self.section("模型下载")
        self.download_card = progress.parentWidget()
        self.model_status = BodyLabel("", self.content)
        self.model_status.setWordWrap(True)
        progress.addWidget(self.model_status)
        self.download_progress = ProgressBar(self.content)
        self.download_progress.setRange(0, 100)
        progress.addWidget(self.download_progress)
        self.pause_download = PushButton("暂停下载", self.content)
        self.pause_download.clicked.connect(window.runner.cancel)
        progress.addWidget(self.pause_download)
        self.download_card.hide()
        result = self.section("接口测试", "测试会发送 Iron Ingot，并使用该接口保存的配置。")
        self.result = BodyLabel("选择接口菜单中的“测试接口”查看连接和试译结果。", self.content)
        self.result.setWordWrap(True)
        result.addWidget(self.result)
        self.body.addStretch()
        self.refresh()

    def get_profile(self, profile_id):
        data = next((p for p in self.window.settings.api_profiles if p["id"] == profile_id), None)
        if data is None:
            if profile_id == INDEX_PROFILE_ID:
                return index_profile()
            raise ValueError("接口不存在，请刷新列表")
        return ApiProfile(**data)

    def get_local_profile(self, profile_id):
        return next((p for p in self.window.settings.local_interfaces() if p.id == profile_id), None)

    def refresh(self):
        for group in self.groups.values():
            group.clear()
        self.cards.clear()
        settings = self.window.settings
        for profile in settings.local_interfaces():
            template = settings.templates()[profile.template_id]
            state = "模型已就绪" if Path(profile.model).is_file() else "模型文件缺失，激活时下载预设或重新选择文件"
            card = ApiItemCard(profile.id, profile.name,
                               f"本地 GGUF · {state}\n模板：{template.name} · 并发 1\n{profile.model}",
                               local=True, parent=self.groups["translation"].container)
            self.add_card(card, "translation")
        profiles = list(settings.api_profiles)
        if not any(p["id"] == INDEX_PROFILE_ID for p in profiles):
            profiles.append(asdict(index_profile()))
        for data in sorted(profiles, key=lambda p: p["name"].casefold()):
            profile = ApiProfile(**data)
            group = profile.interface_type
            template = settings.templates()[profile.template_id]
            deployment = {"local": "本地", "online": "官方远端", "custom": "自定义"}[profile_group(profile)]
            card = ApiItemCard(profile.id, profile.name,
                               f"{deployment} · {profile.protocol} · {profile.model or '未填写模型'}\n"
                               f"模板：{template.name} · 并发 {profile.concurrency}\n{profile.base_url}",
                               parent=self.groups[group].container)
            self.add_card(card, group)
        for group in self.groups.values():
            group.setVisible(group.flow.count() > 0)
        self.empty.setVisible(not settings.api_profiles and not settings.local_interfaces())
        self.sync_active()
        self.set_busy(self.window.runner.busy)

    def add_card(self, card, group):
        for signal, callback in ((card.activateClicked, self.activate), (card.testClicked, self.test),
                                 (card.editClicked, self.edit), (card.argsClicked, self.edit_parameters),
                                 (card.promptClicked, self.edit_prompt), (card.copyClicked, self.duplicate),
                                 (card.deleteClicked, self.remove)):
            signal.connect(callback)
        self.cards[card.profile_id] = card
        self.groups[group].add(card)

    def sync_active(self):
        settings = self.window.settings
        local = settings.current_local_profile()
        selected = local.id if settings.engine == "local" and local else settings.active_api if settings.engine == "api" else ""
        if not settings.interface_ready():
            selected = ""
        text = "已激活：" + settings.engine_label() if selected in self.cards else "尚未激活模型"
        self.status.setText(self.status.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, 300))
        self.status_pill.setToolTip("当前翻译引擎：" + settings.engine_label())
        color = themeColor()
        self.status_pill.setStyleSheet(f"QFrame#apiStatusPill {{ background: rgba({color.red()}, {color.green()}, {color.blue()}, 24); "
                                      f"border: 1px solid rgba({color.red()}, {color.green()}, {color.blue()}, 65); border-radius: 16px; }}")
        for profile_id, card in self.cards.items():
            card.set_active(profile_id == selected)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def store_profile(self, profile):
        profile.validate()
        if isinstance(profile, LocalProfile):
            settings = self.window.settings.store_local_profile(profile)
        else:
            profiles = [dict(p) for p in self.window.settings.api_profiles]
            position = next((i for i, p in enumerate(profiles) if p["id"] == profile.id), None)
            if position is None:
                profiles.append(asdict(profile))
            else:
                profiles[position] = asdict(profile)
            settings = replace(self.window.settings, api_profiles=profiles)
        self.window.save_settings(settings)
        self.refresh()

    def run_editor(self, dialog):
        self.dialog = dialog
        try:
            if dialog.exec() and dialog.profile is not None:
                profile = dialog.profile
                self.store_profile(profile)
                if isinstance(profile, LocalProfile) and getattr(dialog, "download_local", False):
                    self.start_download(profile)
        finally:
            self.dialog = None
            dialog.deleteLater()

    def add_profile(self):
        self.run_editor(AddApiDialog(self.window))

    def edit(self, profile_id):
        local = self.get_local_profile(profile_id)
        self.run_editor(LocalEditDialog(local, self.window) if local else ApiEditDialog(self.get_profile(profile_id), self.window))

    def edit_parameters(self, profile_id):
        local = self.get_local_profile(profile_id)
        self.run_editor(LocalParametersDialog(local, self.window) if local else ApiParametersDialog(self.get_profile(profile_id), self.window))

    def edit_prompt(self, profile_id):
        profile = self.get_local_profile(profile_id) or self.get_profile(profile_id)
        self.window.prompts.edit_template(profile.template_id)

    def activate(self, profile_id):
        if self.window.runner.busy:
            self.window.notify("已有操作正在运行，请完成或暂停后再激活接口", warning=True)
            return
        try:
            settings = self.window.settings
            local = self.get_local_profile(profile_id)
            if local:
                if not Path(local.model).is_file():
                    if not local.download_enabled:
                        raise ValueError("模型文件不存在，请编辑此接口并重新选择 GGUF")
                    return self.start_download(local)
                settings = settings.use_local_profile(profile_id)
            else:
                profile = self.get_profile(profile_id)
                profile.validate()
                if not any(p["id"] == profile_id for p in settings.api_profiles):
                    self.store_profile(profile)
                    settings = self.window.settings
                settings = replace(settings, engine="api", active_api=profile_id)
            self.window.save_settings(settings)
            self.refresh()
        except ValueError as exc:
            self.window.notify(str(exc), error=True)

    def start_download(self, profile):
        def arguments():
            self.pending_local = profile
            self.download_card.show()
            self.download_progress.setValue(0)
            self.model_status.setText(profile.name + " · 正在准备下载；暂停后可再次激活此接口继续。")
            return Job("download-model", output=Path(profile.model), download_variant=profile.download_variant)
        self.window.run_job(arguments, "模型下载")

    def downloading(self):
        return self.window.runner.busy and self.window.pending_label == "模型下载"

    def update_progress(self, payload):
        if payload.get("operation") == "download-model":
            self.download_card.show()
            self.download_progress.setValue(int(payload["completed"] * 100 / max(1, payload["total"])))
            self.model_status.setText(f"{payload['phase']} · {payload['completed'] / 1e9:.2f} / {payload['total'] / 1e9:.2f} GB")

    def download_finished(self, code, result, cancelled):
        self.pause_download.hide()
        self.download_card.show()
        if cancelled:
            self.model_status.setText("下载已暂停；再次激活此接口可继续下载。")
        elif code != 0 or "error" in result:
            self.model_status.setText(result.get("error", "模型下载失败，请重试"))
        else:
            path = result.get("model", "")
            if not self.pending_local or not path or not Path(path).is_file():
                self.model_status.setText("下载结果中未找到模型文件，请重试。")
                return
            profile = replace(self.pending_local, model=path)
            settings = self.window.settings.store_local_profile(profile).use_local_profile(profile.id)
            self.window.save_settings(settings)
            self.model_status.setText(profile.name + " · 已下载、校验并激活。")
        self.refresh()

    def duplicate(self, profile_id):
        source = self.get_local_profile(profile_id) or self.get_profile(profile_id)
        self.store_profile(replace(source, id=uuid4().hex, name=source.name + " 副本"))

    def remove(self, profile_id):
        local = self.get_local_profile(profile_id)
        profile = local or self.get_profile(profile_id)
        message = "移除此接口配置，模型文件仍保留。" if local else "已有任务的检查点会保留；续跑时需要重新配置凭据。"
        dialog = MessageBox("删除接口", f"删除“{profile.name}”？{message}", self.window)
        dialog.yesButton.setText("删除")
        dialog.cancelButton.setText("取消")
        if not dialog.exec():
            return
        settings = self.window.settings
        if local:
            remaining = [p for p in settings.local_interfaces() if p.id != profile_id]
            current = settings.current_local_profile()
            bindings = dict(settings.local_model_templates)
            if not any(Path(p.model) == Path(local.model) for p in remaining):
                bindings.pop(str(Path(local.model)), None)
            updated = replace(settings, local_profiles=[asdict(p) for p in remaining], local_model_templates=bindings)
            if current and current.id == profile_id:
                if remaining:
                    updated = replace(updated.use_local_profile(remaining[0].id), engine=settings.engine)
                else:
                    updated = replace(updated, model="", active_local="", local_template_id="hy_mt")
            settings = updated
        else:
            settings = replace(settings, api_profiles=[dict(p) for p in settings.api_profiles if p["id"] != profile_id],
                               active_api="" if settings.active_api == profile_id else settings.active_api,
                               script_api="" if settings.script_api == profile_id else settings.script_api,
                               polish_api="" if settings.polish_api == profile_id else settings.polish_api,
                               engine="local" if settings.active_api == profile_id else settings.engine)
        self.window.save_settings(settings)
        self.refresh()

    def test(self, profile_id):
        def arguments():
            settings = self.window.settings
            local = self.get_local_profile(profile_id)
            if local:
                settings = settings.use_local_profile(profile_id)
                self.test_name = local.name
            else:
                profile = self.get_profile(profile_id)
                if not any(p["id"] == profile_id for p in settings.api_profiles):
                    settings = replace(settings, api_profiles=[*settings.api_profiles, asdict(profile)])
                settings = replace(settings, engine="api", active_api=profile_id)
                self.test_name = profile.name
            self.result.setText(self.test_name + " · 正在连接并试译…")
            return Job("doctor", probe=True, **settings.model_options())
        self.window.run_job(arguments, "接口试译")

    def show_result(self, result):
        self.result.setText(self.test_name + " · " + (result.get("error") or "试译结果：" + result.get("probe_translation", "无译文")))

    def set_busy(self, busy):
        self.add_button.setEnabled(not busy)
        self.pause_download.setVisible(self.downloading())
        for card in self.cards.values():
            card.set_busy(busy)
