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


class TestCodexTraitOcr(unittest.TestCase):
    """实录 2026-10-27 19:05：「暴君3」读成「君3」，禁止词条没认出来（那张碰巧稀有命运不够被拒）。"""

    def test_missing_char_maps_back(self):
        self.assertEqual("暴君", ui.canonical_trait("君"))
        self.assertEqual("损失", ui.canonical_trait("失"))
        self.assertIsNone(ui.canonical_trait("X"))
        self.assertEqual("坏疽", ui.canonical_trait("坏痛"))          # 19:07 实录错一个字
        self.assertIsNone(ui.canonical_trait("不忽"))                 # 对得上两个（不安/疎忽…）就不认
        info = ui.parse_codex(["裁决之沼", "10 | 等级", "稀有命运触发率增加 50%", "[坏疽3][硬化2][君3]"])
        self.assertEqual([("坏疽", 3), ("硬化", 2), ("暴君", 3)], info["mods"])
        want = {ui.MAP_KEY: "裁决之沼", ui.DIFF_KEY: 10, ui.TRAIT_KEY: "", ui.RARE_KEY: 50, ui.BAN_KEY: ["损失", "暴君", "不安"]}
        self.assertIn("有禁止词条 暴君3", ui.codex_problems(info, want=want))

    def test_unreadable_trait_rejected(self):
        info = ui.parse_codex(["裁决之沼", "10 | 等级", "稀有命运触发率增加 50%", "[坏疽3][X2]"])
        want = {ui.MAP_KEY: "裁决之沼", ui.DIFF_KEY: 10, ui.TRAIT_KEY: "", ui.RARE_KEY: 50, ui.BAN_KEY: ["暴君"]}
        self.assertIn("词条读不清 X2", ui.codex_problems(info, want=want))


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
        # 不是目标装备，品质再高也不装，提炼换信用点（用户 2026-10-27 11:5x）
        self.assertFalse(ui.install_decision(t, {"imprint": "", "rank": None}, 0, True, "品质传说高于普通")[0])
        self.assertFalse(ui.install_decision(t, {"imprint": ui.TARGET, "rank": None}, 0, True, "品质传说高于普通")[0])
        # 不比当前好：不换（提炼）
        self.assertFalse(ui.install_decision(t, {"imprint": "", "rank": None}, 0, False, "品质普通不高于传说")[0])

    def test_non_target_refined(self):
        t = imprint_task()
        self.assertFalse(ui.install_decision(t, {"imprint": ui.OTHER, "rank": None}, 1, True, "品质普通高于未安装")[0])
        # 槽位还没有目标刻印：目标装备装了会被之后的刻印装备顶掉，买的、白拿的都提炼（用户 2026-10-27 11:5x）
        self.assertFalse(ui.install_decision(t, {"imprint": "", "rank": 0}, 1, True, "配置优先级更高")[0])
        self.assertFalse(ui.install_decision(t, {"imprint": ui.OTHER, "rank": 0}, 1, True, "配置优先级更高")[0])
        # 带目标刻印的目标装备照装
        self.assertTrue(ui.install_decision(t, {"imprint": ui.TARGET, "rank": 0}, 1, False, "配置优先级更低")[0])

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

    def test_imprint_outranks_chaos_core(self):
        # 用户 2026-10-27 19:xx：目标刻印 > 混沌之识 > 目标装备（原来混沌之识最高，装着就不换）
        blade = {"name": "绯刃", "imprint": ui.TARGET, "rank": None}
        t = imprint_task()
        t.member_status["equipment"]["names"] = ["混沌之识", "", ""]
        self.assertTrue(ui.install_decision(t, blade, 0, False, "", "混沌之识")[0])      # 没刻印的混沌之识被换掉
        t = imprint_task((ui.TARGET, "", ""))
        t.member_status["equipment"]["names"] = ["混沌之识", "", ""]
        self.assertFalse(ui.install_decision(t, blade, 0, False, "", "混沌之识")[0])     # 混沌之识已继承目标刻印：不换
        self.assertFalse(ui.install_decision(t, {"name": "匕首", "imprint": "", "rank": 1}, 0, True, "", "混沌之识")[0])
        # 混沌之识来了，当前武器带目标刻印也换（没刻印的混沌之识会继承）；它自带别的刻印会顶掉目标刻印就不装
        t = imprint_task((ui.TARGET, "", ""))
        self.assertTrue(ui.install_decision(t, {"name": "混沌之识", "imprint": "", "rank": 0}, 0, True, "",
                                            "命令：108号")[0])
        self.assertFalse(ui.install_decision(t, {"name": "混沌之识", "imprint": ui.OTHER, "rank": 0}, 0, True, "",
                                             "命令：108号")[0])
        t = imprint_task()
        self.assertTrue(ui.install_decision(t, {"name": "混沌之识", "imprint": ui.OTHER, "rank": 0}, 0, True, "",
                                            "")[0])

    def test_required_with_chaos_core(self):
        t = imprint_task(("", "", ui.TARGET))
        t.member_status["equipment"]["names"] = ["混沌之识", "精灵王的金冠", "非典型立方体"]
        # 用户 2026-10-27 16:0x：拿到混沌之识不管几个目标刻印都打完存档；19:xx 目标刻印优先于混沌之识，
        # 混沌之识没刻印的槽位也能换成带刻印的，最终目标一直是 3 个
        self.assertEqual(0, ui.required_imprints(t))
        self.assertEqual(3, ui.goal_imprints(t))
        # 混沌之识继承到了目标刻印（2026-10-27 15:54 第 14 局按 3 个算，逃脱了）
        t.member_status["equipment"]["imprints"] = [ui.TARGET, ui.TARGET, ""]
        self.assertEqual(0, ui.required_imprints(t))
        self.assertEqual(3, ui.goal_imprints(t))
        # 没有混沌之识：两个就打首领（用户 16:1x 降低要求），最终目标还是三个
        t.member_status["equipment"]["names"] = ["欺骗暗影的匕首", "", ""]
        self.assertEqual(2, ui.required_imprints(t))
        self.assertEqual(3, ui.goal_imprints(t))
        # 装备记录被误清了，混沌之识掉落记录还在也认
        t.node_status = {"chaos_core_got": "混沌之识"}
        self.assertEqual(0, ui.required_imprints(t))

    def test_escape_before_layer2_boss(self):
        """实录 2026-10-27 03:27：裁决之沼二层首领打完直接结算（离开），结算页来不及逃脱，法典用掉了。首领前就要逃。"""
        t = imprint_task((ui.TARGET, "", ""))
        t.config = {"刷刻印": True, "刷刻印速刷": True}
        t.member_status["equipment"]["names"] = ["欺骗暗影的匕首", "不朽鳞片", ""]
        t.node_status = {"pass_final_boss_count": 1,
                         "full_route": {"layer": 1, "done": 3, "steps": [{"type": "事件"}] * 3 + [{"type": "首领"}]}}
        self.assertIn("首领前", ui.rush_escape_reason(t))
        t.node_status["full_route"]["done"] = 2                     # 下一步还不是首领：只剩第一层的 2 个门槛
        self.assertIn("第一层打完", ui.rush_escape_reason(t))
        self.assertIn("首领前", ui.rush_escape_reason(t, boss_next=True))   # 没有路线计划、路线页只剩首领
        t.member_status["equipment"]["imprints"] = [ui.TARGET, ui.TARGET, ""]   # 用户 2026-10-27 16:1x：两个就打完
        self.assertIsNone(ui.rush_escape_reason(t, boss_next=True))
        t.member_status["equipment"]["imprints"] = [ui.TARGET, "", ""]
        t.member_status["equipment"]["names"] = ["混沌之识", "不朽鳞片", ""]     # 拿到混沌之识不管几个都打完
        t.node_status["chaos_core_got"] = "混沌之识"
        self.assertIsNone(ui.rush_escape_reason(t, boss_next=True))
        del t.node_status["chaos_core_got"]
        t.member_status["equipment"]["names"] = ["欺骗暗影的匕首", "不朽鳞片", ""]
        t.node_status["pass_final_boss_count"] = 0                   # 第一层首领前不管（第一层打完再看）
        self.assertIsNone(ui.rush_escape_reason(t, boss_next=True))

    def test_last_shop_buys_target_equipment(self):
        """用户 2026-10-27 17:5x：最后一个商店了，只要不覆盖已有的目标刻印，目标装备也买。"""
        t = imprint_task(("", ui.TARGET, ui.TARGET))
        dagger = {"name": "欺骗暗影的匕首", "imprint": "", "rank": 1}
        steps = [{"type": "小怪"}, {"type": "休息[商店]"}, {"type": "精英"}, {"type": "首领"}]
        t.node_status = {"pass_final_boss_count": 1, "full_route": {"layer": 1, "done": 1, "steps": steps}}
        # 用户 2026-10-27 18:2x 新规则：第二层目标装备没刻印也先装，商店还在后面也装（原来这里是不装）
        self.assertTrue(ui.install_decision(t, dagger, 0, True, "")[0])
        t.node_status["full_route"]["done"] = 2                            # 刚进最后一个商店
        self.assertTrue(ui.install_decision(t, dagger, 0, True, "")[0])
        self.assertIn("后面没有商店", ui.install_decision(t, dagger, 0, False, "")[1])   # 最后商店规则不看 better，照旧
        # 槽位已有目标刻印：带别的刻印的目标装备会覆盖，仍不买
        self.assertFalse(ui.install_decision(t, {"name": "精灵王的金冠", "imprint": ui.OTHER, "rank": 0}, 1, True, "")[0])
        t.node_status["pass_final_boss_count"] = 0                          # 第一层不算
        t.node_status["full_route"]["layer"] = 0
        self.assertFalse(ui.install_decision(t, dagger, 0, True, "")[0])

    def test_imprint_count_never_drops(self):
        """2026-10-27 15:48：装备页淡入读成空槽，记录里 2 个目标刻印被清成 0 个，第二层首领前把混沌之识那局逃脱了。"""
        t = imprint_task((ui.TARGET, ui.TARGET, ""))
        t.node_status = {}
        self.assertEqual(2, ui.target_imprint_count(t))
        t.member_status["equipment"]["imprints"] = ["", "", ""]
        self.assertEqual(2, ui.target_imprint_count(t))
        self.assertEqual(2, t.node_status["imprint_peak"])

    def test_deck_spend_waits_for_imprints(self):
        """实录 2026-10-27 04:29：第一层 0 个刻印还冥想 120+160、付费移除 120，第二个商店只剩 79 买不起刻印装备。"""
        t = imprint_task()
        t.config = {"刷刻印": True, "刷刻印速刷": True}
        t.member_status["equipment"]["names"] = ["", "", ""]
        t.node_status = {"pass_final_boss_count": 0}
        self.assertIn("0/2", ui.deck_spend_reason(t))
        t.member_status["equipment"]["imprints"] = [ui.TARGET, ui.TARGET, ""]
        # 用户 2026-10-27 19:xx：第一层够 2 个了也继续留信用点，凑满目标（3 刻印 + 2 目标装备）前都不花
        self.assertIn("第一层目标刻印 2/3", ui.deck_spend_reason(t))
        t.config["装备3号位优先级"] = ["深绿桎梏", "深绿黑夜"]
        t.member_status["equipment"].update(names=["混沌之识", "", "深绿黑夜"], imprints=[ui.TARGET] * 3)
        self.assertIsNone(ui.deck_spend_reason(t))                  # 第一层就凑满了：可以花
        t.config = {"刷刻印": True, "刷刻印速刷": True}
        t.node_status = {"pass_final_boss_count": 0}                 # 刻印最高值只增不减，换一局重新算
        t.member_status["equipment"].update(names=["", "", ""], imprints=[ui.TARGET, ui.TARGET, ""])
        t.node_status["pass_final_boss_count"] = 1
        self.assertIn("2/3", ui.deck_spend_reason(t))
        t.member_status["equipment"]["imprints"] = [ui.TARGET] * 3
        # 用户 2026-10-27 18:2x：达成还要 2 个目标装备，凑满前信用点继续留着
        self.assertIn("目标装备 0/2", ui.deck_spend_reason(t))
        t.config["装备3号位优先级"] = ["深绿桎梏", "深绿黑夜"]
        t.member_status["equipment"]["names"] = ["混沌之识", "", "深绿黑夜"]
        self.assertIsNone(ui.deck_spend_reason(t))
        t.config = {"刷刻印": True, "刷刻印速刷": False}               # 不速刷就不限制
        t.member_status["equipment"]["imprints"] = ["", "", ""]
        self.assertIsNone(ui.deck_spend_reason(t))

    def test_pick_candidate_imprint_first(self):
        # 用户 2026-10-27 19:xx：目标刻印 > 混沌之识
        t = imprint_task()
        t.member_status["equipment"]["names"] = ["", "", ""]
        cands = [{"ocr_name": "绯刃", "name": "绯刃", "slot": 0, "description": "暴击" + TARGET_DESC},
                 {"ocr_name": "混沌之识", "name": "混沌之识", "slot": 0, "description": "……"}]
        self.assertEqual(0, ui.pick_candidate(t, cands))
        self.assertEqual(0, ui.pick_candidate(t, cands[1:]))               # 没有刻印候选时选混沌之识
        t.member_status["equipment"]["names"] = ["混沌之识", "", ""]
        self.assertEqual(0, ui.pick_candidate(t, cands[:1]))               # 装着没刻印的混沌之识，带刻印的照选
        t = imprint_task((ui.TARGET, "", ""))
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



