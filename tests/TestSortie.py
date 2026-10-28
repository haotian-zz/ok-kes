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
    return _Box(x=x * 1920 - w / 2, y=y * 1080 - h / 2, width=w, height=h, name=name, confidence=1.0)


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

    def test_boss_choice_means_layer_one_done(self):
        # 出击模式第一层不选首领；首领节点不是脚本点进去时结算页没记层数，选首领页兜底记上（2026-10-28 00:50 实录速刷没退）
        t = sortie_task({"速刷模式": True}, self._boss_page())
        self.assertTrue(us.handle_boss_selection(t))
        self.assertEqual(t.node_status["pass_final_boss_count"], 1)
        self.assertTrue(t.node_status.get("speedrun_exit"))

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

    def test_exit_from_event_page_via_menu(self):
        # 用户 2026-10-28：选完首领就退，不用等路线页；事件/对白页右上角有 Q 菜单就点
        t = sortie_task({"速刷模式": True}, [box(0.959, 0.080, "Q", w=20), box(0.310, 0.938, "询问物主的意图")])
        t.node_status["speedrun_exit"] = True
        orig = us.is_route_selection_page
        us.is_route_selection_page = lambda task: False
        try:
            self.assertTrue(us.handle_speedrun_exit(t))
            self.assertEqual(t.clicks, [(0.959, 0.051)])
            # 菜单开了：逃脱按钮在，点逃脱，不再点菜单
            t.all_texts = [box(0.952, 0.928, "逃脱")]
            t.node_status["speedrun_exit_clicked_at"] -= 5
            self.assertTrue(us.handle_speedrun_exit(t))
            self.assertEqual(t.clicks[-1], "逃脱")
            self.assertTrue(t.node_status["is_escaped"])
            # 没有 Q 菜单的页面（加载、过场）不点
            t2 = sortie_task({"速刷模式": True}, [box(0.5, 0.5, "加载中")])
            t2.node_status["speedrun_exit"] = True
            self.assertFalse(us.handle_speedrun_exit(t2))
        finally:
            us.is_route_selection_page = orig

    def test_no_exit_without_speedrun(self):
        t = sortie_task({}, self._boss_page())
        t.node_status["pass_final_boss_count"] = 1
        self.assertTrue(us.handle_boss_selection(t))
        self.assertFalse(us.handle_speedrun_exit(t))


class TestSortieLayerCount(unittest.TestCase):
    """卡厄思战利品结算页只在层首领打完后出现：reach_final_boss 没置上（首领节点不是脚本点的）时补记层数，只记一次。"""

    def test_counts_once_when_settlement_missed(self):
        t = sortie_task()
        us._count_sortie_layer(t)
        us._count_sortie_layer(t)            # 领完战利品回到结算页
        self.assertEqual(t.node_status["pass_final_boss_count"], 1)

    def test_not_double_counted_after_settlement_button(self):
        t = sortie_task(texts=[box(0.941, 0.917, "结算")])
        t.node_status["reach_final_boss"] = True
        self.assertTrue(utils.handle_settlement(t))
        self.assertEqual(t.node_status["pass_final_boss_count"], 1)
        us._count_sortie_layer(t)
        self.assertEqual(t.node_status["pass_final_boss_count"], 1)

    def test_next_layer_counts_again(self):
        t = sortie_task(texts=[box(0.484, 0.928, "请选择要遇见的首领"), box(0.358, 0.706, "首领甲")])
        us._count_sortie_layer(t)
        self.assertTrue(us.handle_boss_selection(t))
        us._count_sortie_layer(t)
        self.assertEqual(t.node_status["pass_final_boss_count"], 2)


def card(name, x=0.5, y=0.4):
    return {"name": name, "x": x, "y": y, "type": "", "description": "", "selected": False, "feature_name": "attack_in_deck"}


