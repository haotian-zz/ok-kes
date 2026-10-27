# 卡厄思全屏地图（路线页按 M）整层扫描：小步拖动地图拍几帧，相位相关算平移拼起来，按网格认节点、按白线认连通，
# 输出和小地图识别（utils.recognize_map_connections）同格式的 map_info，交给 find_best_map_route_by_priority 求整条路径。
# 坐标按 1920×1080 国服实机量取（2026-10-24），其他分辨率按高度等比缩放。图像函数都是纯函数，方便用截图单测。
import inspect
import os
import time

import cv2
import numpy as np

REF_H = 1080
ROW_Y = [224, 386, 548, 710, 872]       # 5 行节点中心
# 拖地图的高度取第 3、4 行节点正中间：原来 0.55 正好在第 3 行节点的下尖角，按在节点上拖会被当成点节点，
# 全屏地图关掉去预览那个节点（2026-10-27 06:33 起层开头扫描屡次「拖动后对不上上一帧」，流程追踪截图确认）
DRAG_Y = (ROW_Y[2] + ROW_Y[3]) / 2 / REF_H
ZOOM_REGION = (0.0, 0.86, 0.2, 0.99)    # 全屏地图左下角「缩小（M）」按钮所在区域
ZOOM_IN_REGION = (0.33, 0.58, 0.47, 0.78)   # 路线页小地图右上角「放大（M）」按钮所在区域
EMPTY_SPOT = (0.62, 0.9)                # 全屏地图最下一行节点下面的空白处；路线页同一位置也是空背景
LINE_DY = 14                           # 连线端点比节点中心低这么多
COL_PITCH = 246                        # 列间距
TIP_DX = 79                            # 连线端点离节点中心的水平距离
MAP_TOP, MAP_BOTTOM = 150, 950          # 节点所在的竖直范围（避开顶栏和左下角缩放按钮）

TYPE_BY_HUE = [((80, 115), "事件"), ((115, 145), "精英"), ((150, 180), "小怪"), ((0, 30), "橙")]

_ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "chaos_map")
_REFS = {}


def _ref(name):
    if name not in _REFS:
        _REFS[name] = cv2.imread(os.path.join(_ASSET_DIR, f"{name}.png"), cv2.IMREAD_GRAYSCALE)
    return _REFS[name]


def _scale(frame):
    return frame.shape[0] / REF_H


def _white_mask(hsv):
    return (((hsv[..., 1] < 110) & (hsv[..., 2] > 150)) * 255).astype(np.uint8)


def _hue_type(h):
    for (lo, hi), t in TYPE_BY_HUE:
        if lo <= h < hi:
            return t
    return None


def _cell(hsv, x, y, s):
    """节点菱形中间一条（避开图标）的 HSV 中位数，以及图标区白色像素数。"""
    h, w = hsv.shape[:2]
    x0, x1 = int(x - 50 * s), int(x + 50 * s)
    y0, y1 = int(y - 12 * s), int(y + 12 * s)
    if x0 < 0 or x1 > w or y0 < 0 or y1 > h:
        return None
    core = hsv[y0:y1, x0:x1].reshape(-1, 3)
    icon = hsv[int(y - 28 * s):int(y + 28 * s), int(x - 34 * s):int(x + 34 * s)]
    return np.median(core, axis=0), int((_white_mask(icon) > 0).sum())


def _is_node(cell, s):
    if cell is None:
        return False
    (h, sat, v), white = cell
    # 可选的下一步节点带白色光晕、在闪，饱和度会掉到 129～130（2026-10-24 天幕实测，以前卡 130 时间歇漏检）；
    # 暗的不可达节点饱和度 ≤105、亮度 ≤105，所以亮的放宽到 110
    return (sat >= 130 or (sat >= 110 and v >= 180)) and v >= 80 and white >= 120 * s * s


def _orange_kind(hsv, x, y, s):
    """橙色节点：火焰＝休息，罗盘＝结算（航点）。"""
    big = _white_mask(hsv[int(y - 36 * s):int(y + 36 * s), int(x - 44 * s):int(x + 44 * s)])
    if s != 1:
        big = cv2.resize(big, (88, 72))
    scores = {t: float(cv2.matchTemplate(big, _ref(name), cv2.TM_CCOEFF_NORMED).max())
              for t, name in (("休息", "ref_flame"), ("结算", "ref_compass"))}
    return max(scores, key=scores.get)


