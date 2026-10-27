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
ENTER_GRACE = 15                      # 点「进入」后这么多秒内不再处理选择法典页
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
PICK_COSTS = [(0.54, 0.89, 0.62, 0.95), (0.22, 0.89, 0.31, 0.95)]   # 再合成按钮上的价格（卡厄思 / 普通）
UNREAD_RETRY = 5                      # 珠/金币读不出来时最多再等几帧，不当成不够


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
    if orbs is None and gold is None:
        # 读不出来多半是页面还在转场，等几帧再说（实录 2026-10-27 02:42 读成 None 直接停了任务）
        unread = getattr(task, "_synth_unread", 0) + 1
        task._synth_unread = unread
        if unread <= UNREAD_RETRY:
            task.log_info(f"刷刻印：卡厄思之珠、金币数量没读到，等页面加载（第 {unread} 次）")
            task.sleep(1)
            return True
    task._synth_unread = 0
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
    import time
    # 点了「进入」后转场那几秒还是这一页、右边面板已经空了（实录 2026-10-27 02:00 空面板被当成不合格点了刷新），先等着
    if time.time() - getattr(task, "_codex_enter_at", 0) < ENTER_GRACE:
        task.sleep(1)
        return True
    slot = int(cfg(task, SLOT_KEY))
    click_rel(task, *SLOT_POS.get(slot, SLOT_POS[1]), after=1.5, reason=f"刷刻印：选 {slot} 号法典")
    refresh(task)
    if find_text(task, r"没有保存的法典"):
        click_rel(task, *ENTER_POS, after=3, reason=f"刷刻印：{slot} 号没有法典，点合成")
        return True
    info = parse_codex(_region_lines(task, PANEL))
    if info["map"] is None or info["difficulty"] is None:
        task.log_info(f"刷刻印：{slot} 号法典面板没读全（地图 {info['map']}、难度 {info['difficulty']}），等页面加载，不刷新")
        task.sleep(1)
        return True
    bad = codex_problems(info, task)
    mods = "、".join(f"{n}{lv}" for n, lv in info["mods"]) or "无"
    task.log_info(f"刷刻印：{slot} 号法典 {info['map']} 难度{info['difficulty']} PT{info['pt']} "
                  f"稀有命运+{info['rare']}% 词条 {mods}" + (f"（不合格：{'；'.join(bad)}）" if bad else "（合格）"))
    if not bad:
        if find_text(task, r"^进入$"):
            click_rel(task, *ENTER_POS, after=3, reason="刷刻印：进入法典")
            task._codex_enter_at = time.time()
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


def _free_pick(task):
    """通关后「搜索新坐标」给的免费三选一：只有「确认」，右上没有珠/金币、底下没有再合成的价格。"""
    regions = [PICK_ORBS, PICK_GOLD] + PICK_COSTS
    return all(parse_amount(_region_text(task, r)) is None for r in regions) \
        and find_text(task, r"^确认$", (0.80, 0.86, 0.98, 0.98)) is not None


def handle_codex_pick(task):
    """获得法典（三选一）：挑合格的（稀有命运高的优先）点确认；都不合格就再合成一次。
    通关后的免费那次（用户 2026-10-27：通关后免费生成一次，旧法典已经用掉）没有再合成按钮：都不合格就先领稀有命运最高的，
    回选择法典页按原流程刷新 / 合成。"""
    if not enabled(task) or not find_text(task, r"获得法典", (0.3, 0.05, 0.7, 0.14)):
        return False
    best, infos = None, []
    for i, region in enumerate(PICK_CARDS):
        info = parse_codex(_region_lines(task, region))
        infos.append(info)
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
    if _free_pick(task):
        i = max(range(len(infos)), key=lambda k: (infos[k]["rare"] or 0, infos[k]["pt"] or 0))
        x1, y1, x2, y2 = PICK_CARDS[i]
        click_rel(task, (x1 + x2) / 2, (y1 + y2) / 2, after=1.5,
                  reason=f"刷刻印：通关后免费的三选一都不合格，先领候选法典{i + 1}（稀有命运最高），回选择法典页再刷新")
        click_rel(task, *PICK_CONFIRM, after=3, reason="刷刻印：确认法典")
        return True
    return _pay_and_synth(task, PICK_ORBS, PICK_GOLD, PICK_CHAOS, PICK_NORMAL, *PICK_COSTS)


