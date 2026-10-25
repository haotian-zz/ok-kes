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


def paste_template(frame, name, cx, cy):
    """把 assets/daily 的模板按当前分辨率缩放后贴到相对中心 (cx, cy)。"""
    import cv2
    t = utils_daily._load_template(name)
    t = cv2.resize(t, None, fx=W / utils_daily.TEMPLATE_BASE_WIDTH, fy=W / utils_daily.TEMPLATE_BASE_WIDTH)
    th, tw = t.shape[:2]
    x, y = int(cx * W - tw / 2), int(cy * H - th / 2)
    frame[y:y + th, x:x + tw] = t


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
        page = self.pages.pop(0) if len(self.pages) > 1 else self.pages[0]
        texts, brightness = page[:2]
        self._texts = list(texts)
        self.frame = np.full((H, W, 3), brightness, dtype=np.uint8)
        for name, cx, cy in (page[2] if len(page) > 2 else []):
            paste_template(self.frame, name, cx, cy)
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

    def mouse_down(self, x, y, key="left"):
        self.actions.append(("hold", round(x / W, 3), round(y / H, 3)))

    def mouse_up(self, key="left"):
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


class TestDrinkCoffee(unittest.TestCase):
    HOME_CITY = HOME + [box("方舟城市", 0.883, 0.521)]
    CITY = [box("方舟城市", 0.122, 0.046), box("庭院咖啡店", 0.444, 0.921)]
    SHOP = [box("庭院咖啡店", 0.13, 0.044), box("点单", 0.776, 0.912)]
    POPUP = [box("获得道具", 0.5, 0.377), box("点击屏幕可关闭", 0.5, 0.934)]

    def board(self, ether):
        return [box("菜单板", 0.736, 0.167), box("堂食", 0.627, 0.267), box("外带", 0.845, 0.267),
                box(ether, 0.943, 0.048), box("0/4", 0.833, 0.049), box("点单", 0.737, 0.875)]

    def run_coffee(self, ether, choice="自动"):
        pages = [(self.HOME_CITY, 128), (self.HOME_CITY, 128), (self.CITY, 128), (self.SHOP, 128),
                 (self.board(ether), 128), ([box("跳过", 0.941, 0.05)], 128), (self.POPUP, 128), (self.SHOP, 128)]
        task = FakeTask(pages)
        self.assertTrue(utils_daily.drink_coffee(task, choice))
        return task.actions

    def test_full_ether_takes_out(self):
        actions = self.run_coffee("265/265+")
        self.assertIn(("click",) + utils_daily.COFFEE_TAKEOUT, actions)
        self.assertNotIn(("click",) + utils_daily.COFFEE_DINE_IN, actions)

    def test_low_ether_dines_in(self):
        actions = self.run_coffee("100/265")
        self.assertIn(("click",) + utils_daily.COFFEE_DINE_IN, actions)

    def test_already_ordered(self):
        pages = [(self.HOME_CITY, 128), (self.HOME_CITY, 128), (self.CITY, 128), (self.SHOP, 128),
                 (self.SHOP + [box("每天一杯的咖啡因就足够了！", 0.502, 0.269)], 128)]
        task = FakeTask(pages)
        self.assertTrue(utils_daily.drink_coffee(task))
        self.assertNotIn(("click",) + utils_daily.COFFEE_ORDER_BOARD, task.actions)


class TestTreatPatients(unittest.TestCase):
    HOME_CITY = HOME + [box("方舟城市", 0.883, 0.521)]
    CITY = ([box("方舟城市", 0.122, 0.046), box("庭院咖啡店", 0.444, 0.921)], 128, [("heal_city_enter", 0.555, 0.86)])
    TRAUMA = ([box("创伤中心", 0.122, 0.046)], 128, [("heal_trauma_center", 0.845, 0.685)])
    PATIENT = (0.30, 0.49)

    def ward(self, patient):
        marks = [("heal_center", 0.045, 0.92)]
        marks.append(("heal_has_patient",) + self.PATIENT if patient else ("heal_no_patient", 0.575, 0.515))
        return ([box("疗愈中心", 0.12, 0.046)], 128, marks)

    def test_report_only(self):
        task = FakeTask([(self.HOME_CITY, 128), (self.HOME_CITY, 128), self.CITY, self.TRAUMA, self.ward(True)])
        self.assertTrue(utils_daily.treat_patients(task, "不处理"))
        self.assertIn(("click", 0.791, 0.736), task.actions)
        self.assertFalse([a for a in task.actions if a[0] == "click" and a[2] < 0.4])

    def test_no_patient(self):
        task = FakeTask([(self.HOME_CITY, 128), (self.HOME_CITY, 128), self.CITY, self.TRAUMA, self.ward(False)])
        self.assertTrue(utils_daily.treat_patients(task, "记忆消除"))
        self.assertNotIn(("click",) + utils_daily.HEAL_PLAN_BUTTON["记忆消除"], task.actions)

    def test_memory_erase(self):
        selected = ([box("确认", 0.6625, 0.706)], 128, [("heal_selected", 0.535, 0.235)])
        pages = [(self.HOME_CITY, 128), (self.HOME_CITY, 128), self.CITY, self.TRAUMA,
                 self.ward(True), self.ward(True), self.ward(True), selected, selected, self.ward(False)]
        task = FakeTask(pages)
        self.assertTrue(utils_daily.treat_patients(task, "记忆消除"))
        x = round(self.PATIENT[0] + utils_daily.HEAL_PATIENT_OFFSET[0], 3)
        self.assertIn(x, [a[1] for a in task.actions if a[0] == "click"])
        self.assertIn(("click",) + utils_daily.HEAL_PLAN_BUTTON["记忆消除"], task.actions)


class TestDialogueLine(unittest.TestCase):
    def test_dialogue(self):
        task = SimpleNamespace(width=W, height=H, all_texts=[box("趁着炮塔和异形分神之际，众人迅速离开了战斗区域。", 0.5, 0.85)])
        self.assertIsNotNone(_dialogue_line(task))

    def test_confirm_page_is_not_dialogue(self):
        task = SimpleNamespace(width=W, height=H, all_texts=[box("请确认是否可投入主战员。", 0.5, 0.82), box("确认", 0.6, 0.9)])
        self.assertIsNone(_dialogue_line(task))


if __name__ == "__main__":
    unittest.main()
