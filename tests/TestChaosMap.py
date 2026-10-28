# 卡厄思全屏地图整层扫描（chaos_map）单测：2026-10-24 国服实机「双星的暗影」第 1 层，三帧拖动截图，不需要游戏
import os
import sys
import unittest

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ok_tasks"))

import chaos_map as cm  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures", "chaos_map")


class TestLayerScan(unittest.TestCase):
    frames = [cv2.imread(os.path.join(FIX, f"layer1_b{i}.png")) for i in range(3)]

    def build(self):
        offs = [0.0]
        for a, b in zip(self.frames, self.frames[1:]):
            offs.append(offs[-1] + cm.strip_shift(a, b)[0])
        return cm.build_map(self.frames, offs)

    def test_columns(self):
        info = self.build()
        cols = {}
        for n in info["nodes"]:
            cols.setdefault(n["col"], []).append((n["row"], n["type"], bool(n["special_features"])))
        self.assertEqual([(3, "当前位置", False)], cols[0])
        self.assertEqual([(3, "休息", True), (4, "小怪", False)], cols[1])
        self.assertEqual([(3, "结算", False), (4, "结算", False)], cols[4])
        self.assertEqual([(r, "休息", True) for r in range(5)], cols[11])
        self.assertEqual([(2, "首领", False)], cols[12])
        self.assertEqual(13, len(cols))

    def test_edges(self):
        info = self.build()
        key = {(n["col"], n["row"]): n["id"] for n in info["nodes"]}
        adj = {k: sorted((info["nodes"][j]["col"], info["nodes"][j]["row"]) for j in info["adjacency"][i])
               for k, i in key.items()}
        self.assertEqual([(1, 3), (1, 4)], adj[(0, 3)])
        self.assertEqual([(2, 3), (2, 4)], adj[(1, 4)])
        self.assertEqual([(4, 3), (4, 4)], adj[(3, 4)])
        self.assertEqual([(10, 0), (10, 2)], adj[(9, 2)])
        self.assertEqual([(11, 1), (11, 2)], adj[(10, 2)])
        self.assertEqual([(12, 2)], adj[(11, 0)])
        self.assertEqual(42, sum(len(v) for v in info["adjacency"].values()))

    def test_route(self):
        from utils import find_best_map_route_by_priority
        import chaos_strategy as cs
        info = self.build()
        plan = find_best_map_route_by_priority(info, ["事件", "休息", "小怪", "精英"], cs.ROUTE_WEIGHTS[cs.MODE_EMPTY])
        types = [info["nodes"][i]["type"] for i in plan["route"]]
        self.assertEqual("当前位置", types[0])
        self.assertEqual("首领", types[-1])
        self.assertEqual(13, len(types))


class TestLayerStart(unittest.TestCase):
    def test_virtual_start_without_pin(self):
        # 刚进新的一层没有图钉：补虚拟起点，连到最左列全部节点（用不含图钉的后两帧模拟）
        frames = TestLayerScan.frames[1:]
        info = cm.build_map(frames, [0.0, cm.strip_shift(*frames)[0]])
        cur = info["nodes"][info["current"]]
        self.assertEqual("当前位置", cur["type"])
        first = sorted(info["nodes"][i]["row"] for i in info["adjacency"][info["current"]])
        self.assertEqual([3, 4], first)


class TestPin(unittest.TestCase):
    def test_pin_at_dark_edge(self):
        # 拖到最左端时当前位置在画面右下边缘，图钉偏暗（V 150~190），以前认不出
        frame = cv2.imread(os.path.join(FIX, "layer1_edge_pin.png"))
        cur = [(n["row"], n["type"]) for n in cm.detect_nodes(frame) if n["current"]]
        self.assertEqual([(4, "小怪")], cur)


class TestGlowSuccessor(unittest.TestCase):
    def test_glowing_successors_detected(self):
        # 天幕第 1 层：当前位置后面两个可选节点带白色光晕在闪，饱和度掉到 129，以前间歇漏掉上面那个小怪；左下的暗节点不能算
        frame = cv2.imread(os.path.join(FIX, "tianmu_glow_succ.png"))
        got = sorted((round(n["x"]), n["row"], n["type"], bool(n["current"])) for n in cm.detect_nodes(frame) if n["x"] < 1000)
        self.assertEqual([(512, 2, "小怪", True), (758, 0, "小怪", False), (758, 2, "事件", False)], got)


