# 卡厄思局外准备：读目标主战员的预设构筑、零式系统升级、编队（坐标按 1920×1080 国服实机量取，2026-10-24）
import re
import unicodedata

from ok import BaseTask

from game_db import get_db, norm
from utils_daily import (refresh, find_text, click_rel, click_text, click_text_box, wait_text, open_home_entry,
                         rel_center, in_region, go_home, HOME_WAKE_POINT)

# ------------------------- 预设构筑 -------------------------

MEMBER_DETAIL_CARD_TAB = (0.119, 0.349)      # 主战员详情左栏「卡牌」
PRESET_BUILD_BUTTON = (0.82, 0.13)            # 卡牌页右上「预设构筑」
PRESET_TABS = {1: (0.042, 0.144), 2: (0.042, 0.267), 3: (0.042, 0.388)}
# 预设构筑页 2 行 × 4 列卡牌格子 (x1, y1, x2, y2)
PRESET_COLS = [(0.091, 0.234), (0.247, 0.391), (0.404, 0.547), (0.560, 0.703)]
PRESET_ROWS = [(0.137, 0.507), (0.528, 0.898)]
NAME_BAND = (0.015, 0.075)                   # 卡名在格子顶部这一段（相对格子顶的 y 偏移）
DESC_BAND_START = 0.19                       # 描述从格子顶往下这么多开始
_TYPE_WORDS = re.compile(r"^[©④②四X×\s]*(基础)?(攻击|技能|强化|诅咒|咒术)$")
_NAME_SUFFIX = re.compile(r"[（(][^）)]*[）)]?$")


def parse_preset_cards(texts, width, height):
    """把预设构筑页的 OCR 结果按格子拆成卡：[{name, raw_name, desc, card, n, god_spark}]。纯函数，方便单测。"""
    db = get_db()
    cards = []
    for y1, y2 in PRESET_ROWS:
        for x1, x2 in PRESET_COLS:
            name_boxes, desc_boxes = [], []
            for b in texts:
                cx, cy = (b.x + b.width / 2) / width, (b.y + b.height / 2) / height
                if not (x1 <= cx <= x2 and y1 <= cy <= y2):
                    continue
                dy = cy - y1
                if NAME_BAND[0] <= dy <= NAME_BAND[1]:
                    if not _TYPE_WORDS.match(b.name) and len(b.name.strip()) > 1:
                        name_boxes.append(b)
                elif dy >= DESC_BAND_START:
                    desc_boxes.append(b)
            if not name_boxes:
                continue
            name_boxes.sort(key=lambda b: b.x)
            raw_name = "".join(b.name for b in name_boxes)
            desc_boxes.sort(key=lambda b: (round(b.y / height, 2), b.x))
            desc = "\n".join(b.name for b in desc_boxes)
            card = db.find_card(_NAME_SUFFIX.sub("", raw_name).strip(), include_neutral=True)
            entry = {"raw_name": raw_name, "name": card["name"] if card else raw_name, "desc": desc, "card": card,
                     "n": None, "god_spark": None}
            if card:
                m = db.match_spark(card, desc)
                entry.update(n=m["n"], god_spark=m["god_spark"])
            cards.append(entry)
    return cards


def parse_preset_counts(texts):
    """右侧统计：卡牌数、pt、复制 a/3、移除 b/5。"""
    out = {}
    for b in texts:
        name = unicodedata.normalize("NFKC", b.name)
        m = re.search(r"(\d+)\s*/\s*(\d+)\s*pt", name, re.I)
        if m:
            out["pt"] = (int(m.group(1)), int(m.group(2)))
        m = re.fullmatch(r"\s*(\d)\s*/\s*([35])\s*", name)
        if m:
            out["copy" if m.group(2) == "3" else "remove"] = (int(m.group(1)), int(m.group(2)))
    return out


def open_member_detail(task: BaseTask, member, max_swipes=4):
    """主页 → 主战员 → 列表里点名字 → 详细信息。"""
    if not open_home_entry(task, "主战员"):
        return False
    if not wait_text(task, r"主战员列表", timeout=8):
        return False
    for _ in range(max_swipes + 1):
        refresh(task)
        box = next((b for b in task.all_texts if norm(b.name) == norm(member)), None)
        if box:
            x, y = rel_center(task, box)
            click_rel(task, x, y - 0.13, after=4, reason=f"打开主战员「{member}」")
            return bool(wait_text(task, r"详细信息", timeout=8))
        task.swipe_relative(0.5, 0.8, 0.5, 0.35, duration=0.8)
        task.sleep(1.5)
    task.log_info(f"主战员列表里没找到「{member}」")
    return False


