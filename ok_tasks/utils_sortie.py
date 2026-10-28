from ok import TriggerTask

from utils import (
    handle_dialogue,
    _move_and_click, _simplify_texts, _edit_distance, _get_config_value, _get_card_list, _get_route_priority, _get_game_text,
    find_box_at_point, find_text, recognize_cards,
    _card_has_type_below, select_card, calculate_dominant_hue,
    log_credit, log_node_status, handle_battle_crash, handle_close_page, handle_refine_equipment_credit,
    handle_center_confirm, handle_settlement, handle_skip,
    handle_destiny_choice, handle_main_member_flash,
    handle_card_reward, handle_equipment, settle_equipment_pending,
    handle_select_card, handle_copy_member,
    handle_convert_card,
    handle_negotiation, handle_continue, handle_confirm, handle_enter,
    handle_event_task, handle_route_selection, handle_obtain_reward,
    handle_leave, handle_next_step, handle_select, handle_view_original,
    handle_close_button,
    handle_card_assign, handle_non_battle_page,
    handle_remove, handle_three_choice_card_remove, handle_flash, handle_reflash, handle_grant_flash, handle_copy, handle_convert, handle_equipment_recast, handle_weakness_info, handle_minimizemap,
    handle_held_cards_page,
    handle_stuck_log, is_button_active, _clean_match,
    handle_shop, handle_expedition_result,
    handle_escape,
    _get_current_credit, _get_current_hp_percent, _get_region_text,
    _find_rest_feature, _wait_for_rest_confirm,
    # handle_stage_clear,
    _finish_only_first_layer,
    handle_auto_stop,
    _sortie_speedrun, is_route_selection_page,
    _sortie_flag, SORTIE_LEADER_CARDS_ONLY, sortie_pick_leader_card, reset_layer_status,
)
from utils_chaos import handle_archive_target_member

import re
import random
import time
import cv2

SORTIE_LEVEL = "出击难度(LV，0为不调整)"
HARDCORE = "硬核模式"
HARDCORE_TOGGLE = (0.660, 0.047)    # 主战员配置页顶部火焰眼睛开关；开着时白色旋钮在右边 (0.684, 0.049)
HARDCORE_KNOB_ON = (0.684, 0.049)
USE_SANITY = "使用理智领取奖励"
SANITY_REFILL = "理智不足时用体力补充"
LEVEL_DOWN, LEVEL_UP = (0.318, 0.500), (0.686, 0.500)   # 出击入口页中间难度圈左右的箭头（2026-10-27 实机：V=LV.80 最高档，IV=LV.65）
LEVEL_MAX_CLICKS = 8


# ------------------------- 出击模式独有工具 -------------------------

def _get_member_priority(task: TriggerTask):
    """读取主战员优先级配置，返回列表；解析失败使用默认顺序。"""
    value = _get_config_value(task, '主战员优先级', ["尼娅", "麦格纳", "米卡", "卡修斯"])
    return list(value) if isinstance(value, (list, tuple)) else ["尼娅", "麦格纳", "米卡", "卡修斯"]


def _get_blacklisted_members(task: TriggerTask):
    """读取拉黑主战员列表，返回列表；解析失败使用默认值。"""
    value = _get_config_value(task, '拉黑主战员', ["黛安娜", "阿黛尔海特"])
    return list(value) if isinstance(value, (list, tuple)) else ["黛安娜", "阿黛尔海特"]


def _get_battle_member_priority(task: TriggerTask):
    """读取出战主战员优先级配置，返回列表；解析失败使用默认顺序。"""
    value = _get_config_value(task, "出战主战员优先级", ["海德玛丽", "九", "力", "绯"])
    return list(value) if isinstance(value, (list, tuple)) else ["海德玛丽", "九", "力", "绯"]


def _card_key(text):
    table = str.maketrans("①②③④⑤⑥⑦⑧⑨⑩❶❷❸❹❺❻❼❽❾❿⓵⓶⓷⓸⓹⓺⓻⓼⓽⓾０１２３４５６７８９",
                         "1234567890123456789012345678900123456789")
    text = text.translate(table)
    m = re.search(r"\d", text)
    return m.group(0) if m else None


def _is_card_name(name):
    """判断文本是否为卡牌名：排除类型标签。"""
    exclude_keywords = {"攻击", "强化", "技能", "咒术", "基础", "基本", "状态异常", "诅咒"}
    # 包含类型关键词的文本不是卡牌名
    if any(kw in name for kw in exclude_keywords):
        return False
    # 包含"攻"且长度<=3的文本不是卡牌名（如"X攻"、"基本攻"）
    if "攻" in name and len(name) <= 3:
        return False
    return True


def _hand_card_names(task: TriggerTask):
    """读取手牌区域内的卡牌名，排除按键和类型标签文本。"""
    x1, y1, x2, y2 = 0.159, 0.683, 0.836, 0.831

    # 打印所有文本及其坐标，帮助判断手牌区域过滤问题
    task.log_info(f"_hand_card_names 区域: cx=[{x1}, {x2}], cy=[{y1}, {y2}]")
    for b in task.all_texts:
        cx = (b.x + b.width / 2) / task.width
        cy = (b.y + b.height / 2) / task.height
        in_region = x1 <= cx <= x2 and y1 <= cy <= y2
        has_key = _card_key(b.name)
        name_len = len(b.name.strip())
        task.log_info(f"  OCR: 「{b.name}」 cx={cx:.4f} cy={cy:.4f} in_region={in_region} has_key={has_key} len={name_len}")

    boxes = [b for b in task.all_texts
             if x1 <= (b.x + b.width / 2) / task.width <= x2
             and y1 <= (b.y + b.height / 2) / task.height <= y2]
    result = [b for b in boxes
              if not _card_key(b.name)
              and len(b.name.strip()) > 1
              and _is_card_name(b.name)]
    task.log_info(f"_hand_card_names 区域共{len(boxes)}个文本，过滤后剩{len(result)}个: {[b.name for b in result]}")
    return result


