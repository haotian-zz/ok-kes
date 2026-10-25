# 卡厄思存档存储满了（300/300）自动清理：「存储空间不足」弹窗点「前往」到分解页，按分数从低到高逐个看详情，
# 分解分数最低、不是目标主战员、不是空白存档（模糊的记忆 0PT）的存档，腾出 FREE_SLOTS 个位置再回去继续刷。
# 2026-10-25 用户定：脚本自动清理，空白存档留着；读不准（TB/PT/角色认不出）的一律保留。
import re
import time

import chaos_trace
import game_db
from utils import _get_config_value, _move_and_click, find_box_at_point, find_text

FREE_SLOTS = 30          # 每次腾出的位置
MAX_VIEWED = 150         # 最多看这么多个存档（都不能删就放弃）
SAME_LIMIT = 12          # 翻页后连续这么多次一模一样才算到最后一个
SORT_TOGGLE = (0.232, 0.931)
FIRST_CARD = (0.155, 0.200)
NEXT_SAVE = (0.965, 0.495)
TRASH = (0.807, 0.178)
CLOSE_DETAIL = (0.881, 0.153)
BACK = (0.042, 0.046)
CONFIRM = (0.667, 0.668)
CANCEL = (0.347, 0.667)
CARD_NAME_ROWS = ((0.42, 0.25, 0.84, 0.28), (0.42, 0.52, 0.84, 0.55))


def enabled(task):
    return _get_config_value(task, '存档满了自动清理', True) is True


def start(task):
    task.save_cleanup = {"need": None, "deleted": 0, "viewed": 0, "kept": set(), "pending": None,
                         "last_sig": None, "last_action": None, "trash_tries": 0, "done": False}


def _click(task, pos, after=1.0):
    _move_and_click(task, *pos)
    task.sleep(after)


def _texts(task):
    return task.all_texts or []


def _num(text, unit):
    m = re.search(r'([0-9O]+)\s*' + unit, text.replace(',', ''))
    return int(m.group(1).replace('O', '0')) if m else None


def _count(task):
    for b in _texts(task):
        m = re.fullmatch(r'\s*(\d+)\s*/\s*(\d+)\s*', b.name)
        if m and b.y / task.height > 0.8 and b.x / task.width < 0.4:
            return int(m.group(1)), int(m.group(2))
    return None


def _is_grid(task):
    title = find_box_at_point(task, 0.155, 0.046)
    return bool(title and "分解存储数据" in title.name) and any("总数量" in b.name for b in _texts(task))


def _is_detail(task):
    names = [b.name for b in _texts(task)]
    return any("模糊的记忆" in n for n in names) and any("卡牌数量" in n for n in names)


def _is_confirm(task):
    return any("确定要分解" in b.name or "分解数据后无法恢复" in b.name for b in _texts(task))


def _in(b, task, region):
    cx, cy = (b.x + b.width / 2) / task.width, (b.y + b.height / 2) / task.height
    return region[0] <= cx <= region[2] and region[1] <= cy <= region[3]


def read_detail(task):
    """详情页：TB、模糊的记忆 PT、第一/二排卡名 → (tb, pt, names)。"""
    tb_box = find_box_at_point(task, 0.334, 0.402)
    pt_box = find_box_at_point(task, 0.370, 0.656)
    tb = _num(tb_box.name, "TB") if tb_box else None
    pt = _num(pt_box.name, "PT") if pt_box else None
    names = [re.sub(r'^\d+', '', b.name).strip() for b in _texts(task)
             if any(_in(b, task, r) for r in CARD_NAME_ROWS)]
    return tb, pt, [n for n in names if len(n) >= 2]


def owners_of(names, db=None):
    db = db or game_db.get_db()
    out = set()
    for n in names:
        card = db.find_card(n, include_neutral=False)
        owner = db.card_owner(card) if card else None
        if owner:
            out.add(owner["name"])
    return out


def keep_reason(tb, pt, owners, target):
    """返回保留原因；None 表示可以分解。"""
    if tb is None or pt is None:
        return "TB/PT 读不准"
    if pt == 0:
        return "空白存档（0PT）"
    if not owners:
        return "认不出角色"
    if target and target in owners:
        return f"目标主战员{target}"
    return None


