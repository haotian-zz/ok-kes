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
# 活动卡厄思「凝结于雪上的约定」：精英战必给 1 个记忆残片（赛季记忆卡升阶材料，普通战只是概率掉），
# 所以所有玩法精英都高于普通战（用户 2026-10-25）；血量低时 route_weights 再把精英压回去。
ROUTE_WEIGHTS = {
    MODE_EXPLORE: {"types": {"事件": 6, "休息": 3, "小怪": 3, "精英": 4, "结算": 0},
                   "shop": -1, "special": {"kalei_in_map": 1, "seal_in_map": 1, "hard_in_map": 1}},
    MODE_EMPTY: {"types": {"事件": 5, "休息": 4, "小怪": 2, "精英": 3, "结算": 0},
                 "shop": 2, "special": {"kalei_in_map": 1, "seal_in_map": 0, "hard_in_map": -2}},
    MODE_TARGET: {"types": {"事件": 4, "休息": 3, "小怪": 2, "精英": 5, "结算": 0},
                  "shop": 1, "special": {"kalei_in_map": 1, "seal_in_map": 0, "hard_in_map": -1}},
}

LOW_HP_ROUTE = 40          # 规划整层路线时血量低于这个，精英不再优先、休息加分
EVENT_SOURCE_BONUS = 3     # 本层有只能靠事件拿的目标装备时，事件节点加分
AREA_LAYER = {"外围": 0, "核心": 1}   # 事件库 area → 层号（从 0 起）


def route_weights(mode, layer=0, hp=None, event_bonus=0):
    """按本层情况调整路线权重：血量低精英降到普通战、休息 +2；本层有目标装备的来源事件时事件加分。"""
    base = ROUTE_WEIGHTS.get(mode)
    if not base:
        return base
    w = {**base, "types": dict(base["types"])}
    t = w["types"]
    if hp is not None and hp is not False and hp < LOW_HP_ROUTE:
        t["精英"] = min(t["精英"], t["小怪"])
        t["休息"] += 2
    t["事件"] += event_bonus
    return w


def equipment_event_sources(names, db=None):
    """目标装备里写明「事件-X」才能拿的：返回 [{装备, 事件, 选项, 层}]（层 None = 不限）。
    装备库 obtain 形如「天上防护墙：事件-前往更深之处」，事件库里找给这件装备的选项。"""
    db = db or get_db()
    out = []
    for name in names:
        eq = db.find_equipment(name)
        obtain = (eq or {}).get("obtain") or ""
        m = re.search(r"事件\s*[-－:：]\s*([^；;，,]+)", obtain)
        if not m:
            continue
        event_name = norm(m.group(1))
        for e in db.iter_events():
            if norm(e.get("name", "")) != event_name:
                continue
            for o in e.get("options", []):
                if any(norm(x) == norm(eq["name"]) for x in (o.get("effects") or {}).get("equipment") or []):
                    out.append({"equipment": eq["name"], "event": e["name"], "option": o.get("text"),
                                "layer": AREA_LAYER.get(e.get("area"))})
    return out


def event_source_bonus(sources, layer, owned=()):
    """本层（或不限层）还有没拿到的目标装备来源事件 → 事件节点加分。"""
    owned = {norm(n) for n in owned if n}
    for src in sources:
        if norm(src["equipment"]) in owned:
            continue
        if src["layer"] is None or src["layer"] == layer:
            return EVENT_SOURCE_BONUS
    return 0


# ---------------- 从选项文字解析效果（数据库没命中时的兜底） ----------------

_CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5}


def _num(s):
    return int(s) if s.isdigit() else _CN_NUM.get(s, 1)


