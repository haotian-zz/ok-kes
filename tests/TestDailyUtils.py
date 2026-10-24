# 日常工具（utils_daily）和剧情对白判定的单测：用脚本化的假页面驱动，不需要游戏
import os
import sys
import unittest
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ok_tasks"))

import utils_daily  # noqa: E402
from utils import _dialogue_line  # noqa: E402

W, H = 1920, 1080


def box(text, cx, cy, w=0.05, h=0.03):
    """按相对中心坐标造一个 OCR 框。"""
    return SimpleNamespace(name=text, x=(cx - w / 2) * W, y=(cy - h / 2) * H, width=w * W, height=h * H)


HOME = [box("出击", 0.899, 0.266), box("模拟", 0.899, 0.351), box("卡厄思", 0.891, 0.438), box("主战员", 0.891, 0.616)]


class FakeTask:
    """每次 next_frame 取下一页 (texts, brightness)；最后一页一直重复。记录点击和按键。"""

    def __init__(self, pages):
        self.pages = list(pages)
        self.width, self.height = W, H
        self.frame = None
        self.all_texts = []
        self.actions = []
        self._texts = []

    def next_frame(self):
        texts, brightness = self.pages.pop(0) if len(self.pages) > 1 else self.pages[0]
        self._texts = list(texts)
        self.frame = np.full((H, W, 3), brightness, dtype=np.uint8)
        return self.frame

    def ocr(self):
        return [SimpleNamespace(**vars(b)) for b in self._texts]

    def move_relative(self, x, y):
        pass

    def click(self, x, y):
        self.actions.append(("click", round(x, 3), round(y, 3)))

    def send_key(self, key):
        self.actions.append(("key", key))

    def sleep(self, s):
        pass

    def log_info(self, msg, notify=False):
        pass


class TestGoHome(unittest.TestCase):
    def test_already_home(self):
        task = FakeTask([(HOME, 128)])
        self.assertTrue(utils_daily.go_home(task, timeout=5))
        self.assertEqual([], task.actions)

    def test_result_page_clicks_confirm_not_esc(self):
        # 出击结算页：ESC 无效，要点右下「确认」
        result = [box("奖励", 0.6, 0.62), box("出击记录", 0.71, 0.92), box("确认", 0.931, 0.917), box("战斗失败", 0.3, 0.71)]
        task = FakeTask([(result, 128), (HOME, 128)])
        self.assertTrue(utils_daily.go_home(task, timeout=5))
        self.assertEqual([("click", 0.931, 0.917)], task.actions)

    def test_black_loading_waits_without_input(self):
        # 结算后黑屏加载：只等，不点也不按 ESC
        task = FakeTask([([], 0), ([], 0), (HOME, 128)])
        self.assertTrue(utils_daily.go_home(task, timeout=5))
        self.assertEqual([], task.actions)

    def test_login_tap_prompts(self):
        pages = [([box("点击开始", 0.5, 0.802)], 128),
                 ([box("死灵之书每日礼物", 0.5, 0.11), box("点击以领取补给", 0.5, 0.934)], 128),
                 ([box("死灵之书每日礼物", 0.5, 0.11), box("点击画面后前往大厅", 0.5, 0.934)], 128),
                 (HOME, 128)]
        task = FakeTask(pages)
        self.assertTrue(utils_daily.go_home(task, timeout=5))
        self.assertEqual([("click", 0.5, 0.802), ("click", 0.5, 0.934), ("click", 0.5, 0.934)], task.actions)

    def test_pay_popup_closes_with_x_never_price(self):
        popup = [box("特殊资料", 0.137, 0.268), box("68元", 0.137, 0.752), box("128元", 0.865, 0.753), box("零之资料", 0.863, 0.267)]
        task = FakeTask([(popup, 128), (HOME, 128)])
        self.assertTrue(utils_daily.go_home(task, timeout=5))
        self.assertEqual([("click",) + utils_daily.PAY_POPUP_CLOSE], task.actions)

    def test_in_run_gives_up(self):
        task = FakeTask([([box("卡厄思信息", 0.1, 0.05), box("逃脱", 0.9, 0.93)], 128)])
        self.assertFalse(utils_daily.go_home(task, timeout=5))
        self.assertEqual([], task.actions)


class TestClaimAll(unittest.TestCase):
    def test_clicks_only_claim_all_in_region(self):
        mail = [box("邮箱", 0.107, 0.091), box("全部领取", 0.194, 0.902), box("删除已读邮件", 0.391, 0.904)]
        popup = [box("获得道具", 0.5, 0.375), box("点击屏幕可关闭", 0.5, 0.931)]
        task = FakeTask([(mail, 128), (popup, 128), (mail, 128)])
        self.assertTrue(utils_daily.claim_all(task, region=(0.05, 0.85, 0.25, 0.95)))
        self.assertEqual([("click", 0.194, 0.902), ("click", 0.5, 0.931)], task.actions)

    def test_supply_never_clicks_unlock(self):
        page = [box("全部领取", 0.646, 0.919), box("解锁额外数据", 0.868, 0.918)]
        task = FakeTask([(page, 128)])
        utils_daily.claim_all(task, region=(0.55, 0.86, 0.75, 0.97))
        self.assertEqual([("click", 0.646, 0.919)], task.actions)


class TestDialogueLine(unittest.TestCase):
    def test_dialogue(self):
        task = SimpleNamespace(width=W, height=H, all_texts=[box("趁着炮塔和异形分神之际，众人迅速离开了战斗区域。", 0.5, 0.85)])
        self.assertIsNotNone(_dialogue_line(task))

    def test_confirm_page_is_not_dialogue(self):
        task = SimpleNamespace(width=W, height=H, all_texts=[box("请确认是否可投入主战员。", 0.5, 0.82), box("确认", 0.6, 0.9)])
        self.assertIsNone(_dialogue_line(task))


if __name__ == "__main__":
    unittest.main()