# 用户 2026-10-27 18:2x 规则用的目标装备配置（1 号位混沌之识 / 匕首，2 号位金冠，3 号位深绿桎梏 / 深绿黑夜）
EQUIP_CONFIG = {"刷刻印": True, "刷刻印速刷": True, "记录流程追踪": False,
                "装备1号位优先级": ["混沌之识", "欺骗暗影的匕首"], "装备2号位优先级": ["精灵王的金冠"],
                "装备3号位优先级": ["深绿桎梏", "深绿黑夜"]}


class TestImprintRules1027(unittest.TestCase):
    """用户 2026-10-27 18:2x 新规则（第二层目标装备先装、达成条件）和不可逆守卫的纯函数部分。"""
    def test_guard_reasons(self):
        t = imprint_task()
        self.assertIn("目标刻印", ui.refine_block_reason(t, {"name": "绯刃", "imprint": ui.TARGET}, True))
        self.assertIn("混沌之识", ui.refine_block_reason(t, {"name": "混沌之识", "imprint": "", "rank": 0}, True))
        self.assertIsNotNone(ui.refine_block_reason(t, {"name": "深绿黑夜", "imprint": "", "rank": 1}, False))
        self.assertIsNone(ui.refine_block_reason(t, {"name": "深绿黑夜", "imprint": "", "rank": 1}, True))
        self.assertIsNone(ui.refine_block_reason(t, {"name": "绯刃", "imprint": ui.OTHER, "rank": None}, False))

    def test_layer2_rules(self):
        t = imprint_task()
        t.config = dict(EQUIP_CONFIG)
        t.node_status = {"pass_final_boss_count": 1}
        dagger = {"name": "欺骗暗影的匕首", "imprint": "", "rank": 1}
        self.assertTrue(ui.install_decision(t, dagger, 0, True, "配置优先级更高")[0])
        self.assertFalse(ui.install_decision(t, dagger, 0, False, "当前装备配置优先级更高")[0])
        # 别的刻印也照装（槽位没有目标刻印可顶掉）
        self.assertTrue(ui.install_decision(t, dict(dagger, imprint=ui.OTHER), 0, True, "")[0])
        # 槽位已有目标刻印：仍按旧规则，自带别的刻印会顶掉目标刻印就不装；没刻印的换上继承
        t.member_status["equipment"]["imprints"] = [ui.TARGET, "", ""]
        self.assertFalse(ui.install_decision(t, dict(dagger, imprint=ui.OTHER), 0, True, "")[0])
        self.assertTrue(ui.install_decision(t, dagger, 0, True, "")[0])
        # 混沌之识不换
        t.member_status["equipment"]["names"] = ["混沌之识", "", ""]
        self.assertFalse(ui.install_decision(t, dagger, 0, True, "", "混沌之识")[0])
        # 第一层维持原规则
        t.node_status["pass_final_boss_count"] = 0
        t.member_status["equipment"].update(names=["", "", ""], imprints=["", "", ""])
        self.assertFalse(ui.install_decision(t, dagger, 0, True, "")[0])

    def test_event_target_equipment_layer2(self):
        names = [["欺骗暗影的匕首"], ["精灵王的金冠"], ["深绿桎梏", "深绿黑夜"]]
        t = imprint_task()
        t.member_status["equipment"]["names"] = ["混沌之识", "", ""]
        t.node_status = {"pass_final_boss_count": 1}
        self.assertEqual(["混沌之识", "精灵王的金冠", "深绿桎梏", "深绿黑夜"], ui.event_target_equipment(t, names))