def _hand_cards(task: TriggerTask):
    """识别手牌，返回按位置排序的卡牌名与按键列表，按键缺失时根据手牌数和间距推断。"""
    # 按键：包含数字的
    keys = [(b.x / task.width, b.y / task.height, _card_key(b.name)) for b in task.all_texts if _card_key(b.name)]
    keys.sort(key=lambda x: x[0])

    # 卡牌名
    card_names = _hand_card_names(task)
    card_names.sort(key=lambda b: b.x)

    # 读取手牌数
    hand_count = _read_hand_count(task)

    # 配对：每个卡牌匹配其左上方最近的未使用按键
    used_keys = set()
    cards = []
    for name_box in card_names:
        cx = name_box.x / task.width
        left_x = (name_box.x) / task.width  # 使用左边缘坐标，避免文本长度影响间距判断
        cy = name_box.y / task.height

        candidates = []
        for kx, ky, k in keys:
            if k in used_keys:
                continue
            # 垂直：按键在卡牌名上方 0.03~0.06
            if not (cy - 0.06 <= ky <= cy - 0.03):
                continue
            # 水平：按键在卡牌名左方，距离不超过 0.025
            if not (cx - 0.025 <= kx <= cx + 0.01):
                continue
            candidates.append((kx, ky, k))

        if candidates:
            best = min(candidates, key=lambda x: cx - x[0])
            used_keys.add(best[2])
            cards.append({"name": name_box.name, "key": best[2], "x": cx, "left_x": left_x})
        else:
            cards.append({"name": name_box.name, "key": None, "x": cx, "left_x": left_x})

    # 推断缺失的按键：用最小相邻间距作为 expected_spacing 进行插值
    # 以最近的前一张已有按键的卡牌为基准推算，避免累积误差
    if len(cards) >= 2:
        sorted_cards = sorted(enumerate(cards), key=lambda x: x[1]["left_x"])
        # 计算相邻卡牌 left_x 的最小间距
        min_spacing = float('inf')
        for i in range(len(sorted_cards) - 1):
            spacing = sorted_cards[i + 1][1]["left_x"] - sorted_cards[i][1]["left_x"]
            if spacing < min_spacing:
                min_spacing = spacing
        expected_spacing = max(0.055, min_spacing)  # 从0.055和最小间距中取最大值，防止除零
        task.log_info(f"_hand_cards: 最小间距={min_spacing:.4f}")
        # 确保最左边的卡牌有按键，如果没有则分配1
        if sorted_cards[0][1]["key"] is None:
            sorted_cards[0][1]["key"] = "1"
            task.log_info(f"_hand_cards: 卡牌「{sorted_cards[0][1]['name']}」 left_x={sorted_cards[0][1]['left_x']:.4f} → 最左卡牌分配按键1")
        for i in range(1, len(sorted_cards)):
            idx, c = sorted_cards[i]
            if c["key"] is None:
                # 向前查找最近一张已有按键的卡牌
                for j in range(i - 1, -1, -1):
                    prev_idx, prev_c = sorted_cards[j]
                    if prev_c["key"] is not None:
                        offset = (c["left_x"] - prev_c["left_x"]) / expected_spacing
                        approx_key = int(prev_c["key"]) + round(offset)
                        if 1 <= approx_key <= 9:
                            c["key"] = str(approx_key)
                            task.log_info(f"_hand_cards: 卡牌「{c['name']}」 left_x={c['left_x']:.4f} 基于「{prev_c['name']}」(key={prev_c['key']}) offset={offset:.2f} → {c['key']}")
                        else:
                            task.log_info(f"_hand_cards: 卡牌「{c['name']}」 left_x={c['left_x']:.4f} 基于「{prev_c['name']}」(key={prev_c['key']}) offset={offset:.2f} → 推算={approx_key}超出1-9，不分配")
                        break
    elif len(cards) == 1:
        if cards[0]["key"] is None:
            cards[0]["key"] = "1"
            task.log_info(f"_hand_cards: 单张卡牌，分配按键1")

    task.log_info(f"_hand_cards: 识别到 {len(cards)} 张手牌: {[(c['name'], c['key']) for c in cards]}")
    return cards


def _try_all_card_keys(task: TriggerTask, count):
    """从当前手牌数向下尝试所有手牌按键，兜底处理按键漏识别或识别错误。
    手牌数为10时先发送0（对应第10张牌），再从9发送到1。"""
    task.log_info(f"_try_all_card_keys: 手牌数={count}")
    if count == 10:
        task.log_info("手牌数为10，先发送按键0")
        task.send_key("0")
        task.sleep(0.5)
        task.send_key("enter")
        task.sleep(1)
        start = 9
    else:
        start = min(count, 9)
    task.log_info(f"_try_all_card_keys: 发送按键 {start} 到 1")
    for index in range(start, 0, -1):
        task.send_key(str(index))
        task.sleep(0.5)
        task.send_key("enter")
        task.sleep(1)


def _read_hand_count(task: TriggerTask):
    """读取当前手牌数；OCR 误识别成三位数时只取后两位纠正。"""
    box = find_box_at_point(task, 0.509, 0.972)
    match = re.search(r"(\d+)/10", box.name) if box else None
    if not match:
        return None
    hand_count_text = match.group(1)
    if len(hand_count_text) >= 3:
        corrected = hand_count_text[-2:]
        task.log_info(f"手牌数 OCR 识别为{hand_count_text}，纠正为{corrected}")
        hand_count_text = corrected
    hand_count = int(hand_count_text)
    if hand_count > 10:
        corrected = hand_count % 100
        task.log_info(f"手牌数 OCR 识别超过10: {hand_count}，纠正为{corrected}")
        hand_count = corrected
    return min(hand_count, 10)


def _read_member_slots(task: TriggerTask):
    """根据等级和重新搜索文本动态读取会合主战员候选槽位。"""
    x1, y1, x2, y2 = 0.077, 0.572, 0.946, 0.871
    refresh_text = _get_game_text(task, "重新搜索")
    region_boxes = [
        box for box in task.all_texts
        if x1 <= (box.x + box.width / 2) / task.width <= x2
        and y1 <= (box.y + box.height / 2) / task.height <= y2
    ]
    level_boxes = sorted(
        (box for box in region_boxes if box.name.strip() == "等级"),
        key=lambda box: box.x,
    )
    refresh_boxes = [
        box for box in region_boxes
        if refresh_text in box.name
    ]

    slots = []
    unused_refresh_boxes = list(refresh_boxes)
    for level_box in level_boxes:
        level_center_x = (level_box.x + level_box.width / 2) / task.width
        level_center_y = (level_box.y + level_box.height / 2) / task.height
        name_x = level_center_x + 0.188
        name_y = level_center_y + 0.042
        name_box = find_box_at_point(task, name_x, name_y)
        name = name_box.name if name_box else ""

        refresh_box = None
        if unused_refresh_boxes:
            refresh_box = min(
                unused_refresh_boxes,
                key=lambda box: abs(
                    (box.x + box.width / 2) / task.width - level_center_x
                ),
            )
            unused_refresh_boxes.remove(refresh_box)
        refresh_y = (
            (refresh_box.y + refresh_box.height / 2) / task.height
            if refresh_box else None
        )

        if name_box:
            task.log_info(
                f"_read_member_slots: 等级位置({level_center_x:.3f},{level_center_y:.3f}) "
                f"识别到名称=「{name}」，重新搜索y={refresh_y}"
            )
        else:
            task.log_info(
                f"_read_member_slots: 等级位置({level_center_x:.3f},{level_center_y:.3f}) "
                f"未识别到主战员名称，重新搜索y={refresh_y}"
            )
        slots.append({
            "name": name,
            "x": name_x,
            "y": name_y,
            "refresh_y": refresh_y,
        })
    return slots


def _battle_member_boxes(task: TriggerTask):
    """读取出战主战员列表里的可点击主战员名称文本。"""
    _excluded = {"主战员列表", "甄别主战员", "确认", "返回", "等级", "Q", "6", "支援",
                 "治愈", "守护", "核心", "60", "令", "√", "攻", "弘命", "炫心",
                 "详细信息", "配置", "同步", "全部", "``"}
    matched = []
    for box in task.all_texts:
        cx = (box.x + box.width / 2) / task.width
        cy = (box.y + box.height / 2) / task.height
        in_x = 0.100 <= cx <= 0.984
        in_y = 0.100 <= cy <= 0.892
        excluded = box.name in _excluded
        task.log_debug(f"_battle_member_boxes: name=「{box.name}」 cx={cx:.4f} cy={cy:.4f} "
                       f"in_x={in_x} in_y={in_y} excluded={excluded}")
        if in_x and in_y and not excluded:
            matched.append(box)
    return matched


