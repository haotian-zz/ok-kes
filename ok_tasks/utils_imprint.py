# 刷刻印（用户 2026-10-27）：不走赛季卡厄思，从零式系统 → 法典进「裁决之沼 / 难度 10 / 回荡在银河中的歌声」；
# 法典要稀有命运加成够、没有禁止词条、没有「无法获取存储数据」的特性。坐标按 1920×1080 国服实机量取（2026-10-27）。
import re

from utils_daily import click_rel, click_text_box, find_text, refresh, rel_center

IMPRINT_KEY = "刷刻印"
SPEEDRUN_KEY = "刷刻印速刷"
MAP_KEY = "刻印法典地图"
DIFF_KEY = "刻印法典难度"
TRAIT_KEY = "刻印法典赛季特性"
RARE_KEY = "刻印法典稀有命运至少"
BAN_KEY = "刻印法典禁止词条"
SLOT_KEY = "刻印法典槽位"
MAX_SYNTH_KEY = "刻印法典最多合成次数"
TARGET_IMPRINT_KEY = "目标刻印关键词"

DEFAULTS = {
    IMPRINT_KEY: False,
    SPEEDRUN_KEY: True,
    MAP_KEY: "裁决之沼",
    DIFF_KEY: 10,
    TRAIT_KEY: "回荡在银河中的歌声",
    RARE_KEY: 50,
    BAN_KEY: ["损失", "暴君", "不安"],
    SLOT_KEY: 1,
    MAX_SYNTH_KEY: 30,
    # 国服原文「友军使用能力生成5张以上卡牌时，自身额外攻击伤害量+30%（每回合1次）」（BWIKI rr_lux_06，光之刻印）
    TARGET_IMPRINT_KEY: ["生成5张", "额外攻击伤害量"],
}

NO_SAVE_TEXT = "无法获取存储数据"
MAP_NAMES = ("裁决之沼", "降临的混沌", "第零研究所", "无间烬土", "蓝罐", "双星的暗影", "雾之都市", "幻象剧场", "万花筒孵化场")

# 零式系统「选择法典」页：左侧三个槽位，右侧法典面板
SLOT_POS = {1: (0.088, 0.340), 2: (0.088, 0.535), 3: (0.088, 0.720)}
PANEL = (0.67, 0.17, 0.995, 0.83)
REFRESH_POS = (0.967, 0.152)          # 面板右上角刷新
ENTER_POS = (0.935, 0.899)            # 「进入」/ 空槽时是「合成」
# 合成法典页
SYNTH_MAP_LIST = (0.0, 0.10, 0.25, 0.86)
SYNTH_TITLE_MAP = (0.55, 0.36, 0.78, 0.42)
SYNTH_TITLE_TRAIT = (0.50, 0.43, 0.80, 0.49)
TRAIT_ICONS = [(0.298, y) for y in (0.163, 0.288, 0.417, 0.542, 0.671, 0.799)]
DIFF_VALUE = (0.20, 0.89, 0.29, 0.95)
DIFF_MINUS, DIFF_PLUS = (0.185, 0.923), (0.310, 0.923)
ORBS_TEXT = (0.66, 0.02, 0.76, 0.08)
GOLD_TEXT = (0.79, 0.02, 0.88, 0.08)
SYNTH_NORMAL, SYNTH_CHAOS = (0.47, 0.922), (0.81, 0.922)
# 获得法典（三选一）页
PICK_CARDS = [(0.035, 0.25, 0.32, 0.82), (0.345, 0.25, 0.63, 0.82), (0.655, 0.25, 0.94, 0.82)]
PICK_ORBS = (0.70, 0.02, 0.81, 0.08)
PICK_GOLD = (0.83, 0.02, 0.93, 0.08)
PICK_NORMAL, PICK_CHAOS, PICK_CONFIRM = (0.15, 0.922), (0.46, 0.922), (0.879, 0.921)


def cfg(task, key):
    value = (getattr(task, "config", None) or {}).get(key)
    return DEFAULTS[key] if value is None or value == "" else value


def enabled(task):
    return cfg(task, IMPRINT_KEY) is True


# ------------------------- 解析 -------------------------

