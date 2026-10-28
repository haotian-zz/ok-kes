# 出击模式：难度、速刷（避战选路、第二层选完首领就退）、理智/体力补充的单测（用户 2026-10-27 要的四个开关）。
# 跑法：python -m unittest tests.TestSortie
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ok_tasks"))

import numpy as np  # noqa: E402

import utils  # noqa: E402
import utils_sortie as us  # noqa: E402


class _Box(types.SimpleNamespace):
    def area(self):
        return max(1, self.width * self.height)


def box(x, y, name, w=80, h=30):
    return _Box(x=x * 1920 - w / 2, y=y * 1080 - h / 2, width=w, height=h, name=name)


def sortie_task(config=None, texts=()):
    logs, clicks = [], []
    t = types.SimpleNamespace(name="自动出击模式", node_status=utils._initial_node_status(), config=dict(config or {}),
                              width=1920, height=1080, all_texts=list(texts), frame=None, enabled=True,
                              log_info=lambda *a, **k: logs.append(a[0]), log_error=lambda *a, **k: logs.append(a[0]),
                              log_debug=lambda *a, **k: None,
                              sleep=lambda s: None, move_relative=lambda x, y: None,
                              click=lambda x, y, **k: clicks.append((round(x, 3), round(y, 3))),
                              click_box=lambda b, **k: clicks.append(b.name))
    t.disable = lambda: setattr(t, "enabled", False)
    t.logs, t.clicks = logs, clicks
    return t


def lobby(level):
    return [box(0.499, 0.457, f"LV.{level}"), box(0.499, 0.900, "进入")]


class TestSortieLevel(unittest.TestCase):
    """出击入口页中间难度圈：V=LV.80（最高档）、IV=LV.65，左右箭头切档（2026-10-27 实机）。"""

    def test_reads_level_and_clicks_toward_target(self):
        t = sortie_task({us.SORTIE_LEVEL: 80}, lobby(65))
        self.assertEqual(us._read_sortie_level(t), 65)
        self.assertTrue(us.handle_sortie_lobby(t))
        self.assertEqual(t.clicks, [us.LEVEL_UP])

    def test_at_target_lets_enter_handle_it(self):
        t = sortie_task({us.SORTIE_LEVEL: 80}, lobby(80))
        self.assertFalse(us.handle_sortie_lobby(t))
        self.assertEqual(t.clicks, [])

    def test_zero_means_no_adjust(self):
        t = sortie_task({us.SORTIE_LEVEL: 0}, lobby(65))
        self.assertFalse(us.handle_sortie_lobby(t))
        self.assertEqual(t.clicks, [])

    def test_not_lobby_without_enter_button(self):
        t = sortie_task({us.SORTIE_LEVEL: 80}, lobby(65)[:1])
        self.assertFalse(us.handle_sortie_lobby(t))

    def test_gives_up_when_level_does_not_change(self):
        t = sortie_task({us.SORTIE_LEVEL: 95}, lobby(80))
        self.assertTrue(us.handle_sortie_lobby(t))      # 点一次
        self.assertTrue(us.handle_sortie_lobby(t))      # 没变，再试一次（可能点在动画里）
        self.assertFalse(us.handle_sortie_lobby(t))     # 还不变：到头了，交给「进入」
        self.assertEqual(len(t.clicks), 2)
        self.assertFalse(us.handle_sortie_lobby(t))
        self.assertEqual(len(t.clicks), 2)

    def test_target_between_levels_settles_lower(self):
        t = sortie_task({us.SORTIE_LEVEL: 70}, lobby(65))
        self.assertTrue(us.handle_sortie_lobby(t))
        t.all_texts = lobby(80)
        self.assertTrue(us.handle_sortie_lobby(t))      # 跨过 70，退回低一档
        self.assertEqual(t.clicks, [us.LEVEL_UP, us.LEVEL_DOWN])
        t.all_texts = lobby(65)
        self.assertFalse(us.handle_sortie_lobby(t))
        self.assertEqual(len(t.clicks), 2)

    def test_handlers_order(self):
        h = us.PAGE_HANDLERS
        self.assertLess(h.index(us.handle_sortie_lobby), h.index(utils.handle_enter))
        self.assertLess(h.index(us.handle_rational_supply), h.index(utils.handle_center_confirm))
        self.assertLess(h.index(us.handle_speedrun_exit), h.index(utils.handle_route_selection))
        self.assertEqual(h.count(us.handle_rational_supply), 1)


