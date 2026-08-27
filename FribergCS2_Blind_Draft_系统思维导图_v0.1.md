# FribergCS2 Blind Draft 系统地图 v0.1

> 目的：停止继续“边做边漂”，把整个模式按模块拆开。后续讨论时，只讨论某一个节点，不轻易跨层修改已经稳定的模块。

## 状态标记

- ✅ **已定 / 可冻结**：方向已经明确，除非实测出现硬伤，不再推翻
- 🟡 **可运行 / 待调优**：机制成立，主要调参数、体验和 UI
- 🧪 **原型测试桩**：只为了验证想法，不代表最终玩法
- 🔵 **待实现**：方向明确，但还没进入正式玩法
- ❓ **开放问题**：还需要真人试玩才能决定

---

# 0. 核心目标

## Blind Draft 的核心体验

> 用有限预算，在身份不完全公开的情况下买职业选手，判断“这个资产值不值这个价”，组出一支有特点的队伍，再通过 Buff / Trait / 比赛 Run 看这支队伍能走多远。

### 三个核心乐趣

1. **市场错价**：这人居然只卖 $2？我是不是抄到底了？
2. **阵容构筑**：我要明星、性价比、老将、年轻枪男，还是国籍 / 旧队友核心？
3. **赛后故事**：我买到了谁、错过了谁、这支怪队最后打成什么样？

---

# 1. Player Card / 选手卡层 ✅

整个系统的底座。

## 1.1 固定身份

- nickname
- country
- club
- age
- Major 履历
- 生涯代表位置

## 1.2 位置 ✅

只保留三个 Draft 主位置：

- RIFLER
- AWPER
- IGL

原则：这是 **Draft Primary Role**，不试图完整描述现实里的副位置。像 cadiaN 这种现实中是 IGL + AWPer，系统仍只记 IGL；知名特殊情况用人工 `played_role` 维护生涯代表位置。

暂不做：Entry / Lurker / Support / Anchor、第二位置、完整现实职责系统。

## 1.3 Career Evidence Grade ✅

固定 G1 ~ G5，表示“职业生涯证据有多充分”。

它不是本局价格，也不是临场表现。

## 1.4 四维属性 ✅

- **Firepower**：个人输出上限，“能打多高”
- **Leadership**：组织、指挥、带队能力
- **Experience**：Major、大赛、深轮次经验
- **Stability**：发挥波动，“平时能兑现多少”

## 1.5 Career Peak 规则 ✅

所有卡按生涯代表版本 / 巅峰版本评价，而不是当前年龄和状态。

---

# 2. Market / 市场层 🟡

## 2.1 核心原则 ✅

顺序必须是：

> 先抽到一个已经存在的 Player → 读取固定 Grade / Card → 市场这一局再给他报价

不是先生成价格格子再决定里面是什么 Grade。

## 2.2 Market Price 🟡

价格 $1 ~ $5，价格不是 Grade。

市场可以正常报价、高估、低估，所以能出现：

- G3 卖 $2
- G4 卖 $3
- G5 卖 $4

❓ 待调：抄底概率到底多少最好？

## 2.3 出场权重 🟡

只控制“谁更容易上货架”，不改变选手数值。

原则：

> 出场率可以调，卡不能偷偷改。

---

# 3. Scout Report / 盲选信息层 🟡

每张匿名卡显示：

## 3.1 永久公开

- Price
- Position
- Country

## 3.2 一条真实能力信息 ✅

从四维中按位置加权挑一项：

- RIFLER：偏 Firepower / Stability / Experience
- AWPER：偏 Firepower / Stability / Experience
- IGL：偏 Leadership / Experience / Firepower

非 IGL 的 Leadership 基本不发，避免死线索。

## 3.3 球探区间 ✅

不显示精确值，例如不直接写 `Firepower 70`，而写：

> Firepower 60–74

原则：

- 真值一定在区间内
- 真值不一定在中点
- 区间宽度不固定
- 真值允许贴近边缘
- 每次上板重新生成，不能成为选手指纹

目标：

> 允许玩家算概率，不允许玩家算出 Grade 的唯一答案。

## 3.4 一条履历 / 身份线索 ✅

三选一：

- Club
- Major Appearances
- Age

Country 另外固定公开。

---

# 4. Board Generator / 发牌层 🟡

目前仍需要继续打磨体验。

## 4.1 基本结构

每个 Market Day 给 5 张候选卡，玩家最多签 1 人。

## 4.2 预算可行性 ✅

Board 根据当前余额和剩余席位控制可出现价格，避免后期“所有牌都买不起”。