def parse_codex(lines):
    """法典面板/卡片的文字（从上到下）→ 地图、难度、赛季特性、PT、稀有命运、词条、能不能存档。"""
    text = "".join(lines)
    info = {"map": next((m for m in MAP_NAMES if m in text), None), "difficulty": None, "pt": None,
            "rare": 0, "mods": [], "no_save": NO_SAVE_TEXT in text, "text": text}
    m = re.search(r"(\d+)\s*[|｜丨]?\s*等级", text)
    if m:
        info["difficulty"] = int(m.group(1))
    m = re.search(r"存储数据保存上限\s*(\d+)\s*PT", text, re.I)
    if m:
        info["pt"] = int(m.group(1))
    m = re.search(r"稀有命运触发率增加\s*(\d+)\s*%", text)
    if m:
        info["rare"] = int(m.group(1))
    info["mods"] = [(name, int(level)) for name, level in re.findall(r"[\[【(（]\s*([^\]】)）\d\s]{1,4})\s*(\d)\s*[\]】)）]", text)]
    return info


def codex_problems(info, task=None, want=None):
    """不合格的原因列表；空列表＝合格。"""
    want = want or {k: cfg(task, k) for k in (MAP_KEY, DIFF_KEY, TRAIT_KEY, RARE_KEY, BAN_KEY)}
    bad = []
    if info["map"] != want[MAP_KEY]:
        bad.append(f"地图是{info['map']}")
    if info["difficulty"] != int(want[DIFF_KEY]):
        bad.append(f"难度是{info['difficulty']}")
    if want[TRAIT_KEY] and want[TRAIT_KEY] not in info["text"]:
        bad.append(f"没有赛季特性「{want[TRAIT_KEY]}」")
    if info["rare"] < int(want[RARE_KEY]):
        bad.append(f"稀有命运 +{info['rare']}% 不到 {want[RARE_KEY]}%")
    banned = [f"{n}{lv}" for n, lv in info["mods"] if any(b in n for b in want[BAN_KEY])]
    if banned:
        bad.append(f"有禁止词条 {'、'.join(banned)}")
    if info["no_save"]:
        bad.append(NO_SAVE_TEXT)
    return bad


def parse_amount(text):
    """「3,016」→3016，「18926K」→18926000。"""
    m = re.search(r"(\d[\d,，.]*)\s*([KkMm万]?)", text or "")
    if not m:
        return None
    num = float(re.sub(r"[,，]", "", m.group(1)))
    return int(num * {"k": 1000, "m": 1000000, "万": 10000}.get(m.group(2).lower(), 1))


def _region_lines(task, region):
    x1, y1, x2, y2 = region
    boxes = []
    for b in task.all_texts or []:
        cx, cy = rel_center(task, b)
        if x1 <= cx <= x2 and y1 <= cy <= y2 and b.name.strip():
            boxes.append((cy, cx, b.name.strip()))
    return [name for _, _, name in sorted(boxes)]


def _region_text(task, region):
    return "".join(_region_lines(task, region))


def _title(task, pattern, region=(0, 0, 0.35, 0.09)):
    return find_text(task, pattern, region) is not None


# ------------------------- 页面处理 -------------------------

def _synth_budget(task):
    """这次任务还能合成几次；用完就停任务，别把卡厄思之珠/金币刷光。"""
    used = getattr(task, "_codex_synth_count", 0)
    limit = int(cfg(task, MAX_SYNTH_KEY))
    if used >= limit:
        task.log_error(f"刷刻印：法典已经合成 {used} 次还没刷到合格的，停止（请手动看一下法典）", notify=True)
        task.disable()
        return False
    task._codex_synth_count = used + 1
    return True


def _pay_and_synth(task, orbs_region, gold_region, chaos_pos, normal_pos, chaos_cost_region, normal_cost_region):
    """先用卡厄思之珠（卡厄思合成），不够再用金币（普通合成）。"""
    orbs = parse_amount(_region_text(task, orbs_region))
    gold = parse_amount(_region_text(task, gold_region))
    chaos_cost = parse_amount(_region_text(task, chaos_cost_region)) or 0
    normal_cost = parse_amount(_region_text(task, normal_cost_region)) or 0
    if orbs is not None and orbs >= chaos_cost:
        if not _synth_budget(task):
            return True
        click_rel(task, *chaos_pos, after=3, reason=f"刷刻印：卡厄思合成（卡厄思之珠 {orbs}，花 {chaos_cost}）")
        return True
    if gold is not None and gold >= normal_cost:
        if not _synth_budget(task):
            return True
        click_rel(task, *normal_pos, after=3, reason=f"刷刻印：卡厄思之珠不够（{orbs}），普通合成（金币 {gold}，花 {normal_cost}）")
        return True
    task.log_error(f"刷刻印：卡厄思之珠 {orbs}、金币 {gold} 都不够合成法典，停止", notify=True)
    task.disable()
    return True


