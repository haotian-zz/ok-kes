# 卡厄思局外准备（utils_chaos_prep）单测：用国服实机截图的 OCR 结果（tests/fixtures/*.ocr.txt）做样例，不需要游戏
import os
import sys
import unittest
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ok_tasks"))

from utils_chaos_prep import parse_explore_regions, parse_preset_cards, parse_preset_counts  # noqa: E402

W, H = 1920, 1080


def load_ocr(name):
    """读 dev_probe 存的 OCR 文本（每行：cx,cy<TAB>置信度<TAB>文字），还原成以中心为准的框。"""
    boxes = []
    with open(os.path.join(ROOT, "tests", "fixtures", name), encoding="utf-8-sig") as f:
        for line in f:
            parts = line.rstrip("\r\n").split("\t")
            if len(parts) < 3 or "," not in parts[0]:
                continue
            cx, cy = (float(v) for v in parts[0].split(","))
            w, h = 0.05, 0.02
            boxes.append(SimpleNamespace(name=parts[2], x=(cx - w / 2) * W, y=(cy - h / 2) * H, width=w * W, height=h * H))
    return boxes


class TestPreset(unittest.TestCase):
    texts = load_ocr("preset_rosweisse_1.ocr.txt")

    def test_cards(self):
        cards = parse_preset_cards(self.texts, W, H)
        got = [(c["name"], c["n"], c["god_spark"]) for c in cards]
        self.assertEqual(8, len(cards))
        self.assertEqual(("明灭剑", 5, "add_r_spark_circen_06"), got[0])
        self.assertEqual([("剑鸣九霄", 2, "add_r_spark_circen_03")] * 3, got[1:4])
        self.assertEqual("剑鸣九霄", got[4][0])
        self.assertEqual(("剑刃破晓", 5, None), got[5])
        self.assertEqual(("循环之刃", 2, None), got[6])
        self.assertEqual(("基尔肯的神眷者", 0, None), got[7])

    def test_counts(self):
        self.assertEqual({"pt": (180, 180), "copy": (3, 3), "remove": (3, 5)}, parse_preset_counts(self.texts))


class TestChaosFigure(unittest.TestCase):
    def test_regions(self):
        regions = parse_explore_regions(load_ocr("chaos_figure_regions.ocr.txt"), W, H)
        self.assertEqual({"双星的暗影": 19, "裁决之沼": 30, "蓝罐": 30, "雾之都市": 24},
                         {r["name"]: r["explore"] for r in regions})


class TestZeroUpgrade(unittest.TestCase):
    def test_wants(self):
        import chaos_strategy as cs
        self.assertEqual((["高维启示", "认知闪光"], []), cs.zero_upgrade_wants(cs.MODE_EMPTY))
        self.assertEqual((["高维启示"], ["认知闪光"]), cs.zero_upgrade_wants(cs.MODE_TARGET))
        self.assertEqual(([], []), cs.zero_upgrade_wants(cs.MODE_EXPLORE))
        self.assertEqual((["高维启示"], ["认知闪光", "敌对信号检测", "消除威胁的奖励"]),
                         cs.zero_upgrade_wants(cs.MODE_TARGET, octopus=True))

    def test_levels_ok(self):
        from utils_chaos_prep import _levels_ok
        self.assertEqual([], _levels_ok({"高维启示": (0, 5), "认知闪光": (3, 3)}, ["高维启示"], ["认知闪光"]))
        self.assertEqual(["认知闪光"], _levels_ok({"高维启示": (0, 5), "认知闪光": (3, 3)}, ["高维启示", "认知闪光"], []))
        self.assertEqual(["认知闪光"], _levels_ok({"高维启示": (0, 5)}, ["高维启示"], ["认知闪光"]))

    def test_unmaxed_rows(self):
        # 2026-10-24 实机管理员模式页：只有高维启示没满级（行尾显示材料 100 而不是「已达等级上限」）
        from utils_chaos_prep import _visible_upgrade_rows, _UPGRADE_ROW_NAME
        task = SimpleNamespace(all_texts=load_ocr("chaos_zero_upgrade_admin.ocr.txt"), width=W, height=H)
        rows = _visible_upgrade_rows(task)
        unmaxed = [n for n, (_, maxed) in rows.items() if not maxed and _UPGRADE_ROW_NAME.fullmatch(n)]
        self.assertEqual(["高维启示"], unmaxed)
        self.assertTrue(rows["交涉权扩展"][1])

    def test_reset_dialog_not_paid(self):
        from utils_chaos_prep import _PAID_DIALOG
        texts = " ".join(b.name for b in load_ocr("chaos_zero_reset_dialog.ocr.txt"))
        self.assertIn("将重置全部技能", texts)
        self.assertIsNone(_PAID_DIALOG.search(texts))