class TestGoalReached(unittest.TestCase):
    def _task(self, names, imprints):
        t = imprint_task(imprints)
        t.config = dict(EQUIP_CONFIG)
        t.member_status["equipment"]["names"] = list(names)
        t.node_status = {}
        return t

    def test_goal(self):
        """用户 2026-10-27 18:2x：达成＝至少 2 个目标装备（1 号位混沌之识算）+ 3 个目标刻印。"""
        T = ui.TARGET
        self.assertTrue(ui.goal_reached(self._task(["混沌之识", "怪异之壳", "深绿黑夜"], (T, T, T))))
        self.assertTrue(ui.goal_reached(self._task(["欺骗暗影的匕首", "精灵王的金冠", "不朽鳞片"], (T, T, T))))
        self.assertFalse(ui.goal_reached(self._task(["混沌之识", "怪异之壳", "不朽鳞片"], (T, T, T))))     # 1 个目标装备
        self.assertFalse(ui.goal_reached(self._task(["混沌之识", "精灵王的金冠", "深绿黑夜"], (T, T, ""))))  # 2 个刻印
        self.assertFalse(ui.goal_reached(self._task(["", "", ""], ("", "", ""))))
        self.assertEqual(2, ui.target_equipment_count(self._task(["混沌之识", "", "深绿桎梏"], ("", "", ""))))


