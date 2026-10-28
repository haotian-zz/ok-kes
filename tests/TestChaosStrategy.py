import time
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

    def test_credit_percent(self):
        # norm 把 100% 换成 #%，以前「信用点减少100%」认不出来（2026-10-27 03:45 实录花光 358 信用点换提炼装备）
        self.assertEqual(-100, cs.parse_effects("奉献信念信用点减少100%，获得装备[云端漫游者]")["credit_pct"])
        self.assertEqual(-50, cs.parse_effects("信用点减少50％")["credit_pct"])
        self.assertEqual(-40, cs.parse_effects("信用点减少40 获得窃取者的短刀")["credit"])

    def test_imprint_mode_keeps_credit(self):
        # 2026-10-27 03:45 实录（刷刻印，358 信用点）：不能为一件会提炼的装备花光信用点
        descs = ["铭记教诲择1张获得，普通战斗3次期间异在随机3张中立稀有卡牌中选形生命值变为1",
                 "献上赞美信用点增加100", "奉献信念信用点减少100%，获得装备[云端漫游者]"]
        st = {"imprint": True, "credit": 358, "target_equipment": ["欺骗暗影的匕首"]}
        best, results = cs.pick_event_option(descs, cs.MODE_TARGET, st)
        self.assertEqual(1, best, results)
        self.assertLess(results[2][0], 0, results[2])

    def test_info_option_not_picked(self):
        # 2026-10-27 04:51 实录：「警告」事件另两个选项都是负分，一直选「确认信息」卡了 20 分钟
        descs = ["询问对方的身份确认信息[森林看守]", "解释自己没有恶意移除2张所选卡牌",
                 "想要占有森林强制获得咒术卡牌[根深蒂固]将选择的普通卡牌转换为卡牌[乱和]"]
        best, results = cs.pick_event_option(descs, cs.MODE_TARGET, {"need_remove": 0, "removed": 3})
        self.assertEqual(1, best, results)
        # 探索模式没看过的说明还是看一次；看过了就不再选
        best, _ = cs.pick_event_option(descs, cs.MODE_EXPLORE, {"seen": set()})
        self.assertIn(best, (0, 1, 2))
        self.assertEqual(0, cs.pick_event_option(descs[:1], cs.MODE_TARGET, {})[0])   # 只有它时照选


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
        descs = ["要他回去获得装备[截骨机]", "移除1张卡牌", "选择1张卡牌闪光", "选中主战员闪光1次",
                 "复制选中的1张卡牌", "信用点增加300", "随机主战员触发1次闪光", "获得装备[女神之泪]", "信用点增加100"]
        self.assertEqual(descs, self.rank(list(reversed(descs))))

    def test_named_neutral_card_is_forbidden(self):
        # 2026-10-27 14:40 开局凯尔肯的传令兵「舍弃世俗」：点名转换成中立卡战术射击，字面没有「中立」，只算了转换卡 -10
        for d in ("舍弃世俗将选择的普通卡牌转换为卡牌[战术射击]", "舍弃世俗将选择的普通卡牌转换为卡牌战术射击",
                  "舍弃世俗战术射击]将选择的普通卡牌转换为卡牌["):     # 14:57 两行乱序
            self.assertTrue(cs.parse_effects(d).get("neutral_card"), d)
        self.assertNotIn("neutral_card", cs.parse_effects("将选择的普通卡牌转换为卡牌[明灭剑]"))   # 罗丝薇瑟的卡
        self.assertNotIn("neutral_card", cs.parse_effects("献上肉身最大生命值减少20%，获得装备[阿萨辛之牙]"))
        st = dict(self.need, need_neutral=0)
        self.assertEqual("献上赞美信用点减少50", self.rank(["舍弃世俗将选择的普通卡牌转换为卡牌[战术射击]", "献上赞美信用点减少50"],
                                                   state=st)[0])

    def test_target_other_equipment_below_random_spark(self):
        # 用户 2026-10-24：其他装备放在随机卡牌闪光和 <200 信用点之间
        self.assertEqual("移除1张卡牌", self.rank(["获得装备[女神之泪]", "移除1张卡牌"])[0])
        self.assertEqual("获得装备[女神之泪]", self.rank(["信用点增加150", "获得装备[女神之泪]"])[0])

    def test_target_no_more_removal_prefers_spark(self):
        st = dict(self.need, need_remove=0)
        self.assertEqual("选中主战员闪光1次", self.rank(["移除1张卡牌", "选中主战员闪光1次"], state=st)[0])

    def test_target_neutral_above_remove_and_copy(self):
        st = dict(self.need, need_neutral=1)
        self.assertEqual(["获得1张中立卡牌", "移除1张卡牌", "复制选中的1张卡牌"],
                         self.rank(["移除1张卡牌", "获得1张中立卡牌", "复制选中的1张卡牌"], state=st))
        self.assertEqual("移除1张卡牌", self.rank(["获得1张中立卡牌", "移除1张卡牌"])[0])

    def test_target_never_takes_unlisted_neutral_or_curse(self):
        # 用户 2026-10-26：预设外的中立卡（含咒术卡）一张都不能拿，选中主战员闪光也换不来
        opts = ["甘受玷污强制获得咒术卡牌[赞美的试炼选中主战员闪光1次", "信用点增加50", "在随机3张中立传说卡牌中选择1张获得"]
        self.assertEqual("信用点增加50", self.rank(opts)[0])

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
        self.assertTrue(NOT_EVENT_PAGE.search("请决定闪光效果。"))   # 闪光变体页被当成事件点了第 1 张（2026-10-25）
        self.assertTrue(NOT_EVENT_PAGE.search("收藏自定义"))   # 存档库页被当成事件连点（2026-10-27 12:02）
        self.assertTrue(NOT_EVENT_PAGE.search("批量分解"))
        from utils import at_save_library
        page = lambda *names: SimpleNamespace(all_texts=[SimpleNamespace(name=n) for n in names])
        self.assertTrue(at_save_library(page("存储数据", "批量分解", "收藏自定义", "装备")))
        self.assertFalse(at_save_library(page("存储数据收集完成", "下一步")))
        self.assertTrue(NOT_EVENT_OPTION.search("独特卡牌平均费用0.9"))
        self.assertTrue(NOT_EVENT_OPTION.search("4368 TB"))
        self.assertTrue(NOT_EVENT_OPTION.search("39823TB"))
        self.assertTrue(NOT_EVENT_OPTION.search("B3813 TB."))
        self.assertIsNone(NOT_EVENT_OPTION.search("收起有用的东西随机获得稀有~传说装备"))
        for d in ("5", "0", "901", "12"):      # 路线图上 event9 误中读到的数字
            self.assertTrue(NOT_EVENT_OPTION.search(d), d)
        self.assertIsNone(NOT_EVENT_OPTION.search("献上赞美信用点增加100"))
        from utils import not_event_option
        for d in ("-", "X", "•", "京四", "日92", "1684暴击", "弱点", "T9"):
            self.assertTrue(not_event_option(d), d)
        for d in ("拿走树枝", "就此离开事件结束", "献上赞美信用点增加100"):
            self.assertFalse(not_event_option(d), d)

    def test_target_heal(self):
        st = dict(self.need, hp_pct=60)
        self.assertEqual(["信用点增加300", "恢复50%生命值", "信用点增加100"],
                         self.rank(["信用点增加100", "恢复50%生命值", "信用点增加300"], state=st))
        # 血量 <25%：死了只能带出最近航路点的存档，回血排到删卡、复制前面
        st = dict(self.need, hp_pct=10)
        self.assertEqual(["恢复50%生命值", "移除1张卡牌", "复制选中的1张卡牌"],
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

    def test_imprint_route_prefers_shop(self):
        # 刷刻印：商店节点（休息 + 商店加分）要高过精英，目标刻印主要在商店
        w = cs.route_weights(cs.MODE_TARGET, 0, 80, imprint=True)
        self.assertGreater(w["types"]["休息"] + w["shop"], w["types"]["精英"])
        self.assertEqual(cs.ROUTE_WEIGHTS[cs.MODE_TARGET]["shop"], cs.route_weights(cs.MODE_TARGET, 0, 80)["shop"])

    def test_equipment_event_source_bonus(self):
        # 凝结的光辉残片只能在第 1 层（外围）「前往更深之处」选「劈向地脉」拿：第 1 层事件加分，拿到后不加
        src = cs.equipment_event_sources(["混沌指控", "凝结的光辉残片", "坠落的王冠"])
        self.assertEqual([("凝聚的辉光残片", "前往更深之处", "劈向地脉", 0)],
                         [(s["equipment"], s["event"], s["option"], s["layer"]) for s in src])
        self.assertEqual(cs.EVENT_SOURCE_BONUS, cs.event_source_bonus(src, 0))
        self.assertEqual(0, cs.event_source_bonus(src, 1))
        self.assertEqual(0, cs.event_source_bonus(src, 0, ["凝聚的辉光残片"]))
        w = cs.route_weights(cs.MODE_TARGET, 0, 80, cs.event_source_bonus(src, 0))["types"]
        self.assertEqual(cs.ROUTE_WEIGHTS[cs.MODE_TARGET]["types"]["事件"] + cs.EVENT_SOURCE_BONUS, w["事件"])
    def test_want_last_shop_once(self):
        from utils import _want_shop
        plan = {"layer": 2, "done": 1, "steps": [{"type": "休息"}, {"type": "首领"}]}
        task = SimpleNamespace(node_status={"pass_final_boss_count": 2, "full_route": plan, "shop": False,
                                            "total_rounds": 0, "node_count": 2})
        self.assertTrue(_want_shop(task))                      # 「进入商店」没开也进最后一个商店
        task.node_status["shop_visited"] = (0, 2, 2)
        self.assertFalse(_want_shop(task))                     # 出来后不再进
        task.node_status["shop"] = True
        self.assertTrue(_want_shop(task))

    def test_observe_modifiers(self):
        # 实录观测面板文字（OCR 拼接）
        e4 = ("存储数据保存上限140PT[暴君3]精英、首领区异形的攻击与生命[疾病3]生命值上限减少40%"
              "[愤怒1]异形每3回合获得士气1[疏忽1]回合开始时，随机丢掉1张卡牌")
        mods = cs.parse_modifiers(e4)
        self.assertEqual([("暴君", 3), ("疾病", 3), ("愤怒", 1), ("疏忽", 1)], [(n, lv) for n, lv, _ in mods])
        ok, why = cs.judge_modifiers(mods)
        self.assertFalse(ok)
        self.assertIn("暴君+疾病", why)
        ok, _ = cs.judge_modifiers(cs.parse_modifiers("存储数据保存上限140PT·稀有命运触发率增加50%[精英1]追加2个精英区[不安1]无法在安全区休息"))
        self.assertTrue(ok)
        ok, why = cs.judge_modifiers(cs.parse_modifiers("[损失1]战斗信用点减少40%[精英2]无法获得存储数据"))
        self.assertFalse(ok)
        self.assertEqual([], cs.parse_modifiers("[欺诈]威胁他退下"))      # 事件选项的方括号不算词条
        self.assertEqual(8, cs.observe_start_difficulty(None))          # 用户 2026-10-25：锁定 Ⅷ
        self.assertEqual(10, cs.observe_start_difficulty(10))
        self.assertEqual(130, cs.config_overrides(cs.MODE_TARGET, "罗丝薇瑟", {})["存储数据保存上限大于多少"])

    def test_pt_ledger(self):
        from utils import _pt_used, _pt_room
        task = SimpleNamespace(chaos_mode=cs.MODE_TARGET, chaos_pt_cap=150, log_info=lambda *a, **k: None,
                               node_status={"removed_card_count": 3, "copy_count": 2, "neutral_card_count": 0})
        self.assertEqual(60, _pt_used(task))
        self.assertTrue(_pt_room(task, "复制"))           # 第 3 次复制 40：60+40=100 ≤ 150
        task.node_status.update(copy_count=3, god_spark_count=2)
        self.assertEqual(140, _pt_used(task))
        self.assertFalse(_pt_room(task, "神闪"))          # 140+20 > 150：正确的神闪也不选
        self.assertFalse(_pt_room(task, "移除"))
        task.chaos_mode = cs.MODE_EXPLORE                  # 探索度不记账
        self.assertTrue(_pt_room(task, "神闪"))

    def test_event_score_pt_room(self):
        base = {"removed": 0, "need_remove": 3, "need_copy": 1, "copy_count": 2, "pt_room": 30}
        copy, _ = cs.score_effects({"copy_card": 1}, cs.MODE_TARGET, base)
        remove, _ = cs.score_effects({"remove_card": 1}, cs.MODE_TARGET, base)
        self.assertLess(copy, -100)                        # 第 3 次复制要 40 > 剩 30
        self.assertGreater(remove, 0)                      # 删 1 张 20 ≤ 30

    def test_need_copy_counts_done(self):
        from utils import _chaos_strategy_state
        import utils
        task = SimpleNamespace(node_status={"copy_count": 2}, chaos_plan={"copy": ["剑鸣九霄", "剑鸣九霄"]})
        orig = (utils._get_current_hp_percent, utils._get_current_credit, utils._member_deck_state, utils._equipment_priority)
        utils._get_current_hp_percent = lambda t: 100
        utils._get_current_credit = lambda t: 0
        utils._member_deck_state = lambda t: {}
        utils._equipment_priority = lambda t, slot: []
        try:
            self.assertEqual(0, _chaos_strategy_state(task)["need_copy"])   # 复制够了就不再加分
        finally:
            (utils._get_current_hp_percent, utils._get_current_credit, utils._member_deck_state,
             utils._equipment_priority) = orig

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


class TestRestChoice(unittest.TestCase):
    """休息页：满血不休息改训练；目标卡组有待冥想的卡、钱够冥想就冥想（2026-10-25 实录）。"""
    cost = "4"      # 实录：冥想费用 80 被 OCR 成 4

    def run_rest(self, hp, credit, pending, mode=cs.MODE_TARGET, golden=False):
        import utils
        box = lambda name, x, y: SimpleNamespace(name=name, x=x * 1920 - 20, y=y * 1080 - 10, width=40, height=20)
        texts = [box("安全区采取", 0.5, 0.1), box("训练", 0.85, 0.18), box("免费", 0.85, 0.23), box(self.cost, 0.8, 0.7)]
        clicks = []
        task = SimpleNamespace(width=1920, height=1080, all_texts=texts, chaos_mode=mode,
                               node_status={"flash_or_rest": True}, log_info=lambda *a, **k: None,
                               box_of_screen=lambda *a: None, sleep=lambda *a: None, move_relative=lambda *a: None,
                               click_box=lambda b: clicks.append(b.name))
        def find_one(feature_name=None, box=None, threshold=0):
            if feature_name == "meditate":
                return box_("meditate")
            if golden and "special_flash_luosi" in feature_name and threshold <= 0.75:
                return box_("golden")       # 实录金色卡牌匹配度 0.75
            return None
        task.find_one = find_one
        box_ = lambda n: SimpleNamespace(name=n, x=0.8 * 1920 - 20, y=0.62 * 1080, width=40, height=40, confidence=0.75)
        patches = {"_find_rest_feature": lambda t: box_("rest"), "_get_region_text": lambda t, r: "免费",
                   "_member_deck_state": lambda t: {"冥想": {"剑鸣九霄": pending}},
                   "_get_current_credit": lambda t: credit, "_get_current_hp_percent": lambda t: hp,
                   "_wait_for_rest_confirm": lambda t: True, "find_box_at_point": lambda *a: None}
        orig = {k: getattr(utils, k) for k in patches}
        try:
            for k, v in patches.items():
                setattr(utils, k, v)
            utils.handle_rest(task)
        finally:
            for k, v in orig.items():
                setattr(utils, k, v)
        return clicks

    def test_full_hp_trains(self):
        self.assertEqual(["训练"], self.run_rest(hp=100, credit=50, pending=False))

    def test_low_hp_rests(self):
        self.assertEqual(["rest"], self.run_rest(hp=40, credit=50, pending=False))

    def test_target_meditates_below_config_threshold(self):
        self.assertEqual(["meditate"], self.run_rest(hp=100, credit=269, pending=True))

    def test_meditate_needs_80_even_if_cost_misread(self):
        self.assertEqual(["训练"], self.run_rest(hp=100, credit=50, pending=True))

    def test_golden_card_clicked_first(self):
        # 主战员头上的金色卡牌（灵光一闪）先点，匹配度 0.75 也要认
        moves = []
        import utils
        old = utils._move_and_click
        utils._move_and_click = lambda t, x, y: moves.append((round(x, 2), round(y, 2)))
        try:
            clicks = self.run_rest(hp=100, credit=500, pending=True, golden=True)
        finally:
            utils._move_and_click = old
        self.assertEqual([], clicks)
        self.assertEqual(1, len(moves))

    def test_train_retries_when_click_ignored(self):
        import time as _t
        clicks = self.run_rest(hp=100, credit=50, pending=False)
        self.assertEqual(["训练"], clicks)


class TestLayerReset(unittest.TestCase):
    def test_pt_ledger_survives_layer(self):
        from utils import reset_layer_status
        task = SimpleNamespace(node_status={"copy_count": 2, "god_spark_count": 1, "removed_card_count": 3,
                                            "pass_final_boss_count": 1})
        reset_layer_status(task)
        self.assertEqual((2, 1, 3), (task.node_status["copy_count"], task.node_status["god_spark_count"],
                                     task.node_status["removed_card_count"]))

    def test_copy_needed(self):
        from utils import _copy_needed
        task = SimpleNamespace(chaos_mode=cs.MODE_TARGET, chaos_plan={"copy": ["剑鸣九霄", "剑鸣九霄"]},
                               node_status={"copy_count": 1})
        self.assertTrue(_copy_needed(task))
        task.node_status["copy_count"] = 2
        self.assertFalse(_copy_needed(task))

    def test_flash_done_counts_copies(self):
        from utils import _flash_done
        plan = {"flash": [{"name": "剑鸣九霄"}] * 3 + [{"name": "明灭剑"}]}
        task = SimpleNamespace(chaos_plan=plan, node_status={"flash_ok": ["剑鸣九霄", "明灭剑"]})
        self.assertFalse(_flash_done(task, "剑鸣九霄"))
        self.assertTrue(_flash_done(task, "明灭剑"))
        task.node_status["flash_ok"] += ["剑鸣九霄", "剑鸣九霄"]
        self.assertTrue(_flash_done(task, "剑鸣九霄"))

    def test_ocr_name_one_char_off(self):
        from utils import _ocr_name_matches
        self.assertTrue(_ocr_name_matches("明灰剑", "明灭剑"))
        self.assertFalse(_ocr_name_matches("黑云奥义：残", "黑云奥义：灭"))
        self.assertFalse(_ocr_name_matches("明剑", "灭剑"))
        self.assertTrue(_ocr_name_matches(cs.base_card_name("明灰剑 (强化)"), "明灭剑"))

    def test_ocr_desc_match(self):
        from utils import _ocr_desc_matches
        desc = "明暗分裂时，分裂成剑华：伤害464%明、剑华：暗1回合内士气1"
        self.assertTrue(_ocr_desc_matches("灰剑", desc, "明灭剑"))
        self.assertFalse(_ocr_desc_matches("灰剑", desc, "剑鸣九霄"))
        self.assertFalse(_ocr_desc_matches("剑刃破晓", "伤害232%丢弃1", "明灭剑"))
        self.assertFalse(_ocr_desc_matches("灰剑", "生成3张剑穗加入手牌", "明灭剑"))

    def test_run_state_roundtrip(self):
        import tempfile
        import utils
        old = utils.RUN_STATE_FILE
        utils.RUN_STATE_FILE = os.path.join(tempfile.mkdtemp(), "s.json")
        try:
            logs = []
            src = SimpleNamespace(chaos_pt_cap=130, log_info=logs.append, member_status={"deck": {"冥想": {"明灭剑": True}}},
                                  node_status={"removed_card_count": 3, "copy_count": 2, "flash_ok": ["循环之刃"]})
            utils.save_run_state(src)
            dst = SimpleNamespace(log_info=logs.append, member_status={"deck": {}},
                                  node_status={"removed_card_count": 0, "total_rounds": 1})
            self.assertTrue(utils.restore_run_state(dst))
            self.assertEqual(130, dst.chaos_pt_cap)
            self.assertEqual(3, dst.node_status["removed_card_count"])
            self.assertEqual(["循环之刃"], dst.node_status["flash_ok"])
            self.assertTrue(dst.member_status["deck"]["冥想"]["明灭剑"])
            utils.clear_run_state(dst)
            self.assertFalse(utils.restore_run_state(dst))
        finally:
            utils.RUN_STATE_FILE = old


class TestVariantSuffix(unittest.TestCase):
    def test_base_name(self):
        self.assertEqual("明灭剑", cs.base_card_name("明灭剑 （闪击)"))
        self.assertEqual("明灭剑", cs.base_card_name("明灭剑(强化)"))
        self.assertEqual("黑云奥义：残", cs.base_card_name("黑云奥义：残"))

    def test_pick_with_suffix(self):
        choices = [{"name": "明灭剑（闪击）", "description": "伤害100%"},
                   {"name": "明灭剑（强化）", "description": "伤害464%必定触发弱点攻击"}]
        targets = [{"name": "明灭剑", "desc": "伤害464%必定触发弱点攻击"}]
        self.assertEqual(1, cs.pick_flash_variant("明灭剑 （强化)", choices, targets))


class TestVariantByNumber(unittest.TestCase):
    def test_preset_with_god_line(self):
        db = cs.get_db()
        vs = db.card_variants(db.find_card("明灭剑"))
        preset = [{"name": "明灭剑", "n": 5, "desc": vs[5]["desc"] + "\n必定触发弱点攻击"}]
        choices = [{"name": "明灭剑", "description": vs[i]["desc"]} for i in (1, 5, 3)]
        self.assertEqual(1, cs.pick_flash_variant("明灭剑", choices, preset))
        wrong = [{"name": "明灭剑", "description": vs[i]["desc"]} for i in (1, 2, 3)]
        self.assertIsNone(cs.pick_flash_variant("明灭剑", wrong, preset))
        # 神闪页（0.9）不放宽
        self.assertIsNone(cs.pick_flash_variant("明灭剑", choices, preset, min_sim=0.9))


class TestRemoveSplitOcr(unittest.TestCase):
    def test_split_remove(self):
        self.assertEqual(2, cs.parse_effects("开始赎罪所有主战员压力增加20，除2张所选卡牌移").get("remove_card"))


class TestModifierOcr(unittest.TestCase):
    def test_variant_char(self):
        mods = cs.parse_modifiers("【精英2】多2个精英【疎忽1】某效果")
        self.assertEqual("疏忽", mods[1][0])
        self.assertFalse(cs.judge_modifiers(mods)[0])


class TestGodNames(unittest.TestCase):
    def test_all_gods(self):
        for d in ("闪光：基尔肯", "赋予1张所选卡牌赛克雷德闪光", "随机卡牌维托尔闪光"):
            self.assertTrue(cs.parse_effects(d).get("god_spark"), d)
        self.assertFalse(cs.parse_effects("选择基尔肯的神眷者闪光").get("god_spark"))


class TestGodSparkAllowed(unittest.TestCase):
    """2026-10-25 用户：和预设一致、不爆 PT 的神闪可以拿。"""
    st = {"removed": 0, "need_remove": 0, "need_spark": 1, "god_spark_wanted": 1, "pt_room": 40}

    def test_pick_god_spark_when_wanted_and_room(self):
        e = cs.parse_effects("观察状况赋予1张所选卡牌迪亚洛斯闪光")
        self.assertTrue(e.get("god_spark_pick"))
        self.assertGreater(cs.score_effects(e, cs.MODE_TARGET, self.st)[0], 100)

    def test_no_room_or_not_wanted(self):
        e = cs.parse_effects("观察状况赋予1张所选卡牌迪亚洛斯闪光")
        self.assertLess(cs.score_effects(e, cs.MODE_TARGET, dict(self.st, pt_room=10))[0], 0)
        self.assertLess(cs.score_effects(e, cs.MODE_TARGET, dict(self.st, god_spark_wanted=0))[0], 0)

    def test_wanted_list(self):
        from utils import _god_spark_wanted
        task = SimpleNamespace(chaos_plan={"flash": [{"name": "明灭剑", "god_spark": "x"}, {"name": "剑鸣九霄", "god_spark": "y"},
                                                     {"name": "剑鸣九霄", "god_spark": "y"}, {"name": "剑刀破晓"}]},
                               node_status={"god_ok": ["明灭剑"]})
        self.assertEqual(["剑鸣九霄"], _god_spark_wanted(task))


class TestGameRestart(unittest.TestCase):
    def test_launcher_path(self):
        import tempfile
        from game_restart import launcher_path
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "bin"))
        os.makedirs(os.path.join(root, "WeGameLauncher"))
        exe = os.path.join(root, "bin", "ssr-xcent.exe")
        self.assertIsNone(launcher_path(exe))
        open(os.path.join(root, "WeGameLauncher", "launcher.exe"), "w").close()
        self.assertEqual(launcher_path(exe), os.path.join(root, "WeGameLauncher", "launcher.exe"))
        self.assertIsNone(launcher_path(None))


