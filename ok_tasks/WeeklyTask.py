import traceback

from ok import BaseTask

import game_speed
import utils_daily
from utils_daily import go_home

RESTAURANT_DISHES = ("巧克力面包", "软绵绵的桃子馒头", "微甜照烧串", "肉汁满满的直火烤串", "海香寿司拼盘")


class WeeklyTask(BaseTask):
    """一键周常：F2 补给「每周任务」里脚本能做的几项，做完领补给经验。单项失败只记录并回主页。

    卡厄思相关的周常（通关卡厄思、德朗商店买东西、通关未知区域）用「自动卡厄思」跑，
    咖啡每天一杯、以太用量靠一键日常慢慢攒，这里不管。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "一键周常"
        self.description = "星光餐厅点餐、模拟挑战，最后领阿基亚农补给。请先启动游戏（国服 PC 客户端）。"
        self.all_texts = []
        self.default_config.update({
            "星光餐厅点餐": True,
            "星光餐厅菜品": "巧克力面包",
            "模拟挑战": True,
            "模拟挑战对象": "哀嚎的浪子",
            "领取阿基亚农补给": True,
        })
        game_speed.add_config(self)
        self.config_description.update({
            "星光餐厅点餐": "方舟城市 → 星光餐厅，按每周任务「星光餐厅点餐3次」的进度补够次数（每次 8000～15000 单元币，增益进卡厄思时用 2 次）",
            "星光餐厅菜品": "点哪道菜（巧克力面包＝所有主战员生命值 +10%）",
            "模拟挑战": "模拟 → 战斗训练 → 挑战，把每周 3 次免费次数打完（周常「通关1次/3次模拟[挑战]」），不花以太，战斗失败就停",
            "模拟挑战对象": "挑战哪个首领",
            "领取阿基亚农补给": "最后 F2 补给任务/奖励页签各点一次全部领取，把周常经验领掉",
        })
        self.config_type = {
            "星光餐厅菜品": {"type": "drop_down", "options": list(RESTAURANT_DISHES)},
            "模拟挑战对象": {"type": "drop_down", "options": list(utils_daily.CHALLENGE_BOSSES)},
        }
        # (配置项, 本类里的方法名)
        self.steps = [
            ("星光餐厅点餐", "_restaurant"),
            ("模拟挑战", "_challenge"),
            ("领取阿基亚农补给", "_claim"),
        ]

    def _restaurant(self):
        progress = utils_daily.weekly_mission_progress(self, r"星光餐厅.*点餐")
        go_home(self)
        if progress is None:
            self.log_info("读不到「星光餐厅点餐」周常进度，不点餐")
            return False
        done, total = progress
        self.log_info(f"星光餐厅点餐周常 {done}/{total}")
        return utils_daily.order_restaurant(self, self.config.get("星光餐厅菜品", "巧克力面包"), max(total - done, 0))

    def _challenge(self):
        return utils_daily.challenge_training(self, self.config.get("模拟挑战对象", "哀嚎的浪子"))

    def _claim(self):
        return utils_daily.claim_supply(self)

    def run(self):
        results = []
        setattr(self, utils_daily.LEFTOVER_RUN_ATTR, False)
        utils_daily.refresh(self)
        game_speed.ensure_speed(self)
        for key, fn_name in self.steps:
            if not self.config.get(key):
                continue
            self.log_info(f"开始：{key}")
            try:
                ok = getattr(self, fn_name)()
            except Exception as e:
                self.log_error(f"{key} 出错: {e}\n{traceback.format_exc()}")
                self.screenshot(f"weekly_error_{fn_name}")
                ok = False
            results.append(f"{key}：{'完成' if ok else '未完成'}")
            self.info_set(key, "完成" if ok else "未完成")
            go_home(self)
            if getattr(self, utils_daily.LEFTOVER_RUN_ATTR, False):
                results.append("后面的项没做（登录弹出未完成的玩法，要人决定继续还是逃脱）")
                break
        self.log_info("一键周常结束：" + "；".join(results), notify=True)
