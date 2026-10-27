# 国服自带变速（WeGame 卡厄思梦境助手的游戏内浮窗「变速功能」）：F8 唤出，点 3.0x，再点右上角关闭。
# 实机 2026-10-27：浮窗画在游戏画面里，截图能 OCR 到，PostMessage 点击也有效；
# 但 F8 只认真实按键（PostMessage 发 F8 没反应），所以唤出时要把游戏切到前台按一下，再把原来的前台窗口还回去。
import re
import time

SPEED_KEY = "三倍速"
TITLE = "变速功能"
RATE_BOX = (0.10, 0.09, 0.21, 0.17)      # 「3.0x 当前运行倍率」的大字
CLOSE_POS = (0.263, 0.051)                # 「F8 / ESC 关闭 ×」的 ×
TRIES = 3


def parse_rate(text):
    """大字 OCR 常丢小数点（「30x」「20x」），按 1.0/1.5/2.0/3.0 四档还原。"""
    digits = re.sub(r"\D", "", text or "")
    if not digits:
        return None
    return {"10": 1.0, "1": 1.0, "15": 1.5, "20": 2.0, "2": 2.0, "30": 3.0, "3": 3.0}.get(digits[:2])


def _hwnd_window():
    from ok import og
    return getattr(getattr(og, "device_manager", None), "hwnd_window", None)


def _game_pid(hwnd):
    try:
        import win32process
        return win32process.GetWindowThreadProcessId(hwnd)[1]
    except Exception:  # noqa: BLE001
        return None


def _press_f8_foreground(hwnd):
    """游戏切前台按真实 F8，再把原来的前台窗口还回去（只动一下焦点，不动鼠标）。"""
    import win32api
    import win32con
    import win32gui
    prev = win32gui.GetForegroundWindow()
    try:
        # 按一下 Alt 才允许后台进程 SetForegroundWindow
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.8)
        win32api.keybd_event(win32con.VK_F8, 0x42, 0, 0)
        time.sleep(0.08)
        win32api.keybd_event(win32con.VK_F8, 0x42, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.5)
    finally:
        if prev and prev != hwnd:
            try:
                win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
                win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
                win32gui.SetForegroundWindow(prev)
            except Exception:  # noqa: BLE001
                pass


def _texts(task):
    import utils_daily
    utils_daily.refresh(task)
    return task.all_texts or []


def _click(task, x, y):
    task.move_relative(x, y)
    task.sleep(0.3)
    task.click(x, y)


def _panel_open(task, boxes):
    return any(TITLE in b.name for b in boxes)


def _rate(task, boxes):
    x1, y1, x2, y2 = RATE_BOX
    for b in boxes:
        cx, cy = (b.x + b.width / 2) / task.width, (b.y + b.height / 2) / task.height
        if x1 <= cx <= x2 and y1 <= cy <= y2 and re.search(r"\d", b.name):
            return parse_rate(b.name)
    return None


def _button_3x(task, boxes):
    """第一排倍率按钮（y≈0.244）里的「3.0x」；滑条下面也有一个 3.0x 刻度（y≈0.345），不点那个。"""
    for b in boxes:
        cy = (b.y + b.height / 2) / task.height
        if re.fullmatch(r"3\.?0x", b.name.replace(" ", "")) and 0.20 <= cy <= 0.29:
            return b
    return None


def ensure_speed(task):
    """设置开着、这个游戏进程还没设过 3 倍速时设一次。动过画面返回 True（本帧别再处理页面）。"""
    if task.config.get(SPEED_KEY, True) is not True:
        return False
    win = _hwnd_window()
    hwnd = getattr(win, "hwnd", 0)
    if not hwnd:
        return False
    pid = _game_pid(hwnd)
    if pid is None or getattr(task, "_speed_pid", None) == pid:
        return False
    if not task.all_texts:
        return False          # 加载/黑屏，等有画面再弄
    task._speed_pid = pid     # 不管成不成都只试这一回，别每帧切前台
    boxes = task.all_texts
    for attempt in range(TRIES):
        if not _panel_open(task, boxes):
            _press_f8_foreground(hwnd)
            task.sleep(1)
            boxes = _texts(task)
            if not _panel_open(task, boxes):
                continue
        rate = _rate(task, boxes)
        if rate != 3.0:
            btn = _button_3x(task, boxes)
            if btn:
                task.click_box(btn)
            else:
                _click(task, 0.248, 0.244)
            task.sleep(1)
            boxes = _texts(task)
            rate = _rate(task, boxes)
        task.log_info(f"变速功能：当前运行倍率 {rate}x，关闭浮窗")
        _click(task, *CLOSE_POS)
        task.sleep(1)
        boxes = _texts(task)
        if _panel_open(task, boxes):
            _click(task, *CLOSE_POS)
            task.sleep(1)
        return True
    task.log_info("按了 F8 没唤出变速浮窗，这次不设 3 倍速")
    return True
