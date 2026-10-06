# [Module: desktop.review] [Status: 已完成] [Brief: 检查点浏览、搜索筛选、人工审核、续跑及补丁导出]
from dataclasses import replace
from pathlib import Path

from PyQt6.QtCore import QSignalBlocker, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QHeaderView, QSplitter
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    MessageBox,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SearchLineEdit,
    SpinBox,
    TableView,
    TextEdit,
)

from ....application.tasks.jobs import Job
from ....application.tasks.requests import PatchOptions, polish_job, review_job, task_job
from ....application.tasks.store import entry_hints, task_counts
from ....core.translation.polishing import DEFAULT_POLISH_PROMPT
from ....paths import migrated_path
from ...components.forms import FormLayout, Page, PathPicker
from ...process import TaskLoader
from .entry_model import EntryFilter, EntryModel
from .polish_dialog import PolishResultsDialog


class ReviewPage(Page):
    taskLoaded = pyqtSignal(object, str)

    def __init__(self, window):
        super().__init__("review", "校润", "检查译文、修改用语和格式，保存后重新导出补丁；可打开历史任务续跑。", window, heading=False)
        self.window = window
        self.scan = None
        self.task_path = ""
        self.current_entry = None
        self.loading = False
        self._selection_guard = False
        self.loaders = []
        self.load_generation = 0
        self.queued_polish_preview = None
        self.polish_dialog = None
        task = self.section("任务目录")
        self.task_card = task.parentWidget()
        self.compact_task = CardWidget(self.content)
        compact = QHBoxLayout(self.compact_task)
        compact.setContentsMargins(18, 14, 18, 14)
        self.compact_counts = BodyLabel("", self.compact_task)
        self.compact_counts.setWordWrap(True)
        compact.addWidget(self.compact_counts, 1)
        change = PushButton("切换任务", self.compact_task)
        change.clicked.connect(self.show_task_picker)
        compact.addWidget(change)
        self.body.insertWidget(0, self.compact_task)
        self.compact_task.hide()
        row = QHBoxLayout()
        self.path = PathPicker("包含 state.sqlite3 或 snapshot.json 的目录")
        self.load = PushButton("打开任务")
        self.load.clicked.connect(lambda: self.open_task(self.path.text()))
        row.addWidget(self.path, 1)
        row.addWidget(self.load)
        task.addLayout(row)
        self.recent = ComboBox()
        self.update_recent()
        self.recent.currentIndexChanged.connect(self.choose_recent)
        task.addWidget(self.recent)
        self.counts = BodyLabel("尚未打开任务")
        self.counts.setWordWrap(True)
        task.addWidget(self.counts)

        entries = self.section("译文列表")
        row = QHBoxLayout()
        self.search = SearchLineEdit()
        self.search.setPlaceholderText("搜索文件、语言键、原文或译文")
        self.filter = ComboBox()
        self.filter.addItems(["全部条目", "未翻译（含失败）", "失败", "已翻译", "已复用", "已审核", "修润失败"])
        row.addWidget(self.search, 1)
        row.addWidget(self.filter)
        entries.addLayout(row)
        self.model = EntryModel(self)
        self.proxy = EntryFilter(self)
        self.proxy.setSourceModel(self.model)
        self.table = TableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(TableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(TableView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(TableView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setMinimumHeight(290)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 90)
        self.table.selectionModel().currentRowChanged.connect(self.select_entry)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self.update_polish_actions())
        self.search.textChanged.connect(self.apply_filter)
        self.filter.currentIndexChanged.connect(self.apply_filter)
        entries.addWidget(self.table)

        editor = self.section("人工校润")
        editor.setContentsMargins(14, 14, 14, 14)
        editor.setSpacing(8)
        self.location = BodyLabel("选择一条文本")
        self.location.setWordWrap(True)
        self.location.setMaximumHeight(48)
        editor.addWidget(self.location)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.source = TextEdit()
        self.source.setReadOnly(True)
        self.source.setPlaceholderText("原文")
        self.translation = TextEdit()
        self.translation.setPlaceholderText("输入或修改译文")
        self.translation.setMinimumHeight(150)
        splitter.addWidget(self.source)
        splitter.addWidget(self.translation)
        editor.addWidget(splitter)
        self.hints = BodyLabel("")
        self.hints.setWordWrap(True)
        editor.addWidget(self.hints)
        self.save = PrimaryPushButton("保存为已审核")
        self.save.clicked.connect(self.save_entry)
        self.restore_polish = PushButton("载入修润前译文")
        self.restore_polish.clicked.connect(self.restore_previous_polish)
        row = QHBoxLayout()
        row.addWidget(self.save)
        row.addWidget(self.restore_polish)
        editor.addLayout(row)
        # Keep text selection and editing together in the proofreading stage.
        editor_card = editor.parentWidget()
        self.body.removeWidget(editor_card)
        entries.removeWidget(self.table)
        proof_splitter = QSplitter(Qt.Orientation.Horizontal)
        proof_splitter.addWidget(self.table)
        proof_splitter.addWidget(editor_card)
        proof_splitter.setStretchFactor(0, 3)
        proof_splitter.setStretchFactor(1, 2)
        proof_splitter.setSizes([480, 320])
        entries.addWidget(proof_splitter)
        splitter.setOrientation(Qt.Orientation.Vertical)
        self.source.setFixedHeight(75)
        self.translation.setFixedHeight(100)
        splitter.setFixedHeight(190)
        splitter.setSizes([80, 110])

        polishing = self.section("API 批量修润", "Ctrl / Shift 可多选。结果先在弹窗中对照、修复和选择接受，确认前保留原译文与状态。未翻译项也可补译。")
        self.polish_api = ComboBox()
        self.polish_mode = ComboBox()
        self.polish_mode.addItem("纠错修正", userData="correct")
        self.polish_mode.addItem("表达润色", userData="polish")
        form = FormLayout()
        form.addRow("修润 API 接口", self.polish_api)
        form.addRow("处理模式", self.polish_mode)
        polishing.addLayout(form)
        self.polish_prompt = TextEdit()
        self.polish_prompt.setMinimumHeight(110)
        self.polish_prompt.setMaximumHeight(180)
        self.polish_prompt.setPlainText(window.settings.polish_prompt)
        self.polish_prompt.setPlaceholderText("专用修润提示词；可使用 {source_language}、{target_language}、{source}、{translation}、{context}、{glossary}")
        polishing.addWidget(self.polish_prompt)
        self.polish_hint = BodyLabel("")
        self.polish_hint.setWordWrap(True)
        polishing.addWidget(self.polish_hint)
        row = QHBoxLayout()
        self.polish_selected = PrimaryPushButton("修润所选条目")
        self.polish_all = PushButton("修润全部条目")
        self.select_all = PushButton("全选当前列表")
        self.polish_stop = PushButton("暂停修润")
        self.polish_selected.clicked.connect(lambda: self.start_polishing(False))
        self.polish_all.clicked.connect(lambda: self.start_polishing(True))
        self.select_all.clicked.connect(self.table.selectAll)
        self.polish_stop.clicked.connect(window.runner.cancel)
        for button in (self.select_all, self.polish_selected, self.polish_all, self.polish_stop):
            row.addWidget(button)
        polishing.addLayout(row)
        row = QHBoxLayout()
        self.polish_save = PushButton("保存修润配置")
        self.polish_reset = PushButton("恢复默认修润提示词")
        self.polish_configure = PushButton("配置 API 接口")
        self.polish_preview = PushButton("查看修润结果")
        self.polish_save.clicked.connect(self.save_polish_settings)
        self.polish_reset.clicked.connect(lambda: self.polish_prompt.setPlainText(DEFAULT_POLISH_PROMPT))
        self.polish_configure.clicked.connect(lambda: window.switchTo(window.api))
        self.polish_preview.clicked.connect(lambda: self.show_polish_results())
        for button in (self.polish_save, self.polish_reset, self.polish_configure, self.polish_preview):
            row.addWidget(button)
        polishing.addLayout(row)
        self.polish_api.currentIndexChanged.connect(lambda *_: self.update_polish_actions())
        self.refresh_polish_profiles()

        actions = self.section("续跑与补丁", "续跑保留任务的接口、提示词、术语、禁翻和格式策略；密钥及推理解释器使用当前设置。")
        self.override = CheckBox("续跑时使用当前模型设置（包括保留符宽松选项）")
        self.partial = CheckBox("允许存在未处理项")
        self.replace = CheckBox("允许替换已有 FTBQ 目标语言文件")
        self.i18n = CheckBox("加入对应版本 I18nUpdateMod")
        self.override.setChecked(True)
        self.partial.setChecked(window.settings.output_allow_partial)
        self.replace.setChecked(window.settings.output_replace_locale)
        self.i18n.setChecked(True)
        self.offline = CheckBox("离线模式")
        self.jar = PathPicker("可选；使用本地已有的 I18nUpdate 模组", "file", "模组 (*.jar)")
        self.limit = SpinBox()
        self.limit.setRange(0, 1000000)
        self.limit.setSpecialValueText("全部待翻译条目")
        form = FormLayout()
        form.addRow("翻译条数", self.limit)
        actions.addLayout(form)
        # for widget in (self.override, self.partial, self.replace, self.i18n, self.offline, self.jar):
        for widget in (self.override, self.partial, self.replace, self.i18n, self.jar):
            actions.addWidget(widget)
        row = QHBoxLayout()
        self.resume = PrimaryPushButton("继续翻译")
        self.export = PushButton("导出补丁")
        self.patch_folder = PushButton("打开补丁目录")
        self.report = PushButton("打开审核报告")
        self.resume.clicked.connect(lambda: self.start("resume"))
        self.export.clicked.connect(lambda: self.start("export"))
        self.patch_folder.clicked.connect(lambda: window.open_path(Path(self.task_path) / "patch"))
        self.report.clicked.connect(lambda: window.open_path(Path(self.task_path) / "report.html"))
        for button in (self.resume, self.export, self.patch_folder, self.report):
            row.addWidget(button)
        actions.addLayout(row)
        self.progress = ProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        actions.addWidget(self.progress)
        self.body.addStretch()
        self.set_busy(False)

    def update_recent(self):
        self.recent.blockSignals(True)
        self.recent.clear()
        self.recent.addItem("最近任务…")
        for path in self.window.recent_tasks:
            self.recent.addItem(path)
        self.recent.blockSignals(False)

    def refresh_polish_profiles(self):
        selected = self.polish_api.currentData() or self.window.settings.polish_api
        blocker = QSignalBlocker(self.polish_api)
        self.polish_api.clear()
        self.polish_api.addItem("请选择已配置的 API", userData="")
        for profile in self.window.settings.api_profiles:
            if profile.get("prompt_mode", "custom") == "custom":
                self.polish_api.addItem(f"{profile['name']} · {profile.get('model') or '未填写模型'}", userData=profile["id"])
        self.polish_api.setCurrentIndex(max(0, self.polish_api.findData(selected)))
        del blocker
        self.update_polish_actions()

    def update_polish_actions(self):
        if not hasattr(self, "polish_selected"):
            return
        active = not self.window.runner.busy and not self.loading
        count = len(self.table.selectionModel().selectedRows())
        ready = active and self.resumable() and bool(self.polish_api.currentData())
        self.polish_selected.setEnabled(ready and count > 0)
        self.polish_all.setEnabled(ready and self.scan is not None and bool(self.scan.entries))
        self.select_all.setEnabled(active and self.proxy.rowCount() > 0)
        self.polish_stop.setEnabled(self.window.runner.busy and self.window.pending_label == "API 批量修润")
        self.polish_preview.setEnabled(active and self.scan is not None and any(
            run.get("preview_only") and run.get("results") for run in self.scan.metadata.get("polish_runs", [])))
        self.polish_hint.setText(
            f"已选 {count} 条 · 全部修润处理整个任务，不受搜索筛选限制。" if self.polish_api.currentData() else
            "请先配置并选择 API 接口。修润使用独立提示词；HY-MT-2 固定模板模式的接口不参与修润。")

    def save_polish_settings(self):
        try:
            self.window.save_settings(replace(self.window.settings, polish_api=self.polish_api.currentData() or "",
                                              polish_prompt=self.polish_prompt.toPlainText()))
            self.polish_prompt.document().setModified(False)
            return True
        except ValueError as exc:
            self.window.notify(str(exc), error=True)
            return False

    def start_polishing(self, all_entries=False):
        if not self.resumable() or self.scan is None or self.window.runner.busy or self.loading:
            return
        if not self.polish_api.currentData():
            self.window.notify("请先配置并选择修润 API 接口", error=True)
            return
        entry_ids = None if all_entries else [self.model.entries[self.proxy.mapToSource(index).row()].id
                                             for index in self.table.selectionModel().selectedRows()]
        if entry_ids == []:
            self.window.notify("请先选中需要修润的条目", warning=True)
            return
        if self.save_polish_settings():
            self.window.run_job(lambda: polish_job(self.task_path, entry_ids, self.window.settings,
                                                   self.polish_mode.currentData()), "API 批量修润", self.task_path)

    def previous_polish_translation(self):
        if self.scan is not None and self.current_entry is not None:
            for run in reversed(self.scan.metadata.get("polish_runs", [])):
                if run.get("preview_only") and not run.get("results", {}).get(self.current_entry.id, {}).get("accepted"):
                    continue
                if run.get("results", {}).get(self.current_entry.id, {}).get("error"):
                    continue
                previous = run.get("previous", {}).get(self.current_entry.id)
                if previous is not None:
                    return previous.get("translation")
        return None

    def show_polish_results(self, run_id=None):
        if self.scan is None or self.loading or self.window.runner.busy or not self.discard_changes():
            return
        run = next((run for run in reversed(self.scan.metadata.get("polish_runs", []))
                    if run.get("preview_only") and (run_id is None or run.get("id") == run_id)), None)
        if run is None:
            return
        dialog = PolishResultsDialog(self.scan, run, self.window)
        self.polish_dialog = dialog
        try:
            if dialog.exec() and dialog.updates:
                self.window.run_job(lambda: Job("polish-accept", output=self.task_path, polish_run_id=run["id"],
                                               polish_updates=dialog.updates), "接受修润结果", self.task_path)
        finally:
            self.polish_dialog = None
            dialog.deleteLater()

    def restore_previous_polish(self):
        previous = self.previous_polish_translation()
        if previous is not None and self.discard_changes():
            self.translation.setPlainText(previous)
            self.translation.document().setModified(True)

    def choose_recent(self, index):
        if index > 0:
            self.open_task(self.recent.itemText(index))

    def discard_changes(self):
        if not self.translation.document().isModified():
            return True
        dialog = MessageBox("译文尚未保存", "切换后会放弃当前编辑的译文。", self.window)
        dialog.yesButton.setText("放弃修改")
        dialog.cancelButton.setText("继续编辑")
        if dialog.exec():
            self.translation.document().setModified(False)
            return True
        return False

    def open_task(self, path, refresh=False):
        path = migrated_path(path)
        if not path or self.window.runner.busy:
            return
        if not refresh and not self.discard_changes():
            return
        self.load_generation += 1
        generation = self.load_generation
        self.loading = True
        self.set_busy(False)
        self.counts.setText("正在读取任务检查点…")
        loader = TaskLoader(path, self)
        self.loaders.append(loader)
        loader.loaded.connect(lambda scan: self.loaded(scan, path, generation))
        loader.failed.connect(lambda error: self.load_failed(error, generation))
        loader.finished.connect(lambda: self.release_loader(loader))
        loader.start()

    def release_loader(self, loader):
        self.loaders.remove(loader)
        loader.deleteLater()

    def load_failed(self, error, generation):
        if generation != self.load_generation:
            return
        self.loading = False
        self.counts.setText("读取任务失败：" + error)
        self.set_busy(False)
        self.window.notify(error, error=True)

    def loaded(self, scan, path, generation):
        if generation != self.load_generation:
            return
        selected_id = self.current_entry.id if self.current_entry else None
        self.scan, self.task_path = scan, str(Path(path).resolve())
        if Path(self.task_path).is_file():
            self.task_path = str(Path(self.task_path).parent)
        self.path.setText(self.task_path)
        self.current_entry = None
        self._selection_guard = True
        self.model.replace(scan.entries)
        from ....core.pack.extraction import resource_exclusions
        self.model.set_excluded_documents(resource_exclusions(scan))
        errors = {}
        for run in scan.metadata.get("polish_runs", []):
            if run.get("preview_only"):
                for key, proposal in run.get("results", {}).items():
                    errors[key] = proposal.get("error", "") if not proposal.get("accepted") else ""
        self.model.polish_errors = errors
        self.proxy.set_polish_failures({key for key, error in errors.items() if error})
        self._selection_guard = False
        self.source.clear()
        self.translation.clear()
        self.translation.document().setModified(False)
        self.hints.setText("")
        count = task_counts(scan)
        model = scan.metadata.get("model_config", {})
        policy = "宽松兜底" if model.get("allow_missing_placeholders") else "严格保留符"
        engine = (model.get("api_model", "") if model.get("engine") == "api" else "HY-MT-2 GGUF") if model else "尚未开始翻译"
        usage = scan.metadata.get("api_usage", {})
        tokens = f" · API token {usage.get('input_tokens', 0) + usage.get('output_tokens', 0)}" if usage else ""
        self.counts.setText(f"{scan.pack_id} · {count['total']} 条 · 已完成 {count['complete']} · "
                            f"待翻译 {count['remaining']} · 失败 {count.get('failed', 0)} · {policy} · {engine}{tokens}")
        self.compact_counts.setText(self.counts.text())
        self.compact_counts.setToolTip(self.task_path)
        self.compact_task.show()
        self.task_card.hide()
        self.progress.setRange(0, max(count["total"], 1))
        self.progress.setValue(count["complete"])
        self.loading = False
        self.window.remember_task(self.task_path)
        self.set_busy(False)
        if selected_id:
            for row, entry in enumerate(scan.entries):
                if entry.id == selected_id:
                    index = self.proxy.mapFromSource(self.model.index(row, 0))
                    if index.isValid():
                        self.table.setCurrentIndex(index)
                    break

        self.taskLoaded.emit(scan, self.task_path)
        if self.queued_polish_preview and self.queued_polish_preview[0] == self.task_path:
            _, run_id = self.queued_polish_preview
            self.queued_polish_preview = None
            QTimer.singleShot(0, lambda: self.show_polish_results(run_id))

    def show_task_picker(self):
        self.task_card.show()
        self.compact_task.hide()

    def apply_filter(self):
        if not self.discard_changes():
            return
        self.proxy.set_query(self.search.text(),
                             ["all", "untranslated", "failed", "translated", "reused", "reviewed", "polish_failed"][self.filter.currentIndex()])

    def select_entry(self, current, previous):
        if self._selection_guard:
            return
        if not self.discard_changes():
            self._selection_guard = True
            self.table.setCurrentIndex(previous)
            self._selection_guard = False
            return
        if not current.isValid():
            self.current_entry = None
            self.save.setEnabled(False)
            self.restore_polish.setEnabled(False)
            return
        index = self.proxy.mapToSource(current)
        self.current_entry = self.model.entries[index.row()]
        entry = self.current_entry
        self.location.setText(entry.document + " · " + entry.semantic_key + "\n" + entry.context)
        self.location.setToolTip(self.location.text())
        self.source.setPlainText(entry.source)
        self.translation.setPlainText(entry.translation or "")
        self.translation.document().setModified(False)
        self.hints.setText(entry_hints(entry) or "暂无质量提醒")
        self.save.setEnabled(not self.window.runner.busy and self.resumable())
        self.restore_polish.setEnabled(not self.window.runner.busy and self.previous_polish_translation() is not None)

    def resumable(self):
        return bool(self.task_path and (Path(self.task_path) / "state.sqlite3").is_file())

    def save_entry(self):
        if self.current_entry is None:
            return
        self.window.run_job(lambda: review_job(self.task_path, self.current_entry.id,
                                                   self.translation.toPlainText()), "保存审核", self.task_path)

    def start(self, action):
        if not self.discard_changes():
            return
        if action == "resume":
            self.window.workspace.set_stage("translation")
        patch = PatchOptions(self.partial.isChecked(), self.replace.isChecked(), self.i18n.isChecked(),
                             self.jar.text(), self.offline.isChecked())
        self.window.run_job(lambda: task_job(action, self.task_path, self.window.settings, patch,
                                                 self.limit.value(), self.override.isChecked() or not self.scan.metadata.get("model_config")),
                            "继续翻译" if action == "resume" else "导出补丁", self.task_path)

    def set_busy(self, busy):
        active = not busy and not self.loading
        self.load.setEnabled(active)
        self.recent.setEnabled(active)
        for button in (self.resume, self.export):
            button.setEnabled(active and self.resumable())
        self.save.setEnabled(active and self.current_entry is not None and self.resumable())
        self.restore_polish.setEnabled(active and self.previous_polish_translation() is not None)
        self.table.setEnabled(active)
        self.translation.setReadOnly(not active)
        for widget in (self.polish_api, self.polish_mode, self.polish_prompt, self.polish_save, self.polish_reset,
                       self.polish_configure):
            widget.setEnabled(active)
        self.update_polish_actions()
        self.patch_folder.setEnabled(bool(self.task_path))
        self.report.setEnabled(bool(self.task_path))

    def update_progress(self, payload):
        done, failed, remaining = (payload[key] for key in ("completed", "failed", "remaining"))
        self.progress.setRange(0, max(done + failed + remaining, 1))
        self.progress.setValue(done + failed)
        action = "生成候选" if payload.get("operation") == "polish" else "翻译"
        self.counts.setText(f"本次已{action} {done} · 失败 {failed} · 剩余 {remaining}")
        if payload.get("operation") == "polish" and payload.get("error"):
            self.polish_hint.setText("候选结果被拦截，可在预览中手动修复：" + payload["error"])
        self.compact_counts.setText(self.counts.text())