def _has_shop(hsv, x, y, s):
    """休息点右上角的收银机小图标（米色、低饱和、亮）。"""
    p = hsv[int(y - 62 * s):int(y - 28 * s), int(x + 36 * s):int(x + 70 * s)]
    if p.size == 0:
        return False
    m = (p[..., 0] >= 15) & (p[..., 0] <= 40) & (p[..., 1] >= 25) & (p[..., 1] <= 110) & (p[..., 2] >= 160)
    return m.mean() > 0.12


def _has_pin(hsv, x, y, s):
    """当前位置：节点正上方的水滴形图钉（青白色）。"""
    if y < 300 * s and x > hsv.shape[1] - 160 * s:
        return False    # 右上角的「i」说明按钮也是白色，别当成图钉
    p = hsv[int(y - 75 * s):int(y - 30 * s), int(x - 15 * s):int(x + 15 * s)]
    if p.size == 0:
        return False
    # 图钉是青白色；靠近地图边缘时整体偏暗（实测 V 只有 150~190），所以按色相 + 低饱和 + 中等亮度判断
    m = (p[..., 0] >= 75) & (p[..., 0] <= 105) & (p[..., 1] < 140) & (p[..., 2] > 140)
    return m.mean() > 0.25


def column_phase(hsv, s):
    """这一帧里节点列的水平相位：先用连通域找出饱和色的菱形，取它们中心 x 对列间距的环形平均。"""
    mask = ((hsv[..., 1] >= 130) & (hsv[..., 2] >= 80)).astype(np.uint8)
    mask[:int(MAP_TOP * s)] = 0
    mask[int(MAP_BOTTOM * s):] = 0
    n, _lab, stats, cents = cv2.connectedComponentsWithStats(mask)
    pitch = COL_PITCH * s
    xs = [cents[i][0] for i in range(1, n)
          if 1500 * s * s < stats[i][4] < 10000 * s * s and 100 * s < stats[i][2] < 160 * s]
    if not xs:
        return None
    ang = np.array(xs) / pitch * 2 * np.pi
    phase = np.arctan2(np.sin(ang).mean(), np.cos(ang).mean()) / (2 * np.pi) * pitch
    return phase % pitch


def detect_nodes(frame):
    """一帧里所有有色（可到达的）节点：[{x, y, row, type, shop, current}]，x/y 为帧内像素。"""
    s = _scale(frame)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    phase = column_phase(hsv, s)
    nodes = []
    if phase is None:
        return nodes
    boss = detect_boss(frame)
    for x in np.arange(phase, frame.shape[1], COL_PITCH * s):
        for row, ry in enumerate(ROW_Y):
            y = ry * s
            if boss and x > boss[0] - 180 * s:
                continue    # 首领那一大块粉色不算普通节点
            c = _cell(hsv, x, y, s)
            if not _is_node(c, s):
                continue
            t = _hue_type(c[0][0])
            if t is None:
                continue
            if t == "橙":
                t = _orange_kind(hsv, x, y, s)
            nodes.append({"x": float(x), "y": float(y), "row": row, "type": t,
                          "shop": t == "休息" and _has_shop(hsv, x, y, s), "current": _has_pin(hsv, x, y, s)})
    return nodes


def detect_boss(frame):
    """首领：一大块粉色（面积远大于普通节点）。返回帧内中心 (x, y) 或 None。"""
    s = _scale(frame)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = ((hsv[..., 0] >= 150) & (hsv[..., 1] > 100) & (hsv[..., 2] > 120)).astype(np.uint8)
    mask[:int(MAP_TOP * s)] = 0
    n, _lab, stats, cents = cv2.connectedComponentsWithStats(mask)
    big = [(stats[i][4], cents[i]) for i in range(1, n) if stats[i][4] > 15000 * s * s]
    if not big:
        return None
    _a, (cx, cy) = max(big, key=lambda b: b[0])
    return float(cx), float(cy)


