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

    def test_target_god_spark_never_and_battle_over_small_credit(self):
        # 用户 2026-10-24：局内神闪会爆存档，一律不要；战斗是闪光来源，排在 <200 信用点前
        st = dict(self.need, need_god_spark=1)
        self.assertEqual(["发起攻击进入战斗", "信用点增加100", "选择1张卡牌触发神之闪光"],
                         self.rank(["选择1张卡牌触发神之闪光", "发起攻击进入战斗", "信用点增加100"], state=st))
        self.assertLess(cs.score_effects(cs.parse_effects("观察使者赋豫1张所选卡牌迪亚洛斯闪光"), cs.MODE_TARGET, st)[0], 0)

    def test_battle_buff_is_not_battle(self):
        self.assertNotIn("battle", cs.parse_effects("将选择的普通卡牌转换为卡牌冰封启示，普通战斗3次期间异形生命值变为1"))
        self.assertTrue(cs.parse_effects("发起攻击进入战斗").get("battle"))

    def test_god_names_are_god_spark(self):
        for d in ("观察使者赋豫1张所选卡牌迪亚洛斯闪光", "随机[CALIGO]闪光", "拔出相连的针成功时，赋豫1张随机卡牌神之滚动骰子10闪光"):
            e = cs.parse_effects(d)
            self.assertTrue(e.get("god_spark"), d)
            self.assertFalse(e.get("spark"), d)

    def test_god_spark_page_text(self):
        from utils import GOD_SPARK_PAGE
        self.assertTrue(GOD_SPARK_PAGE.search("闪光：迪亚洛斯"))
        self.assertTrue(GOD_SPARK_PAGE.search("闪光:尼希勒姆"))
        self.assertIsNone(GOD_SPARK_PAGE.search("请决定闪光效果。"))
        self.assertIsNone(GOD_SPARK_PAGE.search("请选择1张要赋予闪光的卡牌。"))

    def test_same_option_text(self):
        from utils import _same_option_text
        a = "守望先知最大生命值增加20%，信用点增加40"
        self.assertTrue(_same_option_text("1守望先知加40最大生命值增加20%，信用点增", a))
        self.assertFalse(_same_option_text("回答先知选择1张卡牌闪光，信用点增加40", a))
        self.assertFalse(_same_option_text("拯救先知获得装备[绯刃]，信用点增加40", a))

    def test_memory_card_in_preset(self):
        self.assertEqual("丧失", cs.memory_name("记忆：丧失4强化"))
        self.assertEqual("丧失", cs.memory_name("记忆：丧失"))
        self.assertEqual("万花筒", cs.memory_name("记忆:万花筒"))
        self.assertEqual("", cs.memory_name("明灭剑"))
        plan = cs.deck_plan("罗丝薇瑟", {"cards": [{"name": "记忆：丧失", "desc": "x", "n": None, "god_spark": None}]})
        self.assertEqual(["丧失"], [m["memory"] for m in plan["memory"]])
        self.assertEqual([], plan["neutral"])
        self.assertEqual("丧失", cs.config_overrides(cs.MODE_TARGET, "罗丝薇瑟", plan)["指定记忆卡牌"])
        self.assertEqual("x", cs.config_overrides(cs.MODE_EXPLORE, "罗丝薇瑟", plan)["指定记忆描述"])

    def test_deck_stat_not_event_option(self):
        from utils import NOT_EVENT_OPTION, NOT_EVENT_PAGE
        self.assertTrue(NOT_EVENT_PAGE.search("正在保存战斗数据"))
        self.assertTrue(NOT_EVENT_PAGE.search("存储数据收集完成"))
        self.assertTrue(NOT_EVENT_OPTION.search("独特卡牌平均费用0.9"))
        self.assertTrue(NOT_EVENT_OPTION.search("4368 TB"))
        self.assertTrue(NOT_EVENT_OPTION.search("39823TB"))
        self.assertTrue(NOT_EVENT_OPTION.search("B3813 TB."))
        self.assertIsNone(NOT_EVENT_OPTION.search("收起有用的东西随机获得稀有~传说装备"))

    def test_target_heal(self):
        st = dict(self.need, hp_pct=60)
        self.assertEqual(["信用点增加300", "恢复50%生命值", "信用点增加100"],
                         self.rank(["信用点增加100", "恢复50%生命值", "信用点增加300"], state=st))
        # 血量 <25%：死了只能带出最近航路点的存档，回血仅次于目标装备和复制
        st = dict(self.need, hp_pct=10)
        self.assertEqual(["复制选中的1张卡牌", "恢复50%生命值", "移除1张卡牌"],
                         self.rank(["移除1张卡牌", "恢复50%生命值", "复制选中的1张卡牌"], state=st))

    def test_target_random_copy_after_spark(self):
        self.assertEqual(["选中主战员闪光1次", "在随机3张稀有卡牌中选择1张复制"],
                         self.rank(["在随机3张稀有卡牌中选择1张复制", "选中主战员闪光1次"]))
        e = cs._effects_of({"effects": {"copy_card": 1, "copy_mode": "随机3张稀有+中选1"}})
        self.assertTrue(e["copy_random"])

    def test_target_credit_value_depends_on_use(self):
        done = dict(self.need, need_remove=0, pending_meditation=0)
        self.assertEqual("随机主战员触发1次闪光", self.rank(["信用点增加300", "随机主战员触发1次闪光"], state=done)[0])
        self.assertEqual("信用点增加300", self.rank(["信用点增加300", "随机主战员触发1次闪光"],
                                                 state=dict(done, pending_meditation=1))[0])

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

    def test_explore_random_equipment_pool_not_new(self):
        # 「随机获得稀有~传说装备」是装备池，不保证是没拿过的装备（2026-10-24 实跑被当成新装备 +1000）
        self.assertFalse(cs.is_specific_equipment("随机商店稀有装备"))
        self.assertFalse(cs.is_specific_equipment("商店或尼希勒姆稀有~传说装备"))
        self.assertTrue(cs.is_specific_equipment("平行宇宙耦合体"))
        s, why = cs.score_effects({"equipment": ["商店稀有~传说装备"]}, cs.MODE_EXPLORE, {"seen": set()})
        self.assertLess(s, 1000)

    def test_explore_tiebreak_spark_over_transform(self):
        # 2026-10-24 实跑：两个都没选过，「转换为执行仪式」排在第一个就被选了，应选闪光
        st = {"seen": set(), "unseen": True}
        spark = cs.score_effects({"spark": 1, "spark_card": True}, cs.MODE_EXPLORE, st)[0]
        conv = cs.score_effects({"transform_card": True}, cs.MODE_EXPLORE, st)[0]
        self.assertGreater(spark, conv)
        self.assertLess(spark, 1050)

    def test_shown_equipment_over_db_pool(self):
        # 2026-10-24 实跑：库里「破坏石碑」是随机装备池，画面显示了这次的具体装备[祝圣光轮]
        db = SimpleNamespace(iter_events=lambda region=None: [
            {"name": "最后的纪律", "options": [{"id": "x1", "text": "破坏石碑",
                                              "effects": {"equipment": ["随机装备（稀有度：稀有）"]}}]}])
        _, res = cs.pick_event_option(["破坏石碑获得装备[祝圣光轮]"], cs.MODE_TARGET,
                                      dict(self.need, target_equipment=["祝圣光轮"]), db=db)
        self.assertGreaterEqual(res[0][0], 1000)

    def test_text_key_ignores_bracket_content(self):
        # 同一个选项每局给的装备不同，不能因此算成没选过
        self.assertEqual(cs.text_key("把伊欧娜拉下来获得装备[标准型防毒面具]"),
                         cs.text_key("把伊欧娜拉下来获得装备[幸存者的兜帽]"))
        old_key = cs._legacy_text_key("把伊欧娜拉下来获得装备[标准型防毒面具]")
        _, res = cs.pick_event_option(["把伊欧娜拉下来获得装备[标准型防毒面具]"], cs.MODE_EXPLORE,
                                      {"seen": {old_key, cs.equipment_key("标准型防毒面具")}}, db=self.no_events)
        self.assertLess(res[0][0], 1000)

    def test_explore_text_random_equipment_pool(self):
        e = cs.parse_effects("错误也是计算随机获得稀有~传说装备")
        s, _ = cs.score_effects(e, cs.MODE_EXPLORE, {"seen": set()})
        self.assertGreaterEqual(s, 50)

    def test_explore_text_followup_event(self):
        descs = ["尝试对话发生事件[无法给出答案之人]", "袭击白使者信用点增加160"]
        self.assertEqual(descs[0], self.rank(descs, cs.MODE_EXPLORE, {"seen": set()})[0])

    def test_seen_by_text_even_if_db_match_moves(self):
        # 同一选项上次对到库里 A 事件、这次对到 B 事件：按文字也要认出选过
        db = SimpleNamespace(iter_events=lambda region=None: [
            {"name": "银色遗骸瀑布", "options": [{"id": "b1", "text": "拒绝触碰", "effects": {"remove_card": 1}}]}])
        keys = cs.option_seen_keys("拒绝触碰移除1张所选卡牌", "a1")
        _, res = cs.pick_event_option(["拒绝触碰移除1张所选卡牌"], cs.MODE_EXPLORE, {"seen": set(keys)}, db=db)
        self.assertLess(res[0][0], 1000)

    def test_explore_followup_unseen(self):
        opt = {"id": "a", "text": "进入", "effects": {},
               "next": [{"id": "a1", "text": "x", "effects": {}}, {"id": "a2", "text": "y", "effects": {}}]}
        self.assertGreaterEqual(cs.followup_best(opt, cs.MODE_EXPLORE, {"seen": {"a1"}})[0], 1000)
        self.assertLess(cs.followup_best(opt, cs.MODE_EXPLORE, {"seen": {"a1", "a2"}})[0], 1000)

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

    def test_season_route_weights(self):
        # 活动卡厄思精英必给记忆残片：所有玩法精英高于普通战；血量低时精英压回普通战、休息加分
        for mode in (cs.MODE_EXPLORE, cs.MODE_EMPTY, cs.MODE_TARGET):
            t = cs.ROUTE_WEIGHTS[mode]["types"]
            self.assertGreater(t["精英"], t["小怪"])
        low = cs.route_weights(cs.MODE_TARGET, 0, 30)["types"]
        self.assertEqual(low["精英"], low["小怪"])
        self.assertEqual(cs.ROUTE_WEIGHTS[cs.MODE_TARGET]["types"]["休息"] + 2, low["休息"])
        self.assertEqual(cs.ROUTE_WEIGHTS[cs.MODE_TARGET]["types"], cs.route_weights(cs.MODE_TARGET, 0, False)["types"])

    def test_equipment_event_source_bonus(self):
        # 凝结的光辉残片只能在第 1 层（外围）「前往更深之处」选「劈向地脉」拿：第 1 层事件加分，拿到后不加
        src = cs.equipment_event_sources(["混沌指控", "凝结的光辉残片", "坠落的王冠"])
        self.assertEqual([("凝结的光辉残片", "前往更深之处", "劈向地脉", 0)],
                         [(s["equipment"], s["event"], s["option"], s["layer"]) for s in src])
        self.assertEqual(cs.EVENT_SOURCE_BONUS, cs.event_source_bonus(src, 0))
        self.assertEqual(0, cs.event_source_bonus(src, 1))
        self.assertEqual(0, cs.event_source_bonus(src, 0, ["凝结的光辉残片"]))
        w = cs.route_weights(cs.MODE_TARGET, 0, 80, cs.event_source_bonus(src, 0))["types"]
        self.assertEqual(cs.ROUTE_WEIGHTS[cs.MODE_TARGET]["types"]["事件"] + cs.EVENT_SOURCE_BONUS, w["事件"])
    def test_last_shop(self):
        from utils import _is_last_shop
        plan = {"layer": 2, "done": 1, "steps": [{"type": "休息"}, {"type": "首领"}]}
        task = SimpleNamespace(node_status={"pass_final_boss_count": 2, "full_route": plan})
        self.assertTrue(_is_last_shop(task))
        task.node_status["pass_final_boss_count"] = 1          # 第 2 层首领前的商店不算
        plan["layer"] = 1
        self.assertFalse(_is_last_shop(task))
        task.node_status.update(pass_final_boss_count=2)
        plan.update(layer=2, done=0)                           # 后面还有节点
        self.assertFalse(_is_last_shop(task))
    def test_last_shop_pick(self):
        import utils
        box = lambda x, y, name: SimpleNamespace(x=x * 1920, y=y * 1080, width=0, height=0, name=name)
        legend, rare = object(), object()
        items = [(rare, "某稀有装备", 96, False), (legend, "坠落的王冠", 200, False)]
        paid = [box(0.08, 0.93, "2/3"), box(0.19, 0.93, "30")]
        task = SimpleNamespace(width=1920, height=1080, all_texts=paid)
        # 250 - 30 = 220 ≥ 200：还能刷，先刷新
        self.assertIsNone(utils._last_shop_pick(task, items, 250))
        # 220 - 30 < 200：再刷就不够买传说，先买传说
        self.assertIs(legend, utils._last_shop_pick(task, items, 220)[0])
        # 刷不了：剩下的钱买得起什么买什么
        task.all_texts = []
        self.assertIs(rare, utils._last_shop_pick(task, items, 150)[0])
        # 免费刷新：先刷
        task.all_texts = [box(0.1, 0.93, "免费")]
        self.assertIsNone(utils._last_shop_pick(task, items, 220))
        # 别名展开（之前 utils 没 import game_db，静默失败）
        task = SimpleNamespace(config={"装备1号位优先级": ["混沌指控"]})
        self.assertIn("混沌之识", utils._equipment_priority(task, 0))

if __name__ == "__main__":
    unittest.main()
