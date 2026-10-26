from ok import TriggerTask

import difflib
import json
import re
import random
import time
from types import SimpleNamespace
import sys
import cv2
import os
import numpy as np
from opencc import OpenCC

import chaos_strategy
import chaos_trace
import game_db

_jp2t = OpenCC('jp2t')  # 日文新字体转繁体
_t2s = OpenCC('t2s')  # 繁体转简体

def _normalize_text(text):
    """先将日文汉字字形转繁体，再统一转换为简体。"""
    return _t2s.convert(_jp2t.convert(text))


def _edit_distance(s1, s2, max_dist=1):
    """计算两个字符串的编辑距离是否 <= max_dist。"""
    if abs(len(s1) - len(s2)) > max_dist:
        return False
    if not s1 or not s2:
        return max(len(s1), len(s2)) <= max_dist
    m, n = len(s1), len(s2)
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        curr = [i] + [0] * n
        for j in range(1, n + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[n] <= max_dist


def is_subsequence(first: str, second: str) -> bool:
    """判断第一个字符串是否为第二个字符串的子序列。"""
    second_iter = iter(second)
    return all(char in second_iter for char in first)


def _move_and_click(task: TriggerTask, x, y):
    """先将鼠标移动到目标位置，等待界面响应后再点击。"""
    page_handler = sys._getframe(1).f_code.co_name
    task.log_info(
        f"页面处理「{page_handler}」触发点击事件，点击目标坐标=({x:.3f}, {y:.3f})"
    )
    task.move_relative(x, y)
    task.sleep(0.5)
    task.click(x, y)


def _simplify_texts(texts):
    """将OCR结果按 jp2t → t2s 批量转换为简体（原地修改）。"""
    for b in texts:
        b.name = _normalize_text(b.name)
    return texts


def _get_config_value(task: TriggerTask, key, default):
    """读取运行时配置，优先从 task.config 读取，其次 default_config，最后使用默认值。返回前将字符串转简体。
    卡厄思选了玩法（探索度/刷存档）时，玩法推出来的配置项（task.chaos_overrides）优先。"""
    overrides = getattr(task, 'chaos_overrides', None)
    if overrides and key in overrides:
        value = overrides[key]
    elif hasattr(task, 'config') and key in task.config:
        value = task.config[key]
    else:
        value = getattr(task, 'default_config', {}).get(key, default)
    if isinstance(value, str):
        value = _normalize_text(value).strip()
    elif isinstance(value, (list, tuple)):
        value = [
            _normalize_text(v).strip() if isinstance(v, str) else v
            for v in value
        ]
    return value


def _get_card_list(task: TriggerTask, key):
    """读取列表配置，解析失败返回空列表。"""
    value = _get_config_value(task, key, [])
    return list(value) if isinstance(value, (list, tuple)) else []


def _get_card_reward_priority(task: TriggerTask):
    """读取卡牌奖励优先级，并将刷初始卡牌配置置于最高优先级。"""
    priority = _get_card_list(task, "卡牌奖励优先级")
    initial_card_name = _get_config_value(task, "刷初始卡牌", "")
    initial_card_name = initial_card_name.strip() if isinstance(initial_card_name, str) else ""
    if initial_card_name:
        priority = [
            initial_card_name,
            *(name for name in priority if name != initial_card_name),
        ]
    return priority


# 游戏语言 → 映射文件路径
_GAME_LANG_FILE_MAP = {
    "繁体中文": os.path.join(os.path.dirname(__file__), 'assets', 'game_text_map', 'zh_tw.py'),
}
# 已加载的映射缓存 {语言: SERVER_TEXT_MAP字典}
_LOADED_MAPS = {}


def _load_game_text_map(game_lang):
    """加载指定语言的映射表（带缓存）。"""
    if game_lang not in _LOADED_MAPS:
        file_path = _GAME_LANG_FILE_MAP.get(game_lang)
        if file_path and os.path.exists(file_path):
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(f"_game_map_{game_lang}", file_path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                _LOADED_MAPS[game_lang] = getattr(mod, 'SERVER_TEXT_MAP', {})
            except Exception:
                _LOADED_MAPS[game_lang] = {}
        else:
            _LOADED_MAPS[game_lang] = {}
    return _LOADED_MAPS[game_lang]


def _get_game_language(task: TriggerTask):
    """获取当前模式配置的游戏语言。"""
    try:
        return str(task.config.get('游戏语言', '简体中文')).strip() or '简体中文'
    except Exception:
        return '简体中文'


def _get_game_text(task: TriggerTask, default_text):
    """根据当前模式配置的游戏语言，返回对应服务器版本的搜索文本。"""
    game_lang = _get_game_language(task)

    if game_lang == '简体中文':
        return default_text

    mapping = _load_game_text_map(game_lang)
    return mapping.get(default_text, default_text)


def _migrate_route_boss_to_elite(task: TriggerTask):
    """迁移用户配置中"路线优先级"的"boss"为"精英"（兼容旧配置）。"""
    try:
        if hasattr(task, 'config') and '路线优先级' in task.config:
            priority = task.config['路线优先级']
            if isinstance(priority, (list, tuple)):
                new_priority = ["精英" if v == "boss" else v for v in priority]
                if new_priority != list(priority):
                    task.config['路线优先级'] = new_priority
                    from ok.gui.Communicate import communicate
                    communicate.task_list_updated.emit()
                    task.log_info(f"迁移路线优先级配置: boss→精英 {new_priority}")
    except Exception:
        pass


def _get_route_priority(task: TriggerTask):
    """读取路线节点优先级配置，返回列表；解析失败使用默认顺序。"""
    value = _get_config_value(task, '路线优先级', ["休息", "事件", "小怪", "精英"])
    value = list(value) if isinstance(value, (list, tuple)) else ["休息", "事件", "小怪", "精英"]
    ns = getattr(task, 'node_status', None)
    if (_get_config_value(task, OCTOPUS_RUSH, False) is True and isinstance(ns, dict)
            and ns.get('pass_final_boss_count', 0) == 0 and "小怪" in value):
        # 章鱼哥速刷第一层：普通战 > 精英 > 其他（没整层路线时的兜底）
        value = [v for v in ("小怪", "精英") if v in value] + [v for v in value if v not in ("小怪", "精英")]
    return value


# ------------------------- 通用工具 -------------------------

def _get_current_credit(task: TriggerTask):
    """读取当前信用点数，从两个可能位置取最大值。"""
    credit = 0
    for pos_x, pos_y in [(0.794, 0.054), (0.734, 0.053)]:
        box = find_box_at_point(task, pos_x, pos_y)
        if box and box.name.isdigit():
            val = int(box.name)
            if val > credit:
                credit = val
    return credit


def _neutral_card_limit(task: TriggerTask):
    """卡厄思模式每局最多允许在商店购买3张中立牌。"""
    return 3 if task.name == "自动卡厄思模式" else None


def _neutral_card_limit_reached(task: TriggerTask):
    """判断本局获得的中立牌是否已达到固定上限。"""
    limit = _neutral_card_limit(task)
    if limit is None:
        return False
    acquired = getattr(task, "node_status", {}).get("neutral_card_count", 0)
    return acquired >= limit or not _pt_room(task, "中立卡")


def _record_removed_cards(task: TriggerTask, count=1):
    """记录本局实际完成移除的卡牌数量。"""
    node_status = getattr(task, "node_status", None)
    if not isinstance(node_status, dict):
        return
    count = max(1, int(count))
    node_status["removed_card_count"] = (
        node_status.get("removed_card_count", 0) + count
    )
    task.log_info(
        f"本局移除卡牌数量增加{count}，"
        f"当前共{node_status['removed_card_count']}张"
    )


def _record_neutral_card(task: TriggerTask):
    """记录本局实际获得一张中立牌。"""
    node_status = getattr(task, "node_status", None)
    if not isinstance(node_status, dict):
        return
    node_status["neutral_card_count"] = (
        node_status.get("neutral_card_count", 0) + 1
    )
    task.log_info(
        f"本局获得中立牌数量增加1，"
        f"当前共{node_status['neutral_card_count']}张"
    )


def _parse_discounted_price(price_text):
    """解析可能将折扣前后价格连在一起的 OCR 数字。"""
    price_text = price_text.strip()
    if not re.fullmatch(r"\d+", price_text):
        return None
    if len(price_text) == 6:
        return int(price_text[-3:])
    if len(price_text) in (4, 5):
        return int(price_text[-2:])
    return int(price_text)


def _get_current_hp_percent(task: TriggerTask):
    """读取当前生命值百分比，无法识别时返回 False。"""
    hp_box = find_box_at_point(task, 0.209, 0.040)
    if not hp_box:
        return False
    hp_match = re.search(r'(\d+)/(\d+)', hp_box.name)
    if not hp_match:
        return False
    current_hp = int(hp_match.group(1))
    max_hp = int(hp_match.group(2))
    if max_hp <= 0:
        return False
    hp_percent = int(current_hp * 100 / max_hp)
    task.log_info(f"当前生命值: {current_hp}/{max_hp} = {hp_percent}%")
    return hp_percent


def find_box_at_point(task: TriggerTask, rel_x, rel_y):
    """查找包含相对坐标点的 box，多个命中时返回面积最小的（最精确）。"""
    px, py = rel_x * task.width, rel_y * task.height
    hits = [b for b in task.all_texts
            if b.x <= px <= b.x + b.width and b.y <= py <= b.y + b.height]
    return min(hits, key=lambda b: b.area()) if hits else None


def find_target_card(task: TriggerTask):
    """查找target卡牌特征，返回特征框列表及其对应的相对点击位置。"""
    search_box = task.box_of_screen(0.090, 0.179, 0.927, 0.342)
    target_boxes = task.find_feature(feature_name="target", box=search_box) or []
    click_positions = []
    for target_box in target_boxes:
        center_x = (target_box.x + target_box.width / 2) / task.width
        center_y = (target_box.y + target_box.height / 2) / task.height
        click_positions.append((
            min(1.0, max(0.0, center_x - 0.0975)),
            min(1.0, max(0.0, center_y + 0.2460)),
        ))
    return target_boxes, click_positions


def _recognize_cards_by_features(
    task: TriggerTask,
    region,
    page,
    feature_types,
    min_feature_distance,
    name_offsets,
    type_offsets,
    description_offsets,
    name_only_feature_thresholds=None,
    allow_empty_type_threshold=None,
):
    """按指定特征和相对位置识别卡牌。"""
    search_box = task.box_of_screen(*region)
    feature_candidates = []
    for feature_name, feature_type in feature_types.items():
        feature_boxes = task.find_feature(
            feature_name=feature_name,
            box=search_box,
            threshold=0.65,
        ) or []
        for feature_box in feature_boxes:
            feature_candidates.append((feature_name, feature_type, feature_box))

    def feature_distance(first, second):
        first_x = (first.x + first.width / 2) / task.width
        first_y = (first.y + first.height / 2) / task.height
        second_x = (second.x + second.width / 2) / task.width
        second_y = (second.y + second.height / 2) / task.height
        return (
            (first_x - second_x) ** 2 + (first_y - second_y) ** 2
        ) ** 0.5

    filtered_features = []
    for candidate in sorted(
        feature_candidates,
        key=lambda item: item[2].confidence,
        reverse=True,
    ):
        if any(
            feature_distance(candidate[2], kept[2]) < min_feature_distance
            for kept in filtered_features
        ):
            continue
        filtered_features.append(candidate)

    cards = []
    log_prefix = f"{page}: " if page else ""
    for feature_name, feature_type, feature_box in filtered_features:
        center_x = (feature_box.x + feature_box.width / 2) / task.width
        center_y = (feature_box.y + feature_box.height / 2) / task.height
        name_region = (
            max(0.0, center_x + name_offsets[0]),
            max(0.0, center_y + name_offsets[1]),
            min(1.0, center_x + name_offsets[2]),
            min(1.0, center_y + name_offsets[3]),
        )
        type_region = (
            max(0.0, center_x + type_offsets[0]),
            max(0.0, center_y + type_offsets[1]),
            min(1.0, center_x + type_offsets[2]),
            min(1.0, center_y + type_offsets[3]),
        )
        desc_region = (
            max(0.0, center_x + description_offsets[0]),
            max(0.0, center_y + description_offsets[1]),
            min(1.0, center_x + description_offsets[2]),
            min(1.0, center_y + description_offsets[3]),
        )
        card_name = _get_region_text(task, name_region).strip()
        task.log_info(
            f"{log_prefix}卡牌识别调试: 特征={feature_name}，"
            f"特征中心=({center_x:.4f},{center_y:.4f})，"
            f"特征置信度={feature_box.confidence:.4f}，"
            f"名称区域={tuple(round(value, 4) for value in name_region)}，"
            f"名称OCR={_region_text_debug_info(task, name_region)}，"
            f"类型区域={tuple(round(value, 4) for value in type_region)}，"
            f"类型OCR={_region_text_debug_info(task, type_region)}，"
            f"描述区域={tuple(round(value, 4) for value in desc_region)}"
        )
        if not card_name:
            task.log_info(f"{log_prefix}卡牌识别调试: 因名称为空排除该特征")
            continue
        card_type = _get_region_text(task, type_region).strip()
        description = _get_region_text(task, desc_region)
        name_only_threshold = (name_only_feature_thresholds or {}).get(
            feature_name
        )
        allow_name_only = (
            name_only_threshold is not None
            and feature_box.confidence > name_only_threshold
        )
        allow_empty_type = (
            allow_empty_type_threshold is not None
            and feature_box.confidence > allow_empty_type_threshold
        )
        if not allow_name_only and (
            not description or (not card_type and not allow_empty_type)
        ):
            task.log_info(
                f"{log_prefix}卡牌识别调试: 因类型或描述缺失排除该特征，"
                f"类型=「{card_type}」，描述=「{description}」"
            )
            continue
        cards.append({
            "name": card_name,
            "type": card_type,
            "description": description,
            "feature_name": feature_name,
            "feature_type": feature_type,
            "confidence": feature_box.confidence,
            "feature_box": feature_box,
            "x": (name_region[0] + name_region[2]) / 2,
            "y": (name_region[1] + name_region[3]) / 2,
            "name_region": name_region,
            "type_region": type_region,
            "description_region": desc_region,
        })
    cards.sort(key=lambda card: card["feature_box"].x)
    if cards:
        task.log_info(f"{log_prefix}卡牌识别到{len(cards)}张卡牌")
        for index, card in enumerate(cards, 1):
            task.log_info(
                f"{log_prefix}卡牌{index}: 名称=「{card['name']}」，"
                f"类型=「{card['type'] or card['feature_type']}」，"
                f"描述=「{card['description']}」，"
                f"特征={card['feature_name']}，置信度={card['confidence']:.4f}"
            )
    return cards


def recognize_cards(
    task: TriggerTask,
    region=(0.021, 0.172, 0.988, 0.432),
    page="",
):
    """识别卡牌选择页面中的卡牌。"""
    return _recognize_cards_by_features(
        task=task,
        region=region,
        page=page,
        feature_types={
            "attack": "攻击/基础攻击",
            "skill": "技能/基础技能",
            "enhance": "强化",
            "hex": "咒术",
            "abnormal": "状态异常",
        },
        min_feature_distance=(
            (0.618 - 0.454) ** 2 + (0.304 - 0.306) ** 2
        ) ** 0.5,
        name_offsets=(-0.0150, -0.0635, 0.1450, -0.0175),
        type_offsets=(0.0120, -0.0205, 0.1090, 0.0245),
        description_offsets=(-0.0565, 0.1190, 0.1495, 0.4900),
    )


def recognize_cards_in_deck(
    task: TriggerTask,
    region=(0.274, 0.108, 0.929, 0.874),
    page="",
):
    """识别卡组区域中的卡牌，并标记金色边框选中的卡牌。"""
    cards = _recognize_cards_by_features(
        task=task,
        region=region,
        page=page,
        feature_types={
            "attack_in_deck": "攻击/基础攻击",
            "skill_in_deck": "技能/基础技能",
            "enhance_in_deck": "强化",
            "hex_in_deck": "咒术",
            "hex_in_deck_tw": "诅咒",
        },
        min_feature_distance=(
            (0.464 - 0.326) ** 2 + (0.175 - 0.175) ** 2
        ) ** 0.5,
        name_offsets=(-0.0090, -0.0435, 0.0900, -0.0105),
        type_offsets=(0.0070, -0.0175, 0.0880, 0.0175),
        description_offsets=(-0.0370, 0.0515, 0.1000, 0.3295),
        name_only_feature_thresholds={
            "hex_in_deck": 0.90,
            "hex_in_deck_tw": 0.90,
        },
        allow_empty_type_threshold=0.90,
    )
    _mark_selected_card_by_gold_border(task, cards, page=page)
    return cards


# 不是事件选项的文字：装备/选卡页左下角的卡组统计「独特卡牌平均费用 0.9」、存档收集页的存档价值「4368 TB」
# 会被事件图标特征误命中（2026-10-24 实录）
NOT_EVENT_PAGE = re.compile(r"保存战斗数据|存储数据收集|决定闪光效果|长按卡牌以查看信息")
NOT_EVENT_OPTION = re.compile(r"平均费用|^\W*\w?\s*[\d,]{3,}\s*TB\W*$")


def recognize_event_options(
    task: TriggerTask,
    region=(0.198, 0.840, 0.803, 1.000),
    page="",
):
    """按事件选项特征识别最多三个事件描述。"""
    event_region = task.box_of_screen(*region)
    event_features = []
    for feature_name in ("event1", "event2", "event3", "event4", "event5", "event6", "event7", "event8", "event9"):
        for feature_box in task.find_feature(
            feature_name=feature_name,
            box=event_region,
            threshold=0.70,
        ) or []:
            center_x = (feature_box.x + feature_box.width / 2) / task.width
            center_y = (feature_box.y + feature_box.height / 2) / task.height
            event_features.append(
                (feature_name, feature_box, center_x, center_y)
            )

    filtered_features = []
    for candidate in sorted(
        event_features,
        key=lambda item: item[1].confidence,
        reverse=True,
    ):
        if any(
            (
                (candidate[2] - kept[2]) ** 2
                + (candidate[3] - kept[3]) ** 2
            ) ** 0.5 < 0.207
            for kept in filtered_features
        ):
            continue
        filtered_features.append(candidate)
        if len(filtered_features) >= 3:
            break

    filtered_features.sort(key=lambda item: item[2])
    event_options = []
    for feature_name, feature_box, center_x, center_y in filtered_features:
        description_region = (
            max(0.0, center_x - 0.119),
            max(0.0, center_y - 0.208),
            min(1.0, center_x + 0.122),
            min(1.0, center_y - 0.021),
        )
        description = _get_region_text(task, description_region).strip()
        if not description or NOT_EVENT_OPTION.search(description):
            continue
        event_options.append({
            "x": center_x,
            "y": center_y,
            "description": description,
            "description_region": description_region,
            "feature_name": feature_name,
            "confidence": feature_box.confidence,
        })

    if event_options:
        prefix = f"{page}: " if page else ""
        task.log_info(f"{prefix}识别到{len(event_options)}个事件选项")
        for index, event_option in enumerate(event_options, 1):
            task.log_info(
                f"{prefix}事件选项{index}: 描述=「{event_option['description']}」，"
                f"特征={event_option['feature_name']}，"
                f"置信度={event_option['confidence']:.4f}"
            )
    return event_options


def recognize_map_connections(
    task: TriggerTask,
    region=(0.019, 0.633, 0.380, 0.972),
    feature_threshold=0.85,
    line_threshold=0.30,
    special_feature_threshold=0.65,
):
    """识别小地图节点，并根据节点之间亮线的连续覆盖率生成连通关系。"""
    if task.frame is None:
        task.log_info("小地图连通关系识别失败：当前画面为空")
        return {"nodes": [], "connections": [], "adjacency": {}}

    node_types = {
        "position_in_map": "当前位置",
        "settlement_in_map": "结算",
        "enemy_in_map": "小怪",
        "safezoom_in_map": "休息",
        "elite_in_map": "精英",
        "event_in_map": "事件",
    }
    # 值大于0表示优先进入，小于0表示降低进入优先级；后续新增标志只需
    # 在这里登记，不需要改动识别和绑定逻辑。
    special_feature_priorities = {
        "kalei_in_map": 1,
        "shop_in_map": 1,
        "seal_in_map": 1,
        "hard_in_map": -1,
    }
    search_box = task.box_of_screen(*region)
    candidates = []
    for feature_name, node_type in node_types.items():
        for feature_box in task.find_feature(
            feature_name=feature_name,
            box=search_box,
            threshold=feature_threshold,
        ) or []:
            center_x = (feature_box.x + feature_box.width / 2) / task.width
            center_y = (feature_box.y + feature_box.height / 2) / task.height
            # 当前位置是水滴形图标，线路实际连接点在图标下方尖端而非中心。
            if feature_name == "position_in_map":
                center_y += (feature_box.height / task.height) * 0.36
            candidates.append({
                "feature_name": feature_name,
                "type": node_type,
                "x": center_x,
                "y": center_y,
                "confidence": float(feature_box.confidence),
                "feature_box": feature_box,
            })

    position_candidates = [
        candidate for candidate in candidates
        if candidate["feature_name"] == "position_in_map"
    ]
    position_x = None
    passed_feature_x_limit = None
    if position_candidates:
        position_x = max(
            position_candidates,
            key=lambda item: item["confidence"],
        )["x"]
        passed_feature_x_limit = position_x + 0.027
        original_candidate_count = len(candidates)
        candidates = [
            candidate for candidate in candidates
            if candidate["feature_name"] == "position_in_map"
            or candidate["x"] >= passed_feature_x_limit
        ]
        task.log_info(
            f"小地图当前位置X={position_x:.4f}，过滤X小于"
            f"{passed_feature_x_limit:.4f}的已走过节点，"
            f"排除{original_candidate_count - len(candidates)}个普通节点特征"
        )

    # 同一节点可能被多个普通节点模板命中。按给定的两个参考点
    # (0.229, 0.674)、(0.257, 0.674)之间的距离去重，只保留最高置信度。
    feature_dedup_distance = (
        (0.257 - 0.229) ** 2 + (0.674 - 0.674) ** 2
    ) ** 0.5
    nodes = []
    for candidate in sorted(
        candidates,
        key=lambda item: item["confidence"],
        reverse=True,
    ):
        if any(
            (
                (candidate["x"] - kept["x"]) ** 2
                + (candidate["y"] - kept["y"]) ** 2
            ) ** 0.5 < feature_dedup_distance
            for kept in nodes
        ):
            continue
        nodes.append(candidate)
    # 小地图的推进方向是从左到右。先按横坐标聚类成列，再在每列内
    # 从上到下排序，保证节点编号与实际可选顺序一致。
    columns = []
    for node in sorted(nodes, key=lambda item: item["x"]):
        column = next(
            (
                existing
                for existing in columns
                if abs(node["x"] - existing["center_x"]) < 0.025
            ),
            None,
        )
        if column is None:
            columns.append({"center_x": node["x"], "nodes": [node]})
            continue
        column["nodes"].append(node)
        column["center_x"] = sum(
            item["x"] for item in column["nodes"]
        ) / len(column["nodes"])

    nodes = []
    for column_index, column in enumerate(columns):
        column_nodes = sorted(column["nodes"], key=lambda item: item["y"])
        for row_index, node in enumerate(column_nodes, start=1):
            node["column"] = column_index
            node["row"] = row_index
            node["id"] = len(nodes)
            node["special_features"] = []
            node["special_priority"] = 0
            nodes.append(node)

    # 每个特殊标志只绑定到距离最近的一个节点。节点可以同时具有多个标志。
    special_features = []
    for feature_name, priority in special_feature_priorities.items():
        for feature_box in task.find_feature(
            feature_name=feature_name,
            box=search_box,
            threshold=special_feature_threshold,
        ) or []:
            special_feature = {
                "feature_name": feature_name,
                "priority": priority,
                "x": (feature_box.x + feature_box.width / 2) / task.width,
                "y": (feature_box.y + feature_box.height / 2) / task.height,
                "confidence": float(feature_box.confidence),
                "feature_box": feature_box,
            }
            if (
                passed_feature_x_limit is not None
                and special_feature["x"] < passed_feature_x_limit
            ):
                task.log_info(
                    f"小地图特殊标志{feature_name}位于已走过区域，"
                    f"X={special_feature['x']:.4f}，排除"
                )
                continue
            special_features.append(special_feature)
    filtered_special_features = []
    for special_feature in sorted(
        special_features,
        key=lambda item: item["confidence"],
        reverse=True,
    ):
        if any(
            (
                (special_feature["x"] - kept["x"]) ** 2
                + (special_feature["y"] - kept["y"]) ** 2
            ) ** 0.5 < feature_dedup_distance
            for kept in filtered_special_features
        ):
            continue
        filtered_special_features.append(special_feature)
    special_features = filtered_special_features
    for special_feature in special_features:
        nearest_node = min(
            nodes,
            key=lambda node: (
                (node["x"] - special_feature["x"]) ** 2
                + (node["y"] - special_feature["y"]) ** 2
            ),
            default=None,
        )
        if nearest_node is None:
            continue
        distance = (
            (nearest_node["x"] - special_feature["x"]) ** 2
            + (nearest_node["y"] - special_feature["y"]) ** 2
        ) ** 0.5
        if distance > 0.035:
            continue
        special_feature["node_id"] = nearest_node["id"]
        nearest_node["special_features"].append(special_feature)
        nearest_node["special_priority"] += special_feature["priority"]

    gray = cv2.cvtColor(task.frame[:, :, :3], cv2.COLOR_BGR2GRAY)
    frame_height, frame_width = gray.shape[:2]
    perpendicular_radius = max(2, round(frame_height * 0.004))

    def line_brightness_ratio(first, second):
        start_x = first["x"] * frame_width
        start_y = first["y"] * frame_height
        end_x = second["x"] * frame_width
        end_y = second["y"] * frame_height
        delta_x = end_x - start_x
        delta_y = end_y - start_y
        pixel_distance = (delta_x ** 2 + delta_y ** 2) ** 0.5
        if pixel_distance <= 0:
            return 0.0
        perpendicular_x = -delta_y / pixel_distance
        perpendicular_y = delta_x / pixel_distance
        sample_count = max(8, round(pixel_distance * 0.40))
        bright_samples = 0
        for progress in np.linspace(0.30, 0.70, sample_count):
            sample_x = start_x + delta_x * progress
            sample_y = start_y + delta_y * progress
            band_values = []
            for offset in range(-perpendicular_radius, perpendicular_radius + 1):
                pixel_x = int(round(sample_x + perpendicular_x * offset))
                pixel_y = int(round(sample_y + perpendicular_y * offset))
                if 0 <= pixel_x < frame_width and 0 <= pixel_y < frame_height:
                    band_values.append(gray[pixel_y, pixel_x])
            if band_values and max(band_values) >= 110:
                bright_samples += 1
        return bright_samples / sample_count

    connections = []
    adjacency = {node["id"]: [] for node in nodes}

    def has_intermediate_node(first, second):
        vector_x = second["x"] - first["x"]
        vector_y = second["y"] - first["y"]
        vector_length_squared = vector_x ** 2 + vector_y ** 2
        if vector_length_squared <= 0:
            return False
        for other in nodes:
            if other is first or other is second:
                continue
            progress = (
                (other["x"] - first["x"]) * vector_x
                + (other["y"] - first["y"]) * vector_y
            ) / vector_length_squared
            if not 0.12 < progress < 0.88:
                continue
            projected_x = first["x"] + vector_x * progress
            projected_y = first["y"] + vector_y * progress
            if (
                (other["x"] - projected_x) ** 2
                + (other["y"] - projected_y) ** 2
            ) ** 0.5 < 0.025:
                return True
        return False

    def has_intermediate_special_feature(first, second):
        """判断候选连线是否穿过属于第三个节点的特殊标志。"""
        vector_x = second["x"] - first["x"]
        vector_y = second["y"] - first["y"]
        vector_length_squared = vector_x ** 2 + vector_y ** 2
        if vector_length_squared <= 0:
            return False
        endpoint_ids = {first["id"], second["id"]}
        for special_feature in special_features:
            if special_feature.get("node_id") in endpoint_ids:
                continue
            progress = (
                (special_feature["x"] - first["x"]) * vector_x
                + (special_feature["y"] - first["y"]) * vector_y
            ) / vector_length_squared
            if not 0.12 < progress < 0.88:
                continue
            projected_x = first["x"] + vector_x * progress
            projected_y = first["y"] + vector_y * progress
            if (
                (special_feature["x"] - projected_x) ** 2
                + (special_feature["y"] - projected_y) ** 2
            ) ** 0.5 < 0.015:
                return True
        return False

    for first_index, first in enumerate(nodes):
        for second in nodes[first_index + 1:]:
            # 只保留当前列指向右侧相邻列的边，不生成反向邻接关系。
            if second["column"] != first["column"] + 1:
                continue
            delta_x = abs(first["x"] - second["x"])
            delta_y = abs(first["y"] - second["y"])
            distance = (delta_x ** 2 + delta_y ** 2) ** 0.5
            if not 0.035 <= distance <= 0.210 or delta_x > 0.125:
                continue
            # 地图连线为横线或斜线；不同排的同列节点不直接相连。
            if delta_y > 0.025 and delta_x < 0.025:
                continue
            if has_intermediate_node(first, second):
                continue
            if has_intermediate_special_feature(first, second):
                continue
            brightness_ratio = line_brightness_ratio(first, second)
            if brightness_ratio < line_threshold:
                continue
            connection = {
                "from": first["id"],
                "to": second["id"],
                "brightness_ratio": brightness_ratio,
            }
            connections.append(connection)
            adjacency[first["id"]].append(second["id"])

    task.log_info(f"小地图识别到{len(nodes)}个节点、{len(connections)}条亮线连接")
    for node in nodes:
        task.log_info(
            f"小地图节点{node['id']}: 类型={node['type']}，"
            f"第{node['column'] + 1}列第{node['row']}个，"
            f"位置=({node['x']:.4f}, {node['y']:.4f})，"
            f"特征={node['feature_name']}，置信度={node['confidence']:.4f}，"
            f"特殊标志={[item['feature_name'] for item in node['special_features']]}，"
            f"特殊优先级={node['special_priority']}"
        )
    for connection in connections:
        task.log_info(
            f"小地图连接: 节点{connection['from']} -> 节点{connection['to']}，"
            f"亮线覆盖率={connection['brightness_ratio']:.2%}"
        )
    task.log_info(f"小地图有向邻接关系: {adjacency}")
    return {
        "nodes": nodes,
        "connections": connections,
        "adjacency": adjacency,
    }


def find_best_map_route(map_info, target_node_type):
    """寻找目标类型节点最多的有向路线，并返回下一列应选择的节点。"""
    nodes = map_info.get("nodes", [])
    adjacency = map_info.get("adjacency", {})
    node_by_id = {node["id"]: node for node in nodes}
    current_node = next(
        (node for node in nodes if node["type"] == "当前位置"),
        None,
    )
    if current_node is None:
        return {
            "target_type": target_node_type,
            "target_count": 0,
            "special_priority_score": 0,
            "route": [],
            "next_node_id": None,
            "next_row": None,
        }

    route_cache = {}

    def best_route_from(node_id):
        if node_id in route_cache:
            return route_cache[node_id]
        node = node_by_id[node_id]
        is_target = node["type"] == target_node_type
        own_score = int(is_target)
        own_special_score = node.get("special_priority", 0) if is_target else 0
        next_node_ids = adjacency.get(node_id, [])
        if not next_node_ids:
            result = (own_score, own_special_score, [node_id])
            route_cache[node_id] = result
            return result

        candidates = []
        for next_node_id in next_node_ids:
            child_score, child_special_score, child_route = best_route_from(
                next_node_id
            )
            candidates.append((
                own_score + child_score,
                own_special_score + child_special_score,
                node_by_id[next_node_id]["row"],
                [node_id, *child_route],
            ))
        # 先比较目标节点数量，再比较目标节点携带的特殊优先级；仍相同时
        # 选择下一节点更靠上的路线。
        best_score, best_special_score, _, best_route = min(
            candidates,
            key=lambda item: (-item[0], -item[1], item[2]),
        )
        result = (best_score, best_special_score, best_route)
        route_cache[node_id] = result
        return result

    target_count, special_priority_score, route = best_route_from(
        current_node["id"]
    )
    next_node = node_by_id[route[1]] if len(route) > 1 else None
    return {
        "target_type": target_node_type,
        "target_count": target_count,
        "special_priority_score": special_priority_score,
        "route": route,
        "next_node_id": next_node["id"] if next_node else None,
        "next_row": next_node["row"] if next_node else None,
    }


def find_best_map_route_by_priority(map_info, node_type_priority, weights=None):
    """按节点类型加权计算最优路线（整条路径求和），并返回下一列应选择的节点。

    weights 给了就用它（卡厄思玩法的权重表：{"types": {类型: 分}, "shop": 商店加分, "special": {特征: 分}}），
    否则按 node_type_priority 的名次换算。
    """
    weights = weights or {}
    nodes = map_info.get("nodes", [])
    adjacency = map_info.get("adjacency", {})
    node_by_id = {node["id"]: node for node in nodes}
    current_node = next(
        (node for node in nodes if node["type"] == "当前位置"),
        None,
    )
    if current_node is None:
        return None

    route_cache = {}
    priority_weights = weights.get("types") or {
        node_type: len(node_type_priority) - index
        for index, node_type in enumerate(node_type_priority)
    }
    highest_priority_weight = max(priority_weights.values(), default=1)
    shop_bonus = weights.get("shop", highest_priority_weight * 2)
    special_weights = weights.get("special", {})

    def best_route_from(node_id):
        if node_id in route_cache:
            return route_cache[node_id]
        node = node_by_id[node_id]
        own_counts = tuple(
            int(node["type"] == node_type)
            for node_type in node_type_priority
        )
        own_shop_count = int(any(
            item["feature_name"] == "shop_in_map"
            for item in node.get("special_features", [])
        ))
        own_special_score = sum(
            special_weights.get(item["feature_name"], item["priority"])
            for item in node.get("special_features", [])
            if item["feature_name"] != "shop_in_map"
        )
        own_weighted_score = (
            priority_weights.get(node["type"], 0)
            + own_shop_count * shop_bonus
            + own_special_score
        )
        next_node_ids = adjacency.get(node_id, [])
        if not next_node_ids:
            result = (
                own_weighted_score,
                own_shop_count,
                own_counts,
                own_special_score,
                [node_id],
            )
            route_cache[node_id] = result
            return result

        candidates = []
        for next_node_id in next_node_ids:
            (
                child_weighted_score,
                child_shop_count,
                child_counts,
                child_special_score,
                child_route,
            ) = best_route_from(next_node_id)
            total_counts = tuple(
                own + child
                for own, child in zip(own_counts, child_counts)
            )
            candidates.append((
                own_weighted_score + child_weighted_score,
                own_shop_count + child_shop_count,
                total_counts,
                own_special_score + child_special_score,
                node_by_id[next_node_id]["row"],
                [node_id, *child_route],
            ))
        (
            best_weighted_score,
            best_shop_count,
            best_counts,
            best_special_score,
            _,
            best_route,
        ) = min(
            candidates,
            key=lambda item: (
                -item[0],
                -item[1],
                tuple(-count for count in item[2]),
                -item[3],
                item[4],
            ),
        )
        result = (
            best_weighted_score,
            best_shop_count,
            best_counts,
            best_special_score,
            best_route,
        )
        route_cache[node_id] = result
        return result

    (
        weighted_score,
        shop_count,
        type_counts,
        special_priority_score,
        route,
    ) = best_route_from(current_node["id"])
    next_node = node_by_id[route[1]] if len(route) > 1 else None
    return {
        "priority": list(node_type_priority),
        "priority_weights": priority_weights,
        "shop_bonus": shop_bonus,
        "weighted_score": weighted_score,
        "shop_count": shop_count,
        "type_counts": dict(zip(node_type_priority, type_counts)),
        "special_priority_score": special_priority_score,
        "route": route,
        "next_node_id": next_node["id"] if next_node else None,
        "next_row": next_node["row"] if next_node else None,
        "next_node_type": next_node["type"] if next_node else None,
        "next_special_features": [
            item["feature_name"]
            for item in next_node.get("special_features", [])
        ] if next_node else [],
    }


def _mark_selected_card_by_gold_border(
    task: TriggerTask,
    cards,
    page="",
    threshold=0.25,
):
    """计算卡牌的金黄色边框得分，并在卡牌信息中写入选中状态。"""
    for card in cards:
        card["selected"] = False
        card["gold_border_score"] = 0.0
        card["gold_border_edges"] = {}
    if not cards or task.frame is None:
        return

    frame = task.frame[:, :, :3]
    frame_height, frame_width = frame.shape[:2]
    band_x = max(2, round(frame_width * 0.004))
    band_y = max(2, round(frame_height * 0.006))

    def gold_ratio(left, top, right, bottom):
        left = max(0, min(frame_width, round(left)))
        right = max(0, min(frame_width, round(right)))
        top = max(0, min(frame_height, round(top)))
        bottom = max(0, min(frame_height, round(bottom)))
        if right <= left or bottom <= top:
            return 0.0
        hsv = cv2.cvtColor(frame[top:bottom, left:right], cv2.COLOR_BGR2HSV)
        gold_mask = cv2.inRange(
            hsv,
            np.array((8, 100, 160), dtype=np.uint8),
            np.array((38, 255, 255), dtype=np.uint8),
        )
        return float(cv2.countNonZero(gold_mask)) / gold_mask.size

    scored_cards = []
    for card in cards:
        feature_box = card["feature_box"]
        center_x = feature_box.x + feature_box.width / 2
        center_y = feature_box.y + feature_box.height / 2
        card_left = center_x - frame_width * 0.047
        card_right = center_x + frame_width * 0.103
        card_top = center_y - frame_height * 0.061
        card_bottom = center_y + frame_height * 0.330

        edge_scores = {
            "上": gold_ratio(
                card_left, card_top - band_y, card_right, card_top + band_y
            ),
            "下": gold_ratio(
                card_left, card_bottom - band_y, card_right, card_bottom + band_y
            ),
            "左": gold_ratio(
                card_left - band_x, card_top, card_left + band_x, card_bottom
            ),
            "右": gold_ratio(
                card_right - band_x, card_top, card_right + band_x, card_bottom
            ),
        }
        visible_edge_scores = [
            edge_scores["左"],
            edge_scores["右"],
        ]
        score = sum(visible_edge_scores) / len(visible_edge_scores)
        strong_edge_count = sum(value >= 0.08 for value in visible_edge_scores)
        card["gold_border_score"] = score
        card["gold_border_edges"] = edge_scores
        scored_cards.append((score, strong_edge_count, card))

    prefix = f"{page}: " if page else ""
    for score, strong_edge_count, card in scored_cards:
        if score >= threshold and strong_edge_count == 2:
            card["selected"] = True

    for card in cards:
        edge_scores = card["gold_border_edges"]
        task.log_info(
            f"{prefix}卡牌「{card['name']}」是否选中={card['selected']}，"
            f"金色边框得分={card['gold_border_score']:.4f}，"
            f"上={edge_scores['上']:.4f}，下={edge_scores['下']:.4f}，"
            f"左={edge_scores['左']:.4f}，右={edge_scores['右']:.4f}"
        )

    if not any(card["selected"] for card in cards):
        task.log_info(f"{prefix}未检测到选中卡牌的金色边框")


def find_text(task: TriggerTask, pattern):
    """按正则在所有识别文本中查找第一个匹配的 box。"""
    return next((b for b in task.all_texts if re.search(pattern, b.name)), None)


def _clean_match(name, target):
    """去除OCR文本中的非中文/字母/数字符号后比较是否等于 target。"""
    cleaned = re.sub(r'[^\u4e00-\u9fff\w]', '', name)
    return cleaned == target


def _get_region_text(task: TriggerTask, region):
    """获取指定区域内所有OCR文本，去除空白后用"".join拼接返回。"""
    x1, y1, x2, y2 = region
    texts = [
        b.name.strip() for b in task.all_texts
        if x1 <= (b.x + b.width / 2) / task.width <= x2
        and y1 <= (b.y + b.height / 2) / task.height <= y2
        and b.name.strip()
    ]
    return "".join(texts)


def _region_text_debug_info(task: TriggerTask, region):
    """返回参与区域文本拼接的OCR框信息，用于排查相对区域偏移。"""
    x1, y1, x2, y2 = region
    matched = []
    for box in task.all_texts:
        center_x = (box.x + box.width / 2) / task.width
        center_y = (box.y + box.height / 2) / task.height
        if x1 <= center_x <= x2 and y1 <= center_y <= y2 and box.name.strip():
            matched.append(
                f"「{box.name.strip()}」"
                f"(中心={center_x:.4f},{center_y:.4f},"
                f"置信度={box.confidence:.4f})"
            )
    return "，".join(matched) if matched else "无"


_CARD_TYPE_KEYWORDS = {
    "攻击", "强化", "技能", "技", "咒术", "诅咒",
    "攻", "击", "基础", "基本", "状态", "异常",
}


def _card_has_type_below(task: TriggerTask, box):
    """判断文本框下方是否有卡牌类型标签（卡牌名特征）。"""
    box_bottom_y = (box.y + box.height) / task.height
    box_cx = (box.x + box.width / 2) / task.width
    for b in task.all_texts:
        cx = (b.x + b.width / 2) / task.width
        cy = (b.y + b.height / 2) / task.height
        dy = cy - box_bottom_y
        dx = abs(cx - box_cx)
        if -0.005 <= dy <= 0.040 and dx <= 0.045 and len(b.name) <= 4:
            for kw in _CARD_TYPE_KEYWORDS:
                if kw in b.name:
                    return True
    return False


def region_white_ratio(task: TriggerTask, region):
    """计算指定区域内白色像素占比。"""
    if task.frame is None:
        return 1.0
    region_box = task.box_of_screen(*region)
    pixels = task.frame[
        region_box.y:region_box.y + region_box.height,
        region_box.x:region_box.x + region_box.width,
        :3,
    ]
    if pixels.size == 0:
        return 1.0
    channel_min = pixels.min(axis=2)
    channel_max = pixels.max(axis=2)
    white_mask = (channel_min >= 240) & ((channel_max - channel_min) <= 15)
    return float(np.count_nonzero(white_mask)) / white_mask.size


def _point_is_white(task: TriggerTask, x, y, page):
    """判断指定点是否为选牌页面滚动条使用的白色。"""
    pixel_x = min(task.width - 1, max(0, round(x * task.width)))
    pixel_y = min(task.height - 1, max(0, round(y * task.height)))
    blue, green, red = (
        int(value) for value in task.frame[pixel_y, pixel_x, :3]
    )
    is_white = min(blue, green, red) >= 240 and (
        max(blue, green, red) - min(blue, green, red)
    ) <= 15
    task.log_info(
        f"{page}: 点({x:.3f}, {y:.3f})颜色="
        f"B{blue}/G{green}/R{red}，是否白色={is_white}"
    )
    return is_white


def _scroll_card_page(task: TriggerTask, x, y, amount, page, distance=0.25):
    """将鼠标移到选牌区域后滚动。"""
    direction = "向下" if amount < 0 else "向上"
    if task.is_adb():
        to_y = max(0.05, y - distance) if amount < 0 else min(0.95, y + distance)
        task.log_info(
            f"{page}: ADB从({x:.3f}, {y:.3f})滑动到({x:.3f}, {to_y:.3f})，"
            f"{direction}浏览卡牌"
        )
        task.swipe_relative(x, y, x, to_y, duration=1, settle_time=1)
        task.sleep(1)
    else:
        task.log_info(f"{page}: 在({x:.3f}, {y:.3f}){direction}滚动")
        task.move_relative(x, y)
        task.sleep(0.05)
        task.scroll_relative(x, y, amount)
        task.sleep(0.5)


CARD_PAGE_DUMP_DIR = os.path.join("dev_out", "card_pages")


def _dump_card_page(task: TriggerTask, tag):
    """开发样本：选卡页/闪光三选一页存一张截图（dev_out/card_pages，最多 40 张），用来做游戏「推荐图钉」的识别。"""
    try:
        if not os.path.isdir("dev_out"):
            return
        os.makedirs(CARD_PAGE_DUMP_DIR, exist_ok=True)
        if len(os.listdir(CARD_PAGE_DUMP_DIR)) >= 40 or task.frame is None:
            return
        cv2.imwrite(os.path.join(CARD_PAGE_DUMP_DIR, f"{time.strftime('%H%M%S')}_{tag}.png"), task.frame)
    except Exception as e:  # 只是采样本，失败不影响流程
        task.log_debug(f"存选卡页截图失败: {e}")


_CARD_PIN_TEMPLATE = None
CARD_PIN_OFFSET = (0.097, -0.053)    # 图钉中心相对卡牌类型图标中心（卡牌识别的 x/y）


def find_card_pins(frame):
    """游戏按预设构筑在该选的卡右上角标的橙色图钉（删卡/闪光/复制选卡页）。返回 [(相对x, 相对y)]。
    2026-10-24 实机：模板分 0.76～1.0，图钉处橙色占比约 0.72，没图钉的卡角是 0。"""
    global _CARD_PIN_TEMPLATE
    if _CARD_PIN_TEMPLATE is None:
        _CARD_PIN_TEMPLATE = cv2.imread(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                     "assets", "chaos_map", "ref_card_pin.png"))
    if frame is None or _CARD_PIN_TEMPLATE is None:
        return []
    h, w = frame.shape[:2]
    img = frame[:, :, :3] if (w, h) == (1920, 1080) else cv2.resize(frame[:, :, :3], (1920, 1080))
    res = cv2.matchTemplate(img, _CARD_PIN_TEMPLATE, cv2.TM_CCOEFF_NORMED)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    pins = []
    ys, xs = np.where(res > 0.6)
    for x, y in sorted(zip(xs, ys), key=lambda p: -res[p[1], p[0]]):
        cx, cy = int(x) + 16, int(y) + 16
        if any(abs(cx - px) < 24 and abs(cy - py) < 24 for px, py in pins):
            continue
        p = hsv[cy - 12:cy + 12, cx - 12:cx + 12]
        if ((p[..., 0] < 20) & (p[..., 1] > 150) & (p[..., 2] > 200)).mean() < 0.4:
            continue
        pins.append((cx, cy))
    return [(x / 1920, y / 1080) for x, y in pins]


def card_has_pin(card, pins):
    px, py = card["x"] + CARD_PIN_OFFSET[0], card["y"] + CARD_PIN_OFFSET[1]
    return any(abs(px - x) < 0.035 and abs(py - y) < 0.035 for x, y in pins)


def _trace_card_click(task, action, card, cards, reason):
    chaos_trace.step(task, "card", f"{action or '选卡'}：{card['name']}", task.frame, reason=reason,
                     chosen=card["name"], cards=[c["name"] for c in cards])


def select_card(task: TriggerTask, card_names, count=1, action=""):
    """使用卡组特征识别选择卡牌，支持滚动查找、基础牌移除和兜底选择。"""
    selected = 0
    max_scrolls = 20
    page = f"select_card-{action}" if action else "select_card"
    prefer_remove_base = (
        action == "移除"
        and _get_config_value(task, "优先移除基础牌", True)
    )
    prefer_target_member_row = (
        action == "移除"
        and _get_config_value(task, "刷空档", False) is True
    )
    base_card_type = _get_game_text(task, "基础")
    target_member_box = task.box_of_screen(0.079, 0.092, 0.209, 0.675)
    flash_priority = (
        _get_card_list(task, "闪光优先级")
        if action in ("闪光", "灵光")
        else []
    )

    def record_pending_removal():
        if action == "移除":
            task._pending_removed_card_count = (
                getattr(task, "_pending_removed_card_count", 0) + 1
            )

    def filter_flash_priority_cards(cards):
        """闪光时排除已命中闪光优先级的卡牌，避免重复选择。"""
        if not flash_priority:
            return cards

        filtered_cards = []
        for card in cards:
            combined_text = f"{card['name']}：:{card['description']}"
            matched_keyword = next(
                (
                    keyword.strip()
                    for keyword in flash_priority
                    if isinstance(keyword, str)
                    and keyword.strip()
                    and is_subsequence(keyword.strip(), combined_text)
                ),
                None,
            )
            if matched_keyword:
                task.log_info(
                    f"{page}: 卡牌「{card['name']}」的名称和描述命中"
                    f"闪光优先级「{matched_keyword}」，排除该卡牌"
                )
                continue
            filtered_cards.append(card)
        return filtered_cards

    def refresh_cards():
        task.all_texts = _simplify_texts(task.ocr())
        cards = recognize_cards_in_deck(task, page=page)
        return filter_flash_priority_cards(cards)

    def click_cards(cards, predicate, reason):
        nonlocal selected
        clicked = False
        for card in cards:
            if selected >= count:
                break
            if card["selected"] or not predicate(card):
                continue
            task.log_info(f"{page}: {reason}「{card['name']}」")
            _trace_card_click(task, action, card, cards, reason)
            _move_and_click(task, card["x"], card["y"])
            task.sleep(0.3)
            card["selected"] = True
            selected += 1
            record_pending_removal()
            clicked = True
        return clicked

    chaos_mode = getattr(task, "chaos_mode", chaos_strategy.MODE_LEGACY)
    # 空存不要闪光，图钉只在删卡时用
    # 目标卡组的闪光由 handle_select_card 按「闪错/未闪对」排好候选，图钉不管卡闪没闪对，不用
    use_pins = action != "重新闪光" and not (chaos_mode == chaos_strategy.MODE_TARGET and action in ("闪光", "灵光")) and (chaos_mode in (chaos_strategy.MODE_TARGET, chaos_strategy.MODE_EXPLORE) or (
        chaos_mode == chaos_strategy.MODE_EMPTY and action == "移除"))

    def click_priority_cards(cards):
        nonlocal selected
        clicked = False
        if use_pins and selected < count:
            # 游戏按预设标了图钉的卡最优先（用户 2026-10-24）
            pins = find_card_pins(task.frame)
            if pins and click_cards(cards, lambda card: card_has_pin(card, pins), "游戏推荐图钉，点击"):
                clicked = True
        for target in card_names:
            if selected >= count:
                break
            target = target.strip() if isinstance(target, str) else ""
            if not target:
                continue
            for card in cards:
                if selected >= count:
                    break
                if card["selected"]:
                    continue
                card_name = card["name"].strip()
                if target not in card_name and card_name not in target and not _ocr_name_matches(chaos_strategy.base_card_name(card_name), target) \
                        and not _ocr_desc_matches(chaos_strategy.base_card_name(card_name), card.get("description", ""), target):
                    continue
                task.log_info(
                    f"{page}: 命中优先级「{target}」，点击目标卡牌「{card['name']}」"
                )
                _trace_card_click(task, action, card, cards, f"命中优先级「{target}」")
                _move_and_click(task, card["x"], card["y"])
                task.sleep(0.3)
                card["selected"] = True
                selected += 1
                record_pending_removal()
                clicked = True
        return clicked

    def click_target_member_row_cards(cards):
        """刷空档时优先移除目标主战员同一排的卡牌。"""
        if not prefer_target_member_row or selected >= count:
            return False
        if not task.feature_exists("target_member_in_select_card"):
            return False
        target_member = task.find_one(
            feature_name="target_member_in_select_card",
            box=target_member_box,
            threshold=0.6,
        )
        if not target_member:
            return False
        target_y = (
            target_member.y + target_member.height / 2
        ) / task.height
        task.log_info(
            f"{page}: 刷空档找到目标主战员，相似度="
            f"{target_member.confidence:.4f}，中心Y={target_y:.4f}"
        )
        return click_cards(
            cards,
            lambda card: abs(card["y"] - target_y) <= 0.25,
            "刷空档优先移除目标主战员同排卡牌，点击",
        )

    def sync_visible_selected(cards):
        nonlocal selected
        if selected == 0:
            selected = min(count, sum(card["selected"] for card in cards))

    def find_action_button():
        if not action:
            return None
        action_text = _get_game_text(task, action)
        return next(
            (
                box for box in task.all_texts
                if 0.495 <= (box.x + box.width / 2) / task.width <= 0.997
                and 0.878 <= (box.y + box.height / 2) / task.height <= 1.001
                and action_text in box.name
            ),
            None,
        )

    cards = refresh_cards()
    _dump_card_page(task, f"select_{action or 'card'}")
    if not cards:
        if find_action_button():
            task.log_info(
                f"{page}: 首次识别卡牌漏识别，但仍存在「{action}」按钮，"
                "继续执行选卡流程"
            )
        else:
            task.log_info(f"{page}: 未识别到任何卡牌或操作按钮，终止选卡")
            return False
    sync_visible_selected(cards)
    scrollbar_white_ratio = region_white_ratio(
        task, (0.976, 0.119, 0.988, 0.858)
    )
    single_page = scrollbar_white_ratio < 0.01
    task.log_info(
        f"{page}: 滚动条区域白色像素占比={scrollbar_white_ratio:.2%}，"
        f"是否仅一页卡牌={single_page}"
    )

    down_scrolls = 0
    while True:
        click_target_member_row_cards(cards)
        if selected >= count:
            task.log_info(f"{page}: 已选中{selected}/{count}张卡牌")
            return True
        click_priority_cards(cards)
        if selected >= count:
            task.log_info(f"{page}: 已选中{selected}/{count}张卡牌")
            return True

        if single_page:
            task.log_info(f"{page}: 当前仅一页卡牌，不执行向下滚动")
            break

        if _point_is_white(task, 0.982, 0.846, page):
            task.log_info(f"{page}: 检测到已到达卡牌底部")
            break

        if down_scrolls >= max_scrolls:
            task.log_info(f"{page}: 向下滚动已达到{max_scrolls}次限制")
            break

        _scroll_card_page(task, 0.251, 0.735, -3, page)
        down_scrolls += 1
        cards = refresh_cards()
        if not cards:
            if find_action_button():
                task.log_info(
                    f"{page}: 向下滚动后卡牌漏识别，但仍存在「{action}」按钮，"
                    "继续向下滚动"
                )
                continue
            task.log_info(f"{page}: 向下滚动后未识别到卡牌或操作按钮，终止选卡")
            return False

    if action == "移除" and selected < count:
        bottom_to_top_cards = sorted(
            cards,
            key=lambda card: (card["y"], card["x"]),
            reverse=True,
        )
        click_cards(
            bottom_to_top_cards,
            lambda card: card["feature_name"] in {
                "hex_in_deck",
                "hex_in_deck_tw",
            },
            "底部页面优先移除咒术卡牌，点击",
        )
        if selected >= count:
            return True

    if prefer_remove_base and selected < count:
        bottom_to_top_cards = sorted(
            cards,
            key=lambda card: (card["y"], card["x"]),
            reverse=True,
        )
        click_cards(
            bottom_to_top_cards,
            lambda card: base_card_type in card["type"],
            "底部页面优先移除基础牌，点击",
        )
        if selected >= count:
            return True

        up_scrolls = 0
        while not single_page:
            if _point_is_white(task, 0.982, 0.128, page):
                task.log_info(f"{page}: 检测到已到达卡牌顶部")
                break

            if up_scrolls >= max_scrolls:
                task.log_info(f"{page}: 向上滚动已达到{max_scrolls}次限制")
                break

            _scroll_card_page(task, 0.252, 0.179, 3, page)
            up_scrolls += 1
            cards = refresh_cards()
            if not cards:
                if find_action_button():
                    task.log_info(
                        f"{page}: 向上滚动后卡牌漏识别，但仍存在「{action}」按钮，"
                        "继续向上滚动"
                    )
                    continue
                task.log_info(f"{page}: 向上滚动后未识别到卡牌或操作按钮，终止选卡")
                return False
            click_target_member_row_cards(cards)
            if selected >= count:
                task.log_info(f"{page}: 已选中{selected}/{count}张卡牌")
                return True
            bottom_to_top_cards = sorted(
                cards,
                key=lambda card: (card["y"], card["x"]),
                reverse=True,
            )
            click_cards(
                bottom_to_top_cards,
                lambda card: base_card_type in card["type"],
                "向上翻页找到基础牌，点击",
            )
            if selected >= count:
                return True

    task.all_texts = _simplify_texts(task.ocr())
    action_box = task.box_of_screen(0.424, 0.882, 1.000, 0.999)
    for button_name in ("跳过", "取消"):
        button = next(
            (
                box for box in task.all_texts
                if action_box.x <= box.x + box.width / 2 <= action_box.x + action_box.width
                and action_box.y <= box.y + box.height / 2 <= action_box.y + action_box.height
                and button_name in box.name
            ),
            None,
        )
        if button:
            task.log_info(f"{page}: 未找到足够卡牌，点击「{button_name}」")
            task.click_box(button)
            if action == "移除":
                task._pending_removed_card_count = 0
            return True

    cards = recognize_cards_in_deck(task, page=f"{page}-兜底")
    cards = filter_flash_priority_cards(cards)
    fallback_cards = sorted(
        cards,
        key=lambda card: (card["y"], card["x"]),
        reverse=True,
    )
    click_cards(fallback_cards, lambda card: True, "兜底补选卡牌，点击")
    task.log_info(f"{page}: 兜底处理完成，已选中{selected}/{count}张卡牌")
    return True


def calculate_dominant_hue(task: TriggerTask, region):
    """计算区域的主导色相，返回色相值(0-179)，无有效色相返回-1。"""
    box = task.box_of_screen(*region)
    frame = task.frame[box.y:box.y + box.height, box.x:box.x + box.width, :3]
    hue, sat, val = cv2.split(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV))

    valid_hue = hue[(sat > 30) & (val > 30)]
    if len(valid_hue) == 0:
        return -1

    hist = cv2.calcHist([valid_hue.astype(np.float32)], [0], None, [180], [0, 180])
    return int(np.argmax(hist))


