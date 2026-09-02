# FribergCS2 Blind Draft — Draft 四维重构工作指南 v0.1

> 日期：2026-09-02  
> 目标：在不破坏 Blind Draft 已经冻结的核心玩法前提下，重新构建 Player Card 的四维数值，使 **Grade、能力、历史证据、当前表现** 各自承担清晰职责。  
> 本文只指导 **Draft Career Card** 的重构。AI Current Profile 后续复用同一把能力尺度，但不在本轮直接落地。

---

# 0. 这轮到底要解决什么

当前 v6 的主要问题不是“所有卡都错”，而是：

1. **Grade 对四维约束过强**，导致同档内能力差距被压扁；
2. **G1 / G2 / 部分 G3 缺乏有效个人火力证据**，现有 Firepower 很大程度来自模板与轻微扰动；
3. 年轻、近两年进入一线但尚未积累 Major / Top20 履历的选手，容易被低估；
4. 已有明确巅峰证据的老将、传奇，本身不需要靠“当前一年数据”重估 Career Peak；
5. 5E 已经能提供一部分可靠的当前 S 级赛事数据，但修正后覆盖率明显下降，因此它必须是 **高质量补充证据**，而不是全库唯一真值。

本轮目标不是：

> 用 5E Rating 批量生成所有卡。

而是：

> **建立一把统一的 1–99 能力尺，用可靠现役数据校准这把尺，然后优先修复原本证据最弱的 G1/G2/G3 现役卡。**

---

# 1. 四个概念必须彻底分开

## 1.1 Grade = Career Evidence

Grade 回答：

> **这个人的职业生涯已经被证明到什么程度？**

主要来源：

- Major 履历
- Major 深轮次 / 冠军
- HLTV Top20
- 长期职业成就
- IGL 的带队成绩

Grade **不再等同于能力上限**。

允许出现：

- G2 + Firepower 84
- G3 + Firepower 88
- G5 + Firepower 86

这不是异常，而是 Grade 与 Ability 解耦后的正常结果。

---

## 1.2 Firepower = Peak Combat Ability

Firepower 回答：

> **这个选手生涯代表版本的实际输出能力能打到什么水平？**

对年轻、仍在巅峰或接近巅峰的现役选手：

> 当前可靠顶级赛事表现可以直接成为 Career Peak Evidence。

对已有明确历史巅峰的老将：

> 当前下滑不能覆盖已存在的 Career Peak。

---

## 1.3 Experience = Career Pressure Evidence

Experience 回答：

> **高压场景下，这个人有多少被验证过的大赛经验？**

继续由：

- Major 次数
- Major 深轮次
- 冠军 / 决赛 / 四强
- 长期大赛履历

驱动。

**不要用当前 Rating、KAST、年龄去补偿或修正 Experience。**

---

## 1.4 Stability = Reliability Prior

Stability 回答：

> **这张 Career Card 的发挥波动应当有多大？**

Match Engine 中已经明确：

```text
sigma ∝ (100 - Stability)
```

因此 Stability 代表的是 **发挥方差**，不是平均 Rating，也不是 KAST。

在没有逐图 / 逐场波动数据以前：

> Stability 继续作为“证据驱动的先验”，不要伪装成测量值。

---

# 2. Firepower 的统一尺度

第一轮 31 个 Current Anchor 已经足够建立一把可用的 **游戏语义标尺**。

不要把它理解成“Rating 到 Firepower 的真实数学定律”，而要理解成：

> **现实观感翻译到 1–99 游戏尺度时，各档大概意味着什么。**

建议先固定如下语义：

| Firepower | 语义 |
|---:|---|
| 96–99 | 世代级 / 历史级火力峰值 |
| 92–95 | 世界顶尖超巨巅峰 |
| 88–91 | 顶级明星 / 长期一线 Carry |
| 83–87 | 一线明星 / 极强输出手 |
| 78–82 | 强一线主力 |
| 72–77 | 正常一线强度 |
| 66–71 | 一线偏弱枪位 / 二线强手 |
| 58–65 | 明显偏弱枪位 / 功能型 |
| <58 | 枪法是明确短板 |