class TestLeaderCards(unittest.TestCase):
    """用户 2026-10-28：只拿出战主战员（海德玛丽）的卡，中立卡和别人的卡不拿；删卡先删别人的卡。"""

    RULES = {utils.SORTIE_LEADER_CARDS_ONLY: True, utils.SORTIE_REMOVE_OTHERS_FIRST: True,
             "出战主战员优先级": ["海德玛丽", "九", "力", "绯"], "获得卡牌优先级": ["展开极光", "剑雨"]}

    def test_card_side(self):
        t = sortie_task(self.RULES)
        side = lambda n: utils.sortie_card_side(t, n)  # noqa: E731
        self.assertEqual(side("剑雨"), "leader")
        self.assertEqual(side("缕光芒"), "leader")            # OCR 丢了「一」
        self.assertEqual(side("万众英雄"), "leader")
        self.assertEqual(side("极寒风暴"), "other")           # 麦格纳的
        self.assertEqual(side("水之源"), "other")             # 米卡的
        self.assertEqual(side("绽放：保持耐心"), "neutral")
        self.assertEqual(side("未知：变异体样本"), "neutral")
        self.assertEqual(side("剑甫"), "unknown")

    def test_leader_from_member_selection(self):
        t = sortie_task(self.RULES)
        t._sortie_leader = "麦格纳"
        self.assertEqual(utils.sortie_card_side(t, "极寒风暴"), "leader")
        self.assertEqual(utils.sortie_card_side(t, "剑雨"), "other")

    def _get_card(self, config, names):
        t = sortie_task(config, [box(0.502, 0.128, "获得卡牌"), box(0.883, 0.131, "请选择要获得的卡牌")])
        cards = [card(n, 0.2 + 0.28 * i) for i, n in enumerate(names)]
        orig = us.recognize_cards
        us.recognize_cards = lambda task, page="": cards
        try:
            self.assertTrue(us.handle_get_card(t))
        finally:
            us.recognize_cards = orig
        return t

    def test_get_card_takes_any_leader_card(self):
        t = self._get_card(self.RULES, ["极寒风暴", "万众英雄", "绽放：保持耐心"])
        self.assertEqual(t.clicks, [(0.48, 0.4), (0.912, 0.931)])

    def test_get_card_priority_among_leader_cards(self):
        t = self._get_card(self.RULES, ["万众英雄", "剑雨", "展开极光"])
        self.assertEqual(t.clicks, [(0.76, 0.4), (0.912, 0.931)])

    def test_get_card_skips_others_and_neutral(self):
        t = self._get_card(self.RULES, ["极寒风暴", "冰寒之息", "绽放：酸性气体"])
        self.assertEqual(t.clicks, [(0.749, 0.931)])

    def test_get_card_rule_off_keeps_priority_only(self):
        t = self._get_card({"获得卡牌优先级": ["剑雨"]}, ["万众英雄", "极寒风暴"])
        self.assertEqual(t.clicks, [(0.749, 0.931)])

    def test_card_reward_takes_leader_card(self):
        t = sortie_task(self.RULES, [box(0.49, 0.07, "卡牌奖励")])
        cards = [card("水之源", 0.2), card("凝聚极光", 0.5), card("绽放：保持耐心", 0.8)]
        orig = utils.recognize_cards, utils.find_target_card
        utils.recognize_cards = lambda task, page="": cards
        utils.find_target_card = lambda task: ([], [])
        try:
            self.assertTrue(utils.handle_card_reward(t))
        finally:
            utils.recognize_cards, utils.find_target_card = orig
        self.assertEqual(t.clicks, [(0.5, 0.4)])

    def test_card_reward_skips_without_leader_card(self):
        t = sortie_task(self.RULES, [box(0.49, 0.07, "卡牌奖励"), box(0.80, 0.93, "跳过")])
        cards = [card("水之源", 0.2), card("梦之边境", 0.5)]
        orig = utils.recognize_cards, utils.find_target_card
        utils.recognize_cards = lambda task, page="": cards
        utils.find_target_card = lambda task: ([], [])
        try:
            self.assertTrue(utils.handle_card_reward(t))
        finally:
            utils.recognize_cards, utils.find_target_card = orig
        self.assertEqual(t.clicks, ["跳过"])

    def _remove(self, config, names):
        t = sortie_task(config)
        t.ocr = lambda: []
        t.box_of_screen = lambda *a, **k: None
        cards = [card(n, 0.15 + 0.12 * i) for i, n in enumerate(names)]
        patches = {"recognize_cards_in_deck": lambda task, page="": [dict(c) for c in cards],
                   "_dump_card_page": lambda task, tag: None,
                   "region_white_ratio": lambda task, region: 0.0,
                   "_trace_card_click": lambda *a, **k: None}
        orig = {k: getattr(utils, k) for k in patches}
        for k, v in patches.items():
            setattr(utils, k, v)
        try:
            self.assertTrue(utils.select_card(t, ["剑幕"], count=1, action="移除"))
        finally:
            for k, v in orig.items():
                setattr(utils, k, v)
        return t

    def test_remove_other_member_card_first(self):
        t = self._remove(self.RULES, ["剑幕", "剑光", "极寒风暴", "剑雨"])
        self.assertEqual(t.clicks, [(0.39, 0.4)])

    def test_remove_rule_off_uses_remove_list(self):
        t = self._remove({}, ["剑幕", "剑光", "极寒风暴", "剑雨"])
        self.assertEqual(t.clicks, [(0.15, 0.4)])