class TestOctopusRush(unittest.TestCase):
    def _task(self, seen=False, layers=1):
        import types
        t = types.SimpleNamespace(config={"章鱼哥速刷": True}, all_texts=[], clicks=[],
                                  node_status={"pass_final_boss_count": layers, "success_rounds": 0})
        if seen:
            t.node_status["octopus_seen"] = True
        t.log_info = lambda *a, **k: None
        t.sleep = lambda *a: None
        return t

    def test_exit_when_not_seen(self):
        import utils
        clicks = []
        old = utils._move_and_click
        utils._move_and_click = lambda task, x, y: clicks.append((x, y))
        try:
            self.assertTrue(utils._finish_only_first_layer(self._task()))
            self.assertEqual(clicks, [(0.959, 0.051)])
            clicks.clear()
            # 章鱼哥来了但没掉目标装备，也退出重开（用户 2026-10-25）
            self.assertTrue(utils._finish_only_first_layer(self._task(seen=True)))
            clicks.clear()
            self.assertFalse(utils._finish_only_first_layer(self._task(layers=2)))
            # 默认（只认混沌之识关）：拿到别的目标装备就打完
            other = self._task(seen=True)
            other.node_status["target_equip_got"] = "堕落之冠"
            self.assertFalse(utils._finish_only_first_layer(other))
            self.assertEqual(clicks, [])
            # 用户 2026-10-26：开了只认混沌之识，别的目标装备不算，没掉混沌之识就退出重开
            other = self._task(seen=True)
            other.config["章鱼哥速刷只认混沌之识"] = True
            other.node_status["target_equip_got"] = "堕落之冠"
            self.assertTrue(utils._finish_only_first_layer(other))
            clicks.clear()
            got = self._task(seen=True)
            got.config["章鱼哥速刷只认混沌之识"] = True
            got.node_status["target_equip_got"] = "混沌之识"
            got.node_status["chaos_core_got"] = "混沌之识"
            self.assertFalse(utils._finish_only_first_layer(got))
            self.assertEqual(clicks, [])
            # 用户 2026-10-26：只认混沌之识时，第 2、3 层遇到章鱼哥没掉混沌之识也退出重开
            late = self._task(seen=True, layers=2)
            late.config["章鱼哥速刷只认混沌之识"] = True
            self.assertTrue(utils._finish_only_first_layer(late))
            clicks.clear()
            late = self._task(seen=True, layers=2)
            late.config["章鱼哥速刷只认混沌之识"] = True
            late.node_status["chaos_core_got"] = "混沌之识"
            self.assertFalse(utils._finish_only_first_layer(late))
            late = self._task(seen=False, layers=2)
            late.config["章鱼哥速刷只认混沌之识"] = True
            self.assertFalse(utils._finish_only_first_layer(late))
            self.assertEqual(clicks, [])
        finally:
            utils._move_and_click = old

    def test_note_octopus(self):
        import types
        import utils
        t = self._task()
        t.frame = None
        t.all_texts = [types.SimpleNamespace(name="赛内克图斯")]
        old = utils.chaos_trace.step
        utils.chaos_trace.step = lambda *a, **k: None
        try:
            utils.note_octopus(t)
        finally:
            utils.chaos_trace.step = old
        self.assertTrue(t.node_status["octopus_seen"])
        self.assertIn("octopus_seen", utils.RUN_LEVEL_KEYS)
        self.assertTrue(utils.OCTOPUS_BREAK_IN.match("乱入1"))
        self.assertFalse(utils.OCTOPUS_BREAK_IN.match("乱入0"))
        self.assertFalse(utils.OCTOPUS_BREAK_IN.match("暗星趁乱入侵"))

    def test_octopus_drop_names(self):
        import types
        import utils
        drops = utils.octopus_drop_names()
        for n in ("混沌之识", "混沌指控", "乱世之触", "错乱之骰", "随机之球", "灾难之像", "怪异之壳"):
            self.assertIn(n, drops)
        self.assertNotIn("堕落之冠", drops)
        t = self._task()
        t.frame = None
        t.all_texts = [types.SimpleNamespace(name="乱世之触")]
        old = utils.chaos_trace.step
        utils.chaos_trace.step = lambda *a, **k: None
        try:
            utils.note_octopus(t)
        finally:
            utils.chaos_trace.step = old
        self.assertTrue(t.node_status["octopus_seen"])


