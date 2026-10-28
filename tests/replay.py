"""场景回放测试框架：把一串「帧」（截图 + 预先跑好的 OCR 框 + 预先匹配的特征）按顺序喂给页面处理函数，
记下处理函数做了哪些操作（点击、按键、拖动……）和日志，测试只断言操作序列。不需要游戏、不跑 OCR，可重复。

复盘 docs/czn-okkes-postmortem-redesign.md 4.6：以后改装备/逃脱/路线代码，回放全过才上实机。

用法（tests/TestReplay.py 里有完整例子）：

    from replay import ReplayTask, load_frames, replay
    frames = load_frames("equip_1802.json", order=[0, 0])          # 同一帧喂两次
    task = ReplayTask(frames, config={"刷刻印": True}, default_config={"刷存档主战员": "海德玛丽"})
    steps = replay(utils.handle_equipment, task)                     # 每帧调一次处理函数
    self.assertFalse(any(a.target == "提炼" for a in task.actions))
    replay([utils.handle_equipment, utils.handle_confirm], task)     # 也可以给一串处理函数，按 ChaosMode.run 的顺序试

fixture（tests/fixtures/replay/*.json）用 tools/make_replay_fixture.py 在 Windows 上对流程追踪的 jpg 跑真 OCR 生成：
    {"note": "...", "width": 1920, "height": 1080,
     "frames": [{"image": "0043_refine.jpg", "texts": [[x, y, w, h, 置信度, "文字"], ...],
                 "features": {"leveltag": [[x, y, w, h, 置信度], ...]}}]}
坐标都是放大到 width×height 之后的像素（流程追踪截图被缩到 1280 宽，载入时同样放大），所以颜色取点、相对坐标都和实机一致；
JPEG 压缩会让颜色差几个点，品质色判断有 ±30 容差，实测不受影响。

帧的推进：第一次调用处理函数用第 0 帧；之后每次调用前翻到下一帧；处理函数自己调 next_frame() 也会往后翻
（翻到最后一帧就停在最后一帧）。区域 OCR（task.ocr(x1, y1, x2, y2)）按框中心落在区域内从整帧结果里筛，
和实机单独对小区域 OCR 的结果可能不完全一样。运行时生成的特征（刷存档主战员头像 target_member_*）没法离线匹配，
fixture 里按流程追踪日志手填。

时间：处理函数里的 time.time() / time.sleep() 走假时钟（task.clock），task.sleep() 只推进假时钟不真等；
每帧之间默认推进 frame_interval（0.5 秒，大约是实机一帧 OCR 的时间）。

---- 2026-10-27 的 bug：回放 / 单测分工 ----
适合回放（有实录截图、判断依赖 OCR + 颜色 + 多帧状态）：
- fee1447 装备页点了主战员后下一帧被重判、提炼掉（18:02 深绿黑夜）→ TestReplay.TestEquipmentReplay
- 以后的装备页淡入（品质读不出、空槽误读）、提炼/逃脱前判断：同样从流程追踪取帧做回放
只能单测（纯几何/图像函数，或依赖实机输入时序、截图没留下中间帧）：
- 3dd0581 拖动高度、f797ae4 按下点落在两列之间 / 第一帧转场重拍：图像函数，TestChaosMap.TestDragHeight
- 641c8b7 / 776c870 慢拖参数与在终点松开：输入层消息序列，截图看不出来，用假 interaction 记消息
- 4dc924b / feaabf5 / 825281f / fb3968c 地图被关回路线页后的重开流程：要的是「按 M / 点空白处后画面怎么变」的状态机，
  实录截图只有失败前后两张，没法回放整个过程，用状态机假 task（TestChaosMap._closing_task）
- d63efac 神闪页等「跳过」只等 3 次：判断只看文字，没有当时截图（10-26 的追踪已被轮转删除），用纯文字帧
"""
import json
import os
import random
import re
import sys
import time as _real_time
from types import SimpleNamespace

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OK_TASKS = os.path.join(ROOT, "ok_tasks")
if OK_TASKS not in sys.path:
    sys.path.insert(0, OK_TASKS)
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "replay")