def line_coverage(frame, a, b):
    """两个节点（帧内坐标）之间白线的覆盖率：沿 a 右端点 → b 左端点采样，看多少点附近有亮白像素。"""
    s = _scale(frame)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    x0, y0 = a["x"] + TIP_DX * s, a["y"] + LINE_DY * s
    x1, y1 = b["x"] - TIP_DX * s, b["y"] + LINE_DY * s
    h, w = hsv.shape[:2]
    hits = total = 0
    for t in np.linspace(0.1, 0.9, 17):
        x, y = int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t)
        r = max(2, int(3 * s))
        if not (r <= x < w - r and r <= y < h - r):
            continue
        p = hsv[y - r:y + r + 1, x - r:x + r + 1]
        total += 1
        if ((p[..., 1] < 80) & (p[..., 2] > 170)).any():
            hits += 1
    return hits / total if total else 0.0


def frame_shift(prev, cur):
    """两帧之间地图的水平平移（像素，地图往左移为负），以及相关强度。

    相位相关是周期的，平移超过半屏会混叠（-1023 测成 +897），所以拖动测量用 strip_shift；这个只用来判断「还在不在动」。
    """
    s = _scale(prev)
    a = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)[int(MAP_TOP * s):int(MAP_BOTTOM * s)].astype(np.float32)
    b = cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY)[int(MAP_TOP * s):int(MAP_BOTTOM * s)].astype(np.float32)
    (dx, _dy), resp = cv2.phaseCorrelate(a, b)
    return dx, resp


def strip_shift(prev, cur, x0=0.55, x1=0.85):
    """地图往左拖之后的平移：取上一帧右侧一条（x0~x1 屏宽），在新帧里找它的位置。返回 (dx, 匹配分)。"""
    s = _scale(prev)
    w = prev.shape[1]
    a = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)[int(MAP_TOP * s):int(MAP_BOTTOM * s)]
    b = cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY)[int(MAP_TOP * s):int(MAP_BOTTOM * s)]
    strip = a[:, int(x0 * w):int(x1 * w)]
    res = cv2.matchTemplate(b, strip, cv2.TM_CCOEFF_NORMED)
    _min, score, _minloc, (mx, _my) = cv2.minMaxLoc(res)
    return float(mx - int(x0 * w)), float(score)


