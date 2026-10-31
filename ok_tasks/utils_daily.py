"""日常任务公共工具：OCR 刷新、按文字/模板点击、回主页。

模板图放在 ok_tasks/assets/daily/，按 1280x720 截取，运行时按当前分辨率缩放后匹配。
本文件只放函数，不定义任务类（ok_tasks 下的 .py 会被框架当成任务文件扫描）。
"""

import os
import re
import time

import cv2
import numpy as np
from ok import BaseTask

from utils import _simplify_texts

DAILY_ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets", "daily")
TEMPLATE_BASE_WIDTH = 1280

# 主页右侧入口（UI 未隐藏时能 OCR 到）
HOME_KEYWORDS = ("出击", "模拟", "卡厄思", "方舟城市", "主战员", "营救")
# 主页闲置一段时间会隐藏 UI，此时点空白处唤醒（不会触发任何入口）
HOME_WAKE_POINT = (0.45, 0.42)
# 看板立绘会换，点到立绘身上只触发互动、不出 UI（2026-10-27 22:27 实录：立绘的腿盖住 (0.45, 0.42)，点 30 次都没唤醒），
# UI 隐藏时几个位置轮流点；左侧两个点在立绘外的背景上
HOME_WAKE_POINTS = (HOME_WAKE_POINT, (0.12, 0.45), (0.10, 0.20))
HOME_ICON_REGION = (0.84, 0.0, 0.96, 0.13)
BACK_ICON_REGION = (0.0, 0.0, 0.08, 0.12)
PAY_POPUP_CLOSE = (0.937, 0.05)

# 主页右上角 ≡ 菜单（第一次点击可能只是唤醒隐藏的 UI）
MENU_POINT = (0.959, 0.05)
MENU_MAIL_POINT = (0.961, 0.285)
MENU_SETTINGS_POINT = (0.961, 0.835)
# F3「日常」窗口左侧第 2 个页签（日历图标）=「每日任务」
DAILY_TASK_TAB = (0.057, 0.229)
# F2「阿基亚农补给」左侧页签：第 1 个奖励、第 2 个任务
SUPPLY_REWARD_TAB = (0.053, 0.15)
SUPPLY_TASK_TAB = (0.053, 0.255)
# 设置 → 左侧「键盘」页签
SETTINGS_KEYBOARD_TAB = (0.048, 0.327)
# 庭院咖啡店菜单板：堂食（立即 +120 以太）、外带（以太补充货币 +1，最多 4 个）、点单按钮
COFFEE_DINE_IN = (0.627, 0.45)
COFFEE_TAKEOUT = (0.846, 0.45)
COFFEE_ORDER_BOARD = (0.737, 0.875)
COFFEE_DINE_IN_ETHER = 120
# 模拟 → 战斗训练 → 配置队伍：战斗效率 -/+、进入；每次消耗 20×效率 以太
TRAINING_EFF_MINUS = (0.695, 0.832)
TRAINING_EFF_PLUS = (0.969, 0.832)
TRAINING_ENTER = (0.72, 0.913)
TRAINING_COST_PER_EFF = 20
# 战斗页右上角自动战斗按钮（关闭时按钮中心是纯白，开启后变成 X 图标）
BATTLE_AUTO_POINT = (0.880, 0.056)

_template_cache = {}


# ------------------------- OCR / 点击 -------------------------

def refresh(task: BaseTask, frame=True):
    """取最新一帧并 OCR（繁体转简体），结果存到 task.all_texts。"""
    if frame:
        task.next_frame()
    task.all_texts = _simplify_texts(task.ocr())
    return task.all_texts


def rel_center(task: BaseTask, box):
    return (box.x + box.width / 2) / task.width, (box.y + box.height / 2) / task.height


def in_region(task: BaseTask, box, region):
    if not region:
        return True
    cx, cy = rel_center(task, box)
    x1, y1, x2, y2 = region
    return x1 <= cx <= x2 and y1 <= cy <= y2


def find_text(task: BaseTask, pattern, region=None, texts=None):
    """在当前 OCR 结果里按正则找第一个匹配（可限定相对区域 x1,y1,x2,y2）。"""
    for box in texts if texts is not None else (getattr(task, "all_texts", None) or []):
        if re.search(pattern, box.name) and in_region(task, box, region):
            return box
    return None