def read_deck_preset(task: BaseTask, member, preset=1):
    """读目标主战员的预设构筑 N（只读，不点保存），返回 {"cards": [...], "counts": {...}}；失败返回 None。"""
    if not open_member_detail(task, member):
        return None
    click_rel(task, *MEMBER_DETAIL_CARD_TAB, after=3, reason="主战员详情：卡牌")
    click_rel(task, *PRESET_BUILD_BUTTON, after=3, reason="打开预设构筑")
    if not wait_text(task, r"预设构筑", region=(0, 0, 0.3, 0.1), timeout=8):
        task.log_info("没有进入预设构筑页")
        return None
    click_rel(task, *PRESET_TABS[preset], after=2.5, reason=f"切到 {preset} 号预设")
    refresh(task)
    if not find_text(task, rf"{preset}号预设"):
        task.log_info(f"没有切到 {preset} 号预设")
        return None
    cards = parse_preset_cards(task.all_texts, task.width, task.height)
    counts = parse_preset_counts(task.all_texts)
    for c in cards:
        task.log_info(f"目标卡组：{c['name']} 闪光{c['n']} 神闪{c['god_spark']} | {c['desc'].replace(chr(10), ' ')}")
    task.log_info(f"目标卡组统计：{counts}")
    return {"member": member, "preset": preset, "cards": cards, "counts": counts}


# ------------------------- 零式系统升级 -------------------------

UPGRADE_ENTRY = (0.095, 0.623)                # 零式系统首页左侧「升级」
UPGRADE_TABS = ("访问许可", "扩展权限", "管理员模式")
UPGRADE_LIST_REGION = (0.17, 0.18, 0.69, 0.99)
UPGRADE_LEVEL_REGION = (0.70, 0.16, 1.0, 0.23)   # 右侧「LV a/b」
UPGRADE_MAX_BUTTON = (0.965, 0.825)           # 》一次加到最大
UPGRADE_BUTTON = (0.85, 0.92)
RESET_ALL_BUTTON = (0.513, 0.141)


def _level_of_selected(task: BaseTask):
    # OCR 有时给全角数字和斜杠（「LV４／4」），先 NFKC 归一
    for box in task.all_texts or []:
        m = re.search(r"LV\s*(\d+)\s*/\s*(\d+)", unicodedata.normalize("NFKC", box.name))
        if m and in_region(task, box, UPGRADE_LEVEL_REGION):
            return int(m.group(1)), int(m.group(2))
    return None


def _visible_upgrade_rows(task: BaseTask):
    """当前页可见的升级项：名字 → (box, 是否满级)。"""
    rows = {}
    for b in task.all_texts:
        if not in_region(task, b, (0.17, 0.18, 0.5, 0.99)) or len(b.name) < 2:
            continue
        _, cy = rel_center(task, b)
        maxed = any(abs(rel_center(task, s)[1] - cy) < 0.03 and "等级上限" in s.name for s in task.all_texts)
        rows[b.name] = (b, maxed)
    return rows


def read_upgrade_levels(task: BaseTask, names, tab_of=None):
    """在升级页里读指定项目的等级：{名字: (a, b)}，找不到的不出现在结果里。会切页、拖动列表。
    给了 tab_of 字典就顺便记下每项在哪个分页。"""
    found = {}
    for tab in UPGRADE_TABS:
        refresh(task)
        tab_box = find_text(task, rf"^{tab}$", region=(0, 0.3, 0.17, 0.95))
        if tab_box:
            click_text_box(task, tab_box, after=2)
        for half in range(2):
            refresh(task)
            for name in names:
                if name in found:
                    continue
                box = next((b for b, _ in _visible_upgrade_rows(task).values() if norm(name) in norm(b.name)), None)
                if box:
                    click_text_box(task, box, after=1.5)
                    refresh(task)
                    lv = _level_of_selected(task)
                    if lv:
                        found[name] = lv
                        if tab_of is not None:
                            tab_of[name] = tab
            if half == 0:
                task.swipe_relative(0.47, 0.85, 0.47, 0.3, duration=0.8)
                task.sleep(2)
    return found


def _open_upgrade_page(task: BaseTask):
    """零式系统首页 → 升级页。刚回到首页时按钮还在动画里，点了没反应，所以按文字找、再试一次。"""
    for _ in range(2):
        box = wait_text(task, r"^升级$", region=(0, 0.55, 0.2, 0.7), timeout=8)
        if box:
            click_text_box(task, box, after=3, reason="零式系统：升级")
        else:
            click_rel(task, *UPGRADE_ENTRY, after=3, reason="零式系统：升级")
        if wait_text(task, r"全部重置", timeout=6):
            return True
    task.log_info("没有进入零式系统升级页")
    return False


def _levels_ok(levels, want_zero, want_max):
    bad = [n for n in want_zero if levels.get(n, (None,))[0] != 0]
    bad += [n for n in want_max if not levels.get(n) or levels[n][0] != levels[n][1]]
    return bad


