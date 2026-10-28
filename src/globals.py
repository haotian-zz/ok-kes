from PySide6.QtCore import QObject

from ok import Logger

logger = Logger.get_logger(__name__)


class Globals(QObject):

    def __init__(self, exit_event):
        super().__init__()

    def on_show_main_window(self, main_window):
        """主窗口第一次显示前：装上新界面（侧栏 + 新页面），ok 原来的导航藏起来。"""
        from src.ui.shell.install import install_shell

        install_shell(main_window)
