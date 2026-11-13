# 日常工具（utils_daily）和剧情对白判定的单测：用脚本化的假页面驱动，不需要游戏
import os
import sys
import unittest
from unittest import mock
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

    def test_news_popup_closes_with_x(self):
        # 2026-11-04：登录后弹「资讯速递」公告，ESC 关不掉，日常每项都「连续按 ESC 仍未回到主页」
        popup = [box("资讯速递", 0.315, 0.1), box("网页活动|异常观测指南", 0.155, 0.38), box("常驻战员营救", 0.6, 0.55)]
        task = FakeTask([(popup, 128), (HOME, 128)])
        self.assertTrue(utils_daily.go_home(task, timeout=5))
        self.assertEqual([("click",) + utils_daily.NEWS_POPUP_CLOSE], task.actions)

    def test_in_run_gives_up(self):
        task = FakeTask([([box("卡厄思信息", 0.1, 0.05), box("逃脱", 0.9, 0.93)], 128)])
        self.assertFalse(utils_daily.go_home(task, timeout=5))
        self.assertEqual([], task.actions)

    def test_hidden_ui_wake_point_rotates(self):
        # 2026-10-27 22:27：立绘盖住默认唤醒点，同一个点点 30 次都没唤醒；点不出来要换位置
        task = FakeTask([([], 128), ([], 128), ([], 128), (HOME, 128)])
        self.assertTrue(utils_daily.go_home(task, timeout=5))
        self.assertEqual([("click",) + p for p in utils_daily.HOME_WAKE_POINTS], task.actions)


    def test_leftover_tower_run_escapes(self):
        # 2026-10-29：登录弹「此前进行的哀嚎螺旋塔相关信息仍然保留着。是否继续？」，ESC 关不掉，日常全部失败。
        # 用户定的点逃脱 → 战斗失败结算页点确认 → TIP 页点下一步 → 主页
        prompt = [box("此前进行的哀嚎螺旋塔相关信息仍然保留着。", 0.5, 0.43), box("是否继续？", 0.5, 0.47),
                  box("哀嚎螺旋塔", 0.37, 0.55), box("逃脱", 0.4, 0.767), box("继续", 0.65, 0.767)]
        result = [box("战斗失败", 0.3, 0.71), box("奖励", 0.6, 0.73), box("重来", 0.75, 0.917), box("确认", 0.9, 0.917)]
        tip = [box("TIP", 0.5, 0.29), box("可通过以下方式提升战员。", 0.5, 0.6), box("下一步", 0.9, 0.917)]
        task = FakeTask([(prompt, 128), (result, 128), (tip, 128), (HOME, 128)])
        self.assertTrue(utils_daily.go_home(task, timeout=5))
        self.assertEqual([("click", 0.4, 0.767), ("click", 0.9, 0.917), ("click", 0.9, 0.917)], task.actions)

    def test_leftover_other_run_never_escapes(self):
        # 别的玩法（比如卡厄思，局里可能有目标卡组）的保留弹窗：不点逃脱也不点继续，停下交给人
        prompt = [box("此前进行的卡厄思相关信息仍然保留着。", 0.5, 0.43), box("是否继续？", 0.5, 0.47),
                  box("逃脱", 0.4, 0.767), box("继续", 0.65, 0.767)]
        task = FakeTask([(prompt, 128)])
        self.assertFalse(utils_daily.go_home(task, timeout=5))
        self.assertEqual([], task.actions)

    def test_chaos_disconnect_prompt_never_escapes(self):
        # 2026-10-31：卡厄思局中途关了游戏，登录弹「卡厄思连接意外断开。是否继续？」，日常 7 项都按 ESC 失败
        prompt = [box("卡厄思连接意外断开。", 0.5, 0.444), box("是否继续？", 0.5, 0.475), box("卡厄思", 0.36, 0.553),
                  box("天幕", 0.646, 0.553), box("逃脱", 0.408, 0.69), box("继续", 0.606, 0.69)]
        task = FakeTask([(prompt, 128)])
        self.assertFalse(utils_daily.go_home(task, timeout=5))
        self.assertEqual([], task.actions)
        self.assertTrue(getattr(task, utils_daily.LEFTOVER_RUN_ATTR))


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
        utils_daily.claim_all(task, region=utils_daily.SUPPLY_CLAIM_REGION)
        self.assertEqual([("click", 0.646, 0.919)], task.actions)

    def test_supply_claim_button_on_right(self):
        # 2026-11-08 实录：没有解锁按钮时「全部领取」在右下 x≈0.88，旧区域 0.55～0.75 找不到，补给经验从 11-06 起一直 500/1000
        page = [box("每周任务经验值上限：0/10000", 0.728, 0.142), box("全部领取", 0.884, 0.918)]
        task = FakeTask([(page, 128)])
        utils_daily.claim_all(task, region=utils_daily.SUPPLY_CLAIM_REGION)
        self.assertEqual([("click", 0.884, 0.918)], task.actions)

    def test_claim_all_missing_button_is_none(self):
        task = FakeTask([([box("阿基亚农补给", 0.153, 0.042)], 128)])
        self.assertIsNone(utils_daily.claim_all(task, region=utils_daily.SUPPLY_CLAIM_REGION, timeout=1))


