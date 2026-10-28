# 卡厄思一局一个 RunState（复盘 docs/czn-okkes-postmortem-redesign.md 4.5，2026-10-27）：
# - 开局（点「进入」）/ 刷刻印进法典时新建，带 run_id；本局状态目前仍在 task.node_status / member_status 里，
#   由 utils.save_run_state 连同 run_id 一起落盘（dev_out/chaos_run_state.json），重启时 utils.restore_run_state 读回。
# - 结算（探险结果页）时把本局结果追加到 dev_out/chaos_runs.jsonl，并删掉落盘，结束的局不会再被读回新局
#   （2026-10-27 15:54 实录：上一局的落盘状态被读回带进了新局）。
# - 内存里已经有一局时，run_id 对不上的落盘不读。
import json
import os
import time
import uuid

from dev_paths import dev_out

RUNS_FILE = dev_out("chaos_runs.jsonl")


class RunState:
    def __init__(self, run_id=None, source="", started=None, finished=False):
        self.run_id = run_id or f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        self.source = source
        self.started = started or time.strftime("%Y-%m-%d %H:%M:%S")
        self.finished = finished

    def to_dict(self):
        return {"run_id": self.run_id, "source": self.source, "started": self.started, "finished": self.finished}

    @classmethod
    def from_dict(cls, data):
        return cls(data.get("run_id"), data.get("source", ""), data.get("started"), bool(data.get("finished")))


def current(task):
    rs = getattr(task, "run_state", None)
    return rs if isinstance(rs, RunState) else None


def _has_progress(task):
    ns = getattr(task, "node_status", None) or {}
    return bool(ns.get("node_count") or ns.get("pass_final_boss_count"))


def _is_chaos(task):
    """只有卡厄思模式（ChaosMode，有 chaos_mode）按局记账；出击模式共用 handle_enter / 探险结果页，不建 RunState。"""
    return hasattr(task, "chaos_mode")


def begin(task, source):
    """新的一局：上一局没记结果且有进度就先补记一条「未结算」，再清本局状态（reset_mission_status）、新建 RunState 并立刻落盘
    （立刻落盘是为了覆盖掉上一局的文件：之前要等读到 PT 上限才落盘，这期间重启会读回上一局）。"""
    import utils
    if not _is_chaos(task):
        utils.reset_mission_status(task)
        return None
    old = current(task)
    if old is not None and not old.finished and _has_progress(task):
        finish(task, "未结算", f"开始新一局（{source}）时上一局还没记结果")
    utils.reset_mission_status(task)
    rs = RunState(source=source)
    task.run_state = rs
    task.log_info(f"新的一局（{source}），run_id={rs.run_id}")
    utils.save_run_state(task)
    return rs


def note_escape(task, reason):
    """要逃脱时记下原因，结算时写进本局记录。"""
    ns = getattr(task, "node_status", None)
    if isinstance(ns, dict) and reason:
        ns["escape_reason"] = str(reason)


def summary(task, result, reason=""):
    import utils
    import utils_imprint
    ns = getattr(task, "node_status", None) or {}
    eq = (getattr(task, "member_status", None) or {}).get("equipment") or {}
    rs = current(task)
    names = (list(eq.get("names") or []) + ["", "", ""])[:3]
    rec = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "run_id": rs.run_id if rs else None,
           "source": rs.source if rs else "", "started": rs.started if rs else None,
           "result": result, "reason": reason or ns.get("escape_reason", ""),
           "layers": ns.get("pass_final_boss_count", 0), "nodes": ns.get("node_count", 0),
           "equipment": names, "imprints": (list(eq.get("imprints") or []) + ["", "", ""])[:3],
           "imprint_peak": ns.get("imprint_peak", 0), "chaos_core": ns.get("chaos_core_got") or "",
           "mode": getattr(task, "chaos_mode", ""), "imprint_mode": utils_imprint.enabled(task)}
    if rec["imprint_mode"]:
        try:
            rec["target_imprints"] = utils_imprint.target_imprint_count(task)
            rec["target_equipment"] = target_equipment_count(task)
            rec["goal_reached"] = goal_reached(task)
        except Exception:  # noqa: BLE001
            pass
    rec["pt_cap"] = getattr(task, "chaos_pt_cap", None)
    rec["pt_used"] = utils._pt_used(task) if ns else None
    return rec


