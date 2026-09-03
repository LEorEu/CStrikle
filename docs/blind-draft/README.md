# Blind Draft

> 用 $15 在身份不完全公开的情况下签 5 名职业选手，组一支临时战队，
> 再让它去打一届真实的 Major。

**现在做到哪：** 选人这一层已经可玩（命令行 + 网页原型，十五局真人试玩），
比赛引擎的 32 队 Major / 三段瑞士轮也已跑通。但当前开发重点不是继续扩系统，
而是把**玩家卡 → AI 当前卡 → 极简 Run → Reveal**接成同一条可解释的体验。

AI 页面、Major 与 Match 现已统一使用队伍快照和同一份逐维 AI 当前卡；
当前权威执行顺序见 **[开发主线.md](开发主线.md)**。

## 按这个顺序读

| # | 文档 | 是什么 | 什么时候看 |
|---|---|---|---|
| 1 | [开发主线.md](开发主线.md) | 当前产品目标、里程碑、明确不做什么 | **决定下一步做什么时只看这份** |
| 2 | [系统地图_v0.1.md](系统地图_v0.1.md) | 整个模式按模块拆开，每块标了状态：✅ 冻结 / 🟡 待调 / 🧪 测试桩 / 🔵 待做 / ❓ 开放 | 想知道某件事归哪一层 |
| 3 | [玩法蓝图_v0.2.md](玩法蓝图_v0.2.md) | 最初的正式设计稿。Grade / Price / Power 的分离、生涯代表版本评价、位置权重都出自这里 | 想知道某条规则的原始意图 |
| 4 | [卡牌与落地记录.md](卡牌与落地记录.md) | 选手卡怎么生成（v7：火力已与 Grade 解耦）、实现时和蓝图差在哪、用真实数据核对的数字 | 要改卡库或生成器之前 |
| 5 | [原型实测记录.md](原型实测记录.md) | 真人试玩记录，每条结论后面跟着产生它的那组数字和复算方法 | 想知道某个参数为什么是现在这个值 |
| 6 | [比赛引擎_v0.3.md](比赛引擎_v0.3.md) | **比赛数值层的当前权威**：四维各做一件事、Map Residual 取代胜负骰、Entry 不再静态计入 L/E/S | **动比赛数值之前只看这份** |
| 7 | [回合引擎_v0.1.md](回合引擎_v0.1.md) | **未来设计，暂不接入**：把一张图的黑箱结果展开成回合过程——实时比分、Kill Feed、K/D/A、ADR、KAST、Match Rating。依赖 v0.3 | 想做实时比分或观赛叙事时 |
| 8 | [比赛引擎_v0.1.md](比赛引擎_v0.1.md) | 上一版：把五个人放进一届真实 Major 的瑞士轮，以及当时的验证记录。赛事外壳仍然有效，数值层已被 v0.3 取代 | 看赛制/瑞士轮，或考古某个旧参数 |
| 9 | [数据快照.md](数据快照.md) | AI 对手的「现在」从哪来：五个数据源各管什么、怎么刷新、踩过哪些坑 | 要重抓数据、或怀疑阵容/排名不对时 |
| 10 | [评审_GPT_比赛引擎.md](评审_GPT_比赛引擎.md) | 第三方复核比赛引擎 v0.1 | 想知道某个结论被质疑过没有 |
| 11 | [火力解耦_v0.1.md](火力解耦_v0.1.md) | 用 5E 实测把 Firepower 从 Grade 的模板里解放出来 | 要改火力这一维时 |
| 12 | [FribergCS2_Draft_四维重构工作指南_v0.1.md](FribergCS2_Draft_四维重构工作指南_v0.1.md) | v7 重构的执行口径 | 动四维之前 |
| — | [1.txt](1.txt) | 比赛引擎两轮复盘的原始讨论，v0.3 就是从这里收敛出来的 | 考古某条口径为什么这么定 |
| — | [2.txt](2.txt) | 第三轮复盘：VRS 与 Entry 是两把尺、Projected VRS 的方向、以及「加审计而不是继续改规则」 | 想知道资格层为什么这么设计 |
| — | [major赛制.txt](major赛制.txt) | 真实 Major 赛制资料 | 核对赛事外壳 |
| — | [原始讨论_ChatGPT.md](原始讨论_ChatGPT.md) | 整个模式的原始素材，从看线上站点开始聊起 | 考古 |

