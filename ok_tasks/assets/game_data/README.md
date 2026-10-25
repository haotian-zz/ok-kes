# 卡厄思梦境 国服数据库（game_data）

供 ok-kes 在 OCR 识别游戏内中文后查库：主战员、卡牌（含灵光一闪变体）、神闪/中立闪词条、中立卡、装备。
所有名称和描述都用**国服简中**。生成脚本：`2game-helper/research/czn/build_db.py`（读 `research/czn/raw/`，可重跑）；
gamekee 数据用 `research/czn/fetch_gamekee.py` 重新抓（限速 4 秒/请求；装备图鉴用 `--equipment --delay 2.5`，
同时把图标下到 `equipment_icons/`）。生成日期 2026-10-24。

## 文件和字段

公共约定：UTF-8，`cost` 是整数，或者 `"X"`（X 费）、`"无法使用"`；`desc` 是游戏内显示的纯文本，换行用 `\n`，
wiki 标记、颜色、tooltip 都已去掉。**数值按 1 级卡面**，实机卡面的数字会随等级、潜能变化（例如 斩念 实机显示 伤害112%，库里是 100%），
所以比对时建议把数字替换成通配符再比文字。

### characters.json
- `combatants[]` 主战员：`id`（游戏内 id，如 `30093`；gamekee 补充的写成 `gk_<content_id>`）、`name` 国服名、
  `name_intl` 国际服名（官方繁中 t2s 简化字形）、`nickname`、`class` 职业（前锋/守卫/游侠/猎人/奥义师/操控师）、
  `ego` 属性（热情/正义/秩序/本能/虚无）、`rarity`（星级 4/5）、`faction`、`cn_launch`、
  `start_deck[]` 开局卡组 `{id, count}`（共 8 张，基础攻击一般 2 张）、`source`（bwiki / gamekee）。
- `supporters[]` 辅战员：`id`、`name`、`name_intl`、`class`、`rarity`。

### cards.json — 主战员、辅战员的卡（`cards[]`）
- `id`（如 `c_30093_uni1`；gamekee 补充的写成 `gk_card_<id>`）、`name`、`name_intl`（只在和国服不同时给出）、
  `owner` 角色 id、`sort`（基础卡牌 / 独特卡牌 / 主战员EGO技能 / 辅战员EGO技能 / 可生成卡牌…）、`rarity`、`ego`、`class`、
  `cost`、`type`（攻击/技能/强化…）、`talents` 卡面上方 [ ] 里的天赋（中文，如 `["唯一","开战"]`）、`desc`。
- `start_deck`：在开局卡组里的张数；`links`：关联/衍生卡 id。
- `sparks[]`：**灵光一闪（闪光）专属变体**，固定 5 个，`n` 1~5 对应 bwiki `_rsp1`~`_rsp5`（gamekee 按条目顺序，已和 bwiki 对过一致）。
  每个变体：`id`、`cost`、`type`（只在和基础卡不同时给出，例如 剑刃破晓 的第 5 个闪光变成技能卡）、`talents`、`desc`（变体完整文本），
  以及判断用的差异字段：`changes`（bwiki 用绿/红色高亮标出的改动片段）、`cost_delta`（费用差，如 -1）、
  `talents_added` / `talents_removed`。
- `potential`：潜能强化后的卡面（`_pot`）；`ego_manifest`：自我意识突破后的卡面（`_lbk`）。结构同变体。
- `god_sparks`：这张卡可能出现的神闪词条 id（对应 god_sparks.json 的 `god[]`），按 bwiki 的过滤规则用基础卡计算。
  `god_sparks_approx: 1` 表示 gamekee 来源的卡缺 spark_tag，「护盾类 / 治愈类 / 取对象」这几条词条没法过滤，结果偏多。
- 匹配用的原始字段：`spark_enable`（可出中立闪）、`spark_tag`、`talent_ids`（TALENT_* 原 id）。

闪光判断建议：先按卡名（OCR 后，国际服客户端可再比 `name_intl`）找到卡，再把 3 选 1 每个选项的描述和 `sparks[].desc` 比，
差异最大的地方看 `changes`/`cost_delta`/`talents_added`；对不上任何专属变体时，就是「原效果 + 一条中立闪/神闪词条」，
去 god_sparks.json 的 `public` / `god` 里找追加的那一行。