class TestWeekly(unittest.TestCase):
    # 2026-11-08 实录：F2 补给 → 任务 → 每周任务（OCR 原样）
    WEEK = [box("每日任务", 0.411, 0.305), box("在方舟城市[庭院咖啡店]中点3次咖啡", 0.620, 0.270), box("1/3", 0.495, 0.302),
            box("1500", 0.877, 0.319), box("0/3", 0.494, 0.427), box("在方舟城市[星光餐厅]点餐3次", 0.606, 0.396),
            box("500", 0.880, 0.446), box("每周任务", 0.410, 0.516), box("0/1", 0.494, 0.552),
            box("1通关1次模拟[挑战]", 0.567, 0.520), box("0/3", 0.494, 0.676), box("通关3次模拟[挑战]", 0.569, 0.645),
            box("在德朗的商店购买8件商品", 0.584, 0.769), box("0/8", 0.495, 0.802), box("全部领取", 0.884, 0.918)]
    CITY = [box("方舟城市", 0.122, 0.046), box("政策室", 0.219, 0.920), box("星光餐厅", 0.331, 0.919),
            box("庭院咖啡店", 0.444, 0.921)]
    MAIN = [box("星光餐厅", 0.122, 0.045), box("13047K", 0.956, 0.047), box("点单", 0.776, 0.912)]
    BOARD = [box("星光餐厅", 0.122, 0.046), box("菜单板", 0.778, 0.145), box("巧克力面包", 0.728, 0.221),
             box("10,000", 0.926, 0.219), box("微甜照烧串", 0.728, 0.581), box("10,000", 0.917, 0.581)]
    EAT = BOARD + [box("好！就吃这个吧！", 0.255, 0.721)]
    SKIP = [box("跳过！", 0.941, 0.051), box("点击即可食用。", 0.501, 0.950)]
    BUFF = [box("巧克力面包", 0.491, 0.412), box("进入卡厄思任务时使用：2次", 0.542, 0.645), box("点击屏幕可关闭", 0.5, 0.934)]

    def test_open_supply_retries_after_waking_home(self):
        # 2026-11-08 实录：主页 UI 隐藏时 F2 没反应，一键周常「没有打开阿基亚农补给」
        supply = [box("阿基亚农补给", 0.153, 0.042), box("全部领取", 0.884, 0.918)]
        task = FakeTask([(HOME, 128), (supply, 128)])
        with mock.patch.object(utils_daily, "go_home", return_value=True), \
                mock.patch.object(utils_daily.time, "time", side_effect=[0, 0, 100, 100, 100, 100, 100]):
            self.assertTrue(utils_daily.open_supply(task))
        self.assertEqual([("key", "f2"), ("click",) + utils_daily.HOME_WAKE_POINT, ("key", "f2")], task.actions)

    def test_mission_progress(self):
        task = FakeTask([(self.WEEK, 128)])
        task.next_frame()
        task.all_texts = task.ocr()
        self.assertEqual((0, 3), utils_daily._mission_progress(task, r"星光餐厅.*点餐"))
        self.assertEqual((0, 1), utils_daily._mission_progress(task, r"通关1次模拟"))
        self.assertEqual((0, 3), utils_daily._mission_progress(task, r"通关3次模拟"))
        self.assertEqual((0, 8), utils_daily._mission_progress(task, r"德朗的商店购买"))
        self.assertIsNone(utils_daily._mission_progress(task, r"通关2次卡厄思"))

    def test_weekly_progress_rereads_while_scrolling(self):
        # 2026-11-08 实录：列表还在滚时「通关2次卡厄思」读成 7/2；要两帧一致且不超过目标
        name = box("通关2次卡厄思", 0.545, 0.799)
        moving = [box("每周任务", 0.410, 0.516), name, box("7/2", 0.494, 0.829)]
        still = [box("每周任务", 0.410, 0.516), name, box("0/2", 0.494, 0.829)]
        task = FakeTask([(still, 128)])
        with mock.patch.object(utils_daily, "open_supply", return_value=True), \
                mock.patch.object(utils_daily, "click_text", return_value=True):
            task.pages = [(moving, 128), (still, 128), (still, 128)]
            self.assertEqual((0, 2), utils_daily.weekly_mission_progress(task, r"通关2次卡厄思", scrolls=0))

    def test_order_restaurant_once(self):
        home = HOME + [box("方舟城市", 0.883, 0.521)]
        task = FakeTask([(home, 128), (home, 128), (self.CITY, 128), (self.MAIN, 128), (self.BOARD, 128),
                         (self.BOARD, 128), (self.EAT, 128), (self.SKIP, 128), (self.BUFF, 128), (self.MAIN, 128)])
        self.assertTrue(utils_daily.order_restaurant(task, "巧克力面包", times=1))
        clicks = [a for a in task.actions if a[0] == "click"]
        for point in ((0.331, 0.919), (0.776, 0.912), (0.728, 0.221), (0.255, 0.721), (0.941, 0.051), (0.5, 0.934)):
            self.assertIn(("click",) + point, clicks)
        self.assertNotIn(("click", 0.926, 0.219), clicks)          # 价格不点

    def test_order_restaurant_replaces_active_buff(self):
        # 2026-11-08 实录：第二次点餐弹「之前的食物效果仍在生效…确定要点单新食物吗？」，没点确认就等不到跳过
        prompt = self.EAT + [box("之前的食物效果仍在生效。", 0.495, 0.422),
                             box("如果食用新的食物，之前的食物效果将会消失。确定要点单新食物吗？", 0.497, 0.462),
                             box("取消", 0.347, 0.631), box("确认", 0.666, 0.631)]
        home = HOME + [box("方舟城市", 0.883, 0.521)]
        task = FakeTask([(home, 128), (home, 128), (self.CITY, 128), (self.MAIN, 128), (self.BOARD, 128),
                         (self.BOARD, 128), (self.EAT, 128), (prompt, 128), (prompt, 128), (self.SKIP, 128),
                         (self.BUFF, 128), (self.MAIN, 128)])
        self.assertTrue(utils_daily.order_restaurant(task, "巧克力面包", times=1))
        self.assertIn(("click", 0.666, 0.631), task.actions)
        self.assertNotIn(("click", 0.347, 0.631), task.actions)

    def test_order_restaurant_zero_does_nothing(self):
        task = FakeTask([(HOME, 128)])
        self.assertTrue(utils_daily.order_restaurant(task, times=0))
        self.assertEqual([], task.actions)