GOD_NAMES = r"迪亚洛斯|尼希勒姆|瑟克洛斯|维托尔|CALIGO|caligo|卡利戈|戴奥斯"


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
    # OCR 多行乱序会把「神之闪光」拆成「神之滚动骰子10闪光」（2026-10-24 实机），所以「神之」+「闪光」也算
    # 带神名的闪光也是神闪：「赋予1张所选卡牌迪亚洛斯闪光」（2026-10-24 实机当成普通闪光选了，神闪落到剑鸣九霄上，存档报废）
    if "神之闪光" in t or "神闪" in t or ("神之" in t and "闪光" in t) or \
            (re.search(GOD_NAMES, t) and "闪光" in t):
        e["god_spark"] = True
    elif "闪光" in t:
        e["spark"] = True
    if "复制" in t:
        e["copy_card"] = 1
        if "随机" in t or re.search(r"\d张\S{0,6}中选", t):
            e["copy_random"] = True      # 随机 3 张稀有里选 1：不一定有要复制的卡
    if "中立" in t:
        e["neutral_card"] = 1
    if "咒术" in t and "移除" not in t:
        e["curse_card"] = 1
    if "转换" in t:
        e["transform_card"] = 1
    # 「普通战斗3次期间…」是之后战斗的 buff，不是这个选项要打一场
    if re.search(r"攻击|战斗(?!\d*次期间)", re.sub(r"(普通|精英)?战斗\d*次期间", "", t)):
        e["battle"] = True
    if m := re.search(r"压力(增加|上升)(\d+)?", t):
        e["stress"] = int(m.group(2) or 1)
    elif m := re.search(r"压力(减少|降低)(\d+)?", t):
        e["stress"] = -int(m.group(2) or 1)
    # OCR 多行乱序时「期间异」「形生命值变为1」会被拆开，所以「战斗N次期间…生命值变为1」也算异形
    if re.search(r"(异形|敌人|敌方|怪物)\S{0,4}生命值?(变为|降为|变成)1(?!\d)", t) or \
            (re.search(r"战斗\d*次期间", t) and re.search(r"生命值?(变为|降为|变成)1(?!\d)", t)):
        e["enemy_hp_to_one"] = True    # 「普通战斗3次期间异形生命值变为1」对我方是好事
    elif re.search(r"生命值?(变为|降为|变成)1(?!\d)", t):
        e["hp_to_one"] = True
    elif re.search(r"(恢复|回复)\S*生命", t):
        e["hp_pct"] = 1
    elif re.search(r"(失去|减少)\S*生命", t):
        e["hp_pct"] = -1
    if "装备" in t and "失去" not in t:
        # norm 会去掉方括号，装备名要从原文抽
        names = [norm(n) for n in re.findall(r"装备\s*[\[［【]([^\]］】]+)[\]］】]", text or "")]
        # 「随机获得稀有~传说装备」：没有名字的随机池，记成池子（探索度 +50，和库里匹配上的一致）
        e["equipment"] = names or (["随机装备"] if "随机" in t else ["?"])
    if e.get("spark"):
        if re.search(r"(选择|选中)\S{0,3}张?卡牌?\S{0,4}闪光|卡牌闪光", t) and "主战员" not in t:
            e["spark_card"] = True       # 自己挑 1 张卡闪光（用户 2026-10-24：优先于挑主战员）
        elif "选中" in t or "选择" in t:
            e["spark_choose"] = True     # 选一个主战员闪光
        elif "随机" in t and "卡牌" in t and "主战员" not in t:
            e["spark_random_card"] = True  # 随机 1 张卡闪光（可能闪到队友的卡）
        elif "随机" in t:
            e["spark_random"] = True     # 随机主战员闪光
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
        # 用户 2026-10-24 定的优先级（分档，档间差距大）：目标装备 > 复制 > 中立卡（预设里有中立卡时）> 删卡（还没删够）
        # > 选择卡牌闪光 > 选中主战员闪光 > ≥200 信用点 > 随机主战员闪光 > 随机卡牌闪光 > 其他装备 > <200 信用点
        # > 神闪（预设要求时；局内最好不神闪）> 战斗；回血按血量动态，但不超过 ≥200 信用点
        equip = effects.get("equipment") or []
        targets = state.get("target_equipment") or []
        if any(n != "?" and any(norm(n) in norm(t) or norm(t) in norm(n) for t in targets) for n in equip):
            add(1000, "目标装备")
        elif equip:
            add(40, "装备")
        if effects.get("copy_card"):
            # 用户 2026-10-24：复制会带上卡的一切（闪光等）；随机 3 选 1 的复制放到选择闪光后面
            if state.get("need_copy", 0) <= 0:
                add(-5, "复制")
            elif effects.get("copy_random"):
                add(140, "随机复制")
            else:
                add(300, "复制")
        if effects.get("neutral_card"):
            add(250 if state.get("need_neutral", 0) > 0 else -10, "中立卡")
        if rm and can_remove and state.get("need_remove", 0) > 0:
            add(200, f"移除{rm}张")
        elif rm:
            add(-5, "多余的移除")
        if effects.get("spark") and state.get("need_spark", 0) > 0:
            if effects.get("spark_card"):
                add(170, "选择卡牌闪光")
            elif effects.get("spark_random_card"):
                add(50, "随机卡牌闪光")
            elif effects.get("spark_random"):
                add(60, "随机主战员闪光")
            else:
                add(150, "选中主战员闪光")
        elif effects.get("spark"):
            add(-3, "多余的闪光")
        if effects.get("god_spark"):
            # 用户 2026-10-24：局内神闪闪错卡就「爆存档」（局外也撤销不了），局外加神闪更容易，所以局内一律不要
            add(-40, "神闪")
        for k, v, reason in (("curse_card", -15, "咒术卡"), ("event_card", -8, "获得卡"), ("lumen_card", -8, "获得卡"),
                             ("desire_card", -8, "获得卡"), ("card_choice", -5, "选卡"), ("transform_card", -10, "转换卡")):
            if effects.get(k):
                add(v, reason)
        # 信用点按用途估值：有待冥想的卡（重闪闪错的目标卡）或还要删卡（商店付费删）时才值钱
        useful = state.get("pending_meditation", 0) > 0 or state.get("need_remove", 0) > 0
        if credit >= 200:
            add(100 if useful else 45, "信用点≥200" + ("" if useful else "（暂无用处）"))
        elif credit > 0:
            add((20 + credit * 15 / 200) if useful else (15 + credit * 10 / 200), "信用点<200")
        elif credit:
            add(max(-15, credit / 4), "信用点")
        if effects.get("battle"):
            # 认知闪光满级后战斗中目标卡会自然闪光，战斗也是闪光来源（用户 2026-10-24 同意）
            add(55, "战斗")
    elif mode == MODE_EXPLORE:
        # 用户 2026-10-24：推进探索度时，没触发过的选项 / 没拿过的装备高于一切
        if state.get("unseen"):
            add(1000, "没选过的选项")
        seen = state.get("seen") or set()
        equip = effects.get("equipment") or []
        new_equip = [n for n in equip if is_specific_equipment(n) and equipment_key(n) not in seen]
        if new_equip:
            add(1000, f"没拿过的装备{new_equip}")
        elif any(n != "?" and not is_specific_equipment(n) for n in equip):
            add(50, "随机装备（可能是没拿过的）")
        if credit:
            add(max(-10, min(10, credit / 10)), "信用点")
        if effects.get("equipment"):
            add(4, "装备")
        if effects.get("curse_card"):
            add(-8, "咒术卡")
        if effects.get("battle"):
            add(2, "战斗（新怪物）")
        # 同为没选过的选项时按「让这局打得更顺」排：闪光/删卡/复制让卡组变强，转换和事件卡变弱（分值远小于 +1000/+50）
        for k, v, reason in (("spark", 6, "闪光"), ("god_spark", 6, "神闪"), ("copy_card", 4, "复制"),
                             ("neutral_card", 3, "中立卡"), ("transform_card", -4, "转换卡"),
                             ("event_card", -3, "获得卡"), ("desire_card", -3, "获得卡")):
            if effects.get(k):
                add(v, reason)
        if rm:
            add(5, f"移除{rm}张")
    if hp and mode == MODE_TARGET and hp > 0:
        # 回血按缺血程度动态排名，一般不超过 ≥200 信用点（100）；血量 <25% 时死了就只能带出最近航路点的存档，
        # 回血排到仅次于目标装备和复制
        cur = state.get("hp_pct", 100)
        add(250 if cur < 25 else min(95, max(2, (100 - cur) * 1.4)), "回血")
    elif hp:
        low = state.get("hp_pct", 100) < 50
        add((8 if low else 2) * (1 if hp > 0 else -1) * (2 if hp < 0 and low else 1), "生命")
    if stress:
        add(-3 * stress if stress > 0 else 3, "压力")
    if effects.get("max_hp_pct"):
        add(3 if effects["max_hp_pct"] > 0 else -6, "最大生命")
    if effects.get("hp_to_one"):
        add(-60, "生命值变为1")
    if effects.get("enemy_hp_to_one"):
        add(5, "异形生命值变为1")
    if effects.get("equipment_lost"):
        add(-6, "失去装备")
    if effects.get("requires_credit", 0) > state.get("credit", 10 ** 9):
        add(-5000, "信用点不够")
    return s, why


