# 新界面（src/ui/shell）的单测：卡厄思每个方案显示哪些键、切方案的联动、配置存储格式和旧文件兼容、
# 首页卡厄思卡片和运行记录读 dev_out 文件。不开窗口、不连游戏。
# 跑法：python -m unittest tests.TestShellUI
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ok_tasks"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import chaos_strategy  # noqa: E402
import config_io  # noqa: E402
from ChaosMode import SCHEME_KEYS, ChaosMode, scheme_sub_configs  # noqa: E402
from SortieMode import FLASH_HP_KEY, SortieMode  # noqa: E402
from ok.util.config import Config  # noqa: E402

from src.ui.shell import chaos_schema, chaos_stats, config_rules  # noqa: E402

FIXTURES = os.path.join(ROOT, "tests", "fixtures", "ui")
L, X, E, T = (chaos_schema.MODE_LEGACY, chaos_schema.MODE_EXPLORE, chaos_schema.MODE_EMPTY,
              chaos_schema.MODE_TARGET)


def _fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


def _task(cls):
    """不经过执行器建任务对象（只要 default_config / config_type / config_description）。"""
    task = cls(SimpleNamespace(scene=None), None)
    task.config = dict(task.default_config)
    return task


class TestChaosSchemeVisibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task = _task(ChaosMode)

    def visible(self, mode, **changes):
        config = dict(self.task.default_config, **{chaos_schema.SCHEME_KEY: mode}, **changes)
        return set(chaos_schema.visible_keys(self.task, config))

    def test_every_key_in_exactly_one_section(self):
        keys = chaos_schema.all_section_keys()
        self.assertEqual(len(keys), len(set(keys)), "有键在两个分段里")
        expected = set(self.task.default_config) - {"_enabled", chaos_schema.SCHEME_KEY}
        self.assertEqual(expected, set(keys))

    def test_scheme_constants_match_task(self):
        self.assertEqual(set(chaos_strategy.MODES), set(chaos_schema.SCHEMES))
        for keys in SCHEME_KEYS.values():
            for key in keys:
                self.assertIn(key, self.task.default_config)
        bound = chaos_schema.SCHEME_BOUND
        for key, schemes in bound.items():
            for mode in chaos_schema.SCHEMES:
                self.assertEqual(mode in schemes, key in SCHEME_KEYS[mode], f"{key} @ {mode}")
        self.assertEqual(scheme_sub_configs()["卡厄思玩法"], {m: list(k) for m, k in SCHEME_KEYS.items()})
        self.assertEqual(self.task.config_type["卡厄思玩法"]["sub_configs"], scheme_sub_configs()["卡厄思玩法"])

    def test_overridden_keys_hidden_in_each_scheme(self):
        """选了方案时被 config_overrides 覆盖的键不显示（改了也没用）。"""
        for mode in (X, E, T):
            overrides = chaos_strategy.config_overrides(mode, "罗丝薇瑟", {})
            shown = self.visible(mode)
            for key in overrides:
                if key in self.task.default_config:
                    self.assertNotIn(key, shown, f"{mode} 下「{key}」被覆盖却显示了")
            self.assertNotIn("刷存档主战员", shown)

    def test_legacy_shows_lists_hides_scheme_only(self):
        shown = self.visible(L)
        for key in ("移除卡牌列表", "闪光卡牌列表", "复制卡牌列表", "路线优先级", "刷空档", "刷存档主战员", "任务优先级"):
            self.assertIn(key, shown)
        for key in ("自动编队", "队友", "卡厄思地图", "刷存档难度", "调整零式升级", "目标预设", "章鱼哥速刷", "刷刻印",
                    "中立卡不拿", "装备优先给目标", "会触发闪光的装备不给目标", "刷空档闪光几张就重开"):
            self.assertNotIn(key, shown)

    def test_empty_save_keys(self):
        shown = self.visible(E)
        for key in ("刷空档闪光几张就重开", "刷空档目标顺序", "中立卡不拿", "装备优先给目标", "会触发闪光的装备不给目标",
                    "刷存档难度", "刷存档最低PT", "自动编队", "队友"):
            self.assertIn(key, shown)
        for key in ("章鱼哥速刷", "刷刻印", "刷存档开梦境模式", "目标预设", "探索度达到多少级后改刷目标卡组"):
            self.assertNotIn(key, shown)

    def test_target_sub_settings_chain(self):
        shown = self.visible(T, **{"章鱼哥速刷": False, "刷刻印": False})
        self.assertIn("章鱼哥速刷", shown)
        self.assertIn("刷刻印", shown)
        self.assertNotIn("章鱼哥速刷只认混沌之识", shown)
        self.assertNotIn("刻印法典地图", shown)
        self.assertNotIn("中立卡不拿", shown)
        self.assertIn("会触发闪光的装备不给目标", shown)
        shown = self.visible(T, **{"章鱼哥速刷": True, "刷刻印": True})
        self.assertIn("章鱼哥速刷只认混沌之识", shown)
        for key in chaos_schema.IMPRINT_SUB_KEYS:
            self.assertIn(key, shown)
        # 刷刻印走法典自己的地图和难度
        self.assertNotIn("卡厄思地图", shown)
        self.assertNotIn("刷存档难度", shown)
        # 刷刻印开着但方案不是目标卡组：子项不显示
        shown = self.visible(L, **{"刷刻印": True, "章鱼哥速刷": True})
        self.assertNotIn("刻印法典地图", shown)
        self.assertNotIn("章鱼哥速刷只认混沌之识", shown)

    def test_explore(self):
        shown = self.visible(X)
        self.assertIn("探索度达到多少级后改刷目标卡组", shown)
        self.assertIn("目标预设", shown)
        self.assertNotIn("刷存档难度", shown)
        self.assertNotIn("刷存档最低PT", shown)

    def test_team_needs_auto_formation(self):
        self.assertNotIn("队友", self.visible(T, **{"自动编队": False}))
        self.assertIn("队友", self.visible(T, **{"自动编队": True}))

    def test_parents_accumulate_values(self):
        rules = config_rules.parents(self.task)
        parent, values = rules["自动编队"]
        self.assertEqual("卡厄思玩法", parent)
        self.assertEqual({X, E, T}, set(values))
        self.assertTrue(config_rules.condition_met({"卡厄思玩法": E, "自动编队": True}, "队友", rules))
        self.assertFalse(config_rules.condition_met({"卡厄思玩法": L, "自动编队": True}, "队友", rules))


