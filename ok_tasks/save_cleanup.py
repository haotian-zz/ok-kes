# 卡厄思存档存储满了（300/300）自动清理：「存储空间不足」弹窗点「前往」到分解页，按分数从低到高逐个看详情，
# 定下要分解的（分数最低、不是目标主战员、不是空白存档 = 模糊的记忆 0PT），回到列表按 TB 序列对齐后勾选，
# 一次「批量分解」，腾出 FREE_SLOTS 个位置再回去继续刷。
# 2026-10-25 用户定：脚本自动清理、允许批量分解，空白存档留着；读不准（TB/PT/角色认不出）、列表对不上的一律不删。
import os
import re
import time

import chaos_trace
import game_db
from utils import _get_config_value, _move_and_click, _simplify_texts, find_box_at_point, find_text

DEV_START_FILE = os.path.join("dev_out", "save_cleanup_now")
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


BATCH_BUTTON = (0.931, 0.929)
ROW_GAP = 0.189              # 列表一行的高度（TB 文字 y：0.237 → 0.426 → 0.615）
CELL_CLICK = (-0.175, -0.037)   # 从格子的 TB 文字到头像（点头像=勾选）


def start(task):
    # phase：scan（详情页逐个看）→ select（列表里勾选）→ confirm（批量分解确认）→ done
    task.save_cleanup = {"need": None, "deleted": 0, "viewed": 0, "phase": "scan", "decisions": [],
                         "last_sig": None, "same": 0, "offset": 0, "selected": set(), "top": False,
                         "last_view": None, "pending": None}


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
    """存档清理流程里的三个页面：分解页（列表）、存档详情、分解确认弹窗。没在清理时只处理误入的确认弹窗。"""
    st = getattr(task, "save_cleanup", None)
    if _is_confirm(task):
        if st and st["phase"] == "confirm" and st["pending"] and time.time() - st["pending"] < 15:
            st["deleted"] = len(st["selected"])
            st["phase"], st["pending"] = "done", None
            task.log_info(f"存档清理：确认批量分解 {st['deleted']} 个")
            _click(task, CONFIRM, 3)
        else:
            task.log_info("存档分解确认框不是清理流程点出来的，取消")
            _click(task, CANCEL)
        return True
    if st is None and _is_grid(task) and os.path.exists(DEV_START_FILE):
        os.remove(DEV_START_FILE)        # 开发调试：手动打开分解页 + 放这个文件，按存储满的流程清理
        task.log_info(f"存在 {DEV_START_FILE}，开始存档清理")
        start(task)
        st = task.save_cleanup
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


def _abort(task, st, why):
    task.log_info(f"存档清理：{why}，这次不分解", notify=True)
    st["selected"] = set()
    st["phase"] = "done"
    return _finish(task, st, why)


def _selected_count(task):
    for b in _texts(task):
        m = re.search(r'选择数量\s*(\d+)', b.name)
        if m:
            return int(m.group(1))
    return None


def visible_cells(task):
    """列表里完整可见的格子 → {格子序号(行*3+列): (TB, 文字中心 x, y)}，行从可见的第一行算。"""
    found = []
    for b in _texts(task):
        v = _num(b.name, "TB")
        if v is None:
            continue
        cx, cy = (b.x + b.width / 2) / task.width, (b.y + b.height / 2) / task.height
        if cx > 0.2 and 0.20 <= cy <= 0.79:
            found.append((cy, cx, v))
    if not found:
        return {}
    top = min(f[0] for f in found)
    cells = {}
    for cy, cx, v in found:
        row = int(round((cy - top) / ROW_GAP))
        col = 0 if cx < 0.45 else 1 if cx < 0.75 else 2
        cells[row * 3 + col] = (v, cx, cy)
    return cells


def align(cells, tbs, start, expect):
    """可见格子对到详情页看过的序列 tbs（按分数从低到高）上：返回第一格的序号。
    候选是 start 起每次一行；要求每个能比的格子 TB 都一样，同样吻合的取离 expect 最近的。对不上返回 None。"""
    best = None
    for off in range(start, start + 3 * 12, 3):
        pairs = [(tbs[off + pos], v[0]) for pos, v in cells.items()
                 if off + pos < len(tbs) and tbs[off + pos] is not None]
        if not pairs or any(a != b for a, b in pairs):
            continue
        if len(pairs) < min(3, len(cells)) and off != 0:
            continue
        key = abs(off - expect)
        if best is None or key < best[0]:
            best = (key, off)
    return None if best is None else best[1]


def _on_grid(task, st):
    count = _count(task)
    if count is None:
        return False
    n, cap = count
    if st["need"] is None:
        st["need"] = max(0, n - (cap - FREE_SLOTS))
        task.log_info(f"存档清理：现有 {n}/{cap}，要分解 {st['need']} 个（空白存档、目标主战员的存档保留）")
        if st["need"] == 0:
            st["phase"] = "done"
    if st["phase"] == "done":
        return _finish(task, st, f"{n}/{cap}")
    if st["phase"] == "confirm":
        if st["pending"] and time.time() - st["pending"] < 8:
            return True                  # 等确认框
        return _abort(task, st, "点了批量分解没出确认框")
    cells = visible_cells(task)
    if st["phase"] == "scan":
        ordered = [cells[k][0] for k in sorted(cells)]
        if len(ordered) >= 2 and ordered[0] > ordered[-1]:
            task.log_info("存档清理：改成按分数从低到高")
            _click(task, SORT_TOGGLE, 2)
            return True
        detail = find_text(task, r'^详细信息$')
        if detail:
            task.click_box(detail)
            task.sleep(2)
            return True
        _click(task, FIRST_CARD)         # 选中第一个（分数最低）才会出「详细信息」
        return True
    return _select(task, st, cells)


