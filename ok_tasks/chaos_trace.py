# 卡厄思流程追踪：把每一局的地图、路线、每次分支的打分和选择、每个页面的截图记下来，供人工审阅和事后复盘策略。
# 每次启动任务一个目录 dev_out/chaos_trace/<时间>/：trace.jsonl（一行一条）+ 截图；tools/chaos_trace_report.py 生成 HTML。
import json
import os
import shutil
import time

import cv2
import numpy as np

TRACE_ROOT = os.path.join("dev_out", "chaos_trace")
KEEP_RUNS = 10
IMG_WIDTH = 1280
PAGE_REPEAT_SECONDS = 4     # 同一个页面处理函数连续命中时，这么久内不重复截图


def _state(task):
    t = getattr(task, "_chaos_trace", None)
    if t is None:
        root = TRACE_ROOT
        os.makedirs(root, exist_ok=True)
        runs = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
        for d in runs[:max(0, len(runs) - KEEP_RUNS + 1)]:
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)
        path = os.path.join(root, time.strftime("%Y%m%d_%H%M%S"))
        os.makedirs(path, exist_ok=True)
        t = {"dir": path, "seq": 0, "last_page": None, "last_page_t": 0.0, "iter_seq": -1}
        task._chaos_trace = t
    return t


def enabled(task):
    try:
        return bool(task.config.get("记录流程追踪", True))
    except Exception:
        return False


def _context(task):
    ns = getattr(task, "node_status", None) or {}
    return {"round": ns.get("total_rounds", 0), "layer": ns.get("pass_final_boss_count", 0) + 1,
            "node": ns.get("node_count", 0), "mode": getattr(task, "chaos_mode", "")}


def _write(t, rec):
    with open(os.path.join(t["dir"], "trace.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


def _save_img(t, name, frame, width=IMG_WIDTH):
    if frame is None:
        return None
    h, w = frame.shape[:2]
    if w > width:
        frame = cv2.resize(frame, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)
    cv2.imwrite(os.path.join(t["dir"], name), frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
    return name


def step(task, kind, title, frame=None, **data):
    """记一条决策/页面。frame 给了就存截图。出错不影响任务。"""
    if not enabled(task):
        return
    try:
        t = _state(task)
        t["seq"] += 1
        img = _save_img(t, f"{t['seq']:04d}_{kind}.jpg", frame)
        _write(t, {"seq": t["seq"], "t": time.strftime("%H:%M:%S"), "kind": kind, "title": title,
                   "img": img, **_context(task), "data": data})
    except Exception as e:  # noqa: BLE001
        print(f"chaos_trace.step 失败: {e}")


def log(task, msg):
    """任务日志也记进去，挂在最近一条后面。"""
    if not enabled(task) or getattr(task, "_chaos_trace", None) is None:
        return
    try:
        _write(task._chaos_trace, {"kind": "log", "t": time.strftime("%H:%M:%S"), "msg": str(msg)})
    except Exception:  # noqa: BLE001
        pass


def begin_frame(task):
    """ChaosMode.run 每帧开头调用：记下这一帧开始时的序号，页面处理函数里记过决策就不再另存页面截图。"""
    if enabled(task):
        _state(task)["iter_seq"] = task._chaos_trace["seq"]


def page(task, handler, frame):
    """页面处理函数命中了：存一张处理前的截图（同一页面短时间内重复命中只记一次）。"""
    if not enabled(task):
        return
    t = _state(task)
    now = time.time()
    if t["seq"] != t["iter_seq"]:
        t["last_page"] = handler       # 这一帧已经记了决策（带截图）
        t["last_page_t"] = now
        return
    if handler == t["last_page"] and now - t["last_page_t"] < PAGE_REPEAT_SECONDS:
        return
    t["last_page"], t["last_page_t"] = handler, now
    step(task, "page", handler, frame)


# ---------------- 地图 ----------------

def _panorama(frames, offsets):
    """按每帧的地图平移把几帧拼成一张整层大图。offsets 是相对第一帧的平移（往左拖为负）。"""
    h, w = frames[0].shape[:2]
    width = int(w - min(offsets))
    pano = np.zeros((h, width, 3), np.uint8)
    for f, off in reversed(list(zip(frames, offsets))):
        x = int(round(-off))
        pano[:, x:x + w] = f[:, :min(w, width - x)]
    return pano


def draw_map(pano, info, route=None):
    img = pano.copy()
    by_id = {n["id"]: n for n in info["nodes"]}
    route = route or []
    on_route = set(zip(route, route[1:]))
    for a, bs in info["adjacency"].items():
        na = by_id.get(a)
        for b in bs:
            nb = by_id.get(b)
            if na and nb and "px" in na and "px" in nb:
                hot = (a, b) in on_route
                cv2.line(img, (int(na["px"]), int(na["py"])), (int(nb["px"]), int(nb["py"])),
                         (0, 0, 255) if hot else (0, 255, 255), 6 if hot else 2)
    for n in info["nodes"]:
        if "px" not in n:
            continue
        hot = n["id"] in route
        c = (int(n["px"]), int(n["py"]))
        cv2.circle(img, c, 34, (0, 0, 255) if hot else (0, 255, 0), 5 if hot else 3)
        cv2.putText(img, str(n["id"]), (c[0] - 12, c[1] - 42), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 4)
        cv2.putText(img, str(n["id"]), (c[0] - 12, c[1] - 42), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)
    return img


def map_scan(task, frames, offsets, info):
    """全屏地图扫完：存拼好的整层大图（标节点 id 和连线），留着给路线规划再画一次路线。"""
    if not enabled(task):
        return
    try:
        pano = _panorama(frames, offsets)
        _state(task)["pano"] = pano
        step(task, "map", "全屏地图扫描", draw_map(pano, info), frames=len(frames),
             offsets=[round(o) for o in offsets], nodes=info["nodes"], adjacency=info["adjacency"],
             current=info["current"])
    except Exception as e:  # noqa: BLE001
        print(f"chaos_trace.map_scan 失败: {e}")


def route_plan(task, info, plan, steps):
    if not enabled(task):
        return
    pano = _state(task).get("pano")
    img = draw_map(pano, info, plan["route"]) if pano is not None else None
    by_id = {n["id"]: n for n in info["nodes"]}
    step(task, "route", "整层路线规划", img, route=plan["route"], score=plan.get("weighted_score"),
         path=[by_id[i]["type"] for i in plan["route"]], steps=steps)
