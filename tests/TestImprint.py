# 刷刻印（utils_imprint）单测：法典面板/三选一卡片解析和合格判断（实机 2026-10-27 OCR）、装备刻印图标和装不装的判断
import os
import sys
import unittest
from types import SimpleNamespace

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ok_tasks"))

import utils_imprint as ui  # noqa: E402


def box(x, y, name):
    return SimpleNamespace(x=x * 1920, y=y * 1080, width=0, height=0, name=name)


def task_with(boxes, **config):
    return SimpleNamespace(width=1920, height=1080, all_texts=boxes, config=config)


# 选择法典页，1 号法典（用户生成好的目标法典）
SELECT_PAGE = [box(0.122, 0.046, "零式系统"), box(0.077, 0.242, "选择法典"), box(0.741, 0.221, "裁决之沼"),
               box(0.755, 0.283, "10|等级80"), box(0.825, 0.341, "卡厄思之珠获得量增加100%"),
               box(0.170, 0.409, "1·101J-J-155"), box(0.779, 0.408, "回荡在银河中的歌声"),
               box(0.845, 0.448, "将会出现面具卡牌和刻印装备，稀有种"), box(0.815, 0.478, "战区将转换为面具战斗区。"),
               box(0.786, 0.557, "存储数据保存上限150PT"), box(0.787, 0.597, "稀有命运触发率增加50%"),
               box(0.798, 0.669, "[疾病4]生命值上限减少50%"), box(0.779, 0.707, "[精英4]追加8个精英区"),
               box(0.836, 0.752, "[复仇2]异形死亡时，其他异形获得士2"), box(0.935, 0.899, "进入")]
# 3 号槽：没有赛季特性、有暴君3
SLOT3 = [box(0.741, 0.221, "裁决之沼"), box(0.755, 0.283, "10|等级106"), box(0.825, 0.341, "卡厄思之珠获得量增加120%"),
         box(0.786, 0.406, "存储数据保存上限150PT"), box(0.787, 0.448, "稀有命运触发率增加50%"),
         box(0.839, 0.517, "[暴君3]精英、首领区异形的攻击力与命"), box(0.747, 0.548, "值增加30%"),
         box(0.828, 0.590, "[疏忽1]回合开始时，随机丢掉1张卡牌"), box(0.805, 0.632, "[硬化2]异形每3回合获得不屈2")]
# 获得法典三选一
PICK_PAGE = [box(0.501, 0.101, "获得法典"), box(0.499, 0.152, "请选择1个"),
             box(0.106, 0.292, "裁决之沼"), box(0.419, 0.292, "裁决之沼"), box(0.731, 0.292, "裁决之沼"),
             box(0.117, 0.346, "10|等级80"), box(0.441, 0.346, "10|等级79|"), box(0.742, 0.346, "10|等级78"),
             box(0.139, 0.457, "回荡在银河中的歌声"), box(0.452, 0.457, "回荡在银河中的歌声"),
             box(0.764, 0.457, "回荡在银河中的歌声"),
             box(0.146, 0.585, "存储数据保存上限160PT"), box(0.458, 0.585, "存储数据保存上限160PT"),
             box(0.753, 0.579, "迪亚洛斯的荣光"), box(0.146, 0.624, "稀有命运触发率增加20%"),
             box(0.459, 0.622, "稀有命运触发率增加50%"), box(0.808, 0.611, "进入卡厄思时遇到[物主迪亚洛斯]"),
             box(0.161, 0.685, "[硬化2]异形每3回合获得不屈2"), box(0.504, 0.685, "[暴君3]精英、首领区异形的攻击力与生命"),
             box(0.155, 0.722, "[疾病3]生命值上限减少40%"), box(0.424, 0.713, "值增加30%"),
             box(0.192, 0.758, "[暴君4]精英、首领区异形的攻击力与生命"), box(0.504, 0.749, "[坏疽3]从第二回合起，回合开始时，生命"),
             box(0.767, 0.781, "无法获取存储数据"), box(0.578, 0.922, "120"), box(0.752, 0.049, "3,016"),
             box(0.881, 0.048, "18926K"), box(0.264, 0.922, "57600")]