def _confirm_battle_member_selection(task: TriggerTask):
    """出战主战员选择后，按确认按钮色相决定确认或返回。"""
    dominant_hue = calculate_dominant_hue(task, (0.901, 0.931, 0.911, 0.941))
    if dominant_hue != -1 and 7 <= dominant_hue <= 17:
        task.log_info(f"出战主战员确认按钮色相={dominant_hue}，点击确认")
        _move_and_click(task, 0.906, 0.936)
        task.sleep(2)
    else:
        task.log_info(f"出战主战员确认按钮色相={dominant_hue}，未激活，返回")
        _move_and_click(task, 0.044, 0.050)
    return True


# 主战员名称 → 模板特征名映射字典（用于OCR识别不到时的模板匹配兜底）
_MEMBER_FEATURE_MAP = {
    "九": "nine",
}


def _find_battle_member(task: TriggerTask, boxes, names):
    """当前这一屏里按 names 顺序找第一个出现的主战员（OCR 全名匹配，认不出的用模板兜底），返回 (名次, 名字, box) 或 None。"""
    for rank, name in enumerate(names):
        member = next((box for box in boxes if name.strip() == box.name.strip()), None)
        if member:
            return rank, name, member
        feature_name = _MEMBER_FEATURE_MAP.get(name)
        if feature_name and task.feature_exists(feature_name):
            search_box = task.box_of_screen(0.096, 0.097, 0.988, 0.896)
            feature_box = task.find_one(feature_name=feature_name, box=search_box, threshold=0.5)
            if feature_box:
                task.log_info(f"出战主战员模板匹配成功: 配置名「{name}」 feature=「{feature_name}」 相似度={feature_box.confidence:.4f}")
                return rank, name, feature_box
    return None


def _scroll_battle_members(task: TriggerTask, down=True):
    if task.is_adb():
        y1, y2 = (0.7, 0.3) if down else (0.3, 0.7)
        task.swipe_relative(0.5, y1, 0.5, y2, duration=0.4, settle_time=0.3)
    else:
        task.move_relative(0.5, 0.5)
        task.scroll_relative(0.5, 0.7, -3 if down else 3)
    task.sleep(0.5)
    task.all_texts = _simplify_texts(task.ocr())


def _select_battle_member(task: TriggerTask, max_scrolls=5):
    """按出战主战员优先级选择列表角色：先往下翻完整个列表找排第一的，找不到再选翻到过的最靠前的那个
    （2026-10-28 00:09 实录：海德玛丽在第二排，第一屏只有排第四的绯，原来的逻辑直接选了绯）；都没有就随机选。"""
    priority = _get_battle_member_priority(task)
    task.log_info(f"出战主战员优先级配置: {priority}")
    best = None
    prev_names = None
    pages = 0
    for scroll_index in range(max_scrolls + 1):
        boxes = _battle_member_boxes(task)
        names = [box.name for box in boxes]
        task.log_info(f"第{scroll_index + 1}屏 OCR 到 {len(boxes)} 个名字: {names}")
        found = _find_battle_member(task, boxes, priority if best is None else priority[:best[0]])
        if found:
            rank, name, member = found
            if rank == 0:
                task.log_info(f"出战主战员优先级匹配成功: 「{name}」（第{scroll_index + 1}屏）")
                task._sortie_leader = name
                task.click_box(member)
                task.sleep(0.5)
                return _confirm_battle_member_selection(task)
            best = (rank, name)
            task.log_info(f"第{scroll_index + 1}屏找到优先级第{rank + 1}的「{name}」，继续往下找更靠前的")
        pages = scroll_index
        if prev_names is not None and sorted(names) == prev_names:
            task.log_info("主战员列表已到底")
            break
        prev_names = sorted(names)
        if scroll_index < max_scrolls:
            _scroll_battle_members(task, down=True)
    if best:
        rank, name = best
        task.log_info(f"整份列表没有更靠前的，回到顶部重新找「{name}」")
        for _ in range(pages + 1):
            _scroll_battle_members(task, down=False)
        for scroll_index in range(max_scrolls + 1):
            found = _find_battle_member(task, _battle_member_boxes(task), [name])
            if found:
                task.log_info(f"出战主战员优先级匹配成功: 「{name}」（优先级第{rank + 1}）")
                task._sortie_leader = name
                task.click_box(found[2])
                task.sleep(0.5)
                return _confirm_battle_member_selection(task)
            if scroll_index < max_scrolls:
                _scroll_battle_members(task, down=True)
        task.log_info(f"回头没再找到「{name}」，随机选择")
    boxes = _battle_member_boxes(task)
    if not boxes:
        task.log_info("出战主战员列表为空，无法选择")
        return False
    member = random.choice(boxes)
    task.log_info(f"未找到配置中的出战主战员，随机选择「{member.name}」")
    task._sortie_leader = member.name.strip()
    task.click_box(member)
    task.sleep(0.5)
    return _confirm_battle_member_selection(task)


# ------------------------- 出击模式独有页面处理函数 -------------------------

def handle_boss_selection(task: TriggerTask):
    """首领选择页面: 随机选择一个首领并确认。"""
    box = find_box_at_point(task, 0.484, 0.928)
    if not (box and re.search(r"请选择.*遇见的首领", box.name)):
        return False
    bosses = []
    for x, y in [(0.358, 0.706), (0.641, 0.706)]:
        name_box = find_box_at_point(task, x, y)
        if name_box:
            bosses.append({"name": name_box.name, "x": x, "y": y})
    if not bosses:
        return False
    boss = random.choice(bosses)
    task.log_info(f"首领选择: 随机选择「{boss['name']}」")
    _move_and_click(task, boss["x"], boss["y"])
    ns = task.node_status
    ns.pop("layer_settled", None)
    if ns.get("pass_final_boss_count", 0) == 0:
        # 出击模式第一层不选首领，这一页只在打完一层首领后出现（2026-10-28 两局实录）；结算页漏记时这里兜底
        ns["pass_final_boss_count"] = 1
        task.log_info("首领选择页出现但还没记到通关层数，按已通关第一层处理")
    if _sortie_speedrun(task) and task.node_status.get("pass_final_boss_count", 0) >= 1:
        task.node_status["speedrun_exit"] = True
        task.log_info("出击速刷：第二层首领已选，回到路线页就退出")
    task.sleep(1)
    # _move_and_click(task, 0.919, 0.930)
    return True


