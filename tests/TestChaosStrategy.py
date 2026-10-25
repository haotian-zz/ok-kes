# 卡厄思局内策略（chaos_strategy）单测：事件选项打分、玩法→配置项、目标卡组计划，不需要游戏
import os
import sys
import unittest
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ok_tasks"))

import chaos_strategy as cs  # noqa: E402
from tests.TestChaosPrep import W, H, load_ocr  # noqa: E402
from utils_chaos_prep import parse_preset_cards  # noqa: E402


class TestParseEffects(unittest.TestCase):
    def test_remove_and_credit(self):
        self.assertEqual(2, cs.parse_effects("移除2张所选卡牌")["remove_card"])
        self.assertEqual(120, cs.parse_effects("抢走信用点箱 信用点增加120")["credit"])
        self.assertTrue(cs.parse_effects("移除所有咒术卡牌")["remove_curse_all"])
        self.assertNotIn("curse_card", cs.parse_effects("移除所有咒术卡牌"))

    def test_spark_kinds(self):
        self.assertTrue(cs.parse_effects("赋予神之闪光")["god_spark"])
        self.assertNotIn("god_spark", cs.parse_effects("随机卡牌闪光"))


class TestEventPick(unittest.TestCase):
    descs = ["购买他手上的短刀 信用点减少40 获得窃取者的短刀", "抢走信用点箱 信用点增加120", "夸赞他的技术 获得随机卡厄思教团稀有装备"]

    def test_match_event_from_options(self):
        event, opts = cs.match_event_options(self.descs)
        self.assertEqual("小偷们", event["name"])
        self.assertEqual(["uk_300_s02_01a_s1", "uk_300_s02_01a_s2", "uk_300_s02_01a_s3"], [o["id"] for o in opts])

    def test_empty_prefers_credit_over_equipment(self):
        best, _ = cs.pick_event_option(self.descs, cs.MODE_EMPTY, {"credit": 100})
        self.assertEqual(1, best)

    def test_empty_prefers_remove(self):
        best, res = cs.pick_event_option(["闭上眼睛 移除3张卡牌", "凝视它的眼睛", "缓步靠近"], cs.MODE_EMPTY, {"removed": 0})
        self.assertEqual(0, best, res)

    def test_empty_avoids_spark(self):
        s1, _ = cs.score_effects({"spark": True}, cs.MODE_EMPTY)
        s2, _ = cs.score_effects({"credit": 30}, cs.MODE_EMPTY)
        self.assertLess(s1, s2)

    def test_remove_capped(self):
        s, _ = cs.score_effects({"remove_card": 2}, cs.MODE_EMPTY, {"removed": 5})
        self.assertLessEqual(s, 0)

    def test_explore_prefers_unseen(self):
        seen = {"uk_300_s02_01a_s2"}
        best, _ = cs.pick_event_option(self.descs, cs.MODE_EXPLORE, {"seen": seen})
        self.assertNotEqual(1, best)


    def test_enemy_hp_to_one_is_good(self):
        # 2026-10-24 实机「凯尔肯的传令兵」：「普通战斗3次期间异形生命值变为1」是异形变 1，不能当成我方生命值变 1 重罚
        for d in ["接受恩宠获得装备[截骨机]，普通战斗3次期间异形生命值变为1",
                  "舍弃世俗高速连射]，普通战斗3次期间异将选择的普通卡牌转换为卡牌[形生命值变为1"]:
            e = cs.parse_effects(d)
            self.assertTrue(e.get("enemy_hp_to_one"), d)
            self.assertFalse(e.get("hp_to_one"), d)
        self.assertTrue(cs.parse_effects("所有主战员生命值变为1").get("hp_to_one"))

    def test_explore_prefers_unpicked(self):
        # 选过「献上赞美」后，下次优先选没选过的
        descs = ["接受恩宠获得装备[截骨机]，普通战斗3次期间异形生命值变为1", "献上赞美信用点增加100"]
        best, res = cs.pick_event_option(descs, cs.MODE_EXPLORE, {"seen": set()})
        seen = {res[1][3]}
        best, res = cs.pick_event_option(descs, cs.MODE_EXPLORE, {"seen": seen})
        self.assertEqual(0, best, res)

    def test_text_key_for_unknown_event(self):
        # 库里没有的事件也按文字记「选过」，数值变了还是同一个 key
        a = cs.text_key("打破平静战员闪光1次所有主战员压力增加20")
        self.assertEqual(a, cs.text_key("打破平静战员闪光2次所有主战员压力增加30"))
        _, res = cs.pick_event_option(["完全没见过的选项甲恢复生命", "完全没见过的选项乙恢复生命"], cs.MODE_EXPLORE,
                                      {"seen": {cs.text_key("完全没见过的选项甲恢复生命")}})
        self.assertGreater(res[1][0], res[0][0])