# ------------------------- 装备刻印 -------------------------
# 实机 2026-10-27：刻印装备在装备页名称后面、刻印那行描述开头各有一个圆形小图标——光之刻印黄色太阳、暗之刻印紫色漩涡；
# 德朗商店卡片左下角（信用点图标左上方）也有同样的图标。描述文字＝装备本身效果 + 刻印效果，接在一起。
# 用户 2026-10-27：刻印优先于装备；目标主战员用不上的装备一律提炼换信用点（商店刷新要钱），不分给队友。
TARGET, OTHER = "目标", "其他"
LIGHT, DARK = "光", "暗"
DESC_ICON_STRIP = (0.184, 0.49, 0.204, 0.67)    # 安装/购买装备页：描述区左边一条（刻印那行开头的图标）
SHOP_ICON_OFFSET = (-0.008, -0.081)             # 商店：刻印图标中心相对信用点图标中心
SHOP_ICON_HALF = (0.013, 0.022)
SHOP_RESERVE = 96                               # 商店刷新后至少还要够买一件稀有装备（96），不然刷出来也买不起
TOP_EQUIPMENT = ("混沌之识",)                    # 用户 2026-10-27：混沌之识优先级高于刻印，装上了就不被带目标刻印的武器替换


def is_top(name):
    return any(t in (name or "") for t in TOP_EQUIPMENT)


def _slot_names(task):
    names = (task.member_status.get("equipment") or {}).get("names") or []
    return (list(names) + ["", "", ""])[:3]


def _norm(text):
    return re.sub(r"[\s，,。.、：:（）()【】\[\]{}]", "", text or "")


def is_target_imprint(task, text):
    """刻印描述里目标关键词都在才算（OCR 会把一句拆成几行，先拼起来去掉标点再比）。"""
    words = cfg(task, TARGET_IMPRINT_KEY)
    words = [words] if isinstance(words, str) else list(words or [])
    flat = _norm(text)
    return bool(words) and all(_norm(w) in flat for w in words)