try:
    from ok import Box
except Exception:  # noqa: BLE001  mac 上没装 ok 框架时的替身，字段和 ok.Box 一样
    class Box:
        def __init__(self, x, y, width=0, height=0, confidence=1.0, name=None):
            self.x, self.y = int(round(x)), int(round(y))
            self.width, self.height = max(1, int(round(width))), max(1, int(round(height)))
            self.confidence, self.name = confidence, name

        def area(self):
            return self.width * self.height

        def __repr__(self):
            return f"Box({self.name!r} {self.x},{self.y} {self.width}x{self.height})"


class Frame:
    """一帧：图（BGR ndarray，可以没有）+ OCR 框 + 特征框。框都是像素坐标。"""

    def __init__(self, image=None, texts=(), features=None, name="", width=1920, height=1080):
        self.image = image
        self.texts = list(texts)            # [(x, y, w, h, conf, name)]
        self.features = features or {}       # {名字: [(x, y, w, h, conf)]}
        self.name = name
        self.width, self.height = (image.shape[1], image.shape[0]) if image is not None else (width, height)

    @classmethod
    def from_texts(cls, items, image=None, features=None, name="", width=1920, height=1080):
        """手写文字帧：items 是 [(相对中心x, 相对中心y, 文字)] 或 [(x, y, 文字, 相对宽, 相对高)]，框默认 0.06×0.03。"""
        texts = []
        for it in items:
            x, y, text = it[:3]
            w, h = (it[3], it[4]) if len(it) >= 5 else (0.06, 0.03)
            texts.append(((x - w / 2) * width, (y - h / 2) * height, w * width, h * height, 1.0, text))
        return cls(image, texts, features, name, width, height)

    def boxes(self):
        return [Box(x, y, w, h, conf, name) for x, y, w, h, conf, name in self.texts]


def load_frames(name, order=None):
    """读 fixture json（相对 tests/fixtures/replay 或绝对路径），返回 [Frame]。order 给帧号列表可以重排/重复帧。"""
    path = name if os.path.isabs(name) else os.path.join(FIXTURES, name)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    w, h = data.get("width", 1920), data.get("height", 1080)
    cache, frames = {}, []
    for i, fr in enumerate(data["frames"]):
        img = None
        if fr.get("image"):
            key = fr["image"]
            if key not in cache:
                raw = cv2.imread(os.path.join(os.path.dirname(path), key))
                if raw is None:
                    raise FileNotFoundError(key)
                cache[key] = cv2.resize(raw, (w, h), interpolation=cv2.INTER_CUBIC) if raw.shape[:2] != (h, w) else raw
            img = cache[key]
        frames.append(Frame(img, [tuple(t) for t in fr.get("texts", [])],
                            {k: [tuple(b) for b in v] for k, v in (fr.get("features") or {}).items()},
                            fr.get("image") or f"frame{i}", w, h))
    return [frames[i] for i in order] if order is not None else frames


class Clock:
    """假时钟：替换 ok_tasks 模块里的 time，time()/sleep() 用它，其他（strftime 等）照常。"""

    def __init__(self, start=1_000_000.0):
        self.now = start

    def time(self):
        return self.now

    def sleep(self, s):
        self.now += max(0.0, float(s))

    def __getattr__(self, item):
        return getattr(_real_time, item)


class Action(SimpleNamespace):
    """一次操作：kind=click/click_box/move/key/swipe/mouse_down/mouse_up/scroll；x/y 相对坐标；target 点框时是框的文字。"""

    def __repr__(self):
        extra = f" {self.target!r}" if getattr(self, "target", "") else ""
        pos = f" ({self.x:.3f}, {self.y:.3f})" if getattr(self, "x", None) is not None else ""
        return f"<{self.kind}{pos}{extra} @帧{self.frame}>"


