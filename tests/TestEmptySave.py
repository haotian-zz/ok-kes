# 刷存档-空存（刷空档）的单测：目标的卡闪光计数、闪够了逃脱重开、第一个航点逃脱、按顺序换目标、
# 事件闪光选项一律不选、商店只删卡（用户 2026-10-28）。
# 跑法：python -m unittest tests.TestEmptySave
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ok_tasks"))

import chaos_strategy as cs  # noqa: E402
import run_state  # noqa: E402
import save_cleanup as sc  # noqa: E402
import utils  # noqa: E402
import utils_chaos  # noqa: E402

ORDER = ["希露德", "玛丽贝尔", "凛", "蒂菲拉"]


class _Box(types.SimpleNamespace):
    def area(self):
        return max(1, self.width * self.height)


def box(x, y, name, w=80, h=30):
    return _Box(x=x * 1920 - w / 2, y=y * 1080 - h / 2, width=w, height=h, name=name, confidence=1.0)


def card(name, x=0.3, y=0.5):
    return {"name": name, "description": "", "x": x, "y": y}


def empty_task(target="希露德", texts=(), mode=cs.MODE_EMPTY, config=None):
    logs, clicks = [], []
    cfg = {"目标主战员": target, utils.EMPTY_TARGETS: list(ORDER)}
    cfg.update(config or {})
    t = types.SimpleNamespace(name="卡厄思模式", node_status=utils._initial_node_status(), config=cfg,
                              width=1920, height=1080, all_texts=list(texts), frame=None, chaos_mode=mode,
                              log_info=lambda *a, **k: logs.append(a[0]), log_error=lambda *a, **k: logs.append(a[0]),
                              log_debug=lambda *a, **k: None,
                              sleep=lambda s: None, move_relative=lambda x, y: None,
                              click=lambda x, y, **k: clicks.append((round(x, 3), round(y, 3))),
                              click_box=lambda b, **k: clicks.append(b.name))
    t.setups = 0

    def setup_strategy():
        t.setups += 1
        t.chaos_overrides = dict(cs.config_overrides(t.chaos_mode, t.config["目标主战员"]), 刷存档主战员=t.config["目标主战员"])
    setup_strategy()
    t.setups = 0
    t.setup_strategy = setup_strategy
    t.logs, t.clicks = logs, clicks
    return t


class TestFlashCount(unittest.TestCase):
    def test_card_side(self):
        self.assertEqual("leader", utils.card_side("追踪箭", "希露德"))
        self.assertEqual("other", utils.card_side("水之源", "希露德"))

    def test_target_flash_counted_once_per_page(self):
        t = empty_task()
        cards = [card("追踪箭", 0.25), card("追踪箭", 0.5), card("追踪箭", 0.75)]
        self.assertTrue(utils.record_empty_flash(t, cards))
        self.assertFalse(utils.record_empty_flash(t, cards))        # 同一页下一帧（选中/确认）不再记
        self.assertEqual(1, t.node_status["empty_flashes"])
        t.node_status["node_count"] += 1
        self.assertTrue(utils.record_empty_flash(t, cards))         # 下一个节点又闪了同一张，记第二次
        self.assertEqual(2, t.node_status["empty_flashes"])

    def test_teammate_flash_not_counted(self):
        t = empty_task()
        self.assertFalse(utils.record_empty_flash(t, [card("水之源"), card("水之源"), card("水之源")]))
        self.assertEqual(0, t.node_status.get("empty_flashes", 0))

    def test_unknown_owner_counted(self):
        # 三张都认不出归属：宁可多重开，不存坏档
        t = empty_task()
        self.assertTrue(utils.record_empty_flash(t, [card("嗷嗷嗷"), card("呜呜呜"), card("啦啦啦")]))
        self.assertEqual(1, t.node_status["empty_flashes"])

    def test_other_modes_ignored(self):
        t = empty_task(mode=cs.MODE_TARGET)
        self.assertFalse(utils.record_empty_flash(t, [card("追踪箭")] * 3))