def check_zero_upgrades(task: BaseTask, want_zero, want_max):
    """检查零式升级是否符合：want_zero 里的项必须 0 级，want_max 里的项必须满级。返回 (是否符合, 等级表)。只读不改。"""
    if not open_home_entry(task, "卡厄思"):
        return False, {}
    box = wait_text(task, r"^零式系统$", timeout=15)
    if not box:
        return False, {}
    click_text_box(task, box, after=4, reason="进入零式系统")
    if not _open_upgrade_page(task):
        return False, {}
    levels = read_upgrade_levels(task, list(want_zero) + list(want_max))
    bad = _levels_ok(levels, want_zero, want_max)
    task.log_info(f"零式升级检查：{'不符合 ' + str(bad) if bad else '符合'} {levels}")
    return not bad, levels


_UPGRADE_ROW_NAME = re.compile(r"[*＊]?[\u4e00-\u9fff]{2,}")
_PAID_DIALOG = re.compile(r"\d+元|充值|购买|礼包")


def _row_matches(name, names):
    return any(norm(n) in norm(name) for n in names)


def _confirm_center_dialog(task: BaseTask, what):
    """点掉升级/重置弹出的确认框；带付费字样的不点。返回是否点了确认。"""
    refresh(task)
    ok_box = find_text(task, r"^确认$", region=(0.55, 0.55, 0.8, 0.7))
    if not ok_box:
        return False
    text = " ".join(b.name for b in task.all_texts if in_region(task, b, (0.2, 0.3, 0.8, 0.55)))
    if _PAID_DIALOG.search(text):
        task.log_error(f"{what}弹出的确认框像是付费「{text}」，不点，按取消")
        click_rel(task, 0.347, 0.631, after=1.5, reason="取消")
        return False
    task.log_info(f"{what}确认框「{text}」，点确认")
    click_text_box(task, ok_box, after=2.5)
    return True


def _upgrade_selected_to_max(task: BaseTask, name):
    """已选中某项：》加到最大 → 升级。返回升级后的 (a, b)，读不到为 None。"""
    before = _level_of_selected(task)
    if not before or before[0] >= before[1]:
        return before
    click_rel(task, *UPGRADE_MAX_BUTTON, after=1, reason=f"「{name}」加到最大")
    click_rel(task, *UPGRADE_BUTTON, after=2.5, reason=f"升级「{name}」")
    _confirm_center_dialog(task, f"升级「{name}」")
    refresh(task)
    after = _level_of_selected(task)
    task.log_info(f"零式升级：「{name}」{before} → {after}")
    return after


def upgrade_rows(task: BaseTask, only=None, skip=(), passes=2, tabs=UPGRADE_TABS):
    """在升级页把没满级的项升满：only 给了就只升这些，skip 里的永远不升，tabs 限定分页。
    重置后有的项可能要同页别的项升了才解锁，所以整体走 passes 遍，某遍没有任何变化就停。返回升过的项目名。"""
    done = []
    for _ in range(passes):
        changed = False
        for tab in tabs:
            refresh(task)
            tab_box = find_text(task, rf"^{tab}$", region=(0, 0.1, 0.17, 0.95))
            if tab_box:
                click_text_box(task, tab_box, after=2)
            for half in range(2):
                refresh(task)
                for name, (box, maxed) in _visible_upgrade_rows(task).items():
                    if maxed or not _UPGRADE_ROW_NAME.fullmatch(name) or "等级上限" in name:
                        continue
                    if _row_matches(name, skip) or (only is not None and not _row_matches(name, only)):
                        continue
                    click_text_box(task, box, after=1.5)
                    refresh(task)
                    before = _level_of_selected(task)
                    after = _upgrade_selected_to_max(task, name)
                    if before and after and after[0] > before[0]:
                        changed = True
                        done.append(name)
                if half == 0:
                    task.swipe_relative(0.47, 0.85, 0.47, 0.3, duration=0.8)
                    task.sleep(2)
        if not changed:
            break
    return done


def reset_all_upgrades(task: BaseTask, tab):
    """升级页「全部重置」：只重置**当前分页**（2026-10-24 实机：在管理员模式点，访问许可和扩展权限不变），
    花 10 个货币，已消耗的材料全部返还。"""
    tab_box = wait_text(task, rf"^{tab}$", region=(0, 0.1, 0.17, 0.95), timeout=5)
    if not tab_box:
        task.log_info(f"升级页找不到分页「{tab}」，不重置")
        return False
    click_text_box(task, tab_box, after=2)
    click_rel(task, *RESET_ALL_BUTTON, after=2, reason="零式系统：全部重置")
    if not wait_text(task, r"将重置全部技能", timeout=5):
        task.log_info("没有弹出全部重置确认框")
        return False
    return _confirm_center_dialog(task, "全部重置")


