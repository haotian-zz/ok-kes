# 本文件取自 YES-BD2（https://github.com/nobell001/YES-BD2，GPL-3.0），按 ok-kes 需要改动；见 THIRD_PARTY_NOTICES.md
"""Puts the new sidebar and pages into ok's main window.

ok 原来的导航只是藏起来：页面还在 stacked widget 里，但新界面里没有入口（用户 2026-10-28：只用新界面）。
ok 自己跳到旧页面时（启动出错、通知）转回首页。从 ``Globals.on_show_main_window`` 装进来。
"""

from __future__ import annotations

from ok import Logger
from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from src.ui.shell import actions, theme
from src.ui.shell.motion import PageCover

logger = Logger.get_logger(__name__)

MIN_WIDTH = 940
MIN_HEIGHT = 600


def build_pages(window, navigate) -> dict[str, QWidget]:
    """所有新页面（也给离屏截图脚本用）。"""
    from src.ui.shell.about_page import AboutPage
    from src.ui.shell.chaos_page import ChaosPage
    from src.ui.shell.guide_page import GuidePage
    from src.ui.shell.home import HomePage
    from src.ui.shell.runs_page import RunsPage
    from src.ui.shell.settings import SettingsPage
    from src.ui.shell.task_page import TaskPage

    return {
        "home": HomePage(navigate),
        "daily": TaskPage("shellDaily", "DailyTask", "一键日常", "依次执行勾选的日常项目"),
        "chaos": ChaosPage(),
        "sortie": TaskPage("shellSortie", "SortieMode", "出击", "自动出击：选人、选路、出牌"),
        "story": TaskPage("shellStory", "StoryMode", "剧情", "半自动剧情：点对话、跳过、进战斗"),
        "runs": RunsPage(),
        "guide": GuidePage(),
        "settings": SettingsPage(window),
        "about": AboutPage(window),
    }


class Shell(QObject):
    """Owns the sidebar and the new pages; keeps the sidebar on the shown page."""

    def __init__(self, window):
        super().__init__(window)
        from src.ui.shell.sidebar import Sidebar

        self.window = window
        self.pages = build_pages(window, self.navigate)
        self.sidebar = Sidebar()
        self.sidebar.navigate.connect(self.navigate)

        # Everything above only builds widgets; from here on the window changes.
        stack = window.stackedWidget
        for page in self.pages.values():
            page.setProperty("isStackedTransparent", True)
            stack.addWidget(page)
        window.hBoxLayout.insertWidget(0, self.sidebar)
        _hide_old_navigation(window)
        _tidy_title_bar(window)
        _use_flat_background(window)
        theme.sync_fluent_accent()
        theme.on_theme_changed(self, theme.sync_fluent_accent)
        if window.minimumWidth() < MIN_WIDTH or window.minimumHeight() < MIN_HEIGHT:
            window.setMinimumSize(max(window.minimumWidth(), MIN_WIDTH), max(window.minimumHeight(), MIN_HEIGHT))

        self.cover = PageCover(stack)
        from src.ui.shell.nav_history import BackForward, History

        self.history = History()
        self.back_forward = BackForward(window, self.go_back, self.go_forward)
        _drop_old_touch_guards(window)
        stack.currentChanged.connect(self._on_page_changed)
        self._take_over_start_switch()
        window.switchTo(self.pages["home"])
        self._on_page_changed(stack.currentIndex())

    # ------------------------------------------------------------ navigation

    def navigate(self, key: str) -> None:
        page = self.pages.get(key)
        if page is not None:
            self.window.switchTo(page)

    def go_back(self) -> None:
        self._go(self.history.go_back())

    def go_forward(self) -> None:
        self._go(self.history.go_forward())

    def _go(self, key: str | None) -> None:
        if key is not None:
            self.navigate(key)

    def _on_page_changed(self, _index: int) -> None:
        current = self.window.stackedWidget.currentWidget()
        for key, page in self.pages.items():
            if page is current:
                self.history.arrived(key)
                self.sidebar.select(key)
                self.cover.play(page)
                return
        if current is not None:
            # ok 自己切到了旧页面（启动出错时的「捕获」页、通知跳转）：消息还在窗口上方提示，页面回首页
            logger.info(f"ok opened an old page ({type(current).__name__}), back to 首页")
            QTimer.singleShot(0, lambda: self.navigate("home"))

    # ------------------------------------------------------------ start

    def _take_over_start_switch(self) -> None:
        """ok 开始后会跳到旧任务列表；改成只提示。"""
        from ok.gui.Communicate import communicate

        try:
            communicate.executor_paused.disconnect(self.window.executor_paused)
        except (RuntimeError, TypeError):
            pass
        communicate.executor_paused.connect(self._executor_paused)

    def _executor_paused(self, paused: bool) -> None:
        window = self.window
        window.show_notification(window.tr("Start Success.") if not paused else window.tr("Pause Success."), tray=False)


def _noop(*_args, **_kwargs) -> None:
    return None


def _drop_old_touch_guards(window) -> None:
    """Take the old pages' touch-scroll guards off the application (they only cost time now)."""
    from PySide6.QtWidgets import QAbstractScrollArea, QApplication

    app = QApplication.instance()
    dropped = 0
    for area in window.findChildren(QAbstractScrollArea):
        guard = getattr(area, "_touch_scroll_click_guard", None)
        if guard is not None and app is not None:
            app.removeEventFilter(guard)
            dropped += 1
    logger.info(f"dropped {dropped} old touch-scroll guards")


def _hide_old_navigation(window) -> None:
    """Hide ok's navigation for good, including its pop-over menu mode."""
    nav = window.navigationInterface
    panel = nav.panel
    for target in (nav, panel):
        target.expand = _noop
        target.toggle = _noop
    window.removeEventFilter(panel)
    if panel.parent() is not nav:
        panel.hide()
        panel.setParent(nav)
        panel.move(0, 0)
    nav.hide()


def _tidy_title_bar(window) -> None:
    """The sidebar shows the name; keep the title bar for dragging and buttons."""
    bar = getattr(window, "titleBar", None)
    if bar is None:
        return
    for name in ("iconLabel", "titleLabel"):
        label = getattr(bar, name, None)
        if label is not None:
            label.hide()
    bar.raise_()


def _use_flat_background(window) -> None:
    """Plain ground colour instead of Windows 11 Mica, in both themes."""
    try:
        window.setMicaEffectEnabled(False)
    except Exception as exc:
        logger.warning(f"shell: mica off failed: {exc}")
    try:
        window.setCustomBackgroundColor(QColor(theme.LIGHT["bg"]), QColor(theme.DARK["bg"]))
    except Exception as exc:
        logger.warning(f"shell: background colour failed: {exc}")


def install_shell(window):
    if getattr(window, "_okkes_shell", None) is not None:
        return window._okkes_shell
    try:
        shell = Shell(window)
    except Exception as exc:
        logger.error("new main window pages failed, keeping the old ones", exc)
        return None
    window._okkes_shell = shell
    logger.info("new main window pages installed")
    return shell


__all__ = ["install_shell", "build_pages", "actions"]