def is_button_active(task: TriggerTask, button_box):
    """判断按钮是否处于可点击状态（激活状态）。

    参数:
        task: TriggerTask实例
        button_box: 按钮文本的Box对象（像素坐标）

    返回:
        bool: True表示按钮可点击（激活），False表示不可点击（未激活/灰色）
    """
    # 计算左侧检测区域（按钮图标/背景区域）
    # 根据用户提供的例子推算比例：
    # 按钮box: (0.898, 0.908, 0.941, 0.950) w=0.043, h=0.042
    # 左侧区域: (0.866, 0.912, 0.895, 0.947) w=0.029, h=0.035
    # 左侧区域宽度 = 按钮宽度 * 0.67，x = 按钮x - 左侧区域宽度 * 1.1
    # 左侧区域高度 = 按钮高度 * 0.83，y = 按钮y + 按钮高度 * 0.1

    left_width = int(button_box.width * 0.67)
    left_height = int(button_box.height * 0.83)
    left_x = button_box.x - int(left_width * 1.1)
    left_y = button_box.y + int(button_box.height * 0.1)

    # 确保区域在屏幕内
    if left_x < 0:
        left_x = 0
    if left_y < 0:
        left_y = 0
    if left_x + left_width > task.width:
        left_width = task.width - left_x
    if left_y + left_height > task.height:
        left_height = task.height - left_y

    if left_width <= 0 or left_height <= 0:
        task.log_info(f"按钮左侧区域无效: ({left_x}, {left_y}, {left_width}, {left_height})")
        return False

    # 提取区域图像
    region_img = task.frame[left_y:left_y + left_height, left_x:left_x + left_width, :3]
    if region_img.size == 0:
        task.log_info("按钮左侧区域图像为空")
        return False

    # 计算平均BGR颜色
    avg_color = cv2.mean(region_img)[:3]  # B, G, R 平均值
    avg_b, avg_g, avg_r = avg_color

    # 判断是否接近禁用灰色 (195,195,195)
    # 容错范围：每个通道在190-200之间，且三个通道值接近
    # target_gray = 195
    tolerance = 5  # 允许±5的误差

    # 计算范围边界
    lower_bound = 120 #target_gray - tolerance  # 190
    upper_bound = 200 #target_gray + tolerance  # 200

    # 检查每个通道是否在目标范围内
    in_range = (
        lower_bound <= avg_b <= upper_bound and
        lower_bound <= avg_g <= upper_bound and
        lower_bound <= avg_r <= upper_bound
    )

    # 检查三个通道是否接近（最大差异小）
    max_diff = max(abs(avg_b - avg_g), abs(avg_g - avg_r), abs(avg_r - avg_b))
    is_close = max_diff < tolerance

    # 如果是接近(195,195,195)的灰色，按钮不可点击
    is_disabled_gray = in_range and is_close

    task.log_info(f"按钮左侧区域颜色: B={avg_b:.1f}, G={avg_g:.1f}, R={avg_r:.1f}, "
                  f"是否禁用灰色={is_disabled_gray} (范围{lower_bound}-{upper_bound}, 最大差异={max_diff:.1f})")

    # 如果是禁用灰色，按钮不可点击；否则可点击
    return not is_disabled_gray


