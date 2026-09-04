# Blind Draft Broadcast（前端外壳）

转播风格的前端：intro → draft → reveal → build → Major → wrap-up 六屏。

```bash
npm install
npm run dev      # http://localhost:5173，/api 和 /img 代理到 8621
npm run build    # vite-plugin-singlefile -> dist/index.html（单文件, ~310KB）
```

页面由本地调参后台发出去，所以先起后端：

```powershell
uvicorn bdserver.main:app --host 127.0.0.1 --port 8621   # 然后开 /broadcast
```

`dist/` 不进仓库（生成物，而且 300 KB 的 diff 没人读得动）。改完前端要重新
`npm run build`，`/broadcast` 才会更新。

## 它只是一个外壳

**所有玩法、所有数值、所有随机数都来自后端。** 前端不算分、不发牌、不判胜负，
也不持有选手库 —— 它拿到什么就画什么。以前这里有 `src/game/engine.ts`
（578 行独立比赛引擎）和 `src/data/players.ts`（78 张虚构卡），两个文件已经
删掉，`test_broadcast_shell.py` 盯着它们别回来。

| 屏 | 数据从哪来 | 状态 |
| --- | --- | --- |
| intro | — | 只有一个 seed 输入框 |
| draft | `POST /api/draft` | 接通 |
| reveal | `draft.owned` + `run.roster` 同序合并 | 接通 |
| build | `run.entry` / `roster` / `demoted` | 接通；Rogue Shop **未实现** |
| tournament | `run.legs[].maps[]` | 接通；Swiss 积分榜 **未实现** |
| final | `run` 的战绩 + 逐人账本加总 | 接通；后悔值、淘汰赛 **未实现** |

### `/api/draft`

一局盲选就是 `seed` 加一串动作，没有服务端会话：

```jsonc
POST /api/draft
{ "seed": 7, "actions": [0, -1, 2] }   // 数字 = 签板面第几张，-1 = 放掉这个市场日
```

回来的是当前这一天的全部可见信息 —— `board` / `owned` / `left` / `max_price` /
`can_pass` / `passes_left` / `missing` / `blueprints`，签满五人后多一个 `pages`，
拿它去调 `/api/run`。

两件事要知道：

- **每一步都是整局重放**（~50ms）。前端只往 `actions` 里 push 一个数字再请求
  一次，不维护任何局面状态；同一个 `seed` 和命令行
  `python -m blinddraft.draft --seed 7` 是同一局。
- **板面上没有真值。** `page` / `nickname` / 档位 / 四维一概不下发，只有标价、
  位置、国籍、一条球探区间、一条身份线索。想在选人阶段显示昵称是做不到的 ——
  盲选的信息边界由后端把住，见 `bdserver/draft.py`。

### 逐回合播报是表演层

`/api/run` 只算到每图（`player_won` / `margin` / 每人 `effective_firepower`）。
回合流水和 K/D 由 `src/game/playByPlay.ts` **演绎**：比分收敛到引擎给的那一图
结果，K/D 按 carry 权重分。它不参与任何判定 —— 删掉那个文件，比赛结果一分不变。
比赛屏底下常驻一行字说明这件事，逐人火力账本（引擎的原始输出）就摆在旁边对照。

那一层允许有自己的数（margin → 比分的斜率、一个回合几个人头），因为它们不是
引擎系数。**引擎系数一个都不许抄进 TS**，`test_broadcast_shell.py` 盯着。

### 没实现的功能就写「未实现」

Rogue Buff 商店、淘汰赛、夺冠路径、后悔值复盘后端都没有。**不要用前端逻辑把
它们补上，也不要把入口藏起来** —— 屏保留着，用 `<NotImplemented>` 明写为什么
没有。藏起来会让人以为做完了，用前端补上则等于把玩法拆成两份实现，而这个仓库
刚为「同一件事两份实现」付过一次代价。要真做，先在 `blinddraft/` 里立住。