> 数字边界后续可根据完整重算后的分布微调，但**语义不要再跟 Grade 绑定**。

---

# 3. 5E 数据在 Draft 重构中的角色

## 3.1 5E 不是 Ground Truth

现在已经确认：

- 数据抓取逻辑修正后，错误 S 级样本已被剔除；
- 剩下数据质量明显更好；
- 但覆盖人数也明显下降。

因此正确定位是：

> **5E = 高质量 Performance Evidence。**

它可以修正：

- 当前正值巅峰的年轻人；
- 近两年突然崛起但历史履历不足的人；
- 旧卡明显被 G1/G2/G3 模板压住的人。

它不应该：

- 自动重写所有历史传奇；
- 因当前低迷而下调 Career Peak；
- 为了覆盖率去放宽赛事等级；
- 因样本少而强行生成精确数值。

---

## 3.2 数据可信度只分三档即可

不要一开始做复杂评分系统。

### A. Strong Evidence

满足：

- S 级赛事口径确认正确；
- 样本量足够；
- 数据与公开观感、实际比赛表现没有明显冲突。

处理：

> 可作为 Firepower 的主要依据。

### B. Supporting Evidence

满足：

- 样本偏少，或数据可用但不够稳；
- 没有明显错误。

处理：

> 只作为方向和幅度参考，不直接覆盖原 Career 值。

### C. No Reliable Evidence

- 无 S 级样本；
- 数据异常；
- 赛事实体归类仍存疑。

处理：

> 完全回退 Career 模型。

---

# 4. Draft Firepower v7 的核心规则

## 4.1 最重要的单向规则

对 Draft Career Card：

> **可靠的当前强表现可以建立新的 Career Peak。**
>
> **当前弱表现不能抹掉已经被证明过的历史 Peak。**

因此：

```text
new_firepower = max(existing_peak_firepower, evidence_supported_firepower)
```

这不是最终代码公式，而是本轮重构的语义约束。

---

## 4.2 按人群分层处理

### A. G4 / G5 或已有明确巅峰证据

默认：

> 不自动下修。

处理顺序：

1. 保留现有 Career Evidence；
2. 5E 只作为 sanity check；
3. 明显离谱的知名选手进入人工 override；
4. 不为了“全库统一公式”强行批量改。

原因：

> 这批人数量少、认知度高、历史证据足，人工修正成本很低。

---

### B. Active G1 / G2

这是本轮最重要的修复区。

旧值的问题：

> 同档内缺乏真实个人火力输入，模板占比过高。

处理：

- Strong Evidence → Firepower 允许直接离开 Grade 模板；
- Supporting Evidence → 做有上限的向上校正；
- No Reliable Evidence → 保留模板 / Career 先验。

允许出现：

```text
G1 F78
G2 F84
```

不要因为 Grade 低就强行压回去。

---

### C. Active G3

G3 是混合区。

它可能同时存在：

- 已有 Top20 / Major Evidence 的老选手；
- 刚进入一线的新明星；
- 履历中等但当前爆发的选手。

处理：

- 有明确旧 Peak：只允许当前强证据向上刷新，不向下覆盖；
- 无明确旧 Peak：与 G1/G2 类似，由可靠 Performance Evidence 重新评估；
- 若历史证据与当前证据冲突，保留更能代表 Career Peak 的一侧。

---

### D. Retired / Inactive / Old Peak Players

没有可靠历史逐年统计时：

> 不要拿当前或最近一年数据反推巅峰。

继续使用：

- Top20
- Major
- 同时代地位
- 现有人工 override
- Role template

以后若历史数据源足够可靠，再单独做 Historical Peak v2。

---

# 5. 不再使用“Grade 模板 ± 很小扰动”决定火力

v6 的问题之一是：

```text
G2 Rifle ≈ 60
G3 Rifle ≈ 70
G4 Rifle ≈ 80
G5 Rifle ≈ 89
```

再在附近抖几分。

v7 应改成：

```text
Grade / Role Template
        ↓
只提供 Prior
        ↓
Career Evidence
Performance Evidence
Manual Override
        ↓
最终 Firepower
```