def handle_codex_select(task):
    """零式系统「选择法典」页：点配置的槽位，合格就进入；空槽点合成；不合格点刷新 → 确认 → 合成页。"""
    if not enabled(task) or not _title(task, r"零式系统") or not find_text(task, r"^选择法典$"):
        return False
    slot = int(cfg(task, SLOT_KEY))
    click_rel(task, *SLOT_POS.get(slot, SLOT_POS[1]), after=1.5, reason=f"刷刻印：选 {slot} 号法典")
    refresh(task)
    if find_text(task, r"没有保存的法典"):
        click_rel(task, *ENTER_POS, after=3, reason=f"刷刻印：{slot} 号没有法典，点合成")
        return True
    info = parse_codex(_region_lines(task, PANEL))
    bad = codex_problems(info, task)
    mods = "、".join(f"{n}{lv}" for n, lv in info["mods"]) or "无"
    task.log_info(f"刷刻印：{slot} 号法典 {info['map']} 难度{info['difficulty']} PT{info['pt']} "
                  f"稀有命运+{info['rare']}% 词条 {mods}" + (f"（不合格：{'；'.join(bad)}）" if bad else "（合格）"))
    if not bad:
        if find_text(task, r"^进入$"):
            click_rel(task, *ENTER_POS, after=3, reason="刷刻印：进入法典")
        return True
    click_rel(task, *REFRESH_POS, after=2, reason="刷刻印：法典不合格，点刷新")
    refresh(task)
    box = find_text(task, r"^确认$")
    if box:
        click_text_box(task, box, after=3, reason="刷刻印：确认刷新法典")
    return True


def handle_codex_synth(task):
    """合成法典页：地图、难度、赛季特性都对上再合成。"""
    if not enabled(task) or not _title(task, r"合成法典"):
        return False
    want_map, want_diff, want_trait = cfg(task, MAP_KEY), int(cfg(task, DIFF_KEY)), cfg(task, TRAIT_KEY)
    if want_map not in _region_text(task, SYNTH_TITLE_MAP):
        box = find_text(task, want_map, SYNTH_MAP_LIST)
        if box:
            click_text_box(task, box, after=1.5, reason=f"刷刻印：合成选地图「{want_map}」")
        else:
            task.log_info(f"刷刻印：左侧地图列表里没看到「{want_map}」，往下拖")
            task.swipe_relative(0.12, 0.70, 0.12, 0.30, duration=0.6)
            task.sleep(1.5)
        return True
    diff = parse_amount(_region_text(task, DIFF_VALUE))
    if diff != want_diff:
        pos = DIFF_PLUS if diff is None or diff < want_diff else DIFF_MINUS
        click_rel(task, *pos, after=0.8, reason=f"刷刻印：合成难度 {diff} → {want_diff}")
        return True
    if want_trait and want_trait not in _region_text(task, SYNTH_TITLE_TRAIT):
        tried = getattr(task, "_trait_icon_index", -1) + 1
        if tried >= len(TRAIT_ICONS):
            task.log_error(f"刷刻印：赛季特性一栏点了一遍都没找到「{want_trait}」，停止", notify=True)
            task.disable()
            return True
        task._trait_icon_index = tried
        click_rel(task, *TRAIT_ICONS[tried], after=1.5, reason=f"刷刻印：找赛季特性「{want_trait}」，点第 {tried + 1} 个图标")
        return True
    task._trait_icon_index = -1
    return _pay_and_synth(task, ORBS_TEXT, GOLD_TEXT, SYNTH_CHAOS, SYNTH_NORMAL,
                          (0.90, 0.89, 0.98, 0.95), (0.56, 0.89, 0.66, 0.95))