# 通关后「搜索新坐标」免费给的三选一（实机 2026-10-27 02:49）：只有「确认」，没有珠/金币和再合成按钮；三个都不合格
FREE_PICK = [box(0.501, 0.101, "获得法典"), box(0.500, 0.150, "请选择1个"), box(0.106, 0.292, "裁决之沼"),
             box(0.418, 0.292, "裁决之沼"), box(0.731, 0.290, "裁决之沼"), box(0.119, 0.346, "10|等级90|"),
             box(0.431, 0.344, "10|等级90|"), box(0.744, 0.346, "10|等级90|"), box(0.176, 0.398, "卡厄思之珠获得量增加90%"),
             box(0.492, 0.397, "卡厄思之珠获得量增加140%"), box(0.801, 0.397, "卡厄思之珠获得量增加90%"), box(0.139, 0.457, "回荡在银河中的歌声"),
             box(0.451, 0.457, "回荡在银河中的歌声"), box(0.764, 0.457, "回荡在银河中的歌声"), box(0.197, 0.492, "将会出现面具卡牌和刻印装备，稀有种"),
             box(0.170, 0.519, "战斗区将转换为面具战斗区。"), box(0.510, 0.492, "将会出现面具卡牌和刻印装备，稀有种"),
             box(0.483, 0.519, "战斗区将转换为面具战斗区。"), box(0.823, 0.492, "将会出现面具卡牌和刻印装备，稀有种"),
             box(0.794, 0.517, "战斗区将转换为面具战斗区。"), box(0.146, 0.585, "存储数据保存上限150PT"),
             box(0.459, 0.585, "存储数据保存上限160PT"), box(0.771, 0.585, "存储数据保存上限150PT"),
             box(0.146, 0.624, "稀有命运触发率增加10%"), box(0.456, 0.624, "稀有命运触发率增加3%"), box(0.772, 0.624, "稀有命运触发率增加30%"),
             box(0.155, 0.685, "[疾病4]生命值上限减少50%"), box(0.491, 0.683, "[损失4]战中获得的信用点减少70%"),
             box(0.779, 0.683, "[疾病2]命值上限减少30%"), box(0.192, 0.722, "[暴君4]精英、领区异形的攻击与命"),
             box(0.111, 0.749, "值增加40%"), box(0.494, 0.722, "[疏忽1]回合开始时，随机丢掉1张卡牌"),
             box(0.817, 0.722, "[暴君4]精英、领区异形的攻击与命"), box(0.191, 0.784, "[坏病11从第回合起，回合开始时，命"),
             box(0.460, 0.759, "[不安1]无法在安全区休息"), box(0.736, 0.750, "值增加40%"), box(0.804, 0.783, "「损失31战中获得的信点减60%"),
             box(0.879, 0.924, "确认")]


class TestCodexParse(unittest.TestCase):
    def test_target_codex_ok(self):
        t = task_with(SELECT_PAGE)
        info = ui.parse_codex(ui._region_lines(t, ui.PANEL))
        self.assertEqual(("裁决之沼", 10, 150, 50), (info["map"], info["difficulty"], info["pt"], info["rare"]))
        self.assertEqual([("疾病", 4), ("精英", 4), ("复仇", 2)], info["mods"])
        self.assertEqual([], ui.codex_problems(info, t))

    def test_slot3_rejected(self):
        t = task_with(SLOT3)
        bad = ui.codex_problems(ui.parse_codex(ui._region_lines(t, ui.PANEL)), t)
        self.assertTrue(any("赛季特性" in b for b in bad))
        self.assertTrue(any("暴君3" in b for b in bad))

    def test_pick_cards(self):
        t = task_with(PICK_PAGE)
        infos = [ui.parse_codex(ui._region_lines(t, r)) for r in ui.PICK_CARDS]
        problems = [ui.codex_problems(i, t) for i in infos]
        self.assertTrue(any("稀有命运" in b for b in problems[0]))     # 20%
        self.assertTrue(any("暴君" in b for b in problems[1]))
        self.assertTrue(any("无法获取存储数据" in b for b in problems[2]))
        self.assertEqual(120, ui.parse_amount(ui._region_text(t, (0.54, 0.89, 0.62, 0.95))))

    def test_unrest_banned_here(self):
        info = ui.parse_codex(["裁决之沼", "10|等级80", "回荡在银河中的歌声", "稀有命运触发率增加60%", "[不安1]……"])
        self.assertTrue(any("不安1" in b for b in ui.codex_problems(info, task_with([]))))

    def test_amounts(self):
        self.assertEqual(3016, ui.parse_amount("3,016"))
        self.assertEqual(18926000, ui.parse_amount("18926K"))
        self.assertEqual(57600, ui.parse_amount("57600"))


