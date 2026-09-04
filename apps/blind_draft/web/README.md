# Blind Draft Broadcast（前端原型）

转播风格的前端：intro → draft → reveal → build → Major → wrap-up 六屏，
比赛屏是逐回合比分 + K/D 记分板 + play-by-play 文字流。

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # vite-plugin-singlefile -> dist/index.html(单文件, ~320KB)
```

## 现在还没接后端

**`src/game/engine.ts` 和 `src/data/players.ts` 不是权威实现，别照着它们改数值。**

这两个文件是一整套独立的比赛引擎和选手库，和 Python 那边零交集：

| | 这里 | 后端 |
| --- | --- | --- |
| 选手库 | 78 张虚构卡，TS 里现算属性 | 648 张真实选手（`blinddraft/cards.py`，还有人工层和待发布清单） |
| 队伍模型 | `TeamStats{firepower,tactics,consistency,experience,chemistry,clutch,mapBonus}` | Entry = 火力聚合 + 结构（无狙罚 + 磨合度），外加 tactical |
| 阵容加成 | `Trait.apply()` 直接改数 | Trait 只是标签，加分统一走 `chemistry()` |
| 赛制 | 16 队单段瑞士 + QF/SF/Final，可以夺冠 | 32 队三段 Swiss，Stage 由区域 VRS 名额定，进 Playoffs 即终止 |
| 比赛粒度 | 逐回合胜负 + 每人 K/D + 地图 BP | 只到每图：strength / margin / 逐人 form-pressure-delta |
| Rogue Buff | 12 个道具，花剩余预算买 | 没有这套东西 |
| 球探报告区间 | 没做 | `SCOUT_WIDTH / SCOUT_POS`，是核心盲选机制 |

这个仓库的规矩是**比赛公式只有一份，在 Python**——`d980e37` 退役 v1、
`84c67a6` 统一标尺、`3d46a31` 把揭晓页和 Run 页拉回同一个 Entry，都是在执行
这条。`engine.ts` 是第二份，而且算的是另一个游戏，所以它只能当表现层的占位数据用。

## 接下来要做的（方案 A：只留皮）

胜负和数值全部交给 `/api/run`，这里只负责渲染：

1. 开局拉 `/api/cards` 换掉 `data/players.ts`；比赛调 `/api/run` 换掉
   `simulateMatch` / `generateOpponents` / 瑞士轮那一段。
2. `/api/run` 只给到每图，逐回合播报和 K/D 因此没有真数据。做法是拿
   `player_won + margin + 每人 effective_firepower` **演绎**一条回合流水：
   比分必须收敛到后端给的那一图结果，K/D 按火力权重分配。这是表演层，
   不参与胜负判定，也不许反过来影响任何数字。
3. Rogue Buff、淘汰赛、夺冠路径后端都没有。要么先砍掉，要么先在
   `proto_match_v2` 里立住——那是设计工作，不是接入工作。

## 已知问题（和接入无关）

- `generateBoards()` 只按价位填槽，不管位置：实测第一轮发出过 4 个 AWPER +
  1 个 RIFLER。后端 `draw()` 那套 `need / quota / forcePos`（缺 IGL/AWP 时强制
  塞一张）这里没有，可能出现六轮凑不出指挥。
- 瑞士积分榜是装饰：`concludeMatch` 给其他 15 队每轮各掷一次硬币，不配对。
  跑完三轮出现过「1 支 3-0、1 支 2-1、其余 11 支全是 1-2」这种真瑞士轮不可能
  的分布。