class TestSortieSpeedrun(unittest.TestCase):

    def test_speedrun_only_for_sortie(self):
        self.assertTrue(utils._sortie_speedrun(sortie_task({"速刷模式": True})))
        self.assertFalse(utils._sortie_speedrun(sortie_task({"速刷模式": False})))
        chaos = sortie_task({"速刷模式": True})
        chaos.name = "自动卡厄思模式"
        self.assertFalse(utils._sortie_speedrun(chaos))

    def test_route_avoids_battles(self):
        # 当前位置 → 上：普通战 → 精英 → 首领；下：事件 → 休息 → 首领
        nodes = [{"id": 0, "type": "当前位置", "row": 1}, {"id": 1, "type": "小怪", "row": 1},
                 {"id": 2, "type": "精英", "row": 1}, {"id": 3, "type": "事件", "row": 2},
                 {"id": 4, "type": "休息", "row": 2}, {"id": 5, "type": "结算", "row": 1}]
        map_info = {"nodes": nodes, "adjacency": {0: [1, 3], 1: [2], 2: [5], 3: [4], 4: [5]}}
        t = sortie_task({"速刷模式": True, "路线优先级": ["精英", "小怪", "事件", "休息"]})
        priority = utils._get_route_priority(t)
        self.assertEqual(priority, ["休息", "事件", "小怪", "精英"])      # 速刷不看配置的路线优先级
        plan = utils.find_best_map_route_by_priority(map_info, priority, utils._chaos_route_weights(t))
        self.assertEqual(plan["route"][:3], [0, 3, 4])

    def test_settlement_does_not_exit_on_layer_one(self):
        t = sortie_task({"速刷模式": True, "只打第一层": True})
        t.node_status["pass_final_boss_count"] = 1
        self.assertFalse(utils._finish_only_first_layer(t))
        self.assertEqual(t.clicks, [])
        self.assertEqual(t.node_status["success_rounds"], 0)
        # 没开速刷：只打第一层照旧在结算页退出
        t2 = sortie_task({"只打第一层": True})
        t2.node_status["pass_final_boss_count"] = 1
        self.assertTrue(utils._finish_only_first_layer(t2))
        self.assertEqual(t2.clicks, [(0.959, 0.051)])

    def _boss_page(self):
        return [box(0.484, 0.928, "请选择要遇见的首领"), box(0.358, 0.706, "首领甲"), box(0.641, 0.706, "首领乙")]

    def test_first_layer_boss_choice_does_not_exit(self):
        t = sortie_task({"速刷模式": True}, self._boss_page())
        self.assertTrue(us.handle_boss_selection(t))
        self.assertFalse(t.node_status.get("speedrun_exit"))

    def test_exit_after_layer_two_boss_chosen(self):
        t = sortie_task({"速刷模式": True}, self._boss_page())
        t.node_status["pass_final_boss_count"] = 1
        self.assertTrue(us.handle_boss_selection(t))
        self.assertTrue(t.node_status["speedrun_exit"])
        orig = us.is_route_selection_page
        us.is_route_selection_page = lambda task: True
        try:
            t.clicks.clear()
            self.assertTrue(us.handle_speedrun_exit(t))
            self.assertEqual(t.clicks, [(0.959, 0.051)])
            self.assertEqual(t.node_status["success_rounds"], 1)
            self.assertTrue(us.handle_speedrun_exit(t))          # 3 秒内不重复点
            self.assertEqual(len(t.clicks), 1)
            t.node_status["speedrun_exit_clicked_at"] -= 5
            self.assertTrue(us.handle_speedrun_exit(t))          # 菜单没出来，再点一次，不重复记成功
            self.assertEqual(len(t.clicks), 2)
            self.assertEqual(t.node_status["success_rounds"], 1)
            t.node_status["is_escaped"] = True
            self.assertFalse(us.handle_speedrun_exit(t))
        finally:
            us.is_route_selection_page = orig

    def test_no_exit_without_speedrun(self):
        t = sortie_task({}, self._boss_page())
        t.node_status["pass_final_boss_count"] = 1
        self.assertTrue(us.handle_boss_selection(t))
        self.assertFalse(us.handle_speedrun_exit(t))


