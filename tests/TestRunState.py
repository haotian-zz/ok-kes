# 卡厄思一局一个 RunState、局内状态落盘/恢复、账本和游戏对账、刷刻印达成即停的单测（2026-10-27 状态类 bug 回归）。
# 跑法：python -m unittest tests.TestRunState（tests/__init__.py 先把 dev_out 指到临时目录）
import json
import os
import sys
import time
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ok_tasks"))

import chaos_trace  # noqa: E402
import utils  # noqa: E402
import utils_imprint  # noqa: E402


def _snapshot(path):
    """目录下所有文件（相对路径 → 大小、修改时间）；目录不存在返回 None。"""
    if not os.path.isdir(path):
        return None
    out = {}
    for d, _, files in os.walk(path):
        for f in files:
            p = os.path.join(d, f)
            st = os.stat(p)
            out[os.path.relpath(p, path)] = (st.st_size, st.st_mtime)
    return out


class TestDevOutIsolation(unittest.TestCase):
    """实录 2026-10-27 17:58:50：TestRouteClickSettle 走到 audit_escape → chaos_trace.step，往实机 dev_out/chaos_trace 写了
    一条「escape」，还会按 KEEP_RUNS 删实机旧追踪。测试环境下追踪和落盘都要在临时目录。"""

    def test_trace_and_state_files_not_in_real_dev_out(self):
        real_dev_out = os.path.abspath("dev_out")
        for path in (chaos_trace.TRACE_ROOT, utils.RUN_STATE_FILE, utils.LAST_BOSS_FAIL_FILE):
            self.assertFalse(os.path.abspath(path).startswith(real_dev_out + os.sep), path)

    def test_escape_audit_does_not_touch_real_trace(self):
        real = os.path.abspath(os.path.join("dev_out", "chaos_trace"))
        before = _snapshot(real)
        logs = []
        ns = {"enter_new_node": False, "node_count": 8, "pass_final_boss_count": 1, "route_clicked_at": 0,
              "full_route": {"layer": 1, "steps": [{"type": "精英"}, {"type": "首领"}], "done": 1}}
        t = types.SimpleNamespace(node_status=ns, config={"刷刻印": True, "刷刻印速刷": True, "刷刻印对账": False},
                                  member_status={"equipment": {"imprints": ["", "", ""]}}, frame=None,
                                  log_info=logs.append, sleep=lambda s: None,
                                  move_relative=lambda x, y: None, click=lambda x, y: logs.append(("click", x, y)))
        orig = utils.is_route_selection_page, utils.handle_escape
        utils.is_route_selection_page = lambda task: True
        utils.handle_escape = lambda task: False
        try:
            self.assertTrue(utils_imprint.handle_rush_escape(t))
        finally:
            utils.is_route_selection_page, utils.handle_escape = orig
        self.assertEqual(before, _snapshot(real))                      # 实机目录没被写、也没被删
        with open(os.path.join(t._chaos_trace["dir"], "trace.jsonl"), encoding="utf-8") as f:
            self.assertIn('"kind": "escape"', f.read())                # 写进了临时目录


if __name__ == "__main__":
    unittest.main()