def apply_zero_upgrades(task: BaseTask, want_zero, want_max):
    """零式系统首页进升级页，把等级调成要求的样子，再退回零式系统首页。返回最后是否符合。

    want_zero 有项不是 0 级 → 把它所在的分页全部重置，再把那页除 want_zero 外的项升满（重置会返还已消耗的材料）；
    只是 want_max 没满 → 只升这几项。"""
    if not want_zero and not want_max:
        return True
    if not _open_upgrade_page(task):
        return False
    names = list(want_zero) + list(want_max)
    tab_of = {}
    levels = read_upgrade_levels(task, names, tab_of)
    missing = [n for n in names if n not in levels]
    if missing:
        task.log_error(f"零式升级页找不到 {missing}，不调整")
        bad = missing
    elif any(levels[n][0] > 0 for n in want_zero):
        tabs = list(dict.fromkeys(tab_of[n] for n in want_zero if levels[n][0] > 0))
        task.log_info(f"零式升级 {levels}：{[n for n in want_zero if levels[n][0] > 0]} 要 0 级，重置分页 {tabs} 后重新升满其他项")
        for tab in tabs:
            if reset_all_upgrades(task, tab):
                upgrade_rows(task, skip=want_zero, passes=3, tabs=[tab])
        # 前面分页没满时后面分页会不会受影响还没摸清，统一再补一遍
        upgrade_rows(task, skip=want_zero, passes=1)
        levels = read_upgrade_levels(task, names)
        bad = _levels_ok(levels, want_zero, want_max)
    else:
        if _levels_ok(levels, want_zero, want_max):
            upgrade_rows(task, only=want_max)
            levels = read_upgrade_levels(task, names)
        bad = _levels_ok(levels, want_zero, want_max)
    task.log_info(f"零式升级调整：{'仍不符合 ' + str(bad) if bad else '符合'} {levels}")
    task.send_key("esc")
    task.sleep(2)
    wait_text(task, r"^法典$", timeout=8)
    return not bad


# ------------------------- 梦境模式 -------------------------

# 配置队伍页右上角紫色开关。位置不固定：常驻卡厄思右边有体力条（开关在 x≈0.78），活动卡厄思没有（x≈0.93）
DREAM_SEARCH = (1250, 10, 1920, 95)           # 1920×1080 下的搜索范围