def handle_codex_pick(task):
    """获得法典（三选一）：挑合格的（稀有命运高的优先）点确认；都不合格就再合成一次。"""
    if not enabled(task) or not find_text(task, r"获得法典", (0.3, 0.05, 0.7, 0.14)):
        return False
    best = None
    for i, region in enumerate(PICK_CARDS):
        info = parse_codex(_region_lines(task, region))
        bad = codex_problems(info, task)
        mods = "、".join(f"{n}{lv}" for n, lv in info["mods"]) or "无"
        task.log_info(f"刷刻印：候选法典{i + 1} 难度{info['difficulty']} PT{info['pt']} 稀有命运+{info['rare']}% "
                      f"词条 {mods}" + (f"（不合格：{'；'.join(bad)}）" if bad else "（合格）"))
        if not bad and (best is None or (info["rare"], info["pt"] or 0) > (best[1]["rare"], best[1]["pt"] or 0)):
            best = (i, info)
    if best:
        x1, y1, x2, y2 = PICK_CARDS[best[0]]
        click_rel(task, (x1 + x2) / 2, (y1 + y2) / 2, after=1.5, reason=f"刷刻印：选候选法典{best[0] + 1}")
        click_rel(task, *PICK_CONFIRM, after=3, reason="刷刻印：确认法典")
        return True
    return _pay_and_synth(task, PICK_ORBS, PICK_GOLD, PICK_CHAOS, PICK_NORMAL,
                          (0.54, 0.89, 0.62, 0.95), (0.22, 0.89, 0.31, 0.95))


# ------------------------- 装备刻印 -------------------------

def _norm(text):
    return re.sub(r"[\s，,。.、：:（）()【】\[\]{}]", "", text or "")


def is_target_imprint(task, text):
    """刻印描述里目标关键词都在才算（OCR 会把一句拆成几行，先拼起来去掉标点再比）。"""
    words = cfg(task, TARGET_IMPRINT_KEY)
    words = [words] if isinstance(words, str) else list(words or [])
    flat = _norm(text)
    return bool(words) and all(_norm(w) in flat for w in words)


def slot_imprints(task):
    """目标主战员三个装备位上的刻印描述（空串＝没有刻印），记在装备状态里，跟装备名一起维护。"""
    equipment = task.member_status.setdefault("equipment", {})
    values = equipment.get("imprints")
    if not isinstance(values, list):
        values = []
    equipment["imprints"] = (values + ["", "", ""])[:3]
    return equipment["imprints"]


def target_imprint_count(task):
    return sum(1 for text in slot_imprints(task) if text and is_target_imprint(task, text))


def rush_escape_reason(task):
    """刷刻印速刷要不要逃脱重开：第一层打完不到 2 个目标刻印（拿到混沌之识除外）；第二层首领打完不到 3 个。"""
    if not enabled(task) or cfg(task, SPEEDRUN_KEY) is not True:
        return None
    ns = getattr(task, "node_status", None)
    if not isinstance(ns, dict) or ns.get("is_escaped"):
        return None
    layer = ns.get("pass_final_boss_count", 0)
    n = target_imprint_count(task)
    if layer >= 2 and n < 3:
        return f"第二层首领打完目标刻印只有 {n} 个（要 3 个）"
    if layer >= 1 and n < 2 and not ns.get("chaos_core_got"):
        return f"第一层打完目标刻印只有 {n} 个（要 2 个，章鱼哥掉混沌之识除外）"
    return None


def handle_rush_escape(task):
    """路线页兜底：结算页没赶上退出（被「继续」点过去了）时，回到路线页也按速刷规则逃脱。法典逃脱后还在。"""
    import time
    import utils
    reason = rush_escape_reason(task)
    if not reason:
        return False
    if utils.handle_escape(task):
        return True
    if not utils.is_route_selection_page(task):
        return False
    ns = task.node_status
    if time.time() - ns.get("imprint_escape_at", 0) < 5:
        task.sleep(1)
        return True
    ns["imprint_escape_at"] = time.time()
    task.log_info(f"刷刻印速刷：{reason}，回到路线页逃脱重开（法典保留）")
    click_rel(task, 0.959, 0.051, after=1)
    return True