class TestApplyScheme(unittest.TestCase):
    def test_enter_empty_turns_on_three(self):
        config = _fixture("ChaosMode.json")
        config[chaos_schema.SCHEME_KEY] = T
        changes = chaos_schema.apply_scheme(config, E)
        self.assertEqual(E, config["卡厄思玩法"])
        self.assertTrue(config["中立卡不拿"] and config["装备优先给目标"] and config["会触发闪光的装备不给目标"])
        # 章鱼哥速刷是目标卡组的细分，切到空存要关掉（空存关梦境，章鱼哥本来就不会出现）
        self.assertFalse(config["章鱼哥速刷"])
        self.assertIn("章鱼哥速刷：关", changes)

    def test_leave_empty(self):
        config = _fixture("ChaosMode.json")
        chaos_schema.apply_scheme(config, E)
        chaos_schema.apply_scheme(config, T)
        self.assertFalse(config["中立卡不拿"])
        self.assertFalse(config["装备优先给目标"])
        self.assertTrue(config["会触发闪光的装备不给目标"])
        chaos_schema.apply_scheme(config, L)
        self.assertFalse(config["会触发闪光的装备不给目标"])
        self.assertEqual([], chaos_schema.hidden_but_active(config))

    def test_hidden_but_active_warns(self):
        config = _fixture("ChaosMode.json")
        config["卡厄思玩法"] = L      # 手改文件：原有逻辑下章鱼哥速刷还开着
        self.assertIn("章鱼哥速刷", chaos_schema.hidden_but_active(config))
        decided = chaos_schema.decided_by_scheme(config)
        self.assertTrue(any("章鱼哥速刷" in w for w in decided["warnings"]))

    def test_unknown_scheme_ignored(self):
        config = {"卡厄思玩法": T}
        self.assertEqual([], chaos_schema.apply_scheme(config, "章鱼哥速刷"))
        self.assertEqual(T, config["卡厄思玩法"])