def dream_toggle(frame):
    """找梦境模式开关：返回 (中心相对 x, 中心相对 y, 是否开着)，找不到为 None。
    2026-10-24 实机：开关右半关着是灰色轨道 BGR≈(205,205,205)，开着是淡紫色圆钮 ≈(206,161,189)～(249,209,235)。"""
    import cv2
    import numpy as np
    if frame.shape[:2] != (1080, 1920):
        frame = cv2.resize(frame, (1920, 1080))
    x0, y0, x1, y1 = DREAM_SEARCH
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    mask = ((hsv[..., 0] > 120) & (hsv[..., 0] < 160) & (hsv[..., 1] > 120) & (hsv[..., 2] > 80)).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n < 2:
        return None
    i = max(range(1, n), key=lambda k: stats[k, 4])
    x, y, w, h, area = stats[i]
    if area < 1500:
        return None
    x, y = x + x0, y + y0
    track = frame[y + h // 3:y + 2 * h // 3, x + int(w * 0.68):x + int(w * 0.9)].reshape(-1, 3).astype(int)
    b, g, r = track.mean(axis=0)
    return (x + w / 2) / 1920, (y + h / 2) / 1080, bool(b - g > 20 and r - g > 10)


def dream_mode_on(task: BaseTask):
    found = dream_toggle(task.frame)
    return bool(found and found[2])


def _back_to_team_page(task: BaseTask, timeout=12):
    """等回到配置队伍页。2026-10-24 实机：第一次开梦境模式会插一段「战斗失败 / 同步失败」画面，右下角只有「确认」，点掉。"""
    import time
    end = time.time() + timeout
    while time.time() < end:
        refresh(task)
        if find_text(task, r"^配置队伍$", region=(0, 0, 0.3, 0.1)):
            return True
        ok_box = find_text(task, r"^确认$", region=(0.8, 0.85, 1, 1))
        if ok_box:
            shown = " ".join(b.name for b in task.all_texts if len(b.name) >= 2)[:80]
            task.log_info(f"开关梦境模式后弹出「{shown}」，点确认")
            click_text_box(task, ok_box, after=2)
            continue
        task.sleep(1)
    return False


def ensure_dream_mode(task: BaseTask, want=True):
    """把梦境模式开关调到 want。开不了（队伍里没有经历过深层创伤的主战员）就记日志返回 False。"""
    if not _back_to_team_page(task, timeout=3):
        task.log_info("不在配置队伍页，不动梦境模式")
        return False
    if dream_mode_on(task) == want:
        task.log_info(f"梦境模式已经{'开着' if want else '关着'}")
        return True
    found = dream_toggle(task.frame)
    if not found:
        task.log_info("配置队伍页没找到梦境模式开关")
        return False
    click_rel(task, found[0], found[1], after=2.5, reason=f"{'开启' if want else '关闭'}梦境模式")
    if not _back_to_team_page(task):
        task.log_info("开关梦境模式后没回到配置队伍页")
        return False
    if dream_mode_on(task) == want:
        cap = find_text(task, r"\d+\s*PT", region=(0.85, 0.78, 0.99, 0.85))
        task.log_info(f"梦境模式已{'开启' if want else '关闭'}，存储数据存储上限 {cap.name if cap else '?'}")
        return True
    task.log_info(f"梦境模式{'开' if want else '关'}不了（开梦境要队伍里有经历过深层创伤的主战员），按现状继续")
    return False


# ------------------------- 编队 -------------------------

TEAM_SLOTS = [(0.12, 0.55), (0.34, 0.55), (0.555, 0.55)]   # 配置队伍页三个主战员卡
TEAM_SLOT_DETAIL = [(0.195, 0.19), (0.409, 0.19), (0.624, 0.19)]  # 每张卡右上的放大镜 → 详细信息
# 主战员列表底栏三个已选头像各自的 ×（移除后槽位不左移，空位显示数字）
SELECTED_BAR_REMOVES = [(0.146, 0.905), (0.206, 0.905), (0.265, 0.905)]
CONFIRM_TEAM = (0.88, 0.937)                                # 主战员列表右下「配置」
LIST_ALL_FILTER = (0.055, 0.154)                            # 主战员列表左栏「全部」
# 主战员列表左栏属性筛选（筛完一般一排放得下；已选的人会排在最前面）
EGO_FILTERS = {"热情": (0.054, 0.25), "正义": (0.054, 0.343), "秩序": (0.054, 0.437),
               "本能": (0.054, 0.532), "虚无": (0.054, 0.627)}
LIST_NAME_BANDS = [(0.1, 0.45, 1.0, 0.52), (0.1, 0.88, 1.0, 0.95)]  # 两排卡底部的名字条
LIST_CARD_X0, LIST_CARD_PITCH = 0.108, 0.146                # 列表每排 6 张卡的起点和间距
SAVE_TEAM_CANCEL = (0.347, 0.631)                           # 「要保存当前队伍配置吗?」的取消


def read_team(task: BaseTask):
    """配置队伍页：逐个点放大镜看名字，返回三个名字（读不到的为 None）。"""
    names = []
    for x, y in TEAM_SLOT_DETAIL:
        click_rel(task, x, y, after=3)
        box = wait_text(task, r"\S", region=(0.70, 0.13, 0.86, 0.2), timeout=5)
        names.append(box.name if box and find_text(task, r"详细信息") else None)
        task.send_key("esc")
        task.sleep(2.5)
    return names


def _find_member_in_list(task: BaseTask, name):
    """主战员列表里找名字，返回 (x, y) 或 None。

    整屏 OCR 和整条 OCR 都会时不时漏掉某个名字（实测漏过「米卡」「罗丝薇瑟」），
    所以依次试：整屏 → 名字条 → 名字条里每张卡单独一格。
    """
    refresh(task)
    for b in task.all_texts:
        if norm(b.name) == norm(name) and rel_center(task, b)[1] < 0.9:
            return rel_center(task, b)
    for x1, y1, x2, y2 in LIST_NAME_BANDS:
        for b in task.ocr(x1, y1, x2, y2):
            if norm(b.name) == norm(name):
                return rel_center(task, b)
        for i in range(6):
            cx1 = LIST_CARD_X0 + i * LIST_CARD_PITCH
            for b in task.ocr(cx1, y1, cx1 + LIST_CARD_PITCH, y2):
                if norm(b.name) == norm(name):
                    return rel_center(task, b)
    return None


def _leave_member_list(task: BaseTask):
    """不保存，退回配置队伍页。"""
    task.send_key("esc")
    task.sleep(2)
    refresh(task)
    if find_text(task, r"要保存当前队伍配置"):
        click_rel(task, *SAVE_TEAM_CANCEL, after=3, reason="不保存编队")


def same_team(current, members):
    """编队一致：逐位比名字，3 字以上的名字允许 OCR 错一个字（2026-10-28 12:06 实录「海德马丽」当成不一致，
    重开主战员列表时断网，脚本跑进了存储数据页连点）。"""
    if len(current) != len(members):
        return False
    for got, want in zip(current, members):
        got, want = norm(got or ""), norm(want)
        if got == want:
            continue
        if len(want) < 3 or len(got) != len(want) or sum(a != b for a, b in zip(got, want)) > 1:
            return False
    return True


def setup_team(task: BaseTask, members):
    """在配置队伍页把三个主战员换成 members（顺序即槽位顺序）。已经一致就什么都不点。"""
    db = get_db()
    refresh(task)
    if not find_text(task, r"^配置队伍$", region=(0, 0, 0.3, 0.1)):
        return False
    current = read_team(task)
    task.log_info(f"当前编队：{current}，目标：{members}")
    if same_team(current, members):
        return True
    click_rel(task, *TEAM_SLOTS[0], after=4, reason="打开主战员列表")
    if not wait_text(task, r"主战员列表", timeout=8):
        return False
    for i, (x, y) in enumerate(SELECTED_BAR_REMOVES):
        click_rel(task, x, y, after=1, reason=f"移除已选主战员 {i + 1}")
    for m in members:
        info = db.combatant(m)
        filt = EGO_FILTERS.get(info["ego"]) if info else None
        # 属性筛选是开关，先点「全部」复位再点目标属性
        click_rel(task, *LIST_ALL_FILTER, after=2)
        if filt:
            click_rel(task, *filt, after=2.5, reason=f"筛选「{info['ego']}」")
        pos = _find_member_in_list(task, m)
        if not pos:
            task.swipe_relative(0.55, 0.75, 0.55, 0.45, duration=0.8)
            task.sleep(1.5)
            pos = _find_member_in_list(task, m)
        if not pos:
            task.log_info(f"主战员列表里没找到「{m}」，放弃编队")
            _leave_member_list(task)
            return False
        click_rel(task, pos[0], pos[1] - 0.13, after=1.5, reason=f"选择「{m}」")
    click_rel(task, *CONFIRM_TEAM, after=4, reason="确认编队")
    if not wait_text(task, r"^配置队伍$", region=(0, 0, 0.3, 0.1), timeout=8):
        return False
    final = read_team(task)
    ok = same_team(final, members)
    task.log_info(f"编队结果：{final}（{'正确' if ok else '不符'}）")
    return ok


# ------------------------- 进入卡厄思 -------------------------

_EXPLORE = re.compile(r"探索度\D{0,2}(\d+)")


def parse_explore_regions(texts, width, height):
    """卡厄思具象区域页：每个「探索度：N」正上方那行是区域名。返回 [{name, explore, box}]，纯函数。"""
    regions = []
    for b in texts:
        m = _EXPLORE.search(unicodedata.normalize("NFKC", b.name))
        if not m or "等级" in b.name:
            continue
        cx, cy = (b.x + b.width / 2) / width, (b.y + b.height / 2) / height
        above = [t for t in texts
                 if t is not b and not _EXPLORE.search(t.name) and len(t.name.strip()) >= 2
                 and 0.02 <= cy - (t.y + t.height / 2) / height <= 0.08
                 and abs((t.x + t.width / 2) / width - cx) <= 0.06]
        if above:
            name = min(above, key=lambda t: cy - (t.y + t.height / 2) / height)
            regions.append({"name": name.name.strip(), "explore": int(m.group(1)), "box": name})
    return regions


def enter_chaos_figure(task: BaseTask, max_explore=30):
    """主页 → 卡厄思 → 卡厄思具象 → 探索度最低（且没满 max_explore）的区域 → 进入，停在配置队伍页。"""
    if not open_home_entry(task, "卡厄思"):
        return False
    if not click_text(task, r"^卡厄思具象$", timeout=8, after=4):
        return False
    if not wait_text(task, r"探索度", timeout=8):
        return False
    regions = parse_explore_regions(task.all_texts, task.width, task.height)
    task.log_info(f"卡厄思具象区域探索度：{[(r['name'], r['explore']) for r in regions]}")
    todo = [r for r in regions if r["explore"] < max_explore]
    if not todo:
        task.log_info(f"所有区域探索度都已达到 {max_explore}，不进入")
        return False
    target = min(todo, key=lambda r: r["explore"])
    click_text_box(task, target["box"], after=4, reason=f"选择区域「{target['name']}」（探索度 {target['explore']}）")
    if not click_text(task, r"^进入$", region=(0.8, 0.85, 1, 1), timeout=8, after=4):
        return False
    return bool(wait_text(task, r"^配置队伍$", region=(0, 0, 0.3, 0.1), timeout=10))


# ------------------------- 活动卡厄思 -------------------------

# 主页右下角活动横幅上的倒计时（左上角也有别的活动倒计时，所以限定右下）；横幅本体在倒计时下方一点
EVENT_COUNTDOWN_REGION = (0.7, 0.72, 1.0, 0.88)
EVENT_BANNER_BELOW = 0.07
EVENT_CHAOS_REGION = (0.0, 0.4, 0.4, 0.65)         # 活动页左侧「卡厄思」大字
# 活动卡厄思难度：左侧一列罗马数字圆圈（OCR 认不出），选中的实心粉色，没解锁的是锁
DIFF_COLUMN_X = 0.0714
DIFF_PITCH = 129 / 1080                            # 相邻难度圆的间距
DIFF_CLICK_Y = (0.17, 0.8)                         # 列表上下两头会被标题和「探索度」按钮挡住
DIFF_LEVEL_REGION = (0.68, 0.25, 0.76, 0.31)       # 右侧面板「等级NN」（推荐等级）
# 2026-10-24 天幕实测：难度 → 推荐等级（Ⅷ 以上当时没解锁）
DIFF_LEVELS = {1: 30, 2: 40, 3: 50, 4: 60, 5: 65, 6: 70, 7: 75, 8: 80, 9: 95, 10: 110}   # Ⅷ 2026-10-24 通关Ⅶ后解锁实机80；Ⅸ 95、Ⅹ 110（2026-10-25）
_LOCK_TEMPLATE = None


def _lock_template():
    global _LOCK_TEMPLATE
    if _LOCK_TEMPLATE is None:
        import os
        import cv2
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "chaos_map", "ref_diff_lock.png")
        _LOCK_TEMPLATE = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    return _LOCK_TEMPLATE


