# FribergCS2 Blind Draft — Round Engine 构建文档 v0.1

> 日期：2026-09-03  
> 状态：**Future Design / 暂不接入正式流程**  
> 依赖：Match Engine v0.3  
> 目标：为未来“实时比分、Round Log、Kill Feed、K/D/A、ADR、KAST、Match Rating”预留一套可落地的抽象回合引擎，而不是模拟一场真正的 CS2。

---

# 0. 为什么要有 Round Engine

当前 Match Engine v0.3 已经能回答：

> 这张地图双方大概发挥成什么样，以及最终谁赢。

当前链路可以概括为：

```text
Player Card / Current Profile
        ↓
Player Performance Roll
        ↓
Pressure / Experience
        ↓
Team Performance
        ↓
Leadership / Chemistry / Buff
        ↓
Map Residual
        ↓
Winner
```

这足够跑通 Road to Major。

但它不能自然生成：

- 0:0 → 13:X 的比分过程；
- 谁杀了谁；
- 谁完成残局；
- 谁在连续拿分；
- 实时 K / A / D；
- ADR；
- KAST；
- 一张图结束后的 Match Rating；
- “ZywOo 已经杀疯了但队伍还是落后”这种观赛叙事。

Round Engine 的价值不是更精确地预测 CS，而是：

> **把现在一张图的黑箱结果，展开成一段内部一致、可以观看的比赛过程。**

---

# 1. 明确不做什么

Round Engine **不是 CS2 Simulator**。

第一版明确不模拟：

- 玩家坐标；
- 瞄准角度；
- 每颗烟 / 闪 / 火；
- 真实武器购买清单；
- HP / Armor 精确变化；
- 每一发子弹；
- 站位与补枪距离；
- 真实地图路径；
- 逐秒时间轴；
- 完整投掷物战术；
- 真实 Demo 级事件。

否则复杂度会瞬间失控，而且没有足够数据校准。

第一版只模拟：

> **“这一回合大概发生了什么。”**

---

# 2. 长期目标架构

当前：

```text
Map Profile
    ↓
Map Residual
    ↓
Winner
```

未来：

```text
Map Profile
    ↓
Round Engine
    ↓
Round Events
    ↓
13:X / Winner
    ↓
Player Match Stats
```

Round Engine 成熟以后，会逐步吃掉当前 Map Residual 的职责。

例如：

```text
现在的 Map Residual
=
地图适配
+ 经济波动
+ 手枪局
+ timing
+ clutch
+ 关键首杀
+ 未建模战术
+ 其他噪声
```

未来：

```text
Map Matchup
+ Economy Engine
+ Round Noise
+ Clutch Events
+ smaller Map Residual
```

因此 Round Engine 是 **Map Residual 的逐步展开**，不是推翻现有 Match Engine。

---

# 3. 两种运行模式必须共用一套数据结构

## Mode A — Constrained Replay

先由当前 Match Engine 决定：

```text
Winner
Map Result / Target Result
Player Map Performance
```

Round Engine 再生成一段与结论一致的过程。

用途：

- 最低风险；
- 先做观赛 UI；
- 验证 Kill Feed / Stats / Replay 体验。

本质：

> **结果已知，过程后生成。**

---

## Mode B — True Round Simulation

Map Engine 只给 Round Engine：

```text
Player Map Profile
Team Execution
Pressure Context
Chemistry / Buff
Map-level latent factors
```

从：

```text
0 : 0
```

开始逐回合模拟。

最终：

> **Round Engine 自己决定 13:X 和 Winner。**

这是长期目标。

---

## 3.1 为什么两种模式必须共享 Event Schema

第一版即使只是 Replay，也要输出：

```json
{
  "round": 17,
  "score_before": [9, 7],
  "winner": "team_a",
  "reason": "bomb_exploded",
  "economy": {
    "team_a": "FULL",
    "team_b": "FORCE"
  },
  "kills": [
    {
      "killer": "ZywOo",
      "victim": "xfl0ud",
      "assist": null,
      "trade": false
    }
  ]
}
```

以后切换成真正 Round Simulation：

> 前端、统计结算、回放 UI 全部不用重写。

---

# 4. Round Engine 的输入

第一版不要直接读取 Grade。

每张地图的输入应来自 Match Engine 已经处理过的 Map Profile。

推荐：

