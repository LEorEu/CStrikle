# Blind Draft

> 用 $15 在身份不完全公开的情况下签 5 名职业选手，组一支临时战队，
> 再让它去打一届真实的 Major。

**现在做到哪：** 选人这一层已经可玩（命令行 + 网页原型，十五局真人试玩）。
比赛这一层跑通了第一版：32 队 Major、玩家按实力插队、三个瑞士轮串联。
AI 对手用**当前阵容 + 当前位置 + 年龄衰减**（`field_source: current`，已接进比赛模拟）；
玩家的卡仍然是生涯巅峰版本。还没有淘汰赛、没有 Rogue Buff、只有命令行。

## 按这个顺序读

| # | 文档 | 是什么 | 什么时候看 |
|---|---|---|---|
| 1 | [系统地图_v0.1.md](系统地图_v0.1.md) | 整个模式按模块拆开，每块标了状态：✅ 冻结 / 🟡 待调 / 🧪 测试桩 / 🔵 待做 / ❓ 开放 | **想知道某件事归哪一层、能不能动，先查这份** |
| 2 | [玩法蓝图_v0.2.md](玩法蓝图_v0.2.md) | 最初的正式设计稿。Grade / Price / Power 的分离、生涯代表版本评价、位置权重都出自这里 | 想知道某条规则的原始意图 |
| 3 | [卡牌与落地记录.md](卡牌与落地记录.md) | 648 张选手卡怎么生成的、实现时和蓝图差在哪、用真实数据核对的数字 | 要改卡库或生成器之前 |
| 4 | [原型实测记录.md](原型实测记录.md) | 真人试玩记录，每条结论后面跟着产生它的那组数字和复算方法 | 想知道某个参数为什么是现在这个值 |
| 5 | [比赛引擎_v0.1.md](比赛引擎_v0.1.md) | 把这五个人放进一届真实 Major 的瑞士轮。§44~§48 是已经跑出来的数和据此改掉的设计，§47 是几个悬案的结论，§48 是拿真实阵容试跑撞出来的，§49 修了 AI 层违反卡库规矩的那处，§50 是补位，§51 记的是「当前实力」这条线的三次尝试和找到的真值数据源，§52 是抓取管线 | 现在 |
| 6 | [数据快照.md](数据快照.md) | AI 对手的「现在」从哪来：五个数据源各管什么、怎么刷新、踩过哪些坑 | 要重抓数据、或怀疑阵容/排名不对时 |
| 7 | [评审_GPT_比赛引擎.md](评审_GPT_比赛引擎.md) | 第三方复核比赛引擎 v0.1，抬头写明哪几条被采纳、哪几条明确不做 | 想知道某个结论被质疑过没有 |
| — | [原始讨论_ChatGPT.md](原始讨论_ChatGPT.md) | 整个模式的原始素材，从看线上站点开始聊起 | 考古 |

**第 4 份是按时间顺序写的**，二 / 三 / 五节是 v1 / v2 当时的状态，不是现状；
现状在六 / 七 / 八节。

## 代码在哪

整个模式住在 `apps/blind_draft/`，是一个叫 `blinddraft` 的包；抓数据的工具在
隔壁 `bdtools`。它只依赖共享底座 `playerdb`，**不碰猜选手那一侧**——这条边界
由 `tests/test_architecture.py` 盯着。整体分层见 [../架构.md](../架构.md)。

| 模块 | 管什么 | 产出 |
|---|---|---|
| `blinddraft.cards` | 卡牌生成器 | `data/blind_draft/draft_cards.json`（v6，已提交） |
| `blinddraft.draft` | 命令行原型，选人这一层的全部逻辑都在这 | — |
| `blinddraft.major` | 入场层：生成赛场 → 玩家插队 → 定 Stage → 首轮对阵 | — |
| `blinddraft.match` | 比赛引擎：瑞士轮、BO1/BO3、Form Roll、三 Stage 串联 | — |
| `blinddraft.ai_teams` | AI 对手：当前阵容 + 当前位置 + 年龄衰减 | — |
| `bdtools.fetch_rankings` | 队伍快照（阵容+位置+HLTV/VRS 排名）、5E 选手照片与队标 | `team_snapshot.json`、`5e_images.json`、`img/` |
| `bdtools.fetch_5e_stats` | 5eplay 当前个人竞技数据 | `5e_player_stats.json` |
| `bdtools.export_web` | 把卡和常量注进网页模板 | `.cache/proto_draft_web.html` |
| `playerdb.build_db` | 重建选手库（共享层，`--refresh-existing` 只刷新当前队/角色） | `data/players.json` |

