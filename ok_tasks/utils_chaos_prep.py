# 卡厄思局外准备：读目标主战员的预设构筑、零式系统升级、编队（坐标按 1920×1080 国服实机量取，2026-10-24）
import re
import unicodedata

from ok import BaseTask

from game_db import get_db, norm
from utils_daily import (refresh, find_text, click_rel, click_text, click_text_box, wait_text, open_home_entry,
                         rel_center, in_region)

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
    box = wait_text(task, r"^零式系统$", timeout=8)
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


def setup_team(task: BaseTask, members):
    """在配置队伍页把三个主战员换成 members（顺序即槽位顺序）。已经一致就什么都不点。"""
    db = get_db()
    refresh(task)
    if not find_text(task, r"^配置队伍$", region=(0, 0, 0.3, 0.1)):
        return False
    current = read_team(task)
    task.log_info(f"当前编队：{current}，目标：{members}")
    if [norm(n or "") for n in current] == [norm(m) for m in members]:
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
    ok = [norm(n or "") for n in final] == [norm(m) for m in members]
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


def enter_zero_system(task: BaseTask, want_zero=(), want_max=()):
    """主页 → 卡厄思 → 零式系统首页（之后由卡厄思模式原有的法典流程接手）。给了升级要求就先去升级页调好。"""
    if not open_home_entry(task, "卡厄思"):
        return False
    if not click_text(task, r"^零式系统$", timeout=8, after=4):
        return False
    if not wait_text(task, r"零式系统", region=(0, 0, 0.3, 0.1), timeout=10):
        return False
    if want_zero or want_max:
        apply_zero_upgrades(task, want_zero, want_max)
    return True
