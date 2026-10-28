from ok import TriggerTask, og

import utils_sortie
from config_io import (
    make_export_callback,
    make_import_callback,
    make_save_local_config_callback,
    make_switch_local_config_callback,
    migrate_game_language_config_file,
    migrate_renamed_config_keys,
)
from config_sync import check_upload_if_needed, show_hot_configs_dialog
from utils import (
    reset_all_status,
    _migrate_route_boss_to_elite,
    _simplify_texts,
)


class SortieMode(TriggerTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "自动出击模式"
        self.description = "1. 自动战斗依赖按键识别，请在游戏设置中打开快捷键显示，提升出牌准确率。\n2. 国际服玩家请将本模式配置中的\"游戏语言\"设置为繁体中文。"
        self.instructions = """<a href="https://github.com/ok-oldking/ok-py">ok-py</a>"""
        self.trigger_interval = 1
        self.all_texts = []
        self.default_config["_enabled"] = False
        self.default_config["配置操作"] = ""
        self.default_config["游戏语言"] = "简体中文"
        self.default_config["出战主战员优先级"] = ["海德玛丽", "九", "力", "绯"]
        self.default_config["主战员优先级"] = ["米卡", "尼娅", "蒂菲拉", "麦格纳", "卡修斯"]
        self.default_config[utils_sortie.USE_SANITY] = False
        self.default_config[utils_sortie.SANITY_REFILL] = False
        self.default_config[utils_sortie.SORTIE_LEVEL] = 0
        self.default_config["速刷模式"] = False
        self.default_config["出牌优先级"] = ["剑雨", "水之源", "一缕光芒", "万众英雄","极光剑", "展开极光","解放极光"]
        self.default_config["获得卡牌优先级"] = ["展开极光", "剑雨", "一缕光芒","缕光芒","凝聚极光"]
        self.default_config["移除卡牌列表"] = ["剑幕"]
        self.default_config["复制卡牌列表"] = ["剑雨", "展开极光", "一缕光芒","缕光芒"]
        self.default_config["闪光卡牌列表"] = ["剑雨", "展开极光", "一缕光芒","缕光芒"]
        self.default_config["装备1号位优先级"] = ["蚀化臂铠"]
        self.default_config["装备2号位优先级"] = ["拷问工具箱"]
        self.default_config["装备3号位优先级"] = ["异象石碑"]
        self.default_config["只打第一层"] = True
        self.default_config["进入商店"] = False
        self.default_config["商店刷新信用点阈值"] = 300
        self.default_config["优先移除基础牌"] = True
        self.default_config["几轮后停止(0为不停止)"] = 0
        self.default_config["卡牌奖励优先级"] = ["梦之边境", "装备包"]
        self.default_config["丢弃卡牌优先级"] = ["展开极光", "极光剑", "凝聚极光"]
        self.default_config["任务优先级"] = ["选取随机3条命运","信用点增加", "移除"]
        self.default_config["拉黑任务"] = ["咒术卡牌", "压力"]
        self.default_config["拉黑主战员"] = ["黛安娜", "阿黛尔海特"]
        self.default_config["生命值大于多少优先闪光(百分比)"] = "60"
        self.default_config["路线优先级"] = ["休息", "事件", "小怪", "精英"]
        self.default_config["第几层boss前自动暂停"] = "不暂停"
        # self.default_config["从右往左出牌"] = True
        self.node_status = {"shop": False, "flash_or_rest": False, "reach_final_boss": False, "final_boss_battle": False, "pass_final_boss_count": 0, 
                            "total_rounds": 0, "success_rounds": 0, "node_count": 0, "enter_new_node": False, "node_type": "",
                            "is_escaped": False, "save_target_member": False,
                            "removed_card_count": 0, "neutral_card_count": 0}
        self.member_status = {
            "equipment": {
                "names": ["", "", ""],
                "descriptions": ["", "", ""],
                "qualities": ["", "", ""],
            },
            "deck": {},
        }

        self._last_upload_time = 0
        self.config_type = {
            '游戏语言': {'type': 'drop_down', 'options': ['简体中文', '繁体中文']},
            '配置操作': {
                'type': 'button',
                'buttons': [
                    {'text': '导入配置码', 'callback': make_import_callback(self)},
                    {'text': '导出配置码', 'callback': make_export_callback(self)},
                    {'text': '热门配置', 'callback': self._show_hot_configs},
                    {'text': '保存配置', 'callback': make_save_local_config_callback(self, 'sortie')},
                    {'text': '切换配置', 'callback': make_switch_local_config_callback(self, 'sortie')},
                ],
            },
            '第几层boss前自动暂停': {'type': 'drop_down', 'options': ['不暂停', '1', '2', '3']},
        }
        self.config_description['游戏语言'] = "国际服请设置为繁体中文"
        self.config_description[utils_sortie.USE_SANITY] = "每层结算时消耗理智（理性，右上角大脑图标）领取卡厄思战利品；关闭则放弃战利品"
        self.config_description[utils_sortie.SANITY_REFILL] = (
            "领取奖励时理智不够、弹出「补充理性」就点确认，用体力（以太）补充；关闭或体力也不够时放弃补充，回到出击入口页停止"
        )
        self.config_description[utils_sortie.SORTIE_LEVEL] = (
            "出击入口页按左右箭头调到这个等级再进入（例如 80 = V 档）；目标不是整档时停在低一档，0 为不调整"
        )
        self.config_description["速刷模式"] = (
            "选路尽量避开战斗（休息 > 事件 > 普通战 > 精英）；第一层首领打完进第二层，选完第二层首领就退出，算一次成功"
        )
        self.config_description['商店刷新信用点阈值'] = (
            "德朗商店免费刷新次数用完后，仅当信用点大于该值且足够支付刷新价格时才付费刷新。"
        )

    def load_config(self):
        migrate_game_language_config_file(self)
        # 「领取奖励」改名「使用理智领取奖励」（2026-10-27），沿用旧值
        migrate_renamed_config_keys(self, {"领取奖励": utils_sortie.USE_SANITY})
        super().load_config()

    def enable(self):
        """开启出击模式时自动禁用卡厄思模式，重置状态并迁移配置。"""
        from ChaosMode import ChaosMode
        chaos = og.executor.get_task_by_class(ChaosMode)
        if chaos and chaos.enabled:
            chaos.disable()
        reset_all_status(self)
        self._level_adjust = None       # 重新开启：再按配置调一次难度
        self._sanity_exhausted = False
        _migrate_route_boss_to_elite(self)
        super().enable()

    def _check_upload_if_needed(self):
        check_upload_if_needed(self, "sortie")

    def _show_hot_configs(self):
        show_hot_configs_dialog(self, "sortie")

    def run(self):
        self.all_texts = _simplify_texts(self.ocr())
        for handle_page in utils_sortie.PAGE_HANDLERS:
            if handle_page(self):
                return
        # 帧末尾检查是否需要上传配置
        self._check_upload_if_needed()