def handle_speedrun_exit(task: TriggerTask):
    """出击速刷：第二层首领选完、回到路线页就点右上角退出，交给 handle_escape 点「逃脱」。退出时记一次成功。"""
    ns = task.node_status
    if not ns.get("speedrun_exit") or ns.get("is_escaped") or not is_route_selection_page(task):
        return False
    if time.time() - ns.get("speedrun_exit_clicked_at", 0) < 3:
        task.sleep(1)       # 刚点过退出，菜单还没出来
        return True
    if not ns.get("speedrun_exit_clicked_at"):
        ns["success_rounds"] += 1
        ns["escape_reason"] = "出击速刷"
        task.log_info(f"出击速刷：第一层通关、第二层首领已选，退出（成功次数 {ns['success_rounds']}）")
    ns["speedrun_exit_clicked_at"] = time.time()
    _move_and_click(task, 0.959, 0.051)
    task.sleep(1)
    return True


def _read_sortie_level(task: TriggerTask):
    """出击入口页中间难度圈上的「LV.80」，读不到返回 None。"""
    box = find_box_at_point(task, 0.499, 0.457)
    m = re.search(r"LV\.?\s*(\d+)", box.name, re.I) if box else None
    return int(m.group(1)) if m else None


def _sortie_target_level(task: TriggerTask):
    try:
        return int(_get_config_value(task, SORTIE_LEVEL, 0) or 0)
    except (TypeError, ValueError):
        return 0


def handle_sortie_lobby(task: TriggerTask):
    """出击入口页（中间难度圈 LV.xx + 下方「进入」）：按「出击难度」点左右箭头调到目标等级再交给 handle_enter 进入。
    点了等级不变（到头/没解锁）或跨过目标（目标不是整档）就停在不超过目标的那档；理智用完又不能补就停任务。"""
    level = _read_sortie_level(task)
    enter = find_box_at_point(task, 0.499, 0.900)
    if level is None or not (enter and _clean_match(enter.name, "进入")):
        return False
    if _get_config_value(task, USE_SANITY, False) is True and getattr(task, "_sanity_exhausted", False):
        task.log_info("理智不足又没法用体力补充，停止出击（开「理智不足时用体力补充」或等理智恢复后再开）", notify=True)
        task.disable()
        return True
    target = _sortie_target_level(task)
    st = getattr(task, "_level_adjust", None)
    if not isinstance(st, dict):
        st = task._level_adjust = {"last": None, "clicks": 0, "same": 0, "done": False}
    if not target or level == target or st["done"]:
        return False

    def finish(why):
        st["done"] = True
        task.log_info(f"出击难度停在 LV.{level}（目标 LV.{target}）：{why}")
        return False

    last = st["last"]
    if last is not None:
        if level == last:
            st["same"] += 1
            if st["same"] >= 2:
                return finish("点箭头等级不变，已经到头或没解锁")
        elif (last - target) * (level - target) < 0:
            if level < target:
                return finish("目标不是整档，停在低一档")
            st["done"] = True     # 从低往高跨过了目标：退回低一档
            task.log_info(f"出击难度 LV.{level} 超过目标 LV.{target}，退回低一档")
            _move_and_click(task, *LEVEL_DOWN)
            task.sleep(2)
            return True
        else:
            st["same"] = 0
    if st["clicks"] >= LEVEL_MAX_CLICKS:
        return finish(f"已点 {LEVEL_MAX_CLICKS} 次箭头")
    st["last"] = level
    st["clicks"] += 1
    task.log_info(f"出击难度 LV.{level} → 目标 LV.{target}，点{'右' if level < target else '左'}箭头")
    _move_and_click(task, *(LEVEL_UP if level < target else LEVEL_DOWN))
    task.sleep(2)
    return True


def _use_sanity(task: TriggerTask):
    """开了「使用理智领取奖励」且这次运行没碰到理智用完又补不了。"""
    return _get_config_value(task, USE_SANITY, False) is True and not getattr(task, "_sanity_exhausted", False)


def handle_secret_enemy(task: TriggerTask):
    """战斗页面：发现特殊怪物时，随机拖动一张手牌到怪物中心。"""
    hand_count_box = find_box_at_point(task, 0.513, 0.975)
    if not (hand_count_box and re.search(r"\d+/\d+", hand_count_box.name)):
        return False

    search_box = task.box_of_screen(0.496, 0.154, 0.967, 0.636)
    secret_enemy = task.find_one(
        feature_name="secret_enemy",
        box=search_box,
        threshold=0.7,
    )
    if not secret_enemy:
        return False

    enemy_x = (secret_enemy.x + secret_enemy.width / 2) / task.width
    enemy_y = (secret_enemy.y + secret_enemy.height / 2) / task.height
    card_x = random.uniform(0.202, 0.795)
    card_y = random.uniform(0.726, 0.911)
    task.log_info(
        f"发现特殊怪物，从({card_x:.3f}, {card_y:.3f})拖动手牌到"
        f"怪物中心({enemy_x:.3f}, {enemy_y:.3f})，"
        f"相似度={secret_enemy.confidence:.4f}"
    )
    task.move_relative(card_x, card_y)
    task.swipe_relative(card_x, card_y, enemy_x, enemy_y, duration=0.5)
    return False