def build_map(frames, offsets, line_threshold=0.75):
    """把几帧（及每帧相对第一帧的地图平移 offsets，像素）拼成整层图。

    返回 map_info：{"nodes": [{id, type, row, col, special_features}], "adjacency": {id: [id]}, "current": id}，
    当前位置节点的 type 记为「当前位置」（和小地图识别一致）；在它左边的列（走过的）丢掉。
    """
    s = _scale(frames[0])
    pitch = COL_PITCH * s
    merged = {}           # (col, row) → node
    seen_in = {}          # (col, row) → [(frame_idx, frame_node)]
    origin = None
    boss_gx = None
    for i, (frame, off) in enumerate(zip(frames, offsets)):
        for n in detect_nodes(frame):
            gx = n["x"] - off
            if origin is None:
                origin = gx
            col = int(round((gx - origin) / pitch))
            key = (col, n["row"])
            seen_in.setdefault(key, []).append((i, n))
            # 同一个节点好几帧都拍到：类型/商店取离屏幕中间最近那帧的。屏幕右边缘有暗角，火焰图标的白色不全会认成罗盘
            # （2026-10-27 08:24 两个休息[商店]在第一次露出的右边缘那帧认成了结算，走到跟前重扫才认对）
            edge = abs(n["x"] - frame.shape[1] / 2)
            if key not in merged or edge < merged[key]["edge"]:
                was_current = key in merged and merged[key]["current"]
                merged[key] = dict(n, col=col, px=gx, edge=edge, current=n["current"] or was_current)
            elif n["current"]:
                merged[key]["current"] = True
        boss = detect_boss(frame)
        if boss:
            boss_gx, boss_gy = boss[0] - off, boss[1]
    if boss_gx is not None:
        # 首领只露出一部分时面积不够、认不成首领，它左边那截会被当成普通节点
        merged = {k: n for k, n in merged.items() if n["px"] < boss_gx - 180 * s}
    if not merged:
        return {"nodes": [], "adjacency": {}, "current": None}
    # 当前位置在打开地图时的第一帧里；有多个候选取最左边的
    cur_key = min((k for k, n in merged.items() if n["current"]), default=None)
    min_col = cur_key[0] if cur_key else min(k[0] for k in merged)
    keys = sorted(k for k in merged if k[0] >= min_col)
    ids = {k: i for i, k in enumerate(keys)}
    nodes = []
    for k in keys:
        n = merged[k]
        nodes.append({"id": ids[k], "type": "当前位置" if k == cur_key else n["type"], "row": k[1], "col": k[0],
                      "special_features": [{"feature_name": "shop_in_map", "priority": 1}] if n["shop"] else [],
                      "px": n["px"], "py": n["y"]})    # px/py：拼接大图上的位置（流程追踪画图用）
    adjacency = {ids[k]: [] for k in keys}
    by_col = {}
    for k in keys:
        by_col.setdefault(k[0], []).append(k)
    current = ids.get(cur_key) if cur_key else None
    if current is None:
        # 刚进新的一层：人还在第一列之前，地图上没有图钉。补一个虚拟起点连到最左列的所有节点
        current = len(nodes)
        nodes.append({"id": current, "type": "当前位置", "row": 2, "col": min_col - 1, "special_features": []})
        adjacency[current] = [ids[k] for k in by_col[min_col]]
    for col, ks in by_col.items():
        for a in ks:
            for b in by_col.get(col + 1, []):
                cov = 0.0
                for ia, na in seen_in[a]:
                    nb = next((n for ib, n in seen_in[b] if ib == ia), None)
                    if nb is not None:
                        cov = max(cov, line_coverage(frames[ia], na, nb))
                if cov >= line_threshold:
                    adjacency[ids[a]].append(ids[b])
    last_col = max(by_col)
    if boss_gx is not None:
        boss_id = len(nodes)
        nodes.append({"id": boss_id, "type": "首领", "row": 2, "col": last_col + 1, "special_features": [],
                      "px": boss_gx, "py": boss_gy})
        adjacency[boss_id] = []
        for k in by_col[last_col]:
            adjacency[ids[k]].append(boss_id)
    return {"nodes": nodes, "adjacency": adjacency, "current": current}


def successors_rank(map_info, node_id):
    """路线页右侧的可选节点就是当前节点的后继，从上到下排；返回 node_id 在其中的名次（1 起）。"""
    cur = map_info.get("current")
    succ = sorted(map_info["adjacency"].get(cur, []), key=lambda i: map_info["nodes"][i]["row"])
    return succ.index(node_id) + 1 if node_id in succ else None


def describe(map_info):
    """日志用：按列列出节点 类型@行 和连线。"""
    cols = {}
    for n in map_info["nodes"]:
        tag = n["type"] + ("[商店]" if n["special_features"] else "")
        cols.setdefault(n["col"], []).append(f"{tag}@{n['row']}")
    parts = [f"列{c}:" + ",".join(v) for c, v in sorted(cols.items())]
    edges = sum(len(v) for v in map_info["adjacency"].values())
    return f"{len(map_info['nodes'])}个节点 {edges}条连线 | " + " ".join(parts)


# ------------------------- 实机操作 -------------------------

def _grab(task):
    task.next_frame()
    return task.frame.copy()


def gap_x(frame, near):
    """离 near（屏宽比例）最近的两列节点正中间的 x（比例）。拖地图按下的点要落在列与列之间：
    只避开行还不够，2026-10-27 08:15 按在 0.6 那列节点的光晕下面，照样被当成点节点、关了地图去预览。"""
    s = _scale(frame)
    phase = column_phase(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV), s)
    if phase is None:
        return near
    pitch, w = COL_PITCH * s, frame.shape[1]
    k = round((near * w - phase - pitch / 2) / pitch)
    return (phase + pitch / 2 + k * pitch) / w