class TestOctopusRoute(unittest.TestCase):
    def test_first_layer_normal_first(self):
        w = cs.route_weights(cs.MODE_TARGET, 0, None, 0, octopus=True)["types"]
        self.assertGreater(w["小怪"], max(w["事件"], w["精英"], w["休息"]))
        # 所有战斗都高于问号事件（用户 2026-10-25），事件有目标装备加分也一样
        for bonus in (0, 3):
            w = cs.route_weights(cs.MODE_TARGET, 0, 50, bonus, octopus=True)["types"]
            self.assertGreater(w["精英"], max(w["事件"], w["休息"]))
            self.assertGreater(w["小怪"], w["精英"])
        w2 = cs.route_weights(cs.MODE_TARGET, 1, None, 0, octopus=True)["types"]
        self.assertEqual(w2, cs.ROUTE_WEIGHTS[cs.MODE_TARGET]["types"])
        self.assertEqual(cs.route_weights(cs.MODE_TARGET, 0)["types"], cs.ROUTE_WEIGHTS[cs.MODE_TARGET]["types"])


class TestStorageFull(unittest.TestCase):
    def test_stop_on_storage_full(self):
        import types
        import utils
        box = lambda n: types.SimpleNamespace(name=n, x=0, y=0, width=1, height=1)
        state = {"disabled": False, "clicks": []}
        t = types.SimpleNamespace(config={}, frame=None, all_texts=[box("存储空间不足"), box("确认")],
                                  log_info=lambda *a, **k: None, click_box=lambda b: state["clicks"].append(b.name),
                                  disable=lambda: state.update(disabled=True))
        # 追踪写到临时目录：以前写进 dev_out/chaos_trace，留下一条假的「存储空间不足」（2026-10-27 查问题时被误导）
        import tempfile
        import chaos_trace
        with tempfile.TemporaryDirectory() as tmp:
            old_root, chaos_trace.TRACE_ROOT = chaos_trace.TRACE_ROOT, tmp
            try:
                self.assertTrue(utils.handle_storage_full(t))
            finally:
                chaos_trace.TRACE_ROOT = old_root
        self.assertTrue(state["disabled"])
        self.assertEqual(state["clicks"], ["确认"])
        t.all_texts = [box("进入")]
        self.assertFalse(utils.handle_storage_full(t))


