# 刷刻印：账本和游戏对账（复盘 docs/czn-okkes-postmortem-redesign.md 4.4，2026-10-27）。
# 脚本记的装备/刻印账（member_status["equipment"]、node_status 的 imprint_peak / chaos_core_got）一错，逃脱判断就跟着错
# （15:48 装备页淡入读成空槽，混沌之识 + 2 个目标刻印那局被逃脱）。所以在不可逆的逃脱前、层结束、第二层首领前，
# 从路线页打开主战员面板，逐个点刷存档主战员的 3 个装备格读名字和刻印全文，对不上以游戏为准：
# - 游戏里的目标刻印 / 混沌之识比账本多：修正账本，这一层不逃脱，记日志、追踪留底；
# - 比账本少：只记日志、追踪留底，不改账（面板读法未经实机核对，读漏改账会误逃脱）。
# 已知画面（17:59 实机）：路线页点 (0.30, 0.075) 开面板；装备格中心 x = 列左边 + 0.047 + 0.0805×槽位、y≈0.90；
# 点格子弹出详情（名字 + 属性 + 刻印全文）；ESC 会把详情和面板一起关掉，所以每个格子都要重新开面板。
# 路线页右上 (0.959, 0.051) 是「逃脱」按钮，面板的 X 也在那里——面板没开时绝不点那里。
import re

import chaos_trace
import utils
import utils_imprint

LEDGER_KEY = "刷刻印对账"
PANEL_OPEN_POS = (0.30, 0.075)
PANEL_CLOSE_POS = (0.959, 0.050)
PANEL_MARK = "模糊的记忆"
SLOT_Y = 0.900
DETAIL_WAIT = 1.5


def enabled(task):
    if not utils_imprint.enabled(task):
        return False
    value = (getattr(task, "config", None) or {}).get(LEDGER_KEY)
    return value is not False


def slot_pos(col, slot):
    x0, _ = utils.MEMBER_PANEL_COLUMNS[col]
    return x0 + 0.047 + 0.0805 * slot, SLOT_Y


def _read(task):
    task.next_frame()
    return utils._simplify_texts(task.ocr())


def _panel_open(texts):
    return any(PANEL_MARK in b.name for b in texts)


def _target_col(task, texts):
    target = str(utils._get_config_value(task, "刷存档主战员", "") or "").strip()
    if not target:
        return None
    cols = utils.parse_member_panel(texts, task.width, task.height)
    return next((i for i, c in enumerate(cols) if c.get("name") and (target in c["name"] or c["name"] in target)), None)


def open_panel(task):
    """打开主战员面板，返回面板文字；打不开返回 None（不点别的地方）。"""
    texts = _read(task)
    if not _panel_open(texts):
        utils._move_and_click(task, *PANEL_OPEN_POS)
        task.sleep(1.5)
        texts = _read(task)
    if not _panel_open(texts):
        task.log_info("对账：主战员面板没打开，这次不对账")
        return None
    return texts


def close_panel(task):
    """ESC 关详情和面板；只有 ESC 后还认得出面板时才点右上角 X（面板没开时那里是逃脱按钮）。"""
    task.send_key("esc")
    task.sleep(1)
    texts = _read(task)
    if _panel_open(texts):
        task.log_info("对账：ESC 后主战员面板还开着，点右上角 X 关掉")
        utils._move_and_click(task, *PANEL_CLOSE_POS)
        task.sleep(1)


def _equipment_name(texts):
    import game_db
    try:
        db = game_db.get_db()
    except Exception:  # noqa: BLE001
        return ""
    for b in sorted(texts, key=lambda b: (b.y, b.x)):
        text = b.name.strip()
        if not 2 <= len(text) <= 14 or re.search(r"\d", text):
            continue
        eq = db.find_equipment(text)
        if eq:
            return eq["name"]
    return ""