**第 4 份是按时间顺序写的**，二 / 三 / 五节是 v1 / v2 当时的状态，不是现状；
现状在六 / 七 / 八节。

## 代码在哪

整个模式住在 `apps/blind_draft/`，是一个叫 `blinddraft` 的包；抓数据的工具在
隔壁 `bdtools`。它只依赖共享底座 `playerdb`，**不碰猜选手那一侧**——这条边界
由 `tests/test_architecture.py` 盯着。整体分层见 [../架构.md](../架构.md)。

| 模块 | 管什么 | 产出 |
|---|---|---|
| `blinddraft.cards` | 玩家卡生成器（生涯代表版本） | `data/blind_draft/draft_cards.json`（v7，已提交） |
| `blinddraft.draft` | 命令行原型，选人这一层的全部逻辑都在这 | — |
| `blinddraft.major` | 赛场层：赛场从哪来、Entry Rating 怎么算。**不管怎么打** | — |
| `blinddraft.ai_teams` | AI 对手：队伍快照 + 当前角色 + 逐维当前化 | — |
| `blinddraft.proto_match_v2` | **比赛引擎**：实现设计稿 v0.3，四维各干一件事、一图 11 个随机数（10 Player + 1 Map Residual），并按区域 VRS 名额跑完整的 Road to Major。赛事外壳（插队、Swiss、三段串联）也在这里 | — |
| `bdtools.fetch_rankings` | 队伍快照（阵容+位置+HLTV/VRS 排名）、5E 选手照片与队标 | `team_snapshot.json`、`5e_images.json`、`img/` |
| `bdtools.fetch_5e_stats` | 5eplay 当前个人竞技数据 | `5e_player_stats.json` |
| `bdtools.export_web` | 把卡和常量注进网页模板 | `.cache/proto_draft_web.html` |
| `bdserver.main` | **调参后台**：卡牌页（改人工层、看推导、发布） | 写 `draft_overrides.json` |
| `bdserver.ai` | 后台的 AI 对手页装配：卡面 / 现况 / 5E 实测三列并排 | 只读 |
| `bdserver.anchor` | **火力打锚台**：人工给可信的现役选手定 1–99 这把尺子 | 写 `firepower_anchors.json` |
| `playerdb.build_db` | 重建选手库（共享层，`--refresh-existing` 只刷新当前队/角色） | `data/players.json` |

人工层都在 `data/blind_draft/` 下：`major_field.json`（赛场来源、固定几支、
权重、阵容、磨合度上限）、`5e_aliases.json`（卡库昵称 → 5eplay 名字/id）、
`team_roles.json`、`draft_overrides.json`、`firepower_anchors.json`（火力锚点）。

测试在 `apps/blind_draft/tests/`：`test_anchor.py` 12 项，盯着打锚台的口径
（peak 与 firepower 不许混、键必须真实存在、指挥不给建议值）；
`test_cards.py` 11 项，盯着卡库、确定性取整、快照年龄、已发布文件与
「卡牌与落地记录.md」里的 SPEC 块不许漂移；`test_tuning_console.py` 10 项，
盯着后台展示的推导和卡上的数不许对不上；`test_ai_view.py` 19 项，盯着
AI 页与 Match 共用同一份阵容、四维和来源口径；`test_star_visibility.py` 8 项，
盯着比赛叙事认得出谁是核心（F96 的 MVP 率必须明显高过 F50）、Carry 权重由卡面
定死、逐人归因逐项加得回 delta。

## 调参后台

```powershell
uvicorn bdserver.main:app --host 127.0.0.1 --port 8621
```

本地工具，不上线。地址栏支持两个快捷入口：卡牌页 `#<page>` 直接定位到那张卡
（选中时会写回地址栏，可以把链接发给别人）；AI 页 `#all` 一次展开候选池全部 45 支队。

玩家体验入口是 `http://127.0.0.1:8621/play`：选满五人后进入真实三段 Swiss Run。
**这一页已经切到 Match Engine v2**（`blinddraft.proto_match_v2`，设计稿 v0.3）——
Entry 是纯火力口径、Stage 由区域 VRS 名额决定、没有「赛前胜率」这一项
（胜率只能实测，不能解析算）。

左边 648 张卡可搜可筛，右边把选中那张摊开成
**模板 → 履历修正 → 抖动 → 人工覆盖 → 最终值**，附带背后的证据
（Top20 履历、指挥荣誉分、Major 深度、年龄）。