# ------------------------- 装备页回归（handle_equipment 整页驱动） -------------------------
# 假 task：OCR 框 all_texts + 假画面（只画用得到的像素：待装备品质点、刻印图标、目标主战员三个装备位颜色）+ 假特征（三个 leveltag、
# 刷存档主战员头像在第 1 个）。断言真实动作（点了哪里）和装备账。2026-10-27 装备页每个 bug 一个用例。
LV_X, LV_Y = 0.63, (0.35, 0.55, 0.75)              # 三个主战员 leveltag 中心
SLOT_OFFSETS = ((0.130, -0.044), (0.201, -0.044), (0.270, -0.044))
LEGEND, NORMAL, EPIC = (135, 82, 164), (61, 76, 138), (160, 88, 69)
MEMBER = [("member", 0.756, y) for y in LV_Y]     # 点第 i 个主战员


def equip_frame(quality=None, slots=(None, None, None), icon=False):
    """quality：待装备品质色（None＝淡入时的黑）；slots：目标主战员三个装备位颜色（None＝黑，读成空槽）；icon：光之刻印图标。"""
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

    def px(x, y, rgb):
        frame[round(y * 1080), round(x * 1920)] = rgb[::-1]
    if quality:
        px(0.117, 0.409, quality)
    for (dx, dy), rgb in zip(SLOT_OFFSETS, slots):
        if rgb:
            px(LV_X + dx, LV_Y[0] + dy, rgb)
    if icon:                                        # 黄色太阳：铺满描述区左边一条的上半段
        x1, y1, x2, _ = ui.DESC_ICON_STRIP
        frame[round(y1 * 1080):round(y1 * 1080) + 40, round(x1 * 1920):round(x2 * 1920)] = (0, 200, 255)
    return frame


