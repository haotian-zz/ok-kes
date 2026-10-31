# 刷存档-空存（刷空档）的单测：目标卡组里多出的闪光卡计数（三选一卡牌闪光不算）、删卡账和卡组读数、
# 删卡次数不够就逃脱重开、第一个航点逃脱、按顺序换目标、事件闪光选项一律不选、商店只删卡、装备优先给目标（用户 2026-10-28）。
# 跑法：python -m unittest tests.TestEmptySave
import os
import sys
import time
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
    logs, clicks, scrolls = [], [], []
    cfg = {"目标主战员": target, utils.EMPTY_TARGETS: list(ORDER),
           # 刷空档配置里打开的三个设置（用户 2026-10-28：要能通过设置切换，不跟玩法绑）
           utils.NEUTRAL_SKIP: True, utils.EQUIP_TARGET_FIRST: True, utils.FLASH_EQUIP_NOT_TARGET: True}
    cfg.update(config or {})
    t = types.SimpleNamespace(name="卡厄思模式", node_status=utils._initial_node_status(), config=cfg,
                              width=1920, height=1080, all_texts=list(texts), frame=None, chaos_mode=mode,
                              log_info=lambda *a, **k: logs.append(a[0]), log_error=lambda *a, **k: logs.append(a[0]),
                              log_debug=lambda *a, **k: None,
                              sleep=lambda s: None, move_relative=lambda x, y: None, is_adb=lambda: False,
                              scroll_relative=lambda x, y, n: scrolls.append(n),
                              click=lambda x, y, **k: clicks.append((round(x, 3), round(y, 3))),
                              click_box=lambda b, **k: clicks.append(b.name))
    t.setups = 0

    def setup_strategy():
        t.setups += 1
        t.chaos_overrides = dict(cs.config_overrides(t.chaos_mode, t.config["目标主战员"]), 刷存档主战员=t.config["目标主战员"])
    setup_strategy()
    t.setups = 0
    t.setup_strategy = setup_strategy
    t.logs, t.clicks, t.scrolls = logs, clicks, scrolls
    return t