class TestCardPins(unittest.TestCase):
    # 2026-10-24 天幕实机选卡页：游戏按预设在该删/该闪的卡右上角标橙色图钉；卡牌识别给的 x/y 是左上类型图标
    ICONS = [(626, 187), (946, 187), (1262, 187), (1578, 187), (626, 640), (946, 640), (1262, 640), (1578, 640)]

    def pinned(self, name):
        from utils import find_card_pins, card_has_pin
        pins = find_card_pins(cv2.imread(os.path.join(FIX, name + ".jpg")))
        return [i for i, (x, y) in enumerate(self.ICONS) if card_has_pin({"x": x / 1920, "y": y / 1080}, pins)]

    def test_remove_page(self):
        self.assertEqual([0, 1, 4], self.pinned("cards_remove_pins"))      # 斩念、入鞘、酷寒斗士

    def test_flash_page(self):
        self.assertEqual([0, 1, 3, 4, 5], self.pinned("cards_flash_pins"))  # 除了酷寒斗士都标了


class TestMergeNearCenter(unittest.TestCase):
    def test_type_from_frame_nearest_center(self):
        # 2026-10-27 08:24：休息[商店]第一次露出在右边缘（暗角）认成结算，往左拖到中间那帧认对了；合并取中间那帧
        import numpy as np
        frames = [np.zeros((1080, 1920, 3), np.uint8) for _ in range(2)]
        seen = [[{"x": 300.0, "y": 710.0, "row": 3, "type": "精英", "shop": False, "current": True},
                 {"x": 1846.0, "y": 710.0, "row": 3, "type": "结算", "shop": False, "current": False}],
                [{"x": 1100.0, "y": 710.0, "row": 3, "type": "休息", "shop": True, "current": False}]]
        calls = iter(seen)
        old = cm.detect_nodes
        cm.detect_nodes = lambda frame: next(calls)
        try:
            info = cm.build_map(frames, [0.0, -746.0])
        finally:
            cm.detect_nodes = old
        node = next(n for n in info["nodes"] if n["col"] == 6)
        self.assertEqual("休息", node["type"])
        self.assertTrue(node["special_features"])
        self.assertEqual("当前位置", next(n for n in info["nodes"] if n["col"] == 0)["type"])


class TestLayerStartPin(unittest.TestCase):
    def _build(self, seen):
        import numpy as np
        frames = [np.zeros((1080, 1920, 3), np.uint8)]
        old = cm.detect_nodes
        cm.detect_nodes = lambda frame: seen
        try:
            return cm.build_map(frames, [0.0])
        finally:
            cm.detect_nodes = old

    @staticmethod
    def _node(x, row, current=False, t="小怪"):
        return {"x": x, "y": 300.0 + 100 * row, "row": row, "type": t, "shop": False, "current": current}

    def test_pin_in_column_with_other_nodes_ignored(self):
        # 2026-10-27 11:37 第二层开头：第一列 3 个小怪，最上面那个认出了图钉 → 当前位置是第一列之前的虚拟起点
        info = self._build([self._node(500, 0, True), self._node(500, 2), self._node(500, 3), self._node(746, 1)])
        cur = next(n for n in info["nodes"] if n["id"] == info["current"])
        self.assertEqual(-1, cur["col"])
        self.assertEqual(3, len(info["adjacency"][info["current"]]))
        self.assertEqual(3, sum(1 for n in info["nodes"] if n["col"] == 0 and n["type"] == "小怪"))

    def test_pin_alone_in_column_kept(self):
        info = self._build([self._node(500, 2, True), self._node(746, 1), self._node(746, 3)])
        cur = next(n for n in info["nodes"] if n["id"] == info["current"])
        self.assertEqual((0, 2, "当前位置"), (cur["col"], cur["row"], cur["type"]))