## 4.3 Position Supply 🟡

- 缺少的位置提高出现权重
- 最后阶段才硬保底

原则：系统负责不让玩家因纯随机彻底死局，但不应该自动把完美答案送上门。

❓ 待调：缺位权重到底多少最舒服？

## 4.4 Teammate Supply 🟡

真实旧队友轻度提高出场权重，不硬塞。

## 4.5 Market Days 数量 ❓

需要继续真人试玩：

- 6 Days / 5 Picks
- 7 Days / 5 Picks

当前的新问题不是“没决策”，而是玩家已经产生 Build 想法，但可见候选人可能不够多。

---

# 5. Draft Decision / 玩家决策层 🟡

每轮同时判断：

1. **价格**：值不值 $N？
2. **球探**：某项能力大概在哪？
3. **身份**：我是不是能猜出是谁？
4. **位置**：我还缺什么？
5. **阵容方向**：我想把这队做成什么？

可能的玩家自发 Build：

- 超级明星队
- 性价比队
- CIS 青春风暴
- 丹麦核心
- 老将队
- 国际纵队
- 真实旧队重组
- 双 AWP
- 无顶级明星均衡阵容

当前最大不足：

> 玩家已经会产生这些 Build 想法，但主动追求 Build 的工具还很少。

❓ 未来是否需要一次性的 `Scouting Focus` 等轻量主动工具，暂不决定。

---

# 6. Budget / 经济层 🟡 + 🧪

## 6.1 初始预算 ✅

> $15，最终签 5 人。

## 6.2 剩余预算正式用途 🔵

正式玩法：

> 剩余 $ → Rogue Points / Buff 购买资源

所以“买明星”和“省钱做 Build”应该是两条路线。

## 6.3 当前原型测试桩 🧪

目前 Buff 还没做，所以暂时把 Rogue Points 折算成战力，只用于验证：

> 如果余钱真的有价值，省钱会不会成为真决策？

这不是最终机制，正式版不能变成固定 `$1 = Firepower +X`。

---

# 7. Roster / 阵容层 🟡

## 7.1 位置是软限制 ✅

允许：

- 没有 IGL
- 没有 AWP
- 双 AWP
- 多 IGL
- 奇怪阵容

后续由 Trait / Debuff / Run 中的适配问题承担代价，不直接禁止。

## 7.2 Chemistry 🟡

可来自：

- 真实旧队友
- 国籍 / 地区关系
- 阵容构成

## 7.3 Roster Traits 🟡

已经开始出现：

- REUNION
- INTERNATIONAL MIX
- BARGAIN 等

Trait 的第一目标不一定是加很多分，而是告诉玩家：

> “你到底组出了一支什么队。”

未来再考虑：Youth Core / Veteran Core / National Core / No Superstar / Major Champions / Star Power 等。

---

# 8. Reveal / 揭晓层 🔵 / 🟡

这是 Blind Draft 的高潮之一。

## 8.1 Your Team Reveal

逐个揭晓：

- Identity
- Grade
- 精确四维
- 当时价格
- 当时 Scout Report
- 是否低估 / 高估

## 8.2 Full Board Reveal 🔵

应该把所有轮次、所有候选人都翻出来，包括 Pass 的轮次和没买的四个人。

目的：

> 让玩家知道自己错过了什么。

## 8.3 Hindsight 与 Decision Quality 分离 🔵

不能简单写“你选错了，应该拿 X”。

要区分：

- **Hindsight**：所有隐藏信息揭晓后，哪张数学收益最高？
- **Decision Quality**：根据当时能看到的信息，这个选择是否合理？

## 8.4 Reveal 情绪标签 🔵

未来可以有：

- STEAL
- FAIR
- OVERPAY
- BIGGEST STEAL
- MISSED STEAL
- BULLET DODGED
- BETTER THAN SCOUTED
- WORSE THAN EXPECTED

目标：让结算讲故事，而不是只给排名。

---

# 9. Post-Draft Build / Rogue Buff 层 🔵

这是接下来真正需要补的大模块之一。

## 9.1 输入

- 剩余 Rogue Points
- 当前五人阵容
- 当前 Traits
- 四维结构

## 9.2 Buff 方向

### 稳定型
- Bootcamp
- Preparation
- Anti-Choke

### 高方差型
- Loose Style
- Giant Killer
- Life Game

### 地图型
- Map Specialist
- Deep Map Pool

### IGL / 战术型
- Tactical Preparation
- Better Veto

### 阵容型
- Double AWP Setup
- National Core
- Reunion 强化

## 9.3 设计原则

