"""关于：版本、项目链接、赞赏、开源说明。"""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from src.ui.shell.page import Page
from src.ui.shell.settings import HubRow
from src.ui.shell.widgets import Card, Separator, Text, vbox


def _links() -> dict:
    try:
        from src.config import config

        return (config.get("links") or {}).get("default") or {}
    except Exception:
        return {}


def _version() -> str:
    try:
        from src.config import version

        return str(version)
    except Exception:
        return "?"


class AboutPage(Page):
    interval = 60000

    def __init__(self, window):
        super().__init__("shellAbout", "关于", f"卡厄思梦境助手 ok-kes · 版本 {_version()}")
        self._window = window
        links = _links()
        card = Card()
        column = vbox(card, (16, 8, 16, 8), 0)
        rows = [
            ("code", "项目主页", links.get("github", ""), lambda: self._open(links.get("github"))),
            ("download", "下载", "GitHub Releases、Mirror酱、网盘", lambda: self._open(links.get("github", "") + "/releases")),
            ("message-circle-heart", "QQ 频道", links.get("qq_channel", ""), lambda: self._open(links.get("qq_channel"))),
            ("heart", "赞赏支持", "如果喜欢这个工具，可以赞赏作者持续开发", self._sponsor),
        ]
        for index, (icon, title, sub, click) in enumerate(rows):
            if index:
                column.addWidget(Separator())
            column.addWidget(HubRow(icon, title, sub, on_click=click))
        self.body.addWidget(card)
        notice = Card()
        notes = vbox(notice, (20, 14, 20, 14), 6)
        notes.addWidget(Text("开源说明", "h3"))
        notes.addWidget(Text(
            "基于 ok-script 框架。新界面（src/ui/shell）取自 YES-BD2（GPL-3.0，https://github.com/nobell001/YES-BD2），"
            "这部分文件按 GPL-3.0 发布；图标来自 Lucide（ISC）。详见 THIRD_PARTY_NOTICES.md。",
            "sub", wrap=True))
        self.body.addWidget(notice)
        self.body.addStretch(1)

    @staticmethod
    def _open(url) -> None:
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _sponsor(self) -> None:
        from src.ui.SponsorDialog import SponsorDialog

        SponsorDialog(self.window()).exec()
