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
| 5 | [比赛引擎_v0.1.md](比赛引擎_v0.1.md) | 把这五个人放进一届真实 Major 的瑞士轮。§44~§48 是已经跑出来的数和据此改掉的设计，§47 是几个悬案的结论，§48 是拿真实阵容试跑撞出来的 | 现在 |
| 6 | [评审_GPT_比赛引擎.md](评审_GPT_比赛引擎.md) | 第三方复核比赛引擎 v0.1，抬头写明哪几条被采纳、哪几条明确不做 | 想知道某个结论被质疑过没有 |
| — | [原始讨论_ChatGPT.md](原始讨论_ChatGPT.md) | 整个模式的原始素材，从看线上站点开始聊起 | 考古 |

**第 4 份是按时间顺序写的**，二 / 三 / 五节是 v1 / v2 当时的状态，不是现状；
现状在六 / 七 / 八节。

## 代码在哪

```
scripts/gen_draft_cards.py    卡牌生成器 → data/draft_cards.json（v6，已提交）
scripts/proto_draft.py        命令行原型（选人这一层的全部逻辑都在这）
scripts/proto_draft_web.html  网页原型模板
scripts/export_draft_web.py   把卡和常量注进模板 → .cache/proto_draft_web.html
scripts/proto_major.py        入场层：生成赛场 → 玩家插队 → 定 Stage → 首轮对阵
data/manual/major_field.json  赛场人工层：赛场来源、固定几支、权重、阵容、磨合度上限
scripts/proto_match.py        比赛引擎：瑞士轮、BO1/BO3、Form Roll、三 Stage 串联
scripts/proto_ai_teams.py     AI 对手：当前阵容 + 当前位置 + 年龄衰减（赛场候选池）
tests/test_draft_cards.py     8 项，盯着卡库和「卡牌与落地记录.md」里的 SPEC 块
```

一条一直守着的规矩：**原型不改 `data/` 和 `gen_draft_cards.py`。**
所有实验只活在 `proto_draft.py` 里，哪一版验证成立了再决定回写什么。

## 一句话状态

卡是固定的，市场会给他报错价，卡面只给球探区间；选人时你看得见可以去追哪几种
阵容，散场时每一张牌都会翻开。**现在这支队会去打一届真实的 Major，
从第几个阶段进场取决于你抽得怎么样。**

```
python scripts/proto_major.py --seed 1              # 只看入场：排第几、挤掉谁
python scripts/proto_major.py --sweep-field        # 每局赛场翻新几支
python scripts/proto_match.py --seed 50296 --cap 4  # 打完整届
python scripts/proto_match.py --selftest            # 两条不变量
python scripts/proto_match.py --stats --cap 4       # §35 的 Q1/Q2
python scripts/proto_match.py --lab  --cap 4        # §35 的 Q3/Q4（控制变量）
python scripts/proto_ai_teams.py                   # AI 赛场 32 队名单
python scripts/proto_ai_teams.py --changes         # 只看被改判/衰减/占位的人
python scripts/proto_match.py --roster "s1mple,electroNic,Magisk,mzinho,Senzu"        --label BC.GAME                             # 拿一支真实阵容直接上场
```

赛场用哪一套口径由 `data/manual/major_field.json` 的 `field_source` 决定：
`current`（默认，当前阵容）/ `major_pool`（旧口径，按参赛那届的阵容）。

两个可交互的页面（Artifact，私有）：

- **比赛引擎调参台** — 7 个参数接在实时模拟上，拖动当场重跑几十届 Major
  重算 §35 的四组读数
- **AI 对手名册** — 32 支队逐人摊开，年龄曲线可现场调，用来一眼找出判错的人

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