三条它必须遵守的规矩，都是从 `blinddraft/cards.py` 的注释里继承来的：

- **只写人工层，不写生成物。** 后台改的是 `draft_overrides.json`；
  `draft_cards.json` 永远由 `cards.generate()` 产出。手填进生成物的数会在
  下一次 `--write` 时**静默**消失。
- **每次请求实时重算**（全库 0.15s），所以页面显示的就是生成器算的。
  反过来说，已提交的 `draft_cards.json` 会和实时结果不一致——顶栏那个
  「待发布 N」就是专门盯这个差的，点开能看到每张卡差在哪、为什么差。
- **覆盖必须填理由**（§21 Algorithm First, Override Last）。空理由的写入
  会被拒。留不下理由的覆盖，三个月后没人敢删，算法就这么被一点点架空。

顶栏还常驻全库分布（各位置 / 各档的 overall 中位数）——调一张卡很容易把
整档带歪，这组数以前得手写脚本才算得出来。

### AI 对手页（`/ai`，只读）

**这一页故意不给编辑入口。** 卡牌那边人工层是主角（算法算错了要有出口）；
这边相反：AI 的“当前实力”现在由统一生成器逐维投影。`team_snapshot.json`
决定真实首发和当前位置，`5e_player_stats.json` 的近 12 个月 S 级数据接管当前
Firepower；其余维度保留带置信度的生涯先验。在有证据的地方开一个手调数值的
口子，等于把刚拿到的证据又换回骰子。

所以它的职责是**把三列摆在一起**，审计当前投影：

| 列 | 是什么 | 来源 |
|---|---|---|
| 卡面 | 生涯巅峰，玩家抽到的那张 | `blinddraft/cards.py` |
| 现况 | AI 实际使用的逐维当前卡（含来源与置信度） | `blinddraft/ai_teams.py` |
| 5E 实测 | rating / ADR / KAST / K-D / KPR / DPR / HS%，近 12 个月 | `bdtools/fetch_5e_stats.py` |

5E 当前数据**只接管 Firepower**：Strong（≥80 图）直接读人工锚定的标尺，
Supporting（10~79 图）向生涯先验收缩；不足 10 图、IGL、无数据者回退生涯先验。
Leadership / Experience 继续走生涯侧证据，Stability 只有生涯先验一个来源。

`map_count` 是 **Evidence Confidence，不是 Stability**——它只决定火力那一维
信不信当前证据，不折算成稳定值。试过让出场量去扣稳定值，实测是对同一批人罚
两次、把爆冷压没了，已撤回（见开发主线）。

`--audit-cards` 专门审这一层：正赛 160 席里现在 11 人（7%）没有任何当前火力
证据，门槛从 30 图降到 10 图之前是 37 人。卡库外真人也能
生成 AI 专属当前卡，但玩家卡一栏保持空白，不会因此进入抽卡库。

队一级还摆了个对照：我们算出来的 entry 顺位 vs HLTV 世界排名，附秩相关 ρ
（当前赛场实测 **0.633**）。§48 记的 0.53 是另一批样本上的数；不管取哪个，
它都是这套映射要改善的东西，所以让它常驻页面。

现况列里每一分和卡面的差都上色，并且**必须有一条改动说明兜着**——没有说明
的差值意味着有一条没人记得的规则在改数，`test_ai_view.py` 盯着这条。

25 列很难扫，所以三组各铺一层底色、组间用一道亮线断开、组名压在表头上方：
先找组、再找列，而不是在一排等价的数字里数格子。

一条一直守着的规矩：**原型不改 `data/` 和 `blinddraft/cards.py`。**
所有实验只活在 `blinddraft/draft.py` 里，哪一版验证成立了再决定回写什么。

## 一句话状态

卡是固定的，市场会给他报错价，卡面只给球探区间；选人时你看得见可以去追哪几种
阵容，散场时每一张牌都会翻开。网页已能把选出的五人送进真实三段 Swiss，每张图
给出十个人的逐人火力账本——每一分变化都拆到「全队状态 / 个人状态 / 指挥挽回 /
经验挽回 / 软顶」。比赛数值层正在做第二轮重构（[比赛引擎_v0.3.md](比赛引擎_v0.3.md)）：
v1 已修掉 Carry 权重乱跳和 MVP 口径两处错并在服役，v2 原型
（`blinddraft.proto_match_v2`）六项验收已过，Road to Major 三阶段外壳已接通，
`/play` 和命令行都跑它；v1 已退役删除。

