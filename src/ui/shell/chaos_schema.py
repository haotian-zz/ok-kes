"""卡厄思页的结构：方案、分段、切方案时联动的设置、「由方案决定」只读段（不依赖 Qt，方便单测）。

存储格式不变：方案就是 configs/ChaosMode.json 里的「卡厄思玩法」，各项还是原来的键。
每个键在哪些方案下显示由任务自己的 ``sub_configs`` 声明（ok_tasks/ChaosMode.py 的 SCHEME_KEYS），
这里只管分段、顺序和界面上的联动。
"""

from __future__ import annotations

import json
import os

SCHEME_KEY = "卡厄思玩法"
MODE_LEGACY = "原有逻辑"
MODE_EXPLORE = "探索度"
MODE_EMPTY = "刷存档-空存"
MODE_TARGET = "刷存档-目标卡组"
# 分段按钮的顺序（用户 2026-10-28：章鱼哥速刷、刷刻印不是方案，是目标卡组里的细分设置）
SCHEMES = [MODE_EXPLORE, MODE_EMPTY, MODE_TARGET, MODE_LEGACY]
SCHEME_HINTS = {
    MODE_EXPLORE: "活动卡厄思打最高难度，优先没见过的事件选项，删卡/闪光按目标的预设",
    MODE_EMPTY: "删光目标主战员的卡，避开闪光和获得卡，到第一个航点存档就逃脱",
    MODE_TARGET: "按目标主战员的预设构筑删卡、复制、闪光；可再开章鱼哥速刷或刷刻印",
    MODE_LEGACY: "不按方案推导，下面的删卡/闪光/复制/路线列表原样生效",
}

NEUTRAL_SKIP = "中立卡不拿"
EQUIP_TARGET_FIRST = "装备优先给目标"
FLASH_EQUIP_NOT_TARGET = "会触发闪光的装备不给目标"
EMPTY_FLASH_LIMIT = "刷空档闪光几张就重开"
EMPTY_TARGETS = "刷空档目标顺序"
OCTOPUS_RUSH = "章鱼哥速刷"
OCTOPUS_CORE_ONLY = "章鱼哥速刷只认混沌之识"
IMPRINT_KEY = "刷刻印"
IMPRINT_SUB_KEYS = [
    "刷刻印速刷", "刻印法典地图", "刻印法典难度", "刻印法典赛季特性", "刻印法典稀有命运至少",
    "刻印法典禁止词条", "刻印法典槽位", "刻印法典最多合成次数", "目标刻印关键词", "刷刻印对账",
]
REWARD_KEYS = [
    "额外战利品：有战利品验证卡就用",
    "额外战利品：验证卡用完后用体力兑换",
    "额外战利品：体力不足时用免费道具补充体力",
]

# (分段标题, 键)。没在当前方案下显示的键会被藏起来，整段都藏了就不画这一段。
SECTIONS = [
    ("队伍", ["目标主战员", "目标预设", "刷存档主战员", "自动编队", "队友", EMPTY_TARGETS]),
    ("入场", [
        "卡厄思地图", "刷存档难度", "刷存档最低PT", "刷存档开梦境模式", "调整零式升级",
        "探索度达到多少级后改刷目标卡组", "存储数据保存上限大于多少", "保留大于多少TB的存档",
    ]),
    ("目标卡组细分", [OCTOPUS_RUSH, OCTOPUS_CORE_ONLY, IMPRINT_KEY, *IMPRINT_SUB_KEYS]),
    ("卡组规则", [
        EMPTY_FLASH_LIMIT, NEUTRAL_SKIP, "刷空档", "刷初始卡牌", "优先移除基础牌", "移除卡牌列表", "闪光卡牌列表",
        "复制卡牌列表", "闪光优先级", "首层刷特定闪光", "需要冥想的卡牌", "多少信用点以上冥想", "卡牌奖励优先级",
        "任务优先级", "拉黑任务", "指定记忆卡牌", "指定面具卡牌", "面具卡牌刻印",
    ]),
    ("装备", ["装备1号位优先级", "装备2号位优先级", "装备3号位优先级", EQUIP_TARGET_FIRST, FLASH_EQUIP_NOT_TARGET]),
    ("路线与商店", ["路线优先级", "进入商店", "商店刷新信用点阈值"]),
    ("逃脱与停止", ["只打第一层", "几轮后停止(0为不停止)", "第几层boss前自动暂停", "治疗崩溃", "优先使用金币治疗"]),
    ("通用", [
        "游戏语言", "三倍速", "记录流程追踪", "存档满了自动清理", "存档清理保留空白存档", *REWARD_KEYS, "配置操作",
    ]),
]

# 只靠界面绑方案的开关：代码里不分方案都读，所以方案下看不到时要关掉，不然藏着还在生效。
# 值：在哪些方案下显示（和 ChaosMode.SCHEME_KEYS 一致）。
SCHEME_BOUND = {
    NEUTRAL_SKIP: (MODE_EMPTY,),
    EQUIP_TARGET_FIRST: (MODE_EMPTY,),
    FLASH_EQUIP_NOT_TARGET: (MODE_EXPLORE, MODE_EMPTY, MODE_TARGET),
    OCTOPUS_RUSH: (MODE_TARGET,),
    IMPRINT_KEY: (MODE_TARGET,),
}
# 切到空存时自动打开（设计文档 4.4「方案专属默认值」）
EMPTY_ON = (NEUTRAL_SKIP, EQUIP_TARGET_FIRST, FLASH_EQUIP_NOT_TARGET)
# 开了刷刻印就走零式系统法典，用法典自己的地图和难度
IMPRINT_REPLACES = ("卡厄思地图", "刷存档难度")


