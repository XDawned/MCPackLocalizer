# coding:utf-8
from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QWidget, QLabel, QFileDialog
from qfluentwidgets import FluentIcon as FIF, OptionsConfigItem
from qfluentwidgets import InfoBar
from qfluentwidgets import (SettingCardGroup, SwitchSettingCard, OptionsSettingCard, PushSettingCard,
                            HyperlinkCard, PrimaryPushSettingCard, ScrollArea, ExpandLayout, CustomColorSettingCard,
                            setTheme, setThemeColor, InfoBarPosition)

from common.activate import activate
from common.config import cfg, HELP_URL, FEEDBACK_URL, AUTHOR, VERSION, YEAR
from common.style_sheet import StyleSheet
from components.input_setting_card import PushEditSettingCard


class SettingInterface(ScrollArea):
    checkUpdateSig = pyqtSignal()
    cacheFoldersChanged = pyqtSignal(list)
    acrylicEnableChanged = pyqtSignal(bool)
    saveFolderChanged = pyqtSignal(str)
    minimizeToTrayChanged = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.scrollWidget = QWidget()
        self.expandLayout = ExpandLayout(self.scrollWidget)

        # setting label
        self.settingLabel = QLabel(self.tr("通用配置"), self)

        # workspace folders
        self.workSpaceGroup = SettingCardGroup(
            self.tr("目录配置"), self.scrollWidget)
        self.workFolderCard = PushSettingCard(
            self.tr('选择目录'),
            FIF.DOWNLOAD,
            self.tr("工作目录"),
            cfg.get(cfg.workFolder),
            self.workSpaceGroup
        )
        self.cacheFolderCard = PushSettingCard(
            self.tr('选择目录'),
            FIF.DOWNLOAD,
            self.tr("缓存目录"),
            cfg.get(cfg.cacheFolder),
            self.workSpaceGroup
        )
        # self.saveFolderCard = PushSettingCard(
        #     self.tr('选择目录'),
        #     FIF.DOWNLOAD,
        #     self.tr("保存目录"),
        #     cfg.get(cfg.saveFolder),
        #     self.workSpaceGroup
        # )

        # translate api
        self.translateGroup = SettingCardGroup(
            self.tr('机翻配置'), self.scrollWidget)
        self.keepOriginalCard = SwitchSettingCard(
            FIF.BACKGROUND_FILL,
            self.tr('预翻译保留原文'),
            self.tr('为保证生态，未激活拓展功能将无法关闭'),
            configItem=cfg.keepOriginal,
            parent=self.translateGroup
        )
        self.translateAPICard = OptionsSettingCard(
            cfg.translateApi,
            FIF.BRUSH,
            self.tr('翻译API'),
            self.tr("选择使用的翻译API"),
            texts=[
                self.tr('百度翻译'), self.tr('离线翻译')
                , self.tr('OpenAI')
            ],
            parent=self.translateGroup
        )

        self.appKeyCard = PushEditSettingCard(
            self.tr('保存'),
            FIF.BRUSH,
            self.tr('AppKey'),
            self.tr('请在这里输入你的百度翻译api的AppKey'),
            self.tr('MyAppKey'),
            cfg.appKey,
            self.translateGroup
        )

        self.appSecretCard = PushEditSettingCard(
            self.tr('保存'),
            FIF.BRUSH,
            self.tr('AppSecret'),
            self.tr('请在这里输入你的百度翻译api的AppSecret'),
            self.tr('MyAppSecret'),
            cfg.appSecret,
            self.translateGroup
        )
        self.openaiUrlCard = PushEditSettingCard(
            self.tr('保存'),
            FIF.BRUSH,
            self.tr('接口地址'),
            self.tr('请在这里输入你OpenAI接口地址'),
            self.tr('openAiUrl'),
            cfg.openaiUrl,
            self.translateGroup
        )
        self.modelNameCard = PushEditSettingCard(
            self.tr('保存'),
            FIF.BRUSH,
            self.tr('模型名称'),
            self.tr('请在这里输入你的OpenAI模型名称'),
            self.tr('modelName'),
            cfg.modelName,
            self.translateGroup
        )
        self.orgIdCard = PushEditSettingCard(
            self.tr('保存'),
            FIF.BRUSH,
            self.tr('OrganizationID'),
            self.tr('请在这里输入你的OpenAI组织名(本地模型可不填)'),
            self.tr('OrganizationID'),
            cfg.orgId,
            self.translateGroup
        )
        self.secretKeyCard = PushEditSettingCard(
            self.tr('保存'),
            FIF.BRUSH,
            self.tr('SecretKey'),
            self.tr('请在这里输入你的OpenAI密钥(本地模型可不填)'),
            self.tr('SecretKey'),
            cfg.secretKey,
            self.translateGroup
        )
        self.localServiceUrlCard = PushEditSettingCard(
            self.tr('保存'),
            FIF.BRUSH,
            self.tr('本地推理服务地址'),
            self.tr('独立 uv 环境运行的 FastAPI 服务，默认 http://127.0.0.1:8765'),
            self.tr('http://127.0.0.1:8765'),
            cfg.localServiceUrl,
            self.translateGroup
        )

        # personalization
        self.personalGroup = SettingCardGroup(
            self.tr('个性化'), self.scrollWidget)
        self.themeCard = OptionsSettingCard(
            cfg.themeMode,
            FIF.BRUSH,
            self.tr('软件主题'),
            self.tr("修改软件外观"),
            texts=[
                self.tr('明亮'), self.tr('黑暗'),
                self.tr('跟随系统设置')
            ],
            parent=self.personalGroup
        )
        custom_color_setting_card = CustomColorSettingCard(
            cfg.themeColor,
            FIF.PALETTE,
            self.tr('主题颜色'),
            self.tr('修改你应用的主题色'),
            self.personalGroup
        )
        custom_color_setting_card.defaultRadioButton.setText('默认颜色')
        custom_color_setting_card.customRadioButton.setText('自定义颜色')
        custom_color_setting_card.customLabel.setText('选择颜色')
        self.themeColorCard = custom_color_setting_card
        self.zoomCard = OptionsSettingCard(
            cfg.dpiScale,
            FIF.ZOOM,
            self.tr("界面缩放"),
            self.tr("修改界面与字体大小"),
            texts=[
                "100%", "125%", "150%", "175%", "200%",
                self.tr("自动")
            ],
            parent=self.personalGroup
        )

        self.activateSoftwareGroup = SettingCardGroup(
            self.tr("拓展功能"), self.scrollWidget)
        self.activateSoftwareCard = PushEditSettingCard(
            self.tr('激活'),
            FIF.BRUSH,
            self.tr('一些额外功能'),
            self.tr('供专业译者使用'),
            self.tr('请在这里输入你的激活码'),
            cfg.activateCode,
            self.activateSoftwareGroup
        )

        # update software
        self.updateSoftwareGroup = SettingCardGroup(
            self.tr("软件更新"), self.scrollWidget)
        self.updateOnStartUpCard = SwitchSettingCard(
            FIF.UPDATE,
            self.tr('在软件启动时自动检查更新'),
            self.tr('新版本将提供更稳定和更多的功能'),
            configItem=cfg.checkUpdateAtStartUp,
            parent=self.updateSoftwareGroup
        )

        # application
        self.aboutGroup = SettingCardGroup(self.tr('关于'), self.scrollWidget)
        self.helpCard = HyperlinkCard(
            HELP_URL,
            self.tr('打开帮助页面'),
            FIF.HELP,
            self.tr('帮助'),
            self.tr(
                '查看整合包汉化工具的帮助文档'),
            self.aboutGroup
        )
        self.feedbackCard = PrimaryPushSettingCard(
            self.tr('提供反馈'),
            FIF.FEEDBACK,
            self.tr('提供反馈'),
            self.tr('帮助我们改进整合包汉化工具'),
            self.aboutGroup
        )
        self.aboutCard = PrimaryPushSettingCard(
            self.tr('请作者喝杯快乐水？'),
            FIF.INFO,
            self.tr('关于'),
            '© ' + self.tr('Copyright') + f" {YEAR}, {AUTHOR}. " +
            self.tr('版本') + " " + VERSION,
            self.aboutGroup
        )

        self.__initWidget()

    def __initWidget(self):
        self.resize(1000, 800)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setViewportMargins(0, 80, 0, 20)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)

        # initialize style sheet
        self.scrollWidget.setObjectName('scrollWidget')
        self.settingLabel.setObjectName('settingLabel')
        StyleSheet.SETTING_INTERFACE.apply(self)

        # initialize layout
        self.__initLayout()
        self.__connectSignalToSlot()

    def __initLayout(self):
        self.settingLabel.move(36, 30)

        # add cards to group
        self.workSpaceGroup.addSettingCard(self.workFolderCard)
        self.workSpaceGroup.addSettingCard(self.cacheFolderCard)
        # self.workSpaceGroup.addSettingCard(self.saveFolderCard)

        self.translateGroup.addSettingCard(self.keepOriginalCard)
        self.translateGroup.addSettingCard(self.translateAPICard)
        self.translateGroup.addSettingCard(self.appKeyCard)
        self.translateGroup.addSettingCard(self.appSecretCard)
        self.translateGroup.addSettingCard(self.openaiUrlCard)
        self.translateGroup.addSettingCard(self.modelNameCard)
        self.translateGroup.addSettingCard(self.orgIdCard)
        self.translateGroup.addSettingCard(self.secretKeyCard)
        self.translateGroup.addSettingCard(self.localServiceUrlCard)

        self.personalGroup.addSettingCard(self.themeCard)
        self.personalGroup.addSettingCard(self.themeColorCard)
        self.personalGroup.addSettingCard(self.zoomCard)

        self.activateSoftwareGroup.addSettingCard(self.activateSoftwareCard)

        self.updateSoftwareGroup.addSettingCard(self.updateOnStartUpCard)

        self.aboutGroup.addSettingCard(self.helpCard)
        self.aboutGroup.addSettingCard(self.feedbackCard)
        self.aboutGroup.addSettingCard(self.aboutCard)

        # add setting card group to layout
        self.expandLayout.setSpacing(28)
        self.expandLayout.setContentsMargins(36, 10, 36, 0)
        self.expandLayout.addWidget(self.workSpaceGroup)
        self.expandLayout.addWidget(self.translateGroup)
        self.expandLayout.addWidget(self.personalGroup)
        self.expandLayout.addWidget(self.activateSoftwareGroup)
        self.expandLayout.addWidget(self.updateSoftwareGroup)
        self.expandLayout.addWidget(self.aboutGroup)

        self.handle_api_change(self.translateAPICard.configItem)
        self.translateAPICard.optionChanged.connect(self.handle_api_change)

    def __showRestartTooltip(self):
        InfoBar.success(
            self.tr('更新成功'),
            self.tr('如未生效可以尝试重启软件'),
            duration=1500,
            parent=self
        )

    def __onWorkFolderCardClicked(self):
        folder = QFileDialog.getExistingDirectory(
            self, self.tr("请选择工作目录"), "./")
        if not folder or cfg.get(cfg.workFolder) == folder:
            return

        cfg.set(cfg.workFolder, folder)
        self.workFolderCard.setContent(folder)

    def __onCacheFolderCardClicked(self):
        folder = QFileDialog.getExistingDirectory(
            self, self.tr("请选择缓存目录"), "./")
        if not folder or cfg.get(cfg.cacheFolder) == folder:
            return

        cfg.set(cfg.cacheFolder, folder)
        self.cacheFolderCard.setContent(folder)

    # def __onSaveFolderCardClicked(self):
    #     folder = QFileDialog.getExistingDirectory(
    #         self, self.tr("请选择文件保存目录"), "./")
    #     if not folder or cfg.get(cfg.saveFolder) == folder:
    #         return
    #
    #     cfg.set(cfg.saveFolder, folder)
    #     self.saveFolderCard.setContent(folder)

    def __onActivateCardClicked(self):
        activate.check()
        if activate.activate:
            self.keepOriginalCard.switchButton.setEnabled(True)
            InfoBar.success(
                title=self.tr(''),
                content=self.tr(activate.activateInfo),
                orient=Qt.Orientation.Horizontal,
                isClosable=False,
                position=InfoBarPosition.TOP_LEFT,
                duration=2000,
                parent=self
            )
        else:
            self.keepOriginalCard.switchButton.setChecked(True)
            self.keepOriginalCard.switchButton.setEnabled(False)
            InfoBar.warning(
                title=self.tr(''),
                content=self.tr(activate.activateInfo),
                orient=Qt.Orientation.Horizontal,
                isClosable=False,
                position=InfoBarPosition.TOP_LEFT,
                duration=2000,
                parent=self
            )

    def __connectSignalToSlot(self):
        """ connect signal to slot """
        if not activate.activate:
            self.keepOriginalCard.switchButton.setChecked(True)
            self.keepOriginalCard.switchButton.setEnabled(False)
        cfg.appRestartSig.connect(self.__showRestartTooltip)
        cfg.themeChanged.connect(setTheme)
        self.workFolderCard.clicked.connect(
            self.__onWorkFolderCardClicked)
        self.keepOriginalCard.checkedChanged.connect(
            self.__showRestartTooltip)
        self.cacheFolderCard.clicked.connect(
            self.__onCacheFolderCardClicked)
        self.themeColorCard.colorChanged.connect(setThemeColor)
        self.activateSoftwareCard.button.clicked.connect(self.__onActivateCardClicked)
        self.aboutCard.clicked.connect(self.checkUpdateSig)
        self.feedbackCard.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(FEEDBACK_URL)))

    def handle_api_change(self, option):
        if option.value == '0':
            self.secretKeyCard.setVisible(False)
            self.orgIdCard.setVisible(False)
            self.openaiUrlCard.setVisible(False)
            self.modelNameCard.setVisible(False)
            self.appKeyCard.setVisible(True)
            self.appSecretCard.setVisible(True)
            self.localServiceUrlCard.setVisible(False)
        elif option.value == '1':
            self.appKeyCard.setVisible(False)
            self.appSecretCard.setVisible(False)
            self.secretKeyCard.setVisible(False)
            self.orgIdCard.setVisible(False)
            self.openaiUrlCard.setVisible(False)
            self.modelNameCard.setVisible(False)
            self.localServiceUrlCard.setVisible(True)
        elif option.value == '2':
            self.appKeyCard.setVisible(False)
            self.appSecretCard.setVisible(False)
            self.secretKeyCard.setVisible(True)
            self.orgIdCard.setVisible(True)
            self.openaiUrlCard.setVisible(True)
            self.modelNameCard.setVisible(True)
            self.localServiceUrlCard.setVisible(False)
        self.translateGroup.adjustSize()
