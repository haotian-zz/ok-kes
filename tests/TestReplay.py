# 场景回放测试（tests/replay.py）：实录截图 + 预存 OCR 按帧喂给页面处理函数，断言操作序列。只在 Windows 跑（要 ok 框架）
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ok_tasks"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import chaos_strategy  # noqa: E402
import utils  # noqa: E402
import utils_imprint  # noqa: E402
from replay import Frame, ReplayTask, load_frames, replay  # noqa: E402

MEMBER2 = (0.756, 0.544)     # 安装装备页第 2 号主战员那一行（点它＝装给他）


def equip_task(frames):
    """2026-10-27 18:02 那局的状态：刷刻印、第二层，刷存档主战员（2 号）3 号位记的是「女神之泪」+ 目标刻印。"""
    t = ReplayTask(frames, config={"刷刻印": True, "装备3号位优先级": ["深绿黑夜"]},
                   default_config={"刷存档主战员": "海德玛丽"},
                   chaos_mode=chaos_strategy.MODE_TARGET, node_status={"pass_final_boss_count": 1})
    t.member_status = {"equipment": {"names": ["", "兜帽", "女神之泪"], "descriptions": ["", "", ""],
                                     "qualities": ["", "史诗", "史诗"], "imprints": ["", "目标", "目标"]},
                       "deck": {}}
    return t


class TestEquipmentReplay(unittest.TestCase):
    def test_fixture_reads_like_live(self):
        # 回放帧和实机日志一致：标题/提示认得出、待装备是 3 号位史诗、无刻印，3 个 leveltag、头像绑定 2 号
        t = equip_task(load_frames("equip_1802.json"))
        self.assertEqual("装备", utils.find_box_at_point(t, 0.499, 0.126).name)
        info = utils._equipment_info(t, (0.217, 0.379, 0.469, 0.436), (0.188, 0.444, 0.323, 0.489),
                                     (0.179, 0.492, 0.542, 0.668))
        self.assertEqual(("深绿黑夜", 2, "史诗", 0), (info["name"], info["slot"], info["quality"], info["rank"]))
        self.assertEqual("", utils_imprint.equipment_imprint(t, info["description"])[0])
        tags = utils._find_member_level_tags(t, (0.609, 0.290, 0.652, 0.789))
        self.assertEqual(3, len(tags))
        self.assertEqual(1, utils._find_target_member_index(t, tags, (0.607, 0.192, 0.739, 0.856), "target_member_tiny"))

    def test_no_refine_after_picking_member(self):
        # fee1447：18:02:14 点 2 号主战员安装深绿黑夜，18:02:16 同一页又进 handle_equipment，账上已记成装好，
        # 判成「品质史诗不高于史诗」提炼掉了。修复后 8 秒内同一件不重判，交给确认按钮
        # 18:02:14 那帧没存图，两次都用 18:02:16 那帧（同一帧喂两次）
        t = equip_task(load_frames("equip_1802.json", order=[0, 0]))
        first, second = replay(utils.handle_equipment, t)
        self.assertEqual([MEMBER2], [(round(a.x, 3), round(a.y, 3)) for a in first.actions if a.kind == "click"])
        self.assertEqual("深绿黑夜", t.member_status["equipment"]["names"][2])
        self.assertFalse(second.ret)
        self.assertEqual([], second.actions)
        self.assertTrue(any("等确认按钮" in m for m in second.logs))
        self.assertFalse(any(a.target == "提炼" for a in t.actions))

    def test_pick_member_then_confirm(self):
        # 复盘 4.6 的验收：按 ChaosMode.run 的顺序跑装备页附近的处理函数，动作是「点主战员 → 点确认」，不能出现「提炼」
        t = equip_task(load_frames("equip_1802.json", order=[0, 0]))
        steps = replay([utils.handle_equipment, utils.handle_card_assign, utils.handle_confirm], t)
        self.assertEqual(["handle_confirm", "handle_confirm"], [s.ret for s in steps])
        self.assertEqual([("click", ""), ("click_box", "确认"), ("click_box", "确认")],
                         [(a.kind, a.target) for a in t.actions if a.kind != "move"])
        self.assertEqual(MEMBER2, t.clicks()[0])

    def test_rejudge_after_pending_expires(self):
        # 8 秒后还停在这页（确认按钮一直没处理）才重新判断，这时账上已是深绿黑夜，按规则提炼
        t = equip_task(load_frames("equip_1802.json", order=[0, 0]))
        t.frame_interval = 9
        first, second = replay(utils.handle_equipment, t)
        self.assertIn(MEMBER2, t.clicks())
        self.assertTrue(second.ret)
        self.assertEqual(["提炼"], [a.target for a in second.actions if a.kind == "click_box"])


GOD_PAGE = [(0.890, 0.051, "查看原件"), (0.50, 0.80, "闪光：维托尔")]


class TestGodSparkWait(unittest.TestCase):
    """d63efac：神闪变体页等「跳过」最多 3 次。战斗后的神闪页（队友黑云奥义：灭，闪光：维托尔）根本没有「跳过」，
    以前等 8 次（每次 0.8 秒），之后才按普通闪光处理。没有当时截图，用纯文字帧。"""

    def _run(self, frames):
        t = ReplayTask(frames, chaos_mode=chaos_strategy.MODE_TARGET, chaos_plan={"flash": []})
        old = utils.recognize_cards
        utils.recognize_cards = lambda task, page="": []     # 普通闪光那套要卡牌特征，这里只看等不等
        try:
            return t, replay(utils.handle_view_original, t)
        finally:
            utils.recognize_cards = old

    def test_gives_up_after_three_waits(self):
        t, steps = self._run([Frame.from_texts(GOD_PAGE)] * 5)
        self.assertEqual([True, True, True, False], [s.ret for s in steps[:4]])
        self.assertTrue(any("第 3 次" in m for m in steps[2].logs))
        self.assertTrue(any("等不到「跳过」" in m for m in steps[3].logs))
        self.assertEqual([], t.actions)

    def test_clicks_skip_when_it_shows_up(self):
        frames = [Frame.from_texts(GOD_PAGE)] * 2 + [Frame.from_texts(GOD_PAGE + [(0.75, 0.93, "跳过")])]
        t, steps = self._run(frames)
        self.assertEqual(["跳过"], [a.target for a in t.actions])
        self.assertEqual(0, t.node_status["god_skip_waits"])


if __name__ == "__main__":
    unittest.main()
