# 国服变速浮窗（game_speed）单测：倍率大字解析、3.0x 按钮定位（实机 2026-10-27 OCR）
import os
import sys
import unittest
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ok_tasks"))

import game_speed as gs  # noqa: E402


def box(x, y, name):
    return SimpleNamespace(x=x * 1920, y=y * 1080, width=0, height=0, name=name)


# 实机浮窗 OCR（倍率 3.0 时）
PANEL = [box(0.064, 0.062, "变速功能"), box(0.237, 0.050, "F8/ESC关闭X"), box(0.154, 0.131, "30x"),
         box(0.153, 0.187, "当前运行倍率"), box(0.089, 0.243, "1伤择法典.5x"), box(0.185, 0.244, "2.0x"),
         box(0.248, 0.244, "3.0x"), box(0.041, 0.348, "1.0x"), box(0.263, 0.345, "3.0x"),
         box(0.161, 0.424, "暂停")]
TASK = SimpleNamespace(width=1920, height=1080)


class TestGameSpeed(unittest.TestCase):
    def test_add_config_defaults_on(self):
        # 用户 2026-11-06：脚本默认要打开三倍速（卡厄思/出击/剧情/一键日常都用同一个开关）
        task = SimpleNamespace(default_config={}, config_description={})
        gs.add_config(task)
        self.assertIs(True, task.default_config[gs.SPEED_KEY])
        self.assertIn("F8", task.config_description[gs.SPEED_KEY])

    def test_tasks_register_speed_switch(self):
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ok_tasks")
        for name in ("ChaosMode", "SortieMode", "StoryMode", "DailyTask"):
            src = open(os.path.join(root, f"{name}.py"), encoding="utf-8").read()
            self.assertIn("game_speed.add_config(self)", src, name)
            self.assertIn("game_speed.ensure_speed(self)", src, name)

    def test_parse_rate(self):
        self.assertEqual(3.0, gs.parse_rate("30x"))
        self.assertEqual(2.0, gs.parse_rate("20x"))
        self.assertEqual(1.5, gs.parse_rate("1.5x"))
        self.assertEqual(1.0, gs.parse_rate("1.0x"))
        self.assertIsNone(gs.parse_rate("当前运行倍率"))

    def test_panel_and_rate(self):
        self.assertTrue(gs._panel_open(TASK, PANEL))
        self.assertEqual(3.0, gs._rate(TASK, PANEL))
        self.assertFalse(gs._panel_open(TASK, [box(0.122, 0.045, "零式系统")]))

    def test_button_is_top_row(self):
        b = gs._button_3x(TASK, PANEL)
        self.assertAlmostEqual(0.244, b.y / 1080, places=3)


if __name__ == "__main__":
    unittest.main()