def handle_battle_page(task: TriggerTask):
    """战斗页面: 优先按"出牌优先级"配置出牌；找不到优先级中的牌时按当前手牌数从大到小兜底尝试。"""

    hand_count = _read_hand_count(task)
    if hand_count is None:
        return False

    # 如果已到达最终boss节点，标记boss战状态
    if hasattr(task, 'node_status') and task.node_status.get('reach_final_boss', False):
        task.node_status['final_boss_battle'] = True
        task.log_info("检测到最终boss战斗开始，final_boss_battle=True")

    # 检测 EP 能量条是否满（0.032,0.947 处 RGB 接近 (193,255,255)）
    ep_px = int(0.032 * task.width)
    ep_py = int(0.947 * task.height)
    if 0 <= ep_px < task.width and 0 <= ep_py < task.height:
        ep_region = task.frame[max(0, ep_py-2):ep_py+3, max(0, ep_px-2):ep_px+3, :3]
        if ep_region.size > 0:
            avg_bgr = cv2.mean(ep_region)[:3]
            # OpenCV 是 BGR 格式，用户描述的是 RGB(193,255,255) → BGR(255,255,193)
            avg_b, avg_g, avg_r = avg_bgr
            task.log_info(f"EP能量条区域颜色: B={avg_b:.1f} G={avg_g:.1f} R={avg_r:.1f} (期望接近 B=255 G=255 R=193)")
            if abs(avg_b - 255) <= 15 and abs(avg_g - 255) <= 15 and abs(avg_r - 193) <= 15:
                task.log_info("EP能量达到最大值，随机释放Ego技能")
                task.send_key(random.choice(["F1", "F2", "F3"]))
                task.sleep(1)
                task.send_key("enter")
                task.sleep(4)
                return True

    finishturn_box = task.box_of_screen(0.844, 0.782, 0.998, 0.990)
    if not task.find_feature(feature_name="finishturn", box=finishturn_box):
        task.log_info("未检测到finishturn特征，return True等待下一帧")
        return True

    card_names = _hand_card_names(task)
    cards = _hand_cards(task)

    if (cards or card_names):
        # 出牌卡手检测：追踪上一次尝试打出的卡牌是否连续多轮仍留在手牌中
        if not hasattr(task, '_play_stuck_count'):
            task._play_stuck_count = 0
        if not hasattr(task, '_last_attempted_card'):
            task._last_attempted_card = None

        # 检查"出牌优先级"配置
        play_priority = _get_config_value(task, "出牌优先级", [])
        if play_priority and cards:
            for pri_name in play_priority:
                matched = next((c for c in cards if pri_name and (pri_name in c["name"] or c["name"] in pri_name) and c["key"] is not None), None)
                if matched:
                    # 检测当前匹配到的卡牌是否与上次尝试打出的是同一张且仍在手牌中
                    if task._last_attempted_card == matched["name"]:
                        task._play_stuck_count += 1
                        task.log_info(f"卡牌「{matched['name']}」连续{task._play_stuck_count + 1}次尝试未出掉")
                        if task._play_stuck_count >= 3:
                            task.log_info(f"卡牌「{matched['name']}」连续3次未出掉，执行兜底出牌")
                            task._last_attempted_card = None
                            task._play_stuck_count = 0
                            _try_all_card_keys(task, hand_count)
                            return True
                    else:
                        task._last_attempted_card = matched["name"]
                        task._play_stuck_count = 0

                    task.log_info(f"出牌优先级匹配: 卡牌「{matched['name']}」→ 按键 {matched['key']}")
                    task.send_key(matched['key'])
                    task.sleep(1)
                    task.send_key("enter")
                    task.sleep(2)
                    if "极光" in matched["name"]:
                        task.log_info(f"卡牌「{matched['name']}」包含极光，额外等待2秒")
                        task.sleep(2)
                    elif "万众英雄" in matched["name"]:
                        task.log_info(f"卡牌「{matched['name']}」包含万众英雄，额外等待2秒")
                        task.sleep(2)
                    return True

        # 未命中出牌优先级，重置卡手状态
        task._last_attempted_card = None
        task._play_stuck_count = 0
        # 兜底从大到小出牌
        task.log_info(f"未命中出牌优先级，按当前手牌数{hand_count}从大到小兜底出牌")
        _try_all_card_keys(task, hand_count)
        return True
    else:
        finishturn_box = task.box_of_screen(0.844, 0.782, 0.998, 0.990)
        if task.find_feature(feature_name="finishturn", box=finishturn_box):
            task.log_info("检测到finishturn特征，按E结束回合")
            task.send_key("e")
            task.sleep(1)
        return True
    return True


def handle_get_card(task: TriggerTask):
    """获得卡牌页面: 按优先级选择卡牌。"""
    title = find_box_at_point(task, 0.502, 0.128)
    tip = find_box_at_point(task, 0.883, 0.131)
    if not (title and title.name == "获得卡牌" and tip and re.search(r"请选择.*获得的卡牌", tip.name)):
        return False
    cards = recognize_cards(task, page="获得卡牌页面")
    if not cards:
        task.log_info("获得卡牌: 未识别到卡牌类型特征，无法选择")
        return False

    priority = _get_config_value(task, "获得卡牌优先级", [])
    task.log_info(f"获得卡牌: 当前优先级配置: {priority}")
    if _sortie_flag(task, SORTIE_LEADER_CARDS_ONLY):
        # 用户 2026-10-28：出战主战员的卡就拿（优先级里的先拿），别的角色的卡和中立卡都不拿
        chosen = sortie_pick_leader_card(task, cards, priority, "获得卡牌")
        if chosen:
            task.log_info(f"获得卡牌: 选出战主战员的卡「{chosen['name']}」")
            _move_and_click(task, chosen["x"], chosen["y"])
            task.sleep(0.5)
            _move_and_click(task, 0.912, 0.931)
            return True
        priority = []
    for name in priority:
        task.log_info(f"获得卡牌: 检查优先级「{name}」是否在卡牌列表中")
        chosen = next((card for card in cards if name in card["name"]), None)
        if chosen:
            task.log_info(f"获得卡牌: 优先选择「{chosen['name']}」(匹配优先级「{name}」)")
            _move_and_click(task, chosen["x"], chosen["y"])
            task.sleep(0.5)
            _move_and_click(task, 0.912, 0.931)
            return True
    task.log_info("获得卡牌: 未命中任何优先级卡牌，跳过非优先级卡牌")
    _move_and_click(task, 0.749, 0.931)
    task.sleep(1)
    return True


def handle_draw_card_event(task: TriggerTask):
    """抽牌事件页面: 按获得卡牌优先级选择一张要手持的卡牌。"""
    title = find_box_at_point(task, 0.509, 0.108)
    prompt_pattern = _get_game_text(task, r"请选择.*手持的卡牌")
    if not (title and re.search(prompt_pattern, title.name)):
        return False
    x1, y1, x2, y2 = 0.028, 0.211, 0.938, 0.857
    cards = [
        box for box in task.all_texts
        if x1 <= (box.x + box.width / 2) / task.width <= x2
        and y1 <= (box.y + box.height / 2) / task.height <= y2
        and box.name.strip()
    ]
    if not cards:
        return False
    chosen = None
    for name in _get_config_value(task, "获得卡牌优先级", []):
        chosen = next((card for card in cards if name in card.name), None)
        if chosen:
            task.log_info(f"抽牌事件: 优先选择「{chosen.name}」")
            break
    if chosen is None:
        chosen = random.choice(cards)
        task.log_info(f"抽牌事件: 未命中优先级，随机选择「{chosen.name}」")
    task.click_box(chosen)
    task.sleep(1)
    # _move_and_click(task, 0.952, 0.933)
    return True


def handle_discard_hand_card(task: TriggerTask):
    """手牌中仍有可用卡牌提示: 点击丢弃手牌。"""
    box = find_box_at_point(task, 0.5, 0.356)
    if box and "手牌中仍有可用卡牌" in box.name:
        task.log_info("检测到手牌丢弃页面，点击丢弃")
        _move_and_click(task, 0.424, 0.500) #今日不再提示
        task.sleep(0.5)
        _move_and_click(task, 0.663, 0.607)
        return True
    return False


def _count_sortie_layer(task: TriggerTask):
    """卡厄思战利品结算页只在层首领打完后出现。首领节点不是脚本自己点进去时 reach_final_boss 没置上，
    handle_settlement 不记层数（2026-10-28 00:50 实录：第一层首领打完还是 0 层，速刷不退出），这里补记一次。"""
    ns = task.node_status
    if ns.get("layer_settled"):
        return
    ns["pass_final_boss_count"] = ns.get("pass_final_boss_count", 0) + 1
    task.log_info(f"出击模式战利品结算页：首领已打完，补记通关层数 (当前: {ns['pass_final_boss_count']})")
    reset_layer_status(task)
    task.node_status["layer_settled"] = True


def handle_sortie_reward_settlement(task: TriggerTask):
    """出击模式奖励结算页面: 按配置领取奖励或关闭页面。"""
    title = find_box_at_point(task, 0.550, 0.068)
    if not (title and title.name == "结算"):
        return False
    _count_sortie_layer(task)
    reward_box = find_box_at_point(task, 0.848, 0.389)
    if reward_box and reward_box.name == "获得" and _use_sanity(task):
        task.log_info("检测到出击模式奖励结算页面，领取奖励")
        task.click_box(reward_box)
        task.sleep(1)
        return True
    task.log_info("检测到出击模式奖励结算页面，关闭页面")
    return _finish_only_first_layer(task) if not task.node_status.get('is_escaped', False) else False