模板的职责变成：

> **没有证据时给一个合理默认值。**

不是：

> **有证据也必须锁在模板附近。**

---

# 6. 其余三维怎么重构

## 6.1 Leadership

暂时不要被 Rating 驱动。

### RIFLER / AWPER

- 维持低领导力先验；
- 只有明确 IGL / secondary caller / 长期组织角色证据才上调。

### IGL

Leadership 仍由：

- 当前 / 生涯 IGL 证据
- Major 深轮次
- 带队履历
- 长期成功程度

决定。

不要因为枪法弱就扣 Leadership。

也不要因为 Rating 高就自动加 Leadership。

---

## 6.2 Experience

保持现有 Career 模型。

建议重构时只做一件事：

> 检查现有 G1/G2/G3 Experience 是否真的来自履历，而不是被 Grade 模板机械抬高 / 压低。

优先依据：

1. Major 出场次数；
2. Major 深轮次；
3. 冠军 / 决赛 / 四强；
4. 高级别大赛长期出场。

Experience 不参与 Firepower 的“平衡补偿”。

---

## 6.3 Stability

本轮只重做“生成逻辑”，不假装有真实测量。

建议：

### 有长期高等级履历

> Stability 先验更高。

### 年轻 / 样本少 / 履历不足

> Stability 先验稍低，但不能与 Firepower 增长做线性抵消。

禁止：

```text
Firepower +10
→ Stability -5
```

这种纯配重式修正。

正确做法：

> Stability 必须由“我们对发挥可靠性的证据”单独决定。

在拿到逐图 / 逐场 Rating 方差以前，不做数据化精算。

---

# 7. Grade 本轮原则上不动

v7 第一轮：

> **先重构四维，Grade 继续表示 Career Evidence。**

原因：

- Grade 体系已经承担 Draft 市场、历史证据、稀有度；
- 当前最明显的问题是 Ability 被 Grade 模板绑死；
- 现在同时改 Grade 和四维，会失去诊断能力。

允许：

```text
G2 F84
G3 F88
G5 F86
```

如果这类卡大量出现后，游戏层出现问题：

> 再修改 Market Value / tier_gap，而不是把四维重新压回 Grade。

---

# 8. 必须重做的下游逻辑：Grade ≠ Ability

重构后，代码中任何：

```text
grade 高 → 一定能力高
```

的隐含假设都必须搜索一次。

重点检查：

- `tier_gap`
- BARGAIN BIN
- 最大抄底
- 市场价值
- Scout 信息
- Hindsight / 事后最优
- Draft value
- Price 与“实际实力”的关系

尤其旧逻辑：

```python
tier_gap = grade - price
```

重构后不再成立。

建议新增：

```text
Ability Value
```

它由 Role-weighted 四维决定。

然后：

```text
Value Gap = Ability Tier - Price
```

Grade 回归：

> Career Evidence / rarity / history。

---

# 9. 推荐的实际开发顺序

## Phase 1 — 只重算 Firepower

先不要一次重做四维。

目标：

> 看 Grade 与 Firepower 解耦后，卡库是否明显更合理。

流程：

1. 冻结 v6；
2. 建 `firepower_v7_preview.json`；
3. 只处理 Active G1/G2/G3；
4. Strong Evidence 直接进入新尺度；
5. Supporting Evidence 做有限修正；
6. 无证据回退模板；
7. G4/G5 默认不自动下修；
8. 输出 diff 报告。

必须展示：

```text
player
grade
role
old_firepower
new_firepower
delta
evidence_source
evidence_strength
sample_count
manual_override
```

---

## Phase 2 — 人工审核异常值

重点列出：

- +10 以上；
- -8 以下；
- G1/G2 但 F80+；
- G3 但 F88+；
- 有 Top20 却被下修；
- 无可靠数据却发生大变化。

这一步不要自动修。

先确认：

> 是模型真的发现了低估，还是数据 / 角色 / 身份有问题。

---

## Phase 3 — 再检查 Leadership / Experience / Stability

不要重新“生成一遍”。

而是逐维做 audit：

