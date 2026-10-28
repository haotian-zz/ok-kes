"""首页：卡厄思卡片（方案、目标、这一局的账、本轮统计）和各任务的快捷入口。"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QWidget

from src.ui.shell import actions, chaos_schema, chaos_stats, data
from src.ui.shell.page import Page, pill, set_pill
from src.ui.shell.widgets import Bar, Button, Card, IconTile, Inset, Separator, Text, hbox, vbox


class Stat(QWidget):
    """一个小数字块：上面说明，下面数值。"""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        column = vbox(self, (0, 0, 0, 0), 2)
        column.addWidget(Text(label, "muted"))
        self.value = Text("-", "h2")
        column.addWidget(self.value)

    def set(self, text: str, role: str = "h2") -> None:
        self.value.set_text(text)
        self.value.set_role(role)


class HomePage(Page):
    interval = 2000

    def __init__(self, navigate: Callable[[str], None]):
        super().__init__("shellHome", "首页", "卡厄思梦境助手")
        self._navigate = navigate
        self._build_chaos()
        self._build_tasks()
        self.body.addStretch(1)

    # ---------------------------------------------------------------- 卡厄思

    def _build_chaos(self) -> None:
        card = Card()
        column = vbox(card, (22, 18, 22, 18), 12)
        head = hbox(None, (0, 0, 0, 0), 12)
        head.addWidget(IconTile("sparkles", 40, 22), 0, Qt.AlignTop)
        titles = vbox(None, (0, 0, 0, 0), 2)
        self.chaos_title = Text("卡厄思", "h2")
        self.chaos_sub = Text("", "sub", wrap=True)
        titles.addWidget(self.chaos_title)
        titles.addWidget(self.chaos_sub)
        head.addLayout(titles, 1)
        self.chaos_pill = pill()
        head.addWidget(self.chaos_pill, 0, Qt.AlignTop)
        self.chaos_open = Button("设置", "secondary", "sliders-horizontal", size="sm",
                                 on_click=lambda: self._navigate("chaos"))
        head.addWidget(self.chaos_open, 0, Qt.AlignTop)
        self.chaos_start = Button("开始", "primary", "play", size="sm", on_click=self._chaos_start)
        self.chaos_stop = Button("停止", "danger", "square", size="sm", on_click=self._chaos_stop)
        head.addWidget(self.chaos_start, 0, Qt.AlignTop)
        head.addWidget(self.chaos_stop, 0, Qt.AlignTop)
        column.addLayout(head)

        live = Inset()
        live_column = vbox(live, (16, 12, 16, 12), 8)
        self.live_title = Text("这一局", "h3")
        live_column.addWidget(self.live_title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)
        self.stat_pt = Stat("PT 已用 / 上限")
        self.stat_copy = Stat("复制")
        self.stat_remove = Stat("移除")
        self.stat_layer = Stat("层 · 节点")
        for index, stat in enumerate((self.stat_pt, self.stat_copy, self.stat_remove, self.stat_layer)):
            grid.addWidget(stat, 0, index)
        live_column.addLayout(grid)
        self.pt_bar = Bar(height=5)
        live_column.addWidget(self.pt_bar)
        self.live_note = Text("", "muted", wrap=True)
        live_column.addWidget(self.live_note)
        column.addWidget(live)

        session = Inset()
        session_column = vbox(session, (16, 12, 16, 12), 8)
        self.session_title = Text("本轮", "h3")
        session_column.addWidget(self.session_title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        self.stat_runs = Stat("局数")
        self.stat_octopus = Stat("遇到章鱼哥")
        self.stat_core = Stat("掉混沌之识")
        self.stat_results = Stat("结果")
        for index, stat in enumerate((self.stat_runs, self.stat_octopus, self.stat_core, self.stat_results)):
            grid.addWidget(stat, 0, index)
        session_column.addLayout(grid)
        self.last_run = Text("", "muted", wrap=True)
        session_column.addWidget(self.last_run)
        row = hbox(None, (0, 0, 0, 0), 8)
        row.addStretch(1)
        row.addWidget(Button("全部运行记录", "ghost", "history", size="sm", on_click=lambda: self._navigate("runs")))
        session_column.addLayout(row)
        column.addWidget(session)
        self.body.addWidget(card)

    def _refresh_chaos(self) -> None:
        task = data.chaos_task()
        if task is None:
            self.chaos_sub.set_text("卡厄思任务没加载（看日志）")
            self.chaos_start.setEnabled(False)
            return
        config = task.config
        mode = chaos_schema.scheme_of(config)
        parts = [f"方案：{mode}"]
        if mode != chaos_schema.MODE_LEGACY:
            parts.append(f"目标：{config.get('目标主战员', '')}")
            if mode in (chaos_schema.MODE_EXPLORE, chaos_schema.MODE_TARGET):
                parts.append(f"{config.get('目标预设', 1)} 号预设")
        subs = []
        if mode == chaos_schema.MODE_TARGET:
            if config.get(chaos_schema.OCTOPUS_RUSH) is True:
                subs.append("章鱼哥速刷" + ("（只认混沌之识）" if config.get(chaos_schema.OCTOPUS_CORE_ONLY) is True else ""))
            if config.get(chaos_schema.IMPRINT_KEY) is True:
                subs.append("刷刻印")
        if mode == chaos_schema.MODE_EMPTY and config.get(chaos_schema.EMPTY_TARGETS):
            subs.append("目标顺序 " + "→".join(config.get(chaos_schema.EMPTY_TARGETS)))
        if subs:
            parts.append(" · ".join(subs))
        self.chaos_sub.set_text("　".join(parts))
        running = data.running(task)
        set_pill(self.chaos_pill, "运行中" if running else "", "run" if running else None)
        self.chaos_start.setVisible(not running)
        self.chaos_stop.setVisible(running)
        self.chaos_start.setEnabled(actions.can_start(task))

        live = chaos_stats.read_live_run()
        if live is not None and not live.stale:
            self.live_title.set_text(f"这一局（{live.started or '开始时间未知'}）")
            cap = live.pt_cap or 0
            self.stat_pt.set(f"{live.pt_used}/{cap}" if cap else f"{live.pt_used}/?",
                             "bad" if cap and live.pt_used is not None and live.pt_used >= cap else "h2")
            self.pt_bar.set_value(min(1.0, (live.pt_used or 0) / cap) if cap else 0.0)
            self.stat_copy.set(f"{live.copies}/{chaos_stats.COPY_CAP}")
            self.stat_remove.set(f"{live.removes}/{chaos_stats.REMOVE_CAP}")
            self.stat_layer.set(f"{live.layers + 1} · {live.nodes}")
            notes = []
            if live.octopus_seen:
                notes.append("遇到章鱼哥")
            if live.chaos_core:
                notes.append(f"拿到{live.chaos_core}")
            if live.equipment:
                notes.append("装备 " + "、".join(live.equipment))
            self.live_note.set_text("；".join(notes))
            self.live_note.setVisible(bool(notes))
        else:
            self.live_title.set_text("这一局：不在局内")
            for stat in (self.stat_pt, self.stat_copy, self.stat_remove, self.stat_layer):
                stat.set("-", "h2")
            self.pt_bar.set_value(0.0)
            self.live_note.set_text("")
            self.live_note.hide()

        runs = chaos_stats.read_runs()
        session = chaos_stats.session_runs(runs)
        summary = chaos_stats.summarize(session)
        if session:
            mode_text = chaos_stats.scheme_label(session[-1])
            self.session_title.set_text(f"本轮（{summary.first[5:16]} 起，{mode_text}）")
        else:
            self.session_title.set_text("本轮：还没有记录")
        self.stat_runs.set(str(summary.runs))
        self.stat_octopus.set(str(summary.octopus))
        self.stat_core.set(str(summary.chaos_core), "ok" if summary.chaos_core else "h2")
        results = "、".join(f"{name}{count}" for name, count in summary.results.items())
        self.stat_results.set(results or "-", "sub" if results else "h2")
        if runs:
            last = runs[-1]
            reason = last.get("reason") or ""
            self.last_run.set_text(f"上一局 {last.get('time', '')}：{last.get('result', '')}"
                                   + (f"（{reason}）" if reason else ""))
        else:
            self.last_run.set_text("")

    def _chaos_start(self) -> None:
        actions.start(data.chaos_task(), self.window())
        self.refresh()

    def _chaos_stop(self) -> None:
        actions.stop(data.chaos_task())
        self.refresh()

    # ---------------------------------------------------------------- 其他任务

    def _build_tasks(self) -> None:
        self.body.addWidget(Text("其他任务", "eyebrow"))
        card = Card()
        column = vbox(card, (16, 8, 16, 8), 0)
        self.task_rows = {}
        for index, (key, class_name) in enumerate((k, v) for k, v in data.PAGE_TASKS.items() if k != "chaos"):
            if index:
                column.addWidget(Separator())
            name, icon = data.TASK_LOOK[class_name]
            row = QWidget()
            line = hbox(row, (2, 8, 2, 8), 12)
            line.addWidget(IconTile(icon, 32, 17))
            texts = vbox(None, (0, 0, 0, 0), 1)
            texts.addWidget(Text(name, "h3"))
            state = Text("", "muted")
            texts.addWidget(state)
            line.addLayout(texts, 1)
            line.addWidget(Button("设置", "secondary", size="sm", on_click=lambda k=key: self._navigate(k)))
            start = Button("开始", "primary", "play", size="sm",
                           on_click=lambda c=class_name: self._start(c))
            stop = Button("停止", "danger", "square", size="sm", on_click=lambda c=class_name: self._stop(c))
            line.addWidget(start)
            line.addWidget(stop)
            column.addWidget(row)
            self.task_rows[class_name] = (state, start, stop)
        self.body.addWidget(card)

    def _refresh_tasks(self) -> None:
        for class_name, (state, start, stop) in self.task_rows.items():
            task = data.task_by_class_name(class_name)
            running = data.running(task)
            state.set_text("没加载" if task is None else ("运行中" if running else "没在跑"))
            start.setVisible(not running)
            stop.setVisible(running)
            start.setEnabled(actions.can_start(task))

    def _start(self, class_name: str) -> None:
        actions.start(data.task_by_class_name(class_name), self.window())
        self.refresh()

    def _stop(self, class_name: str) -> None:
        actions.stop(data.task_by_class_name(class_name))
        self.refresh()

    def refresh(self) -> None:
        self._refresh_chaos()
        self._refresh_tasks()