class TestMapOpen(unittest.TestCase):
    def test_zoom_button_tells_map_from_route_page(self):
        # 拖动后地图被关回路线页时要能认出来（2026-10-27 08:45 实录的路线页）
        self.assertTrue(cm.map_open(cv2.imread(os.path.join(FIX, "drag_hit_node.jpg"))))
        self.assertTrue(cm.map_open(cv2.imread(os.path.join(FIX, "layer1_b0.png"))))
        self.assertFalse(cm.map_open(cv2.imread(os.path.join(FIX, "route_page.jpg"))))
        # 地图上开着节点信息面板时「缩小」按钮被盖住（2026-10-27 08:54 实录首领面板）
        self.assertFalse(cm.map_open(cv2.imread(os.path.join(FIX, "map_node_panel.jpg"))))

    def test_zoom_in_button_tells_route_page(self):
        self.assertTrue(cm.route_page(cv2.imread(os.path.join(FIX, "route_page.jpg"))))
        for name in ("drag_hit_node.jpg", "layer1_b0.png", "map_node_panel.jpg", "cards_flash_pins.jpg"):
            self.assertFalse(cm.route_page(cv2.imread(os.path.join(FIX, name))), name)


class TestCloseMap(unittest.TestCase):
    def _task(self, start):
        views = {k: cv2.imread(os.path.join(FIX, f)) for k, f in
                 (("panel", "map_node_panel.jpg"), ("map", "layer1_b0.png"), ("route", "route_page.jpg"))}
        st = {"view": start, "keys": 0, "clicks": [], "logs": []}

        class T:
            frame = None
            def next_frame(self): self.frame = views[st["view"]]
            def sleep(self, s): pass
            def log_info(self, msg, *a, **k): st["logs"].append(msg)
            def send_key(self, k):
                st["keys"] += 1
                if st["view"] == "map":
                    st["view"] = "route"
            def click(self, x, y):
                st["clicks"].append((x, y))
                if st["view"] == "panel":
                    st["view"] = "map"

        return T(), st

    def test_dismiss_node_panel_then_close(self):
        # 2026-10-27 08:54：扫完地图开着首领面板，没按 M，点路线节点点中了地图上的首领；先点空白处关面板再按 M
        t, st = self._task("panel")
        self.assertTrue(cm.close_map(t))
        self.assertEqual([cm.EMPTY_SPOT], st["clicks"])
        self.assertEqual(1, st["keys"])

    def test_already_on_route_page(self):
        t, st = self._task("route")
        self.assertTrue(cm.close_map(t))
        self.assertEqual((0, []), (st["keys"], st["clicks"]))


class TestEmptySpot(unittest.TestCase):
    def test_empty_spot_clear_of_ui(self):
        # 825281f：点空白处原来在 (0.62, 0.9)，路线页的节点大图从 0.52 起、左边小地图到 0.42，节点大图状态下点上去不回来
        # （2026-10-27 09:33）；挪到 (0.5, 0.96)：两者中间、全屏地图最下一行节点和左下角缩放按钮之外
        x, y = cm.EMPTY_SPOT
        self.assertTrue(0.42 < x < 0.52, x)
        self.assertGreater(y * cm.REF_H, cm.MAP_BOTTOM)
        zx1, zy1, zx2, zy2 = cm.ZOOM_REGION
        self.assertFalse(zx1 <= x <= zx2 and zy1 <= y <= zy2)
        for name in ("layer1_b0.png", "drag_hit_node.jpg"):
            frame = cv2.imread(os.path.join(FIX, name))
            h, w = frame.shape[:2]
            for n in cm.detect_nodes(frame):
                self.assertGreater(abs(n["y"] - y * h) + abs(n["x"] - x * w), 120 * cm._scale(frame), (name, n))