def finish(task, result, reason=""):
    """本局结束：结果追加到 chaos_runs.jsonl，删掉局内落盘。同一局只记一次。"""
    import utils
    rs = current(task)
    if (rs is not None and rs.finished) or not _is_chaos(task):
        return None
    rec = summary(task, result, reason)
    try:
        os.makedirs(os.path.dirname(RUNS_FILE) or ".", exist_ok=True)
        with open(RUNS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception as e:  # noqa: BLE001
        task.log_info(f"本局记录写入失败: {e}")
    if rs is None:
        rs = RunState(source="未知")
        task.run_state = rs
    rs.finished = True
    utils.clear_run_state(task)
    task.log_info(f"本局结束（{result}{'：' + rec['reason'] if rec['reason'] else ''}），第 {rec['layers']} 层，"
                  f"装备 {rec['equipment']}，刻印 {rec['imprints']}，混沌之识 {rec['chaos_core'] or '无'}，记入 {RUNS_FILE}")
    return rec


def read_runs(path=None):
    try:
        with open(path or RUNS_FILE, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except (OSError, ValueError):
        return []


# ------------------------- 刷刻印达成即停 -------------------------
# 用户 2026-10-27 定的达成条件：至少 2 个目标装备（1 号位混沌之识算目标装备）+ 3 个目标刻印。
# 另一个分支在 utils_imprint 里实现 goal_reached(task)；有它就用它，这里只是同名签名的占位（合并时以那边为准）。

GOAL_EQUIPMENT = 2
GOAL_IMPRINTS = 3


def target_equipment_count(task):
    import utils
    import utils_imprint
    names = (list(((getattr(task, "member_status", None) or {}).get("equipment") or {}).get("names") or [])
             + ["", "", ""])[:3]
    n = 0
    for slot, name in enumerate(names):
        if not name:
            continue
        if slot == 0 and utils_imprint.is_top(name):
            n += 1
            continue
        matched, _ = utils._match_equipment_name(name, utils._equipment_priority(task, slot))
        n += matched is not None
    return n


def _goal_reached_placeholder(task):
    import utils_imprint
    return (target_equipment_count(task) >= GOAL_EQUIPMENT
            and utils_imprint.target_imprint_count(task) >= GOAL_IMPRINTS)


def goal_reached(task):
    import utils_imprint
    impl = getattr(utils_imprint, "goal_reached", None)
    return bool(impl(task) if callable(impl) else _goal_reached_placeholder(task))


GOAL_STOP_ATTR = "imprint_goal_stop"


def check_goal_on_success(task):
    """结算（探险结果成功、已存档）时调用：刷刻印达成目标就记下，回到局外（零式系统/卡厄思初始页）停任务，
    不再进法典合成/刷新消耗资源。要在 reset_mission_status 之前调（账本还在）。"""
    import utils_imprint
    if not utils_imprint.enabled(task) or not goal_reached(task):
        return False
    eq = (getattr(task, "member_status", None) or {}).get("equipment") or {}
    msg = (f"刷刻印达成目标：目标装备 {target_equipment_count(task)} 个、目标刻印 {utils_imprint.target_imprint_count(task)} 个"
           f"（装备 {eq.get('names')}，刻印 {eq.get('imprints')}），回到局外就停，不再进法典")
    setattr(task, GOAL_STOP_ATTR, msg)
    task.log_info(msg)
    return True


def handle_goal_stop(task):
    """达成目标后回到局外页面（卡厄思/零式系统初始页、选择法典页）就停任务。"""
    msg = getattr(task, GOAL_STOP_ATTR, None)
    if not msg:
        return False
    import utils_chaos
    import utils_imprint
    if not (utils_chaos._at_chaos_initial_page(task)
            or (utils_imprint._title(task, r"零式系统") and utils_imprint.find_text(task, r"^选择法典$"))):
        return False
    setattr(task, GOAL_STOP_ATTR, None)
    task.log_info(f"{msg}；已回到局外，停止任务")
    task.disable()
    return True