def pick_task(boxes):
    clicks, logs = [], []
    t = SimpleNamespace(width=1920, height=1080, all_texts=boxes, config={"刷刻印": True},
                        log_info=logs.append, log_error=lambda *a, **k: logs.append(a[0]),
                        sleep=lambda *a: None, move_relative=lambda *a: None,
                        click=lambda x, y, **k: clicks.append((round(x, 3), round(y, 3))))
    t.disabled = False
    t.disable = lambda: setattr(t, "disabled", True)
    return t, clicks


class TestCodexPick(unittest.TestCase):
    def test_free_pick_takes_best_and_confirms(self):
        """实录 2026-10-27 02:42：通关后免费三选一都不合格，以前去读珠/金币读成 None 就停了任务。"""
        t, clicks = pick_task(FREE_PICK)
        self.assertTrue(ui._free_pick(t))
        self.assertTrue(ui.handle_codex_pick(t))
        self.assertFalse(t.disabled)
        x1, y1, x2, y2 = ui.PICK_CARDS[2]                     # 第三个稀有命运 30% 最高
        self.assertEqual([(round((x1 + x2) / 2, 3), round((y1 + y2) / 2, 3)), ui.PICK_CONFIRM], clicks)

    def test_paid_pick_is_not_free(self):
        self.assertFalse(ui._free_pick(task_with(PICK_PAGE)))

    def test_unread_amounts_wait_then_stop(self):
        t, clicks = pick_task([])
        args = (ui.ORBS_TEXT, ui.GOLD_TEXT, ui.SYNTH_CHAOS, ui.SYNTH_NORMAL, *ui.PICK_COSTS)
        for _ in range(ui.UNREAD_RETRY):
            self.assertTrue(ui._pay_and_synth(t, *args))
            self.assertFalse(t.disabled)
        self.assertTrue(ui._pay_and_synth(t, *args))
        self.assertTrue(t.disabled)
        self.assertEqual([], clicks)



# 实机 trace 截图（1280x720 放大到 1920x1080）裁出来的条带，贴回空白画面原位置：(文件, 左上角像素)
FIXTURES = os.path.join(ROOT, "tests", "fixtures")


def frame_with(name, left, top):
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    crop = cv2.imread(os.path.join(FIXTURES, f"imprint_{name}.jpg"))
    frame[top:top + crop.shape[0], left:left + crop.shape[1]] = crop
    return frame


# 商店五个商品的信用点图标中心（1920x1080，左右两头的卡片位置高一些、中间那张低一些）
SHOP_CREDIT = [(117, 868), (492, 898), (867, 916), (1242, 898), (1617, 868)]
TARGET_DESC = "友军使用能力生成5张以上卡牌时，自身额外攻击伤害量+30%（每回合1次）"