def difficulty_circles(frame):
    """左侧难度圆圈：[(相对 y, 是否选中, 是否上锁)]，从上到下。"""
    import cv2
    h, w = frame.shape[:2]
    sx, sy = w / 1920, h / 1080
    x0, x1, y0, y1 = int(60 * sx), int(220 * sx), int(160 * sy), int(940 * sy)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if (w, h) != (1920, 1080):
        frame = cv2.resize(frame, (1920, 1080))
        gray = cv2.resize(gray, (1920, 1080))
        x0, x1, y0, y1 = 60, 220, 160, 940
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    found = cv2.HoughCircles(cv2.medianBlur(gray[y0:y1, x0:x1], 5), cv2.HOUGH_GRADIENT, dp=1, minDist=90,
                             param1=80, param2=30, minRadius=30, maxRadius=50)
    if found is None:
        return []
    lock = _lock_template()
    out = []
    for cx, cy, _ in sorted(found[0], key=lambda c: c[1]):
        x, y = int(cx) + x0, int(cy) + y0
        if not 100 < x < 175:
            continue
        selected = hsv[y - 25:y + 25, x - 25:x + 25, 2].mean() > 180
        crop = gray[max(0, y - 35):y + 35, x - 30:x + 30]
        locked = (lock is not None and crop.shape[0] >= lock.shape[0] and crop.shape[1] >= lock.shape[1]
                  and cv2.matchTemplate(crop, lock, cv2.TM_CCOEFF_NORMED).max() > 0.8)
        out.append((y / 1080, bool(selected), bool(locked)))
    return out


