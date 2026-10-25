# 卡厄思局外准备（utils_chaos_prep）单测：用国服实机截图的 OCR 结果（tests/fixtures/*.ocr.txt）做样例，不需要游戏
import os
import sys
import unittest
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ok_tasks"))

from utils_chaos_prep import parse_explore_regions, parse_preset_cards, parse_preset_counts  # noqa: E402

W, H = 1920, 1080


def load_ocr(name):
    """读 dev_probe 存的 OCR 文本（每行：cx,cy<TAB>置信度<TAB>文字），还原成以中心为准的框。"""
    boxes = []
    with open(os.path.join(ROOT, "tests", "fixtures", name), encoding="utf-8-sig") as f:
        for line in f:
            parts = line.rstrip("\r\n").split("\t")
            if len(parts) < 3 or "," not in parts[0]:
                continue
            cx, cy = (float(v) for v in parts[0].split(","))
            w, h = 0.05, 0.02
            boxes.append(SimpleNamespace(name=parts[2], x=(cx - w / 2) * W, y=(cy - h / 2) * H, width=w * W, height=h * H))
    return boxes


class TestPreset(unittest.TestCase):
    texts = load_ocr("preset_rosweisse_1.ocr.txt")

    def test_cards(self):
        cards = parse_preset_cards(self.texts, W, H)
        got = [(c["name"], c["n"], c["god_spark"]) for c in cards]
        self.assertEqual(8, len(cards))
        self.assertEqual(("明灭剑", 5, "add_r_spark_circen_06"), got[0])
        self.assertEqual([("剑鸣九霄", 2, "add_r_spark_circen_03")] * 3, got[1:4])
        self.assertEqual("剑鸣九霄", got[4][0])
        self.assertEqual(("剑刃破晓", 5, None), got[5])
        self.assertEqual(("循环之刃", 2, None), got[6])
        self.assertEqual(("基尔肯的神眷者", 0, None), got[7])

    def test_counts(self):
        self.assertEqual({"pt": (180, 180), "copy": (3, 3), "remove": (3, 5)}, parse_preset_counts(self.texts))


class TestChaosFigure(unittest.TestCase):
    def test_regions(self):
        regions = parse_explore_regions(load_ocr("chaos_figure_regions.ocr.txt"), W, H)
        self.assertEqual({"双星的暗影": 19, "裁决之沼": 30, "蓝罐": 30, "雾之都市": 24},
                         {r["name"]: r["explore"] for r in regions})


if __name__ == "__main__":
    unittest.main()