class TestDiceReroll(unittest.TestCase):
    """掷骰子失败页（实机 2026-10-27 03:00）：「再次滚动」消耗 2，右上角资源 30/30。用户：骰子失败了可以重投。"""

    def _task(self, points="30/30", node=5, rarity="稀有"):
        import types
        box = lambda x, y, n: types.SimpleNamespace(name=n, x=x * 1920 - 40, y=y * 1080 - 15, width=80, height=30,
                                                    area=lambda: 2400)
        clicks = []
        t = types.SimpleNamespace(width=1920, height=1080, node_status={"node_count": node},
                                  all_texts=[box(0.5, 0.678, "失败"), box(0.266, 0.9, "再次滚动"),
                                             box(0.466, 0.9, "2"), box(0.666, 0.9, "下一步"),
                                             box(0.916, 0.104, points)],
                                  log_info=lambda *a, **k: None, sleep=lambda *a: None,
                                  move_relative=lambda *a: None, click=lambda x, y, **k: clicks.append((x, y)),
                                  _event_rarity=(node, rarity, "生命循环"))
        return t, clicks

    def test_reroll_until_limit_then_next(self):
        import utils
        t, clicks = self._task()
        for _ in range(utils.DICE_REROLL_MAX):
            self.assertTrue(utils.handle_negotiation(t))
        self.assertTrue(utils.handle_negotiation(t))
        self.assertAlmostEqual(0.266, clicks[0][0], places=2)
        self.assertEqual(utils.DICE_REROLL_MAX, sum(1 for x, _ in clicks if x < 0.4))
        self.assertEqual((0.665, 0.899), clicks[-1])
        t.node_status["node_count"] = 6                      # 下一个节点的骰子重新计数
        t._event_rarity = (6, "稀有", "生命循环")
        utils.handle_negotiation(t)
        self.assertLess(clicks[-1][0], 0.4)

    def test_only_rare_events(self):
        """用户 2026-10-27：重投只用于稀有事件；普通事件、没认出的事件（或上个节点的记录）直接下一步。"""
        import utils
        for rarity, node in (("普通", 5), (None, 5), ("稀有", 4)):
            t, clicks = self._task(rarity=rarity)
            t._event_rarity = (node, rarity, "生命循环" if rarity else None)
            self.assertTrue(utils.handle_negotiation(t))
            self.assertEqual([(0.665, 0.899)], clicks, (rarity, node))

    def test_event_rarity_from_options(self):
        """同名事件分普通/稀有两版、选项不同：按画面选项对到哪一版。"""
        rare = ["协助精灵仪式 移除2张所选卡牌 最大生命值增加5%", "接过生命之火 在随机3张中立普通~稀有卡牌中选择1张获得",
                "摘走花朵 强制获得精灵的咒术 获得生命之花"]
        normal = ["尝试拯救花朵 移除1张所选卡牌 最大生命值增加5%", "接过生命之火 在随机3张中立普通卡牌中选择1张获得",
                  "摘走花朵 强制获得精灵的咒术 获得暮色生命之花"]
        self.assertEqual(("生命之花", "稀有"), (lambda e: (e["name"], e["rarity"]))(cs.match_event_options(rare)[0]))
        self.assertEqual(("生命之花", "普通"), (lambda e: (e["name"], e["rarity"]))(cs.match_event_options(normal)[0]))

    def test_cost_ignores_icon_read_as_nine(self):
        import types
        import utils
        t, clicks = self._task(points="3/30")
        t.all_texts.insert(0, types.SimpleNamespace(name="9", x=0.408 * 1920 - 10, y=0.9 * 1080 - 15, width=20,
                                                    height=30, area=lambda: 600))
        self.assertTrue(utils.handle_negotiation(t))
        self.assertLess(clicks[-1][0], 0.4)                  # 花 2、剩 3，够重投

    def test_not_enough_points(self):
        import utils
        t, clicks = self._task(points="1/30")
        self.assertTrue(utils.handle_negotiation(t))
        self.assertEqual([(0.665, 0.899)], clicks)

    def test_cost_missed_by_ocr_defaults_to_two(self):
        """实录 07:55：页面写着 2、资源 18/30，OCR 没读到价格，以前就跳过了。"""
        import utils
        t, clicks = self._task(points="18/30")
        t.all_texts = [b for b in t.all_texts if b.name != "2"]
        self.assertTrue(utils.handle_negotiation(t))
        self.assertLess(clicks[-1][0], 0.4)
        t, clicks = self._task(points="1/30")
        t.all_texts = [b for b in t.all_texts if b.name != "2"]
        utils.handle_negotiation(t)
        self.assertEqual([(0.665, 0.899)], clicks)

    def test_wait_for_buttons_before_skipping(self):
        import utils
        t, clicks = self._task()
        full = list(t.all_texts)
        t.all_texts = [b for b in full if b.name in ("失败", "30/30")]
        self.assertTrue(utils.handle_negotiation(t))
        self.assertEqual([], clicks)                         # 按钮还没出来：不点下一步
        t.all_texts = full
        self.assertTrue(utils.handle_negotiation(t))
        self.assertLess(clicks[-1][0], 0.4)                  # 出来了就重投

    def test_no_reroll_button_skips_after_waits(self):
        import utils
        t, clicks = self._task()
        t.all_texts = [b for b in t.all_texts if b.name != "再次滚动"]
        for _ in range(utils.DICE_BUTTON_WAITS):
            self.assertTrue(utils.handle_negotiation(t))
        self.assertEqual([], clicks)
        self.assertTrue(utils.handle_negotiation(t))
        self.assertEqual([(0.665, 0.899)], clicks)