class TestFlashCount(unittest.TestCase):
    def test_card_side(self):
        self.assertEqual("leader", utils.card_side("追踪箭", "希露德"))
        self.assertEqual("other", utils.card_side("水之源", "希露德"))

    def test_card_kind(self):
        # 卡库 id：srt1～3 基础卡、srt4 初始独特卡、uni1～4 闪光卡
        self.assertEqual(("basic", "多重箭"), utils.empty_card_kind("多重箭", "希露德"))
        self.assertEqual(("start", "装载箭筒"), utils.empty_card_kind("装载箭筒", "希露德"))
        self.assertEqual(("flash", "等离子之雨"), utils.empty_card_kind("等离子之雨", "希露德"))
        self.assertEqual(("other", "追踪箭"), utils.empty_card_kind("追踪箭", "希露德"))
        self.assertEqual(("start", "意志冲锋"), utils.empty_card_kind("意志冲锋", "玛丽贝尔"))
        self.assertEqual(("flash", "狼之穹铠"), utils.empty_card_kind("狼之穹铠", "玛丽贝儿"))
        self.assertEqual((None, None), utils.empty_card_kind("剑光", "玛丽贝儿"))
        self.assertEqual(4, utils._empty_start_total("希露德"))     # 多重箭×2 + 弓箭护卫 + 装载箭筒

    def test_card_flash_on_existing_card_not_counted(self):
        # 用户 2026-10-28：三选一卡牌闪光只是把已有的卡变强、不加新卡，不算
        t = empty_task()
        self.assertFalse(utils.record_empty_flash(t, [card("装载箭筒")] * 3))
        self.assertFalse(utils.record_empty_flash(t, [card("多重箭")] * 3))
        self.assertEqual(0, t.node_status.get("empty_flashes", 0))

    def test_flash_card_seen_counted_once(self):
        # 闪的是目标的闪光卡（10-28 玛丽贝儿的狼之穹铠）：说明它已经被塞进卡组，按闪光卡记一次
        t = empty_task("玛丽贝儿")
        cards = [card("狼之穹铠", 0.25), card("狼之穹铠", 0.5), card("狼之穹铠", 0.75)]
        self.assertTrue(utils.record_empty_flash(t, cards))
        self.assertFalse(utils.record_empty_flash(t, cards))
        t.node_status["node_count"] += 1
        self.assertFalse(utils.record_empty_flash(t, cards))        # 同一张卡下一个节点再闪也还是这一张
        self.assertEqual(["狼之穹铠"], t.node_status["empty_flash_cards"])
        self.assertEqual(1, t.node_status["empty_flashes"])

    def test_teammate_flash_not_counted(self):
        t = empty_task()
        self.assertFalse(utils.record_empty_flash(t, [card("水之源"), card("水之源"), card("水之源")]))
        self.assertEqual(0, t.node_status.get("empty_flashes", 0))

    def test_unknown_owner_not_counted(self):
        t = empty_task()
        self.assertFalse(utils.record_empty_flash(t, [card("嗷嗷嗷"), card("呜呜呜"), card("啦啦啦")]))
        self.assertEqual(0, t.node_status.get("empty_flashes", 0))

    def test_single_flash_popup_counted(self):
        # 10-28 02:27：装备「时间调节器」佩戴即闪光，弹单张「卡牌闪光」结果页，等离子之雨是新塞进卡组的闪光卡
        t = empty_task(texts=[box(0.500, 0.113, "卡牌闪光"), box(0.500, 0.258, "等离子之雨"), box(0.500, 0.937, "点击屏幕可关闭")])
        self.assertTrue(utils.handle_close_page(t))
        self.assertEqual(1, t.node_status["empty_flashes"])
        self.assertTrue(utils.handle_close_page(t))                  # 同一页下一帧不再记
        self.assertEqual(1, t.node_status["empty_flashes"])
        # 队友的卡、目标已有的初始卡都不算
        for name in ("水之源", "装载箭筒"):
            t2 = empty_task(texts=[box(0.500, 0.113, "卡牌闪光"), box(0.500, 0.258, name), box(0.500, 0.937, "点击屏幕可关闭")])
            utils.handle_close_page(t2)
            self.assertEqual(0, t2.node_status.get("empty_flashes", 0))
        # 三选一选完再弹结果页：同一张只记一次
        t3 = empty_task(texts=[box(0.500, 0.113, "卡牌闪光"), box(0.500, 0.258, "抽取&释放"), box(0.500, 0.937, "点击屏幕可关闭")])
        utils.record_empty_flash(t3, [card("抽取&释放")] * 3)
        utils.handle_close_page(t3)
        self.assertEqual(1, t3.node_status["empty_flashes"])
        # 别的「点击屏幕可关闭」页不算
        t4 = empty_task(texts=[box(0.500, 0.113, "获得装备"), box(0.500, 0.937, "点击屏幕可关闭")])
        utils.handle_close_page(t4)
        self.assertEqual(0, t4.node_status.get("empty_flashes", 0))

    def test_flash_equipment_not_for_target(self):
        eq = {"name": "时间调节器", "description": "佩戴的主战员触发闪光"}
        self.assertIn("闪光", utils.empty_flash_equipment(empty_task(), eq))
        self.assertIsNone(utils.empty_flash_equipment(empty_task(), {"name": "截骨机", "description": "攻击力增加"}))
        self.assertIsNone(utils.empty_flash_equipment(empty_task(config={utils.FLASH_EQUIP_NOT_TARGET: False}), eq))

    def test_other_modes_ignored(self):
        t = empty_task(mode=cs.MODE_TARGET)
        self.assertFalse(utils.record_empty_flash(t, [card("追踪箭")] * 3))


def removed(t, *names):
    for name in names:
        utils.empty_pick_removal(t, name)
    utils.empty_commit_removals(t)