def has_text(task: BaseTask, pattern, region=None):
    return find_text(task, pattern, region) is not None


def click_rel(task: BaseTask, x, y, after=1.0, reason=""):
    """先移动再点击（游戏对 PostMessage 点击需要先有鼠标移动）。"""
    if reason:
        task.log_info(f"{reason}：点击 ({x:.3f}, {y:.3f})")
    task.move_relative(x, y)
    task.sleep(0.4)
    task.click(x, y)
    task.sleep(after)


def click_text_box(task: BaseTask, box, after=1.0, reason=""):
    x, y = rel_center(task, box)
    click_rel(task, x, y, after=after, reason=reason or f"点击「{box.name}」")


def wait_text(task: BaseTask, pattern, region=None, timeout=10.0, interval=0.5):
    """等待文字出现，返回 box 或 None。"""
    end = time.time() + timeout
    while True:
        refresh(task)
        box = find_text(task, pattern, region)
        if box or time.time() > end:
            return box
        task.sleep(interval)


def click_text(task: BaseTask, pattern, region=None, timeout=10.0, after=1.0):
    box = wait_text(task, pattern, region, timeout)
    if box:
        click_text_box(task, box, after=after)
        return True
    task.log_info(f"未找到文字「{pattern}」")
    return False


# ------------------------- 模板匹配 -------------------------

def _load_template(name):
    if name not in _template_cache:
        path = os.path.join(DAILY_ASSET_DIR, f"{name}.png")
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise FileNotFoundError(path)
        _template_cache[name] = img
    return _template_cache[name]