class TestEquipmentQualityColor(unittest.TestCase):
    """装备品质按颜色认（实机 RGB）：空槽的暗灰色以前被当成传说。"""

    def _quality(self, rgb, allow_empty=True):
        import numpy as np
        import utils
        frame = np.zeros((1080, 1920, 3), np.uint8)
        frame[540, 960] = rgb[::-1]                          # BGR
        t = SimpleNamespace(frame=frame, width=1920, height=1080)
        return utils._equipment_quality_at(t, (0.5, 0.5), allow_empty=allow_empty)[0]

    def test_real_colors(self):
        for rgb, want in [((61, 75, 136), "普通"), ((72, 89, 160), "普通"), ((161, 89, 69), "史诗"),
                          ((165, 110, 86), "史诗"), ((135, 82, 164), "传说"), ((136, 96, 184), "传说"),
                          ((20, 20, 21), ""), ((24, 42, 46), ""), ((57, 61, 70), ""), ((55, 62, 81), "")]:
            self.assertEqual(want, self._quality(rgb), rgb)

    def test_candidate_unknown_not_legendary(self):
        self.assertIsNone(self._quality((33, 43, 52), allow_empty=False))
        self.assertEqual("传说", self._quality((136, 96, 184), allow_empty=False))


class TestSaveCleanup(unittest.TestCase):
    def test_keep_reason(self):
        import save_cleanup as sc
        self.assertEqual(sc.owners_of(["剑光", "万众英雄"]), {"海德玛丽"})
        self.assertIsNone(sc.keep_reason(11520, 20, {"海德玛丽"}, "罗丝薇瑟"))
        self.assertIn("空白", sc.keep_reason(8400, 0, {"绯"}, "罗丝薇瑟"))
        # 用户 2026-10-26：空白存档可删，但目标主战员的、认不出角色的照样保留
        self.assertIsNone(sc.keep_reason(8400, 0, {"绯"}, "罗丝薇瑟", keep_blank=False))
        self.assertIn("目标", sc.keep_reason(8400, 0, {"罗丝薇瑟"}, "罗丝薇瑟", keep_blank=False))
        self.assertIsNotNone(sc.keep_reason(8400, 0, set(), "罗丝薇瑟", keep_blank=False))
        self.assertIn("目标", sc.keep_reason(66000, 60, sc.owners_of(["斩念", "入鞘"]), "罗丝薇瑟"))
        self.assertIsNotNone(sc.keep_reason(None, 20, {"绯"}, "罗丝薇瑟"))
        self.assertIsNotNone(sc.keep_reason(9000, 20, set(), "罗丝薇瑟"))
        self.assertEqual(sc._num("OPT", "PT"), 0)
        self.assertEqual(sc._num("11520 TB", "TB"), 11520)

    def test_confirm_only_when_pending(self):
        import types
        import save_cleanup as sc
        clicks = []
        old = sc._move_and_click
        sc._move_and_click = lambda task, x, y: clicks.append((x, y))
        try:
            box = types.SimpleNamespace(name="确定要分解吗？", x=0, y=0, width=1, height=1)
            t = types.SimpleNamespace(all_texts=[box], log_info=lambda *a, **k: None, sleep=lambda *a: None)
            self.assertTrue(sc.handle_save_cleanup(t))
            self.assertEqual(clicks, [sc.CANCEL])
            sc.start(t)
            t.save_cleanup.update(phase="confirm", pending=time.time(), need=30, selected={3, 5})
            clicks.clear()
            self.assertTrue(sc.handle_save_cleanup(t))
            self.assertEqual(clicks, [sc.CONFIRM])
            self.assertEqual(t.save_cleanup["deleted"], 2)
        finally:
            sc._move_and_click = old


    def test_align(self):
        import save_cleanup as sc
        tbs = [8400, 8400, 8400, 8400, 8400, 9000, 9000, 9600, 10400, 10560, 11520, 11750, 12000, 12720]
        cells = {0: (8400, 0, 0), 1: (8400, 0, 0), 2: (8400, 0, 0), 3: (8400, 0, 0), 4: (8400, 0, 0), 5: (9000, 0, 0)}
        self.assertEqual(sc.align(cells, tbs, 0, 0), 0)
        later = {0: (9600, 0, 0), 1: (10400, 0, 0), 2: (10560, 0, 0), 3: (11520, 0, 0), 4: (11750, 0, 0)}
        self.assertIsNone(sc.align(later, tbs, 0, 6))       # 9600 在序号 7，不是一行的开头
        later = {0: (9000, 0, 0), 1: (9600, 0, 0), 2: (10400, 0, 0), 3: (10560, 0, 0)}
        self.assertEqual(sc.align(later, tbs, 0, 6), 6)
        self.assertIsNone(sc.align({0: (99999, 0, 0)}, tbs, 0, 0))


class TestEquipmentCnNames(unittest.TestCase):
    def test_season_equipment_cn_alias(self):
        import game_db
        db = game_db.GameDB()
        self.assertIn("堕落之冠", db.equipment_aliases("坠落的王冠"))
        # 国服客户端叫「凝聚的辉光残片」，配置写 gamekee 名也要认出来（2026-10-25 被乱世之触按品质顶掉）
        self.assertIn("凝聚的辉光残片", db.equipment_aliases("凝结的光辉残片"))
        self.assertIn("过载动力机关", db.equipment_aliases("超负荷动力机关"))


class TestOctopusRouteBonus(unittest.TestCase):
    def test_normal_beats_event_bonus(self):
        w = cs.route_weights(cs.MODE_TARGET, 0, None, 3, octopus=True)["types"]
        self.assertGreater(w["小怪"], w["事件"])
        w = cs.route_weights(cs.MODE_TARGET, 0, 50, 3, octopus=True)["types"]
        self.assertGreater(w["小怪"], max(w["事件"], w["休息"]))


class TestMemoryProcessConfirm(unittest.TestCase):
    def test_click_confirm_after_select(self):
        import utils_chaos
        clicked = []
        box = SimpleNamespace(x=1560, y=980, width=60, height=30, name="确认")
        task = SimpleNamespace(next_frame=lambda: None, log_info=lambda *a, **k: None,
                               ocr=lambda *a, **k: [SimpleNamespace(name="免费"), box],
                               click=lambda b, after_sleep=0: clicked.append(b.name))
        self.assertTrue(utils_chaos._click_memory_process_confirm(task))
        self.assertEqual(clicked, ["确认"])
        task.ocr = lambda *a, **k: []
        self.assertFalse(utils_chaos._click_memory_process_confirm(task))

    def test_specified_memory_ocr_one_char(self):
        import utils_chaos
        card = lambda n: {"name": n, "description": "记忆/开幕己方技能卡牌叠加时"}
        self.assertTrue(utils_chaos.is_specified_memory("记忆：丧失", card("记忆：丧失")))
        self.assertTrue(utils_chaos.is_specified_memory("记忆：丧失", card("记忆：丧牛")))
        self.assertFalse(utils_chaos.is_specified_memory("记忆：丧失", card("记忆：誓约")))
        # 配置只写「丧失」（2026-10-26 实录精密加工页没认出「记忆：丧牛」）
        self.assertTrue(utils_chaos.is_specified_memory("丧失", card("记忆：丧牛")))
        self.assertFalse(utils_chaos.is_specified_memory("丧失", card("记忆：埋怨")))
        self.assertFalse(utils_chaos.is_specified_memory("丧失", card("记忆：失丧")))


class TestMemberPanel(unittest.TestCase):
    """局内主战员面板（2026-10-25 实机 OCR）：PT 以游戏为准。"""
    ROWS = [(0.182, 0.365, "罗丝薇瑟"), (0.431, 0.367, "凛"), (0.713, 0.366, "米卡"),
            (0.194, 0.578, "模糊的记忆"), (0.358, 0.578, "60/130"), (0.468, 0.577, "模糊的记忆"),
            (0.632, 0.579, "0/130"), (0.742, 0.577, "模糊的记忆"), (0.906, 0.578, "20/130"),
            (0.173, 0.626, "国复制"), (0.365, 0.629, "2/3"), (0.172, 0.671, "國移除"), (0.365, 0.674, "3/5"),
            (0.446, 0.628, "复制"), (0.638, 0.628, "0/3"), (0.369, 0.519, "796")]

    def boxes(self):
        return [SimpleNamespace(x=x * 1920, y=y * 1080, width=0, height=0, name=n) for x, y, n in self.ROWS]

    def test_parse(self):
        import utils
        cols = utils.parse_member_panel(self.boxes(), 1920, 1080)
        self.assertEqual(cols[0], {"name": "罗丝薇瑟", "pt": 60, "pt_cap": 130, "copy": 2, "remove": 3})
        self.assertEqual(cols[1]["name"], "凛")
        self.assertEqual(cols[2]["pt"], 20)

    def test_pt_used_prefers_game(self):
        import utils
        task = SimpleNamespace(node_status={"removed_card_count": 3, "copy_count": 2})
        self.assertEqual(utils._pt_used(task), 60)
        task.node_status.update(pt_game=100, pt_game_ledger=60)
        self.assertEqual(utils._pt_used(task), 100)
        task.node_status["copy_count"] = 3          # 读完以后又复制了一次（+40）
        self.assertEqual(utils._pt_used(task), 140)