class TestRemovalLedger(unittest.TestCase):
    def test_hilde_1028_cannot_be_emptied(self):
        # 10-28 希露德：删了多重箭×2、弓箭护卫、抽取&释放，还剩装载箭筒、等离子之雨 → 一共要删 6 次，做不成（用户确认）
        t = empty_task()
        utils.note_empty_cards(t, ["抽取&释放", "等离子之雨"], "测试")
        removed(t, "多重箭", "多重箭", "弓箭护卫", "抽取&释放")
        self.assertEqual((4, 2), utils.empty_removal_state(t))

    def test_maribel_1028_ok(self):
        # 10-28 玛丽贝儿：删了 3 张基础卡 + 意志冲锋，卡组里多了狼之穹铠 → 4 + 1 = 5，局外删掉狼之穹铠就是空档
        t = empty_task("玛丽贝儿")
        utils.note_empty_cards(t, ["狼之穹铠"], "测试")
        removed(t, "庇护飞踢", "庇护防御", "庇护坚守", "意志冲锋")
        self.assertEqual((4, 1), utils.empty_removal_state(t))

    def test_panel_count_wins(self):
        # 面板上的移除次数是游戏记的，比脚本账大就用面板的
        t = empty_task()
        removed(t, "多重箭")
        t.node_status["empty_panel_removed"] = 2
        self.assertEqual(2, utils.empty_removal_state(t)[0])

    def test_skip_drops_pending(self):
        t = empty_task()
        utils.empty_pick_removal(t, "多重箭")
        t.node_status.pop("empty_remove_pending")       # 点了跳过
        utils.empty_commit_removals(t)
        self.assertEqual([], t.node_status.get("empty_removed", []))

    def test_phantom_remove_click_not_counted(self):
        # 10-28 02:40：选卡页淡入时「移除」先亮，还没选卡就点了，记成多删一张
        t = empty_task(texts=[box(0.945, 0.918, "移除")])
        orig = utils.is_button_active
        utils.is_button_active = lambda task, b: True
        try:
            # 还没选卡：先不点，交给选卡处理（10-28 03:50：重启前选了一半，新进程直接点移除少删一张）
            self.assertFalse(utils.handle_remove(t))
            self.assertFalse(utils.handle_remove(t))
            self.assertEqual([], t.clicks)
            # 两次都没补选上（比如重启前已经选满）：照样点，不记账
            self.assertTrue(utils.handle_remove(t))
            self.assertEqual(["移除"], t.clicks)
            self.assertEqual(0, t.node_status.get("removed_card_count", 0))
            utils.empty_pick_removal(t, "多重箭")
            t.node_status["pending_removed_card_count"] = 1
            self.assertTrue(utils.handle_remove(t))
            self.assertEqual(["移除", "移除"], t.clicks)
        finally:
            utils.is_button_active = orig
        self.assertEqual(1, t.node_status["removed_card_count"])
        self.assertEqual([["多重箭", "basic"]], t.node_status["empty_removed"])

    def deck_task(self, target, names):
        t = empty_task(target)
        t.ocr = lambda *a, **k: [box(0.2 + 0.1 * i, 0.3, n) for i, n in enumerate(names)]
        t.next_frame = lambda: None
        return t

    def test_deck_read_counts_every_target_card(self):
        # 蒂菲拉点了天赋：开局卡组里就多一张闪光卡，4 张初始卡 + 1 = 5，局内再多一张就做不成（用户 2026-10-28）
        t = self.deck_task("蒂菲拉", ["物质分解", "展开屏障", "展开屏障", "量子晶种", "事件视界", "剑光",
                                     "在抽牌堆中生成1张事件视界并抽取1张卡牌"])
        self.assertEqual(5, utils._read_empty_deck(t, "蒂菲拉", 0))
        self.assertEqual(["事件视界"], t.node_status["empty_flash_cards"])
        self.assertEqual((0, 5), utils.empty_removal_state(t))
        # 删了两张基础卡之后总数不变
        removed(t, "物质分解", "展开屏障")
        self.assertEqual((2, 3), utils.empty_removal_state(t))
        # 战斗里又被塞了一张闪光卡：下个选路页读卡组，一共要删 6 次
        t.ocr = lambda *a, **k: [box(0.3, 0.3, "展开屏障"), box(0.4, 0.3, "量子晶种"), box(0.5, 0.3, "事件视界"),
                                 box(0.6, 0.3, "双重造物")]
        self.assertEqual(6, utils._read_empty_deck(t, "蒂菲拉", 2))
        self.assertEqual((2, 4), utils.empty_removal_state(t))

    def test_panel_remove_unreadable_uses_ledger(self):
        # 10-28 03:04 实录：面板上是「2/5」，希露德那列移除读成 None；用脚本删卡账照样读卡组
        t = empty_task()
        removed(t, "多重箭", "多重箭")
        panel = [box(0.27, 0.367, "希露德"), box(0.20, 0.58, "模糊的记忆"), box(0.36, 0.58, "60/140"),
                 box(0.18, 0.675, "移除"), box(0.37, 0.675, "2/")]
        deck = [box(0.3, 0.3, "弓箭护卫"), box(0.4, 0.3, "装载箭筒")]
        shots = [panel, deck, deck]
        t.ocr = lambda *a, **k: shots.pop(0) if shots else []
        t.next_frame = lambda: None
        utils.read_member_panel(t)
        self.assertEqual(4, t.node_status["empty_deck_need"])
        self.assertTrue(any("没读出来" in m and "2/" in m for m in t.logs))

    def test_deck_section_count_includes_neutral_cards(self):
        # 10-28 03:06「所有牌堆」：希露德那一栏左上角「03」＝弓箭护卫、装载箭筒、中立卡「觉悟」，中立卡也要删
        texts = [box(0.116, 0.182, "03"), box(0.247, 0.465, "希露德"), box(0.37, 0.14, "弓箭护卫"),
                 box(0.53, 0.14, "装载箭筒"), box(0.70, 0.14, "觉悟"),
                 box(0.116, 0.603, "06"), box(0.247, 0.886, "海德玛丽"), box(0.37, 0.56, "剑光")]
        t = self.deck_task("希露德", [])
        t.ocr = lambda *a, **k: texts
        t.node_status["empty_panel_removed"] = 2
        self.assertEqual(3, utils._empty_deck_count(t, texts, "希露德"))
        self.assertEqual(6, utils._empty_deck_count(t, texts, "海德玛丽"))
        self.assertEqual(5, utils._read_empty_deck(t, "希露德", 2))
        # 03:08 又被塞了闪光卡「抽取&释放」：栏上 04，删 2 次 + 4 张 = 6，做不成
        texts[0] = box(0.116, 0.182, "04")
        texts.append(box(0.86, 0.14, "抽取&释放"))
        self.assertEqual(6, utils._read_empty_deck(t, "希露德", 2))
        self.assertEqual(["抽取&释放"], t.node_status["empty_flash_cards"])
        self.assertEqual((2, 4), utils.empty_removal_state(t))

    def test_deck_target_section_below_scrolls(self):
        # 10-28 04:20：「所有牌堆」第一栏是海德玛丽（两行 5 张），蒂菲拉那栏只露出第一行卡名，张数和名字在画面外
        top = [box(0.116, 0.182, "05"), box(0.26, 0.465, "海德玛丽"), box(0.37, 0.14, "剑光"),
               box(0.37, 0.958, "展开屏障"), box(0.53, 0.958, "量子晶种"), box(0.70, 0.958, "形态凝聚")]
        # 往下滚：蒂菲拉那栏整栏露出来，第二行还有一张闪光卡
        lower = [box(0.116, 0.40, "05"), box(0.26, 0.683, "蒂菲拉"), box(0.37, 0.36, "展开屏障"),
                 box(0.53, 0.36, "量子晶种"), box(0.70, 0.36, "形态凝聚"), box(0.86, 0.36, "事件视界"),
                 box(0.37, 0.78, "展开屏障")]
        shots = [top, lower]
        t = self.deck_task("蒂菲拉", [])
        t.ocr = lambda *a, **k: shots.pop(0)
        self.assertEqual(7, utils._read_empty_deck(t, "蒂菲拉", 2))
        self.assertEqual([-5], t.scrolls)
        self.assertEqual(["形态凝聚", "事件视界"], t.node_status["empty_flash_cards"])
        # 目标那栏张数在第一屏就读到了：不滚
        t2 = self.deck_task("蒂菲拉", [])
        t2.ocr = lambda *a, **k: lower
        self.assertEqual(7, utils._read_empty_deck(t2, "蒂菲拉", 2))
        self.assertEqual([], t2.scrolls)

    def test_deck_count_scrolled_off_top_does_not_crash(self):
        # 10-30 18:14 实录：往下滚后艾米尔（编队第一栏）名字在 y≈0.228，张数那块在画面上方，
        # 单独 OCR 的框高 ≤0，ok 抛「width and height must be greater than zero」整个任务停了。读不到就返回 None
        texts = [box(0.26, 0.228, "艾米尔"), box(0.37, 0.50, "钢铁护盾")]
        t = self.deck_task("艾米尔", [])
        calls = []

        def ocr(*a, **k):
            calls.append(a)
            if a and a[3] - a[1] <= 0:
                raise ValueError("width and height must be greater than zero")
            return []
        t.ocr = ocr
        self.assertIsNone(utils._empty_deck_count(t, texts, "艾米尔"))
        self.assertEqual([], calls)

    def test_deck_count_name_one_char_off_and_small_digits(self):
        # 10-28 04:29 下滚后：名字读成「带菲拉」，整屏 OCR 漏了栏上「03」，单独认那一小块认得出
        full = [box(0.377, 0.637, "展开屏障"), box(0.545, 0.639, "量子晶种"), box(0.707, 0.638, "形态凝聚"),
                box(0.170, 0.806, "00"), box(0.170, 0.943, "50"), box(0.245, 0.955, "带菲拉")]
        regions = []
        t = self.deck_task("蒂菲拉", [])
        t.ocr = lambda *a, **k: (regions.append(a) or [box(0.116, 0.674, "03")]) if a else full
        self.assertEqual(3, utils._empty_deck_count(t, full, "蒂菲拉"))
        self.assertEqual(1, len(regions))
        x0, y0, x1, y1 = regions[0]
        self.assertTrue(x0 <= 0.116 <= x1 and y0 <= 0.674 <= y1, regions[0])
        # 两个字的名字不放宽；错两个字不算
        self.assertFalse(utils._member_name_like("米手", "米卡"))
        self.assertFalse(utils._member_name_like("带非拉", "蒂菲拉"))
        self.assertTrue(utils._member_name_like("蒂菲拉", "蒂菲拉"))

    def test_deck_not_open_not_recorded(self):
        t = self.deck_task("希露德", ["主战员", "攻击力", "模糊的记忆"])
        self.assertIsNone(utils._read_empty_deck(t, "希露德", 1))
        self.assertNotIn("empty_deck_need", t.node_status)

    def test_shop_spend_only_when_target_has_cards(self):
        t = empty_task()
        self.assertIsNone(utils.empty_should_remove(t))
        removed(t, "多重箭", "多重箭", "弓箭护卫", "装载箭筒")
        self.assertIn("删完", utils.empty_should_remove(t))
        utils.note_empty_cards(t, ["等离子之雨"], "测试")
        self.assertIsNone(utils.empty_should_remove(t))
        t.node_status["empty_panel_removed"] = 5
        self.assertIn("上限", utils.empty_should_remove(t))