```text
Team A
- 5 player identities
- Base Firepower
- Map Effective Firepower / Map Form
- Role
- Leadership / main IGL
- Experience / Pressure effect
- Chemistry
- Trait / Rogue
- Carry hierarchy

Team B
- 同上

Context
- BO1 / BO3
- Pressure
- Side assignment
- Map identifier（未来）
```

---

## 4.1 Player Map Form 建议一图只 Roll 一次

Round Engine 第一版不要把 Stability 改成：

> 每个 Round 再 Roll 一次。

否则会推翻现有 Player Performance 层。

推荐：

```text
Base Firepower
    ↓
Stability Roll
    ↓
Experience / Pressure
    ↓
Map Effective Firepower
```

这个值代表：

> **这名选手今天这张图整体处于什么状态。**

Round Engine 再围绕这个 Map Form 产生小尺度 Round Noise。

所以：

> donk 这张图 Map F102

意味着他整张图大概率都很有存在感，而不是下一轮突然 F50、再下一轮 F130。

---

# 5. Round Engine 的最小核心

一回合只需要回答四个问题：

1. 双方这一回合谁更有优势？
2. 谁赢？
3. 以什么方式结束？
4. 玩家事件如何分配？

---

# 6. Round Edge

第一版：

```text
Round Edge
=
Map Team Strength Difference
+ Economy Edge
+ Side Edge
+ Tactical / Leadership Edge
+ Small Round Noise
```

然后：

```text
P(A wins round)
= logistic(RoundEdge / ROUND_SCALE)
```

Roll 一次 Round Winner。

注意：

> `ROUND_SCALE` 不等于当前 `MAP_SCALE`。

它必须通过 Monte Carlo 反推。

---

# 7. 为什么不能把 Map 胜率直接当 Round 胜率

例如当前 Match Engine：

```text
Team Strength +10
→ Map Win ≈ 81%
```

不能写成：

```text
每个 Round 胜率 = 81%
```

否则 MR12 会近乎碾压。

真正合理的单 Round 优势可能只有：

```text
54% / 56% / 58% ...
```

但经过最多 24+ 个 Round 累积后：

> Map Win 才达到 70% / 80% / 90%。

因此 Round Engine 最大的校准任务之一是：

> **Strength Gap → Round Win Probability → Map Win Probability**

的反推。

---

# 8. Economy Engine：最值得做的抽象层

CS 的 Round 不能是完全独立硬币。

因为：

> 输一个关键回合，会影响后面一到两个回合。

但第一版也不需要真实金额。

只保留四种经济状态：

```text
FULL
FORCE
HALF
ECO
```

---

## 8.1 Economy Edge

示意：

```text
FULL vs FULL
→ 0

FULL vs FORCE
→ Strong Advantage

FULL vs HALF
→ Larger Advantage

FULL vs ECO
→ Very Large Advantage
```

具体数值由模拟校准。

---

## 8.2 Economy Transition

示意状态机：

```text
赢 Round
→ economy 趋向 FULL

输 FULL
→ FORCE / HALF

连续输
→ ECO

ECO 后
→ 回到 FULL
```

无需还原真实 `$1400 / $1900 / $2400...`。

只要能产生：

- 连分；
- 经济崩盘；
- eco 翻盘；
- 强队滚雪球；
- 关键翻盘后局势逆转；

已经足够有 CS 味。

---

# 9. Side / CT-T

第一版可以保留：

```text
CT
T
```

但不模拟具体地图站位。

Side Edge 可由：

- Map 的整体 CT/T 偏置；
- Team Future Map Profile；

决定。

没有真实 Map Pool 时：

> Side Edge 可以先接近 0。

MR12 中场后换边。

---

# 10. Round Outcome Type

赢回合以后再生成结束方式。

T 方可能：

```text
ELIMINATION
BOMB_EXPLODED
```

CT 方可能：

```text
ELIMINATION
DEFUSE
TIME
```

第一版只需要这些。

它们主要用于：

- Round Log；
- UI；
- KAST / Clutch / Bomb Story。

无需模拟完整炸弹时间轴。

---

# 11. Kill Feed 生成

Kill Feed 不需要真实空间模拟。

已知：

```text
Round Winner
Round Type
双方本回合大概损失人数
```

然后根据 Player Map Effective Firepower 分配击杀。

---

## 11.1 Kill Share

概念：

```text
KillWeight(player)
=
Effective Firepower
× Role Modifier
× Carry Modifier
× small random
```

高 Firepower：

> 更容易积累 Kill。

但不是每一回合都由第一枪杀完。

---

## 11.2 Death Assignment

受：