class TestMemoryRefresh(unittest.TestCase):
    """选择铭刻的记忆：三张卡各自 4 次重新搜索（2026-10-26 实录第 1 张 4/4 没用就随机选了）。"""

    def _run(self, counts, ns):
        import utils_chaos as uc
        clicks = []
        texts = [SimpleNamespace(x=x * 1920, y=0.824 * 1080, width=0, height=0, name=c)
                 for x, c in zip((0.33, 0.58, 0.83), counts) if c]
        task = SimpleNamespace(all_texts=texts, width=1920, height=1080, node_status=ns,
                               log_info=lambda *a, **k: None, sleep=lambda *a: None)
        old = (uc._get_region_text, uc.recognize_cards, uc.find_target_card, uc._get_config_value, uc._move_and_click)
        uc._get_region_text = lambda t, r: "选择铭刻的记忆"
        uc.recognize_cards = lambda *a, **k: [{"name": "记忆：埋怨", "description": "", "x": 0.2, "y": 0.4}]
        uc.find_target_card = lambda t: ([], [])
        uc._get_config_value = lambda t, k, d=None: "丧失" if k == "指定记忆卡牌" else d
        uc._move_and_click = lambda t, x, y: clicks.append((x, y))
        try:
            uc.handle_memory_card_select(task)
        finally:
            (uc._get_region_text, uc.recognize_cards, uc.find_target_card, uc._get_config_value, uc._move_and_click) = old
        return clicks

    def test_uses_every_column(self):
        ns = {}
        self.assertEqual(self._run(["4/4", "1/4", "1/4"], ns), [(0.211, 0.824)])
        self.assertEqual(self._run(["0/4", "1/4", "0/4"], ns), [(0.461, 0.824)])
        # 次数读不到时按点过的次数，每列最多 4 次
        ns = {"memory_refresh_clicks": [4, 4, 3]}
        self.assertEqual(self._run([None, None, None], ns), [(0.711, 0.824)])
        # 都用完了：随机选一张
        self.assertEqual(self._run(["0/4", "0/4", "0/4"], {}), [(0.2, 0.4)])


class TestGodSparkPage(unittest.TestCase):
    """神闪三选一（2026-10-26 实录）：描述对不上时按游戏图钉选并记 PT；没图钉又没「跳过」就等，不落到普通闪光。"""

    def _run(self, ns, target, skip=False, room=True):
        import utils as u
        clicks = []
        task = SimpleNamespace(all_texts=[SimpleNamespace(x=0, y=0, width=0, height=0, name="闪光：瑟克洛斯")],
                               width=1920, height=1080, node_status=ns, chaos_mode=u.chaos_strategy.MODE_TARGET,
                               chaos_plan={"flash": [{"name": "剑鸣九霄", "god_spark": True, "description": "完全不同"}]},
                               log_info=lambda *a, **k: None, sleep=lambda *a: None)
        cards = [{"name": "剑鸣九霄", "description": d, "x": x, "y": 0.4}
                 for d, x in (("抽取1张自身卡牌", 0.25), ("粉碎抽取1", 0.5), ("士气2", 0.75))]
        names = ("find_box_at_point", "recognize_cards", "find_target_card", "_move_and_click", "_pt_room", "_click_bottom_skip")
        old = {n: getattr(u, n) for n in names}
        u.find_box_at_point = lambda t, x, y: SimpleNamespace(name="查看原件")
        u.recognize_cards = lambda *a, **k: cards
        u.find_target_card = lambda t: (([1], [(0.5, 0.45)]) if target else ([], []))
        u._move_and_click = lambda t, x, y: clicks.append((x, y))
        u._pt_room = lambda t, w: room
        u._click_bottom_skip = lambda t, r: skip
        try:
            u.handle_view_original(task)
        finally:
            for n, f in old.items():
                setattr(u, n, f)
        return clicks

    def test_pinned_variant_counts_pt(self):
        ns = {}
        self.assertEqual(self._run(ns, target=True), [(0.5, 0.45)])
        self.assertEqual(ns["god_spark_count"], 1)

    def test_no_room_waits_for_skip_instead_of_pin(self):
        ns = {}
        self.assertEqual(self._run(ns, target=True, room=False), [])
        self.assertEqual(ns.get("god_spark_count", 0), 0)
        self.assertEqual(ns["god_skip_waits"], 1)

    def test_second_frame_confirms_without_counting(self):
        ns = {}
        self._run(ns, target=True)
        # 同一页第二帧：PT 账就算显示不够也不跳过，只重点一下确认，不再记账
        self.assertEqual(self._run(ns, target=True, room=False), [(0.5, 0.45)])
        self.assertEqual(ns["god_spark_count"], 1)


class TestFateNeutral(unittest.TestCase):
    def test_only_gaining_counts(self):
        from utils import FATE_GIVES_NEUTRAL as f
        self.assertTrue(f.search("拿取获得1张咒术卡牌贫血。"))
        self.assertTrue(f.search("获得1张随机中立卡牌"))
        self.assertIsNone(f.search("灵感每次生成除状态异常、咒术卡牌以外的卡牌时，有25%的概率多生成1张。"))
        self.assertIsNone(f.search("信念战斗开始时，赋予手牌中的攻击卡牌粉碎。"))

    def test_swap_basic_cards_counts(self):
        # 选完游戏面板多 40PT、多 1 次移除：基础卡被换成了中立卡（10-26 02:11、10-27 07:20）
        from utils import FATE_GIVES_NEUTRAL as f
        self.assertTrue(f.search("3张基础普通卡牌更换为"))
        self.assertIsNone(f.search("基础卡牌伤害次数增加1"))

    def _destiny_task(self, columns):
        """命运页：每列一个标题 + 下面的描述，标题在 y≈0.53。"""
        boxes = [SimpleNamespace(name="请选择你的命运", x=900, y=1000, width=120, height=20)]
        for i, (title, desc) in enumerate(columns):
            x = int((0.3 + 0.2 * i) * W)
            boxes.append(SimpleNamespace(name=title, x=x, y=int(0.52 * H), width=60, height=20))
            boxes.append(SimpleNamespace(name=desc, x=x - 20, y=int(0.62 * H), width=100, height=20))
        clicked = []
        task = SimpleNamespace(all_texts=boxes, width=W, height=H, chaos_mode=cs.MODE_TARGET,
                               log_info=lambda *a, **k: None, sleep=lambda *a: None, click_box=clicked.append)
        return task, clicked

    def test_destiny_skips_leader(self):
        # 10-27 07:45「领导」：开局卡组多了中立卡「致命射击」，存进了 08:12 的存档
        import utils as u
        task, clicked = self._destiny_task([("领导", "x"), ("忍耐", "y"), ("3张基础普通卡牌更换为", "z")])
        orig = u.find_box_at_point
        u.find_box_at_point = lambda t, x, y: t.all_texts[0]
        try:
            for _ in range(10):
                clicked.clear()
                self.assertTrue(u.handle_destiny_choice(task))
                self.assertEqual(["忍耐"], [b.name for b in clicked])
        finally:
            u.find_box_at_point = orig


class TestDisconnectDialog(unittest.TestCase):
    def _task(self, names):
        clicks = []
        boxes = [SimpleNamespace(name=n, x=i * 100, y=500, width=10, height=10) for i, n in enumerate(names)]
        return SimpleNamespace(all_texts=boxes, width=1920, height=1080, click_box=clicks.append,
                               log_info=lambda *a, **k: None, sleep=lambda *a: None), clicks

    def test_clicks_continue_never_escape(self):
        import utils as u
        task, clicks = self._task(["卡厄思连接意外断开。", "是否继续?", "逃脱", "继续"])
        self.assertTrue(u.handle_chaos_disconnected(task))
        self.assertEqual([b.name for b in clicks], ["继续"])
        task, clicks = self._task(["卡厄思连接意外断开。", "是否继续?", "逃脱"])
        self.assertFalse(u.handle_chaos_disconnected(task))
        self.assertEqual(clicks, [])

    def test_title_start(self):
        import utils as u
        task, clicks = self._task(["ready", "点击开始"])
        self.assertTrue(u.handle_title_start(task))
        task, clicks = self._task(["开始战斗"])
        self.assertFalse(u.handle_title_start(task))


class TestSaveDifficultyAndModifiers(unittest.TestCase):
    def test_user_banned_modifiers_any_level(self):
        # 用户 2026-10-26：损失、暴君、愤怒、松懈任何级数都不要
        for text in ("[损失1]战斗信用点减少40%", "[暴君1]精英、首领区异形的攻击与生命", "[愤怒1]异形每3回合获得士气1",
                     "[松懈1]每回合随机丢掉1张卡牌"):
            ok, _ = cs.judge_modifiers(cs.parse_modifiers(text))
            self.assertFalse(ok, text)
        ok, _ = cs.judge_modifiers(cs.parse_modifiers("[精英4]追加8个精英区[不安1]无法在安全区休息"))
        self.assertTrue(ok)

    def _lock(self, levels, switches=0):
        import utils_chaos as uc
        import utils_chaos_prep as prep
        calls, flags = [], {}
        task = SimpleNamespace(_difficulty_switches=switches, log_info=lambda *a, **k: None,
                               log_error=lambda *a, **k: None, disable=lambda: flags.setdefault("disabled", True))
        old = (prep._difficulty_level, prep.select_difficulty, uc._get_config_value)
        it = iter(levels)
        prep._difficulty_level = lambda t: next(it)
        prep.select_difficulty = lambda t, want: calls.append(want)
        uc._get_config_value = lambda t, k, d=None: d
        try:
            r = uc._lock_save_difficulty(task)
        finally:
            prep._difficulty_level, prep.select_difficulty, uc._get_config_value = old
        return r, calls, flags, task

    def test_unknown_top_difficulty_switches_back(self):
        # 最高难度推荐等级 130 认不出是第几档，也要切回 Ⅷ（2026-10-26 实录被放行）
        r, calls, flags, _ = self._lock([130])
        self.assertTrue(r)
        self.assertEqual(calls, [8])
        r, calls, flags, task = self._lock([80], switches=1)
        self.assertFalse(r)
        self.assertEqual(task._difficulty_switches, 0)

    def test_stops_instead_of_playing_wrong_difficulty(self):
        r, calls, flags, _ = self._lock([130], switches=1)
        self.assertTrue(r)
        self.assertEqual(calls, [])
        self.assertTrue(flags.get("disabled"))


