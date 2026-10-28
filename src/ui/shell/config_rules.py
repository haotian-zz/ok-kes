"""配置项的显示规则（不依赖 Qt，方便单测）。

任务在 ``config_type[父项]['sub_configs'] = {父项取值: [子项...]}`` 里声明子项只在父项取某个值时显示。
和 YES-BD2 的 config_form 一样支持多级链式；另外同一个子项可以挂在父项的几个取值下
（卡厄思的一个键在三种玩法下都读），任一取值满足就显示。
"""

from __future__ import annotations


def type_of(task, key) -> dict:
    the_type = (getattr(task, "config_type", None) or {}).get(key)
    if isinstance(the_type, dict):
        return the_type
    if the_type is None:
        return {}
    return {"type": the_type}


def parents(task) -> dict[str, tuple[str, list]]:
    """子项 -> (父项, 父项要取的值列表)。"""
    result: dict[str, tuple[str, list]] = {}
    for key, the_type in (getattr(task, "config_type", None) or {}).items():
        if not isinstance(the_type, dict):
            continue
        rules = the_type.get("sub_configs")
        if not isinstance(rules, dict):
            continue
        for value, children in rules.items():
            if isinstance(children, str):
                children = [children]
            for child in children or ():
                parent, values = result.setdefault(child, (key, []))
                if parent == key and value not in values:
                    values.append(value)
    return result


def _matches(current, value) -> bool:
    if isinstance(value, str) and isinstance(current, bool):
        current = str(current).lower()
    return current == value


def condition_met(config, key: str, rules: dict[str, tuple[str, list]]) -> bool:
    """``key`` 这一行该不该显示：沿父项一路往上，每一级父项的当前值都在允许的值里。"""
    seen = set()
    while key in rules and key not in seen:
        seen.add(key)
        parent, values = rules[key]
        current = config.get(parent)
        if not any(_matches(current, value) for value in values):
            return False
        key = parent
    return True


def visible_keys(task, keys, config=None) -> list[str]:
    """``keys`` 里按当前配置该显示的那些（保持顺序）。"""
    config = task.config if config is None else config
    rules = parents(task)
    return [key for key in keys if condition_met(config, key, rules)]