class TestImprintIcons(unittest.TestCase):
    def test_install_page_dark_imprint(self):
        t = task_with([])
        t.frame = frame_with("0043", 326, 518)
        desc = "攻击卡牌的伤害总量提升40% (每场战斗1次)回合开始时，若手牌中持有安息卡牌，则对随机敌人造成固定伤害60%"
        self.assertEqual((ui.OTHER, ui.DARK), ui.equipment_imprint(t, desc))
        self.assertEqual((ui.TARGET, ui.DARK), ui.equipment_imprint(t, "暴击伤害+12%" + TARGET_DESC))
        t.frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.assertEqual(("", None), ui.equipment_imprint(t, "战斗开始时，保存1"))

    def _shop_kinds(self, name):
        t = task_with([])
        t.frame = frame_with(name, 0, 756)
        dx, dy = ui.SHOP_ICON_OFFSET
        hx, hy = ui.SHOP_ICON_HALF
        kinds = []
        for x, y in SHOP_CREDIT:
            cx, cy = x / 1920 + dx, y / 1080 + dy
            kinds.append(ui.icon_kind(t, (cx - hx, cy - hy, cx + hx, cy + hy), win=2 * hy, min_frac=0.25))
        return kinds

    def test_shop_icons(self):
        # 0099：第2件「讥笑匕首」暗之刻印；第1件特价（橙色标签）、第3/4件传说（橙色底）都不能当成光之刻印
        self.assertEqual([None, ui.DARK, None, None, None], self._shop_kinds("0099"))
        # 0101：第2件光之刻印（黄色太阳）
        self.assertEqual([None, ui.LIGHT, None, None, None], self._shop_kinds("0101"))

    def test_target_is_light(self):
        self.assertEqual({ui.LIGHT}, ui.target_kinds(task_with([])))


def imprint_task(imprints=("", "", "")):
    t = task_with([])
    t.member_status = {"equipment": {"imprints": list(imprints)}}
    t.log_info = lambda *a, **k: None
    return t