def _effects_of(option):
    e = dict(option.get("effects", {}))
    req = option.get("requires") or ""
    if m := re.search(r"(\d+)以上的信用点", req):
        e["requires_credit"] = int(m.group(1))
    if e.get("copy_card") and e.get("copy_mode"):
        e["copy_random"] = e["copy_mode"] != "选择任意卡"
    target = e.get("spark_target") or ""
    if e.get("spark") and target:
        e["spark_card"] = target == "选择卡牌"
        e["spark_random_card"] = target == "随机卡牌"
        e["spark_random"] = target == "随机主战员"
        e["spark_choose"] = target == "选择主战员"
    return e


FOLLOWUP_DEPTH = 4


def followup_best(option, mode, state, depth=FOLLOWUP_DEPTH):
    """选了这个选项后出现的下一层选项（库里的 next 树）里能拿到的最好分数和理由；没有后续返回 (0, [])。

    用户 2026-10-24：后续事件要把所有可能性一起排，比如后续能给目标装备，那这个选项就是第一优先级。
    """
    children = option.get("next") or []
    if not children or depth <= 0:
        return 0.0, []
    seen = state.get("seen") or set()
    best = None
    for c in children:
        # 探索度：后续事件里没选过的选项也加探索度（用户 2026-10-24：第一次选的选项才算）
        st = dict(state, unseen=mode == MODE_EXPLORE and c.get("id") not in seen)
        s, why = score_effects(_effects_of(c), mode, st)
        fs, fwhy = followup_best(c, mode, state, depth - 1)
        if best is None or s + fs > best[0]:
            best = (s + fs, [f"后续「{c.get('text', '')}」"] + why + fwhy)
    return best


