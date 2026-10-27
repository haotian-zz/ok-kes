# 目标卡组闪光：还要复制的卡不选带「唯一」的变体（用户 2026-10-27：唯一不能复制，复制完再冥想成目标闪光）
import os
import sys
import unittest
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ok_tasks"))

import chaos_strategy  # noqa: E402
import utils  # noqa: E402


def task(copy_count=0):
    return SimpleNamespace(chaos_mode=chaos_strategy.MODE_TARGET, chaos_plan={"copy": ["展开极光"]},
                           node_status={"copy_count": copy_count}, log_info=lambda *a, **k: None)


CARDS = [{"name": "展开极光", "description": "[唯一]生成3张极光加入手牌"},
         {"name": "展开极光", "description": "生成2张极光加入手牌"},
         {"name": "展开极光（闪击）", "description": "[唯生成2张极光，费用减少1"}]


class TestUniqueFlash(unittest.TestCase):
    def test_drop_unique_before_copy(self):
        keep, dropped = utils._drop_unique_if_copy_pending(task(), CARDS)
        self.assertTrue(dropped)
        self.assertEqual(["生成2张极光加入手牌"], [c["description"] for c in keep])

    def test_unique_ok_after_copy(self):
        keep, dropped = utils._drop_unique_if_copy_pending(task(copy_count=1), CARDS)
        self.assertFalse(dropped)
        self.assertEqual(3, len(keep))

    def test_other_card_untouched(self):
        cards = [{"name": "剑雨", "description": "[唯一]伤害200%"}, {"name": "剑雨", "description": "伤害150%"}]
        self.assertEqual((cards, False), utils._drop_unique_if_copy_pending(task(), cards))

    def test_all_unique_falls_back(self):
        cards = [dict(c, description="[唯一]" + c["description"]) for c in CARDS]
        self.assertEqual((cards, False), utils._drop_unique_if_copy_pending(task(), cards))

    def test_copied_instance_may_take_unique(self):
        """实录 2026-10-27 03:15：闪的是复制品（OCR「[安息/已复制]」常认成「巴复制」），原卡还能复制，唯一可以选。"""
        cards = [{"name": "展开极光", "description": "安息已复制生成2张极光剑加入手牌1回合内，极光剑伤害量+50%抽取1"},
                 {"name": "展开极光", "description": "回合开始时，安息/唯一巴复制]光剑加入手牌生成2张极极光剑伤害量+50%"}]
        task2 = task()
        task2.chaos_plan = {"copy": ["展开极光", "展开极光"]}
        task2.node_status = {"copy_count": 1}
        self.assertEqual((cards, False), utils._drop_unique_if_copy_pending(task2, cards))



class TestNeutralVariant(unittest.TestCase):
    """用户 2026-10-27：存档里不允许任何中立卡。实录 02:33 神闪页随机选中漩涡「视作中立卡牌」的变体。"""
    VORTEX = [{"name": "漩涡", "x": 0.27, "description": "对全体敌人造成伤害228%抽取1张中立卡牌淼视作中立卡牌"},
              {"name": "漩涡", "x": 0.52, "description": "对全体敌人造成伤害228%每命中1个目标即可治愈100%"},
              {"name": "漩涡", "x": 0.77, "description": "对全体敌人造成伤害228%1回合内不屈3"}]

    def test_drop_neutral_variant_in_save_mode(self):
        keep, dropped = utils._drop_neutral_variants(task(), self.VORTEX)
        self.assertEqual(self.VORTEX[1:], keep)
        self.assertEqual(self.VORTEX[:1], dropped)

    def test_keep_all_outside_save_mode_or_all_neutral(self):
        t = task()
        t.chaos_mode = chaos_strategy.MODE_LEGACY
        self.assertEqual((self.VORTEX, []), utils._drop_neutral_variants(t, self.VORTEX))
        only = self.VORTEX[:1]
        self.assertEqual((only, []), utils._drop_neutral_variants(task(), only))


if __name__ == "__main__":
    unittest.main()
