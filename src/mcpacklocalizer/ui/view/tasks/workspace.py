# [Module: desktop.workspace] [Status: 已完成] [Brief: 整合包识别、翻译与校润工作流]
import json

from PyQt6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import CardWidget, FluentIcon, SegmentedWidget, TitleLabel, TransparentPushButton

from ....application.tasks.requests import PackRequest, PatchOptions, pack_job, task_job
from ....application.tasks.store import result_summary
from .recognition import RecognitionPage
from .translation import TranslationStagePage


class WorkspacePage(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.setObjectName("workspace")
        self.window = window
        self.task_path = ""
        self.task_scan = None
        self.current_stage = "recognition"
        box = QVBoxLayout(self)
        box.setContentsMargins(24, 24, 24, 20)
        box.setSpacing(14)
        box.addWidget(TitleLabel("整合包翻译", self))
        header = CardWidget(self)
        row = QHBoxLayout(header)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(10)
        back = TransparentPushButton(FluentIcon.RETURN, "识别目录", header)
        back.clicked.connect(lambda: self.set_stage("recognition"))
        row.addWidget(back)
        row.addStretch(1)
        self.steps = SegmentedWidget(header)
        self.steps.setFixedWidth(330)
        for key, title in (("recognition", "识别"), ("translation", "翻译"), ("proofreading", "校润")):
            self.steps.addItem(routeKey=key, text=title, onClick=lambda checked=False, key=key: self.set_stage(key))
        self.steps.setCurrentItem("recognition")
        row.addWidget(self.steps)
        row.addStretch(1)
        history = TransparentPushButton(FluentIcon.FOLDER, "打开任务", header)
        history.clicked.connect(self.open_task_picker)
        row.addWidget(history)
        self.export = TransparentPushButton(FluentIcon.SHARE, "导出补丁", header)
        self.export.clicked.connect(lambda: window.review.start("export"))
        self.export.setEnabled(False)
        row.addWidget(self.export)
        box.addWidget(header)
        self.stack = QStackedWidget(self)
        box.addWidget(self.stack, 1)
        self.recognition = RecognitionPage(self, window)
        self.translation = TranslationStagePage(self, window)
        self.proofreading = window.review
        self.proofreading.body.setContentsMargins(16, 12, 16, 18)
        self.pages = {"recognition": self.recognition, "translation": self.translation,
                      "proofreading": self.proofreading}
        for page in self.pages.values():
            self.stack.addWidget(page)
        for name in ("root", "output", "mode", "pack_id", "baseline", "cfpa", "offline", "version", "loader", "diff"):
            setattr(self, name, getattr(self.recognition, name))
        for name in ("engine", "partial", "replace", "i18n", "jar", "limit", "status", "progress", "stop", "logs"):
            setattr(self, name, getattr(self.translation, name))
        self.scan = self.extract = self.recognition.identify
        self.translate = self.translation.start
        window.review.taskLoaded.connect(self.bind_task)

    def set_stage(self, key):
        if key not in self.pages:
            return
        if self.current_stage == "proofreading" and key != "proofreading" and not self.window.review.discard_changes():
            self.steps.setCurrentItem(self.current_stage)
            return
        self.current_stage = key
        self.steps.setCurrentItem(key)
        self.stack.setCurrentWidget(self.pages[key])

    def invalidate_task(self):
        if self.task_path:
            self.recognition.new_output()
        self.task_path, self.task_scan = "", None
        self.recognition.clear_resources()
        self.translation.clear_task()
        self.export.setEnabled(False)

    def open_task_picker(self):
        self.set_stage("proofreading")
        self.window.review.show_task_picker()

    def bind_task(self, scan, path):
        self.task_scan, self.task_path = scan, path
        self.recognition.bind_scan(scan, path)
        self.translation.bind_scan(scan, path)
        self.set_busy(self.window.runner.busy)

    def refresh_languages(self):
        self.recognition.refresh_languages(self.task_scan)

    def patch_options(self):
        return PatchOptions(self.partial.isChecked(), self.replace.isChecked(), self.i18n.isChecked(),
                            self.jar.text(), self.offline.isChecked(), self.version.text().strip(),
                            "" if self.loader.currentIndex() == 0 else self.loader.currentText())

    def start(self, action):
        if action == "localize":
            return self.start_translation()
        if action == "extract" and self.task_path == self.output.text():
            self.recognition.new_output()
        request = PackRequest(self.root.text(), self.output.text(), self.pack_id.text().strip(), self.baseline.text(),
                              self.mode.selectedData() == ["mods"], self.offline.isChecked(), self.cfpa.text(),
                              self.version.text().strip(),
                              "" if self.loader.currentIndex() == 0 else self.loader.currentText(),
                              recognition_scope=self.mode.selectedData(),
                              translation_library=self.recognition.translation_library.text(),
                              reuse_policy=self.recognition.reuse_policy.currentData())
        labels = {"extract": "识别资源", "scan": "识别预览", "diff": "版本对比"}
        self.set_stage("recognition")
        self.window.run_job(lambda: pack_job(action, request, self.window.settings, self.patch_options()),
                            labels[action], request.output if action == "extract" else "")

    def start_translation(self):
        if not self.task_path or self.task_scan is None:
            self.window.notify("请先识别资源或打开已有任务", warning=True)
            return
        self.set_stage("translation")
        saved = self.task_scan.metadata.get("model_config", {})
        use_current = self.translation.override.isChecked() or not any(key in saved for key in ("engine", "model"))
        self.window.run_job(lambda: task_job("resume", self.task_path, self.window.settings, self.patch_options(),
                                            self.limit.value(), use_current), "整合包翻译", self.task_path)

    def set_busy(self, busy):
        self.recognition.set_busy(busy)
        self.translation.set_busy(busy)
        self.export.setEnabled(not busy and bool(self.task_path) and self.window.review.resumable() and not self.window.review.loading)

    def update_progress(self, payload):
        self.translation.update_progress(payload)

    def show_result(self, result, cancelled=False):
        message = "操作已暂停；已保存条目可续跑" if cancelled else result_summary(result)
        self.status.setText(message)
        if self.window.pending_label in {"识别资源", "识别预览", "版本对比"}:
            self.recognition.status.setText(message)
        self.window.append_task_log(json.dumps(result, ensure_ascii=False, indent=2))