人工层都在 `data/blind_draft/` 下：`major_field.json`（赛场来源、固定几支、
权重、阵容、磨合度上限）、`5e_aliases.json`（卡库昵称 → 5eplay 名字/id）、
`team_roles.json`、`draft_overrides.json`。

测试在 `apps/blind_draft/tests/test_cards.py`——8 项，盯着卡库和
「卡牌与落地记录.md」里的 SPEC 块不许漂移。

一条一直守着的规矩：**原型不改 `data/` 和 `blinddraft/cards.py`。**
所有实验只活在 `blinddraft/draft.py` 里，哪一版验证成立了再决定回写什么。

## 一句话状态

卡是固定的，市场会给他报错价，卡面只给球探区间；选人时你看得见可以去追哪几种
阵容，散场时每一张牌都会翻开。**现在这支队会去打一届真实的 Major，
从第几个阶段进场取决于你抽得怎么样。**

```
python -m blinddraft.major --seed 1              # 只看入场：排第几、挤掉谁
python -m blinddraft.major --sweep-field        # 每局赛场翻新几支
python -m blinddraft.match --seed 50296 --cap 4  # 打完整届
python -m blinddraft.match --selftest            # 两条不变量
python -m blinddraft.match --stats --cap 4       # §35 的 Q1/Q2
python -m blinddraft.match --lab  --cap 4        # §35 的 Q3/Q4（控制变量）
python -m blinddraft.ai_teams                   # AI 赛场 32 队名单
python -m blinddraft.ai_teams --changes         # 只看被改判/衰减/占位的人
python -m blinddraft.match --roster "s1mple,electroNic,Magisk,mzinho,Senzu"        --label BC.GAME                             # 拿一支真实阵容直接上场
```

赛场用哪一套口径由 `data/blind_draft/major_field.json` 的 `field_source` 决定：
`current`（默认，当前阵容）/ `major_pool`（旧口径，按参赛那届的阵容）。

两个可交互的页面（Artifact，私有）：

- **比赛引擎调参台** — 7 个参数接在实时模拟上，拖动当场重跑几十届 Major
  重算 §35 的四组读数
- **AI 对手名册** — 32 支队逐人摊开，年龄曲线可现场调，用来一眼找出判错的人（旧版，未同步今日改动）
- **卡面与现况** — 40 队 200 人，卡面火力与近一年 S 级实测 rating 摆在同一条百分位轴上
  <https://claude.ai/code/artifact/a062f63f-50d4-4c3f-b68c-da88e16e0e72>

---

## 文件改过名

原来都堆在仓库根，名字有三套风格，容易混：

```
FribergCS2_Blind_Draft_系统思维导图_v0.1.md      -> 系统地图_v0.1.md
FribergCS2_Blind_Draft_System_Design_v0.2.md     -> 玩法蓝图_v0.2.md
FribergCS2_Blind_Draft_Match_Engine_Design_v0.1.md -> 比赛引擎_v0.1.md
DESIGN_GAMEPLAY.md                               -> 卡牌与落地记录.md
DESIGN_DRAFT_PROTOTYPE.md                        -> 原型实测记录.md
ChatGPT-小项目反馈与建议.md                       -> 原始讨论_ChatGPT.md
```

（`DESIGN_GAMEPLAY.md` 这个名字尤其误导——它听着像整个游戏的玩法设计，
实际是选手卡生成的落地记录。）