class TestFlashEscape(unittest.TestCase):
    def setUp(self):
        self.orig = utils.is_route_selection_page
        utils.is_route_selection_page = lambda task: True

    def tearDown(self):
        utils.is_route_selection_page = self.orig

    def test_below_limit_keeps_going(self):
        t = empty_task()
        t.node_status["empty_flashes"] = 1
        self.assertFalse(utils.handle_empty_flash_escape(t))

    def test_limit_reached_escapes_from_route_page(self):
        t = empty_task()
        t.node_status["empty_flashes"] = 2
        self.assertTrue(utils.handle_empty_flash_escape(t))
        self.assertEqual([(0.959, 0.051)], t.clicks)
        self.assertIn("闪了 2 张", t.node_status["escape_reason"])
        self.assertTrue(utils.handle_empty_flash_escape(t))         # 3 秒内不重复点
        self.assertEqual(1, len(t.clicks))
        t.all_texts = [box(0.952, 0.928, "逃脱")]
        self.assertTrue(utils.handle_empty_flash_escape(t))
        self.assertEqual("逃脱", t.clicks[-1])
        self.assertTrue(t.node_status["is_escaped"])
        self.assertFalse(utils.handle_empty_flash_escape(t))

    def test_talent_limit_one(self):
        t = empty_task(config={utils.EMPTY_FLASH_LIMIT: 1})
        t.node_status["empty_flashes"] = 1
        self.assertTrue(utils.handle_empty_flash_escape(t))

    def test_not_during_battle(self):
        t = empty_task(texts=[box(0.512, 0.969, "5/10")])
        t.node_status["empty_flashes"] = 2
        self.assertFalse(utils.handle_empty_flash_escape(t))
        self.assertEqual([], t.clicks)


class TestWaypointEscape(unittest.TestCase):
    def settlement(self, t):
        t.all_texts = [box(0.552, 0.067, "结算")]
        return utils_chaos.handle_chaos_reward_settlement(t)

    def test_first_waypoint_escapes_and_saves(self):
        t = empty_task()
        t.node_status["empty_flashes"] = 1
        self.assertTrue(self.settlement(t))
        self.assertEqual([(0.959, 0.051)], t.clicks)
        self.assertTrue(t.node_status["empty_saved"])
        self.assertEqual(1, t.node_status["success_rounds"])
        self.assertTrue(self.settlement(t))                          # 菜单还没出来：等，不重复点、不重复记
        self.assertEqual(1, len(t.clicks))
        t.node_status["empty_escape_at"] -= 5
        self.assertTrue(self.settlement(t))
        self.assertEqual(2, len(t.clicks))
        self.assertEqual(1, t.node_status["success_rounds"])

    def test_flash_over_limit_not_counted_as_save(self):
        t = empty_task()
        t.node_status["empty_flashes"] = 2
        self.assertTrue(self.settlement(t))
        self.assertFalse(t.node_status["empty_saved"])
        self.assertEqual(0, t.node_status["success_rounds"])

    def test_other_modes_do_not_escape_at_waypoint(self):
        t = empty_task(mode=cs.MODE_TARGET)
        self.assertFalse(self.settlement(t))
        self.assertEqual([], t.clicks)

    def test_state_survives_layer_reset(self):
        t = empty_task()
        t.node_status.update(empty_flashes=1, empty_saved=True)
        utils.reset_layer_status(t)
        self.assertEqual(1, t.node_status["empty_flashes"])
        self.assertTrue(t.node_status["empty_saved"])