class TestRaisedCardName(unittest.TestCase):
    """鼠标悬停的卡放大上移，卡名落进类型区域（10-28 01:16 实录：水之源；00:51 漏了海德玛丽的万众英雄）。"""

    def test_name_taken_from_type_region(self):
        feats = {"attack": (0.4609, 0.3472, 0.917), "enhance": (0.6646, 0.3093, 0.784)}
        texts = [box(0.4974, 0.3106, "协调：毁灭"), box(0.4786, 0.3463, "攻击"), box(0.50, 0.60, "伤害432%"),
                 box(0.7094, 0.3162, "日", w=20), box(0.7516, 0.3088, "水之源"), box(0.71, 0.55, "回复体力")]
        t = sortie_task(texts=texts)
        t.box_of_screen = lambda *a, **k: None
        t.find_feature = lambda feature_name, box=None, threshold=0: (
            [types.SimpleNamespace(x=feats[feature_name][0] * 1920 - 10, y=feats[feature_name][1] * 1080 - 10,
                                   width=20, height=20, confidence=feats[feature_name][2])]
            if feature_name in feats else [])
        cards = utils.recognize_cards(t, page="获得卡牌页面")
        self.assertEqual([c["name"] for c in cards], ["协调：毁灭", "水之源"])
        self.assertEqual(cards[1]["type"], "强化")
        self.assertAlmostEqual(cards[1]["x"], 0.7516, places=3)      # 点卡名本身，不点推算的空区域
        self.assertAlmostEqual(cards[1]["y"], 0.3088, places=3)

    def test_type_words_not_names(self):
        t = sortie_task(texts=[box(0.5, 0.3, "④技能"), box(0.55, 0.3, "基础攻击"), box(0.6, 0.3, "日", w=20)])
        self.assertIsNone(utils._raised_card_name_box(t, (0.4, 0.2, 0.7, 0.4)))


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
        self.assertEqual(t._sortie_leader, "海德玛丽")      # 拿牌/删牌按这位算

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
        frame[cy - 40:cy - 20, cx - 14:cx - 12] = 220     # 灰箭头也有零星亮点（实机一档右边灰箭头 35）
        frame[cy - 40:cy - 20, cx + 2:cx + 4] = 220
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

    def _confirm(self, t):
        """第一帧只记下来；假装 1 秒后又读到同一档。"""
        self.assertFalse(utils._ensure_auto_play_fast(t))
        t._auto_play_pending = (t._auto_play_pending[0], t._auto_play_pending[1] - 1)

    def test_clicks_until_two_then_stops(self):
        t = self._task(True, False)
        self._confirm(t)
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
            self._confirm(t)
            self.assertTrue(utils._ensure_auto_play_fast(t))
        t._auto_play_clicks = [c - 2 for c in t._auto_play_clicks]
        self._confirm(t)
        self.assertFalse(utils._ensure_auto_play_fast(t))       # 认错状态也不会一直转圈
        self.assertEqual(len(t.clicks), utils.AUTO_PLAY_MAX_CLICKS)

    def test_dark_frame_not_judged(self):
        # 实录 00:45:48：淡入淡出时两边都是 0，当成关着点了一下
        t = self._task(True, True)
        t.frame[:] = 0
        self.assertIsNone(utils._auto_play_level(t)[0])
        self.assertFalse(utils._ensure_auto_play_fast(t))
        self.assertEqual(t.clicks, [])

    def test_missed_ctrl_after_seen_does_not_fall_back(self):
        # 实录 00:47:05：前一帧认出两档，下一帧 OCR 漏了 Ctrl，旧模板逻辑又点了一下
        t = self._task(True, True)
        self.assertFalse(utils._ensure_auto_play_fast(t))
        t.all_texts = []
        self.assertFalse(utils._ensure_auto_play_fast(t))

    def test_single_odd_frame_not_clicked(self):
        # 实录 01:08:24：两档读得好好的，一帧读成一档就点了；要连续两帧同一档才点
        t = self._task(True, True)
        self.assertFalse(utils._ensure_auto_play_fast(t))
        t1 = self._task(True, False)
        t1.__dict__.update({k: v for k, v in t.__dict__.items() if k.startswith("_auto_play")})
        self.assertFalse(utils._ensure_auto_play_fast(t1))       # 第一帧一档：先不点
        t2 = self._task(True, True)
        t2.__dict__.update({k: v for k, v in t1.__dict__.items() if k.startswith("_auto_play")})
        self.assertFalse(utils._ensure_auto_play_fast(t2))       # 下一帧又是两档：不点，清掉
        self.assertIsNone(t2._auto_play_pending)
        self.assertEqual(t1.clicks + t2.clicks, [])

    def test_no_ctrl_label_falls_back(self):
        t = self._task(True, True)
        t.all_texts = []
        self.assertIsNone(utils._ensure_auto_play_fast(t))


