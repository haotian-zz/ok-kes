from ok import TriggerTask, og

import json
import os

import chaos_strategy
import utils
import utils_chaos
import utils_chaos_prep
import utils_daily
from config_io import (
    make_export_callback,
    make_import_callback,
    make_save_local_config_callback,
    make_switch_local_config_callback,
    migrate_flash_priority_config_file,
    migrate_game_language_config_file,
)
from config_sync import check_upload_if_needed, show_hot_configs_dialog
from utils import (
    reset_all_status,
    _migrate_route_boss_to_elite,
    _simplify_texts,
)

class ChaosMode(TriggerTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "自动卡厄思模式"
        self.description = "1. 战斗中自动战斗没开时会自动点开；自动剧情请主动打开。\n2. 国际服玩家请将本模式配置中的\"游戏语言\"设置为繁体中文。"
        self.instructions = """<a href="https://github.com/ok-oldking/ok-py">ok-py</a>"""
        self.trigger_interval = 1
        self.all_texts = []
        # 默认关闭，由用户在界面中手动启停，保持 TriggerTask 自己作为主任务运行
        self.default_config['_enabled'] = False
        self.default_config['配置操作'] = ""
        self.default_config['游戏语言'] = "简体中文"
        # 玩法：原有逻辑＝按下面各项配置走；其他玩法会自动推出删卡/闪光/复制/路线/事件等配置，覆盖下面对应的项
        self.default_config['卡厄思玩法'] = chaos_strategy.MODE_LEGACY
        self.default_config['目标主战员'] = "罗丝薇瑟"
        self.default_config['目标预设'] = 1
        self.default_config['队友'] = ["海德玛丽", "米卡"]
        self.default_config['自动编队'] = True
        self.default_config['调整零式升级'] = True
        self.default_config['刷存档主战员'] = "海德玛丽"
        self.default_config['存储数据保存上限大于多少'] = 120
        self.default_config['保留大于多少TB的存档'] = 62000
        self.default_config['领取奖励(只使用验证卡)'] = False
        # 事件任务优先级列表, 匹配到包含对应文字的选项时会优先选择
        self.default_config['任务优先级'] = ["复制","信用点增加", "移除"]
        self.default_config['拉黑任务'] = ["咒术卡牌", "压力"]
        # 闪光卡牌优先级配置，按列表顺序匹配卡牌名称与描述的组合文本
        self.default_config['闪光优先级'] = [
            "剑雨感应：生成2张极光剑",
            "剑雨赋予其回收",
            "缕光芒80%",
            "缕光芒216%",
            "展开极光70%",
            "展开极光安息唯一",
            "展开极光200%",
        ]
        # 卡牌策略配置 (列表)
        self.default_config['移除卡牌列表'] = ["剑幕", "剑光", "水之伞", "海潮的庇护", "作战分析"]
        self.default_config['闪光卡牌列表'] = ["展开极光", "剑雨", "缕光芒", "一缕光芒", "万众英雄"]
        self.default_config['复制卡牌列表'] = ["展开极光", "剑雨", "缕光芒", "一缕光芒", "万众英雄"]
        self.default_config['需要冥想的卡牌'] = ["剑雨", "展开极光"]
        self.default_config['多少信用点以上冥想'] = 300
        self.default_config['商店刷新信用点阈值'] = 300
        self.default_config['装备1号位优先级'] = ["蚀化臂铠"]
        self.default_config['装备2号位优先级'] = ["拷问工具箱"]
        self.default_config['装备3号位优先级'] = ["异象石碑"]
        self.default_config['卡牌奖励优先级'] = ["梦之边境"]
        self.default_config['指定记忆卡牌'] = ""
        self.default_config['首层刷特定闪光'] = False
        self.default_config['刷空档'] = False
        self.default_config['优先使用金币治疗'] = True
        self.default_config['治疗崩溃'] = True
        self.default_config['优先移除基础牌'] = True
        self.default_config['进入商店'] = False
        self.default_config['指定面具卡牌'] = "丢弃最多2张卡牌"
        self.default_config['面具卡牌刻印'] = "自身攻击卡牌伤害总量提升30%"
        self.default_config['刷初始卡牌'] = ""
        self.default_config['只打第一层'] = False
        # 路线节点优先级 (列表), 越靠前优先级越高
        self.default_config['路线优先级'] = ["休息", "事件", "小怪", "精英"]
        self.default_config['几轮后停止(0为不停止)'] = 0
        self.default_config['第几层boss前自动暂停'] = "不暂停"
        self.node_status = {"shop": False, "flash_or_rest": False, "reach_final_boss": False, "final_boss_battle": False, "pass_final_boss_count": 0, 
                            "total_rounds": 0, "success_rounds": 0, "node_count": 0, "enter_new_node": False, "node_type": "",
                            "is_escaped": False, "save_target_member": False,
                            "target_mask_card_position": -1,
                            "get_specific_flash": False,
                            "precision_memory_visited": False,
                            "removed_card_count": 0,
                            "neutral_card_count": 0}
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
            '卡厄思玩法': {'type': 'drop_down', 'options': chaos_strategy.MODES},
            '目标预设': {'min': 1, 'max': 3},
            '配置操作': {
                'type': 'button',
                'buttons': [
                    {'text': '导入配置码', 'callback': make_import_callback(self)},
                    {'text': '导出配置码', 'callback': make_export_callback(self)},
                    {'text': '热门配置', 'callback': self._show_hot_configs},
                    {'text': '保存配置', 'callback': make_save_local_config_callback(self, 'chaos')},
                    {'text': '切换配置', 'callback': make_switch_local_config_callback(self, 'chaos')},
                ],
            },
            '第几层boss前自动暂停': {'type': 'drop_down', 'options': ['不暂停', '1', '2']},
            '存储数据保存上限大于多少': {'min': 0, 'max': 170},
        }
        self.config_description['游戏语言'] = "国际服请设置为繁体中文"
        self.config_description['卡厄思玩法'] = (
            "探索度：优先没见过的事件选项；刷存档-空存：删光目标主战员的卡，避开闪光/获得卡；"
            "刷存档-目标卡组：按目标主战员的预设构筑删/复制/闪光。选了玩法后删卡、闪光、复制、路线、任务优先级等项自动生成。"
        )
        self.config_description['目标预设'] = "目标卡组读主战员详情 → 卡牌 → 预设构筑里的第几号预设"
        self.config_description['队友'] = "自动编队时目标主战员之外的两个人（按槽位顺序）"
        self.config_description['调整零式升级'] = (
            "刷存档玩法从主页进零式系统时，先把升级调好：高维启示 0 级；认知闪光空存 0 级、目标卡组满级。"
            "要降级时会「全部重置」（花 10 个货币，材料全部返还）再把其他项升满"
        )
        self.config_description['闪光优先级'] = (
            "卡牌名称和描述无需完整填写，输入几个关键字即可，但顺序须与游戏原文一致。"
        )
        self.config_description['刷初始卡牌'] = (
            "填写目标卡牌名称后反复刷新初始卡牌；不能与“刷空档”同时使用。"
        )
        self.config_description['刷空档'] = (
            "初始任务必须包含“移除2张”，否则重新开始；不能与“刷初始卡牌”同时使用。"
        )
        self.config_description['首层刷特定闪光'] = (
            "默认刷闪光优先级第一张，可刷神闪，第一层没刷出自动逃脱"
        )
        self.config_description['商店刷新信用点阈值'] = (
            "德朗商店免费刷新次数用完后，仅当信用点大于该值且足够支付刷新价格时才付费刷新。"
        )

    def load_config(self):
        migrate_flash_priority_config_file(self)
        migrate_game_language_config_file(self)
        super().load_config()

    def enable(self):
        """开启卡厄思模式时自动禁用出击模式，重置状态并迁移配置。"""
        from SortieMode import SortieMode
        sortie = og.executor.get_task_by_class(SortieMode)
        if sortie and sortie.enabled:
            sortie.disable()
        reset_all_status(self)
        _migrate_route_boss_to_elite(self)
        self.strategy_ready = False
        super().enable()

    def setup_strategy(self):
        """按「卡厄思玩法」算出配置覆盖项；目标卡组读缓存的预设（configs/chaos_target_deck.json）。"""
        mode = self.config.get('卡厄思玩法', chaos_strategy.MODE_LEGACY)
        member = self.config.get('目标主战员', '')
        self.chaos_mode = mode
        self.chaos_plan = None
        self.chaos_seen = chaos_strategy.load_seen() if mode == chaos_strategy.MODE_EXPLORE else set()
        self.team_checked = False
        self.entry_checked = False
        self.strategy_ready = True
        if mode == chaos_strategy.MODE_TARGET:
            preset = load_target_deck(member, self.config.get('目标预设', 1))
            if preset:
                self.chaos_plan = chaos_strategy.deck_plan(member, preset)
            else:
                self.log_info("目标卡组还没读过预设构筑，开局前会先去读一次")
        overrides = chaos_strategy.config_overrides(mode, member, self.chaos_plan)
        if overrides and member:
            overrides['刷存档主战员'] = member
        self.chaos_overrides = overrides
        if overrides:
            self.log_info(f"卡厄思玩法「{mode}」，自动配置：{overrides}")

    def _prepare_target_deck(self):
        """目标卡组玩法还没有预设时，在主页先去读一次预设构筑（只读），读完回主页。"""
        if getattr(self, 'chaos_mode', '') != chaos_strategy.MODE_TARGET or self.chaos_plan is not None:
            return False
        if not (utils_daily.is_home(self) or not self.all_texts):
            return False
        member = self.config.get('目标主战员', '')
        preset = self.config.get('目标预设', 1)
        deck = utils_chaos_prep.read_deck_preset(self, member, preset)
        utils_daily.go_home(self)
        if not deck or not deck.get('cards'):
            self.log_error(f"没读到「{member}」的 {preset} 号预设，目标卡组玩法先按原有逻辑跑")
            self.chaos_mode = chaos_strategy.MODE_LEGACY
            self.chaos_overrides = {}
            return True
        save_target_deck(deck)
        self.setup_strategy()
        self.log_info(f"目标卡组计划：{self.chaos_plan}")
        return True

    def _enter_chaos_from_home(self):
        """选了玩法且停在主页时自己进卡厄思：探索度 → 卡厄思具象探索度最低的区域；刷存档 → 零式系统。失败两次就停下。"""
        mode = getattr(self, 'chaos_mode', chaos_strategy.MODE_LEGACY)
        if mode == chaos_strategy.MODE_LEGACY or self.entry_checked:
            return False
        # 只在启动后第一帧判断：主页（主页闲置会隐藏 UI，整帧没有文字）才自己进卡厄思，已经在卡厄思里就交给原有流程
        self.entry_checked = True
        if not (utils_daily.is_home(self) or not self.all_texts):
            return False
        if not utils_daily.go_home(self):
            return False
        if mode == chaos_strategy.MODE_EXPLORE:
            ok = utils_chaos_prep.enter_chaos_figure(self)
        else:
            want_zero, want_max = chaos_strategy.zero_upgrade_wants(mode) if self.config.get('调整零式升级') else ([], [])
            ok = utils_chaos_prep.enter_zero_system(self, want_zero, want_max)
        if ok:
            self.enter_failures = 0
            return True
        self.enter_failures = getattr(self, 'enter_failures', 0) + 1
        self.log_error(f"从主页进入卡厄思失败（第{self.enter_failures}次）")
        utils_daily.go_home(self)
        if self.enter_failures >= 2:
            self.disable()
        else:
            self.entry_checked = False
        return True

    def _check_upload_if_needed(self):
        check_upload_if_needed(self, "chaos")

    def _show_hot_configs(self):
        show_hot_configs_dialog(self, "chaos")

    def run(self):
        # 每帧执行一次 OCR 并转简体, 供各页面处理函数复用
        self.all_texts = _simplify_texts(self.ocr())
        if os.path.exists(PAUSE_AT_ROUTE_FILE) and utils.is_route_selection_page(self):
            # 开发调试：存在这个文件时停在路线页不点节点，方便探全屏地图
            self.log_info(f"存在 {PAUSE_AT_ROUTE_FILE}，停在路线页")
            self.sleep(3)
            return
        if not getattr(self, 'strategy_ready', False):
            self.setup_strategy()
        if self._prepare_target_deck() or self._enter_chaos_from_home():
            return
        # 依次尝试各页面处理函数, 命中(返回 True)即结束本次循环
        for handle_page in utils_chaos.PAGE_HANDLERS:
            if handle_page(self):
                return
        # 帧末尾检查是否需要上传配置
        self._check_upload_if_needed()


TARGET_DECK_FILE = os.path.join("configs", "chaos_target_deck.json")
PAUSE_AT_ROUTE_FILE = os.path.join("dev_out", "pause_at_route")


def load_target_deck(member, preset):
    """读缓存的预设构筑（read_deck_preset 的结果），主战员和预设号对不上就当没有。"""
    try:
        with open(TARGET_DECK_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if data.get("member") != member or int(data.get("preset", 0)) != int(preset):
        return None
    return data


def save_target_deck(deck):
    os.makedirs(os.path.dirname(TARGET_DECK_FILE), exist_ok=True)
    cards = [{k: c.get(k) for k in ("name", "raw_name", "desc", "n", "god_spark")} for c in deck.get("cards", [])]
    with open(TARGET_DECK_FILE, "w", encoding="utf-8") as f:
        json.dump(dict(deck, cards=cards), f, ensure_ascii=False, indent=1)
