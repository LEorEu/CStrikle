# 文档索引

这个仓库里有**两个游戏**，共用同一份选手数据库。之前所有文档堆在根目录，
分不清哪份属于哪个，所以按游戏拆开了。

## 先看这份

- **[架构.md](架构.md)** — 三个包怎么分、依赖只许往哪个方向走、数据放哪、
  怎么跑、什么进镜像什么不进。**动代码之前先看它**，边界是有测试盯着的。

## [guess-the-player/](guess-the-player/) — 猜选手（已上线）

CStrikle，blast.tv 那个 Counter-Strikle 的自建版：猜一名神秘 CS 职业选手，
按国籍 / 战队 / 年龄 / 位置 / Major 次数给反馈。带每日挑战、双人对战、
随机匹配和 LLM AI 对手。**产品说明在仓库根的 [README.md](../README.md)。**

## [blind-draft/](blind-draft/) — Blind Draft（在做）

用 $15 预算、在身份不完全公开的情况下签 5 名职业选手，组一支临时战队，
再让它去打一届真实的 Major。选人、网页 Run 和 32 队三段瑞士轮都已跑通；当前
开发主线是比赛数值层的第二轮重构——让四维各做一件事、每张图能逐人解释火力
为什么变。见 **[blind-draft/开发主线.md](blind-draft/开发主线.md)**，
数值口径见 **[blind-draft/比赛引擎_v0.3.md](blind-draft/比赛引擎_v0.3.md)**。

## 两边共用的

- [角色与战队口径.md](角色与战队口径.md) — 角色真值 = **生涯代表角色**，
  不是当前职务。两个游戏的位置字段都按这条走，Blind Draft 的 Draft Role
  也是它的下游。

---

## 关于文档里的路径

代码在 2026-09-01 拆成了三个包（见 [架构.md](架构.md)）。「照着做」的那几份
文档已经改成新路径；**历史记录类的没改**——`原型实测记录.md`、
`玩法蓝图_v0.2.md`、`原始讨论_ChatGPT.md`、`guess-the-player/项目记忆.md`
里写的是当时跑过什么，把路径改成今天的等于篡改记录。读到 `scripts/proto_*.py`
这类旧路径，对照下表换算：

| 旧 | 新 |
|---|---|
| `scripts/proto_draft.py` | `python -m blinddraft.draft` |
| `scripts/proto_major.py` / `proto_match.py` / `proto_ai_teams.py` | `python -m blinddraft.major` / `.match` / `.ai_teams` |
| `scripts/gen_draft_cards.py` | `python -m blinddraft.cards` |
| `scraper/build_db.py` / `fetch_images.py` | `python -m playerdb.build_db` / `.fetch_images` |
| `scraper/fetch_rankings.py` | `python -m bdtools.fetch_rankings` |
| `server/players.py` / `regions.py` | `playerdb/players.py` / `regions.py` |
| `data/draft_cards.json` 等 Blind Draft 数据 | `data/blind_draft/` 下 |

## 还留在根目录的

`progress.md` / `task_plan.md` / `findings.md` 是 gitignore 掉的本地工作文件
（猜选手时期留下的），没有跟着搬，也不在版本库里。
