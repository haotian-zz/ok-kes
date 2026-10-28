"""新界面共用的只读查询：任务、是否在跑、游戏窗口。"""

from __future__ import annotations

from ok import Logger

logger = Logger.get_logger(__name__)

# 侧栏页面 -> 任务类名
PAGE_TASKS = {
    "daily": "DailyTask",
    "chaos": "ChaosMode",
    "sortie": "SortieMode",
    "story": "StoryMode",
}
# 任务类名 -> (界面名, 图标)
TASK_LOOK = {
    "DailyTask": ("一键日常", "calendar-check"),
    "ChaosMode": ("卡厄思", "sparkles"),
    "SortieMode": ("出击", "swords"),
    "StoryMode": ("剧情", "book-open"),
}


def og():
    from ok import og as _og

    return _og


def executor():
    return getattr(og(), "executor", None)


def onetime_tasks() -> list:
    return list(getattr(executor(), "onetime_tasks", None) or [])


def trigger_tasks() -> list:
    return list(getattr(executor(), "trigger_tasks", None) or [])


def task_by_class_name(class_name: str):
    """ok_tasks 里的任务改代码后会被框架重新加载成新对象，所以每次按类名现找。"""
    for task in onetime_tasks() + trigger_tasks():
        if type(task).__name__ == class_name:
            return task
    return None


def is_trigger(task) -> bool:
    return any(task is each for each in trigger_tasks())


def running(task) -> bool:
    """这个任务在跑：触发式任务（卡厄思/出击/剧情）看开关，一次性任务（一键日常）看是否启用或执行中。"""
    if task is None:
        return False
    if is_trigger(task):
        return bool(getattr(task, "enabled", False))
    return bool(getattr(task, "enabled", False) or getattr(task, "running", False))


def active_tasks() -> list:
    """正在跑的任务（按侧栏顺序）。"""
    result = []
    for class_name in PAGE_TASKS.values():
        task = task_by_class_name(class_name)
        if running(task):
            result.append(task)
    return result


def busy() -> bool:
    return bool(active_tasks())


def display_name(task) -> str:
    look = TASK_LOOK.get(type(task).__name__)
    return look[0] if look else str(getattr(task, "name", "") or "")


def tr(text: str) -> str:
    app = getattr(og(), "app", None)
    try:
        return app.tr(text) if app is not None else text
    except Exception:
        return text


def game_window() -> dict:
    """{'connected', 'title', 'size'}，给侧栏底部。"""
    manager = getattr(og(), "device_manager", None)
    result = {"connected": False, "title": "", "size": ""}
    if manager is None:
        return result
    try:
        window = getattr(manager, "hwnd_window", None)
        capture = getattr(manager, "capture_method", None)
        if window is not None and getattr(window, "exists", False):
            result["connected"] = capture is not None
            result["title"] = str(getattr(window, "title", "") or "")
            width, height = (
                int(getattr(window, "width", 0) or 0),
                int(getattr(window, "height", 0) or 0),
            )
            if width and height:
                result["size"] = f"{width}×{height}"
    except Exception:
        pass
    return result


def chaos_task():
    return task_by_class_name("ChaosMode")