def _difficulty_level(task: BaseTask):
    refresh(task)
    for b in task.all_texts or []:
        m = re.search(r"等级\s*(\d+)", b.name)
        if m and in_region(task, b, DIFF_LEVEL_REGION):
            return int(m.group(1))
    return None


def _diff_of_level(level):
    return next((d for d, lv in DIFF_LEVELS.items() if lv == level), None)


def _swipe_difficulty_list(task: BaseTask, to_top, times=2):
    for _ in range(times):
        if to_top:
            task.swipe_relative(DIFF_COLUMN_X, 0.3, DIFF_COLUMN_X, 0.75, duration=0.6)
        else:
            task.swipe_relative(DIFF_COLUMN_X, 0.75, DIFF_COLUMN_X, 0.3, duration=0.6)
        task.sleep(1.5)


def _click_difficulty(task: BaseTask, y):
    click_rel(task, DIFF_COLUMN_X, y, after=2, reason="选择卡厄思难度")
    refresh(task)
    return any(abs(cy - y) < 0.03 and sel for cy, sel, _ in difficulty_circles(task.frame))


def select_difficulty(task: BaseTask, want=None):
    """活动卡厄思首页选难度：want=None 选已解锁的最高难度，否则选第 want 档（Ⅰ=1）。
    选不到 want 就返回当前档（认不出为 None），由调用方决定重试或停止，不退回最高难度。"""
    if want:
        _swipe_difficulty_list(task, to_top=True)
        refresh(task)
        circles = [c for c in difficulty_circles(task.frame) if DIFF_CLICK_Y[0] - 0.05 < c[0] < DIFF_CLICK_Y[1] + 0.1]
        # 拖到顶后第一个圆是 Ⅰ
        if len(circles) >= want and not circles[want - 1][2] and DIFF_CLICK_Y[0] < circles[want - 1][0] < DIFF_CLICK_Y[1]:
            _click_difficulty(task, circles[want - 1][0])
        else:
            # 在屏幕下方：先点一个可见的已解锁圆，按推荐等级认出它是第几档，再按间距算出目标的位置，不在可点范围就小幅拖动再算
            # 2026-10-26 15:32 实录：参照圆取了最上面那个（0.18，半挡在标题下），点了没认出选中就放弃，停在 Ⅵ。
            # 改成取最靠中间的已解锁圆当参照，点完不对就按实际选中的档位再算一次，不放弃
            for _ in range(8):
                refresh(task)
                circles = [c for c in difficulty_circles(task.frame) if DIFF_CLICK_Y[0] < c[0] < DIFF_CLICK_Y[1]]
                unlocked = [c for c in circles if not c[2]]
                if not unlocked:
                    break
                ref = min(unlocked, key=lambda c: abs(c[0] - 0.5))
                if not _click_difficulty(task, ref[0]):
                    continue
                base = _diff_of_level(_difficulty_level(task))
                if not base:
                    continue
                if base == want:
                    break
                y = ref[0] + (want - base) * DIFF_PITCH
                if DIFF_CLICK_Y[0] < y < DIFF_CLICK_Y[1]:
                    _click_difficulty(task, y)
                    if _diff_of_level(_difficulty_level(task)) == want:
                        break
                    continue
                # 目标在上面 → 往下拖（列表向上翻）；在下面 → 往上拖
                dy = 0.08 if y < DIFF_CLICK_Y[0] else -0.08
                task.swipe_relative(DIFF_COLUMN_X, 0.5 - dy / 2, DIFF_COLUMN_X, 0.5 + dy / 2, duration=0.6)
                task.sleep(1.5)
        got = _diff_of_level(_difficulty_level(task))
        if got == want:
            task.log_info(f"卡厄思难度：选了第 {want} 档（推荐等级 {DIFF_LEVELS[want]}）")
            return want
        # 指定了难度就绝不退回最高难度（2026-10-26 实录没认出 Ⅷ 就选了最高难度，之后一直在最高难度刷）
        task.log_info(f"卡厄思难度：没选到第 {want} 档（当前 {got}）")
        return got
    _swipe_difficulty_list(task, to_top=False)
    refresh(task)
    circles = [c for c in difficulty_circles(task.frame) if DIFF_CLICK_Y[0] < c[0] < DIFF_CLICK_Y[1]]
    unlocked = [c for c in circles if not c[2]]
    if not unlocked:
        _swipe_difficulty_list(task, to_top=True, times=1)
        refresh(task)
        unlocked = [c for c in difficulty_circles(task.frame) if DIFF_CLICK_Y[0] < c[0] < DIFF_CLICK_Y[1] and not c[2]]
    if not unlocked:
        task.log_info("卡厄思难度：没找到已解锁的难度，按游戏当前选择")
        return _diff_of_level(_difficulty_level(task))
    y, selected, _ = unlocked[-1]
    if not selected:
        _click_difficulty(task, y)
    level = _difficulty_level(task)
    task.log_info(f"卡厄思难度：选了最高难度（推荐等级 {level}，第 {_diff_of_level(level)} 档）")
    return _diff_of_level(level)


