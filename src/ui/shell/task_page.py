"""一个任务一页：上面是开始/停止和运行状态，下面是这个任务自己的设置（ConfigForm）。

一键日常、出击、剧情用它；卡厄思页（chaos_page）在它上面加方案和分段。
"""

from __future__ import annotations

from src.ui.shell import actions, data
from src.ui.shell.config_form import ConfigForm
from src.ui.shell.page import Page, pill, set_pill
from src.ui.shell.widgets import Button, Card, Inset, Separator, Text, hbox, vbox


class TaskPage(Page):
    interval = 1500

    def __init__(self, object_name: str, class_name: str, title: str, sub: str = ""):
        super().__init__(object_name, title, sub)
        self.class_name = class_name
        self._task_id = None
        self.state_pill = pill()
        self.add_action(self.state_pill)
        self.start_button = self.add_action(Button("开始", "primary", "play", on_click=self._start))
        self.stop_button = self.add_action(Button("停止", "danger", "square", on_click=self._stop))
        self.content = vbox(None, (0, 0, 0, 0), 16)
        self.body.addLayout(self.content)
        self.body.addStretch(1)
        self.forms: list[ConfigForm] = []

    # ---------------------------------------------------------------- data

    def task(self):
        return data.task_by_class_name(self.class_name)

    # ---------------------------------------------------------------- build

    def build(self, task) -> None:
        """任务对象换了（改代码后框架重新加载）或第一次显示时重建下面的内容。"""
        from src.ui.shell.widgets import clear_layout

        clear_layout(self.content)
        self.forms = []
        description = str(getattr(task, "description", "") or "").strip()
        if description:
            note = Inset()
            hbox(note, (16, 10, 16, 10), 0).addWidget(Text(description, "sub", wrap=True))
            self.content.addWidget(note)
        self.info_card = Card()
        info = vbox(self.info_card, (20, 14, 20, 14), 6)
        info.addWidget(Text("这次运行", "h3"))
        self.info_text = Text("", "sub", wrap=True)
        info.addWidget(self.info_text)
        self.content.addWidget(self.info_card)
        self.build_settings(task)

    def build_settings(self, task) -> None:
        card = Card()
        column = vbox(card, (22, 18, 22, 18), 12)
        column.addWidget(Text("设置", "h2"))
        form = ConfigForm(task, right_inset=4)
        column.addWidget(form)
        column.addWidget(Separator())
        foot = hbox(None, (0, 2, 0, 0), 12)
        foot.addWidget(Button("恢复默认", "ghost", size="sm", on_click=form.reset))
        foot.addWidget(Text("改了马上存，下一帧生效", "muted"))
        foot.addStretch(1)
        column.addLayout(foot)
        self.content.addWidget(card)
        self.forms.append(form)

    # ---------------------------------------------------------------- refresh

    def refresh(self) -> None:
        task = self.task()
        if task is None:
            self.set_sub("没找到这个任务（ok_tasks 加载失败？看日志）")
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            return
        if id(task) != self._task_id:
            self._task_id = id(task)
            self.build(task)
        running = data.running(task)
        self.start_button.setVisible(not running)
        self.stop_button.setVisible(running)
        self.start_button.setEnabled(actions.can_start(task))
        set_pill(self.state_pill, "运行中" if running else "", "run" if running else None)
        info = getattr(task, "info", None) or {}
        lines = [f"{key}：{value}" for key, value in info.items()]
        self.info_text.set_text("\n".join(lines) if lines else ("运行中……" if running else "还没跑过"))
        for form in self.forms:
            form.sync()

    def _start(self) -> None:
        actions.start(self.task(), self.window())
        self.refresh()

    def _stop(self) -> None:
        actions.stop(self.task())
        self.refresh()