MK_LBUTTON = 0x0001


def _drag(task, x0, y, x1, duration=0.6, steps=20):
    """慢拖：按下 → 分 steps 步匀速移到终点（每步真等）→ 停住再松开，地图只移动拖的距离、不甩。
    框架的 PostMessage swipe 把 duration 当毫秒、每 100ms 一步：swipe_relative(duration=1.0) 实际只有 10 步 × 10ms，
    0.1 秒的甩动（地图惯性滑出 2.6 倍）；游戏一卡帧，按下和松开落在同一帧就成了点击，全屏地图被关回路线页
    （2026-10-27 08:15/08:31/08:37 三次，按下点都不在节点上）。"""
    inter = getattr(getattr(task, "executor", None), "interaction", None)
    if inter is None or "down_btn" not in inspect.signature(inter.move).parameters:
        task.swipe_relative(x0, y, x1, y, duration=duration)
        return
    ax, ay, bx = int(x0 * task.width), int(y * task.height), int(x1 * task.width)
    inter.move(ax, ay)
    time.sleep(0.05)
    task.mouse_down(ax, ay)
    for i in range(1, steps + 1):
        time.sleep(duration / steps)
        inter.move(int(ax + (bx - ax) * i / steps), ay, down_btn=MK_LBUTTON)
    time.sleep(0.15)
    task.mouse_up()


def _drag_to_left(task):
    """地图会记住上次的滚动位置：往右拖到拖不动（最左端），返回停下后的帧。"""
    frame = _settle(task)
    for _ in range(10):
        x0 = gap_x(frame, 0.3)
        _drag(task, x0, DRAG_Y, x0 + 0.4)
        cur = _settle(task)
        moved = frame_shift(frame, cur)[0]
        frame = cur
        if abs(moved) < 10 * _scale(cur):
            break
    return frame


def _settle(task, timeout=6.0):
    """等地图停下（打开动画、拖动惯性）：连续两帧平移小于 3 像素。返回最后一帧。"""
    prev = _grab(task)
    waited = 0.0
    while waited < timeout:
        task.sleep(0.5)
        waited += 0.5
        cur = _grab(task)
        if abs(frame_shift(prev, cur)[0]) < 3 * _scale(cur):
            return cur
        prev = cur
    return prev


def _button_score(frame, region, name):
    s = _scale(frame)
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = region
    reg = cv2.cvtColor(frame[int(y1 * h):int(y2 * h), int(x1 * w):int(x2 * w)], cv2.COLOR_BGR2GRAY)
    if s != 1:
        reg = cv2.resize(reg, (int(reg.shape[1] / s), int(reg.shape[0] / s)))
    tpl = _ref(name)
    if reg.shape[0] < tpl.shape[0] or reg.shape[1] < tpl.shape[1]:
        return 0.0
    return float(cv2.matchTemplate(reg, tpl, cv2.TM_CCOEFF_NORMED).max())


def map_open(frame):
    """全屏地图开着：左下角有「缩小（M）」按钮。路线页、开关地图的转场都没有（实测地图帧 ≥0.98、其他 ≤0.25）。
    地图上点开了节点信息面板时按钮被面板盖住，也认不出来。"""
    return _button_score(frame, ZOOM_REGION, "ref_zoom_out") >= 0.7


def route_page(frame):
    """回到了路线页：小地图右上角有「放大（M）」按钮（实测路线页 ≥0.88、全屏地图/转场/节点面板 ≤0.24）。"""
    return _button_score(frame, ZOOM_IN_REGION, "ref_zoom_in") >= 0.7


def _wait_route_page(task, timeout):
    waited = 0.0
    while waited < timeout:
        task.sleep(0.5)
        waited += 0.5
        if route_page(_grab(task)):
            task.sleep(0.5)
            return True
    return False