class TestDreamMode(unittest.TestCase):
    def test_toggle_state(self):
        # 2026-10-24 实机配置队伍页，点开关前后（缩到 960×540）
        import cv2
        from utils_chaos_prep import dream_mode_on
        for name, want in (("team_dream_off", False), ("team_dream_on", True), ("team_event_dream_off", False)):
            frame = cv2.imread(os.path.join(ROOT, "tests", "fixtures", "chaos_map", name + ".png"))
            self.assertEqual(want, dream_mode_on(SimpleNamespace(frame=frame)), name)


class TestEventDifficulty(unittest.TestCase):
    # 2026-10-24 活动卡厄思「天幕」难度列：拖到底时 Ⅶ 选中、下面 4 个锁；拖到顶 Ⅰ～Ⅴ（+半个 Ⅵ），点了 Ⅴ 后 Ⅴ 选中
    def circles(self, name):
        import cv2
        from utils_chaos_prep import difficulty_circles
        return difficulty_circles(cv2.imread(os.path.join(ROOT, "tests", "fixtures", "chaos_map", name + ".jpg")))

    def test_bottom(self):
        c = [(round(y, 2), sel, lock) for y, sel, lock in self.circles("event_diff_bottom_vii") if 0.17 < y < 0.8]
        self.assertEqual([(0.27, True, False), (0.39, False, True), (0.51, False, True), (0.63, False, True), (0.75, False, True)], c)

    def test_top(self):
        c = self.circles("event_diff_top")
        self.assertEqual(6, len(c))
        self.assertAlmostEqual(0.233, c[0][0], places=2)
        self.assertFalse(any(sel or lock for _, sel, lock in c[:5]))
        c = self.circles("event_diff_top_v")
        self.assertEqual([False, False, False, False, True], [sel for _, sel, _ in c[:5]])

    def test_level_map(self):
        from utils_chaos_prep import _diff_of_level
        self.assertEqual(7, _diff_of_level(75))
        self.assertEqual(1, _diff_of_level(30))
        self.assertIsNone(_diff_of_level(99))


class TestDialogue(unittest.TestCase):
    def test_chaos_dialogue_with_hud(self):
        # 2026-10-24 实机：卡厄思局内事件对白，顶栏 HUD + Space 提示共 8 个框，以前因为 >6 认不出对白而卡住
        from utils import _dialogue_line
        task = SimpleNamespace(all_texts=load_ocr("chaos_dialogue_hud.ocr.txt"), width=W, height=H)
        self.assertEqual("幼虫专心地啃食着生肉，姿态十分诡异。", _dialogue_line(task).name)


if __name__ == "__main__":
    unittest.main()