def equip_texts(name, type_text, desc, refine=True, confirm=True, purchase=False, price="96", credit="300"):
    boxes = [ocr_box(0.499, 0.126, "装备"), ocr_box(0.921, 0.135, "请选择主战员", w=0.12)]
    if name:
        boxes.append(ocr_box(0.30, 0.41, name, w=0.15))
    if type_text:
        boxes.append(ocr_box(0.25, 0.466, type_text, w=0.08))
    if desc:
        boxes.append(ocr_box(0.35, 0.55, desc, w=0.30))
    if purchase:
        boxes += [ocr_box(0.60, 0.93, "取消"), ocr_box(0.80, 0.93, price, w=0.03), ocr_box(0.92, 0.93, "购买"),
                  ocr_box(0.794, 0.054, credit, w=0.04)]
    else:
        if refine:
            boxes.append(ocr_box(0.75, 0.93, "提炼"))
        if confirm:
            boxes.append(ocr_box(0.92, 0.93, "确认"))
    return boxes


class EquipPageCase(unittest.TestCase):
    def setUp(self):
        import tempfile
        from unittest import mock
        import chaos_trace
        import utils
        self.utils = utils
        tmp = tempfile.mkdtemp()
        # 测试不写真实 dev_out：流程追踪、局内状态落盘都指到临时目录
        for target, attr, value in ((chaos_trace, "TRACE_ROOT", os.path.join(tmp, "trace")),
                                    (utils, "RUN_STATE_FILE", os.path.join(tmp, "run_state.json")),
                                    (utils, "is_button_active", lambda task, b: getattr(task, "confirm_active", False))):
            p = mock.patch.object(target, attr, value)
            p.start()
            self.addCleanup(p.stop)
        self.tmp = tmp

    def make_task(self, names=("", "", ""), imprints=("", "", ""), qualities=("", "", ""), layer=0, **config):
        acts, logs = [], []
        cfg = dict(EQUIP_CONFIG)
        cfg.update(config)
        lv = [Box(x=LV_X * 1920 - 10, y=y * 1080 - 10, width=20, height=20, confidence=0.9, name="") for y in LV_Y]
        avatar = Box(x=lv[0].x + 40, y=lv[0].y - 20, width=40, height=40, confidence=0.8, name="")
        t = SimpleNamespace(
            width=1920, height=1080, all_texts=[], frame=None, config=cfg, default_config={"刷存档主战员": "海德玛丽"},
            member_status={"equipment": {"names": list(names), "descriptions": ["", "", ""], "qualities": list(qualities),
                                         "imprints": list(imprints)}},
            node_status={"pass_final_boss_count": layer}, chaos_seen=None, confirm_active=False, disabled=False,
            log_info=lambda m, *a, **k: logs.append(m), log_error=lambda m, *a, **k: logs.append(m),
            sleep=lambda *a: None, move_relative=lambda *a: None,
            click=lambda x, y, **k: acts.append(("member", round(x, 3), round(y, 3))),
            click_box=lambda b, **k: acts.append(b.name),
            find_feature=lambda feature_name=None, box=None, threshold=0: list(lv) if feature_name == "leveltag" else [],
            find_one=lambda feature_name=None, box=None, threshold=0: avatar,
            feature_exists=lambda name: True, box_of_screen=lambda *a, **k: None)
        t.disable = lambda: setattr(t, "disabled", True)
        t.acts, t.logs = acts, logs
        return t

    def frame(self, t, texts, frame, confirm_active=False):
        """跑一帧：页面处理表里装备相关的两个（settle 在最前面，不拦截）。"""
        t.all_texts, t.frame, t.confirm_active = texts, frame, confirm_active
        settle = getattr(self.utils, "settle_equipment_pending", None)
        if settle:
            settle(t)
        return self.utils.handle_equipment(t)

    def eq(self, t):
        return t.member_status["equipment"]