### god_sparks.json — 闪光词条池
- `categories`：各类别含义（中文说明，和下面一致）。
- `god[]` 神之一闪（神闪）30 条：`god` 为 `通用`（15 条，所有神共用）或神名（卡利戈、基尔肯、迪亚洛斯、尼希勒姆、瑟克洛斯、维托尔 各 3 条）。
  神闪卡 = 1 个灵光效果 + 1 条神闪词条；闪光 3 选 1 里最多 1 个带神闪；已闪光过的卡不能再神闪。
- `public[]` 中立闪光 313 条：在原效果上追加 1 条，按 费用/类型/职业/天赋/spark_tag 过滤（3 费最高档，4 费以上按 2 费档）。
  适用于 `spark_enable=1` 的卡（中立卡、角色独特卡）；角色独特卡闪光时的选项来自「5 个专属变体 + 符合条件的中立闪」。
- `assault[]` 出击模式专用神闪池 62 条（按神分组）。
- `eidolon[]` 人格面具卡的刻印 38 条（`imprint` 光之刻印 / 暗之刻印，`add` 附加费用/天赋）。
- 每条：`id`、`desc`、`filters`（`cost_min`/`cost_max`、`card_category`、`card_class`、`talent`/`exclude_talent`、
  `spark_tag`/`exclude_spark_tag`，列表任一命中即可）、`add_talent`。
- 禁忌卡不是闪光类别，是 neutral_cards.json 里 `sort=禁忌卡牌` 的中立卡。

### neutral_cards.json — 非角色卡（`cards[]`）
字段同 cards.json（没有 owner），`sort` 区分：中立卡牌 250、怪物卡牌 85、欲望卡牌 64、状态异常 42、咒术卡牌 32、
人格面具 20、禁忌卡牌 7、竞技场/任务/闯入事件卡牌若干。有变体的同样带 `sparks`/`potential`/`ego_manifest`。

### equipment.json
- `equipment[]` 491 件（bwiki 475 + gamekee 补 16 件新赛季「天上防护墙」装备）：
  - `id`（bwiki 的游戏内 id，如 `eq_pub_038`；gamekee 补充的写成 `gk_eq_<content_id>`）、`name` 国服名、`name_intl`（不同时）、
    `slot`（1 武器 / 2 防具 / 3 饰品；gamekee 的「护甲」统一记成 `slot=2`、`slot_name="防具"`）、`slot_name`、
    `rarity`（普通 / 稀有 / 传说 / 独特；gamekee 的「神话」= 独特，按已配对条目 36/36 一致换算）、`desc`、
    `stat` + `stat_values`（主属性 1~5 级数值）、`area` 掉落区域、`season`（S1~S4）、`mode: "出击"`（出击模式专用的 `_ca_` 版本）、`assault_type`。
  - `source`：`bwiki` / `gamekee`。gamekee 新增的条目没有 `area`/`season`，文本是 gamekee 编辑录入的，措辞可能和国服有出入。
  - gamekee 图鉴补充字段（和 bwiki 对上的条目也有）：`gk_content_id`（gamekee 页面 id，页面 `https://www.gamekee.com/czn/<content_id>.html`）、
    `name_gamekee`（gamekee 用的名字，和 `name`/`name_intl` 都不同时给出，例如 混沌之识 在 gamekee 叫 混沌指控 = `name_intl`、
    碎珀蘑菇 叫 帕格纳蘑菇）、`rarity_gamekee`（神话/传说/稀有）、`obtain` 获取来源（如「梦境模式限定：击杀赛内克图斯」「天上防护墙」
    「第0研究所：事件-矿脉之心」）、`season_name` gamekee 标的赛季名（如 禁忌催化剂、雪上凝结的约定）、
    `desc_gamekee`（gamekee 效果文本和 bwiki 不一样时给出，多为译法差异）。
  - `icon`：本地图标相对路径（相对 game_data/），如 `equipment_icons/gk_683031.png`，124×124 PNG，来自 gamekee 图鉴；
    出击版（`_ca_`）共用普通版的图标。没有图标的：时间调节器（gamekee 图鉴没收录）和它对应的出击版等 47 件出击专用装备。
- `equipment_icons/`：`gk_<gk_content_id>.png`，249 张（gamekee 图鉴全部条目；`gk_683913.png` 是 gamekee 重复录入的 群体之翼，库里不引用）。
- `memory_fragment_sets[]` 记忆碎片套装 18 个：`id`、`name`、`set`（2/4 件）、`desc`。