def _select(task, st, cells):
    dec = st["decisions"]
    todo = {i for i, d in enumerate(dec) if d["delete"]}
    if not st["top"]:
        # 详情页翻页可能带着列表滚了；先回到最上面，第一屏从序号 0 对齐
        pre = _selected_count(task) or 0
        if pre > 1:
            return _abort(task, st, f"列表里已经勾选了 {pre} 个存档")
        st["pre0"] = pre == 1            # 进详情时点了第一个（序号 0），它还勾着
        for _ in range(4):
            task.swipe_relative(0.5, 0.30, 0.5, 0.78, duration=0.4)
            task.sleep(0.5)
        task.sleep(1)
        st["top"], st["offset"], st["expect"] = True, None, 0
        return True
    tbs = [d["tb"] for d in dec]
    off = align(cells, tbs, 0 if st["offset"] is None else st["offset"], st.get("expect", 0))
    if off is None:
        return _abort(task, st, f"列表对不上详情页看过的顺序（可见 {[cells[k][0] for k in sorted(cells)]}）")
    st["offset"] = off
    before = _selected_count(task) or 0
    clicked = delta = 0
    if st.get("pre0") and off == 0 and 0 in cells:
        st["pre0"] = False
        if 0 in todo:
            st["selected"].add(0)        # 本来就勾着，正好要删
        else:
            v, cx, cy = cells[0]
            _move_and_click(task, cx + CELL_CLICK[0], cy + CELL_CLICK[1])     # 要留的，取消勾选
            task.sleep(0.6)
            clicked, delta = 1, -1
    for pos in sorted(cells):
        i = off + pos
        if i in todo and i not in st["selected"]:
            v, cx, cy = cells[pos]
            _move_and_click(task, cx + CELL_CLICK[0], cy + CELL_CLICK[1])
            task.sleep(0.6)
            st["selected"].add(i)
            clicked += 1
            delta += 1
    if clicked:
        task.sleep(1)
        task.next_frame()
        task.all_texts = _simplify_texts(task.ocr())
        after = _selected_count(task)
        if after != before + delta:
            return _abort(task, st, f"勾选数量对不上（之前 {before}，点了 {clicked}，现在 {after}）")
        task.log_info(f"存档清理：勾选第 {sorted(i for i in st['selected'] if i >= off)} 个，共 {after} 个")
        return True
    last_visible = off + max(cells)
    if any(i > last_visible for i in todo - st["selected"]):
        view = tuple(cells[k][0] for k in sorted(cells))
        if view == st["last_view"]:
            task.log_info("存档清理：列表滚不动了，按已勾选的分解")
        else:
            st["last_view"] = view
            st["expect"] = off + 6
            task.swipe_relative(0.5, 0.70, 0.5, 0.70 - 2 * ROW_GAP, duration=1.2)
            task.sleep(1.5)
            return True
    if not st["selected"]:
        return _abort(task, st, "没有可分解的存档")
    n_sel = _selected_count(task)
    if n_sel != len(st["selected"]):
        return _abort(task, st, f"勾选数量 {n_sel} 和计划 {len(st['selected'])} 对不上")
    chaos_trace.step(task, "page", "存档清理-批量分解", task.frame, selected=sorted(st["selected"]),
                     saves=[dec[i] for i in sorted(st["selected"])])
    task.log_info(f"存档清理：批量分解 {len(st['selected'])} 个")
    st["phase"], st["pending"] = "confirm", time.time()
    _click(task, BATCH_BUTTON, 2)
    return True


def _on_detail(task, st):
    if st["phase"] != "scan":
        _click(task, CLOSE_DETAIL, 2)
        return True
    tb, pt, names = read_detail(task)
    date = find_box_at_point(task, 0.226, 0.200)
    sig = (tb, pt, tuple(names), date.name if date else None)
    # 翻页后一模一样：可能是到最后一个了，也可能是连着几个一模一样的空白存档（2026-10-25 实录，第三个就误判到底），
    # 连续 SAME_LIMIT 次一样才算到底（多记的几条去掉）
    st["same"] = st["same"] + 1 if sig == st["last_sig"] else 0
    st["last_sig"] = sig
    dec = st["decisions"]
    n_del = sum(d["delete"] for d in dec)
    if st["same"] >= SAME_LIMIT or len(dec) >= MAX_VIEWED or n_del >= st["need"]:
        if st["same"] >= SAME_LIMIT:
            del dec[len(dec) - st["same"]:]
        task.log_info(f"存档清理：看了 {len(dec)} 个，定下分解 {sum(d['delete'] for d in dec)} 个，回列表勾选")
        st["phase"] = "select"
        _click(task, CLOSE_DETAIL, 2)
        return True
    owners = owners_of(names)
    reason = keep_reason(tb, pt, owners, _get_config_value(task, '目标主战员', ''))
    dec.append({"tb": tb, "pt": pt, "owners": sorted(owners), "delete": reason is None})
    st["viewed"] = len(dec)
    if st["same"] == 0:
        task.log_info(f"存档清理：第 {len(dec) - 1} 个 {tb}TB {pt}PT {'/'.join(owners) or '?'}"
                      f"（{reason or '分解'}）")
    _click(task, NEXT_SAVE, 1.5)
    return True
