# 卡厄思局内策略：按玩法（探索度 / 刷存档-空存 / 刷存档-目标卡组）给事件选项打分，并把玩法翻译成现有 handler 用的配置项
# 只放纯函数和数据，不依赖 ok 框架，方便单测；设计见 2game-helper/docs/czn-chaos-design.md 第 3 节
import json
import os
import re

from game_db import containment, get_db, norm, similarity

MODE_LEGACY = "原有逻辑"
MODE_EXPLORE = "探索度"
MODE_EMPTY = "刷存档-空存"
MODE_TARGET = "刷存档-目标卡组"
MODES = [MODE_LEGACY, MODE_EXPLORE, MODE_EMPTY, MODE_TARGET]

# 每份存档最多记 5 次移除；空存时目标的卡超过这个数就删不干净
REMOVE_LIMIT = 5
# 起始卡组：3 张基础卡 + 1 张独特起始卡
START_DECK_SIZE = 4

SEEN_FILE = os.path.join("configs", "chaos_seen.json")


# 路线权重（越大越优先，整条路径求和）；商店是休息点上的标记，额外加分。见设计文档 3.1
ROUTE_WEIGHTS = {
    MODE_EXPLORE: {"types": {"事件": 6, "休息": 3, "小怪": 3, "精英": 3, "结算": 0},
                   "shop": -1, "special": {"kalei_in_map": 1, "seal_in_map": 1, "hard_in_map": 1}},
    MODE_EMPTY: {"types": {"事件": 5, "休息": 4, "小怪": 2, "精英": 1, "结算": 0},
                 "shop": 2, "special": {"kalei_in_map": 1, "seal_in_map": 0, "hard_in_map": -2}},
    MODE_TARGET: {"types": {"事件": 4, "休息": 3, "小怪": 3, "精英": 2, "结算": 0},
                  "shop": 1, "special": {"kalei_in_map": 1, "seal_in_map": 0, "hard_in_map": -1}},
}


# ---------------- 从选项文字解析效果（数据库没命中时的兜底） ----------------

_CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5}


def _num(s):
    return int(s) if s.isdigit() else _CN_NUM.get(s, 1)


def parse_effects(text):
    """从画面上的选项文字（选项名 + 结果说明）粗略解析出效果，键名和 events.json 的 effects 一致。"""
    t = norm(text)
    e = {}
    if m := re.search(r"移除(所有|全部)咒术", t):
        e["remove_curse_all"] = True
    elif m := re.search(r"移除(\d|[一两二三四五])张", t):
        e["remove_card"] = _num(m.group(1))
    elif "移除" in t and "卡" in t:
        e["remove_card"] = 1
    if re.search(r"信用点(减少|消耗)(100#%|全部|所有)|献上一切信用点", t):
        e["credit"] = -999
    elif m := re.search(r"信用点(增加|获得|\+)(\d+)", t):
        e["credit"] = int(m.group(2))
    elif m := re.search(r"信用点(减少|消耗|-)(\d+)", t):
        e["credit"] = -int(m.group(2))
    if "神之闪光" in t or "神闪" in t:
        e["god_spark"] = True
    elif "闪光" in t:
        e["spark"] = True
    if "复制" in t:
        e["copy_card"] = 1
    if "中立" in t:
        e["neutral_card"] = 1
    if "咒术" in t and "移除" not in t:
        e["curse_card"] = 1
    if "转换" in t:
        e["transform_card"] = 1
    if "战斗" in t or "攻击" in t:
        e["battle"] = True
    if m := re.search(r"压力(增加|上升)(\d+)?", t):
        e["stress"] = int(m.group(2) or 1)
    elif m := re.search(r"压力(减少|降低)(\d+)?", t):
        e["stress"] = -int(m.group(2) or 1)
    if re.search(r"生命值?(变为|降为|变成)1(?!\d)", t):
        e["hp_to_one"] = True
    elif re.search(r"(恢复|回复)\S*生命", t):
        e["hp_pct"] = 1
    elif re.search(r"(失去|减少)\S*生命", t):
        e["hp_pct"] = -1
    if "装备" in t and "失去" not in t:
        e["equipment"] = ["?"]
    return e


# ---------------- 事件选项对到数据库 ----------------

def _option_texts(o):
    raw = o.get("raw")
    if isinstance(raw, dict):
        raw = raw.get("success", []) + raw.get("fail", [])
    return [t for t in (o.get("text"), o.get("text_intl")) if t], "".join(raw or [])


def _iter_options(event):
    stack = list(event.get("options", []))
    while stack:
        o = stack.pop(0)
        yield o
        stack.extend(o.get("next", []))


def _option_score(o, desc):
    names, raw = _option_texts(o)
    best = 0.0
    for n in names:
        # 画面上的选项框 = 选项名 + 结果说明，所以看选项名被包含了多少，再拿结果说明补一点
        s = containment(n, desc) * 0.8 + (similarity(raw, desc) * 0.2 if raw else 0.0)
        best = max(best, s, similarity(n + raw, desc))
    return best