def handle_sortie_reward_claim(task: TriggerTask):
    """出击模式奖励领取页面: 按配置领取或放弃卡厄思战利品。"""
    title = find_box_at_point(task, 0.503, 0.335)
    if not (title and re.search(r"卡.*思战利品", title.name)):
        return False
    if _use_sanity(task):
        task.log_info("检测到出击模式奖励领取页面，用理智领取卡厄思战利品")
        _move_and_click(task, 0.567, 0.708)
        task.sleep(1)
        return True
    task.log_info("检测到出击模式奖励领取页面，放弃卡厄思战利品")
    _move_and_click(task, 0.355, 0.714)
    return True


def _hardcore_on(task: TriggerTask):
    """主战员配置页顶部硬核开关：右边旋钮位置是白色就是开着（2026-10-28 实机：开=白色旋钮在右、关=暗色旋钮在左）。"""
    frame = getattr(task, "frame", None)
    if frame is None:
        return None
    x, y = int(HARDCORE_KNOB_ON[0] * task.width), int(HARDCORE_KNOB_ON[1] * task.height)
    r = max(2, int(5 * task.height / 1080))
    patch = frame[max(0, y - r):y + r, max(0, x - r):x + r, :3]
    if not patch.size:
        return None
    return float(patch.mean()) > 150


def _ensure_hardcore(task: TriggerTask):
    """按「硬核模式」配置开/关主战员配置页顶部的开关；点了返回 True（下一帧再看），点 3 次还不对就不管了。"""
    want = _get_config_value(task, HARDCORE, False) is True
    on = _hardcore_on(task)
    if on is None or on == want:
        return False
    tries = getattr(task, "_hardcore_tries", 0)
    if tries >= 3:
        if tries == 3:
            task._hardcore_tries = 4
            task.log_info(f"硬核模式开关点了 3 次还是{'关' if want else '开'}着，不再点")
        return False
    task._hardcore_tries = tries + 1
    task.log_info(f"硬核模式现在{'开' if on else '关'}着，配置要{'开' if want else '关'}，点开关")
    _move_and_click(task, *HARDCORE_TOGGLE)
    task.sleep(1.5)
    return True


def handle_battle_member_config(task: TriggerTask):
    """主战员配置页面: 区分出战主战员入口和确认进入入口；点进入前按配置对齐硬核模式开关。"""
    title = find_box_at_point(task, 0.130, 0.043)
    if not (title and _get_game_text(task, '主战员配置') in title.name):
        return False
    battle_member_hint = find_box_at_point(task, 0.188, 0.799)
    if not (battle_member_hint and battle_member_hint.name.strip()):
        task.log_info("检测到主战员配置页面: 当前处于出战主战员，点击出战主战员入口")
        _move_and_click(task, 0.315, 0.475)
        task.sleep(2)
        return True
    # 只在干净的页面看开关：右边「LV.xx」在、没有确认弹窗（2026-10-28 00:44 点完进入弹出确认框，画面压暗被当成「关着」又点了开关）
    level = find_box_at_point(task, 0.708, 0.189)
    popup = any(_clean_match(b.name, "确认") for b in task.all_texts)
    if level and re.search(r"LV", level.name, re.I) and not popup and _ensure_hardcore(task):
        return True
    task.log_info("检测到主战员配置页面: 点击进入")
    _move_and_click(task, 0.719, 0.914)
    return True


def handle_battle_member_selection(task: TriggerTask):
    """出战主战员列表页面: 按配置优先级选择角色。"""
    title = find_box_at_point(task, 0.139, 0.044)
    right_hint = find_box_at_point(task, 0.562, 0.044)
    if not ((title and  _get_game_text(task, '主战员列表') in title.name) and  (right_hint and _get_game_text(task, '甄别主战员') in right_hint.name)):
        return False
    return _select_battle_member(task)


def handle_member_selection(task: TriggerTask):
    """主战员选择页面: 优先选配置角色（跳过拉黑角色）；没有则点击每个名字下方按钮刷新一次，仍没有就随机选（跳过拉黑角色）。"""
    prompt = find_box_at_point(task, 0.500, 0.931)
    if not (prompt and _get_game_text(task, '主战员') in prompt.name):
        return False
    priority = _get_member_priority(task)
    blacklisted = _get_blacklisted_members(task)
    task.log_info(f"主战员选择: 优先级={priority}, 拉黑列表={blacklisted}")

    def not_blacklisted(slot):
        return not any(blk in slot["name"] for blk in blacklisted)

    slots = _read_member_slots(task)
    chosen = None
    for name in priority:
        chosen = next((slot for slot in slots if name in slot["name"] and not_blacklisted(slot)), None)
        if chosen:
            task.log_info(f"主战员选择: 优先选择「{chosen['name']}」")
            break
    if chosen is None:
        task.log_info("主战员选择: 未找到优先角色或优先角色被拉黑，点击三个名字下方按钮刷新一次")
        for slot in slots:
            if slot["refresh_y"] is not None:
                _move_and_click(task, slot["x"], slot["refresh_y"])
                task.sleep(1)
        task.sleep(1)
        task.all_texts = _simplify_texts(task.ocr())
        slots = _read_member_slots(task)
        for name in priority:
            chosen = next((slot for slot in slots if name in slot["name"] and not_blacklisted(slot)), None)
            if chosen:
                task.log_info(f"主战员选择: 刷新后选择「{chosen['name']}」")
                break
    if chosen is None:
        valid_slots = [slot for slot in slots if slot["name"] and not_blacklisted(slot)]
        if not valid_slots:
            valid_slots = [slot for slot in slots if slot["name"]]
            if not valid_slots:
                return False
            task.log_info("主战员选择: 所有候选都被拉黑，从全部候选中随机选择")
        chosen = random.choice(valid_slots)
        task.log_info(f"主战员选择: 未找到优先角色，随机选择「{chosen['name']}」")
    _move_and_click(task, chosen["x"], chosen["y"])
    task.sleep(1)
    # _move_and_click(task, 0.884, 0.931)
    # task.sleep(0.5)
    # _move_and_click(task, 0.635, 0.639)
    # task.sleep(0.5)
    return True


