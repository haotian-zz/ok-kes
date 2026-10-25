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


class TestPin(unittest.TestCase):
    def test_pin_at_dark_edge(self):
        # 拖到最左端时当前位置在画面右下边缘，图钉偏暗（V 150~190），以前认不出
        frame = cv2.imread(os.path.join(FIX, "layer1_edge_pin.png"))
        cur = [(n["row"], n["type"]) for n in cm.detect_nodes(frame) if n["current"]]
        self.assertEqual([(4, "小怪")], cur)


if __name__ == "__main__":
    unittest.main()
