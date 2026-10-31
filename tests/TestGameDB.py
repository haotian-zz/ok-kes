# 本地游戏数据库（game_db）单测：用 2026-10-24 国服实机「罗丝薇瑟 1 号预设」的 OCR 文本做样例，不需要游戏
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ok_tasks"))

from game_db import get_db, norm, similarity, strip_talents  # noqa: E402


class TestText(unittest.TestCase):
    def test_norm_masks_percent_and_punct(self):
        self.assertEqual(norm("伤害464%\n分裂时，分裂成剑华：明"), norm("伤害400% 分裂时 分裂成剑华:明"))

    def test_strip_talents(self):
        self.assertEqual("生成3张剑穗加入手牌", strip_talents("[连接/安息/已复制]生成3张剑穗加入手牌").strip())

    def test_similarity_ignores_line_order(self):
        self.assertGreater(similarity(["抽取1张自身卡牌", "生成3张剑穗加入手牌"], "生成3张剑穗加入手牌\n抽取1张自身卡牌"), 0.9)


class TestCards(unittest.TestCase):
    db = get_db()

    def test_nickname_aliases(self):
        # 用户口头叫法（2026-10-30 刷空档名单）：昵称可以多个、逗号隔开
        for alias, name in (("特蕾莎", "特莱莎"), ("小刀", "特莱莎"), ("雷伊", "蕾伊"), ("双马尾", "蒂菲拉"), ("市长", "海德玛丽")):
            self.assertEqual(name, self.db.combatant(alias)["name"])

    def test_rosweisse_cards(self):
        names = [c["name"] for c in self.db.cards_of("罗丝薇瑟")]
        for n in ("斩念", "入鞘", "明灭剑", "剑鸣九霄", "剑刃破晓", "循环之刃", "基尔肯的神眷者"):
            self.assertIn(n, names)
        self.assertEqual("罗丝薇瑟", self.db.card_owner(self.db.find_card("斩念", owner="罗丝薇瑟"))["name"])

    def test_spark_plus_god_spark(self):
        # 0 费剑鸣九霄：闪光 2「抽取1张自身的卡牌」+ 神闪「此卡费用减少1」
        card = self.db.find_card("剑鸣九霄", owner="罗丝薇瑟")
        m = self.db.match_spark(card, ["[已复制]", "生成3张剑穗加入手牌", "抽取1张自身卡牌", "此卡费用减少1"], cost=0)
        self.assertEqual((2, "add_r_spark_circen_03"), (m["n"], m["god_spark"]))

    def test_spark_variant_with_level_scaled_numbers(self):
        # 实机数值随等级变（库里 1 级 300%，实机 348%），百分比不参与比较
        m = self.db.match_spark(self.db.find_card("循环之刃"), "伤害348% 循环烙印2 纯粹：生成2张剑穗加入 手牌")
        self.assertEqual((2, None), (m["n"], m["god_spark"]))

    def test_x_cost_variant_with_god_spark(self):
        m = self.db.match_spark(self.db.find_card("明灭剑"),
                                "[明暗/唯一/终结/弱点攻击1] 伤害464% X每有1，即可使基础伤害量 +120% "
                                "分裂时，分裂成剑华：明（无限）、剑华：暗（无限）必定触发弱点攻击", cost="X")
        self.assertEqual((5, "add_r_spark_circen_06"), (m["n"], m["god_spark"]))

    def test_same_effect_regardless_of_category(self):
        # 闪光「抽取1张自身的卡牌」和神闪「抽取1张自身卡牌」描述一样就算一样
        self.assertTrue(self.db.same_effect("[已复制] 生成3张剑穗加入手牌 抽取1张自身卡牌", "生成3张剑穗加入手牌\n抽取1张自身的卡牌"))
        self.assertFalse(self.db.same_effect("生成3张剑穗加入手牌", "赋予手牌中所有明、暗卡牌回收"))


class TestEventsAndEquipment(unittest.TestCase):
    db = get_db()

    def test_event_remove_three(self):
        e = self.db.match_event("无名之隙", ["凝视它的眼睛", "闭上眼睛", "缓步靠近"])
        self.assertEqual("雾之都市", e["region"])
        self.assertEqual(3, self.db.find_option(e, "闭上眼睛")["effects"].get("remove_card"))

    def test_equipment_aliases(self):
        # 用户写国际服名「混沌指控」，国服画面上是「混沌之识」
        self.assertIn("混沌之识", self.db.equipment_aliases("混沌指控"))
        self.assertIn("混沌指控", self.db.equipment_aliases("混沌之识"))
        self.assertEqual(["没有这件装备"], self.db.equipment_aliases("没有这件装备"))

    def test_equipment_slot(self):
        self.assertEqual(1, self.db.find_equipment("蚀化臂铠")["slot"])


if __name__ == "__main__":
    unittest.main()
