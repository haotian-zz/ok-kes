"""首页卡厄思卡片和运行记录页读的数据（不依赖 Qt，方便单测；只读，不写任何文件）。

- dev_out/chaos_run_state.json：当前这一局的落盘（ok_tasks/utils.save_run_state），结算时删掉。
- dev_out/chaos_runs.jsonl：每局结束追加一行（ok_tasks/run_state.finish）。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime

COPY_CAP = 3
REMOVE_CAP = 5
# 和 utils.RUN_STATE_MAX_AGE 一致：3 小时以上的落盘任务自己也不认
RUN_STATE_MAX_AGE = 3 * 3600
# 两局之间隔这么久以上就算新的一轮
SESSION_GAP = 30 * 60
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def dev_out(*parts) -> str:
    try:
        from dev_paths import dev_out as _dev_out

        return _dev_out(*parts)
    except Exception:
        return os.path.join(os.environ.get("OKKES_DEV_OUT") or "dev_out", *parts)


def run_state_path() -> str:
    return dev_out("chaos_run_state.json")


def runs_path() -> str:
    return dev_out("chaos_runs.jsonl")


# ---------------------------------------------------------------- 当前这一局


@dataclass
class LiveRun:
    run_id: str = ""
    started: str = ""
    pt_used: int | None = None
    pt_cap: int | None = None
    copies: int = 0
    removes: int = 0
    layers: int = 0
    nodes: int = 0
    octopus_seen: bool = False
    chaos_core: str = ""
    target_equipment: str = ""
    equipment: list = field(default_factory=list)
    stale: bool = False  # 文件太旧，任务也不会再读它


def _pt_used(ns: dict) -> int:
    """和 utils._pt_used 同一算法：读过游戏面板就以面板为准，再加读完后记的增量。"""
    try:
        import utils

        raw = utils._pt_ledger(ns)
    except Exception:
        raw = (20 * ns.get("removed_card_count", 0) + 40 * max(0, ns.get("copy_count", 0) - 2)
               + 20 * ns.get("neutral_card_count", 0) + 20 * ns.get("god_spark_count", 0))
    if ns.get("pt_game") is None:
        return raw
    return ns["pt_game"] + max(0, raw - ns.get("pt_game_ledger", raw))


def read_live_run(path: str | None = None, now: float | None = None) -> LiveRun | None:
    path = path or run_state_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        age = (now or time.time()) - os.path.getmtime(path)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    ns = data.get("ns") if isinstance(data.get("ns"), dict) else {}
    run = data.get("run") if isinstance(data.get("run"), dict) else {}
    equipment = (data.get("equipment") or {}).get("names") if isinstance(data.get("equipment"), dict) else None
    return LiveRun(
        run_id=str(run.get("run_id") or ""),
        started=str(run.get("started") or ""),
        pt_used=_pt_used(ns),
        pt_cap=data.get("cap"),
        copies=int(ns.get("copy_count", 0) or 0),
        # 移除次数：面板读到的（空存）和脚本记的取大的
        removes=max(int(ns.get("removed_card_count", 0) or 0), int(ns.get("empty_panel_removed", 0) or 0)),
        layers=int(ns.get("pass_final_boss_count", 0) or 0),
        nodes=int(ns.get("node_count", 0) or 0),
        octopus_seen=bool(ns.get("octopus_seen")),
        chaos_core=str(ns.get("chaos_core_got") or ""),
        target_equipment=str(ns.get("target_equip_got") or ""),
        equipment=[n for n in (equipment or []) if n],
        stale=age > RUN_STATE_MAX_AGE,
    )


# ---------------------------------------------------------------- 每局记录


def read_runs(path: str | None = None) -> list[dict]:
    """一行一局；坏行跳过（任务写到一半被关掉时最后一行可能不完整）。"""
    runs = []
    try:
        with open(path or runs_path(), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict):
                    runs.append(record)
    except OSError:
        return []
    return runs


def _ts(text) -> float | None:
    try:
        return datetime.strptime(str(text), TIME_FORMAT).timestamp()
    except (TypeError, ValueError):
        return None


def octopus_seen(record: dict) -> bool:
    """这一局遇没遇到章鱼哥。新记录有 octopus_seen；旧记录看结果：掉了混沌之识，或逃脱原因说遇到了。"""
    if "octopus_seen" in record:
        return bool(record.get("octopus_seen")) or bool(record.get("chaos_core"))
    if record.get("chaos_core"):
        return True
    reason = str(record.get("reason") or "")
    return "章鱼哥没掉" in reason or "遇到了章鱼哥" in reason


def session_runs(runs: list[dict], gap: float = SESSION_GAP) -> list[dict]:
    """最近这一轮：从最后一局往前，上一局结束到下一局开始不超过 ``gap`` 秒、方案相同的连续几局。"""
    if not runs:
        return []
    session = [runs[-1]]
    for record in reversed(runs[:-1]):
        newer = session[0]
        start = _ts(newer.get("started")) or _ts(newer.get("time"))
        end = _ts(record.get("time"))
        if start is None or end is None or start - end > gap or record.get("mode") != newer.get("mode"):
            break
        session.insert(0, record)
    return session


@dataclass
class RunSummary:
    runs: int = 0
    octopus: int = 0
    chaos_core: int = 0
    results: dict = field(default_factory=dict)
    first: str = ""
    last: str = ""


def summarize(runs: list[dict]) -> RunSummary:
    summary = RunSummary(runs=len(runs))
    for record in runs:
        summary.octopus += octopus_seen(record)
        summary.chaos_core += bool(record.get("chaos_core"))
        result = str(record.get("result") or "?")
        summary.results[result] = summary.results.get(result, 0) + 1
    if runs:
        summary.first = str(runs[0].get("started") or runs[0].get("time") or "")
        summary.last = str(runs[-1].get("time") or "")
    return summary


def scheme_label(record: dict) -> str:
    """表格里的方案：玩法 + 刷刻印标记。"""
    mode = str(record.get("mode") or "原有逻辑")
    return f"{mode}·刷刻印" if record.get("imprint_mode") else mode


def filter_runs(runs: list[dict], scheme: str | None) -> list[dict]:
    """按方案筛（None / "全部" 不筛）；「刷刻印」单独筛刷刻印的局。"""
    if not scheme or scheme == "全部":
        return list(runs)
    if scheme == "刷刻印":
        return [record for record in runs if record.get("imprint_mode")]
    return [record for record in runs if (record.get("mode") or "原有逻辑") == scheme]


def _short_time(text) -> str:
    ts = _ts(text)
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M") if ts else str(text or "")


def _duration(record: dict) -> str:
    start, end = _ts(record.get("started")), _ts(record.get("time"))
    if start is None or end is None or end < start:
        return ""
    minutes = round((end - start) / 60)
    return f"{minutes} 分"


def row(record: dict) -> list[str]:
    """运行记录表的一行，顺序同 COLUMNS。"""
    equipment = [n for n in (record.get("equipment") or []) if n]
    imprints = [n for n in (record.get("imprints") or []) if n]
    pt = ""
    if record.get("pt_cap"):
        pt = f"{record.get('pt_used') if record.get('pt_used') is not None else '?'}/{record['pt_cap']}"
    return [
        _short_time(record.get("time")),
        _duration(record),
        scheme_label(record),
        str(record.get("result") or ""),
        str(record.get("layers", "")),
        pt,
        str(record.get("chaos_core") or ""),
        "、".join(imprints),
        "、".join(equipment),
        str(record.get("reason") or ""),
    ]


# 原因最长，放最后占满剩下的宽度
COLUMNS = ["结束", "用时", "方案", "结果", "层", "PT", "混沌之识", "刻印", "装备", "原因"]
