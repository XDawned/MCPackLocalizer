# [Module: desktop.window] [Status: 已完成] [Brief: Fluent 导航、设置持久化及统一任务生命周期]
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from PyQt6.QtCore import QProcess, QSettings, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon, QTextCursor
from PyQt6.QtWidgets import QApplication
from qfluentwidgets import (
    FluentIcon as FIF,
)
from qfluentwidgets import (
    FluentWindow,
    InfoBar,
    InfoBarPosition,
    MessageBox,
    NavigationItemPosition,
    Theme,
    setTheme,
    setThemeColor,
)

from ...application.config.settings import Settings
from ...paths import RESOURCES, migrated_path
from ..logging import LogStore
from ..process import TaskProcess
from .api.page import ApiPage
from .logs import LogPage
from .settings import SettingsPage
from .tasks.review import ReviewPage
from .tasks.workspace import WorkspacePage
from .tools.language import LanguageToolsPage
from .translation.playground import PlaygroundPage
from .translation.prompts import PromptsPage
from .translation.rules import TranslationRulesPage


class MainWindow(FluentWindow):
    def __init__(self, preferences=None, log_store=None):
        super().__init__()
        self.log_store = log_store if log_store is not None else LogStore(parent=self)
        self.logs_page = LogPage(self, self.log_store)
        self.preferences = preferences if preferences is not None else QSettings("MCPackLocalizer", "Desktop")
        self.first_launch = False
        try:
            data = json.loads(self.preferences.value("settings", "{}"))
            self.first_launch = not isinstance(data, dict) or not data
            self.settings = Settings.from_dict(data if isinstance(data, dict) else {})
        except (ValueError, TypeError):
            self.first_launch = True
            self.settings = Settings.defaults()
        try:
            recent = json.loads(self.preferences.value("recent_tasks", "[]"))
            self.recent_tasks = list(dict.fromkeys(migrated_path(p) for p in recent if isinstance(p, str)))[:10] if isinstance(recent, list) else []
        except (ValueError, TypeError):
            self.recent_tasks = []
        self.runner = TaskProcess(self)
        self.pending_task = ""
        self.pending_label = ""
        self.pending_polish_run_id = None
        self.closing = False
        self.review = ReviewPage(self)
        self.workspace = WorkspacePage(self)
        self.playground = PlaygroundPage(self)
        self.tools = LanguageToolsPage(self)
        self.settings_page = SettingsPage(self)
        self.api = ApiPage(self)
        self.prompts = PromptsPage(self)
        self.rules = TranslationRulesPage(self)
        self.addSubInterface(self.api, FIF.CLOUD, "接口管理")
        self.navigationInterface.addItemHeader('翻译', NavigationItemPosition.SCROLL)
        self.addSubInterface(self.workspace, FIF.HOME, "整合包", NavigationItemPosition.SCROLL)
        self.navigationInterface.addSeparator(NavigationItemPosition.SCROLL)
        self.navigationInterface.addItemHeader('翻译配置', NavigationItemPosition.SCROLL)
        self.addSubInterface(self.prompts, FIF.EDIT, "提示词", NavigationItemPosition.SCROLL)
        self.addSubInterface(self.rules, FIF.BOOK_SHELF, "术语库", NavigationItemPosition.SCROLL)
        self.navigationInterface.addItemHeader('辅助功能', NavigationItemPosition.SCROLL)
        self.addSubInterface(self.playground, FIF.LANGUAGE, "翻译测试", NavigationItemPosition.SCROLL)
        self.addSubInterface(self.tools, FIF.FOLDER, "任务提取", NavigationItemPosition.SCROLL)
        self.addSubInterface(self.logs_page, FIF.DOCUMENT, "运行日志", NavigationItemPosition.BOTTOM)
        self.addSubInterface(self.settings_page, FIF.SETTING, "设置", NavigationItemPosition.BOTTOM)
        self.stackedWidget.setAnimationEnabled(False)
        self.runner.busyChanged.connect(self.busy_changed)
        self.runner.log.connect(self.log_store.append)
        self.runner.log.connect(self.append_task_log)
        self.runner.progress.connect(self.update_progress)
        self.runner.done.connect(self.job_done)
        self.runner.stopper.finished.connect(lambda: QTimer.singleShot(0, self.close) if self.closing else None)
        desktop = QApplication.primaryScreen().availableGeometry()
        initial_width = int(desktop.width() * 0.8)
        initial_height = int(desktop.height() * 0.8)
        self.resize(initial_width, initial_height)
        self.setWindowTitle("MCPackLocalizer")
        if (RESOURCES / "icon.ico").is_file():
            self.setWindowIcon(QIcon(str(RESOURCES / "icon.ico")))
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(min(self.width(), screen.width()), min(self.height(), screen.height()))
        self.move(screen.center() - self.rect().center())
        self.navigationInterface.setExpandWidth(208)
        self.navigationInterface.expand(useAni=False)
        self.apply_theme()
        self.switchTo(self.api if self.first_launch or not self.settings.interface_ready() else self.workspace)

    def apply_theme(self):
        setTheme({"system": Theme.AUTO, "light": Theme.LIGHT, "dark": Theme.DARK}[self.settings.theme])
        setThemeColor(self.settings.theme_color)

    def save_settings(self, settings):
        settings.validate()
        previous = self.settings
        self.settings = settings
        self.preferences.setValue("settings", json.dumps(asdict(settings), ensure_ascii=False))
        if previous.theme != settings.theme or previous.theme_color != settings.theme_color:
            self.apply_theme()
        self.workspace.engine.setText("当前翻译引擎：" + settings.engine_label())
        self.workspace.translation.refresh_script_profiles()
        self.review.refresh_polish_profiles()
        self.playground.refresh()
        if (previous.model != settings.model or previous.active_local != settings.active_local or
                any(getattr(previous, key) != getattr(settings, key) for key in
                    ("runtime_python", "backend", "threads", "gpu_layers", "context_size", "max_tokens", "term_tokens", "timeout"))):
            self.settings_page.restore(settings)
        else:
            self.settings_page.sync_engine(settings.engine)
        self.api.refresh()
        self.workspace.refresh_languages()
        for name, widgets in (("output_allow_partial", (self.workspace.partial, self.review.partial)),
                              ("output_replace_locale", (self.workspace.replace, self.review.replace)),
                              ("output_include_i18n", (self.workspace.i18n, self.review.i18n))):
            if getattr(previous, name) != getattr(settings, name):
                for widget in widgets:
                    widget.setChecked(getattr(settings, name))
        self.notify("设置已保存，下一次翻译使用新设置")

    def remember_task(self, path):
        self.recent_tasks = [path] + [p for p in self.recent_tasks if p != path]
        self.recent_tasks = self.recent_tasks[:10]
        self.preferences.setValue("recent_tasks", json.dumps(self.recent_tasks, ensure_ascii=False))
        self.review.update_recent()

    def notify(self, message, error=False, warning=False):
        if error or warning:
            self.log_store.append(message, "ERROR" if error else "WARNING", "界面")
        method = InfoBar.error if error else InfoBar.warning if warning else InfoBar.success
        method(title="操作提示", content=message[:700], parent=self, duration=8000 if error else 5000,
               position=InfoBarPosition.TOP_RIGHT, isClosable=True)

    def run_job(self, factory, label, task_path=""):
        if self.runner.busy:
            self.notify("已有操作正在运行，可在整合包汉化页查看进度或暂停", warning=True)
            return
        if self.review.loading:
            self.notify("任务正在读取，请稍候", warning=True)
            return
        if label not in {"保存审核", "模型下载"} and not self.review.discard_changes():
            return
        try:
            arguments = factory()
            self.pending_task, self.pending_label = task_path, label
            self.pending_polish_run_id = arguments.polish_run_id if arguments.operation == "polish" else None
            self.workspace.status.setText(label + " · 正在启动…")
            self.workspace.logs.clear()
            self.log_store.append(f"开始{label}" + (f" · {task_path}" if task_path else ""), "INFO", "任务")
            self.runner.start(arguments)
            if label == "模型下载":
                self.switchTo(self.api)
            elif label not in {"单条翻译", "提示词预览", "保存审核", "继续翻译", "导出补丁", "接口试译", "API 批量修润", "接受修润结果"}:
                self.switchTo(self.workspace)
        except (ValueError, OSError, RuntimeError) as exc:
            self.notify(str(exc), error=True)

    def append_task_log(self, line):
        try:
            payload = json.loads(line)
        except ValueError:
            payload = None
        if isinstance(payload, dict) and payload.get("type") == "log":
            line = f"[{payload.get('level', 'INFO')}] {payload.get('message', '')}"
        # 按纯文本追加，模型或异常中的 HTML 不应被日志框解释。
        cursor = self.workspace.logs.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if not self.workspace.logs.document().isEmpty():
            cursor.insertBlock()
        cursor.insertText(line)

    def busy_changed(self, busy):
        for page in (self.workspace, self.review, self.playground, self.tools, self.settings_page, self.api):
            page.set_busy(busy)
        self.setWindowTitle("MCPackLocalizer · " + (self.pending_label + "进行中" if busy else "整合包本地化"))

    def update_progress(self, payload):
        if payload.get("operation") == "download-model":
            self.api.update_progress(payload)
        else:
            self.workspace.update_progress(payload)
            self.review.update_progress(payload)

    def job_done(self, code, result, cancelled):
        level = "WARNING" if cancelled or code == 1 else "ERROR" if code else "INFO"
        self.log_store.append(f"{self.pending_label} · " + ("已暂停" if cancelled else f"结束（退出码 {code}）"),
                              level, "任务")
        self.log_store.append(json.dumps(result, ensure_ascii=False, indent=2),
                              "ERROR" if result.get("error") else "DEBUG", "任务结果")
        for warning in result.get("warnings", []):
            self.log_store.append(str(warning), "WARNING", "任务")
        if self.pending_label == "模型下载":
            self.api.download_finished(code, result, cancelled)
            if self.closing:
                QTimer.singleShot(0, self.close)
            return
        if self.pending_label == "提示词预览":
            self.playground.show_preview(result, cancelled)
            if "error" in result and not cancelled:
                self.notify(result["error"], error=True)
            if self.closing:
                QTimer.singleShot(0, self.close)
            return
        self.workspace.show_result(result, cancelled)
        if self.pending_label == "单条翻译":
            self.playground.show_result(result, cancelled)
        if self.pending_label == "接口试译":
            self.api.show_result(result)
        if self.closing:
            QTimer.singleShot(0, self.close)
            return
        if not cancelled and "error" in result:
            self.notify(result["error"], error=True)
        elif not cancelled:
            i18n = result.get("i18n_mod", {})
            incomplete = (result.get("partial") or result.get("scan_complete") is False
                          or result.get("model_exists") is False or code != 0)
            message = self.pending_label + ("完成，仍有待处理内容；请查看结果" if incomplete else "完成")
            self.notify(message, warning=bool(incomplete))
            if i18n.get("status") == "unavailable":
                self.notify("I18nUpdateMod 未加入补丁：" + i18n.get("message", ""), warning=True)
        if self.pending_task and (Path(self.pending_task) / "state.sqlite3").is_file():
            if self.pending_label == "API 批量修润" and (result.get("run_id") or self.pending_polish_run_id):
                run_id = result.get("run_id") or self.pending_polish_run_id
                self.review.queued_polish_preview = (str(Path(self.pending_task).resolve()), run_id)
            # Successful review has committed the editor value; don't ask to discard it.
            if self.pending_label == "保存审核" and "error" not in result:
                self.review.translation.document().setModified(False)
            if self.pending_label == "保存审核" and "error" in result:
                return
            self.review.open_task(self.pending_task, refresh=True)
            if self.pending_label not in {"识别资源", "整合包翻译", "继续翻译", "排除资源", "恢复资源"}:
                self.workspace.set_stage("proofreading")
            self.switchTo(self.workspace)

    def open_path(self, path):
        path = Path(path)
        if not path.exists():
            self.notify("文件尚未生成：" + str(path), warning=True)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def closeEvent(self, event):
        if self.runner.stopper.state() != QProcess.ProcessState.NotRunning:
            event.ignore()
            return
        if self.review.loaders or self.rules.loader:
            self.notify("任务或术语正在读取，请读取完成后退出", warning=True)
            event.ignore()
            return
        if self.runner.busy:
            message = ("暂停后保留已下载内容，下次激活本地接口时继续下载。" if self.pending_label == "模型下载" else
                       "暂停后保留已提交条目，下次可打开任务继续翻译。")
            dialog = MessageBox("操作仍在运行", message, self)
            dialog.yesButton.setText("暂停并退出")
            dialog.cancelButton.setText("继续运行")
            if dialog.exec():
                self.closing = True
                self.runner.cancel()
            event.ignore()
            return
        if not self.review.discard_changes():
            event.ignore()
            return
        event.accept()