class TestImprintDecision(unittest.TestCase):
    def test_target_imprint_first(self):
        t = imprint_task()
        ok, why = ui.install_decision(t, {"imprint": ui.TARGET, "rank": None}, 0, False, "品质普通不高于传说")
        self.assertTrue(ok, why)

    def test_keep_target_imprint(self):
        t = imprint_task((ui.TARGET, "", ""))
        # 目标装备但带别的刻印：不换，免得把目标刻印顶掉
        self.assertFalse(ui.install_decision(t, {"imprint": ui.OTHER, "rank": 0}, 0, True, "配置优先级更高")[0])
        # 目标装备没刻印：换上去继承目标刻印
        self.assertTrue(ui.install_decision(t, {"imprint": "", "rank": 0}, 0, True, "配置优先级更高")[0])
        # 不是目标装备但品质更高、没刻印：换上去继承目标刻印（用户 2026-10-27）
        self.assertTrue(ui.install_decision(t, {"imprint": "", "rank": None}, 0, True, "品质传说高于普通")[0])
        # 不比当前好：不换（提炼）
        self.assertFalse(ui.install_decision(t, {"imprint": "", "rank": None}, 0, False, "品质普通不高于传说")[0])

    def test_non_target_refined(self):
        t = imprint_task()
        self.assertFalse(ui.install_decision(t, {"imprint": ui.OTHER, "rank": None}, 1, True, "品质普通高于未安装")[0])
        # 槽位还没有目标刻印：目标装备买了会被之后的刻印装备顶掉，不买（实录 2026-10-27 03:37 商店白花 340 信用点）
        self.assertFalse(ui.install_decision(t, {"imprint": "", "rank": 0}, 1, True, "配置优先级更高", purchase=True)[0])
        self.assertFalse(ui.install_decision(t, {"imprint": ui.OTHER, "rank": 0}, 1, True, "配置优先级更高",
                                             purchase=True)[0])
        # 白拿的（掉落、事件奖励）照装（用户 2026-10-27）
        self.assertTrue(ui.install_decision(t, {"imprint": "", "rank": 0}, 1, True, "配置优先级更高")[0])
        self.assertTrue(ui.install_decision(t, {"imprint": ui.OTHER, "rank": 0}, 1, True, "配置优先级更高")[0])
        # 不比当前的目标装备好：不装
        self.assertFalse(ui.install_decision(t, {"imprint": "", "rank": 1}, 1, False, "配置优先级更低")[0])

    def test_event_target_equipment(self):
        names = [["欺骗暗影的匕首"], ["精灵王的金冠"], ["深绿桎梏", "深绿黑夜"]]
        # 槽位没有目标刻印：事件里的目标装备拿了也是提炼，只有混沌之识算
        self.assertEqual(["混沌之识"], ui.event_target_equipment(imprint_task(), names))
        t = imprint_task(("", ui.TARGET, ""))
        self.assertEqual(["混沌之识", "精灵王的金冠"], ui.event_target_equipment(t, names))

    def test_record_inherits(self):
        t = imprint_task((ui.TARGET, "", ""))
        ui.record_install(t, 0, {"imprint": ""})
        ui.record_install(t, 1, {"imprint": ui.TARGET})
        ui.record_install(t, 2, {"imprint": ui.OTHER})
        self.assertEqual([ui.TARGET, ui.TARGET, ui.OTHER], ui.slot_imprints(t))
        self.assertEqual(2, ui.target_imprint_count(t))

    def test_pick_candidate_prefers_imprint(self):
        t = imprint_task()
        cands = [{"ocr_name": "欺骗暗影的匕首", "slot": 0, "description": "暴击伤害+12%"},
                 {"ocr_name": "命令：108号", "slot": 0, "description": "攻击卡牌的伤害总量提升40%" + TARGET_DESC}]
        self.assertEqual(1, ui.pick_candidate(t, cands))
        t = imprint_task((ui.TARGET, "", ""))
        self.assertIsNone(ui.pick_candidate(t, cands))

    def test_chaos_core_outranks_imprint(self):
        t = imprint_task()
        t.member_status["equipment"]["names"] = ["混沌之识", "", ""]
        # 用户 2026-10-27：装着混沌之识，来了带目标刻印的武器也不换
        self.assertFalse(ui.install_decision(t, {"name": "绯刃", "imprint": ui.TARGET, "rank": None}, 0, False, "",
                                             "混沌之识")[0])
        # 混沌之识来了，就算当前武器带目标刻印也换（没刻印的混沌之识会继承）
        t = imprint_task((ui.TARGET, "", ""))
        self.assertTrue(ui.install_decision(t, {"name": "混沌之识", "imprint": "", "rank": 0}, 0, True, "",
                                            "命令：108号")[0])

    def test_required_with_chaos_core(self):
        t = imprint_task(("", "", ui.TARGET))
        t.member_status["equipment"]["names"] = ["混沌之识", "精灵王的金冠", "非典型立方体"]
        self.assertEqual(2, ui.required_imprints(t))
        t.member_status["equipment"]["imprints"] = [ui.TARGET, "", ui.TARGET]   # 混沌之识继承到了目标刻印
        self.assertEqual(3, ui.required_imprints(t))
        t.member_status["equipment"]["names"] = ["欺骗暗影的匕首", "", ""]
        self.assertEqual(3, ui.required_imprints(t))

    def test_escape_before_layer2_boss(self):
        """实录 2026-10-27 03:27：裁决之沼二层首领打完直接结算（离开），结算页来不及逃脱，法典用掉了。首领前就要逃。"""
        t = imprint_task((ui.TARGET, ui.TARGET, ""))
        t.config = {"刷刻印": True, "刷刻印速刷": True}
        t.member_status["equipment"]["names"] = ["欺骗暗影的匕首", "不朽鳞片", ""]
        t.node_status = {"pass_final_boss_count": 1,
                         "full_route": {"layer": 1, "done": 3, "steps": [{"type": "事件"}] * 3 + [{"type": "首领"}]}}
        self.assertIn("首领前", ui.rush_escape_reason(t))
        t.node_status["full_route"]["done"] = 2                     # 下一步还不是首领
        self.assertIsNone(ui.rush_escape_reason(t))
        self.assertIn("首领前", ui.rush_escape_reason(t, boss_next=True))   # 没有路线计划、路线页只剩首领
        t.member_status["equipment"]["imprints"] = [ui.TARGET] * 3
        self.assertIsNone(ui.rush_escape_reason(t, boss_next=True))
        t.member_status["equipment"]["imprints"] = [ui.TARGET, ui.TARGET, ""]
        t.node_status["pass_final_boss_count"] = 0                   # 第一层首领前不管（第一层打完再看）
        self.assertIsNone(ui.rush_escape_reason(t, boss_next=True))

    def test_deck_spend_waits_for_imprints(self):
        """实录 2026-10-27 04:29：第一层 0 个刻印还冥想 120+160、付费移除 120，第二个商店只剩 79 买不起刻印装备。"""
        t = imprint_task()
        t.config = {"刷刻印": True, "刷刻印速刷": True}
        t.member_status["equipment"]["names"] = ["", "", ""]
        t.node_status = {"pass_final_boss_count": 0}
        self.assertIn("0/2", ui.deck_spend_reason(t))
        t.member_status["equipment"]["imprints"] = [ui.TARGET, ui.TARGET, ""]
        self.assertIsNone(ui.deck_spend_reason(t))                  # 第一层够 2 个了，这局能继续
        t.node_status["pass_final_boss_count"] = 1
        self.assertIn("2/3", ui.deck_spend_reason(t))
        t.member_status["equipment"]["imprints"] = [ui.TARGET] * 3
        self.assertIsNone(ui.deck_spend_reason(t))
        t.config = {"刷刻印": True, "刷刻印速刷": False}               # 不速刷就不限制
        t.member_status["equipment"]["imprints"] = ["", "", ""]
        self.assertIsNone(ui.deck_spend_reason(t))

    def test_pick_candidate_chaos_core_first(self):
        t = imprint_task()
        t.member_status["equipment"]["names"] = ["", "", ""]
        cands = [{"ocr_name": "绯刃", "name": "绯刃", "slot": 0, "description": "暴击" + TARGET_DESC},
                 {"ocr_name": "混沌之识", "name": "混沌之识", "slot": 0, "description": "……"}]
        self.assertEqual(1, ui.pick_candidate(t, cands))
        t.member_status["equipment"]["names"] = ["混沌之识", "", ""]
        self.assertIsNone(ui.pick_candidate(t, cands[:1]))

    def test_special_price(self):
        import utils
        self.assertEqual(67, utils._parse_discounted_price("-96 67"))
        self.assertEqual(67, utils._parse_discounted_price("-9667"))
        self.assertEqual(140, utils._parse_discounted_price("200140"))
        self.assertEqual(96, utils._parse_discounted_price("96"))