def enter_event_chaos(task: BaseTask, difficulty=None):
    """主页 → 右下角活动横幅 → 活动页「卡厄思」→ 选难度 → 进入，停在配置队伍页。"""
    if not go_home(task):
        return False
    box = None
    for _ in range(2):
        refresh(task)
        box = find_text(task, r"\d+天\d*小时", region=EVENT_COUNTDOWN_REGION)
        if box:
            break
        click_rel(task, *HOME_WAKE_POINT, after=1.5, reason="唤醒主页 UI")
    if box:
        x, y = rel_center(task, box)
        click_rel(task, x, y + EVENT_BANNER_BELOW, after=4, reason=f"进入活动（倒计时 {box.name}）")
    elif not click_text(task, r"凝结.*约", region=(0.7, 0.8, 1, 1), timeout=3, after=4):
        task.log_info("主页右下角没找到活动入口")
        return False
    if not click_text(task, r"^卡厄思$", region=EVENT_CHAOS_REGION, timeout=10, after=4):
        task.log_info("活动页没找到「卡厄思」")
        return False
    if not wait_text(task, r"再次观测|^难度$", timeout=10):
        return False
    title = find_text(task, r"^[\u4e00-\u9fff]{2,6}$", region=(0.68, 0.17, 0.85, 0.25))
    task.log_info(f"活动卡厄思「{title.name if title else '?'}」")
    on_lobby = getattr(task, "on_chaos_lobby", None)
    if on_lobby and on_lobby() == "restart":
        return "restart"
    got = select_difficulty(task, difficulty)
    if difficulty and got != difficulty:
        # 用户 2026-10-26：选不到指定难度就不要开始，直接报错
        task.log_error(f"卡厄思难度：要第 {difficulty} 档，没选到（当前 {got}），不开始，停止任务", notify=True)
        task.disable()
        return "stopped"
    if (getattr(task, "chaos_overrides", None) or {}).get("存储数据保存上限大于多少"):
        # 刷存档要先观测词条：停在难度页，交给 utils_chaos.handle_season_chaos_initial_page（再次观测 → 进入）
        return True
    if not click_text(task, r"^进入$", region=(0.8, 0.85, 1, 1), timeout=8, after=4):
        return False
    return bool(wait_text(task, r"^配置队伍$", region=(0, 0, 0.3, 0.1), timeout=10))


def enter_zero_system(task: BaseTask, want_zero=(), want_max=()):
    """主页 → 卡厄思 → 零式系统首页（之后由卡厄思模式原有的法典流程接手）。给了升级要求就先去升级页调好。"""
    if not open_home_entry(task, "卡厄思"):
        return False
    if not click_text(task, r"^零式系统$", timeout=15, after=4):     # 卡厄思页加载实测要 10 秒多
        return False
    if not wait_text(task, r"零式系统", region=(0, 0, 0.3, 0.1), timeout=10):
        return False
    if want_zero or want_max:
        apply_zero_upgrades(task, want_zero, want_max)
    return True
