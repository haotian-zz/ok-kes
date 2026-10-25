# 游戏卡死时自动重开：结束游戏进程 → 从 WeGame 启动器点「启动」→ 过标题页和登录弹窗 → 交回卡厄思流程。
# 2026-10-25 第十二局兑换额外战利品后游戏 UI 锁死（点击、ESC 都没反应），用户同意「卡死自动重开」。
# 启动入口是 <安装目录>\WeGameLauncher\launcher.exe；安装目录根下的 exe 是卸载程序，绝不能碰。
import os
import re
import subprocess
import time

LAUNCH_BUTTON = (0.863, 0.941)      # 启动器窗口里「启动」按钮（实测 1600×900 的启动器窗口）
LAUNCHER_MIN_WIDTH = 600
LOGIN_TIMEOUT = 300


def launcher_path(game_exe):
    """游戏 exe 在 <安装目录>\\bin\\ssr-xcent.exe，启动器在 <安装目录>\\WeGameLauncher\\launcher.exe。"""
    if not game_exe:
        return None
    root = os.path.dirname(os.path.dirname(game_exe))
    path = os.path.join(root, "WeGameLauncher", "launcher.exe")
    return path if os.path.isfile(path) else None


def _game_exe():
    from ok import og
    hwnd_window = getattr(getattr(og, "device_manager", None), "hwnd_window", None)
    return getattr(hwnd_window, "exe_full_path", None)


def _launcher_windows():
    """WeGame 启动器窗口：属于 WeGame 的 browser.exe（CEF），标题「WeGame」、类名 CefTopWindow，实测 1600×900。"""
    import win32gui
    found = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd) or win32gui.GetClassName(hwnd) != "CefTopWindow":
            return True
        if win32gui.GetWindowText(hwnd) != "WeGame":
            return True
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        if r - l >= LAUNCHER_MIN_WIDTH and 1.6 <= (r - l) / max(1, b - t) <= 1.9:
            found.append((hwnd, (l, t, r, b)))
        return True

    win32gui.EnumWindows(cb, None)
    return found


def _real_click(hwnd, rect, rel):
    """启动器不在 ok-script 的捕获窗口里，用真实鼠标点（会动一下光标）。"""
    import win32api
    import win32con
    import win32gui
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:  # noqa: BLE001
        pass
    time.sleep(1)
    l, t, r, b = rect
    x, y = int(l + (r - l) * rel[0]), int(t + (b - t) * rel[1])
    win32api.SetCursorPos((x, y))
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.1)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    return x, y


def _game_running(exe_name):
    import psutil
    return any((p.info["name"] or "").lower() == exe_name.lower() for p in psutil.process_iter(["name"]))


def _prefer_pc(task):
    """游戏进程消失时 ok-script 会把首选设备改成别的（实录被存成模拟器 Pie64，之后一直截不到图），重开后改回 PC 窗口。"""
    from ok import og
    dm = getattr(og, "device_manager", None)
    if dm is None:
        return
    try:
        dm.do_refresh()
        pc = next((imei for imei, d in dm.device_dict.items() if d.get("device") == "windows"), None)
        if pc is not None and dm.config.get("preferred") != pc:
            task.log_info(f"首选设备是 {dm.config.get('preferred')}，改回 PC 窗口")
            dm.set_preferred_device(imei=pc)
    except Exception as e:  # noqa: BLE001
        task.log_info(f"改回 PC 窗口失败: {e}")


def restart_game(task, reason):
    """结束并重新拉起游戏，等到能交回页面流程（主页或卡厄思里的页面）。成功返回 True。"""
    from ok.util.process import kill_exe
    import utils_daily

    exe = _game_exe()
    launcher = launcher_path(exe)
    task.log_info(f"游戏卡死（{reason}），自动重开：{exe}", notify=True)
    if not launcher:
        task.log_info(f"找不到 WeGame 启动器（游戏路径 {exe}），不能自动重开")
        return False
    exe_name = os.path.basename(exe)
    kill_exe(abs_path=exe)
    for _ in range(15):
        if not _game_running(exe_name):
            break
        time.sleep(1)
    time.sleep(3)

    subprocess.Popen([launcher], cwd=os.path.dirname(launcher))
    started = False
    for attempt in range(3):
        deadline = time.time() + 40
        windows = []
        while time.time() < deadline and not windows:
            time.sleep(3)
            windows = _launcher_windows()
        if not windows:
            task.log_info("没等到 WeGame 启动器窗口")
            continue
        hwnd, rect = windows[0]
        pos = _real_click(hwnd, rect, LAUNCH_BUTTON)
        task.log_info(f"点启动器「启动」{pos}（第 {attempt + 1} 次）")
        deadline = time.time() + 60
        while time.time() < deadline:
            time.sleep(3)
            if _game_running(exe_name):
                started = True
                break
        if started:
            break
    if not started:
        task.log_info("点了启动器但游戏没起来，停止", notify=True)
        return False

    time.sleep(20)                        # 等游戏窗口出来
    _prefer_pc(task)

    # 过标题页「点击开始」和登录弹窗（每日礼物「点击以领取补给」等）；出现主页或别的游戏页面就交回去
    deadline = time.time() + LOGIN_TIMEOUT
    last_page = None
    while time.time() < deadline:
        task.sleep(3)
        try:
            utils_daily.refresh(task)
        except Exception:  # noqa: BLE001
            continue                      # 新窗口还没绑定上，截图会失败
        texts = [b.name for b in task.all_texts or []]
        if utils_daily.is_home(task):
            task.log_info("重开后回到主页")
            return True
        box = utils_daily.find_text(task, r"^点击(开始|以|屏幕|画面)")
        if box:
            utils_daily.click_text_box(task, box, after=3, reason="重开后过标题页/登录弹窗")
            continue
        page = set(texts)
        if len(texts) >= 3 and not any(re.search(r"适龄|版权|出版|著作权", t) for t in texts):
            # 加载页的提示文字会变；连续两次看到差不多的页面才交回去
            if last_page and len(page & last_page) >= max(2, len(page) // 2):
                task.log_info(f"重开后进入游戏页面：{' | '.join(texts[:6])}")
                return True
        last_page = page
    task.log_info("重开后等不到可识别的页面，停止", notify=True)
    return False