class TestBattleMemberSelect(unittest.TestCase):
    """实录 2026-10-28 00:09：海德玛丽在第二排，第一屏只有排第四的绯，原来直接选了绯。"""

    def _list_task(self, pages, priority):
        t = sortie_task({"出战主战员优先级": priority})
        t.pos = 0

        def ocr():
            return [box(0.2 + 0.15 * i, 0.48, n) for i, n in enumerate(pages[t.pos])]

        def scroll_relative(x, y, n):
            t.pos = min(len(pages) - 1, t.pos + 1) if n < 0 else max(0, t.pos - 1)

        t.ocr, t.scroll_relative = ocr, scroll_relative
        t.is_adb = lambda: False
        t.feature_exists = lambda name: False
        t.all_texts = ocr()
        return t

    def _run(self, t):
        orig = us._confirm_battle_member_selection
        us._confirm_battle_member_selection = lambda task: True
        try:
            self.assertTrue(us._select_battle_member(t))
        finally:
            us._confirm_battle_member_selection = orig

    def test_top_priority_on_later_page(self):
        pages = [["凛", "罗丝薇瑟", "绯"], ["绯", "海德玛丽", "黛安娜"], ["蒂菲拉", "米卡"]]
        t = self._list_task(pages, ["海德玛丽", "九", "力", "绯"])
        self._run(t)
        self.assertEqual(t.clicks, ["海德玛丽"])

    def test_fallback_scrolls_back_to_lower_priority(self):
        pages = [["凛", "罗丝薇瑟", "绯"], ["黛安娜", "雨果"], ["蒂菲拉", "米卡"]]
        t = self._list_task(pages, ["海德玛丽", "九", "力", "绯"])
        self._run(t)
        self.assertEqual(t.clicks, ["绯"])
        self.assertEqual(t.pos, 0)

    def test_first_page_top_priority_no_scroll(self):
        pages = [["海德玛丽", "绯"], ["米卡"]]
        t = self._list_task(pages, ["海德玛丽", "绯"])
        self._run(t)
        self.assertEqual(t.clicks, ["海德玛丽"])
        self.assertEqual(t.pos, 0)


class TestAutoPlayFast(unittest.TestCase):
    """局内剧情右上角自动播放按钮要两档（用户 2026-10-28：只加速了一次）。实机一档：左箭头亮 166、右 35。"""

    def _task(self, left, right):
        frame = np.zeros((1080, 1920, 3), np.uint8)
        cx, cy = 1688, 86                       # 「Ctrl」中心
        if left:
            frame[cy - 40:cy - 20, cx - 14:cx - 4] = 220
        if right:
            frame[cy - 40:cy - 20, cx + 2:cx + 12] = 220
        t = sortie_task(texts=[box(cx / 1920, cy / 1080, "Ctrl", w=40, h=20)])
        t.frame = frame
        return t

    def test_levels(self):
        self.assertEqual(utils._auto_play_level(self._task(False, False))[0], 0)
        self.assertEqual(utils._auto_play_level(self._task(True, False))[0], 1)
        self.assertEqual(utils._auto_play_level(self._task(True, True))[0], 2)

    def test_clicks_until_two_then_stops(self):
        t = self._task(True, False)
        self.assertTrue(utils._ensure_auto_play_fast(t))
        self.assertEqual(len(t.clicks), 1)
        x, y = t.clicks[0]
        self.assertAlmostEqual(x, 0.879, places=2)
        self.assertLess(y, 0.06)
        t2 = self._task(True, True)
        self.assertFalse(utils._ensure_auto_play_fast(t2))
        self.assertEqual(t2.clicks, [])

    def test_click_limit(self):
        t = self._task(False, False)
        for _ in range(utils.AUTO_PLAY_MAX_CLICKS):
            t._auto_play_clicks = [c - 2 for c in getattr(t, "_auto_play_clicks", [])]
            self.assertTrue(utils._ensure_auto_play_fast(t))
        t._auto_play_clicks = [c - 2 for c in t._auto_play_clicks]
        self.assertFalse(utils._ensure_auto_play_fast(t))       # 认错状态也不会一直转圈
        self.assertEqual(len(t.clicks), utils.AUTO_PLAY_MAX_CLICKS)

    def test_no_ctrl_label_falls_back(self):
        t = self._task(True, True)
        t.all_texts = []
        self.assertIsNone(utils._ensure_auto_play_fast(t))