def icon_kind(task, region, win=0.025, min_frac=0.3):
    """区域里按颜色找刻印图标：紫色漩涡＝暗，黄色太阳＝光，都没有返回 None。滑窗取占比最高的。"""
    frame = getattr(task, "frame", None)
    if frame is None:
        return None
    import cv2
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = region
    roi = frame[max(0, int(y1 * h)):int(y2 * h), max(0, int(x1 * w)):int(x2 * w)]
    if roi.size == 0:
        return None
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    masks = {DARK: (hue >= 125) & (hue <= 155) & (sat > 90) & (val > 120),
             LIGHT: (hue >= 12) & (hue <= 32) & (sat > 120) & (val > 150)}
    win_px = max(1, min(roi.shape[0], int(win * h)))
    best, best_frac = None, min_frac
    for top in range(0, roi.shape[0] - win_px + 1, max(1, win_px // 3)):
        for kind, mask in masks.items():
            frac = float(mask[top:top + win_px].mean())
            if frac >= best_frac:
                best, best_frac = kind, frac
    return best


def target_kinds(task):
    """目标刻印是光还是暗：按关键词在刻印库（imprints.json）里找；找不到就两种都看。"""
    try:
        import json
        import os
        import game_db
        with open(os.path.join(game_db.DATA_DIR, "imprints.json"), encoding="utf-8") as f:
            data = json.load(f)
        kinds = {x["type"][0] for x in data.get("imprints", []) if x.get("type", "")[:1] in (LIGHT, DARK)
                 and is_target_imprint(task, x.get("desc", ""))}
        if kinds:
            return kinds
    except Exception:  # noqa: BLE001
        pass
    return {LIGHT, DARK}


def equipment_imprint(task, description):
    """安装/购买装备页上这件装备的刻印：TARGET / OTHER / ""，和图标颜色。"""
    kind = icon_kind(task, DESC_ICON_STRIP)
    if is_target_imprint(task, description):
        return TARGET, kind
    return (OTHER if kind else ""), kind


def slot_imprints(task):
    """目标主战员三个装备位上的刻印（TARGET / OTHER / ""），记在装备状态里跟装备名一起维护。
    换装备时新装备没有刻印就继承原来的（用户 2026-10-27），所以只在新装备自带刻印时改写。"""
    equipment = task.member_status.setdefault("equipment", {})
    values = equipment.get("imprints")
    if not isinstance(values, list):
        values = []
    equipment["imprints"] = [v if v in (TARGET, OTHER) else "" for v in (values + ["", "", ""])[:3]]
    return equipment["imprints"]


def target_imprint_count(task):
    return sum(1 for v in slot_imprints(task) if v == TARGET)


def required_imprints(task):
    """要凑几个目标刻印：3 个；装着混沌之识（且没继承到目标刻印）的槽位不算（混沌之识不会被换掉）。"""
    imprints, names = slot_imprints(task), _slot_names(task)
    return 3 - sum(1 for i in range(3) if is_top(names[i]) and imprints[i] != TARGET)


def install_decision(task, new_eq, slot, better, why, current_name=""):
    """刷刻印模式下这件装不装给目标主战员。better/why 是原来按配置优先级、品质比较的结果。
    混沌之识 > 刻印 > 装备：混沌之识装上就不换、来了就装；带目标刻印的先装（槽位没有目标刻印时）；
    槽位已有目标刻印时，只换没刻印、且更好（配置优先级更高，或同级时品质更高）的装备（继承刻印）；
    槽位还没有目标刻印时，不带目标刻印的目标装备也不装（会被之后的刻印装备顶掉）。"""
    cur_top, new_top = is_top(current_name), is_top(new_eq.get("name"))
    if cur_top and not new_top:
        return False, f"当前是「{current_name}」，优先级高于刻印，不换"
    if new_top and not cur_top:
        return True, f"「{new_eq.get('name')}」优先级高于刻印"
    have = slot_imprints(task)[slot]
    new = new_eq.get("imprint", "")
    if new == TARGET:
        if have != TARGET:
            return True, "带目标刻印（刻印优先于装备）"
        return better, f"这件和当前装备都带目标刻印，{why}"
    if have == TARGET:
        if new == OTHER:
            return False, "槽位已有目标刻印，这件带别的刻印，换上去会把目标刻印顶掉"
        if better:
            # 用户 2026-10-27：没刻印、但比当前好（目标装备，或稀有度更高）就换上去继承刻印，不提炼
            kind = "目标装备" if new_eq.get("rank") is not None else "比当前好"
            return True, f"{kind}、没有刻印，换上去继承槽位的目标刻印（{why}）"
        return False, f"槽位已有目标刻印，这件不比当前好（{why}）"
    if new_eq.get("rank") is not None and better:
        # 槽位还没有目标刻印时先装目标装备没用：之后带目标刻印的装备换上来会把它顶掉（新装备的刻印覆盖、装备本身也没了），
        # 正确顺序是先刻印、再用目标装备继承。商店里白花信用点（实录 2026-10-27 03:37 买了金冠 140、匕首 200），掉落的不如提炼。
        return False, f"目标装备但没带目标刻印，槽位还没有目标刻印，先装会被之后的刻印装备顶掉（{why}）"
    return False, "不是目标刻印也不是更好的目标装备"


def record_install(task, slot, new_eq):
    imprints = slot_imprints(task)
    if new_eq.get("imprint"):
        imprints[slot] = new_eq["imprint"]
    task.log_info(f"刷刻印：装备位刻印 {['{}号{}'.format(i + 1, v or '无') for i, v in enumerate(imprints)]}，"
                  f"目标刻印 {target_imprint_count(task)} 个")


def event_target_equipment(task, names_by_slot):
    """事件打分里当「目标装备」的名字：混沌之识一直算；其他目标装备只在槽位已有目标刻印时才算
    （槽位没有目标刻印时 install_decision 不装，拿到也是提炼，不值得为它放弃别的选项）。"""
    imprints, names = slot_imprints(task), _slot_names(task)
    out = list(TOP_EQUIPMENT)
    for slot, slot_names in enumerate(names_by_slot):
        if imprints[slot] == TARGET and not is_top(names[slot]):
            out += [n for n in slot_names if n not in out]
    return out


def pick_candidate(task, candidates):
    """选择装备（二选一）页：有带目标刻印、且对应槽位还没目标刻印的就选它（刻印优先于装备）。"""
    imprints, names = slot_imprints(task), _slot_names(task)
    for i, c in enumerate(candidates):
        if is_top(c.get("name")) and not is_top(names[c["slot"]]):
            task.log_info(f"刷刻印：候选装备「{c['ocr_name']}」优先级最高，选它")
            return i
    for i, c in enumerate(candidates):
        if is_top(names[c["slot"]]):
            continue
        if is_target_imprint(task, c.get("description", "")) and imprints[c["slot"]] != TARGET:
            task.log_info(f"刷刻印：候选装备「{c['ocr_name']}」带目标刻印，选它（刻印优先于装备）")
            return i
    return None


# ------------------------- 德朗商店 -------------------------

def _shop_seen(task):
    """这个商店里点开看过的商品：(商店, 第几次刷新, 卡片位置)。刷新一次 gen+1。
    按卡片横坐标记，不按第几个信用点图标：买走一件后它的信用点图标没了，后面的序号会前移（实录 2026-10-27）。"""
    import utils
    ns = task.node_status
    key = list(utils._shop_key(task))
    state = ns.get("imprint_shop")
    if not isinstance(state, dict) or state.get("shop") != key:
        state = {"shop": key, "gen": 0, "seen": []}
        ns["imprint_shop"] = state
    return state


def _card_pos(task, icon):
    return round((icon.x + icon.width / 2) / task.width, 1)


def shop_seen(task, icon):
    state = _shop_seen(task)
    return [state["gen"], _card_pos(task, icon)] in state["seen"]


def mark_shop_seen(task, icon):
    state = _shop_seen(task)
    state["seen"].append([state["gen"], _card_pos(task, icon)])


def on_shop_refresh(task):
    if enabled(task):
        _shop_seen(task)["gen"] += 1


def shop_inspect(task, credit_icons, card_indexes, credit):
    """商店里带目标颜色刻印图标的装备逐个点信用点图标打开购买页看刻印全文（购买页由 handle_equipment 决定买还是取消）。"""
    if not enabled(task):
        return False
    kinds = target_kinds(task)
    dx, dy = SHOP_ICON_OFFSET
    hx, hy = SHOP_ICON_HALF
    for index, icon in enumerate(credit_icons):
        if index in card_indexes or shop_seen(task, icon):
            continue
        cx = (icon.x + icon.width / 2) / task.width + dx
        cy = (icon.y + icon.height / 2) / task.height + dy
        kind = icon_kind(task, (cx - hx, cy - hy, cx + hx, cy + hy), win=2 * hy, min_frac=0.25)
        if kind not in kinds:
            continue
        mark_shop_seen(task, icon)
        task.log_info(f"刷刻印：德朗商店第{index + 1}个装备有{kind}之刻印图标，点开看刻印（信用点 {credit}）")
        task.click_box(icon)
        task.sleep(1.5)
        return True
    return False


def deck_spend_reason(task):
    """刷刻印速刷：目标刻印还没达到这一层的要求时，这局多半会逃脱重开，花信用点改卡组（冥想、付费移除、买卡）都白花，
    钱留着在商店买带目标刻印的装备（2026-10-27 04:29 实录：第一层 0 个刻印，冥想 120+160、付费移除 120，
    到第二个商店只剩 79，看到带刻印的装备也买不起）。返回不花的原因，None＝可以花。"""
    if not enabled(task) or cfg(task, SPEEDRUN_KEY) is not True:
        return None
    ns = getattr(task, "node_status", None)
    if not isinstance(ns, dict):
        return None
    n = target_imprint_count(task)
    if ns.get("pass_final_boss_count", 0) == 0:
        if n >= 2 or ns.get("chaos_core_got"):
            return None
        return f"第一层目标刻印 {n}/2，不够这局会逃脱，信用点留着买刻印装备"
    need = required_imprints(task)
    if n >= need:
        return None
    return f"第二层目标刻印 {n}/{need}，不够首领前会逃脱，信用点留着买刻印装备"


def shop_refresh_ok(task, credit, price):
    """刷刻印模式下商店刷新不看「商店刷新信用点阈值」，只要刷完还够买一件稀有装备就刷。"""
    return credit - price >= SHOP_RESERVE


def _boss_next(ns):
    """整层路线计划的下一步是首领。"""
    plan = ns.get("full_route")
    if not plan or plan.get("layer") != ns.get("pass_final_boss_count", 0):
        return False
    steps = plan.get("steps", [])
    return plan.get("done", 0) < len(steps) and steps[plan["done"]].get("type") == "首领"


def rush_escape_reason(task, boss_next=False):
    """刷刻印速刷要不要逃脱重开：第一层打完不到 2 个目标刻印（拿到混沌之识除外）；
    第二层首领打完不到 3 个（装着混沌之识的武器位不算，就是 2 个，用户 2026-10-27 混沌之识优先级高于刻印）。"""
    if not enabled(task) or cfg(task, SPEEDRUN_KEY) is not True:
        return None
    ns = getattr(task, "node_status", None)
    if not isinstance(ns, dict) or ns.get("is_escaped"):
        return None
    layer = ns.get("pass_final_boss_count", 0)
    n, need = target_imprint_count(task), required_imprints(task)
    if layer >= 2 and n < need:
        return f"第二层首领打完目标刻印只有 {n} 个（要 {need} 个）"
    # 裁决之沼只有两层：第二层首领打完就结算（按钮是「离开」）、法典用掉，结算页来不及逃脱（实录 2026-10-27 03:27）。
    # 所以第二层下一步是首领时就检查，不够就不打首领，逃脱保留法典。
    if layer >= 1 and n < need and (boss_next or _boss_next(ns)):
        return f"第二层首领前目标刻印只有 {n} 个（要 {need} 个），首领打完就结算、法典会用掉"
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