def match_event_options(descs, db=None, region=None, min_score=0.6):
    """把一组画面上的选项文字对到同一个事件，返回 (事件, [每个选项对应的库选项或 None])。"""
    db = db or get_db()
    best_event, best_opts, best_total = None, [None] * len(descs), 0.0
    for e in db.iter_events(region):
        opts = list(_iter_options(e))
        picked, total = [], 0.0
        for d in descs:
            scored = max(((_option_score(o, d), o) for o in opts), key=lambda x: x[0], default=(0.0, None))
            if scored[0] >= min_score:
                picked.append(scored[1])
                total += scored[0]
            else:
                picked.append(None)
        if total > best_total:
            best_event, best_opts, best_total = e, picked, total
    if best_event is None:
        return None, [None] * len(descs)
    return best_event, best_opts


# ---------------- 打分 ----------------

def score_effects(effects, mode, state=None):
    """按玩法给一组效果打分，返回 (分数, 理由列表)。state 里有本局进度（已删几张、信用点、血量、已见选项等）。"""
    state = state or {}
    s, why = 0.0, []

    def add(v, reason):
        nonlocal s
        s += v
        why.append(f"{reason}{v:+g}")

    removed = state.get("removed", 0)
    can_remove = removed < REMOVE_LIMIT
    rm = effects.get("remove_card") or 0
    credit = effects.get("credit") or 0
    hp = effects.get("hp_pct") or 0
    stress = effects.get("stress") or 0

    if mode == MODE_EMPTY:
        if rm and can_remove:
            add(30 * min(rm, REMOVE_LIMIT - removed), f"移除{rm}张")
        if effects.get("remove_curse_all"):
            add(15, "移除全部咒术")
        if effects.get("transform_card"):
            add(-10, "转换卡")
        for k, v, reason in (("spark", -25, "闪光"), ("god_spark", -30, "神闪"), ("neutral_card", -20, "中立卡"),
                             ("copy_card", -20, "复制"), ("curse_card", -15, "咒术卡"), ("event_card", -15, "获得卡"),
                             ("card_choice", -15, "选卡"), ("lumen_card", -10, "获得卡"), ("desire_card", -10, "获得卡")):
            if effects.get(k):
                add(v, reason)
        if credit:
            add(max(-20, min(20, credit / 6)), "信用点")
        if effects.get("battle"):
            add(-6, "战斗")
    elif mode == MODE_TARGET:
        if rm and can_remove and state.get("need_remove", 0) > 0:
            add(12 * min(rm, state["need_remove"]), f"移除{rm}张")
        elif rm:
            add(-5, "多余的移除")
        if effects.get("copy_card"):
            add(15 if state.get("need_copy", 0) > 0 else -5, "复制")
        if effects.get("spark"):
            add(10 if state.get("need_spark", 0) > 0 else -3, "闪光")
        if effects.get("god_spark"):
            add(8 if state.get("need_god_spark", 0) > 0 else -15, "神闪")
        for k, v, reason in (("neutral_card", -10, "中立卡"), ("curse_card", -15, "咒术卡"), ("event_card", -8, "获得卡")):
            if effects.get(k):
                add(v, reason)
        if credit:
            add(max(-15, min(15, credit / 8)), "信用点")
        if effects.get("equipment"):
            add(4, "装备")
    elif mode == MODE_EXPLORE:
        if state.get("unseen"):
            add(40, "没见过的选项")
        if credit:
            add(max(-10, min(10, credit / 10)), "信用点")
        if effects.get("equipment"):
            add(4, "装备")
        if effects.get("curse_card"):
            add(-8, "咒术卡")
        if effects.get("battle"):
            add(2, "战斗（新怪物）")
    if hp:
        low = state.get("hp_pct", 100) < 50
        add((8 if low else 2) * (1 if hp > 0 else -1) * (2 if hp < 0 and low else 1), "生命")
    if stress:
        add(-3 * stress if stress > 0 else 3, "压力")
    if effects.get("max_hp_pct"):
        add(3 if effects["max_hp_pct"] > 0 else -6, "最大生命")
    if effects.get("hp_to_one"):
        add(-60, "生命值变为1")
    if effects.get("equipment_lost"):
        add(-6, "失去装备")
    if effects.get("requires_credit", 0) > state.get("credit", 10 ** 9):
        add(-100, "信用点不够")
    return s, why


def _effects_of(option):
    e = dict(option.get("effects", {}))
    req = option.get("requires") or ""
    if m := re.search(r"(\d+)以上的信用点", req):
        e["requires_credit"] = int(m.group(1))
    return e