### Leadership Audit
- IGL 是否被正确识别；
- 非 IGL 是否异常高；
- Current Role / Career Role 是否串用。

### Experience Audit
- 低履历年轻人是否被 Grade 模板抬太高；
- 老将 / Major veterans 是否过低。

### Stability Audit
- 是否仍然存在大量纯 jitter；
- 同类选手分布是否过窄；
- 不做 Firepower 配重。

---

## Phase 4 — 重算 Ability Value / Market

四维稳定以后，再重算：

- Role-weighted Overall
- Market expected value
- Bargain / Overpay
- Price distribution

不要反过来为了维持旧价格分布去改四维。

---

# 10. 必须保留的测试样本

建议永久保留三组：

## A. 当前年轻强者

用于验证：

> 新模型能否突破旧 Grade 模板。

例如：

- HeavyGod
- kyousuke
- luchov
- 其他有可靠 S 级数据的 G1/G2/G3

---

## B. 已建立 Peak 的明星

用于验证：

> 当前低迷不会抹掉 Career Peak。

例如：

- 已有明确 Top20 / Major 高峰的现役老将

---

## C. 无可靠 Performance 数据的人

用于验证：

> fallback 是否稳定、是否仍可生成合理卡。

---

# 11. v7 第一轮验收标准

不要用“和 Rating 相关性最高”作为目标。

真正该问：

1. G1/G2/G3 里，明显被模板低估的人是否被拉开？
2. 同一个 Grade 内是否终于存在有意义的能力差距？
3. G2 强枪与普通 G2 是否肉眼可分？
4. G3 新星能否合理超过部分 G4/G5 的 Firepower？
5. 历史 Peak 是否没有被当前低迷错误覆盖？
6. 没有可靠 5E 数据的人是否安全回退？
7. 四维变化是否都能解释来源，而不是为了“总分守恒”互相补偿？
8. Market / Bargain 是否能识别“低 Grade、高能力”的真正抄底卡？
9. 重新跑标准 Draft Seed 后，是否产生更有趣而不是更扁平的选人决策？

---

# 12. 明确禁止本轮做的事

本轮先不要：

- 用 Rating 一条线重算全部 649 人；
- 用当前低 Rating 下调传奇 Career Peak；
- 用 Stability 抵消 Firepower 上涨；
- 用 KAST 直接生成 Stability；
- 为了保持旧 Overall 均值强行零和；
- 同时改 Grade、四维、Price 三层；
- 为了提高数据覆盖率放宽到低级别赛事；
- 因 5E 无数据就把人判弱；
- 把 Current Tier 和 Career Grade 混成同一个概念。

---

# 13. 推荐的数据结构

建议把证据本身存下来，而不是只存最终四维。

```json
{
  "player": "Example",
  "grade": 2,
  "role": "RIFLER",
  "firepower": 84,
  "leadership": 24,
  "experience": 31,
  "stability": 63,

  "evidence": {
    "career": {
      "top20": [],
      "major_count": 1,
      "major_best": "Stage 3"
    },
    "performance": {
      "status": "strong",
      "source": "5e",
      "window": "12m",
      "tier": "S+",
      "rating": 1.21,
      "maps": 96
    }
  },

  "generation": {
    "firepower_source": "performance_evidence",
    "leadership_source": "role_prior",
    "experience_source": "career_history",
    "stability_source": "career_prior"
  }
}
```

这样以后看到一张离谱卡，可以直接回答：

> **“为什么他是84？”**

而不是重新读生成器猜。

---

# 14. 一句话原则

> **v7 的核心不是“让数据决定卡牌”，而是让每一个数值都有证据来源。**

具体来说：

> Grade 说明职业生涯被证明了多少；  
> Firepower 说明巅峰版本能打多高；  
> Leadership 说明能不能组织团队；  
> Experience 说明大赛压力下经历过多少；  
> Stability 说明发挥有多可靠。  

可靠的现代数据只负责补足原本最缺证据的那一块。

最终目标不是让模型看起来更“数学”，而是：

> **玩家看到两张同为 G2/G3 的卡时，第一次能感受到“这两个人是真的不一样”。**