def parse_detail(task, texts):
    """装备详情弹窗的文字（已去掉面板本来就有的字）→ 名字、是否目标刻印、是否混沌之识。"""
    joined = "".join(b.name for b in sorted(texts, key=lambda b: (b.y, b.x)))
    name = _equipment_name(texts)
    imprint = utils_imprint.TARGET if utils_imprint.is_target_imprint(task, joined) else ""
    core = utils_imprint.is_top(name) or utils_imprint.is_top(joined)
    return {"name": name, "imprint": imprint, "core": bool(core), "read": bool(name), "text": joined[:200]}


def read_slot(task, slot):
    """开面板 → 点刷存档主战员的第 slot 个装备格 → 读详情 → ESC。返回 parse_detail 的结果；面板没开/没找到人返回 None。"""
    texts = open_panel(task)
    if texts is None:
        return None
    col = _target_col(task, texts)
    if col is None:
        task.log_info("对账：主战员面板里没找到刷存档主战员")
        close_panel(task)
        return None
    before = {b.name for b in texts}
    x, y = slot_pos(col, slot)
    utils._move_and_click(task, x, y)
    task.sleep(DETAIL_WAIT)
    after = _read(task)
    detail = parse_detail(task, [b for b in after if b.name not in before])
    chaos_trace.step(task, "ledger", f"对账-{slot + 1}号装备详情", getattr(task, "frame", None), **detail)
    if detail["text"] or _panel_open(after):
        close_panel(task)          # 详情或面板开着才按 ESC：都没开时在路线页按 ESC 会开菜单
    return detail


def read_game_equipment(task):
    """逐个读 3 个装备格。账本里有目标刻印、第一次没读到时再读一次（详情文字可能还没出全），两次都没有才算没有。"""
    imprints = utils_imprint.slot_imprints(task)
    game = []
    for slot in range(3):
        detail = read_slot(task, slot)
        if detail is None:
            break
        if imprints[slot] == utils_imprint.TARGET and detail["read"] and detail["imprint"] != utils_imprint.TARGET:
            again = read_slot(task, slot)
            if again is not None and again["imprint"] == utils_imprint.TARGET:
                detail = again
        game.append(detail)
    return game


def compare_and_fix(task, game):
    """拿游戏里读到的（只看读到名字的格子）对账本，以游戏为准改账。返回 {more, less, renamed}。"""
    ns = task.node_status
    eq = utils._equipment_state(task)
    names = eq.setdefault("names", ["", "", ""])
    imprints = utils_imprint.slot_imprints(task)
    more, less, renamed = [], [], []
    for slot, g in enumerate(game):
        if not g or not g.get("read"):
            continue
        if g["imprint"] == utils_imprint.TARGET and imprints[slot] != utils_imprint.TARGET:
            more.append(f"{slot + 1}号位目标刻印")
            imprints[slot] = utils_imprint.TARGET
        elif g["imprint"] != utils_imprint.TARGET and imprints[slot] == utils_imprint.TARGET:
            # 比账本少只记录不改账：面板详情的读法还没实机核对，读漏了改账会导致误逃脱（往「不逃」那边错才安全）
            less.append(f"{slot + 1}号位目标刻印")
        if g["name"] and g["name"] != names[slot]:
            renamed.append(f"{slot + 1}号位「{names[slot] or '空'}」→「{g['name']}」")
            names[slot] = g["name"]
        if g["core"] and not ns.get("chaos_core_got"):
            more.append(f"{slot + 1}号位混沌之识")
            ns["chaos_core_got"] = g["name"] or "混沌之识"
    # 混沌之识不在身上不清「拿到过」：目标刻印优先于混沌之识（用户 2026-10-27 19:xx），它可能被带刻印的装备正常换掉，
    # 拿到过就不逃脱的规则照旧
    count = sum(1 for v in imprints if v == utils_imprint.TARGET)
    ns["imprint_peak"] = max(count, ns.get("imprint_peak", 0))
    return {"more": more, "less": less, "renamed": renamed, "read": sum(1 for g in game if g and g.get("read")),
            "imprints": count}


