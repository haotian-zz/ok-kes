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


import chaos_strategy as cs  # noqa: E402
import run_state  # noqa: E402


class _Box(types.SimpleNamespace):
    def area(self):
        return max(1, self.width * self.height)


def box(x, y, name, w=80, h=30):
    return _Box(x=x * 1920 - w / 2, y=y * 1080 - h / 2, width=w, height=h, name=name)


def chaos_task(**kw):
    """卡厄思局内的假 task：node_status/member_status 是新开局的样子，点击记进 clicks。"""
    logs, clicks = [], []
    t = types.SimpleNamespace(node_status=utils._initial_node_status(), member_status=utils._initial_member_status(),
                              config={}, chaos_mode="", width=1920, height=1080, all_texts=[], frame=None,
                              log_info=logs.append, log_error=lambda *a, **k: logs.append(a[0]), sleep=lambda s: None,
                              move_relative=lambda x, y: None, click=lambda x, y, **k: clicks.append((x, y)),
                              next_frame=lambda: None, send_key=lambda k: clicks.append(("key", k)),
                              click_box=lambda b, **k: clicks.append(("box", b.name)))
    t.logs, t.clicks = logs, clicks
    for k, v in kw.items():
        setattr(t, k, v)
    return t


class RunStateFileCase(unittest.TestCase):
    """每个用例用自己的落盘文件和每局记录文件。"""

    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp()
        self.saved = utils.RUN_STATE_FILE, run_state.RUNS_FILE
        utils.RUN_STATE_FILE = os.path.join(self.dir, "chaos_run_state.json")
        run_state.RUNS_FILE = os.path.join(self.dir, "chaos_runs.jsonl")

    def tearDown(self):
        import shutil
        utils.RUN_STATE_FILE, run_state.RUNS_FILE = self.saved
        shutil.rmtree(self.dir, ignore_errors=True)

    def restart(self, **kw):
        """模拟重启：新进程的 task（reset_all_status 后的样子）从落盘恢复。"""
        t = chaos_task(**kw)
        utils.reset_all_status(t)
        return t, utils.restore_run_state(t)


class TestBossClickPersisted(RunStateFileCase):
    """cccf494 实录 2026-10-27 04:14：点了首领后重启，reach_final_boss 没落盘，首领结算不算层数，第二层被当成第一层。"""

    def test_restart_after_boss_click_counts_layer(self):
        t = chaos_task(chaos_pt_cap=150, find_feature=lambda **k: [], box_of_screen=lambda *a: None)
        t.run_state = run_state.RunState(source="测试")
        t.node_status.update(node_count=7, pt_panel_read=True)
        orig = utils.is_route_selection_page, utils._move_and_click
        utils.is_route_selection_page = lambda task: True
        utils._move_and_click = lambda task, x, y: task.clicks.append((x, y))
        try:
            self.assertTrue(utils.handle_route_selection(t))       # 认不出节点、没有整层计划 → 首领
            self.assertIn((0.815, 0.492), t.clicks)
            t2, ok = self.restart()                                # 刚点完首领就重启
            self.assertTrue(ok)
            self.assertTrue(t2.node_status["reach_final_boss"])
            t2.all_texts = [box(0.941, 0.917, "结算")]
            self.assertTrue(utils.handle_settlement(t2))            # 首领结算：层数 +1
        finally:
            utils.is_route_selection_page, utils._move_and_click = orig
        self.assertEqual(1, t2.node_status["pass_final_boss_count"])


class TestEquipmentAndShopPersisted(RunStateFileCase):
    """2d5ed0f：装备和装备位刻印随局内状态落盘（重启后速刷把已拿到的目标刻印少算）；
    刷刻印商店看过的商品按卡片位置记，也要落盘（原来漏了，重启后同一商店重新点开看）。"""

    def test_equipment_imprints_and_shop_seen_survive_restart(self):
        t = chaos_task(config={"刷刻印": True})
        t.run_state = run_state.RunState(source="测试")
        eq = t.member_status["equipment"]
        eq["names"] = ["混沌之识", "精灵王的金冠", ""]
        eq["imprints"] = [utils_imprint.TARGET, utils_imprint.TARGET, ""]
        t.node_status.update(node_count=5, pass_final_boss_count=1)
        icons = [box(x, 0.83, "120") for x in (0.10, 0.30, 0.50)]
        utils_imprint.mark_shop_seen(t, icons[1])
        utils.save_run_state(t)
        t2, ok = self.restart(config={"刷刻印": True})
        self.assertTrue(ok)
        self.assertEqual(["混沌之识", "精灵王的金冠", ""], t2.member_status["equipment"]["names"])
        self.assertEqual(2, utils_imprint.target_imprint_count(t2))
        # 买走第一件后后面的信用点图标序号前移，按位置记就不会把没看过的当成看过
        self.assertTrue(utils_imprint.shop_seen(t2, icons[1]))
        self.assertFalse(utils_imprint.shop_seen(t2, icons[2]))