比赛引擎只有一处：`blinddraft.proto_match_v2`。v1（`blinddraft.match`）已退役
删除，它的四个还有用的入口（`--roster` / `--duel` / `--stats` / 任意阵容上场）
都搬到了 v2，口径换成 v2 的；旧文档和旧截图里 `python -m blinddraft.match ...`
的数字是 v1 那把尺子上的，不能和现在的对着看。

```
python -m blinddraft.draft                                  # 盲选一局
python -m blinddraft.major --seed 1                         # 这届赛场 32 支队怎么来的
python -m blinddraft.major --sweep-field                    # 每局赛场翻新几支
python -m blinddraft.ai_teams                               # 本届 32 支真实队与当前四维
python -m blinddraft.ai_teams --changes                     # 只看位置/火力发生投影的人

python -m blinddraft.proto_match_v2 --field                 # 本届 32 席的 VRS 名额与层内种子
python -m blinddraft.proto_match_v2 --major "donk carry"    # 跑完整一届 Road to Major
python -m blinddraft.proto_match_v2 --demo "donk carry"     # 打一场，看十个人的逐人账本
python -m blinddraft.proto_match_v2 --lab                   # 六项验收
python -m blinddraft.proto_match_v2 --tune                  # MAP_SCALE 扫描
python -m blinddraft.proto_match_v2 --compare               # 和 v1 那条历史曲线对比
python -m blinddraft.proto_match_v2 --audit                 # VRS × Entry 偏差审计
python -m blinddraft.proto_match_v2 --audit-cards           # 谁的四维是猜的：证据覆盖，逐队逐人
python -m blinddraft.proto_match_v2 --audit-cards --thin-only  # 只要薄数据/无数据两张名单
python -m blinddraft.proto_match_v2 --stats --runs 200      # 整届分布：Playoffs 率、按分差的强队胜率
python -m blinddraft.proto_match_v2 --duel 80 70            # 两个 Entry 之间的胜率锚（实测）
python -m blinddraft.proto_match_v2 --major "s1mple,electroNic,Magisk,mzinho,Senzu" --label BC.GAME
                                                            # 拿一支真实阵容直接上场
```

赛场用哪一套口径由 `data/blind_draft/major_field.json` 的 `field_source` 决定：
`current`（默认：区域 VRS 名额 + 快照真实首发 + AI 当前卡）/
`major_pool`（旧口径，按参赛那届的阵容）。

两个可交互的页面（Artifact，私有）：

- **比赛引擎调参台** — 7 个参数接在实时模拟上，拖动当场重跑几十届 Major
  重算 §35 的四组读数
- **AI 对手名册** — 32 支队逐人摊开，年龄曲线可现场调，用来一眼找出判错的人（旧版，未同步今日改动）
  <https://claude.ai/code/artifact/0e7a67b4-62eb-44ec-9f66-db604ba5ef1c>
- **卡面与现况** — 40 队 200 人，卡面火力与近一年 S 级实测 rating 摆在同一条百分位轴上
  <https://claude.ai/code/artifact/a062f63f-50d4-4c3f-b68c-da88e16e0e72>

---

## 文件改过名

原来都堆在仓库根，名字有三套风格，容易混：

```
FribergCS2_Blind_Draft_系统思维导图_v0.1.md      -> 系统地图_v0.1.md
FribergCS2_Blind_Draft_System_Design_v0.2.md     -> 玩法蓝图_v0.2.md
FribergCS2_Blind_Draft_Match_Engine_Design_v0.1.md -> 比赛引擎_v0.1.md
FribergCS2_Blind_Draft_Match_Engine_Design_v0.3.md -> 比赛引擎_v0.3.md
FribergCS2_Round_Engine_Design_v0.1.md            -> 回合引擎_v0.1.md
DESIGN_GAMEPLAY.md                               -> 卡牌与落地记录.md
DESIGN_DRAFT_PROTOTYPE.md                        -> 原型实测记录.md
ChatGPT-小项目反馈与建议.md                       -> 原始讨论_ChatGPT.md
```

（`DESIGN_GAMEPLAY.md` 这个名字尤其误导——它听着像整个游戏的玩法设计，
实际是选手卡生成的落地记录。）