class TestChallenge(unittest.TestCase):
    # 2026-11-08 实录：挑战「哀嚎的浪子」配置队伍页和结算页（OCR 原样）
    TEAM = [box("配置队伍", 0.121, 0.043), box("挑战", 0.697, 0.101), box("哀嚎的浪子", 0.734, 0.152),
            box("进入", 0.719, 0.911), box("免费进入3/3", 0.897, 0.914)]

    @staticmethod
    def result(left):
        return [box("挑战", 0.651, 0.237), box("剩余奖励次数", 0.631, 0.357), box(f"{left}/3", 0.931, 0.356),
                box("下个难度", 0.508, 0.918), box("重来", 0.723, 0.917), box("确认", 0.931, 0.916)]

    def test_replays_until_times(self):
        # click_text 也会取一帧：结算页各放两帧（循环读一次、点按钮时再读一次）
        task = FakeTask([(self.TEAM, 128), (self.result(2), 128), (self.result(2), 128),
                         (self.result(1), 128), (self.result(1), 128), (self.TEAM, 128)])
        self.assertTrue(utils_daily._challenge_from_team(task, "哀嚎的浪子", 2))
        clicks = [a for a in task.actions if a[0] == "click"]
        self.assertEqual([("click",) + utils_daily.TRAINING_ENTER, ("click", 0.723, 0.917), ("click", 0.931, 0.916)], clicks)

    def test_replays_with_renamed_button(self):
        # 2026-11-12 起结算页按钮叫「再来一次」（OCR「再来-」「一次」）
        def result(left):
            return [box("挑战", 0.651, 0.237), box("剩余奖励次数", 0.631, 0.357), box(f"{left}/3", 0.931, 0.356),
                    box("再来-", 0.664, 0.918), box("一次", 0.704, 0.918), box("确认", 0.931, 0.916)]
        task = FakeTask([(self.TEAM, 128), (result(2), 128), (result(2), 128),
                         (result(1), 128), (result(1), 128), (self.TEAM, 128)])
        self.assertTrue(utils_daily._challenge_from_team(task, "哀嚎的浪子", 2))
        clicks = [a for a in task.actions if a[0] == "click"]
        self.assertEqual([("click",) + utils_daily.TRAINING_ENTER, ("click", 0.664, 0.918), ("click", 0.931, 0.916)], clicks)

    def test_stops_when_rewards_used_up(self):
        task = FakeTask([(self.TEAM, 128), (self.result(0), 128), (self.result(0), 128), (self.TEAM, 128)])
        self.assertTrue(utils_daily._challenge_from_team(task, "哀嚎的浪子", 3))
        self.assertNotIn(("click", 0.723, 0.917), task.actions)       # 不再重来

    def test_used_up_on_training_page(self):
        # 2026-11-08 实录：免费次数用完后左边「挑战 0/3」，首领卡片上是以太价格 30，配置队伍页没有「免费进入」
        sim = [box("模拟", 0.103, 0.046), box("战斗训练", 0.144, 0.688), box("挑战", 0.144, 0.754), box("0/3", 0.145, 0.794)]
        train = [box("战斗训练", 0.122, 0.045), box("哀嚎的浪子", 0.706, 0.306), box("30", 0.954, 0.310),
                 box("挑战", 0.114, 0.721), box("0/3", 0.250, 0.720)]
        # 等「每周3次机会」说明弹窗只等一帧（真实是 3 秒），其余照常
        real_wait = utils_daily.wait_text

        def wait_text(t, pattern, region=None, timeout=10.0, interval=0.5):
            return real_wait(t, pattern, region, timeout=0 if "每周3次机会" in pattern else timeout, interval=interval)

        task = FakeTask([(sim, 128), (sim, 128), (train, 128)])
        with mock.patch.object(utils_daily, "open_home_entry", return_value=True), \
                mock.patch.object(utils_daily, "wait_text", wait_text):
            self.assertTrue(utils_daily.challenge_training(task, "哀嚎的浪子", 3))
        self.assertIn(("click", 0.144, 0.688), task.actions)          # 战斗训练
        self.assertNotIn(("click", 0.706, 0.306), task.actions)       # 不点首领

    def test_no_free_entries_never_enters(self):
        team = [b for b in self.TEAM if not b.name.startswith("免费")] + [box("免费进入0/3", 0.897, 0.914)]
        task = FakeTask([(team, 128)])
        self.assertTrue(utils_daily._challenge_from_team(task, "哀嚎的浪子", 3))
        self.assertEqual([], task.actions)
        task = FakeTask([([b for b in self.TEAM if not b.name.startswith("免费")], 128)])
        self.assertFalse(utils_daily._challenge_from_team(task, "哀嚎的浪子", 3))   # 看不到免费次数也不点
        self.assertEqual([], task.actions)


