"""运行记录：dev_out/chaos_runs.jsonl 一局一行，新的在上面，可以按方案筛。"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidgetItem
from qfluentwidgets import TableWidget

from src.ui.shell import actions, chaos_schema, chaos_stats
from src.ui.shell.page import Page
from src.ui.shell.widgets import Button, Card, Segmented, Text, hbox, vbox

FILTERS = ["全部", *chaos_schema.SCHEMES, "刷刻印"]
OPTIONAL_COLUMNS = ("混沌之识", "刻印", "装备")
MAX_ROWS = 500


class RunsPage(Page):
    interval = 5000

    def __init__(self):
        super().__init__("shellRuns", "运行记录", "卡厄思每局结束记一行（dev_out/chaos_runs.jsonl）")
        self._filter = "全部"
        self._stamp = None
        bar = hbox(None, (0, 0, 0, 0), 12)
        self.filter = Segmented(FILTERS, self._filter)
        self.filter.changed.connect(self._filter_picked)
        bar.addWidget(self.filter)
        bar.addStretch(1)
        bar.addWidget(Button("打开文件夹", "secondary", "folder-open", size="sm",
                             on_click=lambda: actions.open_folder(os.path.dirname(chaos_stats.runs_path()) or ".")))
        self.body.addLayout(bar)
        card = Card()
        column = vbox(card, (16, 14, 16, 14), 10)
        self.summary = Text("", "sub", wrap=True)
        column.addWidget(self.summary)
        self.table = TableWidget()
        self.table.setColumnCount(len(chaos_stats.COLUMNS))
        self.table.setHorizontalHeaderLabels(chaos_stats.COLUMNS)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        # 装备、刻印可能很长：给固定宽度（可拖），剩下的宽度都给原因；全文在悬停提示里
        for name, width in (("刻印", 140), ("装备", 180)):
            index = chaos_stats.COLUMNS.index(name)
            header.setSectionResizeMode(index, QHeaderView.Interactive)
            self.table.setColumnWidth(index, width)
        header.setSectionResizeMode(chaos_stats.COLUMNS.index("原因"), QHeaderView.Stretch)
        self.table.setMinimumHeight(420)
        column.addWidget(self.table)
        self.body.addWidget(card, 1)

    def _filter_picked(self, value: str) -> None:
        self._filter = value
        self._stamp = None
        self.refresh()

    def refresh(self) -> None:
        path = chaos_stats.runs_path()
        try:
            stamp = (os.path.getmtime(path), os.path.getsize(path), self._filter)
        except OSError:
            stamp = (0, 0, self._filter)
        if stamp == self._stamp:
            return
        self._stamp = stamp
        runs = chaos_stats.read_runs(path)
        shown = chaos_stats.filter_runs(runs, self._filter)
        summary = chaos_stats.summarize(shown)
        results = "、".join(f"{name} {count}" for name, count in summary.results.items())
        self.summary.set_text(
            f"共 {len(runs)} 局，当前筛出 {summary.runs} 局"
            + (f"（{results}）" if results else "")
            + f"；遇到章鱼哥 {summary.octopus} 局，掉混沌之识 {summary.chaos_core} 局"
        )
        rows = list(reversed(shown))[:MAX_ROWS]
        cells = [chaos_stats.row(record) for record in rows]
        # 筛出来的这些局都没有的列（比如没开刷刻印就没有刻印）藏起来，把宽度留给原因
        for c, name in enumerate(chaos_stats.COLUMNS):
            if name in OPTIONAL_COLUMNS:
                self.table.setColumnHidden(c, not any(line[c] for line in cells))
        self.table.setRowCount(len(rows))
        for r, line in enumerate(cells):
            for c, text in enumerate(line):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                if c in (chaos_stats.COLUMNS.index("层"), chaos_stats.COLUMNS.index("PT")):
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, c, item)