class TestCardAssign(unittest.TestCase):
    def assign(self, target_index, texts=(), config=None):
        t = empty_task(texts=[box(0.863, 0.133, "请选择要接受卡牌的主战员"), *texts], config=config)
        lv = [box(0.45, 0.35, "Lv"), box(0.45, 0.55, "Lv"), box(0.45, 0.75, "Lv")]
        patches = {"recognize_cards": lambda task, region, page: [{"name": "觉悟", "description": "回合开始时"}],
                   "_find_member_level_tags": lambda task, region, page: lv,
                   "_find_target_member_index": lambda task, lvs, region: target_index}
        orig = {k: getattr(utils, k) for k in patches}
        for k, v in patches.items():
            setattr(utils, k, v)
        try:
            self.assertFalse(utils.handle_card_assign(t))           # 选好人，「确认」交给通用按钮
        finally:
            for k, v in orig.items():
                setattr(utils, k, v)
        return t

    def test_empty_mode_gives_card_to_teammate(self):
        # 10-28 03:04 实录：分配页不选人直接确认，游戏默认给了第一个（目标希露德），存档多一张中立卡
        t = self.assign(0)
        self.assertEqual((0.756, 0.75), t.clicks[-1])
        t = self.assign(2)
        self.assertEqual((0.756, 0.55), t.clicks[-1])
        t = self.assign(None)                                         # 认不出目标：按编队顺序排除第一个
        self.assertEqual((0.756, 0.75), t.clicks[-1])

    def test_neutral_skip_clicks_skip(self):
        t = empty_task(texts=[box(0.863, 0.133, "请选择要接受卡牌的主战员"), box(0.62, 0.94, "跳过")])
        orig = utils.recognize_cards
        utils.recognize_cards = lambda task, region, page: [{"name": "觉悟", "description": ""}]
        try:
            self.assertTrue(utils.handle_card_assign(t))
        finally:
            utils.recognize_cards = orig
        self.assertEqual(["跳过"], t.clicks)

    def test_setting_off_keeps_old_rule(self):
        # 设置关掉（要中立卡的玩法）：不跳过，按原来的规则走（存档模式交给卡牌奖励页）
        t = empty_task(texts=[box(0.863, 0.133, "请选择要接受卡牌的主战员"), box(0.62, 0.94, "跳过")],
                       config={utils.NEUTRAL_SKIP: False})
        orig = utils.recognize_cards
        utils.recognize_cards = lambda task, region, page: [{"name": "觉悟", "description": ""}]
        try:
            self.assertFalse(utils.handle_card_assign(t))
        finally:
            utils.recognize_cards = orig
        self.assertEqual([], t.clicks)


