"""开始 / 停止任务，做法和 ok 原来的任务卡一样。

- 一键日常（一次性任务）：交给 start_controller.start(task)，和原来的「开始」按钮一样。
- 卡厄思 / 出击 / 剧情（触发式任务）：和原来的开关一样在线程里 task.enable()（它们的 enable 会关掉互斥的模式、
  重置本局状态），执行器还没开就再 start_controller.start() 连接游戏、开执行器。
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from ok import Logger

from src.ui.shell import data

logger = Logger.get_logger(__name__)

_started: list[Callable[[], None]] = []


def on_started(callback: Callable[[], None]) -> None:
    _started.append(callback)


def _notify_started() -> None:
    for callback in list(_started):
        try:
            callback()
        except Exception as exc:
            logger.error("start callback failed", exc)


def other_running(task) -> list:
    return [each for each in data.active_tasks() if each is not task]


def can_start(task) -> bool:
    return task is not None and data.executor() is not None and not data.running(task)


def start(task, window=None) -> bool:
    if task is None:
        _warn(window, "找不到这个任务，请重开工具再试")
        return False
    if data.running(task):
        return False
    others = other_running(task)
    if others:
        # 新界面一次只跑一个任务（原来的开关可以同时开剧情和卡厄思）
        names = "、".join(data.display_name(each) for each in others)
        _warn(window, f"「{names}」还在跑，先停止再开始")
        return False
    logger.info(f"shell start {type(task).__name__}")
    try:
        controller = data.og().app.start_controller
        if data.is_trigger(task):
            threading.Thread(target=task.enable, name="TaskEnable", daemon=True).start()
            if getattr(data.executor(), "paused", True):
                controller.start()
        else:
            controller.start(task)
    except Exception as exc:
        logger.error(f"start {task.name} failed", exc)
        _warn(window, f"开始失败：{exc}")
        return False
    _notify_started()
    return True


def stop(task) -> None:
    if task is None:
        return
    logger.info(f"shell stop {type(task).__name__}")
    task.disable()
    if getattr(task, "paused", False):
        task.unpause()


def _warn(window, text: str) -> None:
    if window is None:
        return
    try:
        from qfluentwidgets import InfoBar, InfoBarPosition

        InfoBar.warning(
            data.tr("没有开始"), data.tr(text), parent=window, position=InfoBarPosition.TOP, duration=6000
        )
    except Exception as exc:
        logger.error("start warning failed", exc)


def open_folder(path: str) -> None:
    import os
    import subprocess
    import sys

    try:
        os.makedirs(path, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(os.path.abspath(path))  # noqa: S606 - 打开用户自己的文件夹
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as exc:
        logger.error(f"open folder failed: {exc}")
