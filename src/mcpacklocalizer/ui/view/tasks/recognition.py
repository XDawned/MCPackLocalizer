# [Module: ui.tasks.recognition] [Status: 已完成] [Brief: 识别文件树、语言 key 警示与可持久化资源排除]
from PyQt6.QtCore import QSignalBlocker, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QHBoxLayout, QHeaderView, QSplitter, QTreeWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import (
    Action,
    BodyLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    RoundMenu,
    SearchLineEdit,
    StrongBodyLabel,
    TableView,
    TextEdit,
    TreeWidget,
)
from qfluentwidgets import FluentIcon as FIF

from ....application.tasks.jobs import Job
from ....application.tasks.requests import new_task_output, output_for
from ....application.tasks.resources import resource_groups
from ....application.tasks.store import reuse_summary, task_counts
from ....core.mods.combined import mod_scan
from ....core.pack.extraction import resource_exclusions
from ....core.patchouli.diagnostics import resource_warnings
from ....core.translation.locales import language_name
from ...components.forms import FormLayout, Page, PathPicker
from ...components.scope_selector import ScopeSelector
from .entry_model import EntryFilter, EntryModel


class RecognitionPage(QWidget):
    def __init__(self, workflow, window):
        super().__init__(workflow)
        self.workflow, self.window = workflow, window
        self.setObjectName("recognition")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        layout.addWidget(splitter)
        navigation = CardWidget(splitter)
        box = QVBoxLayout(navigation)
        box.setContentsMargins(16, 18, 16, 18)
        box.addWidget(StrongBodyLabel("识别资源", navigation))
        self.resource_count = BodyLabel("选择实例目录后开始识别", navigation)
        self.resource_count.setWordWrap(True)
        box.addWidget(self.resource_count)
        self.tree = TreeWidget(navigation)
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(235)
        self.tree.setIndentation(12)
        self.tree.currentItemChanged.connect(self.select_resource)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_resource_menu)
        box.addWidget(self.tree, 1)
        hint = BodyLabel("黄色提示图标表示需检查的文件。右键文件或目录可排除、恢复；已排除资源不参与翻译和导出。", navigation)
        hint.setWordWrap(True)
        box.addWidget(hint)
        splitter.addWidget(navigation)
        page = Page("recognitionContent", "识别", "从目录提取待翻译内容，不调用模型；结果自动保存为可续跑的任务。", splitter, heading=False)
        page.body.setContentsMargins(16, 12, 4, 18)
        splitter.addWidget(page)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 650])
        inputs = page.section("游戏实例与任务", "识别不调用模型；结果保存为可续跑的任务。")
        self.input_card = inputs.parentWidget()
        self.input_summary = CardWidget(page.content)
        summary = QHBoxLayout(self.input_summary)
        summary.setContentsMargins(18, 14, 18, 14)
        self.summary_text = BodyLabel("", self.input_summary)
        self.summary_text.setWordWrap(True)
        summary.addWidget(self.summary_text, 1)
        change = PushButton("识别选项", self.input_summary)
        change.clicked.connect(lambda: self.input_card.setVisible(not self.input_card.isVisible()))
        summary.addWidget(change)
        self.summary_next = PrimaryPushButton("进入翻译", self.input_summary)
        self.summary_next.clicked.connect(lambda: workflow.set_stage("translation"))
        summary.addWidget(self.summary_next)
        page.body.insertWidget(2, self.input_summary)
        self.input_summary.hide()
        form = FormLayout()
        self.root = PathPicker("包含 config、kubejs、mods 的实例目录")
        self.root.setText(window.preferences.value("last_root", ""))
        self.output = PathPicker("新的空任务目录，位于游戏实例之外")
        self.new_output()
        self.mode = ScopeSelector()
        form.addRow("游戏实例", self.root)
        form.addRow("任务目录", self.output)
        form.addRow("识别范围", self.mode)
        inputs.addLayout(form)
        self.output_hint = BodyLabel("任务结果保存到实例外的独立目录，识别不会修改游戏文件。")
        self.output_hint.setWordWrap(True)
        inputs.addWidget(self.output_hint)
        self.suggested_output = PushButton("使用建议任务目录")
        self.suggested_output.clicked.connect(self.new_output)
        self.suggested_output.hide()
        inputs.addWidget(self.suggested_output)
        self.languages = BodyLabel()
        self.languages.setWordWrap(True)
        inputs.addWidget(self.languages)
        row = QHBoxLayout()
        self.identify = PrimaryPushButton("开始识别")
        self.identify.clicked.connect(lambda: workflow.start("extract"))
        self.next = PushButton("进入翻译")
        self.next.clicked.connect(lambda: workflow.set_stage("translation"))
        self.next.setEnabled(False)
        self.more = PushButton("识别选项")
        for button in (self.identify, self.next, self.more):
            row.addWidget(button)
        inputs.addLayout(row)
        self.advanced = QWidget()
        advanced = QVBoxLayout(self.advanced)
        advanced.setContentsMargins(0, 8, 0, 0)
        form = FormLayout()
        self.pack_id = LineEdit()
        self.pack_id.setPlaceholderText("可选；留空时沿用上一版本标识")
        self.baseline = PathPicker("可选；上一版本任务或 snapshot.json")
        self.baseline_file = PushButton("选择快照文件")
        self.baseline_file.clicked.connect(self.choose_baseline_file)
        self.translation_library = PathPicker("留空使用默认共享译库", "file", "SQLite 译库 (*.sqlite3 *.db);;所有文件 (*)")
        self.reuse_policy = ComboBox()
        for label, policy in (("只复用已审核译文（默认）", "reviewed"), ("复用已审核译文和模型草稿", "all"), ("关闭共享复用", "off")):
            self.reuse_policy.addItem(label, userData=policy)
        self.cfpa = PathPicker("可选；本地 CFPA 汉化包", "file", "资源包 (*.zip)")
        self.version = LineEdit()
        self.version.setPlaceholderText("自动识别；例如 1.21.1")
        self.loader = ComboBox()
        self.loader.addItems(["自动识别", "fabric", "forge", "neoforge", "quilt"])
        self.offline = CheckBox("离线模式（模组识别 / I18n 下载）")
        for title, widget in (("整合包标识", self.pack_id), ("上一版本", self.baseline),
                              ("", self.baseline_file), ("模组共享译库", self.translation_library),
                              ("模组复用策略", self.reuse_policy),
                              ("本地汉化包", self.cfpa), ("MC 版本", self.version), ("加载器", self.loader)):
            form.addRow(title, widget)
        advanced.addLayout(form)
        hint = BodyLabel("版本升级请选择旧任务和新的空输出目录。跨整合包的模组复用需勾选“模组缺失汉化”；模型译文保存为草稿，可选择包含草稿的策略。")
        hint.setWordWrap(True)
        advanced.addWidget(hint)
        advanced.addWidget(self.offline)
        row = QHBoxLayout()
        self.diff = PushButton("对比上一版本")
        self.diff.clicked.connect(lambda: workflow.start("diff"))
        new = PushButton("使用新任务目录")
        new.clicked.connect(self.new_output)
        row.addWidget(self.diff)
        row.addWidget(new)
        advanced.addLayout(row)
        inputs.addWidget(self.advanced)
        self.advanced.hide()
        self.more.clicked.connect(lambda: self.advanced.setVisible(not self.advanced.isVisible()))
        self.root.textChanged.connect(self.root_changed)
        self.output.textChanged.connect(self.check_output)
        self.mode.selectionChanged.connect(self.inputs_changed)
        for widget in (self.pack_id, self.baseline, self.translation_library):
            widget.textChanged.connect(self.inputs_changed)
        self.reuse_policy.currentIndexChanged.connect(self.inputs_changed)
        preview = page.section("待翻译内容", "选择左侧资源类型或文件，查看识别到的原文。")
        self.search = SearchLineEdit()
        self.search.setPlaceholderText("搜索文件、语言键和原文")
        self.search.textChanged.connect(lambda text: self.proxy.set_query(text, "all"))
        preview.addWidget(self.search)
        self.model = EntryModel(self)
        self.proxy = EntryFilter(self)
        self.proxy.setSourceModel(self.model)
        self.table = TableView()
        self.table.setModel(self.proxy)
        self.table.hideColumn(3)
        self.table.setSelectionBehavior(TableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(TableView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(TableView.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(240)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        preview.addWidget(self.table)
        self.source = TextEdit()
        self.source.setReadOnly(True)
        self.source.setPlaceholderText("选择条目查看完整原文与背景")
        self.source.setFixedHeight(100)
        preview.addWidget(self.source)
        self.table.selectionModel().currentRowChanged.connect(self.select_entry)
        self.status = BodyLabel("尚未识别资源")
        self.status.setWordWrap(True)
        page.body.addWidget(self.status)
        page.body.addStretch()
        self.update_mode()
        self.refresh_languages()
        self.check_output()

    def new_output(self):
        self.auto_output = new_task_output(self.root.text(), self.window.settings.output_home)
        self.output.setText(self.auto_output)

    def choose_baseline_file(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "选择上一版本快照", self.baseline.text(), "任务快照 (snapshot.json);;JSON (*.json)")
        if path:
            self.baseline.setText(path)

    def check_output(self):
        if not self.root.text():
            self.output_hint.setText("任务结果保存到实例外的独立目录，识别不会修改游戏文件。")
            self.suggested_output.hide()
            return
        try:
            output_for(self.root.text(), self.output.text())
        except ValueError as exc:
            self.output_hint.setText(str(exc) + "\n可点击下方按钮生成建议目录。")
            self.suggested_output.show()
        else:
            self.output_hint.setText("任务结果保存到实例外的独立目录，识别不会修改游戏文件。")
            self.suggested_output.hide()

    def root_changed(self, value):
        self.window.preferences.setValue("last_root", value)
        if self.output.text() == self.auto_output:
            self.new_output()
        self.inputs_changed()
        self.check_output()

    def inputs_changed(self):
        self.update_mode()
        self.workflow.invalidate_task()

    def update_mode(self):
        mods = "mods" in self.mode.selectedData()
        self.cfpa.setEnabled(mods)
        self.translation_library.setEnabled(mods)
        self.reuse_policy.setEnabled(mods)
        standalone_mods = self.mode.selectedData() == ["mods"]
        self.baseline.setEnabled(not standalone_mods)
        self.baseline_file.setEnabled(not standalone_mods)
        self.diff.setEnabled(not standalone_mods and not self.window.runner.busy)

    def refresh_languages(self, scan=None):
        source = scan.source_locale if scan else self.window.settings.source_locale
        target = scan.target_locale if scan else self.window.settings.target_locale
        self.languages.setText(f"{language_name(source)}（{source}） → {language_name(target)}（{target}） · 在设置中选择新任务语言")

    def bind_scan(self, scan, path):
        blockers = [QSignalBlocker(widget) for widget in (self.root, self.mode, self.pack_id,
                                                        self.translation_library, self.reuse_policy)]
        self.root.setText(scan.root)
        self.output.setText(path)
        scope = "mods" if scan.metadata.get("task_kind") == "mod-languages" else scan.metadata.get(
            "recognition_scopes", scan.metadata.get("recognition_scope", "resources"))
        self.mode.setSelectedData(scope)
        self.pack_id.setText(scan.pack_id)
        mods = mod_scan(scan)
        if mods is not None:
            library = mods.metadata["mod_library"]
            self.translation_library.setText(library["path"])
            self.reuse_policy.setCurrentIndex(self.reuse_policy.findData(library["policy"]))
        del blockers
        self.update_mode()
        self.refresh_languages(scan)
        self.tree.clear()
        self.proxy.set_documents(None)
        self.model.replace(scan.entries)
        self.model.set_excluded_documents(resource_exclusions(scan))
        self.source.clear()
        self.populate_tree(scan)
        groups = resource_groups(scan)
        self.resource_count.setText(f"{len(groups)} 类资源 · {len(scan.documents)} 个文件")
        counts = task_counts(scan)
        reuse = reuse_summary(scan.metadata)
        self.summary_text.setText(f"{scan.pack_id} · {counts['total']} 条参与翻译 · 待翻译 {counts['remaining']} 条\n"
                                  f"{language_name(scan.source_locale)} → {language_name(scan.target_locale)}" +
                                  (f" · 已排除 {counts['excluded']} 条" if counts.get("excluded") else "") +
                                  ("\n" + reuse if reuse else ""))
        self.input_summary.show()
        self.input_card.hide()
        self.status.setText("识别结果已保存；可以进入翻译。" + ("\n" + "\n".join(scan.warnings[:8]) if scan.warnings else ""))
        self.next.setEnabled(bool(counts['total']) and not self.window.runner.busy)

    def populate_tree(self, scan):
        groups = resource_groups(scan)
        warnings = resource_warnings(scan)
        excluded = resource_exclusions(scan)
        all_item = QTreeWidgetItem([f"全部资源 · {len(scan.entries)} 条"])
        all_item.setData(0, Qt.ItemDataRole.UserRole, None)
        all_item.setData(0, Qt.ItemDataRole.UserRole + 1, {"kind": "group", "path": ""})
        self.tree.addTopLevelItem(all_item)
        for label, documents in groups.items():
            item = QTreeWidgetItem([f"{label} · {sum(count for _, count in documents)} 条"])
            item.setData(0, Qt.ItemDataRole.UserRole, [name for name, _ in documents])
            item.setData(0, Qt.ItemDataRole.UserRole + 1, {"kind": "group", "path": label})
            item.setToolTip(0, f"{len(documents)} 个文件")
            self.tree.addTopLevelItem(item)
            folders = {}
            for name, count in documents:
                parts = name.replace("\\", "/").split("/")
                parent = item
                for index, part in enumerate(parts[:-1]):
                    prefix = "/".join(parts[:index + 1])
                    if prefix not in folders:
                        folder = QTreeWidgetItem([part])
                        folder.setIcon(0, FIF.FOLDER.icon())
                        folder.setData(0, Qt.ItemDataRole.UserRole, [])
                        folder.setData(0, Qt.ItemDataRole.UserRole + 1, {"kind": "directory", "path": prefix})
                        folder.setToolTip(0, prefix)
                        parent.addChild(folder)
                        folders[prefix] = folder
                    parent = folders[prefix]
                    parent.setData(0, Qt.ItemDataRole.UserRole, parent.data(0, Qt.ItemDataRole.UserRole) + [name])
                messages = warnings.get(name, [])
                child = QTreeWidgetItem([parts[-1] + f" · {count}" +
                                        (" · 已排除" if name in excluded else "")])
                child.setIcon(0, FIF.INFO.icon(color=QColor("#d99a00")) if messages else
                              FIF.CANCEL.icon() if name in excluded else FIF.DOCUMENT.icon())
                child.setData(0, Qt.ItemDataRole.UserRole, [name])
                child.setData(0, Qt.ItemDataRole.UserRole + 1, {"kind": "file", "path": name})
                child.setToolTip(0, "\n".join([name] + messages + (["已排除，不参与翻译与补丁导出"] if name in excluded else [])))
                if name in excluded:
                    child.setForeground(0, QColor("#888888"))
                parent.addChild(child)
                if messages:
                    ancestor = parent
                    while ancestor is not None:
                        ancestor.setExpanded(True)
                        ancestor = ancestor.parent()
            for folder in folders.values():
                paths = folder.data(0, Qt.ItemDataRole.UserRole)
                if all(path in excluded for path in paths):
                    folder.setText(0, folder.text(0) + " · 已排除")
                    folder.setForeground(0, QColor("#888888"))
        self.tree.setCurrentItem(all_item)

    def resource_menu(self, item):
        scan = self.workflow.task_scan
        if scan is None or item is None:
            return None
        paths = item.data(0, Qt.ItemDataRole.UserRole)
        paths = paths if paths is not None else [d.path for d in scan.documents]
        if not paths:
            return None
        manual = set(scan.metadata.get("manual_excluded_resources", []))
        details = item.data(0, Qt.ItemDataRole.UserRole + 1) or {}
        noun = {"file": "此文件", "directory": "此目录", "group": "所选资源"}.get(details.get("kind"), "资源")
        menu = RoundMenu(parent=self.tree)
        exclude = Action(FIF.CANCEL, "排除" + noun, menu)
        restore = Action(FIF.SYNC, "恢复" + noun, menu)
        ready = (not self.window.runner.busy and not self.window.review.loading and self.window.review.resumable())
        exclude.setEnabled(ready and any(path not in manual for path in paths))
        restore.setEnabled(ready and bool(manual.intersection(paths)))
        exclude.triggered.connect(lambda: self.change_exclusion(paths, "exclude"))
        restore.triggered.connect(lambda: self.change_exclusion(paths, "restore"))
        menu.addActions([exclude, restore])
        return menu

    def show_resource_menu(self, position):
        item = self.tree.itemAt(position)
        menu = self.resource_menu(item)
        if menu is not None:
            menu.exec(self.tree.viewport().mapToGlobal(position))
            menu.deleteLater()

    def change_exclusion(self, paths, action):
        if self.window.runner.busy or self.window.review.loading or not self.window.review.resumable():
            return
        label = "排除资源" if action == "exclude" else "恢复资源"
        self.window.run_job(lambda: Job("resource-exclusion", output=self.workflow.task_path,
                                       resource_paths=paths, resource_action=action,
                                       replace_existing_locale=self.workflow.patch_options().replace_existing_locale),
                            label, self.workflow.task_path)

    def clear_resources(self):
        self.tree.clear()
        self.proxy.set_documents(None)
        self.model.replace([])
        self.model.set_excluded_documents(set())
        self.source.clear()
        self.next.setEnabled(False)
        self.input_summary.hide()
        self.input_card.show()
        self.resource_count.setText("选择实例目录后开始识别")
        self.status.setText("输入已更改，请重新识别后翻译")
        self.refresh_languages()

    def select_resource(self, current, previous):
        self.proxy.set_documents(current.data(0, Qt.ItemDataRole.UserRole) if current else None)
        self.source.clear()
        details = current.data(0, Qt.ItemDataRole.UserRole + 1) if current else None
        scan = self.workflow.task_scan
        if details and details.get("kind") == "file" and scan:
            messages = resource_warnings(scan).get(details["path"], [])
            if messages:
                self.source.setPlainText(details["path"] + "\n\n" + "\n".join(messages))

    def select_entry(self, current, previous):
        if current.isValid():
            entry = self.model.entries[self.proxy.mapToSource(current).row()]
            location = f" · 第 {entry.script['line']} 行" if entry.script else ""
            self.source.setPlainText(entry.document + location + "\n" + entry.context + "\n\n" + entry.source)

    def set_busy(self, busy):
        self.suggested_output.setEnabled(not busy)
        for widget in (self.identify, self.root, self.output, self.mode, self.advanced):
            widget.setEnabled(not busy)
        self.next.setEnabled(not busy and bool(self.workflow.task_path))
        self.summary_next.setEnabled(not busy and bool(self.workflow.task_path))
        self.update_mode()