class TestPriorities(unittest.TestCase):
    """用户 2026-10-24 定的优先级。"""
    need = {"need_remove": 2, "need_copy": 1, "need_spark": 3, "credit": 500, "target_equipment": ["截骨机"]}

    # 只测画面文字解析出的效果怎么排：编出来的选项文字会模糊匹配到库里不相干的事件，所以给个空事件库
    no_events = SimpleNamespace(iter_events=lambda region=None: [])

    def rank(self, descs, mode=cs.MODE_TARGET, state=None):
        _, res = cs.pick_event_option(descs, mode, state if state is not None else self.need, db=self.no_events)
        return [d for _, d in sorted(zip([r[0] for r in res], descs), reverse=True)]

    def test_target_order(self):
        descs = ["要他回去获得装备[截骨机]", "复制选中的1张卡牌", "移除1张卡牌", "选择1张卡牌闪光", "选中主战员闪光1次",
                 "信用点增加300", "随机主战员触发1次闪光", "获得装备[女神之泪]", "信用点增加100"]
        self.assertEqual(descs, self.rank(list(reversed(descs))))

    def test_target_other_equipment_below_random_spark(self):
        # 用户 2026-10-24：其他装备放在随机卡牌闪光和 <200 信用点之间
        self.assertEqual("移除1张卡牌", self.rank(["获得装备[女神之泪]", "移除1张卡牌"])[0])
        self.assertEqual("获得装备[女神之泪]", self.rank(["信用点增加150", "获得装备[女神之泪]"])[0])

    def test_target_no_more_removal_prefers_spark(self):
        st = dict(self.need, need_remove=0)
        self.assertEqual("选中主战员闪光1次", self.rank(["移除1张卡牌", "选中主战员闪光1次"], state=st)[0])

    def test_target_neutral_between_copy_and_remove(self):
        st = dict(self.need, need_neutral=1)
        self.assertEqual(["复制选中的1张卡牌", "获得1张中立卡牌", "移除1张卡牌"],
                         self.rank(["移除1张卡牌", "获得1张中立卡牌", "复制选中的1张卡牌"], state=st))
        self.assertEqual("移除1张卡牌", self.rank(["获得1张中立卡牌", "移除1张卡牌"])[0])

    def test_target_god_spark_and_battle_after_small_credit(self):
        st = dict(self.need, need_god_spark=1)
        self.assertEqual(["信用点增加100", "选择1张卡牌触发神之闪光", "发起攻击进入战斗"],
                         self.rank(["发起攻击进入战斗", "选择1张卡牌触发神之闪光", "信用点增加100"], state=st))

    def test_target_heal_capped_below_big_credit(self):
        st = dict(self.need, hp_pct=5)
        self.assertEqual(["信用点增加300", "恢复50%生命值", "信用点增加100"],
                         self.rank(["信用点增加100", "恢复50%生命值", "信用点增加300"], state=st))
        self.assertEqual("信用点增加100", self.rank(["恢复50%生命值", "信用点增加100"])[0])

    def test_followup_target_equipment(self):
        # 后续事件里能拿到目标装备 → 这个选项第一优先级
        opt = {"text": "继续深入", "effects": {"stress": 5},
               "next": [{"text": "拿走", "effects": {"equipment": ["截骨机"]}}, {"text": "离开", "effects": {}}]}
        s, why = cs.followup_best(opt, cs.MODE_TARGET, self.need)
        self.assertGreaterEqual(s, 1000)
        self.assertIn("后续「拿走」", why)
        self.assertEqual((0.0, []), cs.followup_best({"text": "x"}, cs.MODE_TARGET, self.need))

    def test_db_spark_target(self):
        e = cs._effects_of({"effects": {"spark": 1, "spark_target": "随机卡牌"}})
        self.assertTrue(e["spark_random_card"])
        self.assertEqual(50, cs.score_effects(e, cs.MODE_TARGET, self.need)[0])

    def test_explore_unseen_over_everything(self):
        descs = ["献上赞美信用点增加100", "失去理智所有主战员生命值变为1"]
        _, res = cs.pick_event_option(descs, cs.MODE_EXPLORE, {"seen": set()}, db=self.no_events)
        seen = {res[0][3]}
        self.assertEqual(descs[1], self.rank(descs, cs.MODE_EXPLORE, {"seen": seen})[0])

    def test_explore_new_equipment(self):
        descs = ["接受A获得装备[截骨机]", "接受B获得装备[女神之泪]"]
        _, res = cs.pick_event_option(descs, cs.MODE_EXPLORE, {"seen": set()}, db=self.no_events)
        seen = {res[0][3], res[1][3], cs.equipment_key("截骨机")}
        self.assertEqual(descs[1], self.rank(descs, cs.MODE_EXPLORE, {"seen": seen})[0])
        self.assertIn(cs.equipment_key("女神之泪"), cs.option_seen_keys(descs[1], None))