class ReplayTask:
    """假 task：提供页面处理函数用到的 ok 框架接口，操作和日志都记下来。其它属性（node_status、chaos_mode……）
    构造时按关键字参数给，或者直接赋值。"""

    name = "自动卡厄思模式"

    def __init__(self, frames, config=None, default_config=None, frame_interval=0.5, **attrs):
        self.frames = list(frames)
        self.cursor = -1
        self.config = {"记录流程追踪": False, **(config or {})}
        self.default_config = dict(default_config or {})
        self.node_status = {}
        self.member_status = None
        self.chaos_mode = ""
        self.clock = Clock()
        self.frame_interval = frame_interval
        self.actions, self.logs, self.info = [], [], {}
        self.disabled = False
        self.frame = None
        self.all_texts = []
        self.width, self.height = 1920, 1080
        for k, v in attrs.items():
            setattr(self, k, v)
        if self.frames:
            self._show(0)

    # ---------- 帧 ----------
    def _show(self, i):
        import utils
        self.cursor = min(i, len(self.frames) - 1)
        fr = self.frames[self.cursor]
        self.frame = fr.image
        self.width, self.height = fr.width, fr.height
        self.all_texts = utils._simplify_texts(fr.boxes())     # 和 ChaosMode.run 每帧开头一样转简体

    @property
    def current(self):
        return self.frames[self.cursor]

    def next_frame(self):
        if self.cursor + 1 < len(self.frames):
            self._show(self.cursor + 1)
        return self.frame

    def ocr(self, x=0, y=0, to_x=1, to_y=1, match=None, box=None, **_kw):
        if box is not None:
            x, y = box.x / self.width, box.y / self.height
            to_x, to_y = (box.x + box.width) / self.width, (box.y + box.height) / self.height
        out = [b for b in self.current.boxes()
               if x <= (b.x + b.width / 2) / self.width <= to_x and y <= (b.y + b.height / 2) / self.height <= to_y]
        if match is not None:
            pats = match if isinstance(match, (list, tuple)) else [match]
            out = [b for b in out if any((p.search(b.name) if isinstance(p, re.Pattern) else p == b.name)
                                         for p in pats)]
        return out

    def wait_ocr(self, *a, **kw):
        return self.ocr(*a, **kw) or None

    # ---------- 特征 ----------
    def box_of_screen(self, x, y, to_x=1.0, to_y=1.0, width=0.0, height=0.0, name=None, **_kw):
        w = width * self.width if width else (to_x - x) * self.width
        h = height * self.height if height else (to_y - y) * self.height
        return Box(x * self.width, y * self.height, w, h, 1.0, name)

    def feature_exists(self, feature_name):
        return any(feature_name in fr.features for fr in self.frames)

    def find_feature(self, feature_name=None, box=None, threshold=0, **_kw):
        out = []
        for x, y, w, h, conf in self.current.features.get(feature_name, []):
            cx, cy = x + w / 2, y + h / 2
            if box is not None and not (box.x <= cx <= box.x + box.width and box.y <= cy <= box.y + box.height):
                continue
            if conf >= threshold:
                out.append(Box(x, y, w, h, conf, feature_name))
        return out

    def find_one(self, feature_name=None, box=None, threshold=0, **kw):
        found = self.find_feature(feature_name, box=box, threshold=threshold, **kw)
        return max(found, key=lambda b: b.confidence) if found else None

    def wait_feature(self, feature, box=None, threshold=0, **_kw):
        return self.find_one(feature, box=box, threshold=threshold)

    # ---------- 操作 ----------
    def _rel(self, x, y):
        if x is not None and (x > 1 or y > 1):
            return x / self.width, y / self.height
        return x, y

    def _act(self, kind, x=None, y=None, **kw):
        x, y = self._rel(x, y)
        a = Action(kind=kind, x=x, y=y, frame=self.cursor, t=self.clock.now, target=kw.pop("target", ""), **kw)
        self.actions.append(a)
        return a

    def click(self, x=-1, y=-1, **kw):
        self._act("click", x, y)

    def click_relative(self, x, y, **kw):
        self._act("click", x, y)

    def click_box(self, box, relative_x=0.5, relative_y=0.5, **kw):
        self._act("click_box", box.x + box.width * relative_x, box.y + box.height * relative_y,
                  target=getattr(box, "name", "") or "")

    def move_relative(self, x, y, **kw):
        self._act("move", x, y)

    def send_key(self, key, **kw):
        self._act("key", target=str(key))

    def swipe_relative(self, from_x, from_y, to_x, to_y, duration=0.5, **kw):
        self._act("swipe", from_x, from_y, to=(to_x, to_y), duration=duration)

    def scroll_relative(self, x, y, count, **kw):
        self._act("scroll", x, y, count=count)

    def mouse_down(self, x=-1, y=-1, **kw):
        self._act("mouse_down", x, y)

    def mouse_up(self, **kw):
        self._act("mouse_up")

    def sleep(self, s):
        self.clock.sleep(s)

    def is_adb(self):
        return False

    def disable(self):
        self.disabled = True

    # ---------- 日志 ----------
    def log_info(self, msg, *a, **kw):
        self.logs.append(str(msg))

    log_debug = log_info

    def log_error(self, msg, *a, **kw):
        self.logs.append("[错误] " + str(msg))

    def info_set(self, key, value):
        self.info[key] = value

    # ---------- 查询 ----------
    def clicks(self):
        """点击类操作（click / click_box）的 (x, y)，保留三位小数。"""
        return [(round(a.x, 3), round(a.y, 3)) for a in self.actions if a.kind in ("click", "click_box")]

    def logged(self, text):
        return any(text in m for m in self.logs)


