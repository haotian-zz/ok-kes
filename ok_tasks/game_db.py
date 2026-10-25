# 本地游戏数据库：assets/game_data/*.json（由 2game-helper/research/czn/build_*.py 生成），把 OCR 文本映射成卡牌/闪光/事件/装备的语义
import json
import os
import re
from functools import lru_cache

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "game_data")

# OCR / 数据源常见错字 → 统一写法（只在比较时用）
_CHAR_FIXES = str.maketrans({"髓": "穗", "，": "", "。": "", "、": "", "：": "", ":": "", "；": "", ";": ""})
_PUNCT = re.compile(r"[\s\[\]【】〔〕()（）「」『』<>《》/／|｜·•\-—_+＋!！?？\"'`~，,。.、：:；;]+")
_PERCENT = re.compile(r"\d+(\.\d+)?%")
_TALENT_TAG = re.compile(r"[\[【〔][^\]】〕]*[\]】〕]")


def norm(text):
    """比较用的规范化：去空白和标点、统一错字；百分比数值随等级变化，替换成 #%。"""
    if isinstance(text, (list, tuple)):
        text = "".join(text)
    text = (text or "").translate(_CHAR_FIXES)
    text = _PERCENT.sub("#%", text)
    return _PUNCT.sub("", text)


def strip_talents(text):
    """去掉卡面上方 [连接/安息/已复制] 这类天赋标签，只留效果描述。"""
    if isinstance(text, (list, tuple)):
        text = "\n".join(text)
    return _TALENT_TAG.sub("", text or "").replace("已复制", "")


def _bigrams(s):
    return [s[i:i + 2] for i in range(len(s) - 1)] if len(s) > 1 else [s]


def similarity(a, b):
    """字符二元组 Dice 系数（0~1），不受 OCR 多行拼接顺序影响。参数可以是原文，会先 norm。"""
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ga, gb = _bigrams(a), _bigrams(b)
    pool = {}
    for g in gb:
        pool[g] = pool.get(g, 0) + 1
    hit = 0
    for g in ga:
        if pool.get(g, 0) > 0:
            pool[g] -= 1
            hit += 1
    return 2.0 * hit / (len(ga) + len(gb))


def containment(part, text):
    """part 的二元组有多少比例出现在 text 里（0~1）。"""
    a, b = norm(part), norm(text)
    if not a or not b:
        return 0.0
    ga = _bigrams(a)
    pool = {}
    for g in _bigrams(b):
        pool[g] = pool.get(g, 0) + 1
    hit = 0
    for g in ga:
        if pool.get(g, 0) > 0:
            pool[g] -= 1
            hit += 1
    return hit / len(ga)