class TestEquipmentToTarget(unittest.TestCase):
    def decide(self, on, new_quality, cur_quality, live=(None, None, None)):
        t = empty_task(config={utils.EQUIP_TARGET_FIRST: on})
        eq = {"slot": 0, "quality": new_quality, "priority": [], "rank": None, "name": "新装备", "description": ""}
        view = types.SimpleNamespace(eq=eq, preferred=0, live=list(live))
        equipment = {"names": ["旧装备" if cur_quality else "", "", ""], "qualities": [cur_quality, "", ""],
                     "descriptions": ["", "", ""]}
        return utils._decide_install(t, view, equipment, False)[0]

    def test_empty_mode_gives_target_first(self):
        # 用户 2026-10-28：刷空档装备优先直接给目标，同品质也换；品质更低不换
        self.assertTrue(self.decide(True, "史诗", "史诗"))
        self.assertFalse(self.decide(False, "史诗", "史诗"))       # 设置关掉照原规则
        self.assertFalse(self.decide(True, "普通", "史诗"))
        # 不管「一人只装一件传说」
        self.assertTrue(self.decide(True, "传说", "", live=(None, "传说", None)))
        self.assertFalse(self.decide(False, "传说", "", live=(None, "传说", None)))


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
        self.assertIn("多了 2 张闪光卡", t.node_status["escape_reason"])
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

    def test_removal_math_escapes(self):
        # 卡组读出一共要删 6 次：没到航点就重开
        t = empty_task("蒂菲拉")
        t.node_status["empty_deck_need"] = 6
        self.assertTrue(utils.handle_empty_flash_escape(t))
        self.assertIn("超过 5 次", t.node_status["escape_reason"])
        t2 = empty_task("蒂菲拉")
        t2.node_status["empty_deck_need"] = 5
        self.assertFalse(utils.handle_empty_flash_escape(t2))

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

    def test_too_many_removals_not_counted_as_save(self):
        # 10-28 希露德：删了 4 次还剩 2 张，存档不算、不换目标
        t = empty_task()
        utils.note_empty_cards(t, ["抽取&释放", "等离子之雨"], "测试")
        removed(t, "多重箭", "多重箭", "弓箭护卫", "抽取&释放")
        self.assertTrue(self.settlement(t))
        self.assertFalse(t.node_status["empty_saved"])
        self.assertEqual(0, t.node_status["success_rounds"])
        self.assertFalse(utils.empty_rotate_target(t))

    def test_exactly_five_is_a_save(self):
        t = empty_task("玛丽贝儿")
        utils.note_empty_cards(t, ["狼之穹铠"], "测试")
        removed(t, "庇护飞踢", "庇护防御", "庇护坚守", "意志冲锋")
        self.assertTrue(self.settlement(t))
        self.assertTrue(t.node_status["empty_saved"])

    def test_out_of_run_limit(self):
        # 用户 2026-10-30：局外最多删 1 张。删了 2 次还剩 2 张（2+2≤5）也不算存好、不换目标
        t = empty_task("玛丽贝儿", config={utils.EMPTY_OUT_LEFT: 1})
        removed(t, "庇护飞踢", "庇护防御")
        self.assertTrue(self.settlement(t))
        self.assertFalse(t.node_status["empty_saved"])
        self.assertFalse(utils.empty_rotate_target(t))
        t = empty_task("玛丽贝儿", config={utils.EMPTY_OUT_LEFT: 1})
        removed(t, "庇护飞踢", "庇护防御", "庇护坚守")
        self.assertTrue(self.settlement(t))
        self.assertTrue(t.node_status["empty_saved"])

    def test_out_of_run_limit_clamped(self):
        for raw, want in ((9, 5), (-1, 0), ("x", 5), (1, 1)):
            self.assertEqual(want, utils._empty_out_left(empty_task(config={utils.EMPTY_OUT_LEFT: raw})))

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
        # 换到别的玩法也照样保留刷空档的几个目标（2026-10-28 12:14 章鱼哥速刷清理存储时差点分解早上的空档）
        self.assertEqual({"罗丝薇瑟", "希露德", "玛丽贝儿", "凛", "蒂菲拉"},
                         utils.empty_keep_members(empty_task("罗丝薇瑟", mode=cs.MODE_TARGET)))