- 对手 Kill Share；
- Role；
- 当前是否已死亡；
- 小随机；

影响。

第一版不需要建立“谁总是第一个死”的精确角色模型。

---

## 11.3 Kill Feed 必须来自 Round Event

禁止：

```text
先随机赛后 27 kills
→ 再随便补 Kill Feed
```

正确：

```text
Round Events
    ↓
Kills / Deaths
    ↓
Match Stats
```

这是未来整个系统一致性的底线。

---

# 12. Assists

第一版可以概率生成。

一次击杀发生后：

```text
一定概率存在 Assist
```

从存活 / 本回合参与过的队友中分配。

后续如有 Role Profile：

- Support；
- IGL；
- Entry；

可以改变 Assist 倾向。

---

# 13. Damage / ADR

第一版不模拟每枪伤害。

推荐事件层估算：

```text
Kill Damage
+ Assist Damage
+ Non-kill Damage
= Round Damage
```

整张图：

```text
ADR = Total Damage / Rounds Played
```

目标不是精确复刻真实伤害，而是让：

- Kill 高的人 ADR 通常高；
- 有大量非致死伤害的人能出现高 ADR 但普通 K/D；
- 统计范围合理。

---

# 14. KAST

KAST 很适合事件生成。

每轮给每名选手记录：

```text
K = Kill
A = Assist
S = Survive
T = Traded
```

满足任意一项：

> 本回合 KAST = true。

最终：

```text
KAST%
= successful rounds / total rounds
```

---

# 15. Match Rating

不要称为：

> HLTV Rating 3.0

除非真正复现其公式与语义。

项目内部可以叫：

> **Match Rating**

输入：

- KPR；
- DPR；
- ADR；
- KAST；
- Impact-like events；
- Clutch / Opening（未来）。

目标：

```text
普通表现 ≈ 1.00
优秀 ≈ 1.15–1.35
超级图 ≈ 1.4+
极差 <0.8
```

Rating 是 **结算统计**，不能反过来决定这张图发生什么。

---

# 16. MVP

MVP 直接从真实 Round Events / Match Stats 计算。

不再需要：

> 根据卡面或 Life Game 标签猜 MVP。

输入可以是：

```text
Match Rating
+ Impact
+ Round Wins Contribution
```

但第一版 Match Rating 第一即可。

---

# 17. LIFE GAME / UNDERPERFORM

仍与 Career / Current Base 比较：

```text
Expected Map Performance
vs
Observed Match Stats
```

而不是只看 K/D。

例如：

> F62 的选手打出 Rating 1.35

非常适合 LIFE GAME。

> F96 的选手 Rating 1.18

可能仍然是全队 MVP，但不算 LIFE GAME。

---

# 18. Clutch

第一版可以做极简标签，不模拟真实 1vX 战斗。

如果某回合：

```text
Winner 在一度明显少人
```

可以概率标记：

```text
1v1
1v2
1v3
```

并把关键击杀归给一名存活玩家。

未来用于：

- UI；
- Impact；
- Trait；
- Experience 扩展。

---

# 19. Score Distribution

Round Engine 不只是要保证谁赢得合理，还要保证比分像 CS。

需要统计：

```text
13-3
13-5
13-7
13-9
13-10
13-11
13-12 / OT
```

分布。

如果模型几乎全部：

> 13-10 / 13-11

说明 Economy / streak 不够。

如果大量：

> 13-2 / 13-3

说明 Round Edge 太陡。

---

# 20. Overtime

第一版可以先：

> 不做 OT，12:12 后直接用简化 Decider。

但正式接入 UI 前建议至少实现：

```text
MR3 overtime blocks
```

无需完整经济规则。

---

# 21. 两层随机必须分开

未来如果 Round Engine 接管：

### Player Layer

回答：

> 谁今天状态好。

### Round Layer

回答：

> 这一个关键局发生了什么。

不能让同一个随机同时决定：

- ZywOo 是否状态好；
- Vitality 是否赢手枪；
- apEX 是否 1v2。

否则又会重新出现变量语义混乱。

---

# 22. 与 Map Residual 的关系

Round Engine 第一版不要一上来就删掉 Map Residual。

建议迁移：

## Phase R0

```text
Current Map Engine
→ Winner

Round Replay
→ 只做展示
```

---

## Phase R1 — Shadow Simulation

```text
Current Map Engine
→ 正式 Winner

Round Engine
→ 同时独立模拟
→ 不影响正式结果
```

比较：