def _load(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        return json.load(f)


class GameDB:
    def __init__(self):
        chars = _load("characters.json")
        self.combatants = chars["combatants"]
        self.supporters = chars["supporters"]
        self.cards = _load("cards.json")["cards"]
        self.neutral_cards = _load("neutral_cards.json")["cards"]
        sparks = _load("god_sparks.json")
        self.god_sparks = {s["id"]: s for s in sparks["god"]}
        self.equipment = _load("equipment.json")["equipment"]
        self.events = _load("events.json")["regions"]
        self._card_by_id = {c["id"]: c for c in self.cards + self.neutral_cards}
        self._char_by_id = {c["id"]: c for c in self.combatants + self.supporters}

    # ---------------- 角色 ----------------

    def combatant(self, name):
        """按国服名 / 国际服名 / 昵称找主战员，允许 1 个 OCR 错字。"""
        return self._best(self.combatants, name, keys=("name", "name_intl", "nickname"), min_score=0.66)

    def cards_of(self, character, sorts=("基础卡牌", "独特卡牌")):
        """角色自己的卡（默认只要起始卡和独特卡，不含 EGO 技能和衍生卡）。character 可以是名字或 dict。"""
        c = self.combatant(character) if isinstance(character, str) else character
        if not c:
            return []
        return [card for card in self.cards if card.get("owner") == c["id"] and (not sorts or card.get("sort") in sorts)]

    def card_owner(self, card):
        """卡（dict 或 id）属于哪个角色，返回角色 dict；中立卡返回 None。"""
        card = self._card_by_id.get(card) if isinstance(card, str) else card
        return self._char_by_id.get(card.get("owner")) if card else None

    # ---------------- 卡牌 / 闪光 ----------------

    def find_card(self, name, owner=None, include_neutral=True):
        """按卡名找卡；owner（角色名或 dict）给了就先在该角色的卡里找。"""
        pools = []
        if owner:
            pools.append(self.cards_of(owner, sorts=None))
        pools.append(self.cards)
        if include_neutral:
            pools.append(self.neutral_cards)
        for pool in pools:
            hit = self._best(pool, name, keys=("name", "name_intl"), min_score=0.66)
            if hit:
                return hit
        return None

    def card_variants(self, card):
        """一张卡所有可能的卡面：基础（n=0）+ 5 个闪光变体（n=1~5）。"""
        out = [{"n": 0, "cost": card.get("cost"), "desc": card.get("desc", ""), "talents": card.get("talents", [])}]
        for s in card.get("sparks", []):
            out.append({"n": s["n"], "cost": s.get("cost"), "desc": s.get("desc", ""), "talents": s.get("talents", [])})
        return out

    def match_spark(self, card, desc, cost=None):
        """把 OCR 出的卡面描述对到「闪光变体 n + 神闪词条」。

        返回 {"n": 变体号(0=没闪光), "god_spark": 神闪 id 或 None, "score": 0~1}。
        卡面 = 变体描述 + 可能多出的一条神闪；先挑最像的变体，再用剩下的文字去配神闪。
        """
        text = norm(strip_talents(desc))
        best = None
        for v in self.card_variants(card):
            vd = norm(v["desc"])
            score = similarity(vd, text)
            residual = _strip_common(text, vd)
            god, god_score = self._match_god_spark(card, residual)
            if god and god_score >= 0.8:
                # 同样的文字既可能是闪光变体也可能是神闪时，优先认成闪光（神闪更少见）
                score = similarity(vd + norm(self.god_sparks[god]["desc"]), text) - 0.02
            else:
                god = None
            expect_cost = v["cost"]
            if god == "add_r_spark_circen_03" and isinstance(expect_cost, int):
                expect_cost -= 1
            if cost is not None and isinstance(expect_cost, int) and str(cost) != str(expect_cost):
                score -= 0.05
            if best is None or score > best["score"]:
                best = {"n": v["n"], "god_spark": god, "score": round(score, 3)}
        return best

    def _match_god_spark(self, card, residual):
        if len(residual) < 3:
            return None, 0.0
        ids = card.get("god_sparks") or list(self.god_sparks)
        # 剩余文字里还可能混着丢了括号的天赋标签等噪声，所以按「神闪文字有多少被包含」算，不用 Dice
        scored = [(containment(self.god_sparks[i]["desc"], residual), i) for i in ids if i in self.god_sparks]
        if not scored:
            return None, 0.0
        s, i = max(scored)
        return i, s

    @staticmethod
    def same_effect(desc_a, desc_b, threshold=0.9):
        """两张卡面描述是否算同一效果（用户规则：神闪/闪光只要描述一样就行，不管分类）。"""
        return similarity(strip_talents(desc_a), strip_talents(desc_b)) >= threshold

    # ---------------- 事件 ----------------

    def iter_events(self, region=None):
        for r, events in self.events.items():
            if region and r != region:
                continue
            for e in events:
                yield e

    def match_event(self, title=None, options=(), region=None):
        """按事件标题 + 画面上的选项文字找事件变体。同名事件有 a/b/c 多个变体，靠选项文字区分。"""
        options = [o for o in options if o]
        best, best_score = None, 0.0
        for e in self.iter_events(region):
            names = [e["name"], e.get("name_intl")] + list(e.get("name_aliases", []))
            name_score = max((similarity(n, title) for n in names if n), default=0.0) if title else 0.0
            if title and name_score < 0.6:
                continue
            opt_score = 0.0
            if options:
                texts = [o["text"] for o in e.get("options", [])] + [o.get("text_intl") for o in e.get("options", []) if o.get("text_intl")]
                opt_score = sum(max((similarity(t, o) for t in texts), default=0.0) for o in options) / len(options)
            score = name_score + opt_score if title else opt_score
            if score > best_score:
                best, best_score = e, score
        if best is None or (not title and best_score < 0.6):
            return None
        return best

    def find_option(self, event, text):
        """在事件（含下一层分支）里找和 OCR 文字最像的选项。"""
        best, best_score = None, 0.0
        stack = list(event.get("options", []))
        while stack:
            o = stack.pop()
            for t in (o.get("text"), o.get("text_intl")):
                s = similarity(t, text) if t else 0.0
                if s > best_score:
                    best, best_score = o, s
            stack.extend(o.get("next", []))
        return best if best_score >= 0.6 else None

    # ---------------- 装备 ----------------

    def find_equipment(self, name):
        """按装备名找装备（优先非出击专用版本），返回 dict（含 slot 1/2/3、rarity）。"""
        normal = [e for e in self.equipment if e.get("mode") != "出击"]
        return self._best(normal, name, keys=("name", "name_intl"), min_score=0.75) or \
            self._best(self.equipment, name, keys=("name", "name_intl"), min_score=0.75)

    EQUIPMENT_NAME_KEYS = ("name", "name_intl", "name_gamekee")

    def equipment_aliases(self, name):
        """装备的所有叫法（国服名、国际服名、gamekee 名）。用户常用国际服名（「混沌指控」），国服画面上是「混沌之识」。"""
        target = norm(name)
        names = [name]
        for e in self.equipment:
            vals = [e.get(k) for k in self.EQUIPMENT_NAME_KEYS if e.get(k)]
            if any(norm(v) == target for v in vals):
                names += [v for v in vals if v not in names]
        return names

    # ---------------- 工具 ----------------

    @staticmethod
    def _best(items, name, keys, min_score):
        if not name:
            return None
        target = norm(name)
        best, best_score = None, 0.0
        for it in items:
            for k in keys:
                v = it.get(k)
                if not v:
                    continue
                if norm(v) == target:
                    return it
                s = similarity(v, target)
                if s > best_score:
                    best, best_score = it, s
        return best if best_score >= min_score else None


def _strip_common(text, base):
    """从 text 里去掉和 base 共有的片段，剩下的大概就是追加的神闪词条。"""
    import difflib
    sm = difflib.SequenceMatcher(None, base, text, autojunk=False)
    keep = []
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if tag in ("insert", "replace"):
            keep.append(text[j1:j2])
    return "".join(keep)


@lru_cache(maxsize=1)
def get_db():
    return GameDB()
