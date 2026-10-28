"""使用说明（精简版）：第一次用要做的几件事、四个方案怎么选。"""

from __future__ import annotations

from src.ui.shell.page import Page
from src.ui.shell.widgets import Card, Text, vbox

STEPS = [
    ("开始前", [
        "打开国服 PC 客户端，停在主页（或卡厄思里也行）。",
        "游戏设置 → 键盘 → 快捷键显示保持 ON（识别手牌要用卡牌上的按键提示）。",
        "国际服请在各任务的「游戏语言」里选繁体中文。",
    ]),
    ("卡厄思的四个方案", [
        "探索度：活动卡厄思打最高难度，优先没见过的事件选项；到设定的探索度等级会自动改成目标卡组。",
        "刷存档-空存：把目标主战员的卡删光，到第一个航点存好档就逃脱；可以按顺序换几个目标。",
        "刷存档-目标卡组：按目标主战员的预设构筑删卡、复制、闪光；里面还能开章鱼哥速刷、刷刻印。",
        "原有逻辑：不推导，按页面里的删卡/闪光/复制/路线列表跑。",
        "切到一个方案后，页面只显示这个方案会用到的设置；「由方案决定」那一段是自动推导、改不了的值。",
    ]),
    ("运行中", [
        "一次只跑一个任务：先停止正在跑的，再开始另一个。",
        "首页的卡厄思卡片显示这一局的 PT、复制和移除次数；每局结束记到「运行记录」。",
        "停止按钮随时可以按；局内停下后再开始，会读回这一局的账继续。",
    ]),
]


class GuidePage(Page):
    interval = 60000

    def __init__(self):
        super().__init__("shellGuide", "使用说明", "第一次用先看这里")
        for title, lines in STEPS:
            card = Card()
            column = vbox(card, (22, 16, 22, 16), 8)
            column.addWidget(Text(title, "h2"))
            for index, line in enumerate(lines, 1):
                column.addWidget(Text(f"{index}. {line}", "sub", wrap=True))
            self.body.addWidget(card)
        self.body.addStretch(1)