def handle_save_cleanup(task):
    """存档清理流程里的三个页面：分解页（网格）、存档详情、分解确认弹窗。没在清理时只处理误入的确认弹窗。"""
    st = getattr(task, "save_cleanup", None)
    if _is_confirm(task):
        if st and st["pending"] and time.time() - st["pending"] < 15:
            st["pending"] = None
            st["deleted"] += 1
            st["last_action"], st["trash_tries"] = "deleted", 0     # 下一个一模一样的存档不能算「垃圾桶没反应」
            task.log_info(f"存档清理：确认分解（第 {st['deleted']}/{st['need']} 个）")
            _click(task, CONFIRM, 2)
        else:
            task.log_info("存档分解确认框不是清理流程点出来的，取消")
            _click(task, CANCEL)
        return True
    if st is None:
        return False
    if _is_grid(task):
        return _on_grid(task, st)
    if _is_detail(task):
        return _on_detail(task, st)
    return False


def _finish(task, st, why):
    task.log_info(f"存档清理结束（{why}）：分解 {st['deleted']} 个，看过 {st['viewed']} 个", notify=True)
    task.save_cleanup_last = st["deleted"]
    task.save_cleanup = None
    _click(task, BACK, 2)
    return True


def _on_grid(task, st):
    count = _count(task)
    if count is None:
        return False
    n, cap = count
    if st["need"] is None:
        st["need"] = max(0, n - (cap - FREE_SLOTS))
        task.log_info(f"存档清理：现有 {n}/{cap}，要分解 {st['need']} 个（空白存档、目标主战员的存档保留）")
    if st["done"] or st["deleted"] >= st["need"] or st["viewed"] >= MAX_VIEWED:
        return _finish(task, st, f"{n}/{cap}")
    tbs = [(b.y, b.x, _num(b.name, "TB")) for b in _texts(task) if _num(b.name, "TB")]
    tbs.sort()
    if len(tbs) >= 2 and tbs[0][2] > tbs[-1][2]:
        task.log_info("存档清理：改成按分数从低到高")
        _click(task, SORT_TOGGLE, 2)
        return True
    detail = find_text(task, r'^详细信息$')
    if detail:
        task.click_box(detail)
        task.sleep(2)
        return True
    _click(task, FIRST_CARD)             # 选中第一个（分数最低）才会出「详细信息」
    return True


def _on_detail(task, st):
    if st["done"] or st["deleted"] >= st["need"]:
        _click(task, CLOSE_DETAIL, 2)
        return True
    tb, pt, names = read_detail(task)
    date = find_box_at_point(task, 0.226, 0.200)
    sig = (tb, pt, tuple(names), date.name if date else None)
    # 翻页后一模一样：可能是到最后一个了，也可能是连着几个一模一样的空白存档（2026-10-25 实录，第三个就误判到底），
    # 连续 SAME_LIMIT 次一样才算到底
    st["same"] = st.get("same", 0) + 1 if sig == st["last_sig"] and st["last_action"] == "next" else 0
    if st["same"] >= SAME_LIMIT or st["viewed"] >= MAX_VIEWED:
        st["done"] = True
        _click(task, CLOSE_DETAIL, 2)
        return True
    if sig in st["kept"]:
        st["last_sig"], st["last_action"] = sig, "next"
        _click(task, NEXT_SAVE, 1.5)
        return True
    target = _get_config_value(task, '目标主战员', '')
    owners = owners_of(names)
    reason = keep_reason(tb, pt, owners, target)
    if reason is None and sig == st["last_sig"] and st["last_action"] == "trash":
        st["trash_tries"] += 1
        if st["trash_tries"] >= 2:
            reason = "点垃圾桶没反应（可能加了锁）"
    if reason:
        st["kept"].add(sig)
        st["viewed"] += 1
        task.log_info(f"存档清理：保留 {tb}TB {pt}PT {'/'.join(owners) or '?'}（{reason}）")
        st["last_sig"], st["last_action"], st["trash_tries"] = sig, "next", 0
        _click(task, NEXT_SAVE, 1.5)
        return True
    st["viewed"] += 1
    task.log_info(f"存档清理：分解 {tb}TB {pt}PT {'/'.join(owners)}（卡 {' '.join(names)}）")
    chaos_trace.step(task, "page", "存档清理-分解", task.frame, tb=tb, pt=pt, owners=sorted(owners), cards=names)
    st["pending"] = time.time()
    st["last_sig"], st["last_action"] = sig, "trash"
    _click(task, TRASH, 1.5)
    return True