class TestHardcore(unittest.TestCase):
    """主战员配置页顶部硬核开关（2026-10-28 实机：开=白色旋钮在右）。"""

    def _task(self, on, want):
        frame = np.zeros((1080, 1920, 3), np.uint8)
        if on:
            x, y = int(0.684 * 1920), int(0.049 * 1080)
            frame[y - 8:y + 8, x - 8:x + 8] = 240
        t = sortie_task({us.HARDCORE: want}, [box(0.130, 0.043, "主战员配置")])
        t.frame = frame
        return t

    def test_detects_state(self):
        self.assertTrue(us._hardcore_on(self._task(True, True)))
        self.assertFalse(us._hardcore_on(self._task(False, True)))

    def test_turns_on_when_wanted(self):
        t = self._task(False, True)
        self.assertTrue(us.handle_battle_member_config(t))
        self.assertEqual(t.clicks, [us.HARDCORE_TOGGLE])

    def test_turns_off_when_not_wanted(self):
        t = self._task(True, False)
        self.assertTrue(us._ensure_hardcore(t))
        self.assertEqual(t.clicks, [us.HARDCORE_TOGGLE])

    def test_matching_state_no_click(self):
        t = self._task(True, True)
        self.assertFalse(us._ensure_hardcore(t))
        self.assertEqual(t.clicks, [])

    def test_gives_up_after_three(self):
        t = self._task(False, True)
        for _ in range(3):
            self.assertTrue(us._ensure_hardcore(t))
        self.assertFalse(us._ensure_hardcore(t))
        self.assertEqual(len(t.clicks), 3)

    def test_stop_when_ether_short(self):
        t = sortie_task({}, [box(0.502, 0.139, "以太补充")])
        self.assertTrue(us.handle_ether_supply(t))
        self.assertFalse(t.enabled)


class TestSortieSanity(unittest.TestCase):

    def _supply(self, cfg, active):
        t = sortie_task(cfg, [box(0.500, 0.180, "补充理性"), box(0.664, 0.774, "确认"), box(0.352, 0.774, "放弃补充")])
        orig = us.is_button_active
        us.is_button_active = lambda task, b: active
        try:
            self.assertTrue(us.handle_rational_supply(t))
        finally:
            us.is_button_active = orig
        return t

    def test_refill_with_stamina_when_enabled(self):
        t = self._supply({us.USE_SANITY: True, us.SANITY_REFILL: True}, active=True)
        self.assertEqual(t.clicks, ["确认"])
        self.assertFalse(getattr(t, "_sanity_exhausted", False))

    def test_give_up_when_refill_disabled(self):
        t = self._supply({us.USE_SANITY: True, us.SANITY_REFILL: False}, active=True)
        self.assertEqual(t.clicks, [(0.352, 0.774)])
        self.assertTrue(t._sanity_exhausted)
        self.assertFalse(us._use_sanity(t))
        self.assertEqual(t.config[us.USE_SANITY], True)     # 不改用户配置

    def test_give_up_when_stamina_short(self):
        t = self._supply({us.USE_SANITY: True, us.SANITY_REFILL: True}, active=False)
        self.assertEqual(t.clicks, [(0.352, 0.774)])
        self.assertTrue(t._sanity_exhausted)

    def test_stop_at_lobby_after_sanity_exhausted(self):
        t = sortie_task({us.USE_SANITY: True, us.SORTIE_LEVEL: 80}, lobby(80))
        t._sanity_exhausted = True
        self.assertTrue(us.handle_sortie_lobby(t))
        self.assertFalse(t.enabled)

    def test_reward_claim_follows_sanity_switch(self):
        title = box(0.503, 0.335, "卡厄思战利品")
        t = sortie_task({us.USE_SANITY: True}, [title])
        self.assertTrue(us.handle_sortie_reward_claim(t))
        self.assertEqual(t.clicks, [(0.567, 0.708)])
        t = sortie_task({us.USE_SANITY: False}, [title])
        self.assertTrue(us.handle_sortie_reward_claim(t))
        self.assertEqual(t.clicks, [(0.355, 0.714)])


if __name__ == "__main__":
    unittest.main()
