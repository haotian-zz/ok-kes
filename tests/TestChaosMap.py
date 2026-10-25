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


if __name__ == "__main__":
    unittest.main()