class TestTargetDeck(unittest.TestCase):
    preset = {"cards": parse_preset_cards(load_ocr("preset_rosweisse_1.ocr.txt"), W, H)}

    def test_plan(self):
        plan = cs.deck_plan("罗丝薇瑟", self.preset)
        self.assertEqual(["入鞘", "斩念", "斩念"], sorted(plan["remove"]))
        self.assertEqual(["剑鸣九霄"] * 3, plan["copy"])
        self.assertIn("明灭剑", [c["name"] for c in plan["flash"]])

    def test_overrides(self):
        o = cs.config_overrides(cs.MODE_EMPTY, "罗丝薇瑟")
        self.assertTrue(o["刷空档"])
        for n in ("斩念", "入鞘", "基尔肯的神眷者", "明灭剑"):
            self.assertIn(n, o["移除卡牌列表"])
        t = cs.config_overrides(cs.MODE_TARGET, "罗丝薇瑟", cs.deck_plan("罗丝薇瑟", self.preset))
        self.assertEqual(["斩念", "入鞘"], sorted(t["移除卡牌列表"], key=["斩念", "入鞘"].index))
        self.assertEqual({}, cs.config_overrides(cs.MODE_LEGACY))

    def test_flash_variant(self):
        target = [c for c in self.preset["cards"] if c["name"] == "循环之刃"]
        choices = [{"description": "伤害300% 循环烙印2 生成1张剑穗加入手牌"},
                   {"description": target[0]["desc"]},
                   {"description": "伤害300% 赋予回收"}]
        self.assertEqual(1, cs.pick_flash_variant("循环之刃", choices, target))


class TestRoute(unittest.TestCase):
    """整层建图后按玩法权重求整条路径：当前 → (事件 | 精英) → 休息[商店] → 结算。"""
    map_info = {
        "nodes": [
            {"id": 0, "type": "当前位置", "row": 1, "special_features": []},
            {"id": 1, "type": "事件", "row": 1, "special_features": []},
            {"id": 2, "type": "精英", "row": 2, "special_features": []},
            {"id": 3, "type": "小怪", "row": 1, "special_features": []},
            {"id": 4, "type": "休息", "row": 2, "special_features": [{"feature_name": "shop_in_map", "priority": 1}]},
            {"id": 5, "type": "结算", "row": 1, "special_features": []},
        ],
        "adjacency": {0: [1, 2], 1: [3], 2: [4], 3: [5], 4: [5]},
    }

    def test_empty_mode_avoids_elite_but_takes_shop(self):
        from utils import find_best_map_route_by_priority
        prio = ["休息", "事件", "小怪", "精英"]
        r = find_best_map_route_by_priority(self.map_info, prio, cs.ROUTE_WEIGHTS[cs.MODE_EMPTY])
        # 空存：精英1+休息4+商店2=7，事件5+小怪2=7，同分时商店多的优先
        self.assertEqual([0, 2, 4, 5], r["route"])

    def test_explore_mode_prefers_event(self):
        from utils import find_best_map_route_by_priority
        prio = ["事件", "小怪", "精英", "休息"]
        r = find_best_map_route_by_priority(self.map_info, prio, cs.ROUTE_WEIGHTS[cs.MODE_EXPLORE])
        self.assertEqual([0, 1, 3, 5], r["route"])


class TestTrace(unittest.TestCase):
    """流程追踪：记地图（拼图 + 路线）、事件决策、日志，再生成 HTML。"""

    def test_trace_and_report(self):
        import tempfile
        import numpy as np
        import chaos_trace
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import chaos_trace_report
        with tempfile.TemporaryDirectory() as tmp:
            old_root, chaos_trace.TRACE_ROOT = chaos_trace.TRACE_ROOT, tmp
            try:
                task = SimpleNamespace(config={}, node_status={"pass_final_boss_count": 0}, chaos_mode=cs.MODE_EXPLORE)
                frames = [np.full((540, 960, 3), 40, np.uint8), np.full((540, 960, 3), 80, np.uint8)]
                info = {"nodes": [{"id": 0, "type": "当前位置", "col": 0, "px": 100, "py": 270},
                                  {"id": 1, "type": "事件", "col": 1, "px": 1100, "py": 270}],
                        "adjacency": {0: [1], 1: []}, "current": 0}
                chaos_trace.begin_frame(task)      # 每次启动第一帧还没有追踪目录（2026-10-24 实机崩过）
                chaos_trace.page(task, "handle_x", frames[0])
                chaos_trace.map_scan(task, frames, [0, -400], info)
                chaos_trace.log(task, "全屏地图扫描：2帧")
                chaos_trace.route_plan(task, info, {"route": [0, 1], "weighted_score": 6}, [])
                chaos_trace.step(task, "event", "库:小偷们/抢走", frames[0], chosen=1,
                                 options=[{"desc": "A", "score": 1, "why": [], "src": "x"},
                                          {"desc": "B", "score": 9, "why": ["信用点+9"], "src": "x"}])
                path = task._chaos_trace["dir"]
                self.assertEqual(4, len([f for f in os.listdir(path) if f.endswith(".jpg")]))
                with open(chaos_trace_report.render(path), encoding="utf-8") as f:
                    page = f.read()
                self.assertIn("当前位置 → 事件", page)
                self.assertIn('class="chosen"', page)
                self.assertIn("全屏地图扫描：2帧", page)
            finally:
                chaos_trace.TRACE_ROOT = old_root


if __name__ == "__main__":
    unittest.main()