def match_template(task: BaseTask, name, region=(0, 0, 1, 1), threshold=0.8):
    """在当前帧的相对区域里匹配模板，返回 (score, (rel_x, rel_y))；低于阈值返回 (score, None)。"""
    frame = task.frame
    if frame is None:
        return 0.0, None
    h, w = frame.shape[:2]
    template = _load_template(name)
    scale = w / TEMPLATE_BASE_WIDTH
    if abs(scale - 1) > 0.01:
        template = cv2.resize(template, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    x1, y1, x2, y2 = int(region[0] * w), int(region[1] * h), int(region[2] * w), int(region[3] * h)
    crop = frame[y1:y2, x1:x2]
    th, tw = template.shape[:2]
    if crop.shape[0] < th or crop.shape[1] < tw:
        return 0.0, None
    result = cv2.matchTemplate(crop, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(result)
    if score < threshold:
        return float(score), None
    return float(score), ((x1 + loc[0] + tw / 2) / w, (y1 + loc[1] + th / 2) / h)


# ------------------------- 主页 -------------------------

def is_home(task: BaseTask):
    """主页（UI 显示中）：右侧入口文字至少命中 3 个。"""
    hits = {b.name for b in task.all_texts or [] if b.name in HOME_KEYWORDS and rel_center(task, b)[0] > 0.8}
    return len(hits) >= 3


def is_black(task: BaseTask, threshold=8):
    """整帧几乎全黑（加载/切场景）。"""
    frame = task.frame
    return frame is not None and float(frame.mean()) < threshold


def go_home(task: BaseTask, timeout=60.0):
    """从任意页面回到主页：关提示 → 点右上角主页按钮 → 返回键兜底；主页 UI 隐藏时点空白唤醒。"""
    end = time.time() + timeout
    esc_count = 0
    wakes = 0
    while time.time() < end:
        refresh(task)
        if is_home(task):
            return True
        if has_text(task, r"仍然保留"):
            # 登录时「此前进行的<玩法>相关信息仍然保留着。是否继续？」（2026-10-29 实录：哀嚎螺旋塔 131-135区域 1/5，
            # 日常每项都按 ESC 失败）。用户定的：哀嚎螺旋塔点逃脱；别的玩法（卡厄思局里可能有目标卡组）不放弃，停下交给人
            box = find_text(task, r"^逃脱$")
            if has_text(task, r"哀嚎螺旋塔") and box:
                click_text_box(task, box, after=3, reason="未完成的哀嚎螺旋塔：点「逃脱」放弃")
                continue
            task.log_info("登录弹出未完成的玩法（不是哀嚎螺旋塔），不自动放弃，停止", notify=True)
            return False
        if has_text(task, r"卡厄思信息") or has_text(task, r"^逃脱$", region=(0.8, 0.85, 1, 1)):
            task.log_info("当前在出击/卡厄思局内，局内没有回主页入口（只能逃脱），不自动处理")
            return False
        box = find_text(task, r"点击(屏幕|画面)|^点击(开始|以)")
        if box:
            click_text_box(task, box, after=1.5, reason="关闭提示")
            continue
        if has_text(task, r"退出游戏|结束游戏"):
            if click_text(task, r"^取消$", timeout=2):
                continue
        # 出击/卡厄思结算页（战斗失败/胜利 + 奖励）：右下「确认」，ESC 无效
        box = find_text(task, r"^确认$", region=(0.7, 0.85, 1, 1))
        if box and (has_text(task, r"奖励") or has_text(task, r"出击记录")):
            click_text_box(task, box, after=3, reason="结算页确认")
            continue
        # 逃脱螺旋塔后的「TIP 推荐等级 / 可通过以下方式提升战员」页：右下「下一步」，ESC 无效
        box = find_text(task, r"^下一步$", region=(0.7, 0.85, 1, 1))
        if box and has_text(task, r"提升战员"):
            click_text_box(task, box, after=2, reason="TIP 页下一步")
            continue
        if has_text(task, r"^\d+元$"):
            # 付费推荐弹窗（如 F2 先弹的「特殊资料 68元 / 零之资料 128元」）：ESC 关不掉，点右上角 X，绝不点价格按钮
            click_rel(task, *PAY_POPUP_CLOSE, after=2, reason="关闭付费推荐弹窗")
            continue
        _, home = match_template(task, "home_icon", HOME_ICON_REGION, 0.8)
        if home:
            click_rel(task, *home, after=3, reason="点击主页按钮")
            continue
        _, back = match_template(task, "back_icon", BACK_ICON_REGION, 0.8)
        if back:
            click_rel(task, *back, after=2.5, reason="点击返回按钮")
            continue
        if is_black(task):
            # 结算后切场景会黑屏加载，这时不要乱点/按 ESC
            task.log_info("黑屏加载中，等待")
            task.sleep(3)
            continue
        if len(task.all_texts or []) <= 2:
            # 主页 UI 隐藏（只剩立绘）或加载中：点空白处唤醒，点不出来就换个位置
            click_rel(task, *HOME_WAKE_POINTS[wakes % len(HOME_WAKE_POINTS)], after=1.5, reason="唤醒主页 UI")
            wakes += 1
            continue
        if esc_count >= 3:
            task.log_info("连续按 ESC 仍未回到主页，停止")
            return False
        esc_count += 1
        task.log_info("未识别的页面，按 ESC 返回")
        task.send_key("esc")
        task.sleep(2)
    task.log_info("回主页超时")
    return False


def open_home_entry(task: BaseTask, name, timeout=15.0):
    """在主页点右侧入口（如「方舟城市」「模拟」）。UI 被隐藏时先唤醒再点。"""
    if not go_home(task):
        return False
    box = find_text(task, f"^{name}$", region=(0.8, 0.1, 1.0, 0.8))
    if not box:
        click_rel(task, *HOME_WAKE_POINT, after=1.5, reason="唤醒主页 UI")
        refresh(task)
        box = find_text(task, f"^{name}$", region=(0.8, 0.1, 1.0, 0.8))
    if not box:
        task.log_info(f"主页上没有找到入口「{name}」")
        return False
    click_text_box(task, box, after=3, reason=f"进入「{name}」")
    return True


# ------------------------- 领取类日常 -------------------------

def close_reward_popup(task: BaseTask, timeout=4.0):
    """领取后的「获得道具 / 点击屏幕可关闭」弹窗：点掉，返回是否出现过。"""
    end = time.time() + timeout
    seen = False
    while time.time() < end:
        refresh(task)
        box = find_text(task, r"点击屏幕可关闭")
        if box:
            seen = True
            click_text_box(task, box, after=1.5, reason="关闭获得道具")
            continue
        if seen:
            break
        task.sleep(0.5)
    return seen


def claim_all(task: BaseTask, region, timeout=5.0):
    """点区域内的「全部领取」（没有可领的时候按钮是灰的，点了也不会有弹窗），返回是否领到东西。"""
    if not click_text(task, r"^全部领取$", region=region, timeout=timeout, after=1.5):
        return False
    got = close_reward_popup(task)
    task.log_info("领到奖励" if got else "没有可领取的奖励")
    return got


def open_menu(task: BaseTask, tries=3):
    """主页打开右上角 ≡ 菜单（右侧一列：邮箱/主页/公告/…/设置/结束）。"""
    if not go_home(task):
        return False
    for _ in range(tries):
        click_rel(task, *MENU_POINT, after=2, reason="打开菜单")
        refresh(task)
        if has_text(task, r"^辅战员$", region=(0.7, 0.3, 0.85, 0.45)) and has_text(task, r"^商店$", region=(0.7, 0.55, 0.85, 0.7)):
            return True
    task.log_info("没有打开菜单")
    return False


def claim_daily_activity(task: BaseTask):
    """F3「日常」→「每日任务」页签 → 全部领取活跃度奖励。"""
    if not go_home(task):
        return False
    task.send_key("f3")
    if not wait_text(task, r"成长指南|每日任务|模拟训练|作战|达成手册", region=(0.08, 0.05, 0.35, 0.17), timeout=8):
        task.log_info("没有打开日常窗口")
        return False
    click_rel(task, *DAILY_TASK_TAB, after=2, reason="切到每日任务")
    if not wait_text(task, r"每日任务", region=(0.08, 0.05, 0.35, 0.17), timeout=5):
        task.log_info("没有切到每日任务页签")
        return False
    progress = find_text(task, r"^\d+/100$", region=(0.1, 0.55, 0.3, 0.7))
    if progress:
        task.log_info(f"日程进度 {progress.name}")
    claim_all(task, region=(0.08, 0.72, 0.3, 0.88))
    return True


def claim_supply(task: BaseTask):
    """F2「阿基亚农补给」：先关掉付费推荐弹窗，再在任务页签、奖励页签各点一次全部领取。"""
    if not go_home(task):
        return False
    task.send_key("f2")
    end = time.time() + 12
    while True:
        refresh(task)
        if has_text(task, r"^阿基亚农补给$", region=(0.05, 0.0, 0.3, 0.1)):
            break
        if has_text(task, r"^\d+元$"):
            click_rel(task, *PAY_POPUP_CLOSE, after=2, reason="关闭付费推荐弹窗")
            continue
        if time.time() > end:
            task.log_info("没有打开阿基亚农补给")
            return False
        task.sleep(0.5)
    exp_before = _supply_exp(task)
    # 任务页签领经验不弹「获得道具」，用经验值前后对比确认
    for name, point in (("任务", SUPPLY_TASK_TAB), ("奖励", SUPPLY_REWARD_TAB)):
        click_rel(task, *point, after=2, reason=f"切到补给{name}页签")
        claim_all(task, region=(0.55, 0.86, 0.75, 0.97))
    refresh(task)
    task.log_info(f"补给经验 {exp_before} → {_supply_exp(task)}")
    return True


def _supply_exp(task: BaseTask):
    box = find_text(task, r"^\d+/1000$", region=(0.4, 0.1, 0.6, 0.18))
    return box.name if box else "?"


def claim_mail(task: BaseTask):
    """≡ 菜单 → 邮箱 → 全部领取（主页按 M 没反应，所以走菜单）。"""
    if not open_menu(task):
        return False
    click_rel(task, *MENU_MAIL_POINT, after=2.5, reason="打开邮箱")
    if not wait_text(task, r"^邮箱$", region=(0.03, 0.05, 0.2, 0.13), timeout=6):
        task.log_info("没有打开邮箱")
        return False
    claim_all(task, region=(0.05, 0.85, 0.25, 0.95))
    return True


def ensure_hotkey_display(task: BaseTask):
    """设置 → 键盘 →「快捷键显示」保持 ON。出击/卡厄思的手牌识别依赖卡牌上的按键提示。"""
    if not open_menu(task):
        return False
    click_rel(task, *MENU_SETTINGS_POINT, after=3, reason="打开设置")
    click_rel(task, *SETTINGS_KEYBOARD_TAB, after=2, reason="切到键盘设置")
    if not wait_text(task, r"快捷键显示", region=(0.05, 0.2, 0.3, 0.26), timeout=5):
        task.log_info("没有找到「快捷键显示」设置项")
        return False
    for _ in range(2):
        state = find_text(task, r"^(ON|OFF)$", region=(0.6, 0.2, 1.0, 0.27))
        if state and state.name == "ON":
            task.log_info("快捷键显示：ON")
            return True
        if not state:
            task.log_info("读不到快捷键显示开关状态")
            return False
        click_text_box(task, state, after=1.5, reason="打开快捷键显示")
        refresh(task)
    return has_text(task, r"^ON$", region=(0.6, 0.2, 1.0, 0.27))


def read_ether(task: BaseTask):
    """右上角以太「当前/上限」，读不到返回 (None, None)。"""
    box = find_text(task, r"^\d+\s*/\s*\d+", region=(0.88, 0.0, 1.0, 0.1))
    if not box:
        return None, None
    cur, cap = re.match(r"(\d+)\s*/\s*(\d+)", box.name).groups()
    return int(cur), int(cap)


def drink_coffee(task: BaseTask, choice="自动"):
    """方舟城市 → 庭院咖啡店 → 点单（每天一杯）。

    choice：堂食（立即 +120 以太）/ 外带（存一个以太补充货币）/ 自动（以太加 120 会超上限就外带，否则堂食）。
    """
    if not open_home_entry(task, "方舟城市"):
        return False
    if not click_text(task, r"^庭院咖啡店$", region=(0.3, 0.85, 0.6, 0.97), timeout=8, after=3):
        return False
    end = time.time() + 20
    order_clicks = 0
    while True:
        refresh(task)
        if has_text(task, r"^菜单板$"):
            break
        if has_text(task, r"每天一杯的咖啡因就足够了"):
            task.log_info("今天已经点过咖啡")
            return True
        if has_text(task, r"每日限量一杯"):
            # 进店说明弹窗
            if click_text(task, r"^确认$", region=(0.4, 0.85, 0.6, 0.97), timeout=2, after=3):
                continue
        box = find_text(task, r"^点单$", region=(0.65, 0.85, 0.9, 0.97))
        if box:
            if order_clicks >= 3:
                # 「每天一杯…」提示只闪一下，可能没截到；点了几次都不出菜单板就当已点过
                task.log_info("点单后没有出现菜单板，按今天已点过处理")
                return True
            order_clicks += 1
            click_text_box(task, box, after=0.6, reason="打开菜单板")
            continue
        if time.time() > end:
            task.log_info("没有打开咖啡店菜单板")
            return False
        task.sleep(0.5)
    cur, cap = read_ether(task)
    if choice == "自动":
        choice = "外带" if cur is None or cur + COFFEE_DINE_IN_ETHER > cap else "堂食"
    task.log_info(f"以太 {cur}/{cap}，点{choice}")
    click_rel(task, *(COFFEE_DINE_IN if choice == "堂食" else COFFEE_TAKEOUT), after=1.5, reason=f"选择{choice}")
    click_rel(task, *COFFEE_ORDER_BOARD, after=3, reason="点单")
    if click_text(task, r"跳过", region=(0.85, 0.0, 1.0, 0.12), timeout=6, after=2):
        pass
    if not close_reward_popup(task, timeout=8):
        task.log_info("点单后没有看到获得道具")
        return False
    return True


def battle_auto_off(task: BaseTask):
    """战斗页：自动战斗按钮中心 4×4 区域纯白占比 >2% 说明没开（与 utils_chaos.handle_battle_auto_check 同一判定）。"""
    frame = task.frame
    if frame is None:
        return False
    x, y = int(0.877 * task.width), int(0.050 * task.height)
    patch = frame[y:y + 4, x:x + 4]
    return float((patch.min(axis=2) >= 255).mean()) > 0.02


def _training_efficiency(task: BaseTask):
    box = find_text(task, r"战斗效率\D*(\d)", region=(0.7, 0.75, 0.95, 0.82))
    return int(re.search(r"(\d)\s*$", box.name).group(1)) if box else None


def _click_training_stage(task: BaseTask, stage, scrolls=4):
    """关卡名可以写全名「潜能材料-正义」或后半截「正义」；列表一屏放 4 个，不在屏上就往下滚（潜能的正义在第 5 个）。"""
    pattern = f"(^|[-－]){re.escape(stage)}$"
    region = (0.6, 0.15, 1.0, 0.99)              # 列表最后一项（潜能-正义）滑到底也只在 y≈0.95
    for i in range(scrolls + 1):
        if click_text(task, pattern, region=region, timeout=3 if i else 6, after=3):
            return True
        if i < scrolls:
            # 滚轮（PostMessage）滚不动这个列表，要按住往上拖；一次只挪一小段（实测 0.85→0.35 挪了约 0.13 屏）
            task.swipe_relative(0.72, 0.85, 0.72, 0.30, duration=0.8)
            task.sleep(1.5)
    return False


def farm_stamina(task: BaseTask, category="成长", stage="单元币", efficiency=6, keep_ether=0, max_runs=20,
                 next_difficulty=True):
    """模拟 → 战斗训练 → 分类 → 关卡，按战斗效率连续打到以太不够（保留 keep_ether）。

    结算页优先「下个难度」（next_difficulty），不可用时「重来」；战斗失败就停止，不在打不过的难度上继续消耗以太。
    """
    if not open_home_entry(task, "模拟"):
        return False
    # 第一次进可能弹「挑战」说明
    if wait_text(task, r"每周3次机会|这里是模拟", timeout=3):
        click_text(task, r"^确认$", region=(0.4, 0.85, 0.6, 0.97), timeout=2, after=2)
    if not click_text(task, r"^战斗训练$", region=(0.05, 0.6, 0.25, 0.75), timeout=6, after=3):
        return False
    if not click_text(task, f"^{category}$", region=(0.0, 0.1, 0.3, 0.8), timeout=6, after=2):
        return False
    if not _click_training_stage(task, stage):
        return False
    if not wait_text(task, r"^配置队伍$", region=(0.05, 0.0, 0.3, 0.1), timeout=8):
        task.log_info("没有进入配置队伍页面")
        return False
    cur, _ = read_ether(task)
    if cur is None:
        task.log_info("读不到以太")
        return False
    target = min(max(efficiency, 1), 6, (cur - keep_ether) // TRAINING_COST_PER_EFF)
    if target < 1:
        task.log_info(f"以太 {cur}，保留 {keep_ether}，不够打一次")
        return True
    for _ in range(8):
        eff = _training_efficiency(task)
        if eff is None or eff == target:
            break
        click_rel(task, *(TRAINING_EFF_PLUS if eff < target else TRAINING_EFF_MINUS), after=0.8)
        refresh(task)
    cost = target * TRAINING_COST_PER_EFF
    task.log_info(f"以太 {cur}，战斗效率 {target}，每次 {cost}")
    click_rel(task, *TRAINING_ENTER, after=5, reason="进入战斗")
    runs = 1
    end = time.time() + 15 * 60
    last_known = time.time()
    while time.time() < end:
        refresh(task)
        if has_text(task, r"确定要进入当前难度"):
            # 有更高难度解锁时进入前会弹「高阶难度已经解锁。确定要进入当前难度吗？」（Maa_Kes issue #15）
            click_text(task, r"^入场$", region=(0.55, 0.7, 0.8, 0.8), timeout=2, after=5)
            last_known = time.time()
            continue
        if has_text(task, r"^重来$", region=(0.55, 0.85, 0.7, 0.97)) and has_text(task, r"^确认$", region=(0.85, 0.85, 1, 0.97)):
            last_known = time.time()
            cur, _ = read_ether(task)
            failed = has_text(task, r"失败")
            task.log_info(f"第 {runs} 次{'失败' if failed else '结束'}，以太 {cur}")
            if failed or cur is None or cur - cost < keep_ether or runs >= max_runs:
                click_text(task, r"^确认$", region=(0.85, 0.85, 1, 0.97), timeout=2, after=3)
                task.log_info(f"清体力结束，共 {runs} 次" + ("（战斗失败，不再继续）" if failed else ""))
                return True
            runs += 1
            if next_difficulty and click_text(task, r"^下个难度$", region=(0.45, 0.85, 0.56, 0.97), timeout=2, after=4):
                refresh(task)
                if not has_text(task, r"^重来$", region=(0.55, 0.85, 0.7, 0.97)):
                    continue
                # 点了没反应：已经是最高难度（或下个难度未解锁），之后只重来
                task.log_info("下个难度不可用，改为重来")
                next_difficulty = False
            click_text(task, r"^重来$", region=(0.55, 0.85, 0.7, 0.97), timeout=2, after=5)
            continue
        if find_text(task, r"^\d+\s*/\s*10$", region=(0.45, 0.94, 0.58, 1.0)):
            last_known = time.time()
            if battle_auto_off(task):
                click_rel(task, *BATTLE_AUTO_POINT, after=1, reason="开启自动战斗")
                continue
        elif time.time() - last_known > 60:
            task.log_info("清体力：超过 60 秒没识别到战斗/结算页面：" + " | ".join(b.name for b in (task.all_texts or [])[:8]))
            last_known = time.time()
        task.sleep(2)
    task.log_info("清体力超时")
    return False


# ------------------------- 疗愈中心 -------------------------
# 方舟城市 → 创伤中心 → 疗愈中心。卡厄思里精神崩溃的战斗员会住院，治好之前不能出战。
# 画面上全是图标，用 Maa_Kes 的 720p 模板（assets/daily/heal_*.png）和它的点击位置。
HEAL_PLANS = ("不处理", "记忆消除", "咨询")
HEAL_CITY_ENTER_REGION = (0.50, 0.78, 0.61, 0.94)        # 方舟城市底部去创伤中心的图标
HEAL_TRAUMA_REGION = (0.78, 0.58, 0.91, 0.79)            # 创伤中心建筑上的标志
HEAL_TRAUMA_CLICK = (0.791, 0.736)
HEAL_CENTER_REGION = (0.0, 0.85, 0.10, 1.0)              # 疗愈中心左下角标志
HEAL_PATIENT_REGION = (0.25, 0.42, 0.35, 0.57)           # 有病人：病床上的崩溃图标
HEAL_PATIENT_OFFSET = (0.110, -0.151)                    # 从崩溃图标到病人卡片的偏移
HEAL_NO_PATIENT_REGION = (0.46, 0.35, 0.69, 0.68)        # 没病人：中间的空床标志
HEAL_SELECTED_REGION = (0.49, 0.17, 0.58, 0.30)
HEAL_PLAN_BUTTON = {"记忆消除": (0.609, 0.926), "咨询": (0.859, 0.929)}
HEAL_PLAN_CONFIRM = {"记忆消除": (0.6625, 0.706), "咨询": (0.6625, 0.632)}
HEAL_CHOICE_LEFT = (0.230, 0.467)                        # 咨询对话的二选一，点左边
HEAL_DISCHARGE_REGION = (0.27, 0.40, 0.37, 0.55)
HEAL_DISCHARGE_HOLD = (0.775, 0.856)                     # 批准出院：长按 0.5 秒


def _enter_heal_center(task: BaseTask, timeout=30.0):
    if not open_home_entry(task, "方舟城市"):
        return False
    end = time.time() + timeout
    while time.time() < end:
        refresh(task)
        if match_template(task, "heal_center", HEAL_CENTER_REGION)[1] or has_text(task, r"^疗愈中心$"):
            return True
        box = find_text(task, r"^(创伤中心|疗愈中心)$", region=(0.3, 0.85, 0.7, 0.97))
        if box:
            click_text_box(task, box, after=3, reason="进入创伤中心")
            continue
        if match_template(task, "heal_trauma_center", HEAL_TRAUMA_REGION)[1]:
            click_rel(task, *HEAL_TRAUMA_CLICK, after=3, reason="进入疗愈中心")
            continue
        _, pos = match_template(task, "heal_city_enter", HEAL_CITY_ENTER_REGION)
        if pos:
            click_rel(task, *pos, after=3, reason="前往创伤中心")
            continue
        task.sleep(1)
    task.log_info("没有进入疗愈中心：" + " | ".join(b.name for b in (task.all_texts or [])[:8]))
    return False


def _heal_consult_until_discharge(task: BaseTask, timeout=120.0):
    """咨询：推进对话、二选一点左边，直到出现「批准出院」并长按。"""
    end = time.time() + timeout
    while time.time() < end:
        refresh(task)
        if match_template(task, "heal_discharge", HEAL_DISCHARGE_REGION)[1] or has_text(task, r"批准出院"):
            x, y = HEAL_DISCHARGE_HOLD
            task.log_info("批准出院（长按）")
            task.mouse_down(int(x * task.width), int(y * task.height), key="left")
            task.sleep(0.6)
            task.mouse_up(key="left")
            task.sleep(2)
            return True
        if match_template(task, "heal_center", HEAL_CENTER_REGION)[1]:
            return True
        if has_text(task, r"跳过", region=(0.85, 0.0, 1.0, 0.12)):
            click_text(task, r"跳过", region=(0.85, 0.0, 1.0, 0.12), timeout=1, after=1.5)
            continue
        if len(task.all_texts or []) >= 2 and _is_two_choice(task):
            click_rel(task, *HEAL_CHOICE_LEFT, after=1.5, reason="咨询回答（左）")
            continue
        task.send_key("space")
        task.sleep(1)
    task.log_info("咨询超时，没等到批准出院")
    return False


def _is_two_choice(task: BaseTask):
    """咨询对话的左右两个白底回答框：上半屏左右两侧都有文字。"""
    left = [b for b in task.all_texts or [] if in_region(task, b, (0.07, 0.23, 0.48, 0.81))]
    right = [b for b in task.all_texts or [] if in_region(task, b, (0.52, 0.23, 0.93, 0.81))]
    frame = task.frame
    if not left or not right or frame is None:
        return False
    x, y = int(HEAL_CHOICE_LEFT[0] * task.width), int(HEAL_CHOICE_LEFT[1] * task.height)
    return float(frame[y - 5:y + 5, x - 30:x + 30].min()) >= 230


def treat_patients(task: BaseTask, plan="不处理", max_patients=4):
    """疗愈中心：有住院的战斗员就按 plan 治疗（记忆消除花单元币，咨询花旅行券）；不处理＝只报告。"""
    if not _enter_heal_center(task):
        return False
    treated = 0
    for _ in range(max_patients + 2):
        refresh(task)
        task.sleep(1)
        refresh(task)
        if match_template(task, "heal_no_patient", HEAL_NO_PATIENT_REGION)[1]:
            task.log_info(f"疗愈中心没有病人（本次治疗 {treated} 位）")
            return True
        _, pos = match_template(task, "heal_has_patient", HEAL_PATIENT_REGION)
        if not pos:
            task.log_info("疗愈中心：没认出有没有病人：" + " | ".join(b.name for b in (task.all_texts or [])[:8]))
            return treated > 0
        if plan not in HEAL_PLAN_BUTTON:
            task.log_info("疗愈中心有病人，按配置不处理", notify=True)
            return True
        if treated >= max_patients:
            break
        click_rel(task, pos[0] + HEAL_PATIENT_OFFSET[0], pos[1] + HEAL_PATIENT_OFFSET[1], after=1.5, reason="选中病人")
        refresh(task)
        if not match_template(task, "heal_selected", HEAL_SELECTED_REGION)[1]:
            task.log_info("点了病人但没有进入治疗方案页")
            return False
        click_rel(task, *HEAL_PLAN_BUTTON[plan], after=1.5, reason=plan)
        if not click_text(task, r"^确认$", region=(0.4, 0.5, 0.8, 0.8), timeout=3, after=2):
            click_rel(task, *HEAL_PLAN_CONFIRM[plan], after=2, reason=f"{plan}确认")
        refresh(task)
        if has_text(task, r"不足"):
            task.log_info(f"{plan}的材料不足，停止治疗", notify=True)
            return treated > 0
        if plan == "咨询" and not _heal_consult_until_discharge(task):
            return False
        treated += 1
        task.sleep(2)
    task.log_info(f"疗愈中心本次治疗 {treated} 位")
    return True