class TestHardcore(unittest.TestCase):
    """主战员配置页顶部硬核开关（2026-10-28 实机：开=白色旋钮在右）。"""

    def _task(self, on, want, extra=()):
        frame = np.zeros((1080, 1920, 3), np.uint8)
        if on:
            x, y = int(0.684 * 1920), int(0.049 * 1080)
            frame[y - 8:y + 8, x - 8:x + 8] = 240
        texts = [box(0.130, 0.043, "主战员配置"), box(0.188, 0.799, "海德玛丽"), box(0.708, 0.189, "LV.65"),
                 box(0.719, 0.912, "进入")] + list(extra)
        t = sortie_task({us.HARDCORE: want}, texts)
        t.frame = frame
        return t

    def test_detects_state(self):
        self.assertTrue(us._hardcore_on(self._task(True, True)))
        self.assertFalse(us._hardcore_on(self._task(False, True)))

    def test_turns_on_when_wanted(self):
        t = self._task(False, True)
        self.assertTrue(us.handle_battle_member_config(t))
        self.assertEqual(t.clicks, [us.HARDCORE_TOGGLE])

    def test_enters_when_matching(self):
        t = self._task(True, True)
        self.assertTrue(us.handle_battle_member_config(t))
        self.assertEqual(t.clicks, [(0.719, 0.914)])

    def test_popup_dimmed_page_not_toggled(self):
        # 实录 00:44：点完进入弹出确认框，画面压暗，不能当成「关着」去点开关
        t = self._task(False, True, [box(0.936, 0.916, "确认")])
        self.assertTrue(us.handle_battle_member_config(t))
        self.assertNotIn(us.HARDCORE_TOGGLE, t.clicks)

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
