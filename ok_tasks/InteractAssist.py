import time

from ok import TriggerTask

import utils_daily

# 「再战」按钮（橙底交叉双剑）在结算页右下；紫底白圈是剧情地图上的可交互点，位置不固定
RETRY_REGION = (0.55, 0.85, 0.64, 0.98)
CLICK_COOLDOWN = 2.0


class InteractAssist(TriggerTask):
    """交互辅助（移植自 Maa_Kes）：开着时自动点「继续挑战」和地图上的紫底白圈交互按钮。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "交互辅助"
        self.description = "开着时自动点勾选的按钮。自己玩的时候用，别和卡厄思/出击模式同时开。"
        self.trigger_interval = 1
        self.default_config['_enabled'] = False
        self.default_config.update({"继续挑战": False, "紫底白圈": True})
        self.config_description.update({
            "继续挑战": "结算页右下的橙色「再战」按钮（会一直重复打同一关）",
            "紫底白圈": "剧情地图上的紫底白圈交互点",
        })
        self._last_click = 0.0

    def run(self):
        if time.time() - self._last_click < CLICK_COOLDOWN:
            return
        targets = []
        if self.config.get("继续挑战"):
            targets.append(("retry_battle", RETRY_REGION))
        if self.config.get("紫底白圈"):
            targets.append(("interact_circle", (0, 0, 1, 1)))
        for name, region in targets:
            _, pos = utils_daily.match_template(self, name, region, threshold=0.85)
            if pos:
                utils_daily.click_rel(self, *pos, after=0.5, reason=f"交互辅助：{name}")
                self._last_click = time.time()
                return
