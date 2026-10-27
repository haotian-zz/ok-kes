# 刷刻印（utils_imprint）单测：法典面板/三选一卡片解析和合格判断（实机 2026-10-27 OCR）
import os
import sys
import unittest
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ok_tasks"))

import utils_imprint as ui  # noqa: E402


def box(x, y, name):
    return SimpleNamespace(x=x * 1920, y=y * 1080, width=0, height=0, name=name)


def task_with(boxes, **config):
    return SimpleNamespace(width=1920, height=1080, all_texts=boxes, config=config)


# 选择法典页，1 号法典（用户生成好的目标法典）
SELECT_PAGE = [box(0.122, 0.046, "零式系统"), box(0.077, 0.242, "选择法典"), box(0.741, 0.221, "裁决之沼"),
               box(0.755, 0.283, "10|等级80"), box(0.825, 0.341, "卡厄思之珠获得量增加100%"),
               box(0.170, 0.409, "1·101J-J-155"), box(0.779, 0.408, "回荡在银河中的歌声"),
               box(0.845, 0.448, "将会出现面具卡牌和刻印装备，稀有种"), box(0.815, 0.478, "战区将转换为面具战斗区。"),
               box(0.786, 0.557, "存储数据保存上限150PT"), box(0.787, 0.597, "稀有命运触发率增加50%"),
               box(0.798, 0.669, "[疾病4]生命值上限减少50%"), box(0.779, 0.707, "[精英4]追加8个精英区"),
               box(0.836, 0.752, "[复仇2]异形死亡时，其他异形获得士2"), box(0.935, 0.899, "进入")]
# 3 号槽：没有赛季特性、有暴君3
SLOT3 = [box(0.741, 0.221, "裁决之沼"), box(0.755, 0.283, "10|等级106"), box(0.825, 0.341, "卡厄思之珠获得量增加120%"),
         box(0.786, 0.406, "存储数据保存上限150PT"), box(0.787, 0.448, "稀有命运触发率增加50%"),
         box(0.839, 0.517, "[暴君3]精英、首领区异形的攻击力与命"), box(0.747, 0.548, "值增加30%"),
         box(0.828, 0.590, "[疏忽1]回合开始时，随机丢掉1张卡牌"), box(0.805, 0.632, "[硬化2]异形每3回合获得不屈2")]
# 获得法典三选一
PICK_PAGE = [box(0.501, 0.101, "获得法典"), box(0.499, 0.152, "请选择1个"),
             box(0.106, 0.292, "裁决之沼"), box(0.419, 0.292, "裁决之沼"), box(0.731, 0.292, "裁决之沼"),
             box(0.117, 0.346, "10|等级80"), box(0.441, 0.346, "10|等级79|"), box(0.742, 0.346, "10|等级78"),
             box(0.139, 0.457, "回荡在银河中的歌声"), box(0.452, 0.457, "回荡在银河中的歌声"),
             box(0.764, 0.457, "回荡在银河中的歌声"),
             box(0.146, 0.585, "存储数据保存上限160PT"), box(0.458, 0.585, "存储数据保存上限160PT"),
             box(0.753, 0.579, "迪亚洛斯的荣光"), box(0.146, 0.624, "稀有命运触发率增加20%"),
             box(0.459, 0.622, "稀有命运触发率增加50%"), box(0.808, 0.611, "进入卡厄思时遇到[物主迪亚洛斯]"),
             box(0.161, 0.685, "[硬化2]异形每3回合获得不屈2"), box(0.504, 0.685, "[暴君3]精英、首领区异形的攻击力与生命"),
             box(0.155, 0.722, "[疾病3]生命值上限减少40%"), box(0.424, 0.713, "值增加30%"),
             box(0.192, 0.758, "[暴君4]精英、首领区异形的攻击力与生命"), box(0.504, 0.749, "[坏疽3]从第二回合起，回合开始时，生命"),
             box(0.767, 0.781, "无法获取存储数据"), box(0.578, 0.922, "120"), box(0.752, 0.049, "3,016"),
             box(0.881, 0.048, "18926K"), box(0.264, 0.922, "57600")]


class TestCodexParse(unittest.TestCase):
    def test_target_codex_ok(self):
        t = task_with(SELECT_PAGE)
        info = ui.parse_codex(ui._region_lines(t, ui.PANEL))
        self.assertEqual(("裁决之沼", 10, 150, 50), (info["map"], info["difficulty"], info["pt"], info["rare"]))
        self.assertEqual([("疾病", 4), ("精英", 4), ("复仇", 2)], info["mods"])
        self.assertEqual([], ui.codex_problems(info, t))

    def test_slot3_rejected(self):
        t = task_with(SLOT3)
        bad = ui.codex_problems(ui.parse_codex(ui._region_lines(t, ui.PANEL)), t)
        self.assertTrue(any("赛季特性" in b for b in bad))
        self.assertTrue(any("暴君3" in b for b in bad))

    def test_pick_cards(self):
        t = task_with(PICK_PAGE)
        infos = [ui.parse_codex(ui._region_lines(t, r)) for r in ui.PICK_CARDS]
        problems = [ui.codex_problems(i, t) for i in infos]
        self.assertTrue(any("稀有命运" in b for b in problems[0]))     # 20%
        self.assertTrue(any("暴君" in b for b in problems[1]))
        self.assertTrue(any("无法获取存储数据" in b for b in problems[2]))
        self.assertEqual(120, ui.parse_amount(ui._region_text(t, (0.54, 0.89, 0.62, 0.95))))

    def test_unrest_banned_here(self):
        info = ui.parse_codex(["裁决之沼", "10|等级80", "回荡在银河中的歌声", "稀有命运触发率增加60%", "[不安1]……"])
        self.assertTrue(any("不安1" in b for b in ui.codex_problems(info, task_with([]))))

    def test_amounts(self):
        self.assertEqual(3016, ui.parse_amount("3,016"))
        self.assertEqual(18926000, ui.parse_amount("18926K"))
        self.assertEqual(57600, ui.parse_amount("57600"))


if __name__ == "__main__":
    unittest.main()
