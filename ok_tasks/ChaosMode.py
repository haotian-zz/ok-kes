from ok import TriggerTask, og

import json
import os

import chaos_strategy
import chaos_trace
import game_restart
import game_speed
import utils_imprint
import game_db
import ledger_check
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
        self.default_config['卡厄思地图'] = "活动卡厄思"
        self.default_config['刷存档难度'] = 8
        self.default_config['探索度达到多少级后改刷目标卡组'] = 30
        self.default_config['记录流程追踪'] = True
        self.default_config['调整零式升级'] = True
        self.default_config['刷存档开梦境模式'] = True
        self.default_config['刷存档最低PT'] = 130
        self.default_config['刷存档主战员'] = "海德玛丽"
        self.default_config['存储数据保存上限大于多少'] = 120
        self.default_config['保留大于多少TB的存档'] = 62000
        self.default_config['存档满了自动清理'] = True
        self.default_config['存档清理保留空白存档'] = True
        self.default_config['额外战利品：有战利品验证卡就用'] = True
        self.default_config['额外战利品：验证卡用完后用体力兑换'] = True
        self.default_config['额外战利品：体力不足时用免费道具补充体力'] = False
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
        self.default_config[utils.EMPTY_FLASH_LIMIT] = 2
        self.default_config[utils.EMPTY_TARGETS] = []
        self.default_config[utils.EMPTY_OUT_LEFT] = 5
        self.default_config[utils.SAVE_KEEP_MEMBERS] = []
        self.default_config[utils.NEUTRAL_SKIP] = False
        self.default_config[utils.EQUIP_TARGET_FIRST] = False
        self.default_config[utils.FLASH_EQUIP_NOT_TARGET] = False
        self.default_config['优先使用金币治疗'] = True
        self.default_config['治疗崩溃'] = True
        self.default_config['优先移除基础牌'] = True
        self.default_config['进入商店'] = False
        self.default_config['指定面具卡牌'] = "丢弃最多2张卡牌"
        self.default_config['面具卡牌刻印'] = "自身攻击卡牌伤害总量提升30%"
        self.default_config['刷初始卡牌'] = ""
        self.default_config['只打第一层'] = False
        self.default_config['章鱼哥速刷'] = False
        self.default_config['章鱼哥速刷只认混沌之识'] = False
        self.default_config[game_speed.SPEED_KEY] = True
        for key, value in utils_imprint.DEFAULTS.items():
            self.default_config[key] = value
        self.default_config[ledger_check.LEDGER_KEY] = True
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
            '卡厄思地图': {'type': 'drop_down', 'options': ['活动卡厄思', '常驻（探索度→卡厄思具象，刷存档→零式系统）']},
            '刷存档难度': {'min': 0, 'max': 15},
            '刷存档最低PT': {'min': 30, 'max': 180},
            utils.EMPTY_FLASH_LIMIT: {'min': 1, 'max': 5},
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
            '第几层boss前自动暂停': {'type': 'drop_down', 'options': ['不暂停', '1', '2', '3']},
            '存储数据保存上限大于多少': {'min': 0, 'max': 170},
            utils_imprint.SLOT_KEY: {'min': 1, 'max': 3},
            utils_imprint.DIFF_KEY: {'min': 1, 'max': 15},
        }
        self.config_description['游戏语言'] = "国际服请设置为繁体中文"
        self.config_description['卡厄思玩法'] = (
            "探索度：优先没见过的事件选项；刷存档-空存：删光目标主战员的卡，避开闪光/获得卡；"
            "刷存档-目标卡组：按目标主战员的预设构筑删/复制/闪光。选了玩法后删卡、闪光、复制、路线、任务优先级等项自动生成。"
        )
        self.config_description['额外战利品：有战利品验证卡就用'] = "每次打完首领的结算页，每周 4 张免费战利品验证卡有就用来兑换额外战利品"
        self.config_description['额外战利品：验证卡用完后用体力兑换'] = "验证卡用完后用体力兑换额外战利品"
        self.config_description['额外战利品：体力不足时用免费道具补充体力'] = "体力不够兑换时用免费道具补充体力（不会用钻石或付费项）"
        self.config_description['目标预设'] = "目标卡组读主战员详情 → 卡牌 → 预设构筑里的第几号预设"
        self.config_description['队友'] = "自动编队时目标主战员之外的两个人（按槽位顺序）"
        self.config_description['刷存档开梦境模式'] = ("刷存档-目标卡组在配置队伍页打开梦境模式（存档 +1 阶、PT 上限 +10），要队伍里有经历过深层创伤的主战员。"
                                                 "刷存档-空存一律关掉梦境（会提高闪光几率）")
        self.config_description['卡厄思地图'] = (
            "活动卡厄思：主页右下角活动横幅 → 卡厄思（如 2026-10 的「天幕」），探索度打最高难度，刷存档按「刷存档难度」；"
            "常驻：探索度去卡厄思具象探索度最低的区域，刷存档去零式系统法典"
        )
        self.config_description['记录流程追踪'] = (
            "每局把整层地图、选的路线、每次分支的打分和选择、各页面截图存到 dev_out/chaos_trace/<时间>/，"
            "用 tools/chaos_trace_report.py 生成 HTML 复盘；只保留最近 10 次")
        self.config_description['探索度达到多少级后改刷目标卡组'] = (
            "玩法是探索度时，开局在卡厄思入口页读左下角「探索度 等级N」，到这个级数就把玩法改成目标卡组并回主页重新进；0=不切换")
        self.config_description['刷存档难度'] = "活动卡厄思刷存档锁定第几档难度（左侧罗马数字，Ⅰ=1），默认 Ⅷ"
        self.config_description['刷存档最低PT'] = "刷存档时存储数据上限（含梦境 +10）至少多少才进；带出去用过编辑道具上限会变 180。局内按这个上限记 PT 账，绝不爆 PT"
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
        self.config_description[utils.EMPTY_FLASH_LIMIT] = (
            "刷存档-空存：目标卡组里多出这么多张闪光卡（主战员闪光、天赋进场送的、装备给的；三选一卡牌闪光不加新卡不算）"
            "就在第一个航点前逃脱重开，默认 2。另外每个选路页读主战员面板的移除次数和卡组：已删次数 + 卡组里还剩的目标卡"
            "超过 5（一个存档最多记 5 次移除，4 张初始卡也要删）就直接重开。到第一个航点（结算页）存档已存下，直接逃脱，没删完的局外改存档补"
        )
        self.config_description[utils.EMPTY_OUT_LEFT] = (
            "刷存档-空存：到第一个航点时，目标卡组里还要局外改存档补删的张数不超过这个数才算存好（换下一个目标），"
            "超过就逃脱接着刷同一个人。0～5，默认 5（只要已删次数 + 剩下的不超过 5 就算）"
        )
        self.config_description[utils.SAVE_KEEP_MEMBERS] = (
            "存档清理永远保留这些角色的存档（和目标主战员、刷空档目标顺序一样）。刷空档存好一个人的空档会自动加进来，"
            "换了目标顺序上一批的空档也不会被分解"
        )
        self.config_description[utils.EMPTY_TARGETS] = (
            "刷存档-空存按顺序换目标主战员：当前目标到航点存好一个档就换下一个（下一局重新自动编队），最后一个存好就停。"
            "留空就一直刷当前目标。存档清理会保留这些人的存档"
        )
        self.config_description[utils.NEUTRAL_SKIP] = (
            "卡牌分配页（命运、事件给的中立卡/怪物卡）点「跳过」，购买卡牌页点「取消」，谁都不给。"
            "刷空档要开（10-28 开局命运的「觉悟」被默认发给了目标）；要中立卡的玩法关掉"
        )
        self.config_description[utils.EQUIP_TARGET_FIRST] = (
            "装备优先直接给目标主战员：同品质也换上，不管「一个主战员只装一件传说」，只有目标那个位置装着品质更高的才给队友。"
            "刷空档要开（用户 2026-10-28）"
        )
        self.config_description[utils.FLASH_EQUIP_NOT_TARGET] = (
            "描述里带「闪光」的装备（时间调节器「佩戴的主战员触发闪光」）不给目标主战员，按原规则给队友。"
            "刷空档要开：闪光会往目标卡组里塞新卡"
        )
        self.config_description['存档清理保留空白存档'] = (
            "自动清理存档时保留空白存档（0PT）。关掉后空白存档也会被分解；目标主战员的存档始终保留"
        )
        self.config_description['存档满了自动清理'] = (
            "存档存储满了（进不去卡厄思）时去分解页，按分数从低到高分解，腾出 50 个位置；"
            "空白存档（0PT）、目标主战员的存档、读不准的都保留")
        self.config_description['章鱼哥速刷'] = (
            "刷章鱼哥（梦境模式乱入的精英赛内克图斯，掉混沌之识）：第一层打完首领时本局还没拿到目标装备就退出重进（遇到章鱼哥但掉的不是目标装备也一样）；拿到了就照常打完。需要开梦境模式"
        )
        self.config_description['章鱼哥速刷只认混沌之识'] = (
            "配合「章鱼哥速刷」：开启后第一层打完首领时只要本局没拿到混沌之识就退出重进，别的目标装备（堕落之冠、过载动力机关等）不算；不管第几层，章鱼哥掉的不是混沌之识就在回到路线页时立即逃脱重开；关闭时拿到任意目标装备就打完"
        )
        self.config_description[utils_imprint.IMPRINT_KEY] = (
            "刷刻印（配合玩法「刷存档-目标卡组」）：不进赛季卡厄思，从零式系统法典进；法典要地图、难度、赛季特性对上，"
            "稀有命运加成够、没有禁止词条、没有「无法获取存储数据」，不合格就刷新重新合成（先用卡厄思之珠，不够用金币）"
        )
        self.config_description[utils_imprint.SPEEDRUN_KEY] = (
            "刷刻印速刷：第一层打完目标主战员两个不同装备位还没有目标刻印就逃脱重开（章鱼哥掉了混沌之识除外）；"
            "第二层首领打完还没凑齐三个就逃脱重开。逃脱后法典还在，继续用同一个法典"
        )
        self.config_description[utils_imprint.SLOT_KEY] = "刷刻印用零式系统里第几号法典槽位"
        self.config_description[ledger_check.LEDGER_KEY] = (
            "刷刻印：层结束、第二层首领前、逃脱前从路线页打开主战员面板，逐个点刷存档主战员的装备格读名字和刻印，"
            "和脚本记的账对不上以游戏为准；游戏里目标刻印/混沌之识比记的多就不逃脱。结算页不逃脱，回路线页对完账再决定"
        )
        self.config_description[utils_imprint.TARGET_IMPRINT_KEY] = (
            "目标装备刻印：描述里这些关键词都有才算（默认对应「友军使用能力生成5张以上卡牌时，自身额外攻击伤害量+30%」）"
        )
        self.config_description[utils_imprint.MAX_SYNTH_KEY] = "一次任务里最多合成多少次法典，到了还没刷到合格的就停下"
        self.config_description[game_speed.SPEED_KEY] = (
            "国服自带变速：任务开始（和游戏重开后）按一次 F8 唤出「变速功能」浮窗，点 3.0x 再关掉。"
            "F8 只认真实按键，会把游戏切到前台一下再切回原来的窗口"
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
        self.start_window = True
        super().enable()

    def setup_strategy(self):
        """按「卡厄思玩法」算出配置覆盖项；目标卡组读缓存的预设（configs/chaos_target_deck.json）。"""
        mode = self.config.get('卡厄思玩法', chaos_strategy.MODE_LEGACY)
        member = self.config.get('目标主战员', '')
        self.chaos_mode = mode
        self.chaos_plan = None
        # 不分玩法都读：所有玩法选过的选项都记在同一个文件（探索度只算第一次选的选项）
        self.chaos_seen = chaos_strategy.load_seen()
        self.team_checked = False
        self.entry_checked = False
        self.zero_upgrades_checked = False
        self.strategy_ready = True
        if mode in (chaos_strategy.MODE_TARGET, chaos_strategy.MODE_EXPLORE):
            preset = load_target_deck(member, self.config.get('目标预设', 1))
            if preset:
                self.chaos_plan = chaos_strategy.deck_plan(member, preset)
            else:
                self.log_info("目标卡组还没读过预设构筑，开局前会先去读一次")
        overrides = chaos_strategy.config_overrides(mode, member, self.chaos_plan)
        if overrides and member:
            overrides['刷存档主战员'] = member
        self.chaos_overrides = overrides
        if "需要冥想的卡牌" in overrides:
            utils._reset_meditation_state(self)
        if overrides:
            self.log_info(f"卡厄思玩法「{mode}」，自动配置：{overrides}")

    def _prepare_target_deck(self):
        """目标卡组/探索度玩法还没有预设时，在主页先去读一次预设构筑（只读），读完回主页。"""
        if getattr(self, 'chaos_mode', '') not in (chaos_strategy.MODE_TARGET, chaos_strategy.MODE_EXPLORE) \
                or self.chaos_plan is not None:
            return False
        if not (utils_daily.is_home(self) or not self.all_texts):
            return False
        member = self.config.get('目标主战员', '')
        preset = self.config.get('目标预设', 1)
        deck = utils_chaos_prep.read_deck_preset(self, member, preset)
        utils_daily.go_home(self)
        if not deck or not deck.get('cards'):
            if self.chaos_mode == chaos_strategy.MODE_EXPLORE:
                # 探索度不依赖预设：卡牌列表留空（不沿用旧配置），删卡/闪光只认游戏标的图钉
                self.log_error(f"没读到「{member}」的 {preset} 号预设，探索度的删卡/闪光列表留空")
                self.chaos_plan = {}
                self.chaos_overrides = chaos_strategy.config_overrides(self.chaos_mode, member, {})
                self.chaos_overrides['刷存档主战员'] = member
                return True
            self.log_error(f"没读到「{member}」的 {preset} 号预设，目标卡组玩法先按原有逻辑跑")
            self.chaos_mode = chaos_strategy.MODE_LEGACY
            self.chaos_overrides = {}
            return True
        save_target_deck(deck)
        self.setup_strategy()
        self.log_info(f"目标卡组计划：{self.chaos_plan}")
        return True

    def _at_lobby(self):
        """卡厄思难度选择页（局外）：有「每周进展」和「进入」，没有确认/下一步。
        结算后的奖励、存档页也有「每周进展」，确认按钮刚出来时可能还没认出来（2026-10-25 20:11 被当成难度页按了 ESC），
        所以要求同时看到难度页独有的「进入」。"""
        texts = [box.name for box in self.all_texts or []]
        return (any("每周进展" in t for t in texts) and "进入" in texts
                and not any("确认" in t or "下一步" in t for t in texts))

    @staticmethod
    def _out_of_run_page(task):
        """启动第一帧停在这些局外页，要先回主页再进卡厄思（否则会被当成局内页）。"""
        # 用户看完存档停在「存储数据」页就启动了脚本，这页被当成局内事件页连点（2026-10-27 12:02 实录）
        if utils.at_save_library(task):
            return "存储数据页"
        # 冻结时没生效的「进入」被记成了新的一局，重启后当成局内、把赛季页的补给商店当事件连点（2026-10-28 02:12 实录）
        if utils.at_season_hub(task):
            return "卡厄思赛季页"
        # 跨过每日刷新回到主页时先弹「死灵之书每日礼物 / 点击以领取补给」（2026-10-27 12:19 实录），go_home 会点掉
        if utils_daily.has_text(task, r"^点击以领取"):
            return "每日礼物弹窗"
        # 卡厄思大厅（卡厄思具象 / 零式系统两个入口）、零式系统首页：上一轮从主页进卡厄思走到一半被停（2026-10-28 03:12 实录），
        # 重启后「零式系统」被当成事件选项点了，接着走法典合成开错了图
        texts = [b.name for b in getattr(task, "all_texts", None) or []]
        if any("零式系统" in t for t in texts):
            if any("卡厄思具象" in t for t in texts):
                return "卡厄思大厅页"
            if "法典记录" in texts:
                return "零式系统首页"
        return None

    def _start_window_step(self):
        """启动那一刻的局外准备；返回 True 表示本帧动过画面、下一帧还要再判断。
        停在标题页时先点「点击开始」，不能把只做一次的「从主页进卡厄思」判断用在标题页上
        （2026-10-27 22:21 实录：刚开游戏就启动任务，标题页占掉了判断，进主页后被当成故事页，任务自己停了）。"""
        if utils.handle_title_start(self):
            return True
        return self._prepare_target_deck() or self._enter_chaos_from_home()

    def _enter_chaos_from_home(self):
        """选了玩法且停在主页时自己进卡厄思：探索度 → 卡厄思具象探索度最低的区域；刷存档 → 零式系统。失败两次就停下。"""
        mode = getattr(self, 'chaos_mode', chaos_strategy.MODE_LEGACY)
        if mode == chaos_strategy.MODE_LEGACY or self.entry_checked:
            return False
        # 只在启动后第一帧判断：主页（主页闲置会隐藏 UI，整帧没有文字）才自己进卡厄思，已经在卡厄思里就交给原有流程
        self.entry_checked = True
        # 卡厄思难度选择页（有「每周进展」）也在局外：上一轮按轮数停下后就停在这里（2026-10-24 实机），
        # 直接点进入会跳过零式升级和难度选择，所以同样先回主页
        # 结算后的奖励页也有「每周进展」，但带「确认」按钮，要交给页面流程点确认、走存储数据收集（2026-10-25 实录被当成难度页按了 ESC）
        # 第一帧正好在转场（整帧没字）会被当成主页、在局内按 ESC（实录 2026-10-27 03:30 中途重启）：多看几帧再判断
        for _ in range(3):
            if self.all_texts:
                break
            self.sleep(1)
            utils_daily.refresh(self)
        at_lobby = self._at_lobby()
        out_page = self._out_of_run_page(self)
        if not (utils_daily.is_home(self) or not self.all_texts or at_lobby or out_page):
            if not utils_chaos._at_chaos_initial_page(self):
                utils.restore_run_state(self)     # 停在局内：读回 PT 账（中途重启不丢）
            return False
        if out_page:
            self.log_info(f"停在{out_page}（局外），先回主页再按玩法准备")
        if at_lobby or out_page in ("存储数据页", "卡厄思赛季页"):
            # 难度页 → ESC → 活动页 → ESC → 主页；切页有动画，每次 ESC 后等够再判断，免得在主页多按一次 ESC
            if at_lobby:
                self.log_info("停在卡厄思难度选择页（局外），按 ESC 回主页再按玩法准备")
            for _ in range(4):
                if utils_daily.is_home(self):
                    break
                self.send_key("esc")
                self.sleep(3)
                utils_daily.refresh(self)
        if not utils_daily.go_home(self):
            return False
        # 启动那帧停在难度页等局外页时 _prepare_target_deck 不在主页跳过了；回到主页后先读预设再进
        # （2026-10-28 11:02 实录：停在难度页启动，回主页直接进了卡厄思，删卡/闪光列表全空）
        if self._prepare_target_deck():
            self.entry_checked = False
            return True
        self.zero_upgrades_checked = True
        want_zero, want_max = chaos_strategy.zero_upgrade_wants(mode, octopus=self.config.get('章鱼哥速刷') is True) if self.config.get('调整零式升级') else ([], [])
        if utils_imprint.enabled(self):
            # 刷刻印只走零式系统法典（裁决之沼 + 回荡在银河中的歌声），不进赛季卡厄思
            ok = utils_chaos_prep.enter_zero_system(self, want_zero, want_max)
        elif self.config.get('卡厄思地图', '活动卡厄思') == '活动卡厄思':
            if want_zero or want_max:
                utils_chaos_prep.enter_zero_system(self, want_zero, want_max)
            difficulty = None if mode == chaos_strategy.MODE_EXPLORE else \
                chaos_strategy.observe_start_difficulty(self.config.get('刷存档难度'))
            ok = utils_chaos_prep.enter_event_chaos(self, difficulty)
            if ok == "restart":
                return True     # 玩法刚切换，下一帧从难度页回主页按新玩法重新进
            if ok == "stopped":
                return True     # 没选到指定难度，已报错停任务
        elif mode == chaos_strategy.MODE_EXPLORE:
            ok = utils_chaos_prep.enter_chaos_figure(self)
        else:
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

    def on_chaos_lobby(self):
        """活动卡厄思难度页：读探索度等级，到「探索度达到多少级后改刷目标卡组」就切玩法（用户 2026-10-25：
        探索度没到 30 一直打最高难度，到了改刷存档）。切了返回 "restart"。"""
        level = utils_chaos.explore_level(self)
        switch_at = int(self.config.get('探索度达到多少级后改刷目标卡组') or 0)
        self.log_info(f"探索度等级 {level}（{switch_at or '不'}级后改刷目标卡组）")
        if self.chaos_mode != chaos_strategy.MODE_EXPLORE or not switch_at or level is None or level < switch_at:
            return None
        self.log_info(f"探索度 {level} 级 ≥ {switch_at}，玩法改成目标卡组，回主页重新进")
        self.config['卡厄思玩法'] = chaos_strategy.MODE_TARGET
        self.setup_strategy()
        return "restart"

    def _check_upload_if_needed(self):
        check_upload_if_needed(self, "chaos")

    def _show_hot_configs(self):
        show_hot_configs_dialog(self, "chaos")

    def log_info(self, message, *args, **kwargs):
        super().log_info(message, *args, **kwargs)
        chaos_trace.log(self, message)

    def run(self):
        # 每帧执行一次 OCR 并转简体, 供各页面处理函数复用
        self.all_texts = _simplify_texts(self.ocr())
        if os.path.exists(PAUSE_AT_ROUTE_FILE) and utils.is_route_selection_page(self):
            # 开发调试：存在这个文件时停在路线页不点节点，方便探全屏地图
            self.log_info(f"存在 {PAUSE_AT_ROUTE_FILE}，停在路线页")
            self.sleep(3)
            return
        if os.path.exists(PAUSE_AT_LOBBY_FILE) and self._at_lobby():
            # 开发调试：一局打完回到难度页（局外）就停，方便查存档详情、核对 PT
            self.log_info(f"存在 {PAUSE_AT_LOBBY_FILE}，停在局外难度页")
            self.sleep(3)
            return
        if not getattr(self, 'strategy_ready', False):
            game_restart.start_resume_on_restore(self)
            self.setup_strategy()
        if game_speed.ensure_speed(self):
            return
        # 读预设、从主页进卡厄思只在启动那一刻做：之后的无文字帧（战斗开场、加载）不能当成主页
        # （2026-10-24 局内重启后首领战开场被当成主页，点了画面中心、按了 6 次 ESC）
        if getattr(self, 'start_window', True):
            if self._start_window_step():
                return
            self.start_window = False
        # 依次尝试各页面处理函数, 命中(返回 True)即结束本次循环
        # 任务在局内启动时没核对过零式升级：一局结束回到难度页（局外）就回主页补查一次
        if not getattr(self, 'zero_upgrades_checked', True) and self.config.get('调整零式升级') and self._at_lobby():
            self.zero_upgrades_checked = True
            self.entry_checked = False
            if self._enter_chaos_from_home():
                return
        if self.config.get('章鱼哥速刷'):
            if self._at_lobby():
                # 探险结果页列出的战利品（怪异之壳等）会被当成遇到章鱼哥；回到局外难度页就清掉，别带进下一局（2026-10-26 实录）
                utils.clear_octopus_seen(self)
            else:
                utils.note_octopus(self)
        frame = self.frame
        chaos_trace.begin_frame(self)
        for handle_page in utils_chaos.PAGE_HANDLERS:
            if handle_page(self):
                chaos_trace.page(self, handle_page.__name__, frame)
                return
        # 帧末尾检查是否需要上传配置
        self._check_upload_if_needed()


TARGET_DECK_FILE = os.path.join("configs", "chaos_target_deck.json")
PAUSE_AT_ROUTE_FILE = os.path.join("dev_out", "pause_at_route")
PAUSE_AT_LOBBY_FILE = os.path.join("dev_out", "pause_at_lobby")


def load_target_deck(member, preset):
    """读缓存的预设构筑（read_deck_preset 的结果），主战员和预设号对不上就当没有。"""
    try:
        with open(TARGET_DECK_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if data.get("member") != member or int(data.get("preset", 0)) != int(preset):
        return None
    _rematch_unknown_cards(data)
    return data


def _rematch_unknown_cards(deck):
    """缓存里认不出卡名（OCR 错字）的卡重新对一次库：名字纠正后再算闪光变体和神闪。
    2026-10-25：「剑刀破晓」当时没对上「剑刃破晓」，闪光 4 + 神闪没进计划，闪错了也不重闪。"""
    db = game_db.get_db()
    for c in deck.get("cards", []):
        if c.get("n") is not None or chaos_strategy.memory_name(c.get("name", "")):
            continue
        card = db.find_card(c.get("name", ""), owner=deck.get("member"), include_neutral=True)
        if not card:
            continue
        m = db.match_spark(card, c.get("desc", ""))
        c.update(name=card["name"], n=m["n"], god_spark=m["god_spark"])


def save_target_deck(deck):
    os.makedirs(os.path.dirname(TARGET_DECK_FILE), exist_ok=True)
    cards = [{k: c.get(k) for k in ("name", "raw_name", "desc", "n", "god_spark")} for c in deck.get("cards", [])]
    with open(TARGET_DECK_FILE, "w", encoding="utf-8") as f:
        json.dump(dict(deck, cards=cards), f, ensure_ascii=False, indent=1)