def handle_rational_supply(task: TriggerTask):
    """补充理性（理智）弹窗：开了「理智不足时用体力补充」且确认可点就确认（花以太补理智）；
    否则放弃补充，这次运行不再领奖励（不改配置），回到出击入口页再停。
    要排在 handle_center_confirm 前面，不然中间的「确认」会被直接点掉、不看开关就花以太。"""
    x1, y1, x2, y2 = 0.438, 0.101, 0.561, 0.250
    title = next((b for b in task.all_texts
                  if x1 <= (b.x + b.width / 2) / task.width <= x2
                  and y1 <= (b.y + b.height / 2) / task.height <= y2
                  and "补充理性" in b.name), None)
    if not title:
        return False
    confirm_box = find_box_at_point(task, 0.664, 0.774)
    can_confirm = bool(confirm_box and _clean_match(confirm_box.name, "确认") and is_button_active(task, confirm_box))
    refill = _get_config_value(task, SANITY_REFILL, False) is True
    if refill and can_confirm:
        task.log_info("理智不足，用体力（以太）补充理智，点确认")
        task.click_box(confirm_box)
        task.sleep(1)
        return True
    why = "体力也不够（确认不可点）" if refill else "没开「理智不足时用体力补充」"
    task.log_info(f"理智不足，{why}：放弃补充，这次运行不再领取奖励")
    task._sanity_exhausted = True
    _move_and_click(task, 0.352, 0.774)
    task.sleep(1)
    return True


def handle_ether_supply(task: TriggerTask):
    """以太补充页面: 提示用户手动补充以太。"""
    box = find_box_at_point(task, 0.502, 0.139)
    if box and box.name == _get_game_text(task, '以太补充'):
        # 每次进入出击花 10 以太；不够时原来点掉弹窗又回入口页点进入，一直转圈。现在关掉弹窗就停任务
        task.log_info("以太（体力）不够进入出击，关掉以太补充弹窗并停止出击", notify=True)
        _move_and_click(task, 0.347, 0.803)
        task.sleep(0.5)
        task.disable()
        return True
    return False


def handle_battle_hand_select(task: TriggerTask):
    """战斗中手牌选择页面: 检测到请选择卡牌文本且底部有手牌数，随机选择指定数量的卡牌。"""
    # 检测(0.5, 0.111)位置的提示文本
    prompt = find_box_at_point(task, 0.5, 0.111)
    if not prompt:
        return False
    m = re.search(r'请选择(?=.*卡牌).*?(\d+)张', prompt.name)
    if not m:
        return False

    # 检测(0.505, 0.971)是否有手牌数 x/10
    hand_box = find_box_at_point(task, 0.505, 0.971)
    if not (hand_box and re.search(r'\d+/10', hand_box.name)):
        return False

    need = int(m.group(1))
    task.log_info(f"检测到战斗中手牌选择页面，需选择{need}张卡牌，随机选择")

    _card_exclude_keywords = {"攻击", "强化", "技能", "咒术", "基础", "基本", "状态异常", "诅咒"}
    selected = 0
    for _ in range(need):
        task.all_texts = _simplify_texts(task.ocr())
        cards = [
            b for b in task.all_texts
            if 0.116 <= (b.x + b.width / 2) / task.width <= 0.859
            and 0.697 <= (b.y + b.height / 2) / task.height <= 0.878
            and len(b.name.strip()) > 1
            and b.name not in ["确认", "返回", "跳过"]
            and not any(kw in b.name for kw in _card_exclude_keywords)
            and not ("攻" in b.name and len(b.name) <= 3)
        ]
        if not cards:
            task.log_info("手牌区域未找到卡牌，随机在手牌区域内点击一个位置")
            rx = random.uniform(0.216, 0.759)
            ry = random.uniform(0.697, 0.878)
            _move_and_click(task, rx, ry)
            selected += 1
            task.sleep(1)
            continue
        chosen = random.choice(cards)
        task.log_info(f"选择手牌: {chosen.name}")
        task.click_box(chosen)
        selected += 1
        task.sleep(1)

    if selected > 0:
        task.log_info(f"已完成选择，点击确认")
        _move_and_click(task, 0.934, 0.883)
        task.sleep(1)
    return True


def handle_curiosity_activate(task: TriggerTask):
    """尼娅的好奇心发动页面: 按优先级选择要手持的卡牌（战斗相关页面，优先级高于战斗页面）。"""
    box = find_box_at_point(task, 0.499, 0.129)
    if box and _get_game_text(task, '请选择1张要手持的卡牌') in box.name:
        task.log_info("检测到尼娅的好奇心发动页面")
        priority = ["剑雨", "展开极光", "一缕光芒", "万众英雄"]
        cards = recognize_cards(task, page="尼娅的好奇心页面")
        chosen_card = None
        for pri_name in priority:
            for card in cards:
                if card["name"] and card["name"] in pri_name:
                    chosen_card = card
                    task.log_info(f"按优先级选择卡牌: {card['name']}")
                    break
            if chosen_card:
                break
        if not chosen_card and cards:
            chosen_card = random.choice(cards)
            task.log_info(f"未命中优先级，随机选择卡牌: {chosen_card['name']}")
        if chosen_card:
            _move_and_click(task, chosen_card["x"], chosen_card["y"])
            task.sleep(2)
            return True
    return False


def handle_extra_card_use(task: TriggerTask):
    """额外使用卡牌页面: 随机选择一张卡牌使用（战斗相关页面，优先级高于战斗页面）。"""
    box = find_box_at_point(task, 0.498, 0.131)
    if box and "请选择张要额外使用的卡牌" in box.name:
        task.log_info("检测到额外使用卡牌页面，随机选择")
        _move_and_click(task, *random.choice([(0.251, 0.546), (0.508, 0.518), (0.764, 0.525)]))
        task.sleep(2)
        return True
    return False


def handle_card_function_select(task: TriggerTask):
    """卡牌功能选择页面: 量子晶种预测选创造，小丑任务随机选任务（战斗相关页面，优先级高于战斗页面）。"""
    title = find_box_at_point(task, 0.499, 0.131)
    if not (title and "请选择功能" in title.name):
        return False
    task_positions = [(0.115, 0.286), (0.349, 0.289), (0.588, 0.290), (0.827, 0.287)]
    task_boxes = [find_box_at_point(task, x, y) for x, y in task_positions]
    if all(b and "任务" in b.name for b in task_boxes):
        chosen = random.choice(task_boxes)
        task.log_info(f"检测到小丑任务选择卡牌发动，随机选择一项任务")
        task.click_box(chosen)
        task.sleep(4)
        return True
    p1 = find_box_at_point(task, 0.214, 0.289)
    p2 = find_box_at_point(task, 0.470, 0.292)
    p3 = find_box_at_point(task, 0.722, 0.286)
    if p1 and p2 and p3 and "创造" in p1.name and "创造" in p2.name and "创造" in p3.name:
        task.log_info("检测到量子晶种预测卡牌页面，点击创造")
        _move_and_click(task, 0.722, 0.286)
        task.sleep(4)
        return True
    cards = recognize_cards(task, page="卡牌功能选择页面")
    if cards:
        chosen = random.choice(cards)
        task.log_info(
            f"卡牌功能选择兜底: 随机点击卡牌「{chosen['name']}」，"
            f"类型「{chosen['type'] or chosen['feature_type']}」"
        )
        _move_and_click(task, chosen["x"], chosen["y"])
        task.sleep(4)
        return True
    return False