class TestDragHeight(unittest.TestCase):
    def test_drag_between_rows(self):
        # 按在节点上拖会被当成点节点、全屏地图关掉（2026-10-27 实录 0.55 在第 3 行节点下尖角）
        y = cm.DRAG_Y * cm.REF_H
        self.assertTrue(all(abs(y - r) > 60 for r in cm.ROW_Y))

    def test_drag_between_columns(self):
        # 2026-10-27 08:15 实录：在 x=0.6 按下拖，按到那列节点、地图关掉去预览；按下点要落在两列中间
        frame = cv2.imread(os.path.join(FIX, "drag_hit_node.jpg"))
        w, pitch = frame.shape[1], cm.COL_PITCH * cm._scale(frame)
        nodes = cm.detect_nodes(frame)
        self.assertTrue(nodes)
        for near in (0.3, 0.6):
            x = cm.gap_x(frame, near) * w
            self.assertLessEqual(abs(x - near * w), pitch / 2 + 1)
            self.assertTrue(all(abs(x - n["x"]) >= 0.4 * pitch for n in nodes), (near, x))
        self.assertTrue(any(abs(0.6 * w - n["x"]) < 0.3 * pitch for n in nodes))   # 原来的按下点贴着节点列

    def test_scan_retries_transition_first_frame(self):
        # 第一帧是转场画面、拖一下就对不上：拖回最左端重拍，不放弃整次扫描
        import numpy as np
        calls = {"swipes": 0, "logs": []}
        good = cv2.imread(os.path.join(FIX, "drag_hit_node.jpg"))
        wipe = np.random.default_rng(0).integers(0, 255, good.shape, dtype=np.uint8)
        seq = iter([wipe] * 4 + [good] * 200)

        class T:
            frame = None
            def send_key(self, k): pass
            def sleep(self, s): pass
            def log_info(self, msg, *a, **k): calls["logs"].append(msg)
            def next_frame(self): self.frame = next(seq)
            def swipe_relative(self, *a, **k): calls["swipes"] += 1

        cm.scan_layer(T(), max_frames=3)
        self.assertTrue(any("拖回最左端重拍" in m for m in calls["logs"]))
        self.assertFalse(any("放弃这次扫描" in m for m in calls["logs"]))
        self.assertEqual(4, calls["swipes"])                 # 拖到左端 1 + 对不上 1 + 重拖到左端 1 + 拖不动 1

    def test_slow_drag_reaches_end_with_button_held(self):
        # 框架 swipe 实际 0.1 秒甩动、最后一步只到 90%；慢拖要按住左键一路移到终点再松开
        ev = []

        class Inter:
            def move(self, x, y, down_btn=0):
                ev.append(("move", x, y, down_btn))
                return (x, y)
            def post(self, msg, wparam, lparam): ev.append(("post", msg, wparam, lparam))

        class T:
            width, height = 1920, 1080
            executor = type("E", (), {"interaction": Inter()})()
            def mouse_down(self, x, y): ev.append(("down", x, y))
            def mouse_up(self): ev.append(("up",))

        old = cm.time.sleep
        cm.time.sleep = lambda s: None
        try:
            cm._drag(T(), 0.6, 0.5, 0.42)
        finally:
            cm.time.sleep = old
        self.assertEqual(("down", 1152, 540), ev[1])
        self.assertEqual(("move", 806, 540, cm.MK_LBUTTON), ev[-2])
        # 在终点松开：框架 mouse_up 会在 (0, 0) 松开
        self.assertEqual(("post", cm.WM_LBUTTONUP, 0, (806, 540)), ev[-1])
        self.assertNotIn(("up",), ev)
        self.assertTrue(all(e[3] == cm.MK_LBUTTON for e in ev[2:-1]))

    def test_slow_drag_holds_long_enough(self):
        # 641c8b7：框架 swipe_relative(duration=1.0) 实际 10 步 × 10ms，0.1 秒的甩动，游戏一卡帧按下和松开落在同一帧
        # 就成了点击（08:15/08:31/08:37 地图被关）。慢拖：按住至少 0.5 秒、至少 10 步移到终点
        ev, now = [], [0.0]

        class Inter:
            def move(self, x, y, down_btn=0):
                ev.append(("move", now[0], down_btn))
                return (x, y)
            def post(self, msg, wparam, lparam): ev.append(("post", now[0], msg))

        class T:
            width, height = 1920, 1080
            executor = type("E", (), {"interaction": Inter()})()
            def mouse_down(self, x, y): ev.append(("down", now[0]))
            def mouse_up(self): ev.append(("up", now[0]))
            def swipe_relative(self, *a, **k): ev.append(("swipe", now[0]))

        old = cm.time.sleep
        cm.time.sleep = lambda s: now.__setitem__(0, now[0] + s)
        try:
            cm._drag(T(), 0.6, cm.DRAG_Y, 0.42)
        finally:
            cm.time.sleep = old
        self.assertNotIn("swipe", [e[0] for e in ev])
        down = next(e[1] for e in ev if e[0] == "down")
        up = next(e[1] for e in ev if e[0] in ("post", "up"))
        self.assertGreaterEqual(up - down, 0.5)
        self.assertGreaterEqual(sum(1 for e in ev if e[0] == "move" and e[2] == cm.MK_LBUTTON), 10)

    def _closing_task(self, m_reopens, swallow=0, stay_preview=True, route_delay=0.0, swallow_m=0):
        """拍到第 2 帧后再拖，地图关回路线页；m_reopens=False 时按 M 也不响应（打不开）。
        stay_preview=False：关掉后直接是转场、不停在节点大图状态；route_delay：关掉后过这么多秒（task.sleep 累计）路线页才认得出；
        swallow_m：地图被拖动关掉后，头几下 M 不响应（2026-10-27 08:31 刚关上马上按 M 没反应），之后照常。"""
        import numpy as np
        good = cv2.imread(os.path.join(FIX, "drag_hit_node.jpg"))
        moved = good.copy()
        top = int(0.885 * good.shape[0])                     # 只平移地图部分，左下角「缩小 M」按钮不动
        moved[:top] = np.roll(good[:top], -200, axis=1)
        views = [good, moved]
        route = cv2.resize(cv2.imread(os.path.join(FIX, "route_page.jpg")), (good.shape[1], good.shape[0]))
        preview = np.random.default_rng(1).integers(0, 255, good.shape, dtype=np.uint8)   # 不带顶栏的节点大图
        # 关地图转场：路线页淡入、小地图（「放大」按钮）还没出来。画面不动，_settle 马上认为停稳（全黑帧相位相关是 nan，会等满 6 秒）
        fading = route.copy()
        x1, y1, x2, y2 = cm.ZOOM_IN_REGION
        fading[int(y1 * route.shape[0]):int(y2 * route.shape[0]), int(x1 * route.shape[1]):int(x2 * route.shape[1])] = 0
        st = {"open": False, "pos": 0, "swipes": 0, "keys": 0, "logs": [], "preview": False, "clicks": 0,
              "swallow": swallow, "swallow_m": swallow_m, "t": 0.0, "closed_at": None, "click_pos": [], "click_t": []}

        class T:
            frame = None
            def send_key(self, k):
                st["keys"] += 1
                if st["closed_at"] is not None and st["swallow_m"] > 0:
                    st["swallow_m"] -= 1
                    return
                if st["open"]:
                    st["open"] = False
                elif st["keys"] == 1 or m_reopens:
                    st["open"] = True
            def sleep(self, s): st["t"] += s
            def log_info(self, msg, *a, **k): st["logs"].append(msg)
            def next_frame(self):
                if st["open"]:
                    self.frame = views[st["pos"]]
                elif st["preview"]:
                    self.frame = preview
                elif st["closed_at"] is not None and st["t"] - st["closed_at"] < route_delay:
                    self.frame = fading
                else:
                    self.frame = route
            def click(self, x, y):
                st["clicks"] += 1
                st["click_pos"].append((x, y))
                st["click_t"].append(st["t"])
                if st["preview"] and st["swallow"]:      # 落在关地图转场里的点击被吞掉
                    st["swallow"] -= 1
                    return
                st["preview"] = False
            def swipe_relative(self, *a, **k):
                st["swipes"] += 1               # 第 1 下拖到左端（已经在左端），第 2 下拍到第 2 帧，第 3 下关了地图
                if st["swipes"] == 2:
                    st["pos"] = 1
                elif st["swipes"] == 3:
                    st["open"] = False
                    st["preview"] = stay_preview
                    st["closed_at"] = st["t"]

        return T(), st

    def test_scan_reopens_map_closed_by_drag(self):
        # 2026-10-27 08:31：拖动被当成点击、地图关回路线页；按 M 重新打开接着扫，不放弃
        t, st = self._closing_task(m_reopens=True)
        cm.scan_layer(t, max_frames=3)
        self.assertTrue(any("按 M 重新打开" in m for m in st["logs"]))
        self.assertFalse(any("放弃这次扫描" in m for m in st["logs"]))
        self.assertEqual(3, st["keys"])                      # 打开、重开、扫完关掉
        self.assertEqual(1, st["clicks"])                    # 节点大图状态先点空白处才按 M（2026-10-27 09:33）
        self.assertEqual([cm.EMPTY_SPOT], st["click_pos"])
        self.assertFalse(st["open"])

    def test_gives_up_on_route_page_without_pressing_m_again(self):
        # 4dc924b：重开那下 M 没响应、放弃扫描时已经在路线页，不能再按 M（这时 M 有效，会把地图打开，接着点路线节点点到地图上）
        t, st = self._closing_task(m_reopens=True, swallow_m=1)
        self.assertIsNone(cm.scan_layer(t, max_frames=3))
        self.assertTrue(any("按 M 重新打开" in m for m in st["logs"]))
        self.assertTrue(any("放弃这次扫描" in m for m in st["logs"]))
        self.assertEqual(2, st["keys"])
        self.assertFalse(st["open"])

    def test_reopen_waits_for_slow_route_page(self):
        # feaabf5：2026-10-27 09:05 拖完地图关了，路线页转场 3.5 秒还没出小地图；原来固定等 3 秒就判断、没认出就放弃。
        # 按认出路线页为准：转场 5 秒也要等到、按 M 重开
        t, st = self._closing_task(m_reopens=True, stay_preview=False, route_delay=5.0)
        cm.scan_layer(t, max_frames=3)
        self.assertTrue(any("按 M 重新打开" in m for m in st["logs"]))
        self.assertFalse(any("放弃这次扫描" in m for m in st["logs"]))
        self.assertEqual(3, st["keys"])

    def test_reopen_wait_bounded_and_clicks_every_two_seconds(self):
        # 路线页一直认不出：最多等 8 秒就放弃（不卡死），期间每 2 秒点一次空白处（fb3968c），点的都是空白处（825281f）
        t, st = self._closing_task(m_reopens=True, stay_preview=False, route_delay=1e9)
        self.assertIsNone(cm.scan_layer(t, max_frames=3))
        self.assertTrue(any("放弃这次扫描" in m for m in st["logs"]))
        self.assertFalse(any("按 M 重新打开" in m for m in st["logs"]))
        waits = st["click_t"][:4]
        self.assertEqual([2.0, 2.0, 2.0], [b - a for a, b in zip(waits, waits[1:])])
        self.assertTrue(all(p == cm.EMPTY_SPOT for p in st["click_pos"][:4]))

    def test_reopen_clicks_again_when_first_click_swallowed(self):
        # 2026-10-27 11:31：点一次空白处没回来、等满 8 秒放弃；每 2 秒再点一次
        t, st = self._closing_task(m_reopens=True, swallow=1)
        cm.scan_layer(t, max_frames=3)
        self.assertTrue(any("按 M 重新打开" in m for m in st["logs"]))
        self.assertFalse(any("放弃这次扫描" in m for m in st["logs"]))
        self.assertEqual(2, st["clicks"])

    def test_scan_gives_up_without_opening_map_on_route_page(self):
        t, st = self._closing_task(m_reopens=False)
        self.assertIsNone(cm.scan_layer(t, max_frames=3))
        self.assertTrue(any("放弃这次扫描" in m for m in st["logs"]))
        self.assertEqual(2, st["keys"])                      # 还在路线页：最后不再按 M（会把地图打开）
        self.assertFalse(st["open"])


if __name__ == "__main__":
    unittest.main()