# def group_dialog_columns(task: TriggerTask, region, max_width_ratio=0.25, align_tolerance=0.04):
#     """把区域内文本框按左边缘聚成对话框列。"""
#     x1, y1, x2, y2 = region
#     boxes = [
#         box for box in task.all_texts
#         if x1 <= (box.x + box.width / 2) / task.width <= x2
#         and y1 <= (box.y + box.height / 2) / task.height <= y2
#         and box.width / task.width <= max_width_ratio
#         and len(box.name) > 2
#     ]
#     columns = []
#     for box in sorted(boxes, key=lambda item: item.x):
#         left = box.x / task.width
#         center_x = (box.x + box.width / 2) / task.width
#         if columns and left - columns[-1]["left"] <= align_tolerance:
#             columns[-1]["centers"].append(center_x)
#             columns[-1]["texts"].append(box.name)
#         else:
#             columns.append({"left": left, "centers": [center_x], "texts": [box.name]})
#     return [
#         {"x": sum(column["centers"]) / len(column["centers"]), "texts": column["texts"]}
#         for column in columns
#     ]


# ------------------------- 帧卡住检测 -------------------------

def is_frame_stuck(task: TriggerTask, stuck_threshold_seconds=30, change_threshold=0.08):
    """
    基于像素变化检测画面是否卡住。
    在 task 上缓存 _prev_frame_gray 和 _last_change_time。
    连续 stuck_threshold_seconds 秒变化比例低于 change_threshold 返回 True。
    stuck_threshold_seconds: 判定卡住的连续秒数阈值，默认30秒
    change_threshold: 两帧之间变化像素比例阈值，默认0.08（8%）
    """
    if not hasattr(task, '_last_change_time'):
        task._last_change_time = time.time()
        task._prev_frame_gray = None

    frame = task.frame
    if frame is None:
        return False
    # 前面的页面处理函数一直命中时这里不会被调用；隔了很久才调用就不能拿旧时间算卡住
    # （2026-10-25 存档清理连续翻页 3 分多钟，回来一看「画面卡住 210 秒」，差点触发重开游戏）
    now = time.time()
    if now - getattr(task, '_last_stuck_check', now) > 15:
        task._last_change_time = now
        task._prev_frame_gray = None
    task._last_stuck_check = now

    # 缩放灰度图以减少计算量
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (w // 4, h // 4))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    if task._prev_frame_gray is not None and gray.shape == task._prev_frame_gray.shape:
        diff = cv2.absdiff(gray, task._prev_frame_gray)
        _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
        change_ratio = cv2.countNonZero(thresh) / (gray.shape[0] * gray.shape[1])

        if change_ratio >= change_threshold:
            task._last_change_time = time.time()

    task._prev_frame_gray = gray

    return time.time() - task._last_change_time >= stuck_threshold_seconds


STUCK_STOP_SECONDS = 300
GAME_RESTART_MAX = 3


def handle_stuck_log(task: TriggerTask):
    """画面卡住超过10秒时依次处理关闭页、特殊怪物、卡牌或未知页面。"""
    if not is_frame_stuck(task, stuck_threshold_seconds=10):
        return False

    stuck_seconds = int(time.time() - task._last_change_time)
    if stuck_seconds >= STUCK_STOP_SECONDS and getattr(task, "chaos_mode", chaos_strategy.MODE_LEGACY) != chaos_strategy.MODE_LEGACY:
        # 画面几分钟纹丝不动、点什么都没反应（2026-10-25 实录：兑换战利品后游戏 UI 锁死），自动重开游戏（用户同意）；
        # 本次运行重开过 GAME_RESTART_MAX 次还卡就停下来等人看
        chaos_trace.step(task, "page", "画面长时间不变", task.frame)
        restarts = getattr(task, "game_restarts", 0)
        if restarts < GAME_RESTART_MAX:
            import game_restart
            task.game_restarts = restarts + 1
            ok = game_restart.restart_game(task, f"画面 {stuck_seconds} 秒没有变化")
            task._last_change_time = time.time()
            if ok:
                task.entry_checked = False      # 交回 ChaosMode：主页就重新进卡厄思，局内就读回 PT 账
                return True
        task.log_info(f"画面已经 {stuck_seconds} 秒没有任何变化，自动重开 {restarts} 次后仍不行，停止任务", notify=True)
        task.disable()
        return True
    close_page = task.find_one(
        feature_name="close_page",
        box=task.box_of_screen(0.921, 0.003, 0.998, 0.100),
    )
    if close_page:
        task.log_info(
            f"画面卡住已持续{stuck_seconds}秒，检测到close_page特征，点击关闭页面"
        )
        task.click_box(close_page)
        task.sleep(1)
        return True

    from utils_sortie import handle_secret_enemy
    handle_secret_enemy(task)
    cards = recognize_cards(task, page="画面卡住兜底")
    if cards and getattr(task, "chaos_mode", chaos_strategy.MODE_LEGACY) != chaos_strategy.MODE_LEGACY:
        # 玩法模式不随机拿卡：中立卡每张占 20PT。2026-10-25 第十一局训练后的「请选择卡牌奖励」卡住，
        # 这里随机点了「全力以赴」「压制」，再被训练的「确认」发给罗丝薇瑟，存档多出 60PT
        skip = find_text_in_region(task, r"跳过", (0.6, 0.85, 1, 1))
        if skip:
            task.log_info("画面卡住兜底: 玩法模式不随机拿卡，点「跳过」")
            task.click_box(skip)
            task.sleep(1)
        else:
            task.log_info("画面卡住兜底: 玩法模式不随机拿卡，也没有「跳过」，按未知页面处理")
            handle_unknown_page(task)
    elif cards:
        chosen_card = random.choice(cards)
        task.log_info(
            f"画面卡住兜底: 随机点击卡牌「{chosen_card['name']}」"
        )
        _move_and_click(task, chosen_card["x"], chosen_card["y"])
    else:
        handle_unknown_page(task)
    # 普通随机点屏幕兜底暂时停用。
    # click_x = random.uniform(0.059, 0.985)
    # click_y = random.uniform(0.129, 0.981)
    # _move_and_click(task, click_x, click_y)
    task.log_info(f"画面卡住，已持续{stuck_seconds}秒")
    return False


# ------------------------- 页面处理函数（通用） -------------------------
# 约定: 每个函数处理一种页面, 处理成功返回 True, 未命中返回 False。

def handle_auto_stop(task: TriggerTask):
    """自动停止功能: 如果配置"几轮后停止(0为不停止)"不为0，
    且 node_status 中的 total_rounds 达到配置轮数，则自动 disable 当前任务。"""
    stop_rounds = _get_config_value(task, '几轮后停止(0为不停止)', 0)
    if stop_rounds and stop_rounds != 0:
        ns = getattr(task, 'node_status', None)
        if ns and ns.get('total_rounds', 0) >= stop_rounds:
            task.log_info(f"已达到配置的停止轮数 {stop_rounds}，当前 total_rounds={ns['total_rounds']}，自动停止任务")
            task.disable()
            return True
    return False


def log_credit(task: TriggerTask):
    """记录当前信用点数量（仅记录, 不拦截后续处理）。"""
    credit = _get_current_credit(task)
    if credit > 0:
        task.info_set("当前信用点", f"{credit}")
    return False


# def handle_stage_clear(task: TriggerTask):
#     """成功通关页面: 检测(0.142,0.806)处文本是否包含'战斗结束'，成功次数+1。"""
#     box = find_box_at_point(task, 0.142, 0.806)
#     if box and "战斗结束" in box.name:
#         task.log_info("检测到成功通关页面，success_rounds + 1")
#         if hasattr(task, 'node_status'):
#             task.node_status['success_rounds'] += 1
#     return False


def log_node_status(task: TriggerTask):
    """记录当前胜率（仅记录, 不拦截后续处理）。"""
    ns = getattr(task, 'node_status', None)
    save_run_state(task)
    if ns:
        try:
            from src.config import version
            app_version = str(version).strip() or "dev"
        except Exception:
            app_version = "dev"
        task.info_set("版本号", app_version)
        task.info_set("游戏语言", _get_game_language(task))
        total = ns.get('total_rounds', 0)
        node_count = ns.get('node_count', 0)
        node_type = ns.get('node_type', "")
        task.info_set("所处层数，节点，类型", f"第{ns['pass_final_boss_count']+1}层，第{node_count}节点，{node_type}")
        task.info_set("是否到达关底boss", f"{ns['reach_final_boss']}")
        task.info_set("是否进入关底boss战斗", f"{ns['final_boss_battle']}")
        task.info_set("是否已逃脱", f"{ns['is_escaped']}")
        task.info_set(
            "是否已获得特定闪光",
            ns.get("get_specific_flash", False),
        )
        task.info_set(
            "获取刷存档主战员头像",
            ns.get("save_target_member", False),
        )
        task.info_set("本局已移除卡牌", ns.get("removed_card_count", 0))
        task.info_set("本局已获得中立牌", ns.get("neutral_card_count", 0))
        equipment = _equipment_state(task)
        equipment_names = [
            _current_equipment_for_slot(task, equipment, slot)[0]
            for slot in range(3)
        ]
        task.info_set(
            "装备信息",
            "，".join(
                f"{slot + 1}号位：{name or '空'}"
                for slot, name in enumerate(equipment_names)
            ),
        )
        meditation_state = _member_deck_state(task).get("冥想", {})
        if isinstance(meditation_state, dict):
            for card_name, pending in meditation_state.items():
                task.info_set(f"冥想：{card_name}", pending)
        if total > 0:
            task.info_set("当前胜率", f"{ns['success_rounds']}/{total} ({ns['success_rounds']*100//total}%)")
        else:
            task.info_set("当前胜率",f"{ns['success_rounds']}/{total} NaN")
        task.log_info("")
    return False


def handle_battle_crash(task: TriggerTask):
    """战斗信息错乱 / 点击重试: 点击屏幕中央恢复。"""
    if (find_text(task, r'出现错乱')
            or find_text(task, r'点击重试')
            or find_text(task, r'通讯不稳定.*重新尝试')):
        task.log_info("战斗信息出现错乱，点击恢复")
        _move_and_click(task, 0.5, 0.5)
        return True
    return False


def handle_close_page(task: TriggerTask):
    """提示"点击屏幕事件": 点击屏幕。"""
    box = find_text(task, _get_game_text(task, '点击屏幕'))
    if box:
        task.log_info("点击屏幕事件，点击屏幕")
        task.click_box(box)
        return True
    return False


def handle_refine_equipment_credit(task: TriggerTask):
    """提炼装备信用点页面：点击“以信用点接收”。"""
    box = find_box_at_point(task, 0.598, 0.635)
    receive_text = _get_game_text(task, "以信用点接收")
    if box and receive_text in box.name:
        task.log_info(f"检测到提炼装备信用点页面，点击{receive_text}")
        task.click_box(box)
        task.sleep(0.5)
        return True
    return False


# 中央确认弹窗里出现这些字就不点：花钱、重置零式升级、删邮件
_DANGEROUS_CONFIRM = re.compile(r"存储空间不足|超出存储数据的保留限制|确定要分解|分解数据后无法恢复|全部重置|重置所有|\d+元|充值|购买.*礼包|解锁额外数据|删除已读")


def handle_center_confirm(task: TriggerTask):
    """页面中央的"确认"按钮。"""
    confirm_region = (0.009, 0.168, 0.977, 0.875)
    box = next(
        (
            text_box
            for text_box in task.all_texts
            if _clean_match(text_box.name, "确认")
            and confirm_region[0]
            <= (text_box.x + text_box.width / 2) / task.width
            <= confirm_region[2]
            and confirm_region[1]
            <= (text_box.y + text_box.height / 2) / task.height
            <= confirm_region[3]
        ),
        None,
    )
    if box:
        danger = next((b.name for b in task.all_texts if _DANGEROUS_CONFIRM.search(b.name)), None)
        if danger:
            task.log_info(f"页面中央确认按钮所在弹窗含「{danger}」，属于危险操作，不点确认，交给专门的处理逻辑")
            return False
        task.log_info("检测到页面中央确认按钮，点击确认")
        task.click_box(box)
        task.sleep(1)
        return True
    return False


def handle_settlement(task: TriggerTask):
    """"结算"按钮。"""
    box = find_box_at_point(task, 0.941, 0.917)
    if box and _clean_match(box.name, "结算"):
        _move_and_click(task, 0.941, 0.917)
        if hasattr(task, 'node_status') and task.node_status.get('reach_final_boss', False):
            task.node_status['pass_final_boss_count'] += 1
            passed = task.node_status['pass_final_boss_count']
            task.log_info(f"检测到boss结算页面且 reach_final_boss=True，通关层数+1 (当前: {passed})")
            reset_layer_status(task)
        task.sleep(1)
        return True
    return False


AUTO_CHAT_THRESHOLD = 0.96


def _find_auto_chat(task: TriggerTask):
    task.next_frame()
    search_box = task.box_of_screen(0.655, 0.007, 0.996, 0.097)
    return task.find_one(feature_name=["autochatenable", "autochatenable2"], box=search_box)


def _ensure_auto_chat(task: TriggerTask, context=""):
    """自动对话按钮匹配置信度低于阈值就点一下开启。点完立刻再匹配：置信度反而降了说明原本就开着（2026-10-24 实机
    开着时只有 83%～95%，被 0.96 误判过），马上点回去，并把阈值降到这次的置信度以下，本次运行不再误点。返回是否点过。"""
    search_box = task.box_of_screen(0.655, 0.007, 0.996, 0.097)
    auto_chat = task.find_one(feature_name=["autochatenable", "autochatenable2"], box=search_box)
    threshold = getattr(task, "_auto_chat_threshold", AUTO_CHAT_THRESHOLD)
    if not auto_chat or auto_chat.confidence >= threshold:
        return False
    before = auto_chat.confidence
    task.log_info(f"{context}自动对话可能未开启（匹配置信度 {before:.2%}），点击开启")
    cx = (auto_chat.x + auto_chat.width / 2) / task.width
    cy = (auto_chat.y + auto_chat.height / 2) / task.height
    _move_and_click(task, cx, cy)
    task.sleep(0.8)
    after = _find_auto_chat(task)
    if not after:
        return True    # 点完画面换了（对白结束），没法判断，下次再看
    after_conf = after.confidence
    if after_conf < before - 0.02:
        task.log_info(f"点击后置信度降到 {after_conf:.2%}，原本是开着的，点回去；阈值改为 {before - 0.01:.2%}")
        _move_and_click(task, cx, cy)
        task.sleep(0.8)
        task._auto_chat_threshold = before - 0.01
    elif after_conf > before + 0.02:
        task._auto_chat_threshold = min(threshold, (before + after_conf) / 2)
    return True


def handle_auto_chat(task: TriggerTask):
    """自动对话检查: 匹配任一自动对话特征，置信度低于阈值时点击开启（点错会自己纠正）。"""
    return _ensure_auto_chat(task)


def _dialogue_line(task: TriggerTask):
    """剧情对白页面: 画面文字很少，且底部中间有一行较长的台词。"""
    texts = getattr(task, "all_texts", None) or []
    # 卡厄思局内顶栏（血量、信用点、Ctrl/Q 按键提示）和右下角 Space 提示不算页面文字
    texts = [
        b for b in texts
        if (b.y + b.height / 2) / task.height > 0.12
        and not re.fullmatch(r"Space|Ctrl|[A-Z]|回", b.name.strip())
    ]
    if len(texts) > 6:
        return None
    # 带操作按钮的页面（如「请确认是否可投入主战员。」+ 确认）不是对白
    if any(re.fullmatch(r"确认|取消|继续|下一步|选择|进入|离开|跳过", b.name.strip()) for b in texts):
        return None
    for box in texts:
        cx = (box.x + box.width / 2) / task.width
        cy = (box.y + box.height / 2) / task.height
        if 0.78 <= cy <= 0.92 and 0.25 <= cx <= 0.75 and len(box.name) >= 6:
            return box
    return None


def handle_dialogue(task: TriggerTask):
    """出击/卡厄思中的剧情对白: 先尝试开启一次自动对话，之后用对话键（空格）推进，避免反复点击开关。"""
    line = _dialogue_line(task)
    if not line:
        return False
    now = time.time()
    last_toggle = getattr(task, "_auto_chat_toggle_time", 0)
    if now - last_toggle > 60:
        if _ensure_auto_chat(task, f"剧情对白「{line.name}」："):
            task._auto_chat_toggle_time = now
            return True
    if now - getattr(task, "_dialogue_key_time", 0) < 1.5:
        return True
    task._dialogue_key_time = now
    task.log_info(f"剧情对白「{line.name}」：按空格推进")
    task.send_key("space")
    return True


def handle_skip(task: TriggerTask):
    """"跳过"按钮。"""
    box = find_box_at_point(task, 0.941, 0.917)
    if box and _clean_match(box.name, "跳过"):
        if any(t in b.name for b in task.all_texts or [] for t in ("查看原件", "查看之前的闪光", "闪光效果")):
            # 闪光变体三选一页：卡牌还在播发光动画时认不出卡，不能当普通跳过页点掉
            # （2026-10-24 实机：冥想重闪后被点了跳过，160 信用点白花）。神闪变体页的跳过由 handle_view_original 自己点
            task.log_info("闪光变体页（卡牌可能还在播动画），不点跳过，等下一帧")
            task.sleep(1)
            return True
        task.log_info("跳过页面触发跳过事件，点击「跳过」按钮")
        task.click_box(box)
        task.sleep(1)
        return True
    return False


def handle_destiny_choice(task: TriggerTask):
    """命运选择奖励页面: 随机选择一个命运标题。"""
    box = find_box_at_point(task, 0.499, 0.932)
    if box and _get_game_text(task, '请选择你的命运') in box.name:
        task.log_info("检测到命运选择奖励，进行相应操作")
        task.sleep(2)  # 给按钮一些加载时间

        # # 检查确认按钮是否已处于激活状态
        # # 在确认按钮点击位置附近查找"确认"文本
        # confirm_box = find_box_at_point(task, 0.884, 0.931)
        # if confirm_box and confirm_box.name == "确认":
        #     if is_button_active(task, confirm_box):
        #         task.log_info("确认按钮已激活，跳过选择（由其他逻辑处理确认）")
        #         return False  # 按钮已激活，不处理，让其他逻辑点击确认
        # 在命运标题区域随机选择一个
        titles = [
            b for b in task.all_texts
            if 0.202 <= (b.x + b.width / 2) / task.width <= 0.800
            and 0.474 <= (b.y + b.height / 2) / task.height <= 0.600
            and len(b.name.strip()) > 1
            and b.name not in ["确认", "返回", "跳过"]
        ]
        if titles and _avoid_god_spark(task):
            # 刷存档：命运会塞中立/咒术卡就不选（用户 2026-10-26：预设外的中立卡一张都不能拿）
            def column_text(t):
                cx = (t.x + t.width / 2) / task.width
                return "".join(b.name for b in task.all_texts
                               if abs((b.x + b.width / 2) / task.width - cx) <= 0.09
                               and t.y <= b.y and (b.y + b.height / 2) / task.height <= 0.85)
            safe = [t for t in titles if not FATE_GIVES_NEUTRAL.search(column_text(t))]
            if safe and len(safe) < len(titles):
                task.log_info(f"命运：跳过会给中立/咒术卡的 {[t.name for t in titles if t not in safe]}")
            titles = safe or titles
        if titles:
            chosen = random.choice(titles)
            task.log_info(f"随机选择命运: {chosen.name}")
            task.click_box(chosen)
            task.sleep(1)
            # 选择命运后不点击确认按钮，返回False让其他逻辑处理
            return True
    return False


def _prioritize_target_member_click(task: TriggerTask, click_positions, search_region):
    """匹配目标成员头像，并将距离最近的候选点击位置移到最前。"""
    if not click_positions:
        task.log_info("刷存档主战员匹配失败：没有可绑定的候选点击位置")
        return click_positions
    if not task.feature_exists("target_member_large"):
        task.log_info(
            "刷存档主战员匹配跳过：尚未保存target_member_large头像特征，"
            "保持原主战员点击顺序"
        )
        return click_positions
    target_member = task.find_one(
        feature_name="target_member_large",
        box=task.box_of_screen(*search_region),
        threshold=0.35,
    )
    if not target_member:
        task.log_info(
            "刷存档主战员头像匹配失败："
            f"在区域{search_region}内未找到target_member_large（阈值=0.35），"
            "保持原主战员点击顺序"
        )
        return click_positions

    center_x = (target_member.x + target_member.width / 2) / task.width
    center_y = (target_member.y + target_member.height / 2) / task.height
    target_position = min(
        click_positions,
        key=lambda position: (
            (position[0] - center_x) ** 2 + (position[1] - center_y) ** 2
        ),
    )
    task.log_info(
        f"刷存档主战员头像匹配成功，相似度={target_member.confidence:.4f}，"
        f"绑定点击位置{target_position}并设为最高优先级"
    )
    return [target_position] + [
        position for position in click_positions if position != target_position
    ]


def handle_main_member_flash(task: TriggerTask):
    """主战员闪光选择页面: 依次尝试主战员，直到出现确认特征。"""
    box = find_box_at_point(task, 0.495, 0.936)
    if not (box and _get_game_text(task, "请选择获得") in box.name):
        return False

    task.log_info("检测主战员闪光选择，进行相应操作")
    confirm_box = task.box_of_screen(0.145, 0.044, 0.856, 0.214)
    click_positions = [(0.228, 0.510), (0.504, 0.504), (0.755, 0.508)]
    prioritized = _prioritize_target_member_click(
        task, click_positions, (0.173, 0.232, 0.858, 0.508)
    )
    if prioritized != click_positions:
        # 认出了目标主战员：先在她身上多点两次再退到别人。点击有动画，2 秒内没出确认就换人，
        # 2026-10-25 实录两次闪光分别给了凛和米卡（罗丝薇瑟在第 1 位）
        prioritized = [prioritized[0]] * 3 + prioritized[1:]
        task.sleep(1)       # 页面淡入时点击不生效
    click_positions = prioritized

    for cx, cy in click_positions:
        task.log_info(f"点击位置({cx}, {cy})")
        _move_and_click(task, cx, cy)
        task.sleep(0.5)

        feature = task.wait_feature(
            "flashmemberconfirm",
            box=confirm_box,
            threshold=0.7,
            time_out=2,
        )
        if feature:
            task.log_info(
                f"点击位置({cx}, {cy})后成功找到flashmemberconfirm"
            )
            return True
        task.log_info(
            f"点击位置({cx}, {cy})后未找到flashmemberconfirm，继续尝试"
        )

    task.log_info("所有尝试均未找到flashmemberconfirm")
    return True


def handle_card_reward(task: TriggerTask):
    """卡牌奖励页面: 按类型特征识别卡牌，并按优先级选择。"""
    page_title = _get_region_text(task, (0.345, 0.012, 0.642, 0.141))
    if "卡牌奖励" not in page_title:
        return False

    task.log_info("检测到卡牌奖励页面")
    cards = recognize_cards(task, page="卡牌奖励页面")
    if not cards:
        task.log_info("卡牌奖励页面未识别到卡牌，等待下一轮处理")
        return True

    if getattr(task, "chaos_mode", "") == chaos_strategy.MODE_EMPTY:
        skip_box = next((b for b in task.all_texts
                         if 0.620 <= (b.x + b.width / 2) / task.width <= 0.990
                         and 0.883 <= (b.y + b.height / 2) / task.height <= 0.983
                         and "跳过" in b.name), None)
        task.log_info("[刷存档-空存] 卡牌奖励一律跳过")
        if skip_box:
            task.click_box(skip_box)
        else:
            _move_and_click(task, 0.745, 0.933)
        task.sleep(0.5)
        return True

    target_boxes, target_click_positions = find_target_card(task)
    if target_boxes:
        click_position = target_click_positions[0]
        task.log_info(
            f"卡牌奖励页面: 检测到target卡牌，点击位置{click_position}"
        )
        _move_and_click(task, *click_position)
        return True

    priority = _get_card_reward_priority(task)

    initial_card_name = _get_config_value(task, "刷初始卡牌", "")
    initial_card_name = initial_card_name.strip() if isinstance(initial_card_name, str) else ""
    node_status = getattr(task, "node_status", {})
    is_initial_node = (
        node_status.get("pass_final_boss_count", 0) == 0
        and node_status.get("node_count", 0) == 0
    )
    if initial_card_name and is_initial_node:
        initial_card = next(
            (card for card in cards if initial_card_name in card["name"]),
            None,
        )
        if initial_card:
            task.log_info(
                f"刷初始卡牌命中「{initial_card_name}」，点击该卡牌"
            )
            _move_and_click(task, initial_card["x"], initial_card["y"])
            task.sleep(1)
            return True
        task.log_info(
            f"刷初始卡牌未找到「{initial_card_name}」，点击ESC重新开始"
        )
        _move_and_click(task, 0.960, 0.053)
        task.sleep(1)
        return True

    chosen_card = None
    for pri_name in priority:
        chosen_card = next(
            (
                card for card in cards
                if pri_name
                and pri_name in card["name"]
                and _edit_distance(pri_name, card["name"], max_dist=1)
            ),
            None,
        )
        if chosen_card:
            task.log_info(
                f"按优先级选择卡牌: {chosen_card['name']}（配置: {pri_name}）"
            )
            break

    if chosen_card is None:
        refresh_boxes = []
        for box in task.all_texts:
            center_x = (box.x + box.width / 2) / task.width
            center_y = (box.y + box.height / 2) / task.height
            if not (
                0.105 <= center_x <= 0.903
                and 0.764 <= center_y <= 0.851
            ):
                continue
            match = re.fullmatch(r"\s*(\d)\s*/\s*3\s*", box.name)
            if match and int(match.group(1)) != 0:
                refresh_boxes.append((box, int(match.group(1)), 3))
        if refresh_boxes:
            for refresh_box, remaining, maximum in refresh_boxes:
                task.log_info(
                    f"卡牌奖励页面未命中优先级卡牌，"
                    f"点击刷新次数「{remaining}/{maximum}」刷新卡牌"
                )
                task.click_box(refresh_box)
            return True

    if chosen_card is None and cards:
        task.log_info("未命中优先级卡牌，跳过非优先级卡牌")
        # 在区域(0.620,0.883,0.990,0.983)内查找包含"跳过"的box并点击
        skip_box = next((b for b in task.all_texts
                         if 0.620 <= (b.x + b.width / 2) / task.width <= 0.990
                         and 0.883 <= (b.y + b.height / 2) / task.height <= 0.983
                         and "跳过" in b.name), None)
        if skip_box:
            task.log_info("卡牌奖励页面触发跳过事件，点击「跳过」按钮")
            task.click_box(skip_box)
        else:
            task.log_info("未找到跳过按钮，点击固定位置")
            _move_and_click(task, 0.745, 0.933)
        task.sleep(0.5)
        return True

    if chosen_card:
        task.log_info(f"卡牌奖励页面触发选卡事件，点击「{chosen_card['name']}」")
        _move_and_click(task, chosen_card["x"], chosen_card["y"])
        task.sleep(1)
        return True
    return False


_EQUIPMENT_TYPE_SLOTS = {"攻击力": 0, "防御力": 1, "生命值": 2}
_EQUIPMENT_QUALITY_RANKS = {"": 0, "普通": 1, "史诗": 2, "传说": 3}
_EQUIPMENT_NORMAL_RGB = (61, 76, 138)
_EQUIPMENT_EPIC_RGB = (160, 88, 69)
_EQUIPMENT_EMPTY_RGB = (15, 15, 15)
_EQUIPMENT_RGB_TOLERANCE = 30


def _equipment_slot(task: TriggerTask, type_text):
    """根据装备类型文本返回 equipment 下标，无法识别时返回 None。"""
    return next((slot for equipment_type, slot in _EQUIPMENT_TYPE_SLOTS.items()
                 if _get_game_text(task, equipment_type) in type_text), None)


def _equipment_priority(task: TriggerTask, slot):
    """读取指定装备位的优先级配置。"""
    priority = _get_config_value(task, f"装备{slot + 1}号位优先级", [])
    priority = list(priority) if isinstance(priority, (list, tuple)) else []
    # 配置里可能写国际服名，展开成所有叫法（别名紧跟原名，优先级顺序不变）
    try:
        db = game_db.get_db()
        return list(dict.fromkeys(a for n in priority for a in db.equipment_aliases(n)))
    except Exception:  # noqa: BLE001
        return priority


def _match_equipment_name(ocr_name, priority):
    """用双向包含匹配装备名，返回配置中的标准名称及优先级下标。"""
    if not ocr_name:
        return None, None
    for index, config_name in enumerate(priority):
        if not config_name:
            continue
        if ocr_name in config_name or config_name in ocr_name:
            return config_name, index
    return None, None


def _equipment_rank(name, priority):
    """返回已记录装备的优先级下标，未命中配置时排在配置装备之后。"""
    _, rank = _match_equipment_name(name, priority)
    return rank if rank is not None else len(priority)


def _equipment_state(task: TriggerTask):
    """获取并修正目标主战员的装备状态字典。"""
    member_status = getattr(task, "member_status", None)
    if not isinstance(member_status, dict):
        member_status = _initial_member_status()
        task.member_status = member_status
    equipment = member_status.setdefault("equipment", {})
    if not isinstance(equipment, dict):
        equipment = {
            "names": ["", "", ""],
            "descriptions": ["", "", ""],
            "qualities": ["", "", ""],
        }
        member_status["equipment"] = equipment
    elif "names" not in equipment or "descriptions" not in equipment:
        old_equipment = equipment
        equipment = {
            "names": ["", "", ""],
            "descriptions": ["", "", ""],
            "qualities": ["", "", ""],
        }
        for equipment_name, description in old_equipment.items():
            for slot in range(3):
                if _match_equipment_name(
                    equipment_name,
                    _equipment_priority(task, slot),
                )[0]:
                    equipment["names"][slot] = equipment_name
                    equipment["descriptions"][slot] = description
                    break
        member_status["equipment"] = equipment
    for key in ("names", "descriptions", "qualities"):
        values = equipment.get(key)
        if not isinstance(values, list):
            values = []
        equipment[key] = (values + ["", "", ""])[:3]
    if not isinstance(member_status.get("deck"), dict):
        member_status["deck"] = {}
    return equipment


def _member_deck_state(task: TriggerTask):
    """获取并修正目标主战员的卡组状态字典。"""
    member_status = getattr(task, "member_status", None)
    if not isinstance(member_status, dict):
        member_status = _initial_member_status()
        task.member_status = member_status
    deck = member_status.setdefault("deck", {})
    if not isinstance(deck, dict):
        deck = {}
        member_status["deck"] = deck
    return deck


def _reset_meditation_state(task: TriggerTask):
    """按当前配置重建目标主战员的冥想状态。"""
    configured_cards = _get_config_value(task, "需要冥想的卡牌", [])
    if not isinstance(configured_cards, (list, tuple)):
        configured_cards = []

    meditation_state = {}
    for card_name in configured_cards:
        normalized_name = str(card_name).strip()
        if normalized_name and normalized_name not in meditation_state:
            meditation_state[normalized_name] = False

    _member_deck_state(task)["冥想"] = meditation_state


def _matching_meditation_card_names(task: TriggerTask, cards):
    """返回与识别卡牌名称匹配的冥想配置名称。"""
    meditation_state = _member_deck_state(task).get("冥想", {})
    if not isinstance(meditation_state, dict):
        return []

    matched_names = []
    for configured_name in meditation_state:
        for card in cards:
            recognized_name = chaos_strategy.base_card_name(card.get("name", ""))
            # 同长度错一个字也算（「剑刀破晓」对「剑刃破晓」，2026-10-25 没记成待冥想）
            if recognized_name and _edit_distance(configured_name, recognized_name, max_dist=1) and (
                configured_name in recognized_name or recognized_name in configured_name
                or len(configured_name) == len(recognized_name)
            ):
                matched_names.append(configured_name)
                break
    return matched_names


def _current_equipment_for_slot(task: TriggerTask, equipment, slot):
    """按槽位读取当前装备名称及其优先级。"""
    priority = _equipment_priority(task, slot)
    names = equipment.get("names", [])
    equipment_name = names[slot] if slot < len(names) else ""
    if not equipment_name:
        return "", len(priority)
    return equipment_name, _equipment_rank(equipment_name, priority)


def _pixel_rgb(task: TriggerTask, point):
    """读取归一化坐标的像素，并将 OpenCV BGR 转为 RGB。"""
    if task.frame is None:
        return None
    x = min(task.width - 1, max(0, round(point[0] * task.width)))
    y = min(task.height - 1, max(0, round(point[1] * task.height)))
    blue, green, red = (int(value) for value in task.frame[y, x, :3])
    return red, green, blue


def _rgb_is_close(rgb, target, tolerance=_EQUIPMENT_RGB_TOLERANCE):
    """判断 RGB 各通道是否均在指定容差内。"""
    return rgb is not None and all(
        abs(value - expected) <= tolerance
        for value, expected in zip(rgb, target)
    )


def _equipment_quality_at(task: TriggerTask, point, allow_empty=False):
    """按指定点颜色识别装备品质；安装槽位可额外识别空槽。"""
    rgb = _pixel_rgb(task, point)
    if rgb is None:
        return None, None
    if allow_empty and _rgb_is_close(rgb, _EQUIPMENT_EMPTY_RGB):
        return "", rgb
    if _rgb_is_close(rgb, _EQUIPMENT_NORMAL_RGB):
        return "普通", rgb
    if _rgb_is_close(rgb, _EQUIPMENT_EPIC_RGB):
        return "史诗", rgb
    return "传说", rgb


def _member_equipment_qualities(task: TriggerTask, level_box):
    """根据等级文本的相对位置读取该主战员三个装备槽的品质。"""
    level_center_x = (level_box.x + level_box.width / 2) / task.width
    level_center_y = (level_box.y + level_box.height / 2) / task.height
    relative_offsets = (
        (0.130, -0.044),
        (0.201, -0.044),
        (0.270, -0.044),
    )
    qualities = []
    for slot, (offset_x, offset_y) in enumerate(relative_offsets):
        point = (level_center_x + offset_x, level_center_y + offset_y)
        quality, rgb = _equipment_quality_at(task, point, allow_empty=True)
        qualities.append(quality)
        task.log_info(
            f"第{slot + 1}号装备位颜色RGB={rgb}，"
            f"识别品质={quality or '未安装'}"
        )
    return qualities


def _should_install_equipment(task, current_name, current_quality, new_equipment):
    """先比较配置装备优先级，优先级相同时再比较品质。"""
    priority = new_equipment["priority"]
    _, current_rank = _match_equipment_name(current_name, priority)
    new_rank = new_equipment["rank"]
    if new_rank is not None or current_rank is not None:
        if new_rank is not None and (
            current_rank is None or new_rank < current_rank
        ):
            return True, "配置优先级更高"
        if current_rank is not None and (
            new_rank is None or current_rank < new_rank
        ):
            return False, "当前装备配置优先级更高"

    current_quality_rank = _EQUIPMENT_QUALITY_RANKS.get(current_quality or "", 0)
    new_quality_rank = _EQUIPMENT_QUALITY_RANKS.get(
        new_equipment.get("quality") or "", 0
    )
    return (
        new_quality_rank > current_quality_rank,
        f"品质{new_equipment.get('quality') or '未知'}"
        f"{'高于' if new_quality_rank > current_quality_rank else '不高于'}"
        f"{current_quality or '未安装'}",
    )


def _equipment_info(task: TriggerTask, name_region, type_region, description_region):
    """从指定区域读取装备名称、类型和描述，并解析槽位、品质与配置优先级。"""
    ocr_name = _get_region_text(task, name_region).strip()
    type_text = _get_region_text(task, type_region).strip()
    description = _get_region_text(task, description_region).strip()
    if not ocr_name or not type_text:
        return None
    slot = _equipment_slot(task, type_text)
    if slot is None:
        return None
    priority = _equipment_priority(task, slot)
    canonical_name, rank = _match_equipment_name(ocr_name, priority)
    quality, quality_rgb = _equipment_quality_at(task, (0.117, 0.409))
    task.log_info(f"待选装备颜色RGB={quality_rgb}，识别品质={quality or '未知'}")
    return {
        "ocr_name": ocr_name,
        "name": canonical_name or ocr_name,
        "type": type_text,
        "description": description,
        "slot": slot,
        "priority": priority,
        "rank": rank,
        "quality": quality,
    }


def _find_member_level_tags(task: TriggerTask, region, page="主战员选择页面"):
    """在指定区域识别leveltag，按位置去重并从上到下返回最多三个。"""
    level_tags = task.find_feature(
        feature_name="leveltag",
        box=task.box_of_screen(*region),
        threshold=0.7,
    ) or []
    deduplicated_level_tags = []
    for level_tag in sorted(
        level_tags,
        key=lambda feature: feature.confidence,
        reverse=True,
    ):
        level_center_x = level_tag.x + level_tag.width / 2
        level_center_y = level_tag.y + level_tag.height / 2
        if any(
            (
                (level_center_x - (kept.x + kept.width / 2)) ** 2
                + (level_center_y - (kept.y + kept.height / 2)) ** 2
            ) ** 0.5
            < max(level_tag.width, level_tag.height, kept.width, kept.height)
            for kept in deduplicated_level_tags
        ):
            continue
        deduplicated_level_tags.append(level_tag)

    kept_level_tags = sorted(
        deduplicated_level_tags,
        key=lambda feature: feature.y,
    )[:3]
    task.log_info(
        f"{page}识别到{len(level_tags)}个leveltag特征，"
        f"去重并限制后保留{len(kept_level_tags)}个"
    )
    for index, level_tag in enumerate(kept_level_tags, 1):
        task.log_info(
            f"第{index}号主战员leveltag: "
            f"中心=({(level_tag.x + level_tag.width / 2) / task.width:.4f}, "
            f"{(level_tag.y + level_tag.height / 2) / task.height:.4f})，"
            f"置信度={level_tag.confidence:.4f}"
        )
    return kept_level_tags


def _find_target_member_index(
    task: TriggerTask,
    lv_texts,
    region,
    feature_name="target_member_small",
):
    """在指定区域匹配目标成员头像，并返回距离最近的等级文本索引。"""
    if not lv_texts or not task.feature_exists(feature_name):
        return None
    target_member_box = task.find_one(
        feature_name=feature_name,
        box=task.box_of_screen(*region),
        threshold=0.4,
    )
    if not target_member_box:
        return None

    target_center_x = target_member_box.x + target_member_box.width / 2
    target_center_y = target_member_box.y + target_member_box.height / 2
    target_member_index = min(
        range(len(lv_texts)),
        key=lambda index: (
            (lv_texts[index].x + lv_texts[index].width / 2 - target_center_x) ** 2
            + (lv_texts[index].y + lv_texts[index].height / 2 - target_center_y) ** 2
        ),
    )
    task.log_info(
        f"刷存档主战员头像匹配成功，相似度={target_member_box.confidence:.4f}，"
        f"绑定第{target_member_index + 1}号主战员"
    )
    return target_member_index


def _mark_equipment_obtained(task: TriggerTask, name):
    """装备页上读到的实际装备记为「拿过」：随机装备池抽到的具体装备，选项文字里看不到（2026-10-24 实录
    「非典型立方体」从随机池拿过，下一局「获得装备[非典型立方体]」又被当成没拿过）。"""
    seen = getattr(task, "chaos_seen", None)
    if seen is None or not chaos_strategy.is_specific_equipment(name):
        return
    key = chaos_strategy.equipment_key(name)
    if key not in seen:
        seen.add(key)
        chaos_strategy.save_seen(seen)
        task.log_info(f"记下拿过的装备「{name}」")


def handle_equipment(task: TriggerTask):
    """装备选择/安装界面: 按装备位优先级选择，并维护目标主战员的装备状态。"""
    title = find_box_at_point(task, 0.499, 0.126)
    if not (title and title.name == "装备"):
        return False

    task.log_info("检测到装备页面")
    equipment = _equipment_state(task)
    equip_hint = find_box_at_point(task, 0.921, 0.135)

    if equip_hint and _get_game_text(task, '请选择主战员') in equip_hint.name:
        task.log_info("检测到安装装备界面")
        purchase_bottom_boxes = [
            box for box in task.all_texts
            if 0.013 <= (box.x + box.width / 2) / task.width <= 0.992
            and 0.881 <= (box.y + box.height / 2) / task.height <= 0.994
            and box.name.strip()
        ]
        cancel_box = next(
            (box for box in purchase_bottom_boxes if "取消" in box.name), None
        )
        purchase_box = next(
            (box for box in purchase_bottom_boxes if "购买" in box.name), None
        )
        price_box = next(
            (box for box in purchase_bottom_boxes
             if re.fullmatch(r"\d+", box.name.strip())),
            None,
        )
        is_purchase_page = bool(cancel_box and purchase_box)
        equipment_price = None
        current_credit = None
        if is_purchase_page:
            task.log_info("检测到购买装备页面")
            equipment_price = (
                _parse_discounted_price(price_box.name) if price_box else None
            )
            current_credit = _get_current_credit(task)
            task.log_info(
                f"购买装备页面: 当前信用点={current_credit}，"
                f"OCR价格=「{price_box.name if price_box else ''}」，"
                f"实际价格={equipment_price}"
            )
            if equipment_price is None:
                task.log_info("购买装备页面未识别到价格，按价格低于当前信用点继续购买")
            elif equipment_price > current_credit:
                task.log_info(
                    f"装备价格{equipment_price}大于当前信用点{current_credit}，点击「取消」"
                )
                task.click_box(cancel_box)
                task.sleep(1)
                return True

        bottom_buttons = [
            box for box in task.all_texts
            if 0.563 <= (box.x + box.width / 2) / task.width <= 0.998
            and 0.881 <= (box.y + box.height / 2) / task.height <= 0.997
            and box.name.strip()
        ]
        refine_boxes = [box for box in bottom_buttons if "提炼" in box.name]
        if refine_boxes and len(refine_boxes) == len(bottom_buttons):
            task.log_info("安装装备界面只有提炼按钮，直接点击提炼")
            task.click_box(refine_boxes[0])
            return True

        new_equipment = _equipment_info(
            task,
            (0.217, 0.379, 0.469, 0.436),
            (0.188, 0.444, 0.323, 0.489),
            (0.179, 0.492, 0.542, 0.668),
        )
        if not new_equipment:
            task.log_info("未能识别待安装装备的名称或类型")
            if is_purchase_page:
                task.log_info("购买装备无法识别装备信息，点击「取消」")
                task.click_box(cancel_box)
                task.sleep(1)
                return True
            return False
        equipment_desc = new_equipment["description"]
        task.log_info(f"待安装装备描述: 「{equipment_desc}」")
        if not is_purchase_page:
            _mark_equipment_obtained(task, new_equipment.get("name"))
            if new_equipment.get("rank") is not None and isinstance(getattr(task, "node_status", None), dict):
                if not task.node_status.get("target_equip_got"):
                    task.log_info(f"本局拿到目标装备「{new_equipment.get('name')}」")
                task.node_status["target_equip_got"] = new_equipment.get("name")
                _hand_over_on_chaos_core(task, new_equipment.get("name"))

        lv_texts = _find_member_level_tags(
            task,
            (0.609, 0.290, 0.652, 0.789),
            page="安装装备页面",
        )
        target_member_index = _find_target_member_index(
            task,
            lv_texts,
            (0.607, 0.192, 0.739, 0.856),
            feature_name="target_member_tiny",
        )
        tracks_target_member = "刷存档主战员" in getattr(task, "default_config", {})
        preferred_member_index = (
            target_member_index if tracks_target_member else (0 if lv_texts else None)
        )

        slot = new_equipment["slot"]
        current_name, _ = _current_equipment_for_slot(task, equipment, slot)
        current_quality = equipment["qualities"][slot]
        should_install_first = False
        install_reason = "未找到目标主战员"
        if preferred_member_index is not None:
            live_qualities = _member_equipment_qualities(
                task, lv_texts[preferred_member_index]
            )
            for equipment_slot, live_quality in enumerate(live_qualities):
                if live_quality is None:
                    continue
                equipment["qualities"][equipment_slot] = live_quality
                if not live_quality:
                    if equipment["names"][equipment_slot]:
                        task.log_info(
                            f"第{equipment_slot + 1}号装备位实际为空，清除记录装备"
                            f"「{equipment['names'][equipment_slot]}」"
                        )
                    equipment["names"][equipment_slot] = ""
                    equipment["descriptions"][equipment_slot] = ""
            current_name, _ = _current_equipment_for_slot(task, equipment, slot)
            current_quality = equipment["qualities"][slot]
            should_install_first, install_reason = _should_install_equipment(
                task,
                current_name,
                current_quality,
                new_equipment,
            )
            has_legendary_in_other_slot = any(
                quality == "传说" and equipment_slot != slot
                for equipment_slot, quality in enumerate(live_qualities)
            )
            if (
                new_equipment["quality"] == "传说"
                and has_legendary_in_other_slot
            ):
                should_install_first = False
                install_reason = "该主战员其他装备位已有传说装备"
                task.log_info(
                    "目标主战员已安装传说装备，新传说装备改由其他主战员安装"
                )

        if should_install_first and preferred_member_index is not None:
            chosen = lv_texts[preferred_member_index]
            if not tracks_target_member or target_member_index is not None:
                equipment["names"][slot] = new_equipment["name"]
                equipment["descriptions"][slot] = equipment_desc
                equipment["qualities"][slot] = new_equipment["quality"] or ""
            member_label = (
                "刷存档主战员"
                if target_member_index is not None
                else "第一主战员"
            )
            task.log_info(
                f"{slot + 1}号位装备「{new_equipment['name']}」优于当前装备「{current_name}」，"
                f"原因={install_reason}，"
                f"安装给{member_label}"
            )
            _move_and_click(task, 0.756, (chosen.y + chosen.height / 2) / task.height)
            task.sleep(1)
            if is_purchase_page:
                task.log_info(
                    f"购买装备分配完成，价格={equipment_price}，"
                    f"当前信用点={current_credit}，点击「购买」"
                )
                task.click_box(purchase_box)
                task.sleep(1)
                return True
            return False

        other_members = [
            level_box for index, level_box in enumerate(lv_texts)
            if index != preferred_member_index
        ]
        if other_members:
            chosen = random.choice(other_members)
            if tracks_target_member and target_member_index is None:
                task.log_info("未识别到刷存档主战员，随机安装给其他主战员")
            else:
                task.log_info(
                    f"{slot + 1}号位无需替换当前装备「{current_name}」，"
                    f"原因={install_reason}，"
                    "随机安装给其他主战员"
                )
            _move_and_click(task, 0.756, (chosen.y + chosen.height / 2) / task.height)
            task.sleep(1)
            if is_purchase_page:
                task.log_info(
                    f"购买装备分配给其他主战员，价格={equipment_price}，"
                    f"当前信用点={current_credit}，点击「购买」"
                )
                task.click_box(purchase_box)
                task.sleep(1)
                return True
            return False

        if is_purchase_page:
            task.log_info("购买装备无法分配给任何主战员，点击「取消」")
            task.click_box(cancel_box)
            task.sleep(1)
            return True

        refine_box = next(
            (b for b in task.all_texts
             if 0.522 <= (b.x + b.width / 2) / task.width <= 0.999
             and 0.879 <= (b.y + b.height / 2) / task.height <= 0.996
             and "提炼" in b.name),
            None
        )
        if refine_box:
            task.log_info(f"{slot + 1}号位无需替换且没有其他主战员可选，点击提炼")
            task.click_box(refine_box)
            task.sleep(1)
            return True

        task.log_info("未找到可选择的主战员或提炼按钮")
        return False

    candidates = []
    candidate_specs = [
        (
            (0.409, 0.219, 0.678, 0.276),
            (0.384, 0.275, 0.562, 0.319),
            (0.382, 0.324, 0.723, 0.496),
            (0.518, 0.454),
        ),
        (
            (0.410, 0.551, 0.699, 0.608),
            (0.384, 0.613, 0.573, 0.653),
            (0.380, 0.658, 0.720, 0.836),
            (0.521, 0.600),
        ),
    ]
    for name_region, type_region, description_region, click_position in candidate_specs:
        candidate = _equipment_info(
            task, name_region, type_region, description_region
        )
        if not candidate:
            task.log_info("选择装备界面的候选装备信息不完整，等待下轮重新识别")
            return True
        candidate["click_position"] = click_position
        candidates.append(candidate)
    task.log_info(
        f"检测到选择装备界面，候选装备: "
        f"{[(candidate['ocr_name'], candidate['slot'] + 1) for candidate in candidates]}"
    )

    chosen_index = None
    for slot in range(3):
        current_name, current_rank = _current_equipment_for_slot(task, equipment, slot)
        for index, candidate in enumerate(candidates):
            if candidate["slot"] != slot or candidate["rank"] is None:
                continue
            if not current_name or candidate["rank"] < current_rank:
                chosen_index = index
                task.log_info(
                    f"优先选择{slot + 1}号位装备「{candidate['name']}」，当前装备「{current_name}」"
                )
                break
        if chosen_index is not None:
            break

    if chosen_index is None:
        empty_slot_candidates = [
            candidate for candidate in candidates
            if not _current_equipment_for_slot(task, equipment, candidate["slot"])[0]
        ]
        if empty_slot_candidates:
            chosen_candidate = random.choice(empty_slot_candidates)
            click_position = chosen_candidate["click_position"]
            task.log_info(
                f"候选装备均未命中升级条件，优先选择空缺的"
                f"{chosen_candidate['slot'] + 1}号位装备「{chosen_candidate['ocr_name']}」"
            )
        else:
            task.log_info("候选装备均未命中升级条件且对应位置均非空，随机选择一个装备")
            click_position = random.choice([spec[3] for spec in candidate_specs])
    else:
        click_position = candidates[chosen_index]["click_position"]
    _move_and_click(task, *click_position)
    task.sleep(2)
    return False


# 卡牌操作关键词 → 配置 key 映射
_SELECT_CARD_CONFIG_KEYS = {
    "移除": "移除卡牌列表",
    "复制": "复制卡牌列表",
    "闪光": "闪光卡牌列表",
    "灵光": "闪光卡牌列表",
}


def _scroll_to_target_member_for_card_removal(task: TriggerTask):
    """移除卡牌前滚动成员列表，直到目标成员出现或到达底部。"""
    feature_name = "target_member_in_select_card"
    page = "移除卡牌目标主战员查找"
    if not task.feature_exists(feature_name):
        task.log_info(f"{page}: 尚未保存{feature_name}特征，跳过查找")
        return

    search_region = (0.079, 0.092, 0.209, 0.675)
    search_box = task.box_of_screen(*search_region)
    scroll_x = (search_region[0] + search_region[2]) / 2
    scroll_y = (search_region[1] + search_region[3]) / 2
    scrollbar_white_ratio = region_white_ratio(
        task, (0.976, 0.119, 0.988, 0.858)
    )
    single_page = scrollbar_white_ratio < 0.01
    task.log_info(
        f"{page}: 滚动条区域白色像素占比={scrollbar_white_ratio:.2%}，"
        f"是否仅一页卡牌={single_page}"
    )

    max_scrolls = 20
    scroll_count = 0
    while True:
        target_member = task.find_one(
            feature_name=feature_name,
            box=search_box,
            threshold=0.5,
        )
        if target_member:
            task.log_info(
                f"{page}: 找到目标主战员，相似度={target_member.confidence:.4f}"
            )
            return
        if single_page:
            task.log_info(f"{page}: 当前仅一页，未找到目标主战员")
            return
        if _point_is_white(task, 0.982, 0.846, page):
            task.log_info(f"{page}: 已到达底部，未找到目标主战员")
            return
        if scroll_count >= max_scrolls:
            task.log_info(f"{page}: 向下滚动已达到{max_scrolls}次限制")
            return
        _scroll_card_page(
            task,
            scroll_x,
            scroll_y,
            -3,
            page,
            distance=(search_region[3] - search_region[1]) / 4,
        )
        scroll_count += 1


GOD_SPARK_PAGE = re.compile(r"神之闪光|闪光[:：]?\s*(" + chaos_strategy.GOD_NAMES + r")")


# 命运描述里「获得1张咒术卡牌贫血」才算给牌；「灵感：每次生成除状态异常、咒术卡牌以外的卡牌时…」不算（2026-10-26 实录误跳）
FATE_GIVES_NEUTRAL = re.compile(r"(获得|加入)[^。，,]{0,8}(中立|咒术)")


def _avoid_god_spark(task: TriggerTask):
    """刷存档（目标卡组/空存）局内一律不神闪：神闪闪错卡会「爆存档」，局外也撤销不了（用户 2026-10-24）。"""
    return getattr(task, "chaos_mode", "") in (chaos_strategy.MODE_TARGET, chaos_strategy.MODE_EMPTY)


# ---------------- 本局 PT 账（刷存档局内绝不爆 PT，用户 2026-10-25） ----------------
# 按 czn-chaos-mechanics.md 2.2：移除起始卡 20（保守地把每次移除都当起始卡）、复制第 3 张起 40、中立卡 20、神闪 20。
PT_COST = {"移除": 20, "复制": 40, "中立卡": 20, "神闪": 20}


def _pt_ledger(ns):
    return (PT_COST["移除"] * ns.get("removed_card_count", 0)
            + PT_COST["复制"] * max(0, ns.get("copy_count", 0) - 2)
            + PT_COST["中立卡"] * ns.get("neutral_card_count", 0)
            + PT_COST["神闪"] * ns.get("god_spark_count", 0))


def _pt_used(task: TriggerTask):
    """已用 PT。选路页读过游戏「主战员」面板的「模糊的记忆」就以它为准，再加上读完以后脚本记的增量；
    没读到才全靠自己记（2026-10-25 实录自己记的比存档页少 20～60：记忆卡等没算进去）。"""
    ns = getattr(task, "node_status", None) or {}
    raw = _pt_ledger(ns)
    if ns.get("pt_game") is None:
        return raw
    return ns["pt_game"] + max(0, raw - ns.get("pt_game_ledger", raw))


# 局内左上角头像点开的「主战员」面板（2026-10-25 实机）：每人一列，模糊的记忆 a/b、复制 a/3、移除 a/5、压力、装备
MEMBER_PANEL_COLUMNS = ((0.14, 0.40), (0.41, 0.67), (0.68, 0.95))
MEMBER_PANEL_ROWS = {"pt": "模糊的记忆", "copy": "复制", "remove": "移除"}


def parse_member_panel(boxes, width, height):
    """OCR 结果 → [{name, pt, pt_cap, copy, remove}]，每列一个。"""
    def center(b):
        return (b.x + b.width / 2) / width, (b.y + b.height / 2) / height

    cols = []
    for x0, x1 in MEMBER_PANEL_COLUMNS:
        inside = [(b, *center(b)) for b in boxes if x0 <= center(b)[0] <= x1]
        names = [b.name.strip() for b, _, y in inside if 0.33 <= y <= 0.40 and len(b.name.strip()) >= 1
                 and not re.search(r"\d", b.name)]
        col = {"name": max(names, key=len) if names else ""}
        for key, label in MEMBER_PANEL_ROWS.items():
            ys = [y for b, _, y in inside if label in b.name]
            if not ys:
                continue
            for b, _, y in inside:
                m = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", b.name)
                if m and abs(y - ys[0]) <= 0.02:
                    col[key] = int(m.group(1))
                    if key == "pt":
                        col["pt_cap"] = int(m.group(2))
        cols.append(col)
    return cols


def read_member_panel(task: TriggerTask):
    """选路页点开主战员面板读刷存档主战员的 PT/复制/移除，读完关掉。读到就同步进 node_status。"""
    ns = getattr(task, "node_status", None)
    target = str(_get_config_value(task, "刷存档主战员", "") or "").strip()
    if ns is None or not target:
        return None
    _move_and_click(task, 0.30, 0.075)
    task.sleep(1.5)
    task.next_frame()
    texts = _simplify_texts(task.ocr())
    if not any("模糊的记忆" in b.name for b in texts):
        task.log_info("主战员面板没打开，这次不读游戏里的 PT")
        return None
    cols = parse_member_panel(texts, task.width, task.height)
    _move_and_click(task, 0.959, 0.050)      # 右上角 X 关面板
    task.sleep(1)
    col = next((c for c in cols if c.get("name") and (target in c["name"] or c["name"] in target)), None)
    if not col or "pt" not in col:
        task.log_info(f"主战员面板没找到「{target}」的模糊的记忆：{cols}")
        return None
    raw = _pt_ledger(ns)
    task.log_info(f"主战员面板：{col['name']} 模糊的记忆 {col['pt']}/{col.get('pt_cap')}，"
                  f"复制 {col.get('copy')}，移除 {col.get('remove')}")
    if col["pt"] != _pt_used(task):
        task.log_info(f"PT 以游戏为准：主战员面板 {col['pt']}/{col.get('pt_cap')}，脚本记的 {_pt_used(task)}")
    ns["pt_game"], ns["pt_game_ledger"] = col["pt"], raw
    if col.get("pt_cap"):
        task.chaos_pt_cap = col["pt_cap"]
    # 复制/移除次数只记日志不改：移除要等确认后才 +1（_pending_removed_card_count），面板已经算上了，
    # 这时改计数会让之后补的那次再记一遍（2026-10-25 实录面板 40、脚本 60）。多算的增量到下个选路页重读就纠正
    for key, ns_key in (("copy", "copy_count"), ("remove", "removed_card_count")):
        if key in col and col[key] != ns.get(ns_key, 0):
            task.log_info(f"主战员面板{MEMBER_PANEL_ROWS[key]} {col[key]} 次，脚本记 {ns.get(ns_key, 0)} 次")
    return col


def _pt_cost(task: TriggerTask, what):
    if what == "复制":
        return PT_COST["复制"] if (getattr(task, "node_status", None) or {}).get("copy_count", 0) >= 2 else 0
    return PT_COST[what]


def _pt_room(task: TriggerTask, what):
    """刷存档局内：做这件事之后 PT 还在上限内吗。没记到上限（探索度/原有逻辑）就不管。"""
    cap = getattr(task, "chaos_pt_cap", None)
    if not cap or not _avoid_god_spark(task):
        return True
    used, cost = _pt_used(task), _pt_cost(task, what)
    if used + cost <= cap:
        return True
    task.log_info(f"PT 账：已用 {used}，{what}要 {cost}，上限 {cap}，会爆 PT，不做")
    return False


def _god_spark_wanted(task: TriggerTask):
    """预设里要神闪、本局还没拿到一致神闪的卡名（去重）。"""
    plan = getattr(task, "chaos_plan", None) or {}
    done = (getattr(task, "node_status", None) or {}).get("god_ok", [])
    names = []
    for c in plan.get("flash", []):
        if c.get("god_spark") and c["name"] not in done and c["name"] not in names:
            names.append(c["name"])
    return names


_REAL_CARD_NAMES = None


def _ocr_name_matches(ocr_name, target):
    """OCR 卡名错一个字也算目标卡：等长（≥3 字）、只差一个字、且 OCR 出的不是库里另一张真卡的名字。
    2026-10-25 实录重新闪光页把「明灭剑」认成「明灰剑」，没选上就点了跳过，冥想的 80 信用点白花。
    「黑云奥义：残」是真卡名，不会被当成「黑云奥义：灭」。"""
    if len(ocr_name) != len(target) or len(target) < 3:
        return False
    if sum(1 for x, y in zip(ocr_name, target) if x != y) != 1:
        return False
    return ocr_name not in _real_card_names()


def _real_card_names():
    global _REAL_CARD_NAMES
    if _REAL_CARD_NAMES is None:
        try:
            db = game_db.get_db()
            _REAL_CARD_NAMES = {c["name"] for c in list(db.cards) + list(db.neutral_cards)}
        except Exception:  # noqa: BLE001
            _REAL_CARD_NAMES = set()
    return _REAL_CARD_NAMES


_CARD_DESC_BIGRAMS = None


def _bigrams(text):
    t = re.sub(r"[\s:：，,。.、（）()【】\[\]%\d]", "", text or "")
    return {t[i:i + 2] for i in range(len(t) - 1)}


def _ocr_desc_matches(ocr_name, ocr_desc, target):
    """OCR 卡名错得更多时按描述认：OCR 名不是真卡名、和目标至少共一个字，且整个卡库里描述（含各闪光变体）最像的就是目标。
    2026-10-25 实录重新闪光页把「明灭剑」认成「灰剑」（描述「明暗分裂时，分裂成剑华：明、剑华：暗」），冥想 120 信用点白花。"""
    global _CARD_DESC_BIGRAMS
    if not ocr_name or not ocr_desc or not set(ocr_name) & set(target):
        return False
    if ocr_name in _real_card_names():
        return False
    if _CARD_DESC_BIGRAMS is None:
        try:
            db = game_db.get_db()
            _CARD_DESC_BIGRAMS = {}
            for c in list(db.cards) + list(db.neutral_cards):
                grams = _bigrams(c.get("desc"))
                for sp in c.get("sparks") or []:
                    grams |= _bigrams(sp.get("desc"))
                _CARD_DESC_BIGRAMS.setdefault(c["name"], set()).update(grams)
        except Exception:  # noqa: BLE001
            _CARD_DESC_BIGRAMS = {}
    ocr = _bigrams(ocr_desc)
    if len(ocr) < 4 or target not in _CARD_DESC_BIGRAMS:
        return False
    scores = {name: len(ocr & grams) / len(ocr) for name, grams in _CARD_DESC_BIGRAMS.items() if grams}
    best = max(scores, key=scores.get)
    # 实录「灰剑」：明灭剑 0.44，次高 0.28；描述 OCR 常有串行和漏字，阈值不能太高，靠和次高拉开差距防误认
    return best == target and scores[target] >= 0.35 and scores[target] - sorted(scores.values())[-2] >= 0.1


def _flash_done(task: TriggerTask, name):
    """预设里同名卡全部闪对了没有（2026-10-25 实录剑鸣九霄 3 张只闪对 1 张就不再选）。"""
    plan = getattr(task, "chaos_plan", None) or {}
    need = sum(1 for c in plan.get("flash", []) if c.get("name") == name) or 1
    return (getattr(task, "node_status", None) or {}).get("flash_ok", []).count(name) >= need


def _copy_needed(task: TriggerTask):
    """目标卡组还要不要复制（首领奖励的复制不经过事件打分，2026-10-25 实录复制成第 4 张剑鸣九霄）。其他模式不管。"""
    if getattr(task, "chaos_mode", "") != chaos_strategy.MODE_TARGET:
        return True
    plan = getattr(task, "chaos_plan", None) or {}
    done = (getattr(task, "node_status", None) or {}).get("copy_count", 0)
    return len(plan.get("copy", [])) > done


def _record_copy(task: TriggerTask):
    ns = task.node_status
    key = (ns.get("total_rounds", 0), ns.get("pass_final_boss_count", 0), ns.get("node_count", 0))
    if ns.get("copy_key") == key:
        return
    ns["copy_key"] = key
    ns["copy_count"] = ns.get("copy_count", 0) + 1
    task.log_info(f"本局复制 {ns['copy_count']} 次，PT 账 {_pt_used(task)}/{getattr(task, 'chaos_pt_cap', None)}")


def _click_bottom_skip(task: TriggerTask, reason):
    skip_box = next((b for b in task.all_texts or []
                     if 0.620 <= (b.x + b.width / 2) / task.width <= 0.990
                     and 0.850 <= (b.y + b.height / 2) / task.height <= 0.990 and "跳过" in b.name), None)
    if not skip_box:
        return False
    task.log_info(f"{reason}，点击「跳过」")
    task.click_box(skip_box)
    task.sleep(1)
    return True


def handle_select_card(task: TriggerTask):
    """统一卡牌选择页面: 在(0.198,0.039)处检测文本，按移除/复制/闪光等关键字匹配配置并选择卡牌。"""
    box = find_box_at_point(task, 0.198, 0.039)
    if not box:
        return False
    m = re.search(r'请选择(\d*)张*.*?(移除|复制|闪光|灵光).*?卡牌', box.name)
    if not m:
        return False
    count_text = m.group(1)
    action = m.group(2)
    count = int(count_text) if count_text else 1
    config_key = _SELECT_CARD_CONFIG_KEYS.get(action)
    if config_key is None:
        return False
    task.log_info(f"检测到卡牌{action}选择，需选择{count}张，配置key={config_key}")
    god_pick = False
    if action in ("闪光", "灵光") and _avoid_god_spark(task) and task.node_status.get("god_spark_pending"):
        task.node_status["god_spark_pending"] = False
        wanted = _god_spark_wanted(task) if getattr(task, "chaos_mode", "") == chaos_strategy.MODE_TARGET else []
        if wanted and _pt_room(task, "神闪"):
            # 2026-10-25 用户：和预设一致、不爆 PT 的神闪可以拿。只选预设要神闪的卡，变体页再核对一致才选
            task.log_info(f"神闪选卡：只选预设要神闪的卡 {wanted}")
            god_pick = True
        elif _click_bottom_skip(task, "刚选的是神闪选项，预设不需要或 PT 不够"):
            return True

    # 日志打印右下角选牌操作提示
    action_tip = find_box_at_point(task, 0.945, 0.918)
    if action_tip:
        task.log_info(f"右下角选牌操作提示: 「{action_tip.name}」")

    if action in ("移除", "复制") and not _pt_room(task, action):
        if _click_bottom_skip(task, f"{action}会爆 PT"):
            return True
    if action == "复制" and not _copy_needed(task):
        if _click_bottom_skip(task, "目标卡组要复制的已经够了"):
            return True

    if (
        action in ("移除", "复制", "闪光", "灵光")
        and task.name == "自动卡厄思模式"
    ):
        _scroll_to_target_member_for_card_removal(task)

    card_list = _get_card_list(task, config_key)
    select_action = action
    if action in ("闪光", "灵光") and action_tip and _get_game_text(task, '重新闪光') in action_tip.name:
        select_action = "重新闪光"      # 不按图钉/闪光优先级兜底，只选待冥想的卡
        # 冥想的「重新闪光」只该重闪待冥想（闪错）的卡；按闪光列表顺序会把已经闪对的卡重闪掉
        # （2026-10-25 实录：待冥想的是循环之刃，却重闪了剑鸣九霄）
        pending = [n for n, v in (_member_deck_state(task).get("冥想", {}) or {}).items() if v is True]
        task.log_info(f"重新闪光：只选待冥想的卡 {pending}")
        if not pending:
            # 训练后也会给一次重新闪光（2026-10-25 实录）：没有闪错的卡就别动，免得把闪对的卡重闪坏
            if _click_bottom_skip(task, "没有待冥想（闪错）的卡，不重新闪光"):
                return True
            return False
        card_list = pending
        task.node_status['meditate_count'] = task.node_status.get('meditate_count', 0) + 1
    if god_pick:
        card_list = _god_spark_wanted(task)
    elif (action in ("闪光", "灵光") and select_action != "重新闪光"
            and getattr(task, "chaos_mode", "") == chaos_strategy.MODE_TARGET):
        # 目标卡组：先选闪错的（免费重闪），再选还没闪对的；都闪对了就跳过（2026-10-25 实录把闪对的剑鸣九霄又闪坏）
        pending = [n for n, v in (_member_deck_state(task).get("冥想", {}) or {}).items() if v is True]
        ok = task.node_status.get("flash_ok", [])
        card_list = pending + [n for n in card_list if not _flash_done(task, n) and n not in pending]
        task.log_info(f"选卡闪光：闪错待重闪 {pending}，已闪对 {ok} → 候选 {card_list}")
        if not card_list:
            if _click_bottom_skip(task, "目标卡都闪对了，不再闪光"):
                return True
            return False
    result = select_card(task, card_list, count=count, action=select_action)
    if result and action == "复制":
        _record_copy(task)
    if not result and action in ("闪光", "灵光"):
        skip_box = next(
            (
                b for b in task.all_texts
                if 0.620 <= (b.x + b.width / 2) / task.width <= 0.990
                and 0.883 <= (b.y + b.height / 2) / task.height <= 0.983
                and "跳过" in b.name
            ),
            None,
        )
        if skip_box:
            task.log_info(f"卡牌{action}选择无可用卡牌，点击「跳过」")
            task.click_box(skip_box)
            return True
    return result


def handle_copy_card_choice(task: TriggerTask):
    """复制卡牌选择页面: 按类型特征识别卡牌，并按复制卡牌列表优先级选择。"""
    box = find_box_at_point(task, 0.498, 0.133)
    copy_card_prompt = _get_game_text(task, "请选择要复制的卡牌")
    if not (box and copy_card_prompt in box.name):
        return False

    task.log_info("检测到复制卡牌选择页面")
    if not _pt_room(task, "复制") and _click_bottom_skip(task, "复制会爆 PT"):
        return True
    if not _copy_needed(task) and _click_bottom_skip(task, "目标卡组要复制的已经够了"):
        return True
    target_boxes, target_click_positions = find_target_card(task)
    if target_boxes:
        click_position = target_click_positions[0]
        task.log_info(
            f"复制卡牌选择: 检测到target卡牌，点击位置{click_position}"
        )
        _record_copy(task)          # 图钉卡这条路也要记 PT 账（2026-10-25 实录首领奖励复制没记上）
        _move_and_click(task, *click_position)
        return True

    cards = recognize_cards(task, page="复制卡牌选择页面")

    priority = _get_config_value(task, '复制卡牌列表', [])
    for pri_name in priority:
        for card in cards:
            if card["name"] and pri_name in card["name"]:
                task.log_info(f"复制卡牌选择: 按优先级选择「{card['name']}」(匹配「{pri_name}」)")
                _record_copy(task)
                _move_and_click(task, card["x"], card["y"])
                task.sleep(0.5)
                return True

    task.log_info("复制卡牌选择: 未命中任何优先级，return False")
    return False


def handle_copy_member(task: TriggerTask):
    """选择要复制卡牌的主战员页面。"""
    box = find_box_at_point(task, 0.502, 0.932)
    copy_member_prompt = _get_game_text(task, "选择要复制卡牌的主战员")
    if not (box and copy_member_prompt in box.name):
        return False

    task.log_info("检测到卡牌复制主战员选择事件，进行相应操作")

    confirm_box = task.box_of_screen(0.145, 0.044, 0.856, 0.214)
    click_positions = [(0.228, 0.510), (0.504, 0.504), (0.755, 0.508)]
    click_positions = _prioritize_target_member_click(
        task, click_positions, (0.173, 0.232, 0.858, 0.508)
    )

    for i, (cx, cy) in enumerate(click_positions):
        task.log_info(f"点击位置({cx}, {cy})")
        _move_and_click(task, cx, cy)
        task.sleep(0.5)

        feature = task.wait_feature("copymemberconfirm", box=confirm_box, time_out=2)
        if feature:
            task.log_info(f"点击位置({cx}, {cy})后成功找到copymemberconfirm")
            return True
        else:
            task.log_info(f"点击位置({cx}, {cy})后未找到copymemberconfirm，继续尝试")

    task.log_info("所有尝试均未找到copymemberconfirm")
    return True


def handle_convert_card(task: TriggerTask):
    """转换卡牌页面: 跳过转换。"""
    box = find_box_at_point(task, 0.226, 0.046)
    if box and _get_game_text(task, '转换的卡牌') in box.name:
        task.log_info("检测到卡牌转换选择，进行跳过操作")
        _move_and_click(task, 0.776, 0.926)
        task.sleep(0.5)
        _move_and_click(task, 0.661, 0.632)
        return True
    return False


def handle_negotiation(task: TriggerTask):
    """谈判失败页面: 点击下一步跳过。"""
    title = find_box_at_point(task, 0.498, 0.683)
    if title and "失败" in title.name:
        task.log_info("检测到掷骰子失败，跳过掷骰子")
        _move_and_click(task, 0.665, 0.899)
        return True
    return False


def handle_chaos_disconnected(task: TriggerTask):
    """重开游戏后的「卡厄思连接意外断开。是否继续?」弹窗：点「继续」回到局内，绝不点「逃脱」（会放弃本局）。
    2026-10-26 实录：游戏卡死自动重开后停在这个弹窗 5 分钟，又被判卡死重开了一次。"""
    if not any("连接意外断开" in b.name for b in task.all_texts or []):
        return False
    box = next((b for b in task.all_texts if re.sub(r"\W", "", b.name) == "继续"), None)
    if box:
        task.log_info("卡厄思连接意外断开弹窗：点「继续」回到局内")
        task.click_box(box)
        task.sleep(3)
        return True
    task.log_info(f"卡厄思连接意外断开弹窗，没认出「继续」按钮（不点逃脱）：{' | '.join(b.name for b in task.all_texts)}")
    return False


def handle_title_start(task: TriggerTask):
    """停在标题页「点击开始」（重开游戏后标题页没点过去，2026-10-26 实录）。"""
    box = next((b for b in task.all_texts or [] if re.sub(r"\s", "", b.name) == "点击开始"), None)
    if not box:
        return False
    task.log_info("停在标题页，点「点击开始」")
    task.click_box(box)
    task.sleep(3)
    return True


def handle_continue(task: TriggerTask):
    """通用"继续"按钮。"""
    continue_region = (0.459, 0.858, 0.992, 0.988)
    continue_text = _get_game_text(task, '继续')
    box = next(
        (
            text_box
            for text_box in task.all_texts
            if _clean_match(text_box.name, continue_text)
            and continue_region[0]
            <= (text_box.x + text_box.width / 2) / task.width
            <= continue_region[2]
            and continue_region[1]
            <= (text_box.y + text_box.height / 2) / task.height
            <= continue_region[3]
        ),
        None,
    )
    if box:
        task.log_info("检测到下一步操作，点击继续")
        task.click_box(box)
        task.sleep(1)
        return True
    return False


def handle_confirm(task: TriggerTask):
    """通用"确认"按钮。"""
    confirm_region = (0.267, 0.867, 0.991, 0.979)
    box = next(
        (
            text_box
            for text_box in task.all_texts
            if _clean_match(text_box.name, "确认")
            and confirm_region[0]
            <= (text_box.x + text_box.width / 2) / task.width
            <= confirm_region[2]
            and confirm_region[1]
            <= (text_box.y + text_box.height / 2) / task.height
            <= confirm_region[3]
        ),
        None,
    )
    if box:
        if is_button_active(task, box):
            task.log_info("检测到确认操作，点击确认")
            task.click_box(box)
            task.sleep(1)
            return True
        else:
            task.log_info("确认按钮未激活（灰色），跳过点击")
            return False
    return False

def handle_convert(task: TriggerTask):
    """通用"转换"按钮: 按钮激活则点击转换，未激活则点击跳过(0.776,0.926)。"""
    box = find_box_at_point(task, 0.945, 0.918)
    if box and _clean_match(box.name, "转换"):
        if is_button_active(task, box):
            task.log_info("检测到转换按钮，点击转换")
            task.click_box(box)
            task.sleep(1)
            return True
        else:
            task.log_info("转换按钮未激活（灰色），点击跳过")
            _move_and_click(task, 0.776, 0.926)
            task.sleep(1)
            return True
    return False

def handle_remove(task: TriggerTask):
    """通用"移除"按钮。"""
    box = find_box_at_point(task, 0.945, 0.918)
    if box and _clean_match(box.name, "移除"):
        if is_button_active(task, box):
            task.log_info("检测到移除操作，点击移除")
            task.click_box(box)
            removed_count = max(
                1,
                getattr(task, "_pending_removed_card_count", 0),
            )
            _record_removed_cards(task, removed_count)
            task._pending_removed_card_count = 0
            task.sleep(1)
            return True
        else:
            task.log_info("移除按钮未激活（灰色），跳过点击")
            return False
    return False

def handle_three_choice_card_remove(task: TriggerTask):
    """三选一卡牌移除页面：点击指定区域内已激活的“移除”按钮。"""
    region = (0.507, 0.889, 0.740, 0.967)
    remove_box = next(
        (
            box for box in task.all_texts
            if region[0] <= (box.x + box.width / 2) / task.width <= region[2]
            and region[1] <= (box.y + box.height / 2) / task.height <= region[3]
            # 按钮就是「移除」两个字；事件选项「说服先知移除1张所选卡牌」也落在这块，别当成按钮
            # （2026-10-25 实录点了选项文字还记了一次移除，PT 账多算 20）
            and "移除" in box.name and len(box.name.strip()) <= 4
        ),
        None,
    )
    if not remove_box:
        return False
    if not is_button_active(task, remove_box):
        task.log_info("三选一卡牌移除页面的移除按钮未激活（灰色），跳过点击")
        return False

    task.log_info("检测到三选一卡牌移除页面，点击移除")
    task.click_box(remove_box)
    _record_removed_cards(task, 1)
    task._pending_removed_card_count = 0
    return True

def handle_flash(task: TriggerTask):
    """通用"闪光"按钮。"""
    box = find_box_at_point(task, 0.945, 0.918)
    if box and _get_game_text(task, '闪光') in box.name:
        if is_button_active(task, box):
            task.log_info("检测到闪光操作，点击闪光")
            task.click_box(box)
            task.sleep(1)
            return True
        else:
            task.log_info("闪光按钮未激活（灰色），跳过点击")
            return False
    return False

def handle_reflash(task: TriggerTask):
    """通用"重新闪光"按钮。"""
    box = find_box_at_point(task, 0.945, 0.918)
    if box and _get_game_text(task, '重新闪光') in box.name:
        if is_button_active(task, box):
            task.log_info("检测到重新闪光操作，点击重新闪光")
            task.click_box(box)
            task.sleep(2)
            return True
        else:
            task.log_info("重新闪光按钮未激活（灰色），跳过点击")
            return False
    return False

def handle_grant_flash(task: TriggerTask):
    """通用"赋予闪光"按钮。"""
    box = find_box_at_point(task, 0.945, 0.918)
    if box and _clean_match(box.name, "赋予闪光"):
        if is_button_active(task, box):
            task.log_info("检测到赋予闪光操作，点击赋予闪光")
            task.click_box(box)
            task.sleep(1)
            return True
        else:
            task.log_info("赋予闪光按钮未激活（灰色），跳过点击")
            return False
    return False

def handle_copy(task: TriggerTask):
    """通用"复制"按钮。"""
    box = find_box_at_point(task, 0.945, 0.918)
    if box and _clean_match(box.name, "复制"):
        if is_button_active(task, box):
            task.log_info("检测到复制操作，点击复制")
            task.click_box(box)
            task.sleep(1)
            return True
        else:
            task.log_info("复制按钮未激活（灰色），跳过点击")
            return False
    return False

def handle_enter(task: TriggerTask):
    """通用"进入"按钮。"""
    enter_region = (0.017, 0.771, 0.996, 0.992)
    box = next(
        (
            text_box
            for text_box in task.all_texts
            if _clean_match(text_box.name, "进入")
            and enter_region[0]
            <= (text_box.x + text_box.width / 2) / task.width
            <= enter_region[2]
            and enter_region[1]
            <= (text_box.y + text_box.height / 2) / task.height
            <= enter_region[3]
        ),
        None,
    )
    if box:
        task.log_info("检测到进入按钮，点击进入")
        task.click_box(box)
        reset_mission_status(task)
        task.sleep(1)
        return True
    return False

def handle_equipment_recast(task: TriggerTask):
    """装备重铸页面: 点击确认重铸。"""
    box = find_box_at_point(task, 0.501, 0.128)
    if box and _get_game_text(task, '装备重铸') in box.name:
        task.log_info("检测到装备重铸页面，点击跳过")
        _move_and_click(task, 0.749, 0.932)
        task.sleep(1)
        return True
    return False


def _chaos_strategy_state(task: TriggerTask):
    """给 chaos_strategy 打分用的本局进度。"""
    node_status = getattr(task, "node_status", {}) or {}
    plan = getattr(task, "chaos_plan", None) or {}
    removed = node_status.get("removed_card_count", 0)
    hp = _get_current_hp_percent(task)
    return {
        "removed": removed,
        "credit": _get_current_credit(task),
        "hp_pct": hp if hp is not False else 100,
        "seen": getattr(task, "chaos_seen", set()),
        "need_remove": max(0, len(plan.get("remove", [])) - removed),
        "need_copy": max(0, len(plan.get("copy", [])) - node_status.get("copy_count", 0)),
        "need_spark": len(plan.get("flash", [])),
        "need_god_spark": sum(1 for c in plan.get("flash", []) if c.get("god_spark")),
        "god_spark_wanted": len(_god_spark_wanted(task)),
        "need_neutral": len(plan.get("neutral", [])),
        "pending_meditation": sum(1 for v in _member_deck_state(task).get("冥想", {}).values() if v),
        "target_equipment": [n for slot in range(3) for n in _equipment_priority(task, slot)],
        "copy_count": node_status.get("copy_count", 0),
        "pt_room": (task.chaos_pt_cap - _pt_used(task)) if getattr(task, "chaos_pt_cap", None) else None,
    }


def _same_option_text(a, b):
    """抬起后的选项文字和刚选的是不是同一个（OCR 会抖：「1守望先知加40…」/「守望先知…」）。"""
    if not a or not b:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.7


def _pick_event_by_strategy(task: TriggerTask, tasks_info, click_event_option):
    """选了卡厄思玩法时，用事件库 + 选项文字给选项打分，点分数最高的；原有逻辑返回 False 交给关键词匹配。"""
    mode = getattr(task, "chaos_mode", chaos_strategy.MODE_LEGACY)
    if mode == chaos_strategy.MODE_LEGACY or not tasks_info:
        return False
    descs = [t["description"] for t in tasks_info]
    best, results = chaos_strategy.pick_event_option(descs, mode, _chaos_strategy_state(task))
    for t, (score, why, src, _oid) in zip(tasks_info, results):
        task.log_info(f"[{mode}] 事件选项「{t['description']}」{score:+.1f} ({src}; {' '.join(why) or '无效果'})")
    if best is None:
        return False
    if all(src == "文字解析" and not why for _s, why, src, _o in results):
        task.log_info("事件库未命中且选项文字里没有可识别的效果，交给原有关键词匹配")
        return False
    option_id = results[best][3]
    # 「选过的选项」不分玩法都记：第一次选中的选项才加探索度，刷存档时选过的之后探索也不算新（用户 2026-10-24）
    seen = getattr(task, "chaos_seen", None)
    keys = chaos_strategy.option_seen_keys(tasks_info[best]["description"], option_id)
    if seen is not None and not set(keys) <= seen:
        seen.update(keys)
        chaos_strategy.save_seen(seen)
    task.log_info(f"[{mode}] 选择「{tasks_info[best]['description']}」")
    # 选了神闪选项（只能选它、或分数仍最高时）：之后的选卡页/变体页要跳过，避免神闪落到目标卡上
    task.node_status["god_spark_pending"] = any("神闪" in w for w in results[best][1])
    chaos_trace.step(task, "event", results[best][2], task.frame, chosen=best,
                     options=[{"desc": d, "score": round(sc, 1), "why": why, "src": src}
                              for d, (sc, why, src, _o) in zip(descs, results)])
    click_event_option(tasks_info[best])
    task.sleep(1)
    return True


def handle_event_task(task: TriggerTask):
    """事件任务页面: 识别事件选项特征和描述，按任务优先级选择推进。"""
    bottom_box = find_box_at_point(task, 0.516, 0.971)
    if bottom_box and re.search(r'\d+/\d+', bottom_box.name):
        return False
    # 存档页（正在保存战斗数据 / 存储数据收集完成）的 TB 数字滚动时会被事件图标误命中（2026-10-25 实录点了「18T」）
    if any(NOT_EVENT_PAGE.search(b.name) for b in task.all_texts):
        return False

    rewards = task.find_feature(feature_name="taskreward")
    if rewards:
        reward = rewards[0]
        cx = (reward.x + reward.width / 2) / task.width
        cy = (reward.y + reward.height / 2) / task.height
        if 0.437 <= cx <= 0.902 and 0.350 <= cy <= 0.614:
            task.log_info("检测到任务奖励图标，优先点击")
            task.click_box(reward)
            return True

    tasks_info = recognize_event_options(task, page="事件任务页面")
    if not tasks_info:
        return False
    # 选项有入场动画：刚出现时只识别到 1 个就打分会错过后面的（2026-10-24 实录：只看到「拒绝触碰」就选了，
    # 漏了没拿过的装备[模仿之手]）。按策略选之前隔一会儿再认一次，个数不变才算稳定
    if (getattr(task, "chaos_mode", chaos_strategy.MODE_LEGACY) != chaos_strategy.MODE_LEGACY
            and all(t["y"] >= 0.925 for t in tasks_info)):
        for _ in range(3):
            task.sleep(0.6)
            task.next_frame()
            again = recognize_event_options(task, page="事件任务页面（稳定确认）")
            if len(again) == len(tasks_info):
                break
            tasks_info = again
        if not tasks_info:
            return False

    selectable_tasks = []
    for task_info in tasks_info:
        event_x = task_info["x"]
        event_y = task_info["y"]
        forbidden_region = (
            max(0.0, event_x - 0.131),
            max(0.0, event_y - 0.257),
            min(1.0, event_x - 0.090),
            min(1.0, event_y - 0.189),
        )
        forbidden_feature = task.find_one(
            feature_name="forbidden_event",
            box=task.box_of_screen(*forbidden_region),
        )
        if forbidden_feature:
            task.log_info(
                f"事件选项已被禁止，过滤描述「{task_info['description']}」，"
                f"forbidden_event相似度={forbidden_feature.confidence:.4f}"
            )
            continue
        selectable_tasks.append(task_info)
    tasks_info = selectable_tasks
    if not tasks_info:
        task.log_info("事件任务页面的所有选项均被禁止，跳过本次选择")
        return False

    check_region = task.box_of_screen(0.396, 0.286, 0.960, 0.718)
    check_features = [
        feature
        for feature_name in ("check", "check2")
        if (feature := task.find_one(feature_name=feature_name, box=check_region))
    ]
    check_feature = max(
        check_features,
        key=lambda feature: feature.confidence,
        default=None,
    )
    if check_feature:
        task.log_info(
            f"事件任务页面检测到check特征，相似度={check_feature.confidence:.4f}，优先点击"
        )
        task.click_box(check_feature)
        task.sleep(1)
        return True

    def click_event_option(event_task):
        # 记下点的是哪个：下一帧它抬起来时才按「已选中」直接确认（所有分支——策略、就此离开、关键词——都经过这里）
        task.node_status["event_pending_choice"] = event_task["description"]
        left, top, right, bottom = event_task["description_region"]
        description_x = (left + right) / 2
        description_y = (top + bottom) / 2
        _move_and_click(task, description_x, description_y)

    # 已经进过「精密加工记忆」页面后，优先选择「就此离开」结束事件，避免反复进入造成死循环
    event_status = getattr(task, "node_status", {})
    if event_status.get("precision_memory_visited"):
        leave_task = next(
            (task_info for task_info in tasks_info if "就此离开" in task_info["description"]),
            None,
        )
        if leave_task is not None:
            task.log_info("已进入过精密加工记忆，选择「就此离开」结束事件")
            click_event_option(leave_task)
            event_status["precision_memory_visited"] = False
            task.sleep(1)
            return True

    def handle_initial_node_task(description_keyword, purpose):
        """初始节点按描述选择任务；未找到目标描述时点击ESC重新开始。"""
        matched_task = next(
            (
                task_info
                for task_info in tasks_info
                if description_keyword in task_info["description"]
            ),
            None,
        )
        if matched_task:
            task.log_info(
                f"{purpose}：选择包含“{description_keyword}”的事件任务"
            )
            click_event_option(matched_task)
        else:
            task.log_info(
                f"{purpose}：未找到包含“{description_keyword}”的事件任务，"
                "点击ESC重新开始"
            )
            _move_and_click(task, 0.959, 0.053)
        task.sleep(1)
        return True

    # 检查任务区域中是否有 treasure、memoryshards、data_of_light 或 eyes 特征
    treasure_box = task.box_of_screen(0.084, 0.121, 0.991, 0.762)
    reward_features = task.find_feature(
        feature_name=["treasure", "memoryshards", "data_of_light", "eyes"],
        box=treasure_box,
        threshold=0.7,
    )
    if reward_features:
        task.log_info(f"检测到事件任务区域中有{reward_features[0].name}特征，优先点击")
        reward_feature = reward_features[0]
        _move_and_click(
            task,
            (reward_feature.x + reward_feature.width / 2) / task.width,
            (reward_feature.y + reward_feature.height / 2) / task.height,
        )
        task.sleep(2)
        return True

    upper_event_task = next(
        (task_info for task_info in tasks_info if task_info["y"] < 0.925),
        None,
    )
    # 选了卡厄思玩法时，只有抬起的正是策略刚选的选项才直接确认：有的事件选项本来就排得高（2026-10-24 实录
    # 「守望/拯救/回答先知」），会被当成已选中直接点掉，绕过打分
    if (upper_event_task is not None
            and getattr(task, "chaos_mode", chaos_strategy.MODE_LEGACY) != chaos_strategy.MODE_LEGACY
            and len(tasks_info) > 1
            and not _same_option_text(upper_event_task["description"], task.node_status.get("event_pending_choice"))):
        upper_event_task = None
    if upper_event_task is not None:
        task.log_info(
            f"检测到Y坐标小于0.925的任务，立即选择: {upper_event_task['description']}"
        )
        click_event_option(upper_event_task)
        task.sleep(1)
        return True

    initial_card_name = _get_config_value(task, "刷初始卡牌", "")
    initial_card_name = initial_card_name.strip() if isinstance(initial_card_name, str) else ""
    node_status = getattr(task, "node_status", {})
    is_initial_node = (
        node_status.get("pass_final_boss_count", 0) == 0
        and node_status.get("node_count", 0) == 0
    )
    reroll_empty_deck = _get_config_value(task, "刷空档", False)
    if initial_card_name and reroll_empty_deck is True and is_initial_node:
        task.log_info(
            "“刷初始卡牌”和“刷空档”不能同时进行，"
            "本轮优先执行“刷初始卡牌”"
        )
    if initial_card_name and is_initial_node:
        return handle_initial_node_task(
            "传说卡牌",
            f"刷初始卡牌「{initial_card_name}」",
        )

    if reroll_empty_deck is True and is_initial_node:
        return handle_initial_node_task("移除2张", "刷空档")

    if _pick_event_by_strategy(task, tasks_info, click_event_option):
        return True

    # 读取拉黑任务列表
    blacklist = _get_config_value(task, '拉黑任务', ["咒术卡牌"])
    blacklist = list(blacklist) if isinstance(blacklist, (list, tuple)) else []
    if blacklist:
        # 过滤掉描述包含拉黑关键词的任务
        filtered_tasks = [
            t for t in tasks_info
            if not any(is_subsequence(bk, t['description']) for bk in blacklist)
        ]
        if len(filtered_tasks) < len(tasks_info):
            task.log_info(f"拉黑任务关键词: {blacklist}，过滤前{len(tasks_info)}个，过滤后{len(filtered_tasks)}个")
            for t in tasks_info:
                if t not in filtered_tasks:
                    task.log_info(f"  已拉黑: 描述: {t['description']}")
        # 如果全部被拉黑，兜底用原列表
        if not filtered_tasks:
            task.log_info("所有任务均被拉黑，兜底使用原列表")
            filtered_tasks = tasks_info
        tasks_info = filtered_tasks

    equipment_priority = []
    for slot in range(1, 4):
        equipment_priority.extend(
            _get_card_list(task, f"装备{slot}号位优先级")
        )
    priority = [
        *equipment_priority,
        *_get_card_list(task, "任务优先级"),
    ]
    chosen = None
    for keyword in priority:
        for t in tasks_info:
            if is_subsequence(keyword, t['description']):
                chosen = t
                task.log_info(f"优先选择「{keyword}」-> 描述: {t['description']}")
                break
        if chosen is not None:
            break

    if chosen is None and task.name == "自动卡厄思模式":
        attack_event_features = task.find_feature(
            feature_name="attack_event",
            threshold=0.95,
        ) or []
        if attack_event_features:
            attack_event = max(
                attack_event_features,
                key=lambda feature: feature.confidence,
            )
            task.log_info(
                f"未命中任务优先级，检测到attack_event特征，"
                f"相似度={attack_event.confidence:.4f}，点击进入战斗任务"
            )
            task.click_box(attack_event)
            task.sleep(1)
            return True

    if chosen is None:
        chosen = random.choice(tasks_info)
        task.log_info(
            f"未命中优先级描述，从{len(tasks_info)}个可选任务中随机选择: "
            f"{chosen['description']}"
        )

    click_event_option(chosen)
    task.sleep(1)
    return True


def _track_layer_route(task: TriggerTask, map_info, route_plan):
    """每层第一次进路线页时把整层地图建好图、算出整条最佳路径记下来，之后每一步核对还在不在这条路上。

    路径用「类型+特殊标记」序列表示（节点 id 每帧重新编号，不能跨帧比较）。
    和计划对不上（小地图没显示完整、识别漏了节点）时按新识别的图重新规划并在日志里写明。
    """
    node_status = getattr(task, "node_status", None)
    if not isinstance(node_status, dict) or not route_plan:
        return
    node_by_id = {node["id"]: node for node in map_info.get("nodes", [])}

    def describe(node_id):
        node = node_by_id[node_id]
        specials = sorted(item["feature_name"].removesuffix("_in_map") for item in node.get("special_features", []))
        return node["type"] + (f"[{'/'.join(specials)}]" if specials else "")

    steps = [describe(node_id) for node_id in route_plan["route"][1:]]
    layer = node_status.get("pass_final_boss_count", 0)
    plan = node_status.get("layer_route")
    if plan and plan["layer"] == layer:
        remaining = plan["steps"][plan["done"]:]
        common = min(len(steps), len(remaining))
        if common and steps[:common] == remaining[:common]:
            # 小地图只显示一段，往前走会露出后面的节点：前缀一致就算还在计划上，把露出来的部分接到计划后面
            if len(steps) > len(remaining):
                plan["steps"] += steps[len(remaining):]
                task.log_info(f"第{layer + 1}层地图露出更多节点，计划延长为 {plan['steps'][plan['done']:]}")
            task.log_info(f"第{layer + 1}层按计划走第{plan['done'] + 1}/{len(plan['steps'])}步：{steps[0]}")
            plan["done"] += 1
            return
        task.log_info(f"第{layer + 1}层地图和计划不一致，按新识别的图重新规划：计划剩余={remaining}，新路线={steps}")
    else:
        task.log_info(
            f"第{layer + 1}层建图：{len(map_info.get('nodes', []))}个节点，"
            f"{len(map_info.get('connections', []))}条连线，最佳路线={steps}（总分{route_plan['weighted_score']}）"
        )
    node_status["layer_route"] = {"layer": layer, "steps": steps, "done": 1}


def is_route_selection_page(task: TriggerTask):
    position_box = task.box_of_screen(0.335, 0.568, 0.453, 0.751)
    position_feature = task.find_feature(feature_name="position", box=position_box)
    cant_receive = find_box_at_point(task, 0.186, 0.850)
    return bool(position_feature or (cant_receive and "无法接收到梦境号" in cant_receive.name))


def handle_route_selection(task: TriggerTask):
    """路线选择页面: 识别节点类型，按优先级排序后依次点击所有节点，每次间隔1秒。
    同时负责节点计数：离开路线页面时 node_count +1。"""
    is_route_page = is_route_selection_page(task)

    # 如果当前页面不是路线选择页面，但 enter_new_node 为 True（刚离开路线页面），计数+1
    if not is_route_page:
        if hasattr(task, 'node_status') and task.node_status.get('enter_new_node', False):
            task.node_status['enter_new_node'] = False
            task.node_status['node_count'] += 1
            task.node_status['precision_memory_visited'] = False
            task.node_status['pt_panel_read'] = False
            task.log_info(f"离开路线选择页面，当前节点计数: {task.node_status['node_count']}")
        return False

    # 是路线选择页面，标记进入新节点
    if hasattr(task, 'node_status'):
        task.node_status['enter_new_node'] = True

    task.log_info("检测到路线选择页面，按优先级依次点击节点")

    # 更新节点状态：进入路线选择页面时 flash_or_rest 置为 True
    if hasattr(task, 'node_status'):
        task.node_status['flash_or_rest'] = True
        task.node_status['rest_page_frames'] = 0
        task.node_status['training_logged'] = False
        task.node_status['training_clicks'] = 0
        task.node_status['meditate_tries'] = 0
        # 离开休息点了：训练状态作废，免得在别的页面点「确认」（2026-10-25 实录在装备页点了确认）
        task.node_status['training_pending'] = None
        task.node_status['training_member_clicked'] = False
        task.log_info("检测到路线选择页面，更新 node_status['flash_or_rest']=True")
        # 检查"进入商店"配置，若为 True 则同时更新 shop 状态
        if _get_config_value(task, '进入商店', False):
            task.node_status['shop'] = True
            task.log_info(f"进入商店配置为True，更新 node_status['shop']=True")
        # 刷存档：每到选路页读一次游戏里的 PT（模糊的记忆），PT 账以它为准
        if _avoid_god_spark(task) and not task.node_status.get('pt_panel_read'):
            task.node_status['pt_panel_read'] = True
            read_member_panel(task)
    task.sleep(1)

    route_box = task.box_of_screen(0.656, 0.053, 0.977, 0.908)
    node_feature_types = {
        "safezone": "休息",
        "enemy": "小怪",
        "elite": "精英",
        "event": "事件",
        "settlement": "结算",
    }
    nodes = []
    for feature_name, node_type in node_feature_types.items():
        for feature_box in task.find_feature(feature_name=feature_name, box=route_box):
            nodes.append({
                "feature_name": feature_name,
                "node_type": node_type,
                "box": feature_box,
                "special_features": [],
            })

    # 找不到任何普通节点类型特征时，当前路线节点即为boss。
    # 例外：整层路线计划下一步不是首领（2026-10-24 实录：活动卡厄思两个橙色旗子的「结算」航点认不出，被当成首领，
    # 结算时把层数多加了 1）。这时照样点中间的节点，但不标记到达首领。计划的最后一步总是首领（扫描偶尔把首领认成小怪）。
    plan = (getattr(task, "node_status", None) or {}).get("full_route")
    if (not nodes and plan and plan["layer"] == task.node_status.get("pass_final_boss_count", 0)
            and plan["done"] < len(plan["steps"]) - 1 and plan["steps"][plan["done"]]["type"] != "首领"):
        step = plan["steps"][plan["done"]]
        plan["done"] += 1
        task.log_info(f"路线页没识别到节点特征，整层路线下一步是{step['type']}（不是首领），点中间的节点进入")
        _move_and_click(task, 0.815, 0.492)
        task.sleep(2)
        return True
    if not nodes:
        task.log_info("检测到最终boss节点，点击进入")
        if hasattr(task, 'node_status'):
            task.node_status['reach_final_boss'] = True
            task.node_status['node_type'] = "boss"

        # 检查"第几层boss前自动暂停"配置
        pause_config = _get_config_value(task, '第几层boss前自动暂停', "不暂停")
        if pause_config != "不暂停":
            try:
                pause_layer = int(pause_config)
                current_layer = task.node_status.get('pass_final_boss_count', 0)
                if pause_layer - 1 == current_layer:
                    _wait_before_boss(task, pause_layer)
            except (ValueError, TypeError):
                pass

        _move_and_click(task, 0.815, 0.492)
        task.sleep(2)
        return True

    def relative_center(box):
        return (
            (box.x + box.width / 2) / task.width,
            (box.y + box.height / 2) / task.height,
        )

    # 特殊特征优先级：负数高于普通节点，正数低于普通节点。
    special_feature_priorities = {
        "shop": -1,
        "kalei": -1,
        "seal": -1,
        "hard": 1,
    }

    # 每个特殊特征只归属到距离最近的一个节点类型特征。
    for special_name in special_feature_priorities:
        for special_box in task.find_feature(feature_name=special_name, box=route_box):
            special_x, special_y = relative_center(special_box)
            nearest_node = min(
                nodes,
                key=lambda node: (
                    (relative_center(node["box"])[0] - special_x) ** 2
                    + (relative_center(node["box"])[1] - special_y) ** 2
                ),
            )
            nearest_node["special_features"].append(special_name)
            task.log_info(
                f"特殊特征「{special_name}」分配给"
                f"「{nearest_node['node_type']}」节点"
            )

    priority = _get_route_priority(task)
    task.log_info(f"路线优先级配置: {priority}")
    task.log_info(
        f"识别到的路线节点: "
        f"{[(node['node_type'], node['special_features']) for node in nodes]}"
    )

    priority_index = {node_type: index for index, node_type in enumerate(priority)}

    def sort_key(node):
        # 商店节点是固定最高优先级，不受用户配置的节点类型顺序影响。
        shop_priority = 0 if "shop" in node["special_features"] else 1
        if node["node_type"] == "结算":
            type_priority = len(priority) + 1
        else:
            type_priority = priority_index.get(node["node_type"], len(priority))
        special_priority = min(
            (special_feature_priorities[name] for name in node["special_features"]),
            default=0,
        )
        center_x, center_y = relative_center(node["box"])
        return shop_priority, type_priority, special_priority, center_y, center_x

    visible_nodes = sorted(nodes, key=lambda item: relative_center(item["box"])[1])
    node = _follow_full_map_plan(task, visible_nodes, priority)
    if node is not None:
        _click_route_node(task, node)
        return True

    # 先根据左下角小地图的完整连通关系规划路线，再用右侧当前可点击节点
    # 校验规划结果。两边识别不一致时，使用当前节点识别结果兜底。
    map_info = recognize_map_connections(task)
    route_weights = _chaos_route_weights(task)
    route_plan = find_best_map_route_by_priority(map_info, priority, route_weights)
    _track_layer_route(task, map_info, route_plan)
    node = None
    if route_plan and route_plan["next_row"] is not None:
        planned_index = route_plan["next_row"] - 1
        if 0 <= planned_index < len(visible_nodes):
            planned_node = visible_nodes[planned_index]
            expected_specials = {
                name.removesuffix("_in_map")
                for name in route_plan["next_special_features"]
            }
            actual_specials = set(planned_node["special_features"])
            type_matches = (
                planned_node["node_type"] == route_plan["next_node_type"]
            )
            specials_match = actual_specials == expected_specials
            task.log_info(
                f"小地图规划路线={route_plan['route']}，"
                f"下一列第{route_plan['next_row']}个节点，"
                f"预计={route_plan['next_node_type']}+{sorted(expected_specials)}，"
                f"当前节点识别={planned_node['node_type']}+{sorted(actual_specials)}"
            )
            if type_matches and specials_match:
                node = planned_node
                task.log_info("小地图规划与当前节点识别一致，按规划结果进入")
            else:
                task.log_info(
                    "小地图规划与当前节点识别不一致，"
                    "改用当前节点的路线优先级兜底选择"
                )
        else:
            task.log_info(
                f"小地图规划要求进入下一列第{route_plan['next_row']}个节点，"
                f"但当前仅识别到{len(visible_nodes)}个节点，改用优先级兜底"
            )
    else:
        task.log_info("小地图路线规划失败，改用当前节点的路线优先级兜底")

    if node is None:
        node = sorted(nodes, key=sort_key)[0]

    _click_route_node(task, node)
    return True


def _chaos_route_weights(task: TriggerTask):
    """当前玩法的路线权重，按本层血量和「目标装备只能靠本层事件拿」调整（chaos_strategy.route_weights）。"""
    mode = getattr(task, "chaos_mode", "")
    if mode not in chaos_strategy.ROUTE_WEIGHTS:
        return None
    layer = task.node_status.get("pass_final_boss_count", 0) if isinstance(getattr(task, "node_status", None), dict) else 0
    try:
        hp = _get_current_hp_percent(task)
    except Exception:  # noqa: BLE001
        hp = None
    bonus = 0
    try:
        targets = [n for slot in range(3) for n in _equipment_priority(task, slot)]
        owned = [n for n in _equipment_state(task).get("names", []) if n]
        seen = getattr(task, "chaos_seen", None) or set()
        owned += [n for n in targets if chaos_strategy.equipment_key(n) in seen]
        sources = chaos_strategy.equipment_event_sources(targets)
        bonus = chaos_strategy.event_source_bonus(sources, layer, owned)
        if bonus:
            task.log_info(f"本层有目标装备的来源事件（{[s['equipment'] + '←' + s['event'] for s in sources]}），事件节点 +{bonus}")
    except Exception as e:  # noqa: BLE001
        task.log_info(f"目标装备来源事件加权失败: {e}")
    octopus = _get_config_value(task, OCTOPUS_RUSH, False) is True
    if octopus and layer == 0:
        task.log_info("章鱼哥速刷：第一层普通战优先")
    return chaos_strategy.route_weights(mode, layer, hp, bonus, octopus=octopus)


BOSS_PAUSE_FILE = os.path.join("dev_out", "paused_before_boss")


def _wait_before_boss(task: TriggerTask, layer):
    """首领前暂停：建一个标记文件，等它被删掉再进首领（无界面运行也能远程继续；每层只停一次）。"""
    key = (task.node_status.get("total_rounds", 0), layer)
    if task.node_status.get("boss_paused") == key:
        return
    task.node_status["boss_paused"] = key
    os.makedirs("dev_out", exist_ok=True)
    with open(BOSS_PAUSE_FILE, "w", encoding="utf-8") as f:
        f.write(f"第{layer}层首领前暂停，删除本文件继续\n")
    task.log_info(f"第{layer}层首领前暂停：删除 {BOSS_PAUSE_FILE} 后继续")
    while os.path.exists(BOSS_PAUSE_FILE):
        task.sleep(2)
    task.log_info("首领前暂停结束，继续")
    task.next_frame()


def _click_route_node(task: TriggerTask, node):
    # 更新 node_type 为最优先的节点类型
    if hasattr(task, 'node_status'):
        task.node_status['node_type'] = node["node_type"]
        task.log_info(f"更新 node_type 为「{node['node_type']}」")

    box = node["box"]
    center_x = (box.x + box.width / 2) / task.width
    center_y = (box.y + box.height / 2) / task.height
    click_x = center_x - 0.095
    click_y = center_y - 0.0065
    task.log_info(
        f"点击{node['node_type']}节点"
        f"（特殊特征: {node['special_features']}，位置: {click_x:.3f}, {click_y:.3f}）"
    )
    _move_and_click(task, click_x, click_y)

    task.sleep(2)


def _plan_full_map(task: TriggerTask, priority):
    """打开全屏地图扫描整层、按玩法权重求整条最佳路径，存成每一步的「类型 + 在后继里从上往下的名次」。"""
    import chaos_map
    info = chaos_map.scan_layer(task)
    if not info:
        task.log_info("全屏地图扫描失败（没认出当前位置或节点），改用小地图规划")
        return None
    weights = _chaos_route_weights(task)
    plan = find_best_map_route_by_priority(info, priority, weights)
    if not plan or len(plan["route"]) < 2:
        return None
    by_id = {n["id"]: n for n in info["nodes"]}
    steps = []
    for prev, cur in zip(plan["route"], plan["route"][1:]):
        succ = sorted(info["adjacency"].get(prev, []), key=lambda i: by_id[i]["row"])
        steps.append({"type": by_id[cur]["type"], "rank": succ.index(cur) + 1, "options": len(succ),
                      "shop": bool(by_id[cur]["special_features"])})
    layer = task.node_status.get("pass_final_boss_count", 0)
    chaos_trace.route_plan(task, info, plan, steps)
    task.log_info(
        f"第{layer + 1}层整层路线（总分{plan['weighted_score']}）："
        + " → ".join(f"{st['type']}{'[商店]' if st['shop'] else ''}" for st in steps)
    )
    return {"layer": layer, "steps": steps, "done": 0}


def _follow_full_map_plan(task: TriggerTask, visible_nodes, priority):
    """选了卡厄思玩法时：每层第一次进路线页扫全屏地图定好整条路，之后每步按计划点；对不上就重扫一次，再不行交给小地图逻辑。"""
    if getattr(task, "chaos_mode", chaos_strategy.MODE_LEGACY) == chaos_strategy.MODE_LEGACY:
        return None
    node_status = getattr(task, "node_status", None)
    if not isinstance(node_status, dict) or not visible_nodes:
        return None
    layer = node_status.get("pass_final_boss_count", 0)
    for attempt in range(2):
        plan = node_status.get("full_route")
        if attempt or not plan or plan["layer"] != layer or plan["done"] >= len(plan["steps"]):
            plan = _plan_full_map(task, priority)
            node_status["full_route"] = plan
            if not plan:
                return None
        step = plan["steps"][plan["done"]]
        index = step["rank"] - 1
        candidate = visible_nodes[index] if index < len(visible_nodes) else None
        count_ok = len(visible_nodes) == step["options"]
        type_ok = candidate is not None and (step["type"] == "首领" or candidate["node_type"] == step["type"])
        if candidate is not None and count_ok and type_ok:
            plan["done"] += 1
            task.log_info(
                f"第{layer + 1}层按整层路线走第{plan['done']}/{len(plan['steps'])}步："
                f"{step['type']}（{len(visible_nodes)}个可选里从上往下第{step['rank']}个）"
            )
            return candidate
        task.log_info(
            f"整层路线第{plan['done'] + 1}步预计{step['type']}（{step['options']}选{step['rank']}），"
            f"实际可选={[n['node_type'] for n in visible_nodes]}，{'重新扫描' if attempt == 0 else '改用小地图规划'}"
        )
    node_status["full_route"] = None
    return None


def handle_obtain_reward(task: TriggerTask):
    """获得奖励页面: 点击领取。若此时 reach_final_boss 为 True，说明已通关关底boss，过层+1并重置层状态。"""
    box = find_box_at_point(task, 0.924, 0.922)
    if box and _clean_match(box.name, "获得"):
        task.log_info("检测到获得奖励页面，点击领取")
        task.click_box(box)
        task.sleep(1)
        return True
    return False


def handle_leave(task: TriggerTask):
    """离开按钮。"""
    box = find_box_at_point(task, 0.945, 0.918)
    if box and _clean_match(box.name, "离开"):
        # 休息区做完动作后金色气泡才冒出来，这时页面只剩「离开」（2026-10-25 20:58 漏点）：离开前先看几帧
        at_rest = any(t in b.name for b in task.all_texts or [] for t in ("休息", "冥想", "训练"))
        if at_rest and click_golden_card(task, frames=GOLDEN_CARD_FRAMES):
            return True
        if is_button_active(task, box):
            task.log_info("检测到离开按钮，点击离开")
            task.click_box(box)
            task.sleep(1)
            return True
        else:
            task.log_info("离开按钮未激活（灰色），跳过点击")
            return False
    return False
def handle_next_step(task: TriggerTask):
    """通用"下一步"按钮: 在区域(0.833,0.885,0.954,0.957)内检测文本，编辑距离<=2即匹配。"""
    x1, y1, x2, y2 = 0.833, 0.885, 0.954, 0.957
    for b in task.all_texts:
        cx = (b.x + b.width / 2) / task.width
        cy = (b.y + b.height / 2) / task.height
        if x1 <= cx <= x2 and y1 <= cy <= y2:
            if _edit_distance(b.name, "下一步", max_dist=2):
                task.log_info(f"检测到下一步按钮「{b.name}」，点击")
                task.click_box(b)
                task.sleep(1)
                return True
    return False


def handle_craft(task: TriggerTask):
    """合成按钮。"""
    box = find_box_at_point(task, 0.938, 0.903)
    if box and _clean_match(box.name, "合成"):
        if is_button_active(task, box):
            task.log_info("检测到合成按钮，点击合成")
            task.click_box(box)
            task.sleep(1)
            return True
        else:
            task.log_info("合成按钮未激活（灰色），跳过点击")
            return False
    return False

def handle_select(task: TriggerTask):
    """通用"选择"按钮。"""
    box = find_box_at_point(task, 0.945, 0.918)
    if box and _clean_match(box.name, "选择"):
        if is_button_active(task, box):
            task.log_info("检测到选择按钮，点击选择")
            task.click_box(box)
            task.sleep(1)
            return True
        else:
            task.log_info("选择按钮未激活（灰色），跳过点击")
            return False
    return False


def _find_rest_feature(task: TriggerTask):
    """在休息区域查找rest特征，命中时输出置信度。"""
    search_box = task.box_of_screen(0.157, 0.503, 0.467, 0.863)
    rest_feature = task.find_one(feature_name="rest", box=search_box)
    if rest_feature:
        task.log_info(f"检测到rest特征，匹配置信度: {rest_feature.confidence:.2%}")
    return rest_feature


def _wait_for_rest_confirm(task: TriggerTask):
    """等待休息操作后的确认按钮出现。"""
    confirm_boxes = task.wait_ocr(
        0.170, 0.554, to_x=0.855, to_y=0.769,
        match=re.compile(r"确认"), time_out=2,
    )
    if not confirm_boxes:
        task.log_info("等待休息确认按钮超时")
        return False
    return True


SPECIAL_FLASH_THRESHOLD = 0.7
GOLDEN_CARD_FRAMES = 4      # 金色气泡会一闪一闪，离开前多看几帧


_golden_templates = None
GOLDEN_CARD_REGION = (0.219, 0.208, 0.786, 0.814)
GOLDEN_CARD_SCORE = 0.65   # 自己做 TM_CCOEFF_NORMED：trace 实录真气泡 0.72～0.88，冥想金光/篝火最高 0.58


def _golden_card_templates():
    """金色卡牌气泡模板：取 coco 标注里 special_flash_luosi / luosi2 两张原图裁出来（1920×1080 坐标）。"""
    global _golden_templates
    if _golden_templates is None:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
        with open(os.path.join(base, "coco_annotations.json"), encoding="utf-8") as f:
            coco = json.load(f)
        cats = {c["id"]: c["name"] for c in coco["categories"]}
        files = {i["id"]: i["file_name"] for i in coco["images"]}
        out = []
        for a in coco["annotations"]:
            if cats.get(a["category_id"]) in ("special_flash_luosi", "special_flash_luosi2"):
                img = cv2.imread(os.path.join(base, files[a["image_id"]]))
                x, y, w, h = [int(v) for v in a["bbox"]]
                if img is not None:
                    out.append(img[y:y + h, x:x + w])
        _golden_templates = out
    return _golden_templates


def _find_golden_card(task: TriggerTask):
    """ok-script 的 find_one 对这个会闪的气泡给分偏低（实录 0.75 的图实时只有不到 0.7，2026-10-25 连漏三次），自己匹配。"""
    frame = getattr(task, "frame", None)
    if frame is None:
        return task.find_one(feature_name=["special_flash_luosi", "special_flash_luosi2"],
                             box=task.box_of_screen(*GOLDEN_CARD_REGION), threshold=SPECIAL_FLASH_THRESHOLD)
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = GOLDEN_CARD_REGION
    ox, oy = int(w * x1), int(h * y1)
    roi = frame[oy:int(h * y2), ox:int(w * x2)]
    if roi.ndim == 3 and roi.shape[2] == 4:
        roi = cv2.cvtColor(roi, cv2.COLOR_BGRA2BGR)
    scale = w / 1920
    best = None
    for tpl in _golden_card_templates():
        t = cv2.resize(tpl, None, fx=scale, fy=scale) if abs(scale - 1) > 0.01 else tpl
        if t.shape[0] > roi.shape[0] or t.shape[1] > roi.shape[1]:
            continue
        _, v, _, loc = cv2.minMaxLoc(cv2.matchTemplate(roi, t, cv2.TM_CCOEFF_NORMED))
        if best is None or v > best.confidence:
            best = SimpleNamespace(x=ox + loc[0], y=oy + loc[1], width=t.shape[1], height=t.shape[0], confidence=v)
    return best if best and best.confidence >= GOLDEN_CARD_SCORE else None


def click_golden_card(task: TriggerTask, frames=1):
    """休息区主战员头上的金色卡牌气泡＝灵光一闪，看到就点（用户 2026-10-25）。frames>1 时连看几帧（气泡有明暗动画）。"""
    for i in range(frames):
        if i:
            task.sleep(0.4)
            task.next_frame()
        found = _find_golden_card(task)
        if found:
            task.log_info(f"休息区有主战员头上的金色卡牌（灵光一闪），点开 置信度={found.confidence:.2f}")
            _move_and_click(task, (found.x + found.width / 2) / task.width, (found.y + found.height / 2) / task.height)
            task.sleep(1)
            return True
    return False


def handle_rest(task: TriggerTask):
    """休息界面: 根据血量、信用点和冥想状态选择休息或冥想。"""
    if any("卡牌奖励" in b.name for b in task.all_texts or []):
        return False                         # 训练后弹出的卡牌奖励交给 handle_card_reward
    # 主战员头上的金色卡牌气泡＝灵光一闪，要点（用户 2026-10-25）。
    # 实录 trace 里匹配度只有 0.75～0.88，默认阈值 0.8 常常漏掉（冥想点击的金光只有 0.5 左右）
    if click_golden_card(task):
        return True

    rest_feature = _find_rest_feature(task)
    free_text = _get_region_text(task, (0.154, 0.602, 0.359, 0.847))
    flash_or_rest = (
        hasattr(task, 'node_status')
        and task.node_status.get('flash_or_rest', False)
    )
    can_rest = bool(rest_feature and "免费" in free_text and flash_or_rest)

    meditation_region = (0.671, 0.433, 0.945, 0.801)
    meditate_feature = task.find_one(
        feature_name="meditate",
        box=task.box_of_screen(*meditation_region),
    )
    meditation_cost_boxes = [
        text_box for text_box in task.all_texts
        if re.fullmatch(r"\d+", text_box.name.strip())
        and meditation_region[0] <= (text_box.x + text_box.width / 2) / task.width <= meditation_region[2]
        and meditation_region[1] <= (text_box.y + text_box.height / 2) / task.height <= meditation_region[3]
    ]
    if meditate_feature and meditation_cost_boxes:
        feature_center = (
            meditate_feature.x + meditate_feature.width / 2,
            meditate_feature.y + meditate_feature.height / 2,
        )
        meditation_cost_box = min(
            meditation_cost_boxes,
            key=lambda text_box: (
                (text_box.x + text_box.width / 2 - feature_center[0]) ** 2
                + (text_box.y + text_box.height / 2 - feature_center[1]) ** 2
            ),
        )
        meditation_cost = int(meditation_cost_box.name.strip())
    else:
        meditation_cost = None

    meditation_state = _member_deck_state(task).get("冥想", {})
    has_pending_meditation = (
        isinstance(meditation_state, dict)
        and any(value is True for value in meditation_state.values())
    )
    current_credit = _get_current_credit(task)
    meditation_credit_threshold = _get_config_value(
        task, "多少信用点以上冥想", 300,
    )
    try:
        meditation_credit_threshold = int(meditation_credit_threshold)
    except (TypeError, ValueError):
        meditation_credit_threshold = 300
    if getattr(task, "chaos_mode", "") == chaos_strategy.MODE_TARGET and meditation_cost is not None:
        # 目标卡组：目标卡闪错了只能靠冥想重闪，钱够冥想就冥想，不用等到「多少信用点以上冥想」
        # （2026-10-25 实录：剑鸣九霄待冥想、269 信用点、冥想 80，因门槛 300 去休息了）
        # 冥想实际 80 信用点；费用数字 OCR 会认错（实录 80 认成 4），按至少 80 算
        # 冥想每用一次涨 40（实录 80→120→160→200），按本局已冥想次数估，OCR 读数只取更大的
        done = task.node_status.get('meditate_count', 0) if isinstance(task.node_status, dict) else 0
        meditation_cost = max(meditation_cost, MEDITATE_COST + MEDITATE_COST_STEP * done)
        meditation_credit_threshold = min(meditation_credit_threshold, meditation_cost)
    meditate_tries = task.node_status.get('meditate_tries', 0) if isinstance(task.node_status, dict) else 0
    can_meditate = bool(
        meditate_tries < 2                   # 同一休息点点了两次还在休息页（钱不够等），别死循环
        and flash_or_rest
        and meditate_feature
        and meditation_cost is not None
        and has_pending_meditation
        and current_credit >= meditation_credit_threshold
        and current_credit >= meditation_cost
    )

    train_box = find_text_in_region(task, r"^训练$", TRAIN_REGION)
    can_train = bool(flash_or_rest and train_box and find_text_in_region(task, r"免费", TRAIN_REGION))
    on_rest_page = any("安全区采取" in b.name for b in task.all_texts or [])

    pending = task.node_status.get('training_pending') if isinstance(task.node_status, dict) else None
    if pending and time.time() - pending < 8 and not can_train:
        # 刚点过训练，选战斗员页还没出来；这几秒里「训练」字样可能认不到，别改去点休息/冥想（2026-10-25 实录）
        task.sleep(0.5)
        return True

    if can_rest and can_train and not can_meditate:
        hp_percent = _get_current_hp_percent(task)
        if hp_percent is not False and hp_percent >= REST_HP_BELOW:
            # 血量够高时休息白白浪费，改用免费训练（2026-10-25 实录 100% 血还去休息）
            task.log_info(f"当前血量 {hp_percent}% ≥ {REST_HP_BELOW}%，不休息，改训练")
            can_rest = False

    if can_rest and can_meditate:
        hp_percent = _get_current_hp_percent(task)
        # 目标卡组：目标卡闪错了要靠冥想重闪，优先于休息（用户 2026-10-24），血量太低才休息
        rest_below = 25 if getattr(task, "chaos_mode", "") == chaos_strategy.MODE_TARGET else 50
        choose_rest = hp_percent is not False and hp_percent < rest_below
        task.log_info(
            f"休息与冥想均可用，当前血量="
            f"{hp_percent if hp_percent is not False else '未识别'}%，"
            f"选择{'休息' if choose_rest else '冥想'}"
        )
    else:
        choose_rest = can_rest

    if choose_rest:
        task.log_info("检测到休息界面，点击休息")
        task.move_relative(
            (rest_feature.x + rest_feature.width / 2) / task.width,
            (rest_feature.y + rest_feature.height / 2) / task.height,
        )
        task.click_box(rest_feature)
        if not _wait_for_rest_confirm(task):
            return True
        task.node_status['flash_or_rest'] = False
        return True

    if can_meditate:
        pending_cards = [
            name for name, pending in meditation_state.items() if pending is True
        ]
        task.log_info(
            f"检测到可冥想卡牌{pending_cards}，当前信用点={current_credit}，"
            f"冥想费用={meditation_cost}，点击冥想"
        )
        task.node_status['meditate_tries'] = meditate_tries + 1
        task.click_box(meditate_feature)
        if not _wait_for_rest_confirm(task):
            return True
        task.node_status['flash_or_rest'] = False
        return True

    if can_train:
        # 训练（免费）：所选战斗员所有能力值 +1；休息/冥想都不选时用掉，不白跳过（2026-10-25 实录两次直接跳过）
        # 入场动画期点训练可能没反应（2026-10-25 实录）：选战斗员页出现前一直还在休息页，就隔几秒再点，最多 3 次；
        # flash_or_rest 等选中战斗员后再清（handle_training_select）
        ns = task.node_status
        last = ns.get('training_pending') or 0
        if time.time() - last < 2.5:
            task.sleep(0.5)
            return True
        clicks = ns.get('training_clicks', 0)
        if clicks < 3:
            task.log_info("休息/冥想不需要或不可用，点击免费「训练」（选目标主战员）"
                          + (f"（第 {clicks + 1} 次）" if clicks else ""))
            task.click_box(train_box)
            task.sleep(1.5)
            ns['training_pending'] = time.time()
            ns['training_clicks'] = clicks + 1
            return True
        task.log_info("点了 3 次「训练」都没进选战斗员页，放弃训练")
        ns['flash_or_rest'] = False

    if rest_feature and "免费" not in free_text:
        task.log_info("检测到rest特征，但休息区域未找到「免费」，跳过点击休息")


    # 检测是否需要进入德朗商店
    shop_box = find_box_at_point(task, 0.360, 0.138)
    if shop_box and "德朗商店" in shop_box.name and _want_shop(task):
        task.log_info("检测到德朗商店，进入商店" + ("（最后一个商店，钱全部花掉）" if _is_last_shop(task) else ""))
        task.node_status['shop_visited'] = _shop_key(task)
        task.click_box(shop_box)
        task.sleep(2)
        return True
    if on_rest_page and flash_or_rest:
        # 进页面有动画，休息/训练/冥想按钮可能还没认出来，先别让通用「跳过」抢先：稳定看 2 帧再放行
        seen = task.node_status.get('rest_page_frames', 0)
        if seen < 2:
            task.node_status['rest_page_frames'] = seen + 1
            task.sleep(0.8)
            return True
    if on_rest_page:
        task.log_info(f"休息页：休息{'可用' if can_rest else '不可用'}、冥想{'需要' if can_meditate else '不需要/不可用'}、"
                      f"训练{'可用' if can_train else '不可用'}，交给「跳过」")
    return False


TRAIN_REGION = (0.78, 0.15, 0.92, 0.26)     # 休息页右上「训练 / 免费」
REST_HP_BELOW = 70                           # 能训练时，血量低于这个才休息
MEDITATE_COST = 80                           # 休息页冥想的信用点费用（第一次）
MEDITATE_COST_STEP = 40                      # 每冥想一次涨这么多


def find_text_in_region(task, pattern, region):
    x1, y1, x2, y2 = region
    for b in task.all_texts or []:
        cx, cy = (b.x + b.width / 2) / task.width, (b.y + b.height / 2) / task.height
        if x1 <= cx <= x2 and y1 <= cy <= y2 and re.search(pattern, b.name):
            return b
    return None


def handle_training_select(task: TriggerTask):
    """点了「训练」之后的选战斗员页：点目标主战员头像，再点确认。认不出就截图留证、放给别的处理函数。"""
    ns = getattr(task, 'node_status', None)
    started = ns.get('training_pending') if isinstance(ns, dict) else None
    if not started:
        return False
    if time.time() - started > 20:
        if ns.get('training_member_clicked'):
            task.log_info("训练：已选目标主战员（确认由页面中央确认按钮处理）")
        else:
            task.log_info("训练选战斗员超时，放弃（截图见流程追踪）")
            chaos_trace.step(task, "page", "训练选战斗员超时", task.frame)
        ns['training_pending'] = None
        ns['training_member_clicked'] = False
        return False
    if any("安全区采取" in b.name for b in task.all_texts or []):
        return False                         # 还在休息页（训练没点进去），交给 handle_rest 重点
    if any(k in b.name for b in task.all_texts or [] for k in ("卡牌奖励", "接受卡牌的主战员")):
        # 训练完会弹卡牌奖励；这里的「确认」是把卡发给主战员，不是训练确认（2026-10-25 实录误发了中立卡）
        ns['training_pending'] = None
        ns['training_member_clicked'] = False
        return False
    member = None
    if task.feature_exists("target_member_small"):
        member = task.find_one(feature_name="target_member_small", box=task.box_of_screen(0, 0.1, 1, 0.9), threshold=0.4)
    confirm = find_text_in_region(task, r"^(确认|训练|选择)$", (0.6, 0.8, 1, 1))
    if member and not ns.get('training_member_clicked'):
        task.log_info(f"训练：选目标主战员（头像相似度 {member.confidence:.2f}）")
        task.click_box(member)
        task.sleep(1)
        ns['training_member_clicked'] = True
        ns['training_pending'] = time.time()
        ns['flash_or_rest'] = False          # 这次休息用掉了
        return True
    if confirm and ns.get('training_member_clicked'):
        task.log_info(f"训练：点「{confirm.name}」")
        task.click_box(confirm)
        task.sleep(1.5)
        ns['training_pending'] = None
        ns['training_member_clicked'] = False
        return True
    if not ns.get('training_logged'):
        chaos_trace.step(task, "page", "训练选战斗员页（待标定）", task.frame,
                         texts=[b.name for b in (task.all_texts or [])][:30])
        ns['training_logged'] = True
    return False


def _shop_key(task):
    ns = task.node_status
    return (ns.get("total_rounds", 0), ns.get("pass_final_boss_count", 0), ns.get("node_count", 0))


def _want_shop(task):
    """休息页上的德朗商店进不进：配置「进入商店」（路线页置 shop=True），或最后一个商店（不管配置，钱留着没用）。
    最后一个商店只进一次：出来后 _is_last_shop 仍为 True，按 (轮, 层, 节点) 记下已进过。"""
    ns = getattr(task, "node_status", None)
    if not isinstance(ns, dict):
        return False
    if ns.get("shop", False):
        return True
    return _is_last_shop(task) and ns.get("shop_visited") != _shop_key(task)


def _is_last_shop(task: TriggerTask):
    """最后一层（记忆之末）里、整层路线下一步就是最终首领的商店：钱留着没用，全部花掉（用户 2026-10-25）。"""
    ns = getattr(task, "node_status", None)
    if not isinstance(ns, dict) or ns.get("pass_final_boss_count", 0) < 2:
        return False
    plan = ns.get("full_route")
    if not plan or plan.get("layer") != ns.get("pass_final_boss_count", 0):
        return False
    steps = plan.get("steps", [])
    return plan.get("done", 0) < len(steps) and steps[plan["done"]]["type"] == "首领"


LEGEND_PRICE_EST = 200      # 商店传说装备价格（实录 200，打折 140）；稀有 96，付费刷新 30
LEGEND_RARITIES = ("传说", "神话", "独特")


def _shop_item_rarity(name, price):
    """商店装备稀有度：先查装备库，查不到按价格猜（≥130 当传说）。"""
    try:
        eq = game_db.get_db().find_equipment(name)
    except Exception:  # noqa: BLE001
        eq = None
    if eq and eq.get("rarity"):
        return eq["rarity"]
    return "传说" if price >= 130 else "稀有"


def _shop_refresh_option(task: TriggerTask, credit):
    """商店左下角刷新：免费 → ("free", 0)；还有付费次数且够钱 → ("paid", 价格)；否则 (None, None)。只读。"""
    def in_box(b, x0, x1, y0, y1):
        cx, cy = (b.x + b.width / 2) / task.width, (b.y + b.height / 2) / task.height
        return x0 <= cx <= x1 and y0 <= cy <= y1
    if any(in_box(b, 0.012, 0.258, 0.892, 0.979) and "免费" in b.name for b in task.all_texts):
        return "free", 0
    count_text = "".join(b.name.strip() for b in sorted(task.all_texts, key=lambda i: i.x)
                         if in_box(b, 0.045, 0.115, 0.912, 0.952))
    m = re.search(r"(\d+)\s*[/／]\s*(\d+)", count_text)
    price_box = next((b for b in task.all_texts if in_box(b, 0.160, 0.220, 0.915, 0.950) and b.name.strip().isdigit()), None)
    if not m or int(m.group(1)) <= 0 or not price_box or int(price_box.name.strip()) > credit:
        return None, None
    return "paid", int(price_box.name.strip())


def _last_shop_pick(task: TriggerTask, shop_items, credit):
    """最后一个商店买哪件装备（用户 2026-10-25）：下一次刷新后不够买传说了（或刷不了）就先买眼前的传说；
    刷不了时剩下的钱买任意装备（贵的先）。返回 (图标, 名称, 价格, 理由) 或 None（去刷新）。"""
    eqs = sorted(((icon, name, price, _shop_item_rarity(name, price))
                  for icon, name, price, is_card in shop_items if not is_card and price <= credit),
                 key=lambda x: -x[2])
    if not eqs:
        return None
    kind, refresh_price = _shop_refresh_option(task, credit)
    can_refresh_for_legend = kind == "free" or (kind == "paid" and credit - refresh_price >= LEGEND_PRICE_EST)
    legends = [e for e in eqs if e[3] in LEGEND_RARITIES]
    if legends and not can_refresh_for_legend:
        icon, name, price, rarity = legends[0]
        return icon, name, price, f"{rarity}，" + ("刷新次数用完了，先买传说" if kind is None else "再刷新就不够买传说了")
    if kind is None:
        icon, name, price, rarity = eqs[0]
        return icon, name, price, f"{rarity}，刷新不了了，剩下的钱买装备"
    return None


def handle_shop(task: TriggerTask):
    """德朗商店: 优先移除卡牌，其次按配置购买卡牌或装备，最后尝试免费或付费刷新。"""
    box = find_box_at_point(task, 0.729, 0.261)
    soldout = find_box_at_point(task, 0.727, 0.286)
    if (box and "移除卡牌" in box.name) or (soldout and "售" in soldout.name):
        task.log_info("handle_shop: 通过页面判定（移除卡牌或售罄）")
        if soldout and "售" in soldout.name:
            task.log_info(f"德朗商店: 移除卡牌已售罄")
            task.node_status['shop'] = False
        else:
            current_credit = _get_current_credit(task)
            removed_card_count = task.node_status.get("removed_card_count", 0)
            task.log_info(f"handle_shop: 当前信用点={current_credit}")
            cost_box = find_box_at_point(task, 0.724, 0.319)
            task.log_info(f"handle_shop: 0.724,0.319处费用文本='{cost_box.name if cost_box else None}'")
            if cost_box and cost_box.name.isdigit():
                cost = int(cost_box.name)
                if removed_card_count >= 5:
                    task.log_info(
                        f"本局已移除{removed_card_count}张卡牌，"
                        "达到5张上限，不再使用信用点移除卡牌"
                    )
                elif (getattr(task, "chaos_mode", None) == chaos_strategy.MODE_TARGET
                      and _chaos_strategy_state(task)["need_remove"] <= 0):
                    task.log_info("德朗商店: 目标卡组要删的卡已经删够，不付费移除")
                elif cost <= current_credit and task.node_status['shop'] is True:
                    task.log_info(f"德朗商店: 移除卡牌需{cost}信用点，当前{current_credit}，足够，点击移除")
                    task.click_box(box)
                    task.sleep(1)
                    task.node_status['shop'] = False
                    return True
                elif cost <= current_credit:
                    task.log_info("德朗商店: 没开「进入商店」（只因最后一个商店进来），不付费移除，只买装备")
                else:
                    task.log_info(f"德朗商店: 移除卡牌需{cost}信用点，当前{current_credit}，不足，继续挑选其他商品")
            else:
                task.log_info("handle_shop: 移除卡牌费用读取失败，继续挑选其他商品")
            task.node_status['shop'] = False

        current_credit = _get_current_credit(task)
        task.log_info(f"德朗商店挑选商品: 当前信用点={current_credit}")
        credit_icons = sorted(
        task.find_feature(
            feature_name="credit_icon",
            box=task.box_of_screen(0.019, 0.761, 0.979, 0.890),
        ) or [],
        key=lambda feature: feature.x,
        )

        card_type_features = []
        card_type_region = task.box_of_screen(0.032, 0.669, 0.968, 0.799)
        for feature_name in (
            "attack_in_shop",
            "skill_in_shop",
            "enhance_in_shop",
        ):
            for feature in task.find_feature(
            feature_name=feature_name,
            box=card_type_region,
            ) or []:
                card_type_features.append((feature_name, feature))

        card_icon_indexes = set()
        for feature_name, feature in card_type_features:
            if not credit_icons:
                break
            feature_x = feature.x + feature.width / 2
            feature_y = feature.y + feature.height / 2
            closest_index = min(
            range(len(credit_icons)),
            key=lambda index: (
                credit_icons[index].x + credit_icons[index].width / 2 - feature_x
            ) ** 2 + (
                credit_icons[index].y + credit_icons[index].height / 2 - feature_y
            ) ** 2,
            )
            card_icon_indexes.add(closest_index)
            task.log_info(f"德朗商店: {feature_name}特征绑定第{closest_index + 1}个信用点图标")

        card_priority = _get_card_reward_priority(task)
        equipment_priorities = [_equipment_priority(task, slot) for slot in range(3)]
        unaffordable_items = []
        shop_items = []
        last_shop = _is_last_shop(task)
        if last_shop:
            task.log_info("德朗商店：最后一个商店（下一步是最终首领），信用点全部用来买装备和刷新")
        for index, credit_icon in enumerate(credit_icons):
            icon_x = (credit_icon.x + credit_icon.width / 2) / task.width
            icon_y = (credit_icon.y + credit_icon.height / 2) / task.height
            price_box = find_box_at_point(task, icon_x + 0.099, icon_y - 0.001)
            price = _parse_discounted_price(price_box.name) if price_box else None
            item_name = _get_region_text(task, (
            max(0.0, icon_x - 0.013),
            max(0.0, icon_y - 0.247),
            min(1.0, icon_x + 0.120),
            min(1.0, icon_y - 0.105),
            )).strip()
            is_card = index in card_icon_indexes
            item_type = "卡牌" if is_card else "装备"
            task.log_info(f"德朗商店第{index + 1}个商品: 类型={item_type}，名称=「{item_name}」，价格={price}")
            if not item_name or price is None:
                continue
            shop_items.append((credit_icon, item_name, price, is_card))

            if is_card:
                if _neutral_card_limit_reached(task):
                    neutral_card_count = task.node_status.get(
                        "neutral_card_count", 0,
                    )
                    neutral_card_limit = _neutral_card_limit(task)
                    task.log_info(
                        f"本局已获得{neutral_card_count}张中立牌，"
                        f"达到固定上限{neutral_card_limit}张，跳过商店卡牌"
                    )
                    continue
                matched_name = next(
                (name for name in card_priority
                 if name and (name in item_name or item_name in name)),
                None,
                )
            else:
                matched_name = next(
                (canonical_name
                 for priority in equipment_priorities
                 for canonical_name, rank in [_match_equipment_name(item_name, priority)]
                 if rank is not None),
                None,
                )
            if not matched_name:
                task.log_info(f"德朗商店: {item_type}「{item_name}」未命中配置，跳过")
                continue
            if price > current_credit or (price == current_credit and not last_shop):
                unaffordable_items.append(item_name)
                reason = "余额不足" if price > current_credit else "余额等于价格，当前购买规则要求余额大于价格"
                task.log_info(
                    f"德朗商店: {item_type}「{item_name}」命中配置「{matched_name}」，"
                    f"价格={price}，当前信用点={current_credit}，"
                    f"{reason}，跳过购买"
                )
                continue

            task.log_info(
            f"德朗商店: {item_type}「{item_name}」命中配置「{matched_name}」，"
            f"价格{price}小于当前信用点{current_credit}，点击信用点图标"
            )
            task.click_box(credit_icon)
            task.sleep(1)
            return True

        if last_shop:
            pick = _last_shop_pick(task, shop_items, current_credit)
            if pick:
                credit_icon, item_name, price, reason = pick
                task.log_info(f"德朗商店（最后一个）: 装备「{item_name}」价格{price}，当前{current_credit}，{reason}，买下")
                task.click_box(credit_icon)
                task.sleep(1)
                return True

        free_box = next(
        (text_box for text_box in task.all_texts
         if 0.012 <= (text_box.x + text_box.width / 2) / task.width <= 0.258
         and 0.892 <= (text_box.y + text_box.height / 2) / task.height <= 0.979
         and "免费" in text_box.name),
        None,
        )
        if free_box:
            if unaffordable_items:
                task.log_info(
                    f"德朗商店找到配置商品{unaffordable_items}，但余额未满足购买条件，"
                    "点击「免费」刷新"
                )
            else:
                task.log_info("德朗商店没有符合要求的商品，点击「免费」刷新")
            task.click_box(free_box)
            task.sleep(1)
            return True

        # 免费次数用完后按钮只显示「剩余刷新次数 + 信用点价格」，按阈值决定是否付费刷新
        refresh_count_text = "".join(
            text_box.name.strip()
            for text_box in sorted(task.all_texts, key=lambda item: item.x)
            if 0.045 <= (text_box.x + text_box.width / 2) / task.width <= 0.115
            and 0.912 <= (text_box.y + text_box.height / 2) / task.height <= 0.952
        )
        count_match = re.search(r"(\d+)\s*[/／]\s*(\d+)", refresh_count_text)
        if not count_match:
            task.log_info(
                f"德朗商店未识别到刷新次数（识别值「{refresh_count_text}」），不付费刷新"
            )
            return False
        refresh_remaining = int(count_match.group(1))
        if refresh_remaining <= 0:
            task.log_info(
                f"德朗商店付费刷新次数已用完（{refresh_count_text}），不再刷新"
            )
            return False

        refresh_credit_threshold = _get_config_value(task, "商店刷新信用点阈值", 300)
        try:
            refresh_credit_threshold = int(refresh_credit_threshold)
        except (TypeError, ValueError):
            refresh_credit_threshold = 300
        if current_credit <= refresh_credit_threshold and not last_shop:
            task.log_info(
                f"德朗商店免费刷新已用完，当前信用点{current_credit}未超过阈值"
                f"{refresh_credit_threshold}，不付费刷新"
            )
            return False

        refresh_price_box = next(
        (text_box for text_box in task.all_texts
         if 0.160 <= (text_box.x + text_box.width / 2) / task.width <= 0.220
         and 0.915 <= (text_box.y + text_box.height / 2) / task.height <= 0.950
         and text_box.name.strip().isdigit()),
        None,
        )
        if not refresh_price_box:
            task.log_info("德朗商店免费刷新已用完，未识别到刷新价格，不付费刷新")
            return False

        refresh_price = int(refresh_price_box.name.strip())
        if refresh_price > current_credit:
            task.log_info(
                f"德朗商店付费刷新需{refresh_price}信用点，当前{current_credit}，"
                "不足，不刷新"
            )
            return False

        task.log_info(
            f"德朗商店免费刷新已用完，当前信用点{current_credit}超过阈值"
            f"{refresh_credit_threshold}，付费刷新需{refresh_price}信用点，点击刷新"
        )
        task.click_box(refresh_price_box)
        task.sleep(1)
        return True
    return False


def _god_spark_pick(task: TriggerTask, x, y):
    """选定神闪：一页只记一次 PT，记下位置供确认那下重点。"""
    task.node_status["god_spark_count"] = task.node_status.get("god_spark_count", 0) + 1
    task.node_status["god_pick"] = (x, y, time.time())
    _move_and_click(task, x, y)


def handle_view_original(task: TriggerTask):
    """卡牌闪光（查看原件）事件: 按类型特征识别卡牌，并按闪光优先级选择。"""
    box1 = find_box_at_point(task, 0.890, 0.051)
    box2 = find_box_at_point(task, 0.896, 0.131)
    if not ((box1 and (_get_game_text(task, '查看原件') in box1.name or _get_game_text(task, '查看之前的闪光') in box1.name)) or (box2 and (_get_game_text(task, '查看原件') in box2.name or _get_game_text(task, '查看之前的闪光') in box2.name))):
        return False

    if _avoid_god_spark(task) and any(GOD_SPARK_PAGE.search(b.name) for b in task.all_texts or []):
        # 变体页底部写「闪光：迪亚洛斯」= 神闪三选一（2026-10-24 实机随机选了，神闪落到剑鸣九霄上）。
        # 只有和预设一致的神闪、且 PT 账还够才选（用户 2026-10-25：正确的神闪也不能爆 PT）
        task.node_status["god_spark_pending"] = False
        last = task.node_status.get("god_pick")
        if last and time.time() - last[2] < 4:
            # 同一页第二下是确认，不再查 PT、不再记账（2026-10-26 实录每帧都记一次，账 80 记成 120，把下一页预设神闪跳过了）
            task.log_info("神闪变体页：刚选过这页，再点一下确认")
            _move_and_click(task, last[0], last[1])
            return True
        plan = getattr(task, "chaos_plan", None) or {}
        god_cards = [c for c in plan.get("flash", []) if c.get("god_spark")]
        cards = recognize_cards(task, page="神闪变体页") if god_cards and _pt_room(task, "神闪") else []
        if cards and len(cards) < 3 and task.node_status.get("flash_page_waits", 0) < 3:
            task.node_status["flash_page_waits"] = task.node_status.get("flash_page_waits", 0) + 1
            task.log_info(f"神闪三选一只认出 {len(cards)} 张，等动画结束再判断")
            task.sleep(0.8)
            return True
        for card in cards:
            # 神闪选错存档就废，比普通闪光要求更像（0.9）
            index = chaos_strategy.pick_flash_variant(card["name"], cards, god_cards, min_sim=0.9)
            if index is not None:
                pick = cards[index]
                ok = task.node_status.setdefault("god_ok", [])
                if pick["name"] not in ok:
                    ok.append(pick["name"])
                task.log_info(f"神闪变体页：「{pick['name']}」和预设神闪一致，PT 账够，选它（{pick['description']}）")
                _god_spark_pick(task, pick["x"], pick["y"])
                return True
        if cards:
            # 描述 OCR 会把行序打乱（2026-10-26 实录「生成3张剑穗加入手牌下一次明暗…」没对上），
            # 游戏给预设那张钉了图钉（target），PT 够就按图钉选
            target_boxes, target_click_positions = find_target_card(task)
            if target_boxes:
                task.log_info("神闪变体页：描述没对上，但游戏钉了预设那张，PT 账够，选它")
                _god_spark_pick(task, *target_click_positions[0])
                return True
        if _click_bottom_skip(task, "神闪变体页，不是预设的神闪或 PT 不够"):
            task.node_status["god_skip_waits"] = 0
            return True
        # 「跳过」要等入场动画放完才出来；不能马上落到下面普通闪光那套（会点图钉那张，不查 PT 也不记账，2026-10-26 实录）。
        # 战斗后的神闪页（如队友的黑云奥义：灭，闪光：维托尔）根本没有「跳过」，只能三选一，等 3 次就够
        waits = task.node_status.get("god_skip_waits", 0)
        if waits < 3:
            task.node_status["god_skip_waits"] = waits + 1
            task.log_info(f"神闪变体页：不选，等「跳过」出来（第 {waits + 1} 次）")
            task.sleep(0.8)
            return True
        task.log_info("神闪变体页：等不到「跳过」，按普通闪光处理")
    cards = recognize_cards(task, page="卡牌闪光页面")
    if not cards:
        return False
    # 三选一有入场动画，第一帧常只认出 1~2 张；点一下就直接选定，所以认全 3 张再判断
    # （2026-10-25 实录只认出 1 张剑鸣九霄就随机点了，预设那张还没出来）。最多等 3 帧
    if len(cards) < 3:
        waits = task.node_status.get("flash_page_waits", 0)
        if waits < 3:
            task.node_status["flash_page_waits"] = waits + 1
            task.log_info(f"闪光三选一只认出 {len(cards)} 张，等动画结束再选（第 {waits + 1} 次）")
            task.sleep(0.8)
            return True
    task.node_status["flash_page_waits"] = 0
    _dump_card_page(task, "view_original")

    flash_priority = []
    for keyword in _get_card_list(task, '闪光优先级'):
        if not isinstance(keyword, str):
            continue
        normalized_keyword = re.sub(r"\s+", "", keyword)
        if normalized_keyword:
            flash_priority.append(normalized_keyword)
    chosen_card = None
    for desc_keyword in flash_priority:
        for card in cards:
            if is_subsequence(
                desc_keyword,
                card['name'] + "：:" + card['description'],
            ):
                chosen_card = card
                task.log_info(f"优先选择「{card['name']}」({desc_keyword})")
                if (
                    _get_config_value(task, "首层刷特定闪光", False) is True
                    and flash_priority
                    and desc_keyword == flash_priority[0]
                ):
                    task.node_status["get_specific_flash"] = True
                    task.log_info("已命中闪光优先级第一项，记录已获得特定闪光")
                break
            if chosen_card:
                break
        if chosen_card:
            break

    plan = getattr(task, "chaos_plan", None)
    if chosen_card is None and plan and getattr(task, "chaos_mode", "") == chaos_strategy.MODE_TARGET:
        # 目标卡组：选描述和预设里那张卡一致的闪光变体（不管是闪光还是神闪，描述一样就行）
        for card in cards:
            index = chaos_strategy.pick_flash_variant(card["name"], cards, plan.get("flash", []))
            if index is not None:
                chosen_card = cards[index]
                task.log_info(f"[目标卡组] 闪光选择和预设一致的「{chosen_card['name']}」：{chosen_card['description']}")
                break

    target_boxes, target_click_positions = find_target_card(task)
    matched_meditation_cards = _matching_meditation_card_names(task, cards)
    if matched_meditation_cards:
        meditation_state = _member_deck_state(task)["冥想"]
        meditation_completed = chosen_card is None and not target_boxes
        for configured_name in matched_meditation_cards:
            meditation_state[configured_name] = meditation_completed
            # 同一个变体页会连着处理两帧（选中、再点确认），按页面内容只记一次（2026-10-25 实录记了两次）
            last = task.node_status.get("flash_ok_page") or [None, None, 0]
            same_page = last[:2] == [task.node_status.get("node_count", 0), configured_name] and time.time() - last[2] < 8
            if not meditation_completed and not same_page:
                # 每闪对一张记一次：预设里同名有几张（剑鸣九霄 3 张）就要闪对几次，后面「选卡闪光」才不再选它
                task.node_status.setdefault("flash_ok", []).append(configured_name)
            if not meditation_completed:
                task.node_status["flash_ok_page"] = [task.node_status.get("node_count", 0), configured_name, time.time()]
            task.log_info(
                f"冥想卡牌「{configured_name}」状态更新为"
                f"{'待冥想' if meditation_completed else '无需冥想'}"
            )

    if target_boxes:
        click_position = target_click_positions[0]
        task.log_info(
            f"卡牌闪光事件: 检测到target卡牌，点击位置{click_position}"
        )
        _move_and_click(task, *click_position)
        return True

    if not chosen_card:
        chosen_card = random.choice(cards)
        task.log_info(f"随机选择「{chosen_card['name']}」")

    _move_and_click(task, chosen_card['x'], chosen_card['y'])
    return True


def handle_escape(task: TriggerTask):
    """逃脱页面: 检测到逃脱按钮后点击逃脱。"""
    escape_box = find_box_at_point(task, 0.952, 0.928)
    if escape_box and (
        _get_game_text(task, '逃脱') in escape_box.name
        or "脱逃" in escape_box.name
    ):
        task.log_info("检测到逃脱页面，点击逃脱")
        task.click_box(escape_box)
        task.node_status["is_escaped"] = True
        task.sleep(0.5)
        return True
    return False


# def handle_battle_failed(task: TriggerTask):
#     """战斗失败页面: 记录失败并重置boss状态。"""
#     box = find_box_at_point(task, 0.291, 0.718)
#     if box and box.name == "战斗失败":
#         task.log_info("检测到战斗失败，记录失败并重置boss状态")
#         if hasattr(task, 'node_status'):
#             task.node_status['total_rounds'] += 1
#             task.log_info(f"战斗失败，total_rounds={task.node_status['total_rounds']}")
#             task.node_status['pass_final_boss_count'] = 0
#             task.node_status['reach_final_boss'] = False
#             task.node_status['final_boss_battle'] = False
#     return False

# 用户 2026-10-26：最后一层首领持续打不过的话，拿到混沌之识就停下交给用户手动打。
# 「持续」= 刷存档局打到第 3 层（已过 2 个首领）后失败，连续 LAST_BOSS_FAIL_HANDOVER 次；通关一次就清零。跨重启记在文件里。
LAST_BOSS_FAIL_HANDOVER = 2
LAST_BOSS_FAIL_FILE = os.path.join("dev_out", "chaos_last_boss_fails.json")


def _last_boss_fails():
    try:
        with open(LAST_BOSS_FAIL_FILE, encoding="utf-8") as f:
            return int(json.load(f).get("fails", 0))
    except Exception:  # noqa: BLE001
        return 0


def _set_last_boss_fails(n):
    try:
        os.makedirs(os.path.dirname(LAST_BOSS_FAIL_FILE), exist_ok=True)
        with open(LAST_BOSS_FAIL_FILE, "w", encoding="utf-8") as f:
            json.dump({"fails": n, "time": time.strftime("%Y-%m-%d %H:%M:%S")}, f)
    except Exception:  # noqa: BLE001
        pass


def _record_last_boss_result(task: TriggerTask, success):
    if not _avoid_god_spark(task):
        return
    passed = (getattr(task, "node_status", None) or {}).get("pass_final_boss_count", 0)
    if success:
        if _last_boss_fails():
            task.log_info("刷存档通关，最后一层首领连败清零")
        _set_last_boss_fails(0)
    elif passed >= 2:
        n = _last_boss_fails() + 1
        _set_last_boss_fails(n)
        task.log_info(f"刷存档死在最后一层首领，连续 {n} 次（到 {LAST_BOSS_FAIL_HANDOVER} 次后拿到混沌之识就停下交给你）")


def _hand_over_on_chaos_core(task: TriggerTask, name):
    if not name or not re.search(r"混沌之识|混沌指控", name):
        return
    task.node_status["chaos_core_got"] = name
    if not _avoid_god_spark(task):
        return
    n = _last_boss_fails()
    if n < LAST_BOSS_FAIL_HANDOVER:
        task.log_info(f"拿到混沌之识；最后一层首领连败 {n} 次，没到 {LAST_BOSS_FAIL_HANDOVER} 次，脚本继续打")
        return
    task.log_error(f"拿到混沌之识，最后一层首领已连败 {n} 次：装完这件就停下，交给你手动打", notify=True)
    task.disable()


def handle_expedition_result(task: TriggerTask):
    """探险结果页面: 如果0.625,0.122处有"探险结果"，则为探险结果页面。
    如果0.928,0.122处有"完成"，则success_rounds+1。"""
    expedition_result_text = _get_game_text(task, "探险结果")
    title_box = find_box_at_point(task, 0.625, 0.122)
    if not (title_box and expedition_result_text in title_box.name):
        return False
    task.sleep(2)
    task.all_texts = _simplify_texts(task.ocr())
    title_box = find_box_at_point(task, 0.625, 0.122)
    if not (title_box and expedition_result_text in title_box.name):
        return False

    task.log_info("检测到探险结果页面")
    success_before = (getattr(task, "node_status", None) or {}).get("success_rounds", 0)
    complete_box = find_box_at_point(task, 0.928, 0.122)
    failed_box = find_box_at_point(task, 0.296, 0.719)
    if hasattr(task, 'node_status'):
        task.node_status['total_rounds'] += 1
    if complete_box and "完成" in complete_box.name:
        if hasattr(task, 'node_status'):
            task.node_status['success_rounds'] += 1
            task.log_info("出击模式探险结果: 成功")
    elif complete_box and "失败" in complete_box.name:
        if not _get_config_value(task, '只打第一层', False):
            task.log_info("出击模式探险结果: 失败")
        elif task.node_status.get('pass_final_boss_count', 0) == 0:
            task.log_info("出击模式探险结果: 失败")
    elif not complete_box and not failed_box:
        if _get_config_value(task, '只打第一层', False) and task.node_status.get('pass_final_boss_count', 0) >= 1: # 完成第一层任务
            task.log_info("卡厄思模式探险结果: 成功")
        elif not _get_config_value(task, '只打第一层', False) and not task.node_status.get('is_escaped', 0): # 完成了任务且没有逃脱
            task.node_status['success_rounds'] += 1
            task.log_info("卡厄思模式探险结果: 成功")
        else:
            task.log_info("卡厄思模式探险结果: 失败")
    else:
        task.log_info("卡厄思模式探险结果: 失败")
    task.log_info(f"探险完成，成功次数/总次数={task.node_status['success_rounds']}/{task.node_status['total_rounds']}")
    if hasattr(task, 'node_status'):
        _record_last_boss_result(task, task.node_status['success_rounds'] > success_before)
        reset_mission_status(task)
    return False


def _initial_node_status():
    """返回 node_status 的初始副本。"""
    return {"shop": False, "flash_or_rest": False, "reach_final_boss": False, "final_boss_battle": False,
            "pass_final_boss_count": 0, "total_rounds": 0, "success_rounds": 0,
            "node_count": 0, "enter_new_node": False, "node_type": "", "is_escaped": False,
            "save_target_member": False, "target_mask_card_position": -1,
            "get_specific_flash": False, "removed_card_count": 0,
            "neutral_card_count": 0}


def _initial_member_status():
    """返回目标主战员状态的初始副本。"""
    return {
        "equipment": {
            "names": ["", "", ""],
            "descriptions": ["", "", ""],
            "qualities": ["", "", ""],
        },
        "deck": {},
    }


OCTOPUS_RUSH = "章鱼哥速刷"
OCTOPUS_CORE_ONLY = "章鱼哥速刷只认混沌之识"
OCTOPUS_NAMES = ("赛内克图斯",)       # 章鱼哥：梦境模式清完怪后低概率乱入的精英，掉混沌之识（混沌指控）
# 结算页的乱入计数（官方文本 ui_stage_result_break_into「乱入{0}」）；画面没出名字时靠它兜底。噬光者也算乱入，但只在零式法典词条里出现
OCTOPUS_BREAK_IN = re.compile(r"^乱入\s*[1-9]")
# 战斗界面不显示怪物名字（用户 2026-10-25），所以主要靠掉落：画面上出现它掉的六件神话装备之一就算遇到了
_octopus_drops = None


def octopus_drop_names():
    """赛内克图斯掉落的装备名（国服名 + 国际服/gamekee 名），从装备库 obtain 字段取。"""
    global _octopus_drops
    if _octopus_drops is None:
        names = set()
        for e in game_db.get_db().equipment:
            if any(n in str(e.get("obtain", "")) for n in OCTOPUS_NAMES):
                names.update(e[k] for k in ("name", "name_intl", "name_gamekee") if e.get(k))
        _octopus_drops = tuple(sorted(n for n in names if len(n) >= 3))
    return _octopus_drops


def note_octopus(task: TriggerTask):
    """每帧看画面文字里有没有章鱼哥；看到就记下（整局有效），第一次存一张截图方便校准识别。"""
    ns = getattr(task, 'node_status', None)
    if not isinstance(ns, dict) or ns.get('octopus_seen'):
        return
    hit = next((b.name for b in task.all_texts or []
                if any(n in b.name for n in OCTOPUS_NAMES + octopus_drop_names()) or OCTOPUS_BREAK_IN.match(b.name)), None)
    if hit:
        ns['octopus_seen'] = True
        task.log_info(f"遇到章鱼哥：「{hit}」（第 {ns.get('pass_final_boss_count', 0) + 1} 层）", notify=True)
        chaos_trace.step(task, "page", "章鱼哥", task.frame, text=hit)


def _finish_only_first_layer(task: TriggerTask) -> bool:
    """检查并完成只打第一层的退出操作：如果 pass_final_boss_count >= 1 且配置'只打第一层'为 True，则成功次数+1、点击退出并返回 True。"""
    if not (
        hasattr(task, 'node_status')
        and task.node_status.get('pass_final_boss_count', 0) >= 1
    ):
        return False

    if (
        _get_config_value(task, "首层刷特定闪光", False) is True
        and task.node_status.get("get_specific_flash", False) is False
    ):
        task.node_status['success_rounds'] += 1
        task.log_info("未刷到指定闪光且已通关第一层，退出重刷")
        _move_and_click(task, 0.959, 0.051)
        task.sleep(1)
        return True

    core_only = _get_config_value(task, OCTOPUS_CORE_ONLY, False) is True
    got = task.node_status.get('chaos_core_got' if core_only else 'target_equip_got')
    # 用户 2026-10-26：开了「只认混沌之识」时，别的目标装备也不算；不管第几层遇到章鱼哥没掉混沌之识，下一个结算页就退出重开
    late_miss = core_only and task.node_status.get('octopus_seen') and not got
    if (_get_config_value(task, OCTOPUS_RUSH, False) is True
            and (task.node_status.get('pass_final_boss_count', 0) == 1 or late_miss)):
        if got:
            if not task.node_status.get('octopus_rush_kept_logged'):
                task.node_status['octopus_rush_kept_logged'] = True
                task.log_info(f"章鱼哥速刷：本局拿到了「{got}」，不退出，继续打完")
        else:
            miss = "混沌之识" if core_only else "目标装备"
            why = f"遇到了章鱼哥但没掉{miss}" if task.node_status.get('octopus_seen') else "第一层没遇到章鱼哥（赛内克图斯）"
            task.log_info(f"章鱼哥速刷：{why}，退出重进")
            _move_and_click(task, 0.959, 0.051)
            task.sleep(1)
            return True

    if _get_config_value(task, '只打第一层', False):
        task.node_status['success_rounds'] += 1
        task.log_info(f"只打第一层任务已完成，success_rounds + 1 (当前: {task.node_status['success_rounds']}), 退出结算页面")
        _move_and_click(task, 0.959, 0.051)
        task.sleep(1)
        return True
    return False


def reset_all_status(task: TriggerTask):
    """重置所有状态：恢复节点状态和目标主战员状态。"""
    if getattr(task, 'node_status', None) is not None:
        task.node_status = _initial_node_status()
    task.member_status = _initial_member_status()
    _reset_meditation_state(task)
    task._pending_removed_card_count = 0


def reset_mission_status(task: TriggerTask):
    """重置任务状态：保留任务统计和目标成员特征状态，重置其他状态。"""
    ns = getattr(task, 'node_status', None)
    if ns is not None:
        keep = {'total_rounds': ns.get('total_rounds', 0),
                'success_rounds': ns.get('success_rounds', 0),
                'save_target_member': ns.get('save_target_member', False),
                'reward_cards_out': ns.get('reward_cards_out', False)}
        task.node_status = _initial_node_status()
        task.node_status['total_rounds'] = keep['total_rounds']
        task.node_status['success_rounds'] = keep['success_rounds']
        task.node_status['save_target_member'] = keep['save_target_member']
    task.member_status = _initial_member_status()
    _reset_meditation_state(task)
    task._pending_removed_card_count = 0


def reset_layer_status(task: TriggerTask):
    """重置层状态：保留通关计数、任务统计和目标成员特征状态。"""
    ns = getattr(task, 'node_status', None)
    if ns is not None:
        keep = {'pass_final_boss_count': ns.get('pass_final_boss_count', 0),
                'total_rounds': ns.get('total_rounds', 0),
                'success_rounds': ns.get('success_rounds', 0),
                'save_target_member': ns.get('save_target_member', False),
                'target_mask_card_position': ns.get('target_mask_card_position', -1),
                'get_specific_flash': ns.get('get_specific_flash', False),
                'removed_card_count': ns.get('removed_card_count', 0),
                'neutral_card_count': ns.get('neutral_card_count', 0)}
        task.node_status = _initial_node_status()
        task.node_status['pass_final_boss_count'] = keep['pass_final_boss_count']
        task.node_status['total_rounds'] = keep['total_rounds']
        task.node_status['success_rounds'] = keep['success_rounds']
        task.node_status['save_target_member'] = keep['save_target_member']
        task.node_status['target_mask_card_position'] = keep['target_mask_card_position']
        task.node_status['get_specific_flash'] = keep['get_specific_flash']
        task.node_status['removed_card_count'] = keep['removed_card_count']
        task.node_status['neutral_card_count'] = keep['neutral_card_count']
        # PT 账是整局的：换层不能清（2026-10-25 实录第 2 层复制又从 1 次记起）
        for k in RUN_LEVEL_KEYS:
            if k in ns:
                task.node_status[k] = ns[k]


RUN_LEVEL_KEYS = ("copy_count", "copy_key", "god_spark_count", "shop_visited", "meditate_count", "flash_ok", "god_ok",
                  "octopus_seen", "target_equip_got", "chaos_core_got", "octopus_rush_kept_logged", "pt_game", "pt_game_ledger")

# 局内状态落盘：中途重启（改代码、卡死）后 PT 上限、移除/复制次数、闪对/待冥想都还在，不会因为账没了就爆 PT
RUN_STATE_FILE = os.path.join("dev_out", "chaos_run_state.json")
RUN_STATE_MAX_AGE = 3 * 3600
# reach_final_boss 也要落盘：首领战中途重启后结算不 +1 层，速刷把第二层当第一层（2026-10-25 21:06）
_PERSIST_KEYS = RUN_LEVEL_KEYS + ("removed_card_count", "neutral_card_count", "pass_final_boss_count",
                                  "reach_final_boss")


def save_run_state(task: TriggerTask):
    cap = getattr(task, "chaos_pt_cap", None)
    ns = getattr(task, "node_status", None)
    if not cap or ns is None:
        return
    try:
        body = json.dumps({"cap": cap, "ns": {k: ns[k] for k in _PERSIST_KEYS if k in ns},
                           "deck": _member_deck_state(task)}, ensure_ascii=False, default=list, sort_keys=True)
        if body == getattr(task, "_run_state_saved", None):
            return
        os.makedirs(os.path.dirname(RUN_STATE_FILE), exist_ok=True)
        with open(RUN_STATE_FILE, "w", encoding="utf-8") as f:
            f.write(body)
        task._run_state_saved = body
    except Exception as e:  # noqa: BLE001
        task.log_info(f"局内状态落盘失败: {e}")


def clear_run_state(task: TriggerTask):
    """新一局开局（观测到可接受的上限）时清掉上一局的落盘。"""
    task._run_state_saved = None
    try:
        os.remove(RUN_STATE_FILE)
    except OSError:
        pass


def restore_run_state(task: TriggerTask):
    """启动时停在局内：读回落盘的 PT 账和局内进度。3 小时以上的旧文件不认。"""
    try:
        if time.time() - os.path.getmtime(RUN_STATE_FILE) > RUN_STATE_MAX_AGE:
            return False
        with open(RUN_STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return False
    task.chaos_pt_cap = data.get("cap")
    task.node_status.update(data.get("ns", {}))
    if isinstance(data.get("deck"), dict):
        task.member_status["deck"] = data["deck"]
    task._run_state_saved = None
    task.log_info(f"启动时在局内，读回落盘的局内状态：PT 上限 {task.chaos_pt_cap}，{data.get('ns')}")
    return True


def handle_close_button(task: TriggerTask):
    """通用关闭按钮: 检测到关闭按钮则点击关闭。"""
    box = find_box_at_point(task, 0.512, 0.929)
    if box and box.name == "关闭":
        task.log_info("检测到关闭按钮，点击关闭")
        task.click_box(box)
        task.sleep(1)
        return True
    return False


def handle_card_assign(task: TriggerTask):
    """卡牌分配页面: 按奖励优先级刷新或跳过，并优先分配给目标主战员。"""
    title_box = find_box_at_point(task, 0.863, 0.133)
    assign_prompt = _get_game_text(task, "请选择要接受卡牌的主战员")
    if not (title_box and assign_prompt in title_box.name):
        return False

    task.log_info("检测到卡牌分配页面")

    purchase_title_region = (0.326, 0.057, 0.671, 0.210)
    purchase_title_boxes = [
        b for b in task.all_texts
        if purchase_title_region[0] <= (b.x + b.width / 2) / task.width <= purchase_title_region[2]
        and purchase_title_region[1] <= (b.y + b.height / 2) / task.height <= purchase_title_region[3]
    ]
    is_purchase_page = any("购买卡牌" in b.name for b in purchase_title_boxes)
    purchase_box = None
    cancel_box = None
    card_price = None
    current_credit = None
    if is_purchase_page:
        task.log_info("检测到购买卡牌页面")
        current_credit = _get_current_credit(task)
        purchase_bottom_boxes = [
            b for b in task.all_texts
            if 0.016 <= (b.x + b.width / 2) / task.width <= 0.995
            and 0.878 <= (b.y + b.height / 2) / task.height <= 0.996
        ]
        cancel_box = next((b for b in purchase_bottom_boxes if "取消" in b.name), None)
        purchase_box = next((b for b in purchase_bottom_boxes if "购买" in b.name), None)
        price_box = next(
            (b for b in purchase_bottom_boxes if re.fullmatch(r"\d+", b.name.strip())),
            None,
        )
        if price_box:
            card_price = _parse_discounted_price(price_box.name)
        task.log_info(
            f"购买卡牌页面: 当前信用点={current_credit}，"
            f"OCR价格=「{price_box.name if price_box else ''}」，实际价格={card_price}"
        )

        if not (cancel_box and purchase_box):
            task.log_info("购买卡牌页面未完整识别取消和购买按钮")
            if cancel_box:
                task.log_info("购买卡牌页面触发识别失败取消事件，点击「取消」")
                task.click_box(cancel_box)
                task.sleep(1)
                return True
            return False
        if card_price is None:
            task.log_info("购买卡牌页面未识别到价格，按价格低于当前信用点继续购买")
        if _neutral_card_limit_reached(task):
            neutral_card_count = task.node_status.get("neutral_card_count", 0)
            neutral_card_limit = _neutral_card_limit(task)
            task.log_info(
                f"本局已获得{neutral_card_count}张中立牌，"
                f"达到固定上限{neutral_card_limit}张，点击「取消」"
            )
            task.click_box(cancel_box)
            task.sleep(1)
            return True

    assigned_cards = recognize_cards(
        task,
        region=(0.101, 0.217, 0.291, 0.365),
        page="卡牌分配页面",
    )
    assigned_card = assigned_cards[0] if assigned_cards else None
    card_name = assigned_card["name"] if assigned_card else ""
    card_desc = assigned_card["description"] if assigned_card else ""
    task.log_info(f"待分配卡牌: 名称=「{card_name}」，描述=「{card_desc}」")

    bottom_boxes = [
        b for b in task.all_texts
        if 0.290 <= (b.x + b.width / 2) / task.width <= 0.998
        and 0.878 <= (b.y + b.height / 2) / task.height <= 0.997
    ]
    refresh_text = _get_game_text(task, "刷新")
    refresh_box = next((b for b in bottom_boxes if refresh_text in b.name), None)
    skip_box = next((b for b in bottom_boxes if "跳过" in b.name), None)
    refresh_count = None
    for bottom_box in bottom_boxes:
        count_match = re.search(r'(\d+)/(\d+)', bottom_box.name)
        if count_match:
            refresh_count = (int(count_match.group(1)), int(count_match.group(2)))
            break

    reward_priority_config = _get_card_list(task, "卡牌奖励优先级")
    has_reward_priority = any(
        isinstance(item, str) and item.strip()
        for item in reward_priority_config
    )
    priority = _get_card_reward_priority(task)
    matched_card_name = next(
        (config_name for config_name in priority
         if card_name and config_name
         and (config_name in card_name or card_name in config_name)),
        None,
    )
    if matched_card_name:
        task.log_info(f"卡牌「{card_name}」命中奖励优先级「{matched_card_name}」")
    else:
        task.log_info(f"卡牌「{card_name}」未命中奖励优先级")
        if is_purchase_page:
            task.log_info("购买卡牌未命中奖励优先级，点击「取消」")
            task.click_box(cancel_box)
            task.sleep(1)
            return True
        if (
            has_reward_priority
            and refresh_box
            and refresh_count
            and refresh_count[0] > 0
        ):
            task.log_info(f"剩余刷新次数: {refresh_count[0]}/{refresh_count[1]}，点击刷新")
            task.click_box(refresh_box)
            return True
        if skip_box:
            task.log_info("无可用刷新或刷新次数，点击跳过非优先级卡牌")
            task.click_box(skip_box)
            return True

    lv_texts = _find_member_level_tags(
        task,
        (0.426, 0.292, 0.473, 0.783),
        page="卡牌分配页面",
    )
    if not lv_texts:
        task.log_info("未找到主战员leveltag特征")
        if is_purchase_page:
            task.log_info("购买卡牌页面未找到可分配战员，点击「取消」")
            task.click_box(cancel_box)
            task.sleep(1)
            return True
        return False

    target_member_index = _find_target_member_index(
        task, lv_texts, (0.484, 0.169, 0.652, 0.858)
    )

    available_members = []
    for index, level_box in enumerate(lv_texts):
        level_center_x = (level_box.x + level_box.width / 2) / task.width
        level_center_y = (level_box.y + level_box.height / 2) / task.height
        unavailable_box = find_box_at_point(
            task,
            level_center_x + 0.0615,
            level_center_y - 0.0795,
        )
        if unavailable_box and "无法获得" in unavailable_box.name:
            task.log_info(f"第{index + 1}号主战员无法获得该卡牌，排除")
            continue
        available_members.append((index, level_box))

    if not available_members:
        task.log_info("所有主战员均无法获得该卡牌")
        if is_purchase_page:
            task.log_info("购买卡牌无法分配给任何战员，点击「取消」")
            task.click_box(cancel_box)
            task.sleep(1)
            return True
        if skip_box:
            task.log_info("尝试点击跳过")
            task.click_box(skip_box)
            return True
        task.log_info("未找到跳过按钮")
        return False

    target_available = next(
        (member for member in available_members if member[0] == target_member_index),
        None,
    )
    chosen_idx, chosen_lv = target_available or available_members[0]
    if target_available:
        task.log_info(f"优先选择刷存档主战员（第{chosen_idx + 1}号）接受卡牌")
    else:
        task.log_info(f"优先选择第{chosen_idx + 1}号主战员接受卡牌")

    if (
        is_purchase_page
        and card_price is not None
        and current_credit <= card_price
    ):
        task.log_info(
            f"购买卡牌需要{card_price}信用点，当前{current_credit}，信用点不足，点击「取消」"
        )
        task.click_box(cancel_box)
        task.sleep(1)
        return True

    tracks_target_member = "刷存档主战员" in getattr(task, "default_config", {})
    if (
        target_member_index is not None and chosen_idx == target_member_index
    ) or (
        not tracks_target_member and chosen_idx == 0
    ):
        deck = _member_deck_state(task)
        deck[matched_card_name or card_name] = card_desc
    _move_and_click(task, 0.756, (chosen_lv.y + chosen_lv.height / 2) / task.height)
    task.sleep(1)
    if is_purchase_page:
        task.log_info(
            f"购买卡牌需要{card_price}信用点，当前{current_credit}，点击「购买」"
        )
        task.click_box(purchase_box)
        _record_neutral_card(task)
        task.sleep(1)
        return True
    if not chaos_strategy.memory_name(card_name):   # 赛季记忆卡也走分配页，不算中立牌
        _record_neutral_card(task)
    return False

def handle_held_cards_page(task: TriggerTask):
    """持有卡牌页面: 检测到持有卡牌则关闭页面。"""
    box = find_box_at_point(task, 0.500, 0.056)
    if box and box.name == _get_game_text(task, '持有卡牌'):
        task.log_info("检测到持有卡牌页面，点击关闭")
        _move_and_click(task, 0.966, 0.053)
        return True
    return False

def handle_weakness_info(task: TriggerTask):
    """怪物信息页面: 检测到弱点信息则关闭页面。"""
    box = find_box_at_point(task, 0.387, 0.107)
    if box and "弱点" in box.name:
        task.log_info("检测到怪物信息页面，点击关闭")
        _move_and_click(task, 0.502, 0.092)
        return True
    return False

def handle_minimizemap(task: TriggerTask):
    """地图页面: 检测到小地图按钮则点击关闭小地图。"""
    boxes = task.find_feature(feature_name="minimizemap")
    if boxes:
        task.log_info("检测到地图页面，点击关闭小地图")
        task.click_box(boxes[0])
        return True
    return False

def handle_storage_full(task: TriggerTask):
    """「存储空间不足：你已超出存储数据的保留限制，请清理并重新进入」——存档满了进不去卡厄思。
    2026-10-25 实录：玩法模式不自动分解存档，攒满后脚本在「进入」和这个弹窗的「确认」之间循环 10 分钟。
    删哪个存档由用户决定，这里关掉弹窗、通知并停止任务。"""
    if not any("存储空间不足" in b.name or "超出存储数据的保留限制" in b.name for b in task.all_texts or []):
        return False
    chaos_trace.step(task, "page", "存储空间不足", task.frame)
    import save_cleanup
    go = next((b for b in task.all_texts if _clean_match(b.name, "前往")), None)
    if save_cleanup.enabled(task) and go and getattr(task, "save_cleanup_last", None) != 0:
        # 用户 2026-10-25 定：脚本自动清理（空白存档、目标主战员的存档保留）；上次清理一个都没删掉就不再试
        task.log_info("存档存储空间已满，去分解页自动清理")
        save_cleanup.start(task)
        task.click_box(go)
        task.sleep(2)
        return True
    box = next((b for b in task.all_texts if _clean_match(b.name, "确认")), None)
    if box:
        task.click_box(box)
    task.log_info("存档存储空间已满，进不去卡厄思：自动清理没开或腾不出位置，请手动清理存档后再开始，停止任务", notify=True)
    task.disable()
    return True


def handle_non_battle_page(task: TriggerTask):
    """非出击/卡厄思页面: 检测到故事/营救/方舟城市时自动停止当前模式，优先级最高。"""
    if handle_storage_full(task):
        return True
    box = find_box_at_point(task, 0.887, 0.160)
    if box and box.name == "故事":
        task.log_info("检测到故事页面，停止当前模式")
        task.disable()
        return True
    box = find_box_at_point(task, 0.101, 0.046)
    if box and box.name == "营救":
        task.log_info("检测到营救页面，停止当前模式")
        task.disable()
        return True
    box = find_box_at_point(task, 0.124, 0.049)
    if box and box.name == "方舟城市":
        task.log_info("检测到方舟城市页面，停止当前模式")
        task.disable()
        return True
    return False

def handle_unknown_page(task: TriggerTask):
    """检测到待确认的未知页面: 确认按钮不可点击时随机点击页面中央区域。"""
    box = find_box_at_point(task, 0.916, 0.931)
    if box and _clean_match(box.name, "确认") and not is_button_active(task, box):
        task.log_info("检测到待确认的未知页面，确认按钮不可点击，随机点击页面区域")
        import random
        rx = random.uniform(0.043, 0.972)
        ry = random.uniform(0.149, 0.843)
        _move_and_click(task, rx, ry)
        task.sleep(1)
        return True
    return False