Buff 尽量不要只是 `Firepower +5`，而是改变队伍怎么玩。

目标：

> 省钱队和明星队不是同一条数值曲线上的高低版本。

---

# 10. Match / Run 层 🔵

这是四维真正开始“活起来”的地方。

## 10.1 卡面 vs 临场表现 ✅

固定卡 1–99；比赛中的 Effective Performance 可以超过 99，99 以上使用 Soft Cap。

## 10.2 Stability

控制单场波动：低稳定更容易爆种，也更容易拉胯。

## 10.3 Experience

在生死局、淘汰赛、BO3 / BO5、Major 深轮次提高价值。

## 10.4 Leadership

影响战术发挥、BP、Map Pool、队伍整体兑现率。

## 10.5 极简 Run 第一版 🔵

先别直接做完整 Major，只验证：

1. BO1
2. BO3
3. 高压淘汰局

如果已经能让玩家产生：

> “早知道刚才选另一个。”

说明四维真的进入 gameplay。

之后再扩：VRS / Major Qualification / Swiss / Playoffs / Final。

---

# 11. Map / BP 层 🔵

以后可能包含：

- Map Pool
- Pick / Ban
- IGL Leadership
- Experience
- Map Buff
- Double AWP 等 Trait

当前暂缓。

---

# 12. Results / 复盘层 🟡 / 🔵

最后不应该只给 `379 / 17826`。

应该拆成：

## Draft
- 选牌判断
- 市场抄底
- 最大错过

## Budget
- 花了多少
- 留了多少 Rogue Points

## Roster
- Position Fit
- Chemistry
- Traits
- 队伍风格

## Run
- 最终走到哪
- 爆冷
- Life Game
- 谁拉胯
- 谁 Carry

最终目标：

> 每一局都能总结成一句有故事的话。

---

# 13. Meta / 图鉴与长期层 🔵

跨模式共享：

- 遇到过哪些选手
- 买到过哪些人
- 抄底次数
- 最贵冤种
- 最成功阵容
- Trait 收集
- Major 冠军次数
- Challenge Link

不急着做，但架构上要预留。

---

# 14. 当前明确不要再做的东西

- ❌ **Quality Offset**：不用队伍排名 / 活跃度 / 生涯跨度拼隐藏 Rating
- ❌ **Overall 零和整形**：Overall 只是内部估值，不是守恒量
- ❌ **精确四维直接出现在 Blind Card**：会直接泄露 Grade
- ❌ **永久 `$1 = Firepower +X`**：只能做测试桩，不是正式经济机制
- ❌ **每轮硬塞 AWP + IGL**：已经证明会挤压 Rifle
- ❌ **硬塞真实队友**：只做轻度概率加权
- ❌ **为所有现实角色建立副位置系统**：Draft Role 保持轻量

---

# 15. 当前开发优先级

## 第一阶段：冻结 Draft 主体

已基本稳定：

- Player Card
- Grade
- Career Peak
- Market Price 方向
- Scout Report 结构
- Dynamic Board 方向

只继续调：

- Market 错价概率
- 6/1 还是 7/2
- Position Supply 权重
- Teammate Supply 权重

## 第二阶段：补 Reveal

优先做：

- 全 Board Reveal
- Hindsight
- Missed Steal
- Trait 展示
- “为什么这支队是这样”的解释

## 第三阶段：做极简 Rogue Build

目标不是大量 Buff，而是先证明：

> 剩钱真的可以形成另一条 Build。

## 第四阶段：做极简 Run

只跑：

- BO1
- BO3
- Elimination Match

验证 Firepower / Stability / Experience / Leadership 是否真的改变玩家选择。

## 第五阶段：再考虑完整 Major

最后再加：

- VRS
- Stage
- Swiss
- Playoffs
- BP
- Map Pool
- 完整 Buff 池

---

# 16. 后续讨论规则

以后遇到一个问题，先问：

### ① 它属于哪个模块？

Player Card / Market / Scout / Board / Draft / Budget / Roster / Reveal / Buff / Run？

### ② 是方向错了，还是参数没调好？

如果只是“出现率有点高”，就不要推翻整个系统。

### ③ 它是正式机制还是测试桩？

不要再把原型为了验证数学而存在的临时算法，当成正式玩法。

### ④ 有没有真人试玩证据？

优先相信“玩起来哪里不舒服”，而不是只看纸面是否最优。

---

# 当前一句话状态

> **Blind Draft 的主体已经成立。现在不是继续重新设计整个游戏，而是逐块优化 Market、Board、Reveal、Build 和 Run，让已经能运行的骨架逐渐长出“味道”。**