class TestNoFlash(unittest.TestCase):
    def test_event_spark_vetoed(self):
        best, res = cs.pick_event_option(["赋予1张所选卡牌闪光", "进入战斗"], cs.MODE_EMPTY, {"removed": 0})
        self.assertEqual(1, best, res)
        s, _ = cs.score_effects({"spark": True, "credit": 200}, cs.MODE_EMPTY)
        self.assertLess(s, -400)

    def test_flashbang_equipment_not_spark(self):
        # 2026-10-28 03:43：「获得装备[闪光弹]」被当成闪光 -500；闪光弹是给敌人上弱化的装备
        e = cs.parse_effects("把伊欧娜拉下来获得装备[闪光弹]")
        self.assertNotIn("spark", e)
        self.assertEqual(["闪光弹"], e["equipment"])
        self.assertTrue(cs.parse_effects("听完布道随机主战员触发1次闪光").get("spark"))
        # OCR 漏了右括号，闪光还在括号外：照样算
        self.assertTrue(cs.parse_effects("甘受玷污强制获得咒术卡牌[赞美的试炼,选中主战员闪光1次").get("spark"))

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


class TestOpeningRerollMenu(unittest.TestCase):
    # 2026-10-28 03:17 实录：开局没刷到「移除2张」点菜单重开，菜单（卡厄思信息页）的战利品图标被认成事件选项
    # 「获得的战利品可以在返回时带回舰船。结束」，事件处理又点菜单把它关掉，回到同一个开局事件，原地打转 100 多次
    MENU = [box(0.179, 0.050, "卡厄思信息"), box(0.677, 0.164, "战利品"), box(0.810, 0.545, "未获得战利品。"),
            box(0.810, 0.816, "获得的战利品可以在返回时带回舰船。"), box(0.824, 0.890, "结束"), box(0.948, 0.926, "逃脱")]

    def test_menu_left_to_escape(self):
        t = empty_task(texts=self.MENU, config={"刷空档": True})
        t.find_feature = lambda **k: []
        old = utils.recognize_event_options
        utils.recognize_event_options = lambda task, page="": [
            {"description": "获得的战利品可以在返回时带回舰船。结束", "x": 0.82, "y": 0.95,
             "description_region": (0.7, 0.85, 0.95, 0.92)}]
        try:
            self.assertFalse(utils.handle_event_task(t))
        finally:
            utils.recognize_event_options = old
        self.assertEqual([], t.clicks)
        self.assertTrue(utils.handle_escape(t))
        self.assertEqual(["逃脱"], t.clicks)