def pick_event_option(descs, mode, state=None, db=None):
    """给画面上的几个事件选项打分。返回 (最佳下标, [(分数, 理由, 来源)])。"""
    state = dict(state or {})
    event, matched = match_event_options(descs, db=db)
    seen = state.get("seen") or set()
    results = []
    for d, o in zip(descs, matched):
        if o is not None:
            # 库里只有选项名没有效果（如开局的凯尔肯的传令兵）时，用画面上的效果说明补
            shown = parse_effects(d)
            effects = {**shown, **_effects_of(o)}
            # 库里写随机装备池（「随机装备（稀有度：稀有）」），画面上已经显示了这次抽到的具体装备，以画面为准
            if any(is_specific_equipment(n) for n in shown.get("equipment") or []):
                effects["equipment"] = shown["equipment"]
            src = f"库:{event['name']}/{o.get('text')}"
            # 库的模糊匹配同一选项可能对到不同事件（2026-10-24 实录「拒绝触碰」先对到暗约、后对到银色遗骸瀑布），
            # 所以选过的选项同时按文字记，两个都没有才算没选过
            st = dict(state, unseen=o.get("id") not in seen and text_key(d) not in seen)
        else:
            # 库里没有的事件：用选项文字当 key 记「选过」，没选过的同样优先
            effects = parse_effects(d)
            src = "文字解析"
            st = dict(state, unseen=text_key(d) not in seen and _legacy_text_key(d) not in seen)
        score, why = score_effects(effects, mode, st)
        if o is None and mode == MODE_EXPLORE and st["unseen"] and "发生事件" in d:
            # 库里没有的后续事件：只能经这个选项进去，这个没选过时后续的选项大概率也都没见过（库里有后续树的同类选项
            # 实测 +2054），按「后续还有一个没选过的选项」算，略低于确定的新装备
            score, why = score + 900, why + ["后续事件（库里没有，大概率没见过）+900"]
        if o is not None:
            fs, fwhy = followup_best(o, mode, state)
            score, why = score + fs, why + fwhy
        results.append((score, why, src, o.get("id") if o else text_key(d)))
    if not results:
        return None, results
    best = max(range(len(results)), key=lambda i: results[i][0])
    return best, results


# ---------------- 「已见」记录（探索度） ----------------

_EQUIPMENT_POOL = re.compile(r"装备$|随机|~|～|稀有度")


def is_specific_equipment(name):
    """事件库里随机装备池写成「随机商店稀有装备」「商店或尼希勒姆稀有~传说装备」，不是具体装备。"""
    return bool(name) and name != "?" and not _EQUIPMENT_POOL.search(name)


def equipment_key(name):
    """探索度「拿过的装备」记录 key。"""
    return "eq:" + norm(name)


def option_seen_keys(desc, option_id):
    """选中一个选项后要记进「已选」的 key：选项本身 + 里面的装备。"""
    keys = [option_id or text_key(desc), text_key(desc)]
    keys += [equipment_key(n) for n in parse_effects(desc).get("equipment") or [] if is_specific_equipment(n)]
    return keys


