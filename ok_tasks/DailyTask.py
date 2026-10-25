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
            "喝咖啡": True,
            "咖啡点单": "自动",
            "清体力": True,
            "清体力分类": "成长",
            "清体力关卡": "单元币",
            "清体力战斗效率": 6,
            "清体力保留以太": 0,
            "疗愈中心": True,
            "疗愈中心治疗方式": "不处理",
        })
        self.config_description.update({
            "检查快捷键显示": "设置→键盘→快捷键显示保持 ON（出击/卡厄思识别手牌要用卡牌上的按键提示）",
            "领取日常活跃奖励": "F3 日常 → 每日任务的日程进度奖励",
            "领取阿基亚农补给": "F2 补给（通行证）任务经验与等级奖励，只点全部领取，不碰付费按钮",
            "领取邮箱": "菜单 → 邮箱 → 全部领取",
            "喝咖啡": "方舟城市 → 庭院咖啡店，每天一杯",
            "咖啡点单": "堂食立即 +120 以太；外带存 1 个以太补充货币（最多 4 个）；自动＝以太会溢出时外带，否则堂食",
            "清体力": "模拟 → 战斗训练，按战斗效率连续打到以太不够；结算页优先下个难度，战斗失败就停",
            "清体力分类": "战斗训练左侧分类（按画面文字点）",
            "清体力关卡": "分类里的关卡名（按画面文字点，如 单元币）",
            "清体力战斗效率": "每次消耗 20×效率 以太，以太不够时自动降到打得起的效率",
            "清体力保留以太": "留这么多以太不用（比如留给卡厄思）",
            "疗愈中心": "方舟城市 → 创伤中心，查看卡厄思里精神崩溃住院的战斗员（住院期间不能出战）",
            "疗愈中心治疗方式": "不处理＝只提示；记忆消除花单元币；咨询花旅行券，对话自动选左边回答后批准出院",
        })
        # (配置项, 执行函数名)，函数在 utils_daily 里，签名 fn(task) -> bool
        self.steps = [
            ("检查快捷键显示", "ensure_hotkey_display"),
            ("领取日常活跃奖励", "claim_daily_activity"),
            ("领取阿基亚农补给", "claim_supply"),
            ("领取邮箱", "claim_mail"),
            ("疗愈中心", "treat_patients"),
            ("喝咖啡", "drink_coffee"),
            ("清体力", "farm_stamina"),      # 放在喝咖啡后面：堂食咖啡先补以太
        ]
        self.config_type = {
            "咖啡点单": {"type": "drop_down", "options": ["自动", "堂食", "外带"]},
            "清体力分类": {"type": "drop_down", "options": ["成长", "主战员", "辅战员", "潜能", "记忆碎片"]},
            "清体力战斗效率": {"type": "drop_down", "options": [1, 2, 3, 4, 5, 6]},
            "疗愈中心治疗方式": {"type": "drop_down", "options": list(utils_daily.HEAL_PLANS)},
        }

    def _step_kwargs(self, fn_name):
        if fn_name == "drink_coffee":
            return {"choice": self.config.get("咖啡点单", "自动")}
        if fn_name == "farm_stamina":
            return {"category": self.config.get("清体力分类", "成长"), "stage": self.config.get("清体力关卡", "单元币"),
                    "efficiency": int(self.config.get("清体力战斗效率", 6)),
                    "keep_ether": int(self.config.get("清体力保留以太", 0))}
        if fn_name == "treat_patients":
            return {"plan": self.config.get("疗愈中心治疗方式", "不处理")}
        return {}

    def run(self):
        results = []
        for key, fn_name in self.steps:
            if not self.config.get(key):
                continue
            self.log_info(f"开始：{key}")
            try:
                fn = getattr(utils_daily, fn_name)
                ok = fn(self, **self._step_kwargs(fn_name))
            except Exception as e:
                self.log_error(f"{key} 出错: {e}\n{traceback.format_exc()}")
                self.screenshot(f"daily_error_{fn_name}")
                ok = False
            results.append(f"{key}：{'完成' if ok else '未完成'}")
            self.info_set(key, "完成" if ok else "未完成")
            go_home(self)
        self.log_info("一键日常结束：" + "；".join(results), notify=True)