class TestEquipPageRegression(EquipPageCase):
    def test_fade_in_empty_slots_keep_ledger(self):
        """703c6c7 实录 2026-10-27 15:48：装备页淡入时装备位读成空，清掉了账里的混沌之识/目标刻印，后面被逃脱。"""
        names = ["混沌之识", "怪异之壳", "深绿桎梏"]
        t = self.make_task(names, (ui.TARGET, ui.TARGET, ""), ("传说", "传说", "传说"), layer=1)
        item = ("不朽鳞片", "防御力+80", "受到伤害时获得护盾")
        fade = (equip_texts(*item, refine=False, confirm=False), equip_frame(LEGEND))     # 底部按钮没出来、装备位全黑
        for _ in range(2):
            self.frame(t, *fade)
        self.assertEqual(names, self.eq(t)["names"])
        self.assertEqual([ui.TARGET, ui.TARGET, ""], self.eq(t)["imprints"])
        self.assertEqual([], t.acts)
        ready = (equip_texts(*item), equip_frame(LEGEND, (LEGEND, LEGEND, LEGEND)))
        for _ in range(2):
            self.frame(t, *ready)
        self.assertEqual(["提炼"], t.acts)        # 槽位已有目标刻印、不是目标装备：提炼
        self.assertEqual(names, self.eq(t)["names"])
        self.assertEqual(2, ui.target_imprint_count(t))

    def test_fade_in_unknown_quality_not_refined(self):
        """35670f4 实录 2026-10-27 17:03：淡入时品质「未知」、刻印「无」连读 3 帧，带目标刻印的怪异之壳差点被提炼。"""
        t = self.make_task()
        for _ in range(3):
            self.frame(t, equip_texts("怪异之壳", "防御力+80", "受到伤害时获得护盾"), equip_frame(None))
        self.assertEqual([], t.acts)
        good = (equip_texts("怪异之壳", "防御力+80", "受到伤害时获得护盾" + TARGET_DESC), equip_frame(LEGEND, icon=True))
        for _ in range(2):
            self.frame(t, *good)
        self.assertEqual([MEMBER[0]], t.acts)
        self.frame(t, *good, confirm_active=True)
        self.assertEqual([MEMBER[0], "确认"], t.acts)
        self.assertEqual("怪异之壳", self.eq(t)["names"][1])
        self.assertEqual(ui.TARGET, self.eq(t)["imprints"][1])

    def test_no_redecide_after_member_click(self):
        """fee1447 实录 2026-10-27 18:02：点了主战员安装后，下一帧同一页又被当新页面判断；账已提前写成深绿黑夜 →
        「不比当前好」→ 目标装备深绿黑夜被提炼。现在：点完锁住、确认后才写账。"""
        t = self.make_task(("", "", "怪异之壳"), ("", "", ui.TARGET), ("", "", "传说"), layer=1)
        page = (equip_texts("深绿黑夜", "生命值+300", "回合开始时恢复生命"), equip_frame(LEGEND, (None, None, LEGEND)))
        for _ in range(2):
            self.frame(t, *page)
        self.assertEqual([MEMBER[0]], t.acts)
        for _ in range(3):                           # 确认按钮还没亮：等，不重新判断
            self.frame(t, *page)
        self.assertEqual([MEMBER[0]], t.acts)
        self.assertEqual("怪异之壳", self.eq(t)["names"][2])        # 还没确认，不写账
        self.frame(t, *page, confirm_active=True)
        self.assertEqual([MEMBER[0], "确认"], t.acts)
        self.assertEqual("深绿黑夜", self.eq(t)["names"][2])
        self.assertEqual(ui.TARGET, self.eq(t)["imprints"][2])     # 没刻印的目标装备继承槽位的目标刻印
        for _ in range(3):                           # 确认后页面淡出还露几帧：同一件不再判断
            self.frame(t, *page)
        self.assertEqual([MEMBER[0], "确认"], t.acts)

    def test_refine_with_trace_does_not_crash(self):
        """f76f1f5 实录 2026-10-27 17:22：提炼留底 chaos_trace.step(..., kind=...) 撞参数名，任务崩溃（提炼路径没测过）。"""
        import json
        import chaos_trace
        t = self.make_task(**{"记录流程追踪": True})
        page = (equip_texts("命令：108号", "攻击力+120", "攻击卡牌的伤害总量提升40%"), equip_frame(LEGEND, icon=True))
        for _ in range(2):
            self.frame(t, *page)
        self.assertEqual(["提炼"], t.acts)
        with open(os.path.join(t._chaos_trace["dir"], "trace.jsonl"), encoding="utf-8") as f:
            recs = [json.loads(line) for line in f]
        self.assertTrue(chaos_trace.TRACE_ROOT.startswith(self.tmp))
        self.assertEqual("refine", recs[-1]["kind"])
        self.assertEqual((ui.OTHER, ui.LIGHT), (recs[-1]["data"]["imprint"], recs[-1]["data"]["icon"]))

    def test_wait_for_refine_button_before_teammate(self):
        """291f68e 实录 2026-10-27 07:11：装备页淡入时还没认出提炼按钮，就按老规则分给了队友。"""
        t = self.make_task()
        item = ("命令：108号", "攻击力+120", "攻击卡牌的伤害总量提升40%")
        for _ in range(3):
            self.frame(t, equip_texts(*item, refine=False), equip_frame(LEGEND))
        self.assertEqual([], t.acts)
        for _ in range(2):
            self.frame(t, equip_texts(*item), equip_frame(LEGEND))
        self.assertEqual(["提炼"], t.acts)
        # 提炼按钮一直不出来：等够了再按老规则分给队友（不会卡死）
        t = self.make_task()
        for _ in range(self.utils.EQUIP_STABLE_MAX_WAIT + 1):
            self.frame(t, equip_texts(*item, refine=False), equip_frame(LEGEND))
        self.assertEqual(1, len(t.acts))
        self.assertIn(t.acts[0], MEMBER[1:])

    def test_install_saved_to_run_state(self):
        """2d5ed0f：装备和装备位刻印随局内状态落盘（中途重启后目标刻印还在）。确认安装后就落盘。"""
        import json
        t = self.make_task()
        t.chaos_pt_cap = 150
        page = (equip_texts("怪异之壳", "防御力+80", "受到伤害时获得护盾" + TARGET_DESC), equip_frame(LEGEND, icon=True))
        for _ in range(2):
            self.frame(t, *page)
        self.assertFalse(os.path.exists(self.utils.RUN_STATE_FILE))    # 只点了主战员，还没确认
        self.frame(t, *page, confirm_active=True)
        with open(self.utils.RUN_STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(["", "怪异之壳", ""], data["equipment"]["names"])
        self.assertEqual(["", ui.TARGET, ""], data["equipment"]["imprints"])
        fresh = SimpleNamespace(node_status={}, member_status={}, config={}, log_info=lambda *a, **k: None)
        self.assertTrue(self.utils.restore_run_state(fresh))
        self.assertEqual(1, ui.target_imprint_count(fresh))

    def test_dark_grey_empty_slot_not_legendary(self):
        """2ff63c9 实录 2026-10-27 03:04：暗灰色空槽 (24,42,46)、转场 (57,61,70) 被当成传说，新传说装备就不装给目标主战员。"""
        t = self.make_task(**{"刷刻印": False})
        page = (equip_texts("绯刃", "攻击力+120", "暴击伤害+12%"), equip_frame(LEGEND, (None, (24, 42, 46), (57, 61, 70))))
        for _ in range(2):
            self.frame(t, *page)
        self.assertEqual([MEMBER[0]], t.acts)
        self.frame(t, *page, confirm_active=True)
        self.assertEqual(["绯刃", "", ""], self.eq(t)["names"])
        self.assertEqual(["传说", "", ""], self.eq(t)["qualities"])


class TestEquipPageGuard(EquipPageCase):
    def test_never_refine_target_imprint(self):
        """不可逆守卫：1 号位混沌之识已继承目标刻印，又来带目标刻印的武器，规则说不换，但带目标刻印的永远不提炼（分给队友，留底）。"""
        t = self.make_task(("混沌之识", "", ""), ("目标", "", ""), ("传说", "", ""), **{"记录流程追踪": True})
        page = (equip_texts("绯刃", "攻击力+120", "暴击" + TARGET_DESC), equip_frame(LEGEND, (LEGEND, None, None), icon=True))
        for _ in range(2):
            self.frame(t, *page)
        self.assertNotIn("提炼", t.acts)
        self.assertEqual(1, len(t.acts))
        self.assertIn(t.acts[0], MEMBER[1:])
        self.assertEqual("混沌之识", self.eq(t)["names"][0])
        import json
        with open(os.path.join(t._chaos_trace["dir"], "trace.jsonl"), encoding="utf-8") as f:
            self.assertIn("refine_blocked", [json.loads(line)["kind"] for line in f])

    def test_only_refine_button_refuses_target_imprint(self):
        """只有提炼按钮可点时，带目标刻印的装备也不提炼：停下通知。"""
        t = self.make_task()
        page = (equip_texts("怪异之壳", "防御力+80", "护盾" + TARGET_DESC, confirm=False), equip_frame(LEGEND, icon=True))
        for _ in range(2):
            self.frame(t, *page)
        self.assertEqual([], t.acts)
        self.assertTrue(t.disabled)


class TestEquipPageLayer2(EquipPageCase):
    def test_layer2_buys_target_equipment_commits_on_leave(self):
        """用户 2026-10-27 18:2x：第二层目标装备没刻印也先装上。购买页：点主战员 + 购买，离开购买页后才写账。"""
        t = self.make_task(layer=1)
        page = (equip_texts("欺骗暗影的匕首", "攻击力+120", "暴击伤害+12%", purchase=True), equip_frame(LEGEND))
        for _ in range(2):
            self.frame(t, *page)
        self.assertEqual([MEMBER[0], "购买"], t.acts)
        self.frame(t, *page)                          # 购买页还没走：不重新判断、不写账
        self.assertEqual([MEMBER[0], "购买"], t.acts)
        self.assertEqual("", self.eq(t)["names"][0])
        self.frame(t, [ocr_box(0.5, 0.1, "德朗商店")], equip_frame())    # 回到商店
        self.assertEqual("欺骗暗影的匕首", self.eq(t)["names"][0])
        self.assertEqual("", self.eq(t)["imprints"][0])

    def test_layer1_still_refines_target_equipment(self):
        t = self.make_task(layer=0)
        page = (equip_texts("欺骗暗影的匕首", "攻击力+120", "暴击伤害+12%"), equip_frame(LEGEND))
        for _ in range(2):
            self.frame(t, *page)
        self.assertEqual(["提炼"], t.acts)


if __name__ == "__main__":
    unittest.main()