_KEY_NOISE = r"[\d\s%+\-，。,.、：:；;！!？?\[\]【】()（）~～/·]"


def text_key(desc):
    """事件库匹配不上的选项的「已选」key：去掉方括号里的内容（「获得装备[标准型防毒面具]」每局随机，2026-10-24 实录
    同一个选项换了装备就被当成没选过）、数字、空白和标点（数值会随难度变），取前 24 个字。"""
    return "txt:" + re.sub(_KEY_NOISE, "", re.sub(r"[\[【][^\]】]*[\]】]", "", desc or ""))[:24]


def _legacy_text_key(desc):
    """10-24 之前记下的 key（方括号内容没去掉），读旧记录时也认。"""
    return "txt:" + re.sub(_KEY_NOISE, "", desc or "")[:24]


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
    own = {c["name"] for c in db.cards_of(member, sorts=None)}
    memory = [dict(c, memory=memory_name(c["name"])) for c in preset.get("cards", []) if memory_name(c["name"])]
    neutral = [c["name"] for c in preset.get("cards", [])
               if c["name"] not in own and not memory_name(c["name"]) and _is_neutral(db, c["name"])]
    return {"remove": remove, "copy": copy, "flash": flash, "neutral": neutral, "memory": memory}


def memory_name(card_name):
    """赛季卡牌「记忆：丧失」→「丧失」（OCR 常把类型带进来：「记忆：丧失4强化」）；不是记忆卡返回空串。"""
    m = re.match(r"\s*记忆\s*[:：]?\s*([^\d\s:：]+?)(强化|攻击|技能)?(\d.*)?$", card_name or "")
    return m.group(1) if m else ""


def _is_neutral(db, name):
    card = db.find_card(name)
    return bool(card) and db.card_owner(card) is None


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


# ---------------- 零式系统升级 ----------------

GOD_SPARK_UPGRADE = "高维启示"   # 神之闪光触发率，空存和目标卡组都 0 级（用户 2026-10-24：局内最好不神闪）
SPARK_UPGRADE = "认知闪光"       # 闪光触发率，空存 0 级、目标卡组满级


def zero_upgrade_wants(mode):
    """零式系统升级要求：(必须 0 级的项, 必须满级的项)。探索度和原有逻辑不在零式系统刷，不管。"""
    if mode == MODE_EMPTY:
        return [GOD_SPARK_UPGRADE, SPARK_UPGRADE], []
    if mode == MODE_TARGET:
        return [GOD_SPARK_UPGRADE], [SPARK_UPGRADE]
    return [], []


# ---------------- 玩法 → 现有配置项 ----------------

def _memory_override(plan):
    """预设里有赛季记忆卡时，「选择铭刻的记忆」页按它选（没有就不覆盖用户配置）。"""
    mem = [m["memory"] for m in (plan or {}).get("memory", [])]
    return {"指定记忆卡牌": mem[0]} if mem else {}


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
            "路线优先级": ["事件", "休息", "精英", "小怪"],
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
            # 闪光三选一没出现预设的变体 → 标成待冥想，篝火时重闪（冥想优先于休息）
            "需要冥想的卡牌": list(dict.fromkeys(flash_names)),
            "任务优先级": ["复制", "移除", "信用点增加"],
            "拉黑任务": ["咒术卡牌", "压力"],
            "路线优先级": ["精英", "事件", "休息", "小怪"],
            "进入商店": True,
            **_memory_override(plan),
        }
    if mode == MODE_EXPLORE:
        # 删卡/闪光/复制也按目标主战员的预设来（用户 2026-10-24：以前沿用旧配置的移除列表，删了别人的卡）
        plan = plan or {}
        flash_names = [c["name"] for c in plan.get("flash", [])]
        return {
            "优先移除基础牌": False,
            "移除卡牌列表": list(dict.fromkeys(plan.get("remove", []))),
            "闪光卡牌列表": list(dict.fromkeys(flash_names)),
            "复制卡牌列表": list(dict.fromkeys(plan.get("copy", []))),
            "闪光优先级": [],
            "卡牌奖励优先级": list(dict.fromkeys(flash_names)),
            "刷空档": False,
            "刷初始卡牌": "",
            "任务优先级": [],
            "拉黑任务": ["咒术卡牌"],
            "路线优先级": ["事件", "精英", "小怪", "休息"],
            "存储数据保存上限大于多少": 0,   # 探索度不要存档，别花货币「再次观测」
            **_memory_override(plan),
        }
    return {}