def handle_return_to_draw_pile(task: TriggerTask):
    """选择手牌放回抽牌堆页面: 从左往右选择第一张（战斗相关页面，优先级高于战斗页面）。"""
    box = find_box_at_point(task, 0.484, 0.111)
    if not (box and re.search(r"请选择.*要移动至抽牌堆.*", box.name)):
        return False
    task.log_info("检测到选择手牌放回抽牌堆页面，从左往右选择第一张")
    cards = sorted(
        [b for b in task.all_texts
         if 0.116 <= (b.x + b.width / 2) / task.width <= 0.859
         and 0.697 <= (b.y + b.height / 2) / task.height <= 0.908
         and len(b.name.strip()) > 1
         and b.name not in ["确认", "返回", "跳过"]],
        key=lambda b: b.x
    )
    if not cards:
        task.log_info("未找到手牌")
        return False
    chosen = cards[0]
    task.log_info(f"返回抽牌堆页面触发选卡事件，点击「{chosen.name}」")
    task.click_box(chosen)
    task.sleep(1)
    # _move_and_click(task, 0.934, 0.883)
    # task.sleep(1)
    return True





def handle_rest_sortie(task: TriggerTask):
    """出击模式休息页面: 包含休息和闪光两个功能，检测到对应条件分别处理。"""
    # 检测闪光区域 (0.788,0.463)-(0.870,0.594) 是否存在“闪光”和不大于30的数字
    flash_x1, flash_y1, flash_x2, flash_y2 = 0.788, 0.463, 0.870, 0.594
    has_flash_text = False
    flash_cost = None
    flash_box = None
    for b in task.all_texts:
        cx = (b.x + b.width / 2) / task.width
        cy = (b.y + b.height / 2) / task.height
        if flash_x1 <= cx <= flash_x2 and flash_y1 <= cy <= flash_y2:
            if "闪光" in b.name:
                has_flash_text = True
                flash_box = b
            costs = [int(number) for number in re.findall(r"\d+", b.name) if int(number) <= 30]
            if costs and flash_cost is None:
                flash_cost = costs[0]

    flash_feature = task.find_one(
        feature_name="flash_in_sortie_safezoom",
        box=task.box_of_screen(0.702, 0.347, 0.963, 0.713),
    )
    if flash_feature:
        task.log_info(
            f"检测到flash_in_sortie_safezoom特征，匹配置信度: "
            f"{flash_feature.confidence:.2%}"
        )

    if flash_feature and has_flash_text and flash_cost is not None and flash_box and hasattr(task, 'node_status') and task.node_status.get('flash_or_rest', False):
        task.log_info("休息区存在可闪光选项")

        # 获取当前信用点
        credit = _get_current_credit(task)
        task.log_info(f"当前信用点: {credit}")

        # 获取当前生命值百分比，识别失败时维持原有的满生命值兜底
        hp_percent = _get_current_hp_percent(task)
        if hp_percent is False:
            hp_percent = 100

        flash_threshold_str = _get_config_value(task, '生命值大于多少优先闪光(百分比)', "60")
        try:
            flash_threshold = int(flash_threshold_str)
        except (ValueError, TypeError):
            flash_threshold = 60
        task.log_info(f"生命值={hp_percent}%, 阈值={flash_threshold}%, 信用点={credit}")
        if credit > flash_cost and hp_percent >= flash_threshold:
            task.log_info("满足闪光条件，点击闪光")
            task.click_box(flash_box)
            if not _wait_for_rest_confirm(task):
                return True
            task.node_status['flash_or_rest'] = False
            return True
        else:
            task.log_info("不满足闪光条件，继续检测休息")

    rest_feature = _find_rest_feature(task)
    free_text = _get_region_text(task, (0.154, 0.602, 0.359, 0.847))
    if (rest_feature and "免费" in free_text and hasattr(task, 'node_status')
            and task.node_status.get('flash_or_rest', False)):
        task.log_info("检测到休息界面，点击休息")
        task.click_box(rest_feature)
        if not _wait_for_rest_confirm(task):
            return True
        task.node_status['flash_or_rest'] = False
        return True

    if rest_feature and "免费" not in free_text:
        task.log_info("检测到rest特征，但休息区域未找到「免费」，跳过点击休息")

    # 检测是否需要进入德朗商店
    shop_box = find_box_at_point(task, 0.360, 0.138)
    if shop_box and "德朗商店" in shop_box.name and hasattr(task, 'node_status') and task.node_status.get('shop', False):
        task.log_info("检测到德朗商店，且 node_status['shop']=True，进入商店")
        task.click_box(shop_box)
        task.sleep(2)
        return True
    return False


# 出击模式 PAGE_HANDLERS
PAGE_HANDLERS = [
    handle_auto_stop,
    settle_equipment_pending, #装备页点了安装/购买后离开那一页才写装备账（要先于逃脱判断，不拦截）
    handle_speedrun_exit, #速刷：第二层首领选完回到路线页就退出（先于选路）
    handle_route_selection,
    # handle_stage_clear,
    log_credit,
    log_node_status,
    handle_stuck_log,
    handle_close_page, #点击屏幕关闭页面，优先于其他普通页面处理

    handle_sortie_lobby, #出击入口页：调难度、理智用完就停（先于 handle_enter）
    handle_rational_supply, #补充理性：按开关确认或放弃（先于中间确认按钮）
    handle_ether_supply,
    handle_refine_equipment_credit, #提炼装备信用点页面，优先于确认按钮
    handle_center_confirm,
    handle_archive_target_member, #信息统计页面，避免出击模式卡住
    handle_equipment, #装备选择
    handle_card_assign,
    handle_confirm, #确认按钮
    handle_convert, #转换按钮
    handle_shop, #德朗商店
    handle_rest_sortie, #休息/商店入口
    handle_close_button, #关闭按钮
    handle_remove, #移除按钮
    handle_three_choice_card_remove, #三选一卡牌移除页面（低优先级兜底）
    handle_flash, #闪光按钮
    handle_reflash, #重新闪光按钮
    handle_grant_flash, #赋予闪光按钮
    handle_copy, #复制按钮
    handle_leave, #离开按钮
    handle_expedition_result, #探险结果页面，优先级高于下一步
    handle_next_step, #下一步按钮
    handle_select, #选择按钮

    handle_equipment_recast, #装备重铸按钮

    handle_non_battle_page,
    handle_battle_crash,
    handle_discard_hand_card,
    handle_battle_hand_select,
    handle_curiosity_activate,
    handle_extra_card_use,
    handle_card_function_select,
    handle_return_to_draw_pile,
    handle_weakness_info,
    handle_battle_page,
    handle_settlement,
    handle_destiny_choice,
    handle_main_member_flash,
    handle_boss_selection,
    handle_get_card,
    handle_card_reward,
    handle_draw_card_event,
    # handle_equipment,
    # handle_mask_card,
    handle_select_card,
    handle_copy_member,
    handle_convert_card,
    handle_negotiation,
    handle_sortie_reward_settlement,
    handle_sortie_reward_claim,
    handle_continue,
    handle_battle_member_selection,
    handle_member_selection,
    handle_battle_member_config,
    handle_enter,
    handle_obtain_reward,
    handle_view_original,
    handle_skip,
    handle_event_task,
    handle_weakness_info,
    handle_minimizemap,
    handle_held_cards_page,
    handle_escape,
    handle_dialogue,  #剧情对白：开启一次自动对话，之后按空格推进（最低优先级）
]