class TestChaosCoreHandover(unittest.TestCase):
    """用户 2026-10-26：最后一层首领连败的话，拿到混沌之识就停下交给用户。"""

    def setUp(self):
        import utils as u, tempfile
        self.u = u
        self.old = u.LAST_BOSS_FAIL_FILE
        u.LAST_BOSS_FAIL_FILE = os.path.join(tempfile.mkdtemp(), "f.json")

    def tearDown(self):
        self.u.LAST_BOSS_FAIL_FILE = self.old

    def _task(self, passed=0):
        flags = {}
        return SimpleNamespace(chaos_mode=cs.MODE_TARGET, node_status={"pass_final_boss_count": passed},
                               log_info=lambda *a, **k: None, log_error=lambda *a, **k: None,
                               disable=lambda: flags.setdefault("disabled", True)), flags

    def test_hand_over_after_two_last_boss_fails(self):
        u = self.u
        t, f = self._task()
        u._hand_over_on_chaos_core(t, "混沌之识")
        self.assertFalse(f)                                  # 还没连败，继续打
        u._record_last_boss_result(self._task(passed=1)[0], False)   # 第 2 层死的不算
        u._record_last_boss_result(self._task(passed=2)[0], False)
        u._record_last_boss_result(self._task(passed=2)[0], False)
        u._hand_over_on_chaos_core(t, "堕落之冠")
        self.assertFalse(f)
        u._hand_over_on_chaos_core(t, "混沌之识")
        self.assertTrue(f.get("disabled"))

    def test_success_resets(self):
        u = self.u
        u._record_last_boss_result(self._task(passed=2)[0], False)
        u._record_last_boss_result(self._task(passed=2)[0], False)
        u._record_last_boss_result(self._task(passed=3)[0], True)
        t, f = self._task()
        u._hand_over_on_chaos_core(t, "混沌之识")
        self.assertFalse(f)


class TestResumeOnRestore(unittest.TestCase):
    def test_resume_only_after_minimize(self):
        from game_restart import resume_step
        st = {}
        # 用户手动暂停（窗口一直有效）：不恢复
        self.assertFalse(resume_step(st, True, True, 0))
        self.assertFalse(resume_step(st, True, True, 100))
        st = {}
        # 最小化 → 暂停；还原后 5 秒才恢复
        self.assertFalse(resume_step(st, True, False, 0))
        self.assertFalse(resume_step(st, True, True, 10))
        self.assertFalse(resume_step(st, True, True, 13))
        self.assertTrue(resume_step(st, True, True, 15))
        self.assertEqual(st, {})
        # 还原后又最小化：重新计时
        self.assertFalse(resume_step(st, True, False, 20))
        self.assertFalse(resume_step(st, True, True, 21))
        self.assertFalse(resume_step(st, True, False, 22))
        self.assertFalse(resume_step(st, True, True, 23))
        self.assertTrue(resume_step(st, True, True, 28))
        # 没暂停：清状态
        st = {"saw_invalid": True}
        self.assertFalse(resume_step(st, False, True, 0))
        self.assertEqual(st, {})


class TestOctopusMissEscape(unittest.TestCase):
    def test_escape_on_route_page(self):
        import types
        import utils
        clicks = []
        old_click, old_route, old_esc = utils._move_and_click, utils.is_route_selection_page, utils.handle_escape
        utils._move_and_click = lambda task, x, y: clicks.append((x, y))
        utils.is_route_selection_page = lambda task: True
        utils.handle_escape = lambda task: False
        try:
            def task(**ns):
                t = types.SimpleNamespace(config={"章鱼哥速刷": True, "章鱼哥速刷只认混沌之识": True},
                                          node_status=dict(ns))
                t.log_info = lambda *a, **k: None
                t.sleep = lambda *a: None
                return t
            # 没遇到章鱼哥：不逃脱
            self.assertFalse(utils.handle_octopus_miss_escape(task()))
            # 第一层打完、结算页漏退出进了第二层：也逃脱（2026-10-26 22:09）
            l2 = task(pass_final_boss_count=1)
            self.assertTrue(utils.handle_octopus_miss_escape(l2))
            self.assertEqual(clicks, [(0.959, 0.051)])
            clicks.clear()
            self.assertFalse(utils.handle_octopus_miss_escape(task(pass_final_boss_count=1, chaos_core_got="混沌之识")))
            # 拿到混沌之识：不逃脱
            self.assertFalse(utils.handle_octopus_miss_escape(task(octopus_seen=True, chaos_core_got="混沌之识")))
            self.assertEqual(clicks, [])
            # 遇到章鱼哥没掉混沌之识：点右上菜单，5 秒内不重复点但拦住路线处理
            t = task(octopus_seen=True)
            self.assertTrue(utils.handle_octopus_miss_escape(t))
            self.assertTrue(utils.handle_octopus_miss_escape(t))
            self.assertEqual(clicks, [(0.959, 0.051)])
            # 菜单已打开：直接点逃脱，不再点菜单
            utils.handle_escape = lambda task: True
            t2 = task(octopus_seen=True)
            self.assertTrue(utils.handle_octopus_miss_escape(t2))
            self.assertEqual(clicks, [(0.959, 0.051)])
            utils.handle_escape = lambda task: False
            # 回到局外难度页清掉上一局的记录
            utils.clear_octopus_seen(t)
            self.assertNotIn("octopus_seen", t.node_status)
            self.assertFalse(utils.handle_octopus_miss_escape(t))
            # 选项关着：不逃脱
            off = task(octopus_seen=True)
            off.config["章鱼哥速刷只认混沌之识"] = False
            self.assertFalse(utils.handle_octopus_miss_escape(off))
        finally:
            utils._move_and_click, utils.is_route_selection_page, utils.handle_escape = old_click, old_route, old_esc


class TestSelectDifficultySim(unittest.TestCase):
    """模拟左侧难度列：10 档、Ⅹ 未解锁，列表可拖动；靠上沿（<0.2）的圆点了认不出选中。"""

    def _run(self, top, want=8):
        import utils_chaos_prep as prep
        st = {"top": top, "sel": 6}
        P = prep.DIFF_PITCH

        def circles(_frame):
            out = []
            for i in range(10):
                y = st["top"] + i * P
                if 0.15 < y < 0.87:
                    out.append((y, st["sel"] == i + 1, i == 9))
            return out

        def click(task, y):
            for i in range(10):
                cy = st["top"] + i * P
                if abs(cy - y) < 0.03 and i < 9 and 0.17 < cy < 0.8:
                    st["sel"] = i + 1
                    return cy >= 0.2
            return False

        def swipe(x0, y0, x1, y1, duration=0):
            st["top"] = min(0.2, max(0.2 - 9 * P + 0.5, st["top"] + (y1 - y0)))

        import types
        task = types.SimpleNamespace(frame=None, log_info=lambda *a, **k: None, sleep=lambda *a: None,
                                     swipe_relative=swipe)
        old = (prep.difficulty_circles, prep._click_difficulty, prep._difficulty_level, prep.refresh)
        prep.difficulty_circles = circles
        prep._click_difficulty = click
        prep._difficulty_level = lambda t: prep.DIFF_LEVELS[st["sel"]]
        prep.refresh = lambda t: None
        try:
            return prep.select_difficulty(task, want)
        finally:
            prep.difficulty_circles, prep._click_difficulty, prep._difficulty_level, prep.refresh = old

    def test_reaches_eight(self):
        import utils_chaos_prep as prep
        for top in (0.2, 0.1, 0.0, -0.2, 0.2 - 9 * prep.DIFF_PITCH + 0.5):
            self.assertEqual(self._run(top), 8, top)


class TestOctopusAfterRunEnd(unittest.TestCase):
    def test_no_note_after_result(self):
        import types
        import utils
        box = types.SimpleNamespace(name="怪异之壳")
        t = types.SimpleNamespace(node_status={}, all_texts=[box], frame=None,
                                  log_info=lambda *a, **k: None)
        old = utils.chaos_trace.step
        utils.chaos_trace.step = lambda *a, **k: None
        try:
            t._run_ended = True
            utils.note_octopus(t)
            self.assertNotIn("octopus_seen", t.node_status)
            # 回到局外难度页后恢复识别
            utils.clear_octopus_seen(t)
            utils.note_octopus(t)
            self.assertTrue(t.node_status.get("octopus_seen"))
        finally:
            utils.chaos_trace.step = old


