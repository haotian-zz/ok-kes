import traceback

from ok import BaseTask

import utils_daily
from utils_daily import go_home


class DailyTask(BaseTask):
    """一键日常：按开关依次执行各项日常，单项失败只记录并回主页，不影响后面的项。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "一键日常"
        self.description = "依次执行勾选的日常项目。请先启动游戏并进入主页（国服 PC 客户端）。"
        self.all_texts = []
        self.default_config.update({
            "检查快捷键显示": True,
            "领取日常活跃奖励": True,
            "领取阿基亚农补给": True,
            "领取邮箱": True,
        })
        self.config_description.update({
            "检查快捷键显示": "设置→键盘→快捷键显示保持 ON（出击/卡厄思识别手牌要用卡牌上的按键提示）",
            "领取日常活跃奖励": "F3 日常 → 每日任务的日程进度奖励",
            "领取阿基亚农补给": "F2 补给（通行证）任务经验与等级奖励，只点全部领取，不碰付费按钮",
            "领取邮箱": "菜单 → 邮箱 → 全部领取",
        })
        # (配置项, 执行函数名)，函数在 utils_daily 里，签名 fn(task) -> bool
        self.steps = [
            ("检查快捷键显示", "ensure_hotkey_display"),
            ("领取日常活跃奖励", "claim_daily_activity"),
            ("领取阿基亚农补给", "claim_supply"),
            ("领取邮箱", "claim_mail"),
        ]

    def run(self):
        results = []
        for key, fn_name in self.steps:
            if not self.config.get(key):
                continue
            self.log_info(f"开始：{key}")
            try:
                ok = getattr(utils_daily, fn_name)(self)
            except Exception as e:
                self.log_error(f"{key} 出错: {e}\n{traceback.format_exc()}")
                self.screenshot(f"daily_error_{fn_name}")
                ok = False
            results.append(f"{key}：{'完成' if ok else '未完成'}")
            self.info_set(key, "完成" if ok else "未完成")
            go_home(self)
        self.log_info("一键日常结束：" + "；".join(results), notify=True)