def _patch_time(clock):
    """把已载入的 ok_tasks 模块里的 time 换成假时钟，返回还原函数。"""
    patched = []
    for mod in list(sys.modules.values()):
        f = getattr(mod, "__file__", None) or ""
        if os.path.dirname(os.path.abspath(f)) == OK_TASKS and getattr(mod, "time", None) is _real_time:
            mod.time = clock
            patched.append(mod)

    def restore():
        for m in patched:
            m.time = _real_time
    return restore


def _run_handlers(handlers, task):
    """和 ChaosMode.run 一样依次试处理函数，第一个返回 True 的命中；返回命中的函数名（都没命中返回 None）。"""
    for h in handlers:
        if h(task):
            return h.__name__
    return None


def replay(handler, task, steps=None, seed=0):
    """按帧调用 handler(task)：第一次用当前帧，之后每次先翻到下一帧，直到帧用完（或调满 steps 次）。
    handler 也可以是处理函数列表（如 utils_chaos.PAGE_HANDLERS 的一段），按 ChaosMode.run 的顺序试，ret 是命中的函数名。
    返回每次调用的 [SimpleNamespace(frame=帧号, ret=返回值, actions=这次的操作, logs=这次的日志)]。"""
    if isinstance(handler, (list, tuple)):
        handlers = list(handler)
        handler = lambda t: _run_handlers(handlers, t)  # noqa: E731
    random.seed(seed)
    restore = _patch_time(task.clock)
    out = []
    try:
        n = 0
        while steps is None or n < steps:
            if n > 0:
                if task.cursor + 1 >= len(task.frames):
                    break
                task.clock.sleep(task.frame_interval)
                task._show(task.cursor + 1)
            a0, l0, frame = len(task.actions), len(task.logs), task.cursor
            ret = handler(task)
            out.append(SimpleNamespace(frame=frame, ret=ret, actions=task.actions[a0:], logs=task.logs[l0:]))
            n += 1
    finally:
        restore()
    return out