class TestNewRunDoesNotInheritOldRun(RunStateFileCase):
    """f3236d5 / 实录 2026-10-27 15:54：上一局的落盘状态被读回带进了新局（进法典要清上一局）；
    imprint_peak 只增不减、chaos_core_got 要落盘。"""

    def _old_run(self):
        t = chaos_task(config={"刷刻印": True}, chaos_pt_cap=150)
        run_state.begin(t, "法典")
        old_id = t.run_state.run_id
        t.member_status["equipment"]["names"] = ["混沌之识", "", ""]
        t.member_status["equipment"]["imprints"] = [utils_imprint.TARGET, utils_imprint.TARGET, ""]
        t.node_status.update(node_count=9, pass_final_boss_count=1, chaos_core_got="混沌之识")
        utils_imprint.target_imprint_count(t)
        utils.save_run_state(t)
        return t, old_id

    def test_chaos_core_and_peak_survive_restart(self):
        t, old_id = self._old_run()
        t2, ok = self.restart(config={"刷刻印": True})
        self.assertTrue(ok)
        self.assertEqual(old_id, t2.run_state.run_id)
        self.assertEqual("混沌之识", t2.node_status["chaos_core_got"])
        self.assertEqual(2, t2.node_status["imprint_peak"])
        t2.member_status["equipment"]["imprints"] = ["", "", ""]        # 装备页淡入读成空槽
        self.assertEqual(2, utils_imprint.target_imprint_count(t2))      # 只增不减
        self.assertEqual(0, utils_imprint.required_imprints(t2))         # 混沌之识：不要求刻印

    def test_codex_enter_starts_clean_run(self):
        from tests.TestImprint import SELECT_PAGE
        t, old_id = self._old_run()
        t.all_texts = list(SELECT_PAGE)
        t.ocr = lambda *a, **k: list(SELECT_PAGE)
        self.assertTrue(utils_imprint.handle_codex_select(t))           # 1 号法典合格 → 进入
        self.assertNotEqual(old_id, t.run_state.run_id)
        self.assertNotIn("chaos_core_got", t.node_status)
        self.assertEqual(["", "", ""], t.member_status["equipment"]["names"])
        t2, ok = self.restart(config={"刷刻印": True})                  # 新局读到 PT 上限前就重启
        self.assertTrue(ok)
        self.assertEqual(t.run_state.run_id, t2.run_state.run_id)
        self.assertNotIn("chaos_core_got", t2.node_status)
        self.assertEqual(0, t2.node_status.get("imprint_peak", 0))
        self.assertEqual(["", "", ""], t2.member_status["equipment"]["names"])
        runs = run_state.read_runs()                                    # 上一局没走到结算：补记一条
        self.assertEqual([(old_id, "未结算", "混沌之识")], [(r["run_id"], r["result"], r["chaos_core"]) for r in runs])

    def test_other_run_id_not_restored(self):
        t, old_id = self._old_run()
        t2 = chaos_task()
        t2.run_state = run_state.RunState(source="另一局")
        self.assertFalse(utils.restore_run_state(t2))
        self.assertNotIn("chaos_core_got", t2.node_status)

    def test_finished_run_archived_and_not_restored(self):
        t, old_id = self._old_run()
        t.node_status["is_escaped"] = True
        utils_imprint.audit_escape(t, "第二层首领前目标刻印只有 1 个")
        rec = run_state.finish(t, "逃脱")
        self.assertEqual(("逃脱", "第二层首领前目标刻印只有 1 个", 1), (rec["result"], rec["reason"], rec["layers"]))
        self.assertEqual(["混沌之识", "", ""], rec["equipment"])
        self.assertFalse(os.path.exists(utils.RUN_STATE_FILE))
        utils.save_run_state(t)                                         # 结算后每帧的落盘不能把文件写回来
        self.assertFalse(os.path.exists(utils.RUN_STATE_FILE))
        self.assertIsNone(run_state.finish(t, "逃脱"))                  # 同一局只记一次
        self.assertEqual(1, len(run_state.read_runs()))
        _, ok = self.restart()
        self.assertFalse(ok)

    def test_expedition_result_archives_run(self):
        t, old_id = self._old_run()
        t.all_texts = [box(0.625, 0.122, "探险结果"), box(0.928, 0.122, "完成")]
        t.ocr = lambda *a, **k: list(t.all_texts)
        utils.handle_expedition_result(t)
        runs = run_state.read_runs()
        self.assertEqual([(old_id, "通关")], [(r["run_id"], r["result"]) for r in runs])
        self.assertNotIn("chaos_core_got", t.node_status)               # 结算后清本局
        self.assertFalse(os.path.exists(utils.RUN_STATE_FILE))