class TestDecidedByScheme(unittest.TestCase):
    def setUp(self):
        self.deck = os.path.join(FIXTURES, "chaos_target_deck.json")
        self.config = _fixture("ChaosMode.json")

    def test_target_uses_cached_preset(self):
        decided = chaos_schema.decided_by_scheme(self.config, self.deck)
        rows = dict(decided["rows"])
        self.assertIn("缓存", decided["note"])
        self.assertNotEqual("开局时读预设", rows["闪光卡牌列表"])
        self.assertEqual("罗丝薇瑟", rows["刷存档主战员"])
        self.assertIn("第一层路线权重", rows)
        self.assertIn("小怪", rows["第一层路线权重"])

    def test_preset_mismatch_reads_at_start(self):
        self.config["目标预设"] = 3
        rows = dict(chaos_schema.decided_by_scheme(self.config, self.deck)["rows"])
        self.assertEqual("开局时读预设", rows["移除卡牌列表"])

    def test_empty_lists_member_cards(self):
        self.config["卡厄思玩法"] = E
        rows = dict(chaos_schema.decided_by_scheme(self.config, self.deck)["rows"])
        self.assertNotEqual("（空）", rows["移除卡牌列表"])
        self.assertEqual("关", rows["刷存档开梦境模式"])

    def test_legacy_has_no_rows(self):
        self.config["卡厄思玩法"] = L
        self.config["章鱼哥速刷"] = False
        self.config["会触发闪光的装备不给目标"] = False
        decided = chaos_schema.decided_by_scheme(self.config, self.deck)
        self.assertEqual([], decided["rows"])
        self.assertEqual([], decided["warnings"])


