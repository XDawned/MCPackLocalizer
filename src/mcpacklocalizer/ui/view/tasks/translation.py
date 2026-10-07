# [Module: desktop.translation] [Status: 已完成] [Brief: 检查点翻译、进度与完整日志入口]
from dataclasses import replace

from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout
from qfluentwidgets import (
    BodyLabel,
    CheckBox,
    ComboBox,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SpinBox,
    StrongBodyLabel,
    TextEdit,
)

from ....application.tasks.store import task_counts
from ....core.translation.locales import language_name
from ...components.forms import FormLayout, Page, PathPicker


class TranslationStagePage(Page):
    def __init__(self, workflow, window):
        super().__init__("taskTranslation", "翻译", "使用识别阶段保存的内容翻译；暂停后继续处理未完成条目。", workflow, heading=False)
        self.body.setContentsMargins(16, 12, 16, 18)
        self.workflow, self.window = workflow, window
        summary = self.section("当前任务")
        self.task = BodyLabel("请先识别资源，或打开已有任务")
        self.task.setWordWrap(True)
        summary.addWidget(self.task)
        self.engine = BodyLabel("当前翻译引擎：" + window.settings.engine_label())
        self.engine.setWordWrap(True)
        summary.addWidget(self.engine)
        self.language = BodyLabel("")
        self.language.setWordWrap(True)
        summary.addWidget(self.language)
        self.script_api = ComboBox()
        self.script_api.setMinimumWidth(280)
        form = FormLayout()
        form.addRow("KubeJS 脚本大模型", self.script_api)
        summary.addLayout(form)
        self.script_hint = BodyLabel("脚本文本使用独立 API 接口；只替换文字，保留代码结构。")
        self.script_hint.setWordWrap(True)
        summary.addWidget(self.script_hint)
        self.refresh_script_profiles()
        self.script_api.currentIndexChanged.connect(self.select_script_profile)
        grid = QGridLayout()
        self.metrics = {}
        for column, (key, title) in enumerate((("total", "识别条目"), ("complete", "已完成"),
                                               ("remaining", "待翻译"), ("failed", "失败"))):
            grid.addWidget(BodyLabel(title), 0, column)
            label = StrongBodyLabel("0")
            grid.addWidget(label, 1, column)
            self.metrics[key] = label
        summary.addLayout(grid)
        activity = self.section("翻译进度")
        self.status = BodyLabel("就绪 · 识别阶段无需加载模型")
        self.status.setWordWrap(True)
        activity.addWidget(self.status)
        self.progress = ProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        activity.addWidget(self.progress)
        row = QHBoxLayout()
        self.start = PrimaryPushButton("开始翻译")
        self.start.clicked.connect(workflow.start_translation)
        self.start.setEnabled(False)
        self.stop = PushButton("暂停翻译")
        self.stop.clicked.connect(window.runner.cancel)
        self.stop.setEnabled(False)
        self.proof = PushButton("进入校润")
        self.proof.clicked.connect(lambda: workflow.set_stage("proofreading"))
        self.proof.setEnabled(False)
        for button in (self.start, self.stop, self.proof):
            row.addWidget(button)
        self.open_logs = PushButton("查看运行日志")
        self.open_logs.clicked.connect(lambda: window.switchTo(window.logs_page))
        row.addWidget(self.open_logs)
        activity.addLayout(row)
        self.logs = TextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMinimumHeight(150)
        self.logs.document().setMaximumBlockCount(1500)
        activity.addWidget(self.logs)
        options = self.section("本次翻译与补丁", "输出独立 patch/，校润后可重新导出；不会原地修改游戏目录。")
        self.override = CheckBox("续跑时使用当前接口与翻译配置（任务语言保持不变）")
        self.partial = CheckBox("允许存在未处理项（失败项使用原文）")
        self.replace = CheckBox("允许替换已有 FTBQ 目标语言文件")
        self.i18n = CheckBox("加入对应版本 I18nUpdateMod")
        self.partial.setChecked(window.settings.output_allow_partial)
        self.replace.setChecked(window.settings.output_replace_locale)
        self.i18n.setChecked(window.settings.output_include_i18n)
        self.jar = PathPicker("可选；本地 I18nUpdate 模组", "file", "模组 (*.jar)")
        self.limit = SpinBox()
        self.limit.setRange(0, 1000000)
        self.limit.setSpecialValueText("全部待翻译条目")
        for widget in (self.override, self.partial, self.replace, self.i18n, self.jar):
            options.addWidget(widget)
        form = FormLayout()
        form.addRow("本次条数", self.limit)
        options.addLayout(form)
        self.body.addStretch()

    def bind_scan(self, scan, path):
        count = task_counts(scan)
        self.task.setText(scan.pack_id + "\n" + path)
        script_count = sum(bool(entry.script) for entry in scan.entries)
        saved = scan.metadata.get("script_model_config", {})
        self.script_hint.setText(f"{script_count} 条脚本文本 · " + (
            f"续跑保留已保存的接口 {saved.get('api_model', '')}；更换接口将使用当前配置。" if saved else
            "请选择已配置的大模型 API；未配置时仍可识别和校润。"))
        self.language.setText(f"{language_name(scan.source_locale)}（{scan.source_locale}） → {language_name(scan.target_locale)}（{scan.target_locale}）")
        for key, label in self.metrics.items():
            label.setText(str(count.get(key, 0)))
        self.progress.setRange(0, max(1, count["total"]))
        self.progress.setValue(count["complete"])
        self.start.setText("继续翻译" if count["complete"] else "开始翻译")
        self.set_busy(self.window.runner.busy)

    def clear_task(self):
        self.task.setText("请先识别资源，或打开已有任务")
        self.language.clear()
        for label in self.metrics.values():
            label.setText("0")
        self.progress.setValue(0)
        self.start.setEnabled(False)
        self.proof.setEnabled(False)

    def set_busy(self, busy):
        self.script_api.setEnabled(not busy)
        ready = bool(self.workflow.task_path) and not self.window.review.loading
        pending = self.workflow.task_scan and any(entry.translation is None for entry in self.workflow.task_scan.entries)
        self.start.setEnabled(not busy and ready and self.window.review.resumable() and bool(pending))
        self.proof.setEnabled(not busy and ready)
        self.stop.setEnabled(busy)
        if busy:
            self.progress.setRange(0, 0)
        elif self.progress.maximum() == 0:
            self.progress.setRange(0, 100)

    def update_progress(self, payload):
        done, failed, remaining = (payload[key] for key in ("completed", "failed", "remaining"))
        self.progress.setRange(0, max(1, done + failed + remaining))
        self.progress.setValue(done + failed)
        self.status.setText(f"本次已翻译 {done} · 失败 {failed} · 剩余 {remaining}")
        for key, value in (("complete", done), ("remaining", remaining), ("failed", failed)):
            self.metrics[key].setText(str(value))
        if usage := payload.get("api_usage"):
            self.status.setText(self.status.text() + f" · 请求 {usage['requests']} · 输入 {usage['input_tokens']} / 输出 {usage['output_tokens']} token")
        if hints := payload.get("quality_warnings"):
            self.window.append_task_log(f"条目 {payload['entry_id']}：" + "；".join(h["message"] for h in hints))

    def refresh_script_profiles(self):
        blocker = QSignalBlocker(self.script_api)
        self.script_api.clear()
        self.script_api.addItem("未选择（识别无需模型）", userData="")
        for profile in self.window.settings.api_profiles:
            if profile.get("interface_type", "llm" if profile.get("prompt_mode", "custom") == "custom" else "translation") == "llm":
                self.script_api.addItem(f"{profile['name']} · {profile.get('model') or '未选择模型'}", userData=profile["id"])
        self.script_api.setCurrentIndex(max(0, self.script_api.findData(self.window.settings.script_api)))
        del blocker

    def select_script_profile(self):
        profile_id = self.script_api.currentData() or ""
        self.window.save_settings(replace(self.window.settings, script_api=profile_id))
        if self.workflow.task_scan and self.workflow.task_scan.metadata.get("script_model_config"):
            self.override.setChecked(True)
