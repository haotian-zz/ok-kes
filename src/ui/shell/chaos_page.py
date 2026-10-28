"""卡厄思页：顶部选方案，下面按段只显示当前方案会读的设置，再加一段「由方案决定」（只读）。

方案还是存在「卡厄思玩法」里，各项设置还是原来的键（configs/ChaosMode.json 格式不变）。
"""

from __future__ import annotations

import os

from PySide6.QtWidgets import QGridLayout, QWidget

from src.ui.shell import chaos_schema, chaos_stats
from src.ui.shell.config_form import ConfigForm
from src.ui.shell.task_page import TaskPage
from src.ui.shell.widgets import Button, Card, Segmented, Separator, Text, hbox, vbox


class ChaosPage(TaskPage):
    def __init__(self):
        super().__init__("shellChaos", "ChaosMode", "卡厄思", "选方案，下面只显示这个方案会用到的设置")
        self._decided_key = None
        self.section_cards: dict[str, tuple[QWidget, ConfigForm]] = {}

    # ---------------------------------------------------------------- build

    def build_settings(self, task) -> None:
        self.section_cards = {}
        self._decided_key = None
        scheme_card = Card()
        column = vbox(scheme_card, (22, 18, 22, 18), 10)
        head = hbox(None, (0, 0, 0, 0), 12)
        head.addWidget(Text("方案", "h2"))
        head.addStretch(1)
        column.addLayout(head)
        self.scheme = Segmented(chaos_schema.SCHEMES, chaos_schema.scheme_of(task.config), accent=True)
        self.scheme.changed.connect(self._scheme_picked)
        column.addWidget(self.scheme)
        self.scheme_hint = Text("", "sub", wrap=True)
        column.addWidget(self.scheme_hint)
        self.scheme_changes = Text("", "warn", wrap=True)
        self.scheme_changes.hide()
        column.addWidget(self.scheme_changes)
        self.content.addWidget(scheme_card)

        for title, keys in chaos_schema.SECTIONS:
            keys = [key for key in keys if key in task.config]
            if not keys:
                continue
            card = Card()
            box = vbox(card, (22, 16, 22, 16), 12)
            box.addWidget(Text(title, "h2"))
            form = ConfigForm(
                task, keys=keys, right_inset=4,
                on_change=self._setting_changed, extra_hidden=chaos_schema.extra_hidden,
            )
            box.addWidget(form)
            self.content.addWidget(card)
            self.section_cards[title] = (card, form)
            self.forms.append(form)
            if title == "入场":
                # 「由方案决定」紧跟在队伍、入场后面
                self._build_decided()

        foot = hbox(None, (0, 2, 0, 0), 12)
        foot.addWidget(Button("全部恢复默认", "ghost", size="sm", on_click=self._reset_all))
        foot.addWidget(Text("方案不会被恢复；改了马上存，下一帧生效", "muted"))
        foot.addStretch(1)
        self.content.addLayout(foot)

    def _build_decided(self) -> None:
        self.decided_card = Card()
        column = vbox(self.decided_card, (22, 16, 22, 16), 8)
        column.addWidget(Text("由方案决定（只读）", "h2"))
        self.decided_note = Text("", "sub", wrap=True)
        column.addWidget(self.decided_note)
        self.decided_warn = Text("", "warn", wrap=True)
        self.decided_warn.hide()
        column.addWidget(self.decided_warn)
        column.addWidget(Separator())
        self.decided_rows = QWidget()
        self.decided_grid = QGridLayout(self.decided_rows)
        self.decided_grid.setContentsMargins(0, 0, 0, 0)
        self.decided_grid.setHorizontalSpacing(16)
        self.decided_grid.setVerticalSpacing(6)
        self.decided_grid.setColumnStretch(1, 1)
        column.addWidget(self.decided_rows)
        self.content.addWidget(self.decided_card)

    # ---------------------------------------------------------------- refresh

    def refresh(self) -> None:
        super().refresh()
        task = self.task()
        if task is None or not self.section_cards:
            return
        mode = chaos_schema.scheme_of(task.config)
        self.scheme.set_value(mode)
        self.scheme_hint.set_text(chaos_schema.SCHEME_HINTS.get(mode, ""))
        for card, form in self.section_cards.values():
            card.setVisible(form.visible_count() > 0)
        self._refresh_decided(task)
        self._refresh_live(task)

    def _refresh_live(self, task) -> None:
        live = chaos_stats.read_live_run()
        lines = []
        if live is not None and not live.stale:
            pt = f"{live.pt_used}/{live.pt_cap}" if live.pt_cap else f"{live.pt_used}（上限未知）"
            lines.append(f"这一局 {live.started}：PT {pt}，复制 {live.copies}/{chaos_stats.COPY_CAP}，"
                         f"移除 {live.removes}/{chaos_stats.REMOVE_CAP}，第 {live.layers + 1} 层，第 {live.nodes} 个节点")
            extra = []
            if live.octopus_seen:
                extra.append("遇到章鱼哥")
            if live.chaos_core:
                extra.append(f"拿到{live.chaos_core}")
            if live.equipment:
                extra.append("装备 " + "、".join(live.equipment))
            if extra:
                lines.append("；".join(extra))
        info = getattr(task, "info", None) or {}
        lines += [f"{key}：{value}" for key, value in info.items()]
        if lines:
            self.info_text.set_text("\n".join(lines))

    def _refresh_decided(self, task) -> None:
        config = task.config
        try:
            deck_mtime = os.path.getmtime(chaos_schema.TARGET_DECK_FILE)
        except OSError:
            deck_mtime = 0
        key = (
            chaos_schema.scheme_of(config), config.get("目标主战员"), config.get("目标预设"),
            config.get(chaos_schema.OCTOPUS_RUSH), config.get(chaos_schema.IMPRINT_KEY),
            config.get("调整零式升级"), tuple(chaos_schema.hidden_but_active(config)), deck_mtime,
        )
        if key == self._decided_key:
            return
        self._decided_key = key
        try:
            decided = chaos_schema.decided_by_scheme(config)
        except Exception as exc:
            decided = {"note": f"算不出来：{exc}", "rows": [], "warnings": []}
        self.decided_note.set_text(decided["note"])
        self.decided_warn.set_text("\n".join(decided["warnings"]))
        self.decided_warn.setVisible(bool(decided["warnings"]))
        while self.decided_grid.count():
            item = self.decided_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # 先藏起来：deleteLater 要等回到事件循环，期间旧行会和新行叠在一起
                widget.hide()
                widget.deleteLater()
        for row, (name, value) in enumerate(decided["rows"]):
            self.decided_grid.addWidget(Text(name, "muted"), row, 0)
            self.decided_grid.addWidget(Text(value, "sub", wrap=True), row, 1)
        self.decided_rows.setVisible(bool(decided["rows"]))

    # ---------------------------------------------------------------- changes

    def _scheme_picked(self, mode: str) -> None:
        task = self.task()
        if task is None:
            return
        changes = chaos_schema.apply_scheme(task.config, mode)
        if changes:
            self.scheme_changes.set_text("切方案时联动：" + "，".join(changes))
            self.scheme_changes.show()
        else:
            self.scheme_changes.hide()
        self._setting_changed(chaos_schema.SCHEME_KEY)

    def _setting_changed(self, _key: str) -> None:
        for form in self.forms:
            form.sync()
        self.refresh()

    def _reset_all(self) -> None:
        for form in self.forms:
            form.reset()
        self.refresh()