class Box(SimpleNamespace):
    def area(self):
        return max(1, self.width * self.height)


def ocr_box(x, y, name, w=0.06, h=0.03):
    return Box(x=(x - w / 2) * 1920, y=(y - h / 2) * 1080, width=w * 1920, height=h * 1080, name=name)


class TestMaskSkip(unittest.TestCase):
    """国服「[面具]获得卡牌」页没有「跳过」字（只有 ▶| 图标），以前一直找字点不到，10 秒后画面卡住兜底点了卡（实录 2026-10-27）。"""

    def _task(self, texts):
        clicks = []
        t = SimpleNamespace(width=1920, height=1080, all_texts=texts, config={"指定面具卡牌": ""},
                            log_info=lambda *a, **k: None, sleep=lambda *a: None,
                            move_relative=lambda *a: None, click=lambda x, y, **k: clicks.append((x, y)),
                            click_box=lambda b, **k: clicks.append(b.name))
        return t, clicks

    def test_mask_card_page_clicks_skip_icon(self):
        import utils_chaos
        t, clicks = self._task([ocr_box(0.507, 0.090, "[面具]获得卡牌"), ocr_box(0.93, 0.93, "确认")])
        self.assertTrue(utils_chaos.handle_mask_card(t))
        self.assertEqual([utils_chaos.MASK_SKIP_POS], clicks)

    def test_engraving_page_skips(self):
        import utils_chaos
        t, clicks = self._task([ocr_box(0.499, 0.126, "面具卡牌刻印"), ocr_box(0.921, 0.931, "确认"),
                                ocr_box(0.747, 0.928, "跳过")])
        self.assertTrue(utils_chaos.handle_chaos_mask_engraving(t))
        self.assertEqual(["跳过"], clicks)


if __name__ == "__main__":
    unittest.main()
