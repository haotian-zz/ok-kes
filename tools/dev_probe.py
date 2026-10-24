"""开发调试用：无界面跑一组动作（截帧+OCR 落盘、点击坐标/文字、按键、等待），供远程实机测试。

    .venv\\Scripts\\python.exe tools\\dev_probe.py actions.json

actions.json 是动作列表，例如：
    [{"op": "shot", "name": "home"},
     {"op": "click", "x": 0.5, "y": 0.5},
     {"op": "click_text", "text": "确认", "timeout": 10},
     {"op": "key", "key": "esc"},
     {"op": "sleep", "s": 2}]
输出写到 dev_out/：<name>.png（当前帧）和 <name>.txt（OCR 文本及相对坐标）。
"""

import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for p in (ROOT, os.path.join(ROOT, "ok_tasks")):
    if p not in sys.path:
        sys.path.insert(0, p)

import cv2  # noqa: E402
from ok import BaseTask, run_task  # noqa: E402

OUT_DIR = os.path.join(ROOT, "dev_out")
ACTIONS_FILE = os.environ.get("OKKES_ACTIONS", os.path.join(ROOT, "dev_out", "actions.json"))


class DevProbe(BaseTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "DevProbe"
        self.description = "开发调试：按 actions.json 执行动作"

    def _shot(self, name):
        os.makedirs(OUT_DIR, exist_ok=True)
        frame = self.next_frame()
        cv2.imwrite(os.path.join(OUT_DIR, f"{name}.png"), frame)
        h, w = frame.shape[:2]
        lines = [f"frame {w}x{h}"]
        for box in self.ocr() or []:
            cx = (box.x + box.width / 2) / w
            cy = (box.y + box.height / 2) / h
            lines.append(f"{cx:.3f},{cy:.3f}\t{box.confidence:.2f}\t{box.name}")
        with open(os.path.join(OUT_DIR, f"{name}.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        self.log_info(f"shot {name}: {len(lines) - 1} boxes")

    def run(self):
        with open(ACTIONS_FILE, encoding="utf-8") as f:
            actions = json.load(f)
        for a in actions:
            op = a["op"]
            self.log_info(f"action {a}")
            if op == "shot":
                self._shot(a.get("name", time.strftime("%H%M%S")))
            elif op == "click":
                self.move_relative(a["x"], a["y"])
                self.sleep(0.5)
                self.click(a["x"], a["y"], after_sleep=a.get("after", 1))
            elif op == "click_text":
                box = self.wait_ocr(match=re.compile(a["text"]), time_out=a.get("timeout", 10))
                if box:
                    b = box[0]
                    h, w = self.frame.shape[:2]
                    cx, cy = (b.x + b.width / 2) / w, (b.y + b.height / 2) / h
                    self.move_relative(cx, cy)
                    self.sleep(0.5)
                    self.click(cx, cy, after_sleep=a.get("after", 1))
                else:
                    self.log_info(f"text not found: {a['text']}")
            elif op == "key":
                self.send_key(a["key"], after_sleep=a.get("after", 1))
            elif op == "home":
                import utils_daily
                self.log_info(f"go_home -> {utils_daily.go_home(self, a.get('timeout', 60))}")
            elif op == "call":
                import utils_daily
                self.log_info(f"{a['fn']} -> {getattr(utils_daily, a['fn'])(self, **a.get('kwargs', {}))}")
            elif op == "sleep":
                self.sleep(a["s"])
            else:
                self.log_info(f"unknown op {op}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        os.environ["OKKES_ACTIONS"] = ACTIONS_FILE = os.path.abspath(sys.argv[1])
    from src.config import config

    config["onetime_tasks"] = list(config["onetime_tasks"]) + [["tools.dev_probe", "DevProbe"]]
    # 探针只连已经开着的游戏；找不到窗口时别让框架去拉起游戏/模拟器
    config["windows"] = {**config["windows"], "start_exe": False}
    try:
        run_task(config, task="DevProbe")
    finally:
        os._exit(0)