def reconcile(task, when):
    """对一次账（同一层同一个节点只对一次，结果记在 node_status 里随局内状态落盘）。返回结果 dict。"""
    ns = task.node_status
    key = f"{ns.get('pass_final_boss_count', 0)}-{ns.get('node_count', 0)}"
    checks = ns.setdefault("ledger_checks", {})
    if key in checks:
        return checks[key]
    eq = utils._equipment_state(task)
    ledger = {"names": list(eq.get("names") or []), "imprints": list(utils_imprint.slot_imprints(task)),
              "peak": ns.get("imprint_peak", 0), "chaos_core": ns.get("chaos_core_got")}
    try:
        game = read_game_equipment(task)
    except Exception as e:  # noqa: BLE001  对账出错不能让任务停掉，当没读到
        task.log_info(f"对账（{when}）读装备出错：{e}")
        game = []
    result = compare_and_fix(task, game) if game else {"more": [], "less": [], "renamed": [], "read": 0}
    result["when"] = when
    checks[key] = result
    if not result["read"]:
        task.log_info(f"对账（{when}）：没读到游戏里的装备，账本不变")
    elif result["more"] or result["less"] or result["renamed"]:
        task.log_info(f"对账（{when}）：游戏和账本对不上——比账本多 {result['more'] or '无'}（按游戏补上），"
                      f"比账本少 {result['less'] or '无'}（只记录不改账），改名 {result['renamed'] or '无'}；"
                      f"账本原来 {ledger}，现在装备 {eq.get('names')}、刻印 {utils_imprint.slot_imprints(task)}")
    else:
        task.log_info(f"对账（{when}）：游戏和账本一致（读到 {result['read']} 个装备格，目标刻印 {result['imprints']} 个）")
    chaos_trace.step(task, "ledger", f"对账-{when}", getattr(task, "frame", None), ledger=ledger, game=game, **result)
    utils.save_run_state(task)
    return result


def escape_allowed(task, reason):
    """不可逆的逃脱前对一次账：游戏比账本多（目标刻印/混沌之识）→ 修正账本，这一层不逃脱。返回能不能逃脱。"""
    if not enabled(task):
        return True
    ns = task.node_status
    layer = ns.get("pass_final_boss_count", 0)
    result = reconcile(task, "逃脱前")
    if result.get("more"):
        ns["escape_veto"] = layer
    if ns.get("escape_veto") == layer:
        if ns.get("escape_veto_logged") != f"{layer}-{ns.get('node_count', 0)}":
            ns["escape_veto_logged"] = f"{layer}-{ns.get('node_count', 0)}"
            task.log_info(f"对账：游戏里的目标刻印/混沌之识比账本多（{result.get('more') or '这一层之前对账发现'}），"
                          f"账本已修正，这一层不逃脱（原本要逃脱：{reason}）")
            chaos_trace.step(task, "ledger", "对账拦下逃脱", getattr(task, "frame", None), reason=reason, **result)
        return False
    return True


def checkpoint(task):
    """路线页上的对账时机：层结束（首领结算后第一次回到路线页）、第二层首领前。返回这次是否对了账。"""
    ns = task.node_status
    layer = ns.get("pass_final_boss_count", 0)
    if layer >= 1 and ns.get("ledger_layer_end") != layer:
        ns["ledger_layer_end"] = layer
        reconcile(task, "层结束")
        return True
    if layer >= 1 and utils_imprint._boss_next(ns) and ns.get("ledger_boss") != layer:
        ns["ledger_boss"] = layer
        reconcile(task, "首领前")
        return True
    return False


def boss_checkpoint(task):
    """没有整层路线计划、路线页认不出节点（当成首领）时的首领前对账。返回这次是否对了账。"""
    if not enabled(task):
        return False
    ns = task.node_status
    layer = ns.get("pass_final_boss_count", 0)
    if layer < 1 or ns.get("ledger_boss") == layer:
        return False
    ns["ledger_boss"] = layer
    reconcile(task, "首领前")
    return True


def handle_route_ledger(task):
    """页面处理：刷刻印在路线页按时机对账（要先于逃脱判断和路线选择）。"""
    if not enabled(task) or not isinstance(getattr(task, "node_status", None), dict):
        return False
    if not utils.is_route_selection_page(task) or utils.route_click_settling(task):
        return False
    return checkpoint(task)