- Map Win Rate；
- Score Distribution；
- Player Stats；
- Star Visibility。

---

## Phase R2 — Hybrid

```text
Round Engine
+ smaller Map Residual
→ Winner
```

Map Residual 从：

```text
scale 6
```

逐步降低。

---

## Phase R3

当 Round Engine 已经吸收：

- Economy；
- Side；
- Map；
- Clutch / Round Noise；

以后：

> Map Residual 只保留一个很小的无法解释误差。

---

# 23. Event-sourced Match 数据结构

整场地图建议以事件为源。

示意：

```json
{
  "map_id": "...",
  "teams": ["A", "B"],
  "rounds": [
    {
      "round_no": 1,
      "score_before": [0, 0],
      "side": {
        "A": "T",
        "B": "CT"
      },
      "economy": {
        "A": "PISTOL",
        "B": "PISTOL"
      },
      "winner": "A",
      "reason": "elimination",
      "events": [
        {
          "type": "kill",
          "killer": "player_a",
          "victim": "player_b",
          "assist": null
        }
      ]
    }
  ]
}
```

赛后数据全部由这份事件账本汇总。

---

# 24. 前端可以做到什么程度

同一套 Event Stream 可以支持：

### Fast

```text
Round 1  A WIN
Round 2  A WIN
Round 3  B WIN
...
```

### Live

逐条播：

```text
ZywOo → xfl0ud
flameZ → Krabeni
BOMB PLANTED
...
```

### Skip

直接跳到：

```text
13 : 8
```

因此玩家可选：

- Skip Map；
- Fast Forward；
- 4x；
- Live。

---

# 25. 最重要的 Regression Tests

## 25.1 Map Win Curve Preservation

Round Engine 必须尽量复现当前 Match Engine v0.3 已校准的曲线。

例如 baseline gap：

```text
+2
+5
+10
+20
```

对应 Map Win Rate 不应发生大幅漂移。

---

## 25.2 Star Visibility

例如：

```text
donk F96
```

必须长期：

- 高 K；
- 高 ADR；
- 高 Rating；
- 高 MVP；

而不是 Event Engine 把明星贡献重新平均掉。

---

## 25.3 Weak-player Life Game

低卡：

> 可以偶尔打出超级图。

但不能长期比明星更常拿 MVP。

---

## 25.4 Event / Stats Consistency

必须：

```text
Kill Feed kills == Match Stats kills
Death Feed deaths == Match Stats deaths
Round survivors == death ledger
```

不能出现：

> UI 里杀了 18 个，结算却 23 kills。

---

## 25.5 Economy Streak

模型需要出现合理：

- 2–4 round streak；
- eco reset；
- comeback；

不能完全独立硬币。

---

## 25.6 Score Distribution

按实力差分桶检查最终比分。

---

## 25.7 BO1 / BO3

BO3 不额外给强队 Buff。

依靠：

> 多地图模拟自然回归实力。

---

# 26. 第一版开发顺序

未来真正开工时：

### Step 1
定义 Event Schema 与 Stats Aggregator。

### Step 2
做 Constrained Replay：
> 已知 Winner，生成 13:X + Kill Feed + K/D。

### Step 3
加入抽象 Economy 状态机。

### Step 4
做独立 Round Simulation。

### Step 5
Shadow Mode 跑数十万图，与 v0.3 Match Engine 对照。

### Step 6
接 ADR / KAST / Match Rating。

### Step 7
缩小 Map Residual。

### Step 8
通过 Regression 后，Round Engine 接管 Winner。

---

# 27. 现在不做的原因

当前项目更重要的是先稳定：

```text
Blind Draft
→ Qualification / VRS
→ Major Stage
→ Match Engine
→ Run Result
```

Round Engine 会显著增加：

- 参数数量；
- UI；
- 回归测试；
- 统计校准；
- 调试成本。

因此当前决策：

> **先留下设计和接口，不阻塞主流程。**

---

# 28. 一句话定义

> **Round Engine 不是模拟真正 CS2，而是把“一张地图”的概率结果拆成一串内部一致、可观看、可统计的回合事件。**

它最终应该让：

```text
“Vitality 赢了”
```

变成：

```text
“Vitality 13:8 赢了；
ZywOo 26-13、ADR 92、Rating 1.39；
第 18 回合他完成了关键双杀；
FUT 在 7:8 时因为 force buy 失败连续掉了三分。”
```

而这些数据全部来自同一条事件账本，不是赛后分别随机拼出来的。