class TestRotateTarget(unittest.TestCase):
    def test_next_target_after_save(self):
        t = empty_task("希露德")
        t.node_status["empty_saved"] = True
        self.assertTrue(utils.empty_rotate_target(t))
        self.assertEqual("玛丽贝尔", t.config["目标主战员"])
        self.assertEqual(1, t.setups)
        self.assertEqual("玛丽贝尔", utils.empty_target(t))
        self.assertIn("庇护打击", t.chaos_overrides["移除卡牌列表"])   # 删卡列表换成新目标的卡

    def test_alias_matches_order(self):
        t = empty_task("玛丽贝儿")            # 卡库名和配置里的「玛丽贝尔」是同一个人
        t.node_status["empty_saved"] = True
        self.assertTrue(utils.empty_rotate_target(t))
        self.assertEqual("凛", t.config["目标主战员"])

    def test_last_target_stops_at_lobby(self):
        t = empty_task("蒂菲拉")
        t.node_status["empty_saved"] = True
        self.assertFalse(utils.empty_rotate_target(t))
        self.assertEqual("蒂菲拉", t.config["目标主战员"])
        self.assertIn("都存好了", getattr(t, run_state.GOAL_STOP_ATTR))

    def test_no_save_no_rotation(self):
        t = empty_task("希露德")
        self.assertFalse(utils.empty_rotate_target(t))
        t.node_status["empty_saved"] = False
        self.assertFalse(utils.empty_rotate_target(t))
        self.assertEqual("希露德", t.config["目标主战员"])
        self.assertEqual(0, t.setups)

    def test_cleanup_keeps_every_target(self):
        t = empty_task("玛丽贝尔")
        keep = utils.empty_keep_members(t)
        self.assertEqual({"希露德", "玛丽贝儿", "凛", "蒂菲拉"}, keep)
        self.assertIn("希露德", sc.keep_reason(30000, 40, {"希露德", "米卡"}, keep))
        self.assertIsNone(sc.keep_reason(30000, 40, {"米卡", "海德玛丽"}, keep))
        # 别的玩法只保留当前目标
        self.assertEqual({"罗丝薇瑟"}, utils.empty_keep_members(empty_task("罗丝薇瑟", mode=cs.MODE_TARGET)))