class TestAtLobby(unittest.TestCase):
    def test_lobby_needs_enter_button(self):
        from types import SimpleNamespace
        from ChaosMode import ChaosMode
        page = lambda *names: SimpleNamespace(all_texts=[SimpleNamespace(name=n) for n in names])
        self.assertTrue(ChaosMode._at_lobby(page("探索度", "每周进展", "8000/ 8000", "进入")))
        # 结算奖励页确认按钮还没认出来时也有「每周进展」（2026-10-25 20:11）
        self.assertFalse(ChaosMode._at_lobby(page("每周进展", "8000/ 8000", "获得奖励")))
        self.assertFalse(ChaosMode._at_lobby(page("每周进展", "进入", "◎确认")))

    def test_out_of_run_pages(self):
        from types import SimpleNamespace
        from ChaosMode import ChaosMode
        page = lambda *names: SimpleNamespace(all_texts=[SimpleNamespace(name=n) for n in names])
        self.assertEqual("存储数据页", ChaosMode._out_of_run_page(page("存储数据", "编辑存储数据", "批量分解", "收藏自定义", "装备")))
        # 2026-10-28 12:21：存档清理中途重启，停在分解勾选页被当成局内
        self.assertEqual("存储数据页", ChaosMode._out_of_run_page(page(
            "√ 分解存储数据", "全部", "等级61", "6000 TB", "总数量 302/300", "选择数量1/100", "自动选择", "详细信息", "批量分解")))
        self.assertEqual("每日礼物弹窗", ChaosMode._out_of_run_page(page("死灵之书每日礼物", "剩余天数：25天", "点击以领取补给")))
        # 2026-10-28 02:12：赛季页的补给商店被当成事件连点
        self.assertEqual("卡厄思赛季页", ChaosMode._out_of_run_page(page(
            "银河系灾害", "银河徽章", "挑战任务", "卡厄思", "每周进展", "8000/8000", "补给商店", "环境变量", "赛季信息")))
        self.assertIsNone(ChaosMode._out_of_run_page(page("事件", "收起有用的东西", "点击屏幕可关闭")))
        # 2026-10-28 03:12：从主页进卡厄思走到一半被停，重启后大厅的「零式系统」被当成事件点了，走法典合成开错了图
        self.assertEqual("卡厄思大厅页", ChaosMode._out_of_run_page(page("卡厄思", "卡厄思具象", "零式系统")))
        self.assertEqual("零式系统首页", ChaosMode._out_of_run_page(page(
            "零式系统", "0/4", "已达成最高难度", "10", "玩法介绍", "法典", "环境变量", "备份协议", "升级", "图鉴", "法典记录",
            "卡厄思矩阵", "每周进展", "8000/8000")))
        # 法典合成好后的零式系统初始页（有「进入」）要交给页面流程，不算局外
        self.assertIsNone(ChaosMode._out_of_run_page(page("零式系统", "裁决之沼", "进入")))

    def test_same_team_tolerates_one_char(self):
        # 2026-10-28 12:06：「海德马丽」当成编队不一致，重开主战员列表时断网跑进了存储数据页
        from utils_chaos_prep import same_team
        want = ["罗丝薇瑟", "米卡", "海德玛丽"]
        self.assertTrue(same_team(["罗丝薇瑟", "米卡", "海德马丽"], want))
        self.assertFalse(same_team(["罗丝薇瑟", "米卡", "海德"], want))
        self.assertFalse(same_team(["罗丝薇瑟", "米米", "海德玛丽"], want))     # 两字名不放宽
        self.assertFalse(same_team(["罗丝薇瑟", None, "海德玛丽"], want))
        self.assertFalse(same_team(["蒂菲拉", "米卡", "海德玛丽"], want))

    def test_lobby_start_reads_preset_before_entering(self):
        # 2026-10-28 11:02：停在难度页启动，回主页后没读预设就进了卡厄思，删卡/闪光列表全空
        from unittest import mock
        from ChaosMode import ChaosMode
        import chaos_strategy
        import utils_daily
        calls = []
        task = SimpleNamespace(chaos_mode=chaos_strategy.MODE_TARGET, entry_checked=False, chaos_plan=None,
                               all_texts=[SimpleNamespace(name=n) for n in ("每周进展", "8000/8000", "进入")],
                               config={}, log_info=lambda *a: None, send_key=lambda *a: None, sleep=lambda *a: None)
        task._at_lobby = lambda: True
        task._out_of_run_page = ChaosMode._out_of_run_page
        task._prepare_target_deck = lambda: calls.append("preset") or True
        with mock.patch.object(utils_daily, "is_home", return_value=True), \
                mock.patch.object(utils_daily, "go_home", return_value=True), \
                mock.patch.object(utils_daily, "refresh", lambda t: None):
            self.assertTrue(ChaosMode._enter_chaos_from_home(task))
        self.assertEqual(["preset"], calls)
        self.assertFalse(task.entry_checked)     # 读完预设下一帧再按玩法进卡厄思


class TestCardNameOneCharOff(unittest.TestCase):
    def test_one_char_ocr_error(self):
        import game_db
        db = game_db.get_db()
        # 二元组系数只有 0.33，逐字兜底认出来（2026-10-25 预设里的剑刃破晓被读成剑刀破晓）
        self.assertEqual("剑刃破晓", db.find_card("剑刀破晓")["name"])
        self.assertEqual("明灭剑", db.find_card("明灰剑")["name"])

    def test_rematch_cached_deck(self):
        from ChaosMode import _rematch_unknown_cards
        deck = {"member": "罗丝薇瑟", "cards": [
            {"name": "剑刀破晓", "n": None, "god_spark": None,
             "desc": "伤害452%\n本回合凝聚卡牌叠加时，\n基础伤害量+50%（最\n大500%）\n此卡伤害总量提\n升30%"},
            {"name": "记忆：丧失4强化", "n": None, "god_spark": None, "desc": ""}]}
        _rematch_unknown_cards(deck)
        self.assertEqual(("剑刃破晓", 4), (deck["cards"][0]["name"], deck["cards"][0]["n"]))
        self.assertIsNone(deck["cards"][1]["n"])

    def test_flash_variant_with_ocr_name(self):
        import chaos_strategy as cs
        target = [{"name": "剑刃破晓", "n": 4, "god_spark": "add_r_spark_circen_01",
                   "desc": "伤害452%\n本回合凝聚卡牌叠加时，\n基础伤害量+50%（最\n大500%）\n此卡伤害总量提\n升30%"}]
        choices = [{"name": "剑刀破晓", "description": "丢弃最多1张手牌伤害348%费用减少2，下一次发动2张明、暗卡牌时恢复"},
                   {"name": "剑刀破晓", "description": "伤害300%本回合凝聚卡牌叠加时，基础伤害量+50%(最大500%)"},
                   {"name": "剑刀破晓", "description": "伤害232%丢弃最多1张手牌，丢弃后造成伤害174%1回合内坚定2"}]
        self.assertEqual(1, cs.pick_flash_variant("剑刀破晓", choices, target))