class TestZeroCodexInEventChaos(unittest.TestCase):
    # 2026-10-28 03:12 实录：活动卡厄思刷空档误进零式系统，法典 → 合成 → 卡厄思合成花了 120 个材料、开了裁决之沼难度 10
    def craft_page(self, mode, config=None):
        t = empty_task(texts=[box(0.124, 0.045, "合成法典"), box(0.774, 0.925, "卡厄思合成"), box(0.935, 0.923, "120")],
                       mode=mode, config=config)
        t.start_window, t.entry_checked = False, True
        return t

    def test_event_chaos_goes_home_instead(self):
        homes = []
        old = utils_chaos.utils_daily.go_home
        utils_chaos.utils_daily.go_home = lambda task: homes.append(1) or True
        try:
            t = self.craft_page(cs.MODE_EMPTY, {"卡厄思地图": "活动卡厄思"})
            self.assertTrue(utils_chaos.handle_chaos_craft(t))
            self.assertEqual([], t.clicks)
            self.assertEqual([1], homes)
            self.assertTrue(t.start_window)
            self.assertFalse(t.entry_checked)
            # 原有逻辑、刷刻印、常驻刷存档照旧合成
            for mode, cfg in ((cs.MODE_LEGACY, {}), (cs.MODE_EMPTY, {"刷刻印": True}),
                              (cs.MODE_EMPTY, {"卡厄思地图": "常驻（探索度→卡厄思具象，刷存档→零式系统）"})):
                t = self.craft_page(mode, cfg)
                self.assertTrue(utils_chaos.handle_chaos_craft(t))
                self.assertEqual(["卡厄思合成"], t.clicks, (mode, cfg))
        finally:
            utils_chaos.utils_daily.go_home = old
        self.assertEqual([1], homes)