class TestNoFlash(unittest.TestCase):
    def test_event_spark_vetoed(self):
        best, res = cs.pick_event_option(["赋予1张所选卡牌闪光", "进入战斗"], cs.MODE_EMPTY, {"removed": 0})
        self.assertEqual(1, best, res)
        s, _ = cs.score_effects({"spark": True, "credit": 200}, cs.MODE_EMPTY)
        self.assertLess(s, -400)

    def test_remove_still_first(self):
        best, res = cs.pick_event_option(["信用点增加100", "移除2张卡牌"], cs.MODE_EMPTY, {"removed": 0})
        self.assertEqual(1, best, res)

    def test_shop_route_beats_event(self):
        from utils import find_best_map_route_by_priority
        info = {
            "nodes": [
                {"id": 0, "type": "当前位置", "row": 1, "special_features": []},
                {"id": 1, "type": "事件", "row": 0, "special_features": []},
                {"id": 2, "type": "休息", "row": 2, "special_features": [{"feature_name": "shop_in_map", "priority": 1}]},
                {"id": 3, "type": "结算", "row": 1, "special_features": []},
            ],
            "adjacency": {0: [1, 2], 1: [3], 2: [3]},
        }
        r = find_best_map_route_by_priority(info, ["事件", "休息", "精英", "小怪"], cs.ROUTE_WEIGHTS[cs.MODE_EMPTY])
        self.assertEqual([0, 2, 3], r["route"])

    def test_route_only_counts_up_to_first_waypoint(self):
        # 10-28 02:23 实录：航点在第 9 步，整层路线为了航点后的两个商店选了航点前只有 1 个商店的路
        from utils import find_best_map_route_by_priority
        shop = [{"feature_name": "shop_in_map", "priority": 1}]
        info = {
            "nodes": [
                {"id": 0, "type": "当前位置", "row": 1, "special_features": []},
                {"id": 1, "type": "休息", "row": 0, "special_features": shop},
                {"id": 2, "type": "小怪", "row": 2, "special_features": []},
                {"id": 3, "type": "结算", "row": 0, "special_features": []},
                {"id": 4, "type": "结算", "row": 2, "special_features": []},
                {"id": 5, "type": "首领", "row": 1, "special_features": []},
                {"id": 6, "type": "休息", "row": 2, "special_features": shop},
                {"id": 7, "type": "休息", "row": 2, "special_features": shop},
            ],
            "adjacency": {0: [1, 2], 1: [3], 2: [4], 3: [5], 4: [6], 6: [7], 7: [5]},
        }
        prio = ["事件", "休息", "精英", "小怪"]
        w = cs.route_weights(cs.MODE_EMPTY, 0, event_bonus=3)
        self.assertEqual("结算", w["stop_at"])
        self.assertEqual(5, w["types"]["事件"])                      # 目标装备来源事件不加分
        self.assertEqual([0, 1, 3], find_best_map_route_by_priority(info, prio, w)["route"])
        # 不截断时会为了航点后的商店走小怪那条
        self.assertEqual(2, find_best_map_route_by_priority(info, prio, cs.ROUTE_WEIGHTS[cs.MODE_EMPTY])["route"][1])
        self.assertNotIn("stop_at", cs.route_weights(cs.MODE_EMPTY, 1))
        self.assertNotIn("stop_at", cs.route_weights(cs.MODE_TARGET, 0))

    def test_dream_mode_off(self):
        # 用户 2026-10-28：空存不能开梦境（噩梦），会提高闪光几率；开着就关掉
        self.assertFalse(cs.config_overrides(cs.MODE_EMPTY, "希露德")["刷存档开梦境模式"])
        calls = []
        orig = (utils_chaos.utils_chaos_prep.ensure_dream_mode, utils_chaos.utils_chaos_prep.setup_team)
        utils_chaos.utils_chaos_prep.ensure_dream_mode = lambda task, want: calls.append(want) or True
        utils_chaos.utils_chaos_prep.setup_team = lambda task, members: True
        try:
            for mode, cfg, want in ((cs.MODE_EMPTY, {}, [False]), (cs.MODE_TARGET, {"刷存档开梦境模式": True}, [True]),
                                    (cs.MODE_TARGET, {"刷存档开梦境模式": False}, [])):
                calls.clear()
                t = empty_task(mode=mode, config=dict(cfg, 队友=["米卡", "海德玛丽"]),
                               texts=[box(0.121, 0.043, "配置队伍"), box(0.947, 0.912, "进入")])
                t.team_checked = False
                t.ocr = lambda: []
                self.assertTrue(utils_chaos.handle_chaos_team_setup(t))
                self.assertEqual(want, calls, mode)
        finally:
            utils_chaos.utils_chaos_prep.ensure_dream_mode, utils_chaos.utils_chaos_prep.setup_team = orig

    def test_golden_card_not_clicked(self):
        t = empty_task()
        orig = utils._find_golden_card
        utils._find_golden_card = lambda task: self.fail("刷空档不该找金色气泡")
        try:
            self.assertFalse(utils.click_golden_card(t))
        finally:
            utils._find_golden_card = orig

    def test_member_flash_gives_teammates_first(self):
        t = empty_task(texts=[box(0.495, 0.936, "请选择获得闪光的主战员")])
        t.feature_exists = lambda name: False
        t.box_of_screen = lambda *a: None
        t.wait_feature = lambda *a, **k: None
        utils.handle_main_member_flash(t)
        self.assertEqual([(0.504, 0.504), (0.755, 0.508), (0.228, 0.51)], t.clicks)

    def test_shop_only_removes(self):
        # 删卡已售罄：刷空档不再挑商品、不刷新，交给离开
        t = empty_task(texts=[box(0.727, 0.286, "售罄")])
        t.find_feature = lambda *a, **k: self.fail("刷空档不该再挑商品")
        self.assertFalse(utils.handle_shop(t))


if __name__ == "__main__":
    unittest.main()
