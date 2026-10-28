"""有顺序的列表设置（卡牌、装备、主战员……）：一排小标签，可删、可往前挪，输入框带搜索提示。

可以填库里没有的字（很多列表按「包含」匹配，填半个卡名也行）；库里一张都对不上的标签画成提醒色，
悬停说明「库里找不到」，打错字一眼能看出来。
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QStringListModel, Qt, Signal
from PySide6.QtWidgets import QCompleter, QFrame, QWidget
from qfluentwidgets import FlowLayout, LineEdit

from src.ui.shell import theme
from src.ui.shell.widgets import Button, Text, hbox, vbox


def suggestions(source: str | None) -> list[str]:
    """``config_type['suggest']`` -> 候选名字（主战员 / 卡牌 / 各号位装备）。"""
    if not source:
        return []
    try:
        import game_db

        if source == "members":
            return list(game_db.combatant_names())
        db = game_db.get_db()
        if source == "cards":
            return db.card_names()
        if source.startswith("equipment"):
            slot = int(source[len("equipment"):] or 0) or None
            return db.equipment_names(slot=slot)
    except Exception:
        return []
    return []


def known_check(source: str | None, options: list[str]) -> Callable[[str], bool] | None:
    """返回「这个值库里对得上吗」的判断；自由文字（没有候选）返回 None，不提醒。"""
    if options:
        allowed = set(options)
        return lambda text: text in allowed
    names = suggestions(source)
    if not names:
        return None
    if source == "members":
        def member_known(text: str) -> bool:
            if text in names:
                return True
            try:
                import game_db

                return game_db.get_db().combatant(text) is not None
            except Exception:
                return False

        return member_known
    # 卡牌、装备按「包含」匹配（任务里就是这么认的：填「缕光芒」能认「一缕光芒」）
    return lambda text: any(text in name or name in text for name in names)


class _Chip(QFrame):
    def __init__(self, text: str, index: int, known: bool, on_remove, on_left, parent=None):
        super().__init__(parent)
        self.setObjectName("tagChip")
        self.setAttribute(Qt.WA_StyledBackground, True)
        tone = "chip" if known else "chip_warn"
        t = theme.tokens()
        bg = t["accent_soft"] if known else t["warn_soft"]
        ink = t["ink"] if known else t["warn"]
        self.setStyleSheet(
            f"QFrame#tagChip {{ background: {bg}; border-radius: 12px; }}"
            f"QFrame#tagChip QLabel {{ color: {ink}; font-size: 12px; }}"
        )
        self.setProperty("tone", tone)
        row = hbox(self, (4, 0, 2, 0), 0)
        if index > 0:
            left = Button("", "flat", "chevron-left", size="sm", on_click=on_left)
            left.setToolTip("往前挪一位（越靠前越优先）")
            left.setFixedSize(22, 22)
            row.addWidget(left)
        else:
            row.addSpacing(6)
        label = Text(f"{index + 1}. {text}" if index >= 0 else text)
        if not known:
            label.setToolTip("库里找不到这个名字（按包含也对不上），检查有没有打错字")
        row.addWidget(label)
        close = Button("", "flat", "x", size="sm", on_click=on_remove)
        close.setToolTip("删掉")
        close.setFixedSize(22, 22)
        row.addWidget(close)
        self.setFixedHeight(26)


class TagList(QWidget):
    """``changed`` 发出新的列表（顺序就是优先级）。"""

    changed = Signal(list)

    def __init__(self, values, source: str | None = None, options: list[str] | None = None, parent=None):
        super().__init__(parent)
        self._values: list[str] = [str(v) for v in (values or [])]
        self._options = list(options or [])
        self._known = known_check(source, self._options)
        column = vbox(self, (0, 0, 0, 0), 6)
        self._chips_box = QWidget(self)
        self._flow = FlowLayout(self._chips_box, needAni=False)
        self._flow.setContentsMargins(0, 0, 0, 0)
        self._flow.setHorizontalSpacing(6)
        self._flow.setVerticalSpacing(6)
        column.addWidget(self._chips_box)
        self.edit = LineEdit(self)
        names = self._options or suggestions(source)
        self.edit.setPlaceholderText("输入后回车添加" + ("，可搜索" if names else ""))
        self.edit.setClearButtonEnabled(True)
        self.edit.setFixedWidth(240)
        if names:
            completer = QCompleter(QStringListModel(names, self), self)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            completer.setMaxVisibleItems(12)
            self.edit.setCompleter(completer)
        self.edit.returnPressed.connect(self._add_from_edit)
        column.addWidget(self.edit)
        self._rebuild()

    def values(self) -> list[str]:
        return list(self._values)

    def set_values(self, values) -> None:
        values = [str(v) for v in (values or [])]
        if values != self._values:
            self._values = values
            self._rebuild()

    def _add_from_edit(self) -> None:
        text = self.edit.text().strip()
        if not text:
            return
        self.edit.clear()
        if text in self._values:
            return
        self._values.append(text)
        self._commit()

    def _remove(self, index: int) -> None:
        if 0 <= index < len(self._values):
            del self._values[index]
            self._commit()

    def _left(self, index: int) -> None:
        if 0 < index < len(self._values):
            self._values[index - 1], self._values[index] = self._values[index], self._values[index - 1]
            self._commit()

    def _commit(self) -> None:
        self._rebuild()
        self.changed.emit(list(self._values))

    def _rebuild(self) -> None:
        while self._flow.count():
            item = self._flow.takeAt(0)
            widget = item.widget() if hasattr(item, "widget") else item
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        if not self._values:
            empty = Text("（空）", "muted", self._chips_box)
            self._flow.addWidget(empty)
        for index, text in enumerate(self._values):
            known = True if self._known is None else bool(self._known(text))
            chip = _Chip(
                text, index, known,
                lambda i=index: self._remove(i), lambda i=index: self._left(i), self._chips_box,
            )
            self._flow.addWidget(chip)
        self._chips_box.updateGeometry()
        self.updateGeometry()