def pick_event_option(descs, mode, state=None, db=None):
    """给画面上的几个事件选项打分。返回 (最佳下标, [(分数, 理由, 来源)])。"""
    state = dict(state or {})
    event, matched = match_event_options(descs, db=db)
    seen = state.get("seen") or set()
    results = []
    for d, o in zip(descs, matched):
        if o is not None:
            # 库里只有选项名没有效果（如开局的凯尔肯的传令兵）时，用画面上的效果说明补
            effects = {**parse_effects(d), **_effects_of(o)}
            src = f"库:{event['name']}/{o.get('text')}"
            st = dict(state, unseen=o.get("id") not in seen)
        else:
            effects = parse_effects(d)
            src = "文字解析"
            st = dict(state, unseen=False)
        score, why = score_effects(effects, mode, st)
        results.append((score, why, src, o.get("id") if o else None))
    if not results:
        return None, results
    best = max(range(len(results)), key=lambda i: results[i][0])
    return best, results


# ---------------- 「已见」记录（探索度） ----------------

def load_seen(path=SEEN_FILE):
    try:
        with open(path, encoding="utf-8") as f:
            return set(json.load(f).get("options", []))
    except (OSError, ValueError):
        return set()


def save_seen(seen, path=SEEN_FILE):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"options": sorted(seen)}, f, ensure_ascii=False, indent=1)


# ---------------- 目标卡组 ----------------

def deck_plan(member, preset, db=None):
    """对比起始卡组和预设，算出目标卡组还要做什么：删哪些、复制哪些、哪些卡要闪光成什么样。

    preset = utils_chaos_prep.read_deck_preset 的返回值（cards: [{name, n, god_spark, desc}]）。
    """
    db = db or get_db()
    want = {}
    for c in preset.get("cards", []):
        want.setdefault(c["name"], []).append(c)
    start_names = {}
    for c in db.cards_of(member, sorts=("基础卡牌",)):
        start_names[c["name"]] = start_names.get(c["name"], 0) + 1
    remove = []
    for name, n in start_names.items():
        remove += [name] * max(0, n - len(want.get(name, [])))
    copy = []
    for name, cs in want.items():
        extra = len(cs) - max(1, start_names.get(name, 0))
        copy += [name] * max(0, extra)
    flash = [c for c in preset.get("cards", []) if c.get("n") or c.get("god_spark")]
    return {"remove": remove, "copy": copy, "flash": flash}


def pick_flash_variant(card_name, choices, target_cards, db=None):
    """闪光三选一：choices=[{name, description}]，target_cards=预设里同名卡。返回最像预设的下标，没有就 None。"""
    db = db or get_db()
    best, best_s = None, 0.0
    for i, ch in enumerate(choices):
        for t in target_cards:
            if t.get("name") != card_name or not t.get("desc"):
                continue
            s = similarity(ch.get("description", ""), t["desc"])
            if s > best_s:
                best, best_s = i, s
    return best if best_s >= 0.8 else None


# ---------------- 玩法 → 现有配置项 ----------------

def config_overrides(mode, member=None, plan=None, db=None):
    """把玩法翻译成现有 handler 读的配置项（_get_config_value 会先查这里）。原有逻辑返回空字典。"""
    db = db or get_db()
    if mode == MODE_EMPTY:
        names = sorted({c["name"] for c in db.cards_of(member)}) if member else []
        return {
            "刷空档": True,
            "刷初始卡牌": "",
            "首层刷特定闪光": False,
            "优先移除基础牌": False,
            "移除卡牌列表": names,
            "闪光卡牌列表": [],
            "复制卡牌列表": [],
            "闪光优先级": [],
            "卡牌奖励优先级": [],
            "任务优先级": ["移除2张", "移除"],
            "拉黑任务": ["咒术卡牌", "压力", "复制", "闪光", "中立"],
            "路线优先级": ["事件", "休息", "小怪", "精英"],
            "进入商店": True,
            "保留大于多少TB的存档": 0,
        }
    if mode == MODE_TARGET:
        plan = plan or {}
        flash_names = [c["name"] for c in plan.get("flash", [])]
        return {
            "刷空档": False,
            "刷初始卡牌": "",
            "优先移除基础牌": False,
            "移除卡牌列表": list(dict.fromkeys(plan.get("remove", []))),
            "闪光卡牌列表": list(dict.fromkeys(flash_names)),
            "复制卡牌列表": list(dict.fromkeys(plan.get("copy", []))),
            "卡牌奖励优先级": list(dict.fromkeys(flash_names)),
            "任务优先级": ["复制", "移除", "信用点增加"],
            "拉黑任务": ["咒术卡牌", "压力"],
            "路线优先级": ["事件", "休息", "小怪", "精英"],
            "进入商店": True,
        }
    if mode == MODE_EXPLORE:
        return {
            "刷空档": False,
            "刷初始卡牌": "",
            "任务优先级": [],
            "拉黑任务": ["咒术卡牌"],
            "路线优先级": ["事件", "小怪", "精英", "休息"],
        }
    return {}