class TestLobbyEnterGuard(unittest.TestCase):
    def test_no_enter_without_check(self):
        import time
        import types
        import chaos_strategy
        import utils
        texts = [types.SimpleNamespace(name="每周进展")]
        t = types.SimpleNamespace(chaos_mode=chaos_strategy.MODE_TARGET, all_texts=texts)
        self.assertTrue(utils._lobby_needs_check(t))
        t._lobby_checked_at = time.time()
        self.assertFalse(utils._lobby_needs_check(t))
        # 不是入口页、不是刷存档：不拦
        self.assertFalse(utils._lobby_needs_check(types.SimpleNamespace(chaos_mode=chaos_strategy.MODE_TARGET, all_texts=[])))
        self.assertFalse(utils._lobby_needs_check(types.SimpleNamespace(chaos_mode="", all_texts=texts)))


class TestRouteClickSettle(unittest.TestCase):
    """实录 2026-10-27 06:10：点精英后 4 秒路线页又露出来、节点已淡出，被当成「下一步结算」点了中间、整层路线多算一步。"""

    def run_route(self, clicked_ago):
        import time
        import types
        import utils
        import utils_imprint
        logs = []
        ns = {"enter_new_node": False, "node_count": 8, "pass_final_boss_count": 1,
              "route_clicked_at": time.time() - clicked_ago,
              "full_route": {"layer": 1, "steps": [{"type": "精英"}, {"type": "首领"}], "done": 1}}
        t = types.SimpleNamespace(node_status=ns, config={"刷刻印": True, "刷刻印速刷": True},
                                  member_status={"equipment": {"imprints": ["", "", ""]}},
                                  log_info=logs.append, sleep=lambda s: None,
                                  move_relative=lambda x, y: None, click=lambda x, y: logs.append(("click", x, y)))
        orig = utils.is_route_selection_page, utils.handle_escape
        utils.is_route_selection_page = lambda task: True
        utils.handle_escape = lambda task: False
        try:
            escaped = utils_imprint.handle_rush_escape(t)
            handled = None if escaped else utils.handle_route_selection(t)
        finally:
            utils.is_route_selection_page, utils.handle_escape = orig
        return escaped, handled, ns, logs

    def test_wait_while_settling(self):
        escaped, handled, ns, logs = self.run_route(clicked_ago=4)
        self.assertFalse(escaped)              # 首领前商店刚点进去，不能当成「下一步首领」逃脱
        self.assertTrue(handled)
        self.assertFalse(ns["enter_new_node"])  # 不重复计节点
        self.assertEqual(1, ns["full_route"]["done"])
        self.assertIn("刚点过路线节点", logs[0])

    def test_escape_after_settle(self):
        escaped, _, _, logs = self.run_route(clicked_ago=30)
        self.assertTrue(escaped)
        self.assertIn("首领前", logs[0])
        self.assertEqual(("click", 0.959, 0.051), logs[-1])


class TestRouteNodeRetry(unittest.TestCase):
    """实录 2026-10-27 04:48 / 06:27：读完主战员面板后节点一时认不出，直接盲点中间（04:48 走错了路）。"""

    def run_route(self, pages):
        import types
        import utils
        logs, finds = [], []
        ns = {"enter_new_node": False, "node_count": 3, "pass_final_boss_count": 0, "pt_panel_read": True,
              "full_route": {"layer": 0, "steps": [{"type": "小怪"}, {"type": "精英"}, {"type": "首领"}], "done": 1}}
        t = types.SimpleNamespace(node_status=ns, config={}, log_info=logs.append, sleep=lambda s: None,
                                  width=1920, height=1080, box_of_screen=lambda *a: None,
                                  find_feature=lambda **k: finds.append(k["feature_name"]) or [])
        page = iter(pages)
        orig = utils.is_route_selection_page, utils._move_and_click
        utils.is_route_selection_page = lambda task: next(page, pages[-1])
        utils._move_and_click = lambda task, x, y: logs.append(("click", x, y))
        try:
            handled = utils.handle_route_selection(t)
        finally:
            utils.is_route_selection_page, utils._move_and_click = orig
        return handled, ns, logs, finds

    def test_retry_then_fallback(self):
        handled, ns, logs, finds = self.run_route([True])
        self.assertTrue(handled)
        self.assertEqual(15, len(finds))                     # 5 种节点特征 × 3 次
        self.assertIn("点中间的节点进入", logs[-2])
        self.assertEqual(("click", 0.815, 0.492), logs[-1])
        self.assertEqual(2, ns["full_route"]["done"])

    def test_page_left_during_retry(self):
        handled, ns, logs, finds = self.run_route([True, True, False])
        self.assertFalse(handled)
        self.assertFalse(ns["enter_new_node"])
        self.assertEqual(1, ns["full_route"]["done"])
        self.assertNotIn(("click", 0.815, 0.492), logs)


class TestSaveTargetMemberBackoff(unittest.TestCase):
    """实录 2026-10-27 07:23：重启时停在「训练」确认框，顶栏信息按钮点了 8 分钟没反应。"""

    def test_backoff_after_three_tries(self):
        import time
        import types
        import utils_chaos
        clicks = []
        t = types.SimpleNamespace(node_status={}, config={"刷存档主战员": "海德玛丽"}, log_info=lambda *a: None,
                                  sleep=lambda s: None)
        orig = utils_chaos._get_current_hp_percent, utils_chaos._move_and_click
        utils_chaos._get_current_hp_percent = lambda task: 100
        utils_chaos._move_and_click = lambda task, x, y: clicks.append((x, y))
        try:
            results = [utils_chaos.handle_save_target_member(t) for _ in range(5)]
            self.assertEqual([True, True, True, False, False], results)
            t._save_member_tries = (3, time.time() - 31)        # 30 秒后再试
            self.assertTrue(utils_chaos.handle_save_target_member(t))
        finally:
            utils_chaos._get_current_hp_percent, utils_chaos._move_and_click = orig
        self.assertEqual(4, len(clicks))


class TestSaveMemberIndexRemembered(unittest.TestCase):
    """实录 2026-10-27 08:37：重启后第一个装备页头像特征还没取到，装备被随机分给了队友。"""

    def _task(self, has_feature, ns):
        import types
        lv = [types.SimpleNamespace(x=1200, y=y, width=40, height=20) for y in (340, 580, 820)]
        hit = types.SimpleNamespace(x=1150, y=570, width=60, height=60, confidence=0.7)
        t = types.SimpleNamespace(node_status=ns, log_info=lambda *a: None,
                                  feature_exists=lambda name: has_feature,
                                  find_one=lambda **k: hit if has_feature else None,
                                  box_of_screen=lambda *a: None)
        return t, lv

    def test_match_remembers_and_fallback_uses_it(self):
        import utils
        ns = {}
        t, lv = self._task(True, ns)
        self.assertEqual(1, utils._find_target_member_index(t, lv, (0, 0, 1, 1)))
        self.assertEqual(1, ns["save_member_index"])
        self.assertIn("save_member_index", utils._PERSIST_KEYS)
        t, lv = self._task(False, ns)                       # 重启后：特征没了，按记下的
        self.assertEqual(1, utils._find_target_member_index(t, lv, (0, 0, 1, 1)))
        t, lv = self._task(False, {})                       # 新一局还没记：照旧返回 None
        self.assertIsNone(utils._find_target_member_index(t, lv, (0, 0, 1, 1)))


class TestRestoreShopFlag(unittest.TestCase):
    """实录 2026-10-27 07:23：休息点（带商店）中途重启，新进程 shop=False，商店没进。"""

    def test_restore_sets_shop(self):
        import json
        import os
        import tempfile
        import types
        import utils
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "state.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"cap": 180, "ns": {"pass_final_boss_count": 0}}, f)
            orig = utils.RUN_STATE_FILE
            utils.RUN_STATE_FILE = path
            try:
                t = types.SimpleNamespace(node_status={"shop": False}, member_status={}, config={"进入商店": True},
                                          log_info=lambda *a: None)
                self.assertTrue(utils.restore_run_state(t))
                self.assertTrue(t.node_status["shop"])
            finally:
                utils.RUN_STATE_FILE = orig


class TestPanelEquipmentProbe(unittest.TestCase):
    """2026-10-27 17:4x：面板探路按名字框找位置没找到；改按面板列定位。只点一次、截图走 chaos_trace。"""

    def test_probe_clicks_target_column_slot(self):
        import types
        import utils
        clicks, keys, logs = [], [], []
        t = types.SimpleNamespace(
            member_status={"equipment": {"names": ["", "改良战斗强化服", "女神之泪"]}},
            config={"记录流程追踪": False}, log_info=logs.append, sleep=lambda s: None, next_frame=lambda: None,
            ocr=lambda *a, **k: [], frame=None, send_key=keys.append, width=1920, height=1080)
        orig = utils._move_and_click
        utils._move_and_click = lambda task, x, y: clicks.append((round(x, 3), y))
        try:
            cols = [{"name": "罗丝薇瑟"}, {"name": "海德玛丽"}, {"name": "米卡"}]
            self.assertTrue(utils._probe_panel_equipment(t, cols, "海德玛丽"))
            self.assertAlmostEqual(689 / 1280, clicks[0][0], delta=0.005)   # 截图量的海德玛丽 2 号格 689/1280
            self.assertEqual(["esc"], keys)
            self.assertFalse(utils._probe_panel_equipment(t, cols, "海德玛丽"))   # 每次启动只探一次
        finally:
            utils._move_and_click = orig