class TestConfigStorageCompat(unittest.TestCase):
    """新界面只加 config_type/config_description，旧的配置文件原样加载、不被改写。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="okkes_ui_cfg_")
        self.old_folder = Config.config_folder
        Config.config_folder = self.tmp

    def tearDown(self):
        Config.config_folder = self.old_folder
        shutil.rmtree(self.tmp, True)

    def _write(self, name, data):
        path = os.path.join(self.tmp, f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return path

    def test_live_chaos_config_loads_unchanged(self):
        task = _task(ChaosMode)
        data = _fixture("ChaosMode.json")
        path = self._write("ChaosMode", data)
        before = os.path.getmtime(path)
        time.sleep(0.05)
        config = Config("ChaosMode", task.default_config, folder=self.tmp)
        self.assertEqual(data, dict(config))
        self.assertEqual(before, os.path.getmtime(path), "加载时改写了文件")

    def test_scheme_switch_keeps_keys_and_types(self):
        task = _task(ChaosMode)
        data = _fixture("ChaosMode.json")
        for mode in chaos_schema.SCHEMES:
            chaos_schema.apply_scheme(data, mode)
            self.assertEqual(set(task.default_config), set(data))
            for key, default in task.default_config.items():
                self.assertIs(type(default), type(data[key]), key)

    def test_sortie_old_string_threshold_migrated(self):
        task = _task(SortieMode)
        data = _fixture("SortieMode.json")
        data[FLASH_HP_KEY] = "70"
        self._write("SortieMode", data)
        config_io.migrate_numeric_string_keys(task, [FLASH_HP_KEY])
        config = Config("SortieMode", task.default_config, folder=self.tmp)
        self.assertEqual(70, config[FLASH_HP_KEY])
        self.assertNotIn("丢弃卡牌优先级", config)
        self.assertEqual(data["出战主战员优先级"], config["出战主战员优先级"])
        self.assertIsInstance(task.default_config[FLASH_HP_KEY], int)

    def test_sortie_flash_key_unread_dead_key_removed(self):
        self.assertNotIn("丢弃卡牌优先级", _task(SortieMode).default_config)

    def test_import_accepts_old_numeric_string(self):
        import base64
        task = _task(SortieMode)
        self._write("SortieMode", dict(task.default_config))
        task.config = Config("SortieMode", task.default_config, folder=self.tmp)
        task.log_info = lambda *a, **k: None
        code = base64.b64encode(json.dumps({FLASH_HP_KEY: "55", "丢弃卡牌优先级": ["x"]}).encode()).decode()
        self.assertTrue(config_io._import_config_from_text(task, code))
        self.assertEqual(55, task.config[FLASH_HP_KEY])

    def test_ranges_and_descriptions(self):
        for cls in (ChaosMode, SortieMode):
            task = _task(cls)
            for key, value in task.default_config.items():
                if key.startswith("_") or key == "配置操作":
                    continue
                self.assertTrue(task.config_description.get(key), f"{cls.__name__}「{key}」没有说明")
                if isinstance(value, int) and not isinstance(value, bool):
                    the_type = config_rules.type_of(task, key)
                    self.assertTrue("min" in the_type or the_type.get("type") == "drop_down",
                                    f"{cls.__name__}「{key}」没有范围")

    def test_member_drop_down_from_game_db(self):
        task = _task(ChaosMode)
        options = task.config_type["目标主战员"]["options"]
        self.assertIn("罗丝薇瑟", options)
        self.assertIn("海德玛丽", options)
        self.assertEqual("tag_list", task.config_type["队友"]["widget"])
        import utils_imprint
        self.assertEqual(list(utils_imprint.MAP_NAMES), task.config_type["刻印法典地图"]["options"])


class TestChaosStats(unittest.TestCase):
    def setUp(self):
        self.runs = chaos_stats.read_runs(os.path.join(FIXTURES, "chaos_runs.jsonl"))

    def test_read_runs_skips_bad_lines(self):
        tmp = tempfile.mkdtemp(prefix="okkes_ui_runs_")
        try:
            path = os.path.join(tmp, "chaos_runs.jsonl")
            with open(os.path.join(FIXTURES, "chaos_runs.jsonl"), encoding="utf-8") as f:
                text = f.read()
            with open(path, "w", encoding="utf-8") as f:
                f.write(text + '{"time": "2026-10-28 12:00:00", "res')
            self.assertEqual(len(self.runs), len(chaos_stats.read_runs(path)))
        finally:
            shutil.rmtree(tmp, True)
        self.assertEqual([], chaos_stats.read_runs(os.path.join(FIXTURES, "missing.jsonl")))

    def test_session_and_summary(self):
        self.assertEqual(16, len(self.runs))
        session = chaos_stats.session_runs(self.runs)
        self.assertEqual(4, len(session))
        self.assertEqual("2026-10-28 11:06:05", session[0]["started"])
        summary = chaos_stats.summarize(session)
        self.assertEqual(3, summary.octopus)          # 一局整层没遇到，三局章鱼哥没掉混沌之识
        self.assertEqual(0, summary.chaos_core)
        self.assertEqual({"逃脱": 4}, summary.results)

    def test_octopus_field_wins(self):
        self.assertTrue(chaos_stats.octopus_seen({"octopus_seen": True}))
        self.assertFalse(chaos_stats.octopus_seen({"octopus_seen": False, "reason": "章鱼哥没掉混沌之识"}))
        self.assertTrue(chaos_stats.octopus_seen({"octopus_seen": False, "chaos_core": "混沌之识"}))
        self.assertFalse(chaos_stats.octopus_seen({"reason": "章鱼哥速刷：第一层整层没遇到章鱼哥"}))

    def test_filter_and_row(self):
        self.assertEqual(9, len(chaos_stats.filter_runs(self.runs, E)))
        self.assertEqual(3, len(chaos_stats.filter_runs(self.runs, "刷刻印")))
        self.assertEqual(16, len(chaos_stats.filter_runs(self.runs, "全部")))
        row = chaos_stats.row(self.runs[-1])
        self.assertEqual(len(chaos_stats.COLUMNS), len(row))
        self.assertEqual("10-28 11:48", row[0])
        self.assertEqual("8 分", row[1])
        self.assertEqual("灾难之像、符文代码", row[chaos_stats.COLUMNS.index("装备")])
        self.assertEqual("0/150", row[chaos_stats.COLUMNS.index("PT")])
        self.assertEqual("刷存档-目标卡组·刷刻印", chaos_stats.row(self.runs[0])[2])

    def test_live_run(self):
        path = os.path.join(FIXTURES, "chaos_run_state.json")
        live = chaos_stats.read_live_run(path, now=os.path.getmtime(path) + 60)
        self.assertEqual("20261028_114811_3a1c85", live.run_id)
        self.assertEqual(150, live.pt_cap)
        self.assertEqual(60, live.pt_used)        # 面板读到 60，读完以后账没再涨
        self.assertEqual(3, live.removes)
        self.assertEqual(0, live.copies)
        self.assertEqual(["闪光弹", "堕落之冠"], live.equipment)
        self.assertFalse(live.stale)
        self.assertTrue(chaos_stats.read_live_run(path, now=os.path.getmtime(path) + 4 * 3600).stale)
        self.assertIsNone(chaos_stats.read_live_run(os.path.join(FIXTURES, "missing.json")))

    def test_run_record_has_octopus_field(self):
        import run_state
        task = SimpleNamespace(node_status={"octopus_seen": True, "pass_final_boss_count": 0, "node_count": 3},
                               member_status={"equipment": {"names": ["", "", ""]}}, chaos_mode=T, config={})
        rec = run_state.summary(task, "逃脱")
        self.assertTrue(rec["octopus_seen"])


if __name__ == "__main__":
    unittest.main()