class TestRestoreShopFlagWithRun(RunStateFileCase):
    """4d4ecbf 实录 2026-10-27 07:23：休息点（带商店）中途重启，新进程 shop=False，商店没进（TestRestoreShopFlag 覆盖旧格式落盘，
    这里覆盖带 run_id 的新格式）。"""

    def test_restore_sets_shop(self):
        t = chaos_task(config={"进入商店": True})
        run_state.begin(t, "进入")
        t2, ok = self.restart(config={"进入商店": True})
        self.assertTrue(ok)
        self.assertTrue(t2.node_status["shop"])


class TestSaveMemberIndexRestart(RunStateFileCase):
    """ddd2520 实录 2026-10-27 08:37：重启后第一个装备页认不出主战员，装备被随机分给了队友。落盘 → 重启 → 按记下的序号。"""

    def test_index_survives_restart(self):
        t = chaos_task()
        run_state.begin(t, "进入")
        t.node_status["save_member_index"] = 2
        utils.save_run_state(t)
        t2, ok = self.restart(feature_exists=lambda name: False)
        self.assertTrue(ok)
        lv = [types.SimpleNamespace(x=1200, y=y, width=40, height=20) for y in (340, 580, 820)]
        self.assertEqual(2, utils._find_target_member_index(t2, lv, (0, 0, 1, 1)))


class TestPendingRemovalPersisted(RunStateFileCase):
    """原来挂在 task._pending_removed_card_count 上（重启就丢、PT 账少记）：收进 node_status 一起落盘。"""

    def test_pending_removal_counts_after_restart(self):
        t = chaos_task()
        run_state.begin(t, "进入")
        t.node_status["pending_removed_card_count"] = 2
        utils.save_run_state(t)
        t2, ok = self.restart()
        self.assertTrue(ok)
        t2.all_texts = [box(0.945, 0.918, "移除")]
        orig = utils.is_button_active
        utils.is_button_active = lambda task, b: True
        try:
            self.assertTrue(utils.handle_remove(t2))
        finally:
            utils.is_button_active = orig
        self.assertEqual(2, t2.node_status["removed_card_count"])
        self.assertEqual(0, t2.node_status["pending_removed_card_count"])


class TestStartupBlankFrame(unittest.TestCase):
    """d1fdf27 实录 2026-10-27 03:30：中途重启时游戏正好在节点转场，第一帧没字被当成主页，局内连按 ESC，也没读回落盘。"""

    def test_blank_first_frame_waits_and_restores(self):
        import utils_daily
        from ChaosMode import ChaosMode
        frames = iter([[], [box(0.5, 0.5, "收起有用的东西"), box(0.5, 0.9, "点击屏幕可关闭")]])
        t = chaos_task(chaos_mode=cs.MODE_TARGET, entry_checked=False)
        t.ocr = lambda *a, **k: next(frames, t.all_texts)
        t.all_texts = []
        t._at_lobby = lambda: ChaosMode._at_lobby(t)
        t._out_of_run_page = ChaosMode._out_of_run_page
        calls = []
        orig = utils_daily.go_home, utils.restore_run_state
        utils_daily.go_home = lambda task, *a, **k: calls.append("go_home") or False
        utils.restore_run_state = lambda task: calls.append("restore") or True
        try:
            self.assertFalse(ChaosMode._enter_chaos_from_home(t))
        finally:
            utils_daily.go_home, utils.restore_run_state = orig
        self.assertEqual(["restore"], calls)
        self.assertNotIn(("key", "esc"), t.clicks)


class TestImprintIgnoresCrossRunSeen(unittest.TestCase):
    """2c5d226：「拿过」（chaos_seen）是跨局图鉴记录，刷刻印每局都要重新拿目标装备，不能挡住本局目标装备来源事件加分
    （全天深绿黑夜来源事件「森林在提问」加分一次没生效）。"""

    def _bonus(self, imprint):
        t = chaos_task(chaos_mode=cs.MODE_TARGET, config={"刷刻印": imprint, "装备3号位优先级": ["深绿黑夜", "深绿桎梏"]},
                       chaos_seen={cs.equipment_key("深绿黑夜"), cs.equipment_key("深绿桎梏")})
        t.node_status["pass_final_boss_count"] = 1
        got = []
        orig = utils._get_current_hp_percent, cs.route_weights
        utils._get_current_hp_percent = lambda task: 80
        cs.route_weights = lambda mode, layer, hp, bonus, **k: got.append(bonus) or {}
        try:
            utils._chaos_route_weights(t)
        finally:
            utils._get_current_hp_percent, cs.route_weights = orig
        return got[0]

    def test_seen_does_not_block_bonus_in_imprint_mode(self):
        self.assertEqual(cs.EVENT_SOURCE_BONUS, self._bonus(imprint=True))
        self.assertEqual(0, self._bonus(imprint=False))             # 别的玩法照旧认跨局「拿过」


if __name__ == "__main__":
    unittest.main()