## 来源
| 数据 | 来源 |
|---|---|
| 主战员、卡牌、闪光变体、天赋名 | biligame 卡厄思梦境 WIKI（国服）：`Card:<id>` 页 `{{Cards}}` 模板导出、战员页 `{{Combatant}}`、模块 Tooltip/data |
| 神闪 / 中立闪 / 出击 / 刻印 | bwiki 模块 Spark/god、public、assault、eidolon |
| 装备 | bwiki「装备图鉴」渲染页（国服文本；Lua 模块 Relic/data 里部分是国际服旧文本，只作兜底） |
| 新赛季装备、装备来源、图标 | gamekee 装备图鉴 `/v1/entry/treesByPid?pid=197411` + 每件正文 `api-cdn.gamekee.com/wiki2.0/pro/50388/content/<id>.json`；按名字（name/name_intl，出击版国际服名去前缀）配对，配不上再按部位+1~5 星数值+效果相似度兜底（24 件，都是同物异译），配对清单在 `research/czn/build_db_stats.json` 的 `gamekee_equipment` |
| 记忆碎片 | bwiki 模块 Piece/data |
| 国际服名 | NineS11942/ChaosZero-Toolkit 官方繁中全文本（t2s），经 `research/czn/tw_cn_map.csv` |
| bwiki 没有的新角色 | gamekee `/v1/entryCard/query-list`（卡牌 + 灵光一闪条目）、角色页正文 |

## 覆盖率（2026-10-24）
- 主战员 39：bwiki 35 + gamekee 补 4（罗丝薇瑟、安妮卡、奥尔加、阿拉贝拉）；39/39 开局卡组完整，39/39 有 4 张带 5 个闪光变体的卡。辅战员 47。
- 角色卡 488（主战员 442），有闪光变体的卡 156，变体 780 个；bwiki 来源的 700 个变体里 672 个带高亮差异，其余靠天赋/费用差区分（只有 1 个三者都没有）。
- 神闪 30、中立闪 313、出击 62、刻印 38；中立等非角色卡 514；装备 491（bwiki 475 + gamekee 16，444 件带图标）；记忆碎片套装 18。
- gamekee 装备图鉴 249 条：232 条对上 bwiki（名字 208 + 兜底 24），16 条新增（全是「天上防护墙」来源），1 条重复录入跳过。
- 和 gamekee 交叉核对：35 个重合角色的 140 张闪光卡里，134 张 5 个变体的费用和 bwiki 一致；3 张费用不同（卢克 隐密上膛、凯隆 虚无之残相、
  特莱莎 暗袭要害，可能是两服数值不同步，以 bwiki 国服为准），3 张因名字差异没对上。
- 抽查：海德玛丽（bwiki 线上页 8 张卡与库一致；万众英雄 5 个变体和 gamekee 逐条语义一致）、九（老练一击 5 个变体与 gamekee 一致）、
  希露德（抽取&释放 5 个变体顺序/费用/类型一致）、罗丝薇瑟（对照国服实机截图：斩念/入鞘/明灭剑/剑鸣九霄/剑刃破晓/循环之刃/基尔肯的神眷者，
  剑鸣九霄「抽取1张自身卡牌」、循环之刃「纯粹：生成2张剑穗加入手牌」、剑刃破晓「手牌中每有1张正义卡牌…」都在 sparks 里；
  截图里的神闪「此卡费用减少1」「必定触发弱点攻击」在对应卡的 god_sparks 里）。

## 已知缺口
- gamekee 补的 4 个角色：卡面文字是 gamekee 编辑录入的，措辞和国服可能有出入（例如 循环之刃 变体写成「剑髓」，实机是「剑穗」），
  没有 `changes` 高亮、`spark_tag`，没有潜能/自我意识变体；卡牌 id 是 gamekee 的，不是游戏内 id；`name_intl` 为空。
  安妮卡、奥尔加、阿拉贝拉还没对照国服截图。bwiki 收录后重跑 build_db.py 会自动改用 bwiki（按名字或卡名重合判断同一角色）。
- `god_sparks` 用基础卡计算，没有对每个闪光变体单独算；神闪对 X 费、无法使用按 0 费处理。
- 天赋 `TALENT_SURVIVAL`（欲望卡 15 张）、`TALENT_IRREMOVABLE`（1 张）在 bwiki 没有中文名，原样保留 id。
- 9 张角色卡在 bwiki 没有描述（多为无法使用的衍生卡）。
- 个别 bwiki 字段是玩家录入，可能有笔误（如 九 的 cn_launch 写成 2025 年）。
- 国际服名（`name_intl`）来自 2026-05 的国际服文本，之后的新卡没有。