def scheme_of(config) -> str:
    mode = config.get(SCHEME_KEY, MODE_LEGACY)
    return mode if mode in SCHEMES else MODE_LEGACY


def extra_hidden(config) -> set[str]:
    """sub_configs 表达不了的隐藏：开了刷刻印时，赛季卡厄思的地图和难度不读。"""
    if scheme_of(config) == MODE_TARGET and config.get(IMPRINT_KEY) is True:
        return set(IMPRINT_REPLACES)
    return set()


def all_section_keys() -> list[str]:
    return [key for _title, keys in SECTIONS for key in keys]


def visible_keys(task, config=None) -> list[str]:
    """当前方案下界面显示的键（不含方案本身）。"""
    from src.ui.shell import config_rules

    config = task.config if config is None else config
    keys = config_rules.visible_keys(task, all_section_keys(), config)
    hidden = extra_hidden(config)
    return [key for key in keys if key not in hidden and key in config]


def apply_scheme(config, mode: str) -> list[str]:
    """切方案：写「卡厄思玩法」，再按方案联动几项开关。返回改了什么（给界面提示）。"""
    if mode not in SCHEMES:
        return []
    changes = []
    if config.get(SCHEME_KEY) != mode:
        config[SCHEME_KEY] = mode
    for key, schemes in SCHEME_BOUND.items():
        if key in config and mode not in schemes and config.get(key) is True:
            config[key] = False
            changes.append(f"{key}：关")
    if mode == MODE_EMPTY:
        for key in EMPTY_ON:
            if key in config and config.get(key) is not True:
                config[key] = True
                changes.append(f"{key}：开")
    return changes


def hidden_but_active(config) -> list[str]:
    """当前方案下看不到、却开着还在生效的开关（手改了文件、导入了配置、旧界面改过）。"""
    mode = scheme_of(config)
    return [key for key, schemes in SCHEME_BOUND.items() if mode not in schemes and config.get(key) is True]


# ---------------------------------------------------------------- 由方案决定（只读）

PLAN_KEYS = ("移除卡牌列表", "闪光卡牌列表", "复制卡牌列表", "卡牌奖励优先级", "需要冥想的卡牌", "指定记忆卡牌", "指定记忆描述")
TARGET_DECK_FILE = os.path.join("configs", "chaos_target_deck.json")


def cached_deck(member, preset, path: str = TARGET_DECK_FILE):
    """configs/chaos_target_deck.json（开局读预设时缓存的），主战员和预设号对上才算。"""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("member") != member or int(data.get("preset", 0)) != int(preset):
            return None
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    try:
        # 和任务开局时一样：缓存里认不出的卡名（OCR 错字）重新对一次库
        from ChaosMode import _rematch_unknown_cards

        _rematch_unknown_cards(data)
    except Exception:
        pass
    return data


def _text(value) -> str:
    if isinstance(value, bool):
        return "开" if value else "关"
    if isinstance(value, (list, tuple)):
        return "、".join(str(v) for v in value) if value else "（空）"
    if value in ("", None):
        return "（空）"
    return str(value)


def decided_by_scheme(config, deck_path: str = TARGET_DECK_FILE) -> dict:
    """「由方案决定」段：{"note": 一句话, "rows": [(名称, 值文字)], "warnings": [...]}。

    探索度/目标卡组要读目标主战员的预设：缓存里主战员和预设号对得上就按缓存算，否则那几项写「开局时读预设」。
    """
    import chaos_strategy

    mode = scheme_of(config)
    warnings = [f"「{key}」在这个方案下不显示，但还开着、仍会生效" for key in hidden_but_active(config)]
    if mode == MODE_LEGACY:
        return {"note": "原有逻辑：不推导，下面每一项按填的值生效。", "rows": [], "warnings": warnings}
    member = config.get("目标主战员", "")
    preset = config.get("目标预设", 1)
    plan = None
    note = ""
    if mode in (MODE_TARGET, MODE_EXPLORE):
        deck = cached_deck(member, preset, deck_path)
        if deck:
            plan = chaos_strategy.deck_plan(member, deck)
            note = f"按缓存的「{member}」{preset} 号预设（{len(deck.get('cards') or [])} 张卡）推导；开局时会重新读一次。"
        else:
            note = f"还没缓存「{member}」{preset} 号预设，删卡/闪光/复制几项开局时读预设再定。"
    else:
        note = f"按「{member}」的卡库推导：目标的卡全删。"
    overrides = chaos_strategy.config_overrides(mode, member, plan if plan is not None else {})
    if member:
        overrides["刷存档主战员"] = member
    rows = []
    for key, value in overrides.items():
        if plan is None and mode != MODE_EMPTY and key in PLAN_KEYS:
            rows.append((key, "开局时读预设"))
        else:
            rows.append((key, _text(value)))
    octopus = config.get(OCTOPUS_RUSH) is True and mode == MODE_TARGET
    imprint = config.get(IMPRINT_KEY) is True and mode == MODE_TARGET
    weights = chaos_strategy.route_weights(mode, 0, octopus=octopus, imprint=imprint)
    if weights:
        order = sorted(weights["types"].items(), key=lambda kv: -kv[1])
        text = " > ".join(f"{name}{score}" for name, score in order if name != "结算")
        rows.append(("第一层路线权重", f"{text}，商店 +{weights.get('shop', 0)}"))
    if config.get("调整零式升级"):
        zero, full = chaos_strategy.zero_upgrade_wants(mode, octopus=config.get(OCTOPUS_RUSH) is True)
        if zero or full:
            rows.append(("零式升级", f"0 级：{_text(zero)}；满级：{_text(full)}"))
    return {"note": note, "rows": rows, "warnings": warnings}