class TestDrinkCoffee(unittest.TestCase):
    HOME_CITY = HOME + [box("方舟城市", 0.883, 0.521)]
    CITY = [box("方舟城市", 0.122, 0.046), box("庭院咖啡店", 0.444, 0.921)]
    SHOP = [box("庭院咖啡店", 0.13, 0.044), box("点单", 0.776, 0.912)]
    POPUP = [box("获得道具", 0.5, 0.377), box("点击屏幕可关闭", 0.5, 0.934)]

    def board(self, ether, supply="0/4"):
        return [box("菜单板", 0.736, 0.167), box("堂食", 0.627, 0.267), box("外带", 0.845, 0.267),
                box(ether, 0.943, 0.048), box(supply, 0.833, 0.049), box("点单", 0.737, 0.875)]

    def run_coffee(self, ether, choice="自动", supply="0/4", can_wait=False, expect=True):
        pages = [(self.HOME_CITY, 128), (self.HOME_CITY, 128), (self.CITY, 128), (self.SHOP, 128),
                 (self.board(ether, supply), 128), ([box("跳过", 0.941, 0.05)], 128), (self.POPUP, 128), (self.SHOP, 128)]
        task = FakeTask(pages)
        self.assertEqual(expect, utils_daily.drink_coffee(task, choice, can_wait=can_wait))
        return task.actions

    def test_supply_full_and_ether_full_waits_for_stamina(self):
        # 2026-11-04/05：补充货币 4/4 时外带点了没反应，喝咖啡未完成；清体力还没跑就先等，不点单
        actions = self.run_coffee("265/265+", supply="4/4", can_wait=True, expect=utils_daily.COFFEE_LATER)
        self.assertNotIn(("click",) + utils_daily.COFFEE_ORDER_BOARD, actions)

    def test_supply_full_and_ether_full_no_wait_skips(self):
        actions = self.run_coffee("265/265+", supply="4/4", can_wait=False, expect=False)
        self.assertNotIn(("click",) + utils_daily.COFFEE_ORDER_BOARD, actions)

    def test_supply_full_low_ether_dines_in_even_if_takeout_chosen(self):
        actions = self.run_coffee("85/265", choice="外带", supply="4/4")
        self.assertIn(("click",) + utils_daily.COFFEE_DINE_IN, actions)
        self.assertNotIn(("click",) + utils_daily.COFFEE_TAKEOUT, actions)

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


