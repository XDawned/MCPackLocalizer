# [Module: desktop.styles] [Status: 已完成] [Brief: 修正 Fluent 样式与销毁回调的所有权，避免 GC 期间原生访问冲突]
from PyQt6.QtWidgets import QApplication, QStyleFactory
from qfluentwidgets.common import style_sheet
from qfluentwidgets.components.widgets import menu
from qfluentwidgets.components.widgets.menu import CustomMenuStyle


def _styles():
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("创建 Fluent 样式前必须先创建 QApplication")
    # 同时保留 Python 包装和 Qt 所有权；样式随应用释放，不能随旧菜单包装被 GC 回收。
    return app, app.__dict__.setdefault("_mcpl_fluent_styles", {})


class PinnedStyleFactory:
    keys = staticmethod(QStyleFactory.keys)

    @staticmethod
    def create(name):
        app, styles = _styles()
        key = ("factory", name.casefold())
        if key not in styles:
            style = QStyleFactory.create(name)
            if style is None:
                return None
            style.setParent(app)
            styles[key] = style
        return styles[key]


def _menu_style(iconSize=14):
    app, styles = _styles()
    key = ("menu", iconSize)
    if key not in styles:
        style = CustomMenuStyle(iconSize)
        style.setParent(app)
        styles[key] = style
    return styles[key]


def _register_style_sheet(self, source, widget, reset=True):
    """由弱注册表清理控件，避免 destroyed 的 Python 闭包在 GC 析构中重入。"""
    if isinstance(source, str):
        source = style_sheet.StyleSheetFile(source)
    if widget not in self.widgets:
        # 包装回收时 WeakKeyDictionary 自动移除；原生控件先销毁时，上游主题更新会清理失效包装。
        # 两个过滤器都无控件状态，随应用保留，避免临时包装在处理 Qt 事件时被 GC 析构。
        app, styles = _styles()
        for watcher_type in (style_sheet.CustomStyleSheetWatcher, style_sheet.DirtyStyleSheetWatcher):
            key = ("watcher", watcher_type)
            if key not in styles:
                styles[key] = watcher_type(app)
            widget.installEventFilter(styles[key])
        self.widgets[widget] = style_sheet.StyleSheetCompose([source, style_sheet.CustomStyleSheet(widget)])
    if reset:
        self.widgets[widget] = style_sheet.StyleSheetCompose([source, style_sheet.CustomStyleSheet(widget)])
    else:
        self.source(widget).add(source)


def pin_fluent_styles():
    """修正 Fluent 样式与事件过滤器的生命周期；窗口初始化时可安全重入。"""
    style_sheet.QStyleFactory = PinnedStyleFactory
    menu.QStyleFactory = PinnedStyleFactory
    menu.CustomMenuStyle = _menu_style
    style_sheet.StyleSheetManager.register = _register_style_sheet