def close_map(task, tries=4):
    """关掉全屏地图、等回到路线页。返回是否回到了路线页。

    2026-10-27 08:54：扫完最后一帧时地图上开着首领的信息面板（盖住了「缩小」按钮），只在认出按钮时才按 M，
    结果地图没关，接着点路线节点点中了地图上的首领，卡了一分钟。所以按「回到路线页」判断：
    还认得出「缩小」按钮就按 M，两个按钮都认不出（面板挡着或在转场）就点地图空白处关面板，再看。
    """
    for _ in range(tries):
        cur = _grab(task)
        if route_page(cur):
            return True
        if map_open(cur):
            task.send_key("m")
        else:
            task.click(*EMPTY_SPOT)
        task.sleep(2)
    if route_page(_grab(task)):
        return True
    task.log_info("全屏地图关不回路线页（按了 M、点了空白处都没回来）")
    return False


def scan_layer(task, max_frames=12, drag=0.18, dump_dir=None):
    """路线页：按 M 打开全屏地图 → 先拖到最左端 → 每次往左拖 drag 屏宽拍一帧直到拖不动 → 再按 M 关掉。

    地图会记住上次的滚动位置，所以每次都先拖回最左端。返回 map_info，失败返回 None。
    """
    task.send_key("m")
    task.sleep(1.5)
    frames, offsets, total = [_drag_to_left(task)], [0.0], 0.0
    ok, retried, reopened = True, False, False
    while len(frames) < max_frames:
        x0 = gap_x(frames[-1], 0.6)
        _drag(task, x0, DRAG_Y, x0 - drag)
        cur = _settle(task)
        dx, score = strip_shift(frames[-1], cur)
        if score < 0.6 and len(frames) == 1 and not retried:
            # 第一帧可能拍到了打开地图的像素擦除转场（2026-10-27 08:15 刚回路线页就扫描）：拖回最左端重拍一次
            task.log_info(f"全屏地图第一帧对不上（匹配分 {score:.2f}），可能拍到了打开动画，拖回最左端重拍")
            retried = True
            frames = [_drag_to_left(task)]
            continue
        if score < 0.6 and not reopened and not map_open(cur):
            # 拖动后全屏地图被关回了路线页（2026-10-27 08:15/08:31/08:37/08:45，按下点不在节点上、慢拖也有，原因没查清）。
            # 刚关上时马上按 M 不响应（08:31「关地图后」还是路线页）：等转场完、认出路线页再按，
            # 地图记得滚动位置，接着拍。转场有时超过 3.5 秒（09:05 拖完 3.5 秒还没出小地图），按认出为准最多等 8 秒
            if _wait_route_page(task, 8):
                task.log_info(f"全屏地图拖动后被关掉了（匹配分 {score:.2f}），按 M 重新打开接着扫")
                reopened = True
                task.send_key("m")
                task.sleep(1.5)
                cur = _settle(task)
                dx, score = strip_shift(frames[-1], cur)
        if score < 0.6:
            task.log_info(f"全屏地图拖动后对不上上一帧（匹配分 {score:.2f}，平移可能超过半屏），放弃这次扫描")
            # 2026-10-27 06:33 起层开头频繁失败，原因还没看到：前后两帧存进流程追踪
            import chaos_trace
            chaos_trace.step(task, "map_fail", f"拖动前（第{len(frames)}帧）", frames[-1], score=round(score, 2))
            chaos_trace.step(task, "map_fail", "拖动后", cur, score=round(score, 2))
            ok = False
            break
        if abs(dx) < 10 * _scale(cur):
            break
        if dx > 0:
            task.log_info(f"全屏地图往左拖却测到向右平移 {dx:.0f}，放弃这次扫描")
            ok = False
            break
        total += dx
        frames.append(cur)
        offsets.append(total)
    close_map(task)
    if not ok:
        import chaos_trace
        chaos_trace.step(task, "map_fail", "关地图后", _grab(task))
        return None
    if dump_dir:
        os.makedirs(dump_dir, exist_ok=True)
        for i, f in enumerate(frames):
            cv2.imwrite(os.path.join(dump_dir, f"chaos_map_{i}.png"), f)
    info = build_map(frames, offsets)
    task.log_info(f"全屏地图扫描：{len(frames)}帧，平移{[round(o) for o in offsets]}，{describe(info)}")
    import chaos_trace
    chaos_trace.map_scan(task, frames, offsets, info)
    return info if info["nodes"] and info["current"] is not None else None