class TestClaimDailyActivity(unittest.TestCase):
    def test_f3_retries_after_waking_home_ui(self):
        # 2026-11-06：主页 UI 自动隐藏时 F3 没反应；唤醒 UI 后再按
        window = [box("每日任务", 0.2, 0.1), box("60/100", 0.2, 0.62)]
        calls = []

        def fake_wait(task, pattern, region=None, timeout=10.0, interval=0.5):
            calls.append(pattern)
            if len(calls) == 1:
                return None
            utils_daily.refresh(task)
            return utils_daily.find_text(task, pattern, region) or box("每日任务", 0.2, 0.1)

        task = FakeTask([(HOME, 128), (HOME, 128), (window, 128)])
        with mock.patch.object(utils_daily, "wait_text", fake_wait), \
                mock.patch.object(utils_daily, "claim_all", lambda *a, **k: True):
            self.assertTrue(utils_daily.claim_daily_activity(task))
        self.assertEqual(2, task.actions.count(("key", "f3")))
        self.assertIn(("click",) + utils_daily.HOME_WAKE_POINT, task.actions)


class TestFarmStaminaHelpers(unittest.TestCase):
    def test_reads_fixed_cost_on_enter_button(self):
        # 2026-11-06：记忆碎片-光辉与雪花 Ⅹ 一次 60（不是 20×效率），按钮上红字 60
        task = FakeTask([([box("进入", 0.715, 0.915), box("60", 0.946, 0.916), box("30/265+", 0.943, 0.048)], 128)])
        utils_daily.refresh(task)
        self.assertEqual(60, utils_daily._training_cost(task))

    def test_ether_refill_popup_cancels_never_confirms(self):
        popup = [box("以太补充", 0.5, 0.21), box("请选择补充方法。", 0.5, 0.29), box("使用30个后，补充30以太。", 0.5, 0.62),
                 box("取消", 0.351, 0.805), box("确认", 0.65, 0.805)]
        task = FakeTask([(popup, 128)])
        utils_daily.refresh(task)
        self.assertTrue(utils_daily.close_ether_refill(task))
        self.assertEqual([("click", 0.351, 0.805)], task.actions)

    def test_retry_button_renamed(self):
        # 2026-11-12 实录：游戏更新后结算页「重来」变成「再来一次」，OCR 拆成「再来-」「一次」；旧脚本只认「重来」，在结算页干等
        page = [box("等级56", 0.618, 0.112), box("记忆碎片", 0.667, 0.238), box("奖励", 0.595, 0.625),
                box("F1", 0.593, 0.887), box("Enter", 0.807, 0.887), box("再来-", 0.614, 0.918),
                box("一次", 0.654, 0.918), box("60", 0.736, 0.918), box("确认", 0.931, 0.916)]
        task = FakeTask([(page, 128)])
        utils_daily.refresh(task)
        self.assertTrue(utils_daily.has_text(task, utils_daily.RETRY_RE, region=(0.55, 0.85, 0.7, 0.97)))
        self.assertTrue(utils_daily.click_text(task, utils_daily.RETRY_RE, region=(0.55, 0.85, 0.7, 0.97), timeout=1))
        self.assertEqual([("click", 0.614, 0.918)], task.actions)
        # 旧版「重来」照样认，别的字不认
        task = FakeTask([([box("重来", 0.62, 0.917), box("重来一下吗", 0.3, 0.5)], 128)])
        utils_daily.refresh(task)
        self.assertEqual(["重来"], [b.name for b in task.all_texts if __import__("re").search(utils_daily.RETRY_RE, b.name)])

    def test_no_refill_popup(self):
        task = FakeTask([([box("进入", 0.715, 0.915)], 128)])
        utils_daily.refresh(task)
        self.assertFalse(utils_daily.close_ether_refill(task))
        self.assertEqual([], task.actions)


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

    def test_city_click_swallowed_reenters(self):
        # 2026-11-06：点方舟城市被吞，一直停在主页；连续几帧还在主页就重新进
        stay = [(self.HOME_CITY, 128)] * 6
        task = FakeTask([(self.HOME_CITY, 128)] + stay + [self.CITY, self.TRAUMA, self.ward(False)])
        self.assertTrue(utils_daily.treat_patients(task, "不处理"))
        self.assertEqual(2, task.actions.count(("click", 0.883, 0.521)))

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

    def test_comic_bubble_dialogue(self):
        # 实录 2026-10-27 06:42 漫画格剧情，气泡在左边，Space 提示在气泡右下角
        texts = [box("2362 /2508", 0.211, 0.039), box("662", 0.732, 0.050), box("Ctrl", 0.879, 0.080),
                 box("Q", 0.959, 0.080), box("等", 0.098, 0.606), box("说说，", 0.110, 0.651),
                 box("等一", 0.143, 0.606), box("一下，", 0.173, 0.607), box("你想要什么！", 0.194, 0.654),
                 box("Space", 0.281, 0.686)]
        line = _dialogue_line(SimpleNamespace(width=W, height=H, all_texts=texts))
        self.assertEqual("你想要什么！", line.name)
        # 没有 Space 提示就不认
        self.assertIsNone(_dialogue_line(SimpleNamespace(width=W, height=H, all_texts=texts[:-1])))

    def test_mid_screen_bubble_without_space(self):
        # 实录 2026-10-28 01:18：画面中间气泡「除掉……不适格者……」，Space 提示太小没认出，卡了 2 分多钟
        top = [box("1081/1081", 0.211, 0.038), box("230", 0.734, 0.050), box("Ctrl", 0.879, 0.079),
               box("D", 0.878, 0.049), box("Q", 0.959, 0.079)]
        texts = top + [box("除掉…", 0.447, 0.545), box("·不适格者", 0.515, 0.546)]
        line = _dialogue_line(SimpleNamespace(width=W, height=H, all_texts=texts))
        self.assertEqual("·不适格者", line.name)
        # 只有一两个字、或者分散在不同高度的不算
        self.assertIsNone(_dialogue_line(SimpleNamespace(width=W, height=H, all_texts=top + [box("加载", 0.5, 0.5)])))
        # 01:29 两行气泡
        two = top + [box("骰子，", 0.374, 0.395), box("心理", 0.415, 0.394), box("研究。", 0.373, 0.434)]
        self.assertIsNotNone(_dialogue_line(SimpleNamespace(width=W, height=H, all_texts=two)))
        spread = top + [box("剩余回合", 0.3, 0.3), box("敌人行动中", 0.6, 0.6)]
        self.assertIsNone(_dialogue_line(SimpleNamespace(width=W, height=H, all_texts=spread)))

    def test_dialogue_with_ocr_noise(self):
        # 实录 2026-10-28 01:24：石碑花纹 OCR 成 8 段乱码字母，原来按文字太多不认对白，卡住
        noise = [box(n, x, y) for n, x, y in [("hUNY", 0.872, 0.431), ("↑SFYKI", 0.556, 0.480), ("TSRYYI", 0.871, 0.466),
                                              ("TSSYKI", 0.761, 0.493), ("Y12", 0.871, 0.519), ("NhUN", 0.761, 0.574),
                                              ("CSSYK", 0.872, 0.572), ("TSSYKI", 0.557, 0.599)]]
        texts = [box("1291/1291", 0.212, 0.038), box("Ctrl", 0.880, 0.079), box("Q", 0.959, 0.079)] + noise + [
            box("石碑中传来了使者的意志。", 0.489, 0.835), box("Space", 0.935, 0.913)]
        line = _dialogue_line(SimpleNamespace(width=W, height=H, all_texts=texts))
        self.assertEqual("石碑中传来了使者的意志。", line.name)

    def test_stuck_screen_presses_space_once(self):
        import time as _time
        import utils
        now = _time.time()
        logs = []
        task = SimpleNamespace(width=W, height=H, all_texts=[box("1291/1291", 0.212, 0.038), box("奇怪的文字", 0.2, 0.3)],
                               _last_change_time=now - 40, _last_stuck_check=now, log_info=lambda m, **k: logs.append(m))
        self.assertEqual("奇怪的文字", utils._stuck_dialogue_guess(task).name)
        self.assertIsNone(utils._stuck_dialogue_guess(task))          # 15 秒内不再按
        task._stuck_space_at = now - 20
        task.all_texts = task.all_texts + [box("确认", 0.6, 0.9)]
        self.assertIsNone(utils._stuck_dialogue_guess(task))          # 有按钮不按
        task.all_texts = task.all_texts[:2]
        task._last_change_time = now - 10
        self.assertIsNone(utils._stuck_dialogue_guess(task))          # 没卡够 30 秒

    def test_confirm_page_is_not_dialogue(self):
        task = SimpleNamespace(width=W, height=H, all_texts=[box("请确认是否可投入主战员。", 0.5, 0.82), box("确认", 0.6, 0.9)])
        self.assertIsNone(_dialogue_line(task))


if __name__ == "__main__":
    unittest.main()


class TestDailyFinalClaims(unittest.TestCase):
    def test_reclaim_after_point_steps(self):
        # 2026-11-09 实录：一键日常先领活跃和补给、后清体力喝咖啡，这些点数要到第二天才领到
        from DailyTask import final_claims
        steps = [("检查快捷键显示", "ensure_hotkey_display"), ("领取日常活跃奖励", "claim_daily_activity"),
                 ("领取阿基亚农补给", "claim_supply"), ("领取邮箱", "claim_mail"), ("清体力", "farm_stamina")]
        config = {"领取日常活跃奖励": True, "领取阿基亚农补给": True, "领取邮箱": True}
        self.assertEqual([("领取日常活跃奖励", "claim_daily_activity"), ("领取阿基亚农补给", "claim_supply")],
                         final_claims(steps, config, {"claim_supply", "farm_stamina"}))
        self.assertEqual([], final_claims(steps, config, {"claim_supply", "claim_mail"}))   # 没跑涨点数的项
        config["领取阿基亚农补给"] = False
        self.assertEqual([("领取日常活跃奖励", "claim_daily_activity")],
                         final_claims(steps, config, {"drink_coffee"}))
