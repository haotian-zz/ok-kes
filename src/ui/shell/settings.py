"""设置：颜色、通知、OCR、配置上传和几个文件夹。ok 原来的设置页不再有入口（用户 2026-10-28）。"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from qfluentwidgets import ComboBox

from src.ui.shell import actions, theme
from src.ui.shell.page import Page
from src.ui.shell.widgets import (
    Card,
    IconLabel,
    IconTile,
    Segmented,
    Separator,
    Text,
    Toggle,
    hbox,
    vbox,
)

THEME_LABELS = {"light": "淡紫", "dark": "深色", "auto": "跟随系统"}


def _global_config(name: str):
    from ok import og

    global_config = getattr(getattr(og, "executor", None), "global_config", None)
    if global_config is None:
        return None
    try:
        return global_config.get_config(name)
    except Exception:
        return None


def _get(name: str, key: str, default):
    config = _global_config(name)
    return config.get(key, default) if config is not None else default


def _set(name: str, key: str, value) -> None:
    config = _global_config(name)
    if config is not None:
        config[key] = value


class HubRow(QWidget):
    """Icon, title, one line under it, and a control or an arrow on the right."""

    def __init__(self, icon_name: str, title: str, sub: str = "", on_click: Callable | None = None,
                 control: QWidget | None = None, parent=None):
        super().__init__(parent)
        self._on_click = on_click
        layout = hbox(self, (2, 8, 2, 8), 12)
        tile = IconTile(icon_name, 32, 17)
        if on_click is not None and control is None:
            tile.follow_hover(self)
        layout.addWidget(tile)
        texts = vbox(None, (0, 0, 0, 0), 1)
        texts.addWidget(Text(title, "h3"))
        self.sub = Text(sub, "muted", wrap=True)
        self.sub.setVisible(bool(sub))
        texts.addWidget(self.sub)
        layout.addLayout(texts, 1)
        if control is not None:
            layout.addWidget(control)
        elif on_click is not None:
            layout.addWidget(IconLabel("chevron-right", 16, "ink3"))
            self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._on_click is not None:
            self._on_click()
        super().mouseReleaseEvent(event)


class SettingsPage(Page):
    interval = 3000

    def __init__(self, window):
        super().__init__("shellSettings", "设置", "外观、通知、识别和文件夹")
        self._window = window

        look = self._section("外观")
        self.theme_switch = Segmented(list(THEME_LABELS), theme.theme_mode(), labels=THEME_LABELS)
        self.theme_switch.changed.connect(theme.set_theme_mode)
        look.addWidget(HubRow("sun-moon", "颜色", "淡紫、深色，或跟着 Windows 的设定", control=self.theme_switch))

        notify = self._section("通知")
        from ok.util.GlobalConfig import NOTIFICATION_OPTION_NAME, SYSTEM_NOTIFICATION_ENABLED

        self._notify_keys = (NOTIFICATION_OPTION_NAME, SYSTEM_NOTIFICATION_ENABLED)
        self.notify_toggle = Toggle(bool(_get(*self._notify_keys, True)))
        self.notify_toggle.toggled.connect(lambda on: _set(*self._notify_keys, bool(on)))
        notify.addWidget(HubRow("bell", "系统通知", "跑完、出错时在 Windows 右下角跳出通知", control=self.notify_toggle))

        recognise = self._section("识别")
        from src.config import OCR_BACKEND_AUTO, OCR_BACKEND_ONNX, OCR_BACKEND_OPENVINO

        self._ocr_options = [OCR_BACKEND_AUTO, OCR_BACKEND_ONNX, OCR_BACKEND_OPENVINO]
        self.ocr_box = ComboBox()
        self.ocr_box.addItems(self._ocr_options)
        self.ocr_box.setMinimumWidth(150)
        self.ocr_box.currentIndexChanged.connect(self._ocr_picked)
        recognise.addWidget(HubRow(
            "scroll-text", "OCR 后端",
            "自动＝内存不少于 12GB 的 Intel 设备用 OpenVINO，其他用 ONNX Runtime；改了重启工具生效",
            control=self.ocr_box))
        recognise.addWidget(Separator())
        self.upload_toggle = Toggle(bool(_get("配置上传", "是否上传配置", False)))
        self.upload_toggle.toggled.connect(lambda on: _set("配置上传", "是否上传配置", bool(on)))
        recognise.addWidget(HubRow(
            "send", "上传匿名配置", "每 5 分钟上传匿名的配置和胜率，帮助统计热门配置；不上传账号、截图、IP",
            control=self.upload_toggle))

        folders = self._section("文件夹")
        folders.addWidget(HubRow("scroll-text", "日志", "出问题时把这里的文件发给开发者",
                                 on_click=lambda: actions.open_folder("logs")))
        folders.addWidget(Separator())
        folders.addWidget(HubRow("image", "截图", "出错时的截图", on_click=lambda: actions.open_folder("screenshots")))
        folders.addWidget(Separator())
        folders.addWidget(HubRow("folder-open", "运行数据", "卡厄思每局记录、流程追踪（dev_out）",
                                 on_click=lambda: actions.open_folder("dev_out")))
        folders.addWidget(Separator())
        folders.addWidget(HubRow("settings", "配置文件", "各任务的设置（configs）",
                                 on_click=lambda: actions.open_folder("configs")))
        self.body.addStretch(1)

    def _section(self, title: str):
        self.body.addWidget(Text(title, "eyebrow"))
        card = Card()
        column = vbox(card, (16, 8, 16, 8), 0)
        self.body.addWidget(card)
        return column

    def _ocr_picked(self, index: int) -> None:
        if 0 <= index < len(self._ocr_options):
            _set("OCR设置", "OCR后端", self._ocr_options[index])

    def refresh(self) -> None:
        self.theme_switch.set_value(theme.theme_mode())
        self.notify_toggle.set_checked_quietly(bool(_get(*self._notify_keys, True)))
        self.upload_toggle.set_checked_quietly(bool(_get("配置上传", "是否上传配置", False)))
        current = _get("OCR设置", "OCR后端", self._ocr_options[0])
        index = self._ocr_options.index(current) if current in self._ocr_options else 0
        if self.ocr_box.currentIndex() != index:
            self.ocr_box.blockSignals(True)
            self.ocr_box.setCurrentIndex(index)
            self.ocr_box.blockSignals(False)
