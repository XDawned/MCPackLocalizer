# coding:utf-8
import os

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QLabel
from qfluentwidgets import ScrollArea, InfoBar, RoundMenu, Action, FluentIcon, StateToolTip, \
    ProgressBar, TextEdit, MessageBox, CommandBar, TransparentDropDownPushButton, setFont

from common.config import cfg
from common.style_sheet import StyleSheet
from common.update_checker import update_checker
from common.util import Lang, LangTranslateThread, save_lang_file, FTBQuest, BetterQuest
from components.file_browser import FileBrowser
from components.pivot_interface import PivotInterface
from .search_interface import SearchDictInterface


class WorkInterface(ScrollArea):
    """ Home interface """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.ext = None  # 文件后缀.snbt .nbt .json .lang
        self.first_update_flag = True
        self.data = [
            ['', '你可以在左侧工作区域内选择json格式的语言文件，双击读取并编辑', '', ''],
            ['', '需要注意的是你只能编辑译文', '', ''],
            ['', '点击保存进度按钮可以保留此次工作进度', '', '']
        ]
        self.stateTooltip = None
        self.translator_thread = None
        self.trans_list = None
        self.lang = Lang()
        self.quest = None

        self.view = QWidget(self)
        self.layout = QHBoxLayout(self.view)
        self.view.setObjectName('view')

        self.__initWidget()

    def __initWidget(self):
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWidget(self.view)
        self.setWidgetResizable(True)

        self.fileBrowser = FileBrowser(cfg.workFolder)
        self.searchDictInterface = SearchDictInterface()

        self.middleBox = QWidget()
        self.middleLayout = QVBoxLayout()

        self.langBrowser = PivotInterface(self.data)
        self.langBrowser.setMinimumHeight(920)

        self.progressBar = ProgressBar()
        self.progressBar.setValue(0)
        self.middleLayout.addWidget(self.progressBar)

        # 绑定快捷键
        shortcut1 = QShortcut(QKeySequence("F1"), self.view)
        shortcut2 = QShortcut(QKeySequence("F2"), self.view)
        shortcut3 = QShortcut(QKeySequence("F3"), self.view)
        shortcut4 = QShortcut(QKeySequence("F4"), self.view)
        shortcut5 = QShortcut(QKeySequence("F5"), self.view)
        shortcut1.activated.connect(lambda: self.handle_translate_start(self.lang))
        shortcut2.activated.connect(self.handle_translate_stop)
        shortcut3.activated.connect(self.handle_save)
        shortcut4.activated.connect(self.handle_save_as)
        shortcut5.activated.connect(self.handle_save_cache)

        self.middleLayout.addWidget(self.langBrowser)
        self.middleLayout.addStretch(1)
        self.middleLayout.addWidget(self.create_command_bar())
        self.middleBox.setLayout(self.middleLayout)

        self.searchBox = QWidget()
        self.searchLayout = QVBoxLayout()
        self.searchBox.setFixedWidth(300)
        self.remain_time_label = QLabel('', self)
        self.remain_time_label.setFixedHeight(40)
        self.transLog = TextEdit()
        self.transLog.setStyleSheet('background-color: transparent;border:none')
        self.transLog.setFixedSize(280, 320)
        self.transLog.setReadOnly(True)
        self.transLog.setPlainText(f'快捷键：\nCtrl+A-上一条\nCtrl+D-下一条\nCtrl+W上个文件\nCtrl+S下'
                                   f'个文件\nCtrl+Enter开始编辑\nEsc退出编辑\n\nCtrl+?搜索离线词典\n\nF1/F2-开始'
                                   f'/停止机翻\nF3/F4-保存/另存为')
        self.searchDictInterface.setFixedHeight(400)
        self.searchLayout.addWidget(self.searchDictInterface)
        self.searchLayout.addStretch(1)
        self.searchLayout.addWidget(self.remain_time_label)
        self.searchLayout.addWidget(self.transLog)
        self.searchBox.setLayout(self.searchLayout)

        self.fileBrowser.chooseFile.connect(self.handle_choose_file)
        self.fileBrowser.chooseFolder.connect(self.handle_choose_folder)

        self.layout.addWidget(self.fileBrowser)
        self.layout.addWidget(self.middleBox)
        self.layout.addWidget(self.searchBox)

        self.fileBrowser.setObjectName('fileBrowser')
        self.transLog.setObjectName('transLog')
        self.remain_time_label.setObjectName('remain_time_label')
        StyleSheet.WORK_INTERFACE.apply(self)

    def create_command_bar(self):
        bar = CommandBar(self)
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        # 创建下拉菜单
        menu_save = RoundMenu(parent=self)
        menu_pre_trans = RoundMenu(parent=self)
        # menu_extra = RoundMenu(parent=self)
        action_trans_start = Action(FluentIcon.SEND_FILL, '开始机翻', shortcut='F1')
        action_trans_stop = Action(FluentIcon.CLOSE, '终止机翻', shortcut='F2')
        action_save_lang = Action(FluentIcon.SAVE, '保存', shortcut='F3')
        action_save_lang_as = Action(FluentIcon.SAVE_AS, '另存为', shortcut='F4')
        action_save_cache = Action(FluentIcon.PIN, '保存进度', shortcut='F5')
        action_migrate = Action(FluentIcon.HISTORY, '从旧版本迁移')
        # 绑定信号槽
        action_trans_start.triggered.connect(lambda: self.handle_translate_start(self.lang))
        action_trans_start.triggered.connect(self.__check_update)
        action_trans_stop.triggered.connect(self.handle_translate_stop)
        action_save_cache.triggered.connect(self.handle_save_cache)
        action_save_lang.triggered.connect(self.handle_save)
        action_save_lang_as.triggered.connect(self.handle_save_as)
        action_migrate.triggered.connect(self.handle_migrate)
        # 绑定事件
        menu_pre_trans.addAction(action_trans_start)
        menu_pre_trans.addAction(action_trans_stop)
        menu_save.addAction(action_save_lang)
        menu_save.addAction(action_save_lang_as)
        # 调整样式完成菜单创建
        save_btn = TransparentDropDownPushButton('保存', self, FluentIcon.SAVE)
        save_btn.setMenu(menu_save)
        save_btn.setFixedHeight(34)
        setFont(save_btn, 12)
        pre_trans_btn = TransparentDropDownPushButton(self.tr('预翻译'), self, FluentIcon.BASKETBALL)
        pre_trans_btn.setMenu(menu_pre_trans)
        pre_trans_btn.setFixedHeight(34)
        setFont(pre_trans_btn, 12)
        # 放入菜单栏中
        bar.addWidget(pre_trans_btn)
        bar.addWidget(save_btn)
        bar.addSeparator()
        bar.addActions([
            action_save_cache,
            action_migrate,
        ])
        # bar.addHiddenActions([
        #     Action(FIF.SETTING, self.tr('Settings'), shortcut='Ctrl+I'),
        # ])
        return bar

    def __check_update(self):
        if self.first_update_flag and update_checker.need_update and cfg.get(cfg.checkUpdateAtStartUp):
            self.first_update_flag = False
            title = self.tr('检测到新版本:%s' % update_checker.latest_version)
            content = self.tr('更新日志：%s\n' % update_checker.logs)
            w = MessageBox(title, content, self.window())
            if w.exec():
                QDesktopServices.openUrl(QUrl(update_checker.link))

    def update_trans_log(self, info):
        current_text = self.transLog.toHtml()
        new_text = current_text + "\n" + info
        self.transLog.setHtml(new_text)
        self.transLog.verticalScrollBar().setValue(
            self.transLog.verticalScrollBar().maximum()
        )

    def handle_choose_file(self, path):
        self.trans_list = None
        self.transLog.setPlainText('')
        ext = os.path.splitext(path)[1].lower()
        self.ext = ext
        try:
            if ext in ['.json', '.lang']:
                self.lang.read_lang(path)
            elif ext == '.snbt':
                self.quest = FTBQuest(path)
                self.lang = self.quest.lang
            else:
                InfoBar.info(
                    self.tr('无法读取'),
                    self.tr('暂时只支持lang与snbt任务文件'),
                    duration=3000,
                    parent=self
                )
        except Exception as e:
            InfoBar.error(
                self.tr('错误'),
                self.tr(str(e)),
                duration=30000,
                parent=self
            )
        else:
            self.read_cache_tooltip()
            self.langBrowser.browseInterface.update_table(self.lang.lang_bilingual_list)
            self.langBrowser.reviewInterface.update_table(self.lang.lang_bilingual_list)
            self.langBrowser.reviewInterface.current_trans_info.setText('')
            if ext == '.json' or ext == '.lang':
                InfoBar.success(
                    self.tr('读取成功'),
                    self.tr('检测为%s语言文件' % ext),
                    duration=3000,
                    parent=self
                )
            elif ext == '.snbt':
                InfoBar.success(
                    self.tr('读取成功'),
                    self.tr('检测为snbt任务文件，已提取出需翻译部分'),
                    duration=3000,
                    parent=self
                )

    def handle_choose_folder(self, path):
        # 批量预翻译并生成缓存文件
        failed_file = []
        lang = []
        self.transLog.setPlainText('')
        for root, dirs, files in os.walk(path):
            for file in files:
                if "zh_cn" not in file.lower():
                    ext = os.path.splitext(file)[1].lower()
                    file_path = os.path.join(root, file)
                    if ext in ['.json', '.lang']:
                        if "betterquesting" in root and ext == '.json':
                            lang.append(BetterQuest(file_path).lang)
                        else:
                            lang_ = Lang()
                            lang_.read_lang(file_path)
                            lang.append(lang_)
                    elif ext == '.snbt':
                        lang.append(FTBQuest(file_path).lang)
                    else:
                        failed_file.append({
                            'file_name': files,
                            'reason': "不支持的文件类型，自动略过",
                        })
                else:
                    failed_file.append({
                        'file_name': files,
                        'reason': "语言文件可能为中文，自动略过",
                    })
        self.handle_translate_start(lang, single=False)

    def read_cache_tooltip(self):
        if self.lang.cache_dic != {}:
            InfoBar.success(
                self.tr('读取到进度缓存'),
                self.tr(''),
                duration=3000,
                parent=self
            )

    def handle_translate_start(self, lang, single=True):
        self.translator_thread = LangTranslateThread(lang, 'en', 'zh', cfg.get(cfg.appKey),
                                                     cfg.get(cfg.appSecret))
        self.trans_list = self.lang.lang_bilingual_list
        self.remain_time_label.setText('')
        self.translator_thread.finished.connect(lambda: self.on_translation_finished(single))
        self.translator_thread.progress.connect(self.progressBar.setValue)
        self.translator_thread.index.connect(self.langBrowser.reviewInterface.current_trans_info.setText)
        self.translator_thread.remain_time.connect(self.remain_time_label.setText)
        self.translator_thread.error.connect(self.on_translation_failed)
        self.translator_thread.info.connect(self.update_trans_log)
        self.translator_thread.start()

        self.progressBar.show()
        self.stateTooltip = StateToolTip(
            self.tr('翻译'), self.tr('执行中,请耐心等待'), self.window())
        self.stateTooltip.move(self.stateTooltip.getSuitablePos())
        self.stateTooltip.show()

    def handle_translate_stop(self):
        try:
            self.translator_thread.stop()
            self.remain_time_label.setText('')
        except Exception as e:
            InfoBar.warning(
                self.tr('终止出错'),
                self.tr('错误信息:%s' % str(e)),
                duration=10000,
                parent=self
            )

    def on_translation_finished(self, single=True):
        """
        :param single 区分是否为单个翻译，批量翻译情况下无需同步编辑器
        """
        self.progressBar.hide()
        self.stateTooltip.setContent(
            self.tr('完成，你可以在编辑视图中查看!') + ' 😆')
        self.stateTooltip.setState(True)
        self.stateTooltip = None
        self.remain_time_label.setText('')
        if single:
            self.langBrowser.browseInterface.update_table(self.lang.lang_bilingual_list)
            self.langBrowser.reviewInterface.update_table(self.lang.lang_bilingual_list)

    def on_translation_failed(self, error_msg):
        # 隐藏进度条，恢复用户界面
        self.progressBar.hide()
        # 弹出错误提示框
        InfoBar.error(
            self.tr('API调用失败'),
            self.tr('错误信息:%s' % error_msg),
            duration=10000,
            parent=self
        )
        self.progressBar.hide()
        self.stateTooltip.setState(True)
        self.stateTooltip = None

    def handle_save_cache(self):
        # TODO 改为使用向量数据库或AC自动机进行检索，修改数据保存方式
        try:
            result = self.lang.save_cache()
        except Exception as e:
            InfoBar.error(
                self.tr('进度缓存失败'),
                self.tr('错误::%s' % str(e)),
                duration=10000,
                parent=self
            )
        else:
            InfoBar.success(
                self.tr('进度缓存成功'),
                self.tr('已保存于 %s' % result.split('/')[-1]),
                duration=5000,
                parent=self
            )

    def handle_save_as(self):
        if self.ext == '.snbt':
            prefix_path = os.path.dirname(self.quest.input_path) + '/回填后文件'
            os.makedirs(prefix_path) if not os.path.exists(prefix_path) else None
            folder, _ = QFileDialog.getSaveFileName(self, "保存文件", prefix_path + '/' + self.quest.quest_name
                                                    , "SNBT 文件 (*.snbt);;所有文件 (*)")
        else:
            original_path = os.path.dirname(self.lang.file_path) + '/zh_cn' if 'en' in self.lang.file_path else '/zh_CN'
            file_type = 'JSON 文件 (*.json);;' if 'json' in self.lang.file_path else 'LANG 文件 (*.lang);;'
            folder, _ = QFileDialog.getSaveFileName(self, "保存文件", original_path, f"{file_type}所有文件 (*)")

    def handle_save(self):
        if self.ext == '.snbt':
            prefix_path = os.path.dirname(self.quest.input_path) + '/回填后文件'
            os.makedirs(prefix_path) if not os.path.exists(prefix_path) else None
            folder = f"{prefix_path}/{self.quest.quest_name}.snbt"
        else:
            folder = self.lang.file_path.replace('en_us.', 'zh_cn.')
            folder = folder.replace('en_US.', 'zh_CN.')
        self.save_lang_file(folder)

    def save_lang_file(self, path: str):
        if path:
            try:
                data = {row[0]: row[2] for row in self.lang.lang_bilingual_list if row[2] != ''}
                if self.ext != '.snbt':
                    save_lang_file(data, path)
                else:
                    save_lang_file(data, path, self.quest.back_fill(data))
            except Exception as e:
                InfoBar.error(
                    self.tr('保存失败'),
                    self.tr('错误:%s' % str(e)),
                    duration=10000,
                    parent=self
                )
            else:
                InfoBar.success(
                    self.tr('保存成功'),
                    self.tr('已保存于:%s' % path),
                    duration=10000,
                    parent=self
                )

    def handle_migrate(self):
        title = self.tr('须知')
        content = self.tr(
            "此功能针对专业译者提供，主要从旧版本语言文件中迁移汉化\n"
            "使用时请提前在当前视图所打开的文件同级目录下创建old文件夹"
            "并将旧汉化的en_us和zh_cn放到此目录下")
        w = MessageBox(title, content, self.window())
        if not w.exec():
            return
        count = 0
        try:
            old_lang_root = os.path.dirname(self.lang.file_path) + '/old'
            if os.path.exists(old_lang_root):
                old_lang_en = None
                old_lang_zh = None
                for root, dirs, files in os.walk(old_lang_root):
                    for file in files:
                        file_low = file.lower()
                        if "zh_cn" in file_low:
                            old_lang_zh = Lang()
                            old_lang_zh.read_lang(os.path.join(root, file))
                        elif "en_us" in file_low:
                            old_lang_en = Lang()
                            old_lang_en.read_lang(os.path.join(root, file))
                if old_lang_zh and old_lang_en:
                    old_lang_zh_dic = old_lang_zh.lang_dic
                    old_lang_en_dic = old_lang_en.lang_dic
                    for i in range(0, len(self.lang.lang_bilingual_list)):
                        new_lang_en_text = self.lang.lang_bilingual_list[i][1]
                        for key, value in old_lang_en_dic.items():
                            if value == new_lang_en_text:
                                self.lang.lang_bilingual_list[i][2] = old_lang_zh_dic.get(key)
                                count = count + 1
                                break
                    self.langBrowser.browseInterface.update_table(self.lang.lang_bilingual_list)
                    self.langBrowser.reviewInterface.update_table(self.lang.lang_bilingual_list)
            else:
                raise Exception('缺少旧版本语言文件')
        except Exception as e:
            InfoBar.error(
                self.tr('迁移失败'),
                self.tr('错误:%s' % str(e)),
                duration=10000,
                parent=self
            )
        else:
            InfoBar.success(
                self.tr('迁移成功'),
                self.tr('导入了%s条' % str(count)),
                duration=3000,
                parent=self
            )