class TestHandCardsDuringBattle(unittest.TestCase):
    # 2026-10-28 13:22 实录：战斗中手牌「剑华：明-攻击」被 event9 误中当事件选项点了，文字规则挡不完，
    # 改成刚认出战斗页的几秒内不处理事件页
    def test_event_skipped_right_after_battle(self):
        t = empty_task(texts=[])
        t.find_feature = lambda **k: []
        t._battle_seen_at = time.time() - 1
        old = utils.recognize_event_options
        utils.recognize_event_options = lambda task, page="": self.fail("战斗中不该识别事件选项")
        try:
            self.assertFalse(utils.handle_event_task(t))
        finally:
            utils.recognize_event_options = old
        self.assertEqual([], t.clicks)

    def test_event_handled_after_guard(self):
        t = empty_task(texts=[])
        t.find_feature = lambda **k: []
        t._battle_seen_at = time.time() - utils.BATTLE_EVENT_GUARD_SECONDS - 1
        seen = []
        old = utils.recognize_event_options
        utils.recognize_event_options = lambda task, page="": seen.append(page) or []
        try:
            self.assertFalse(utils.handle_event_task(t))
        finally:
            utils.recognize_event_options = old
        self.assertEqual(["事件任务页面"], seen)


class TestStaminaRefillVsDialogue(unittest.TestCase):
    def test_dialogue_mentioning_stamina_is_not_popup(self):
        # 10-30 18:23 实录：剧情对白「众人吃着递来的东西补充体力。」被当成体力补充弹窗，按 ESC、找免费道具原地打转
        texts = [box(0.66, 0.05, "2113/2113"), box(0.70, 0.05, "6"), box(0.80, 0.05, "468"),
                 box(0.88, 0.08, "Ctrl"), box(0.96, 0.08, "Q"),
                 box(0.5, 0.837, "众人吃着递来的东西补充体力。", w=600),
                 box(0.5, 0.878, "稍作休息并交谈后，众人在使徒的送别下离开了那里。", w=800),
                 box(0.935, 0.91, "Space")]
        t = empty_task(texts=texts)
        keys = []
        t.send_key = lambda k, **kw: keys.append(k)
        self.assertFalse(utils_chaos.handle_stamina_refill(t))
        self.assertEqual(([], []), (t.clicks, keys))

    def test_real_popup_still_cancels(self):
        texts = [box(0.5, 0.40, "体力不足"), box(0.5, 0.48, "是否补充体力？"), box(0.35, 0.70, "取消"),
                 box(0.65, 0.70, "确认")]
        t = empty_task(texts=texts)
        t.send_key = lambda k, **kw: None
        self.assertTrue(utils_chaos.handle_stamina_refill(t))
        self.assertEqual(["取消"], t.clicks)
