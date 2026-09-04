# -*- coding: utf-8 -*-
"""引擎的全部系数，以及由系数直接导出的那几条曲线。

**这是参数的唯一出处。** 别的模块要么 `from .params import <函数>`，要么
`from . import params as PA` 再写 `PA.MAP_SCALE`——后者是必须的，只要那个量
会被扫描或改写（`SIGMA_SCALE` / `TEAM_RHO` / `MAP_SCALE`）：`from .params
import SIGMA_SCALE` 绑的是当时那个值，`lab.tune()` 改了 `params.SIGMA_SCALE`
它也不会跟着变，于是扫描表里五行数字一模一样，而且不报错。

每个数后面都写了它是从哪儿反推出来的。没有「随手调一下试试」的余地：
§6.3 已冻结 Stability 分布，宏观爆冷只许动 MAP_SCALE。
"""
# §4.2 角色权重。Carry Hierarchy 顺位由**卡面火力**定死，当图 Roll 完不重排。
STAR_WEIGHTS = (.35, .25)          # 第一枪、第二枪；其余三人平摊 REST_WEIGHT
REST_WEIGHT = .40

# §6 Stability → 兑现率。三条系数都由设计稿 §6.1/§6.3 那两组例子反推：
#   「S90 正向概率 60%，S50 正向概率 42%」                  -> P_UP
#   「S90 F80：大多 78~85，偶尔 74，也能 89/92」            -> σ↑≈4  σ↓≈3
#   「S50 F80：常 62~77，偶尔 84，极少 93/97」              -> σ↑≈8  σ↓≈10
P_UP_AT_50, P_UP_AT_90 = 0.42, 0.60
SIGMA_UP_AT_50, SIGMA_UP_AT_90 = 8.0, 4.0
SIGMA_DOWN_AT_50, SIGMA_DOWN_AT_90 = 10.0, 3.0

# 分布宽度的总缩放。§4 的例子对应 1.0。
#
# 设计稿 v0.3 §6.3 已经**冻结**这条分布：不要再为了宏观爆冷率去动它。放大到
# 4 倍确实能把爆冷拉回旧版水平，代价是 F80/S50 的人单图能打 11~130，Player
# Story 就毁了。爆冷不够就调 MAP_SCALE，不要重新把个人表现搞疯。
SIGMA_SCALE = 1.0

# 队内相关性（高斯 copula）。v0.3 §12 已判 Team Shared Form 退役，所以这条
# 默认 0 并且**不再是调节爆冷的手段**，只作为历史对照留着：
# 实测把它拉到 0.8 也只能把 +10 分差的爆冷从 0.9% 抬到 10.4%（救不动），
# 而且会重新出现整队一起爆、一起崩。队伍级的未建模随机现在归 Map Residual。
TEAM_RHO = 0.0

# §13 Map Residual —— 替代 v1 那个最终 Bernoulli 胜负骰。
#
# 它代表这版引擎**没有展开模拟**的地图级内容：地图适配、手枪局、经济与连败
# 奖励、timing、clutch、CT/T、关键首杀、局内战术克制。它不是 Player Form，
# 所以绝不参与 MVP / LIFE GAME，也不改任何人的 Effective Firepower（§13.4）。
#
# 分布取 Logistic(0, MAP_SCALE)。
#
# **MAP_SCALE 只控制 Residual 这一层，它不是整套引擎的胜率曲线。** 设计稿
# §13.3 说 Residual 与经典 logistic 胜率「统计意义上等价」，这一点只在
# 「双方 Team Performance 是常数」时成立。实际 SA、SB 各自含 Player 波动
# （两队之差 σ≈4.3，Residual 自己 σ≈10.9），最终曲线是两者的**卷积**：
#
#   火力差   实测(整套)   logistic(gap/6)   反解等效 scale
#   +2        57.0%          58.3%             7.06
#   +5        67.5%          69.7%             6.83
#   +10       81.8%          84.1%             6.66
#   +20       95.8%          96.6%             6.40
#   +30       99.1%          99.3%             6.36
#
# 等效 scale 不是常数，它随分差从 7.1 漂到 6.4——所以整条曲线连 logistic 形状
# 都不是，谈不上「换算」。**任何胜率结论都必须靠 Monte Carlo 实测**，不能由
# MAP_SCALE 解析推导；`--tune` 和 `--lab` 就是干这个的。同理，下面 Leadership
# 那三个数用的「1 分 ≈ 3.5 个百分点」也是实测出来的，不是算出来的。
#
# 6 是扫 4/5/6/7/9 之后选的，§13.3 的四条验收目标同时满足（见 `--tune`）：
#   +2 只是小优 56.7% / +5 明显优势但远非必胜 67.0%
#   +10 强 Favorite 但 BO1 仍有 18.8% 爆冷 / +20 极难翻但不机械 100%
# 旧的 WIN_SCALE=13 明确不迁移——那会让 +10 只剩 68%，选手层被宏观随机淹没。
# 留一个常量只为 --compare 画那条历史曲线，引擎里没有任何地方读它。
V1_WIN_SCALE = 13.0
MAP_SCALE = 6.0

# §8 压力只扭曲已经掷出来的那个结果，不掷第二个骰子，也不做队伍级罚分。
# 系数由原文的例子定死：「新人 -7 经验25 生死局 → -11」「老将 -7 经验90 → -7/-8」
#   1 + k × 1.2 × (1-0.25) = 11/7  ->  k ≈ 0.63
CHOKE_AMP = 0.63

# §8.1 Format 和 Pressure 是两件事：BO1 只说明你有几张图回归实力，不代表高压。
PRESSURE = {"swiss": 0.0, "advance": 0.8, "elim": 1.0,
            "decider": 1.2, "playoff": 1.2, "semi": 1.4, "final": 1.6}

# §9 Leadership 只做团队执行。数值**不是拍的，是从胜率目标反推的**——这正是
# v0.3 §9.2 立的新规矩：先定「应该贡献多少胜率差」，再按 MAP_SCALE 换算。
#
# 目标（§9.2）：五人火力完全相同时，elite IGL 比普通 IGL 单图多 4~6 个百分点，
# 无 IGL 比普通 IGL 少 6~10 个百分点。
# 在 MAP_SCALE=6 下五五开附近实测 1 分 Strength ≈ 3.5 个百分点，于是：
#   elite 相对普通 +1.45 分 ≈ +5.1pt；无 IGL 相对普通 -2.30 分 ≈ -8.1pt。
#
# 旧的 +2.5 / -3.0 是「看起来不大」拍出来的，实测把五五开拉到 65% / 26%，
# 远超目标——这就是 §9.2 说「那个口径不可靠」的原因。普通 IGL 取 0 作基准，
# 所以 MAP_SCALE 一变，这三个数必须跟着重算。
TACTICAL_AT_65, TACTICAL_AT_96 = 0.0, 1.45
NO_IGL_TACTICAL = -2.30
TACTICAL_CLAMP = 3.0

# §5 阵容结构修正留在 Entry 里；无 IGL 不在这里罚（交给上面那条），
# 否则又变成同一个缺点收两次费。
NO_AWP_PENALTY = -4.0

# §7 卡面上限 99 是**卡牌尺度**的上限，不是人类单图表现的物理上限。
# 设计稿认为 v1 那个「超出部分只算 35%」太狠，第一轮先完全放开。
SOFT_CAP_AT = 99.0
SOFT_CAP_RATE = 1.0                # 1.0 = 不打折；调小才开始压

# §0.5 叙事阈值
LIFE_GAME_AT = 12.0
UNDERPERFORM_AT = -12.0


def _lerp(x, x0, y0, x1, y1):
    """两点定直线，外推不设限——系数本来就要靠 lab 往两头试。"""
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def p_up(stability):
    return min(0.95, max(0.05, _lerp(stability, 50, P_UP_AT_50, 90, P_UP_AT_90)))


def sigma_up(stability):
    return SIGMA_SCALE * max(0.5, _lerp(stability, 50, SIGMA_UP_AT_50,
                                        90, SIGMA_UP_AT_90))


def sigma_down(stability):
    return SIGMA_SCALE * max(0.5, _lerp(stability, 50, SIGMA_DOWN_AT_50,
                                        90, SIGMA_DOWN_AT_90))


def soft_cap(x):
    if x <= SOFT_CAP_AT or SOFT_CAP_RATE >= 1.0:
        return x
    return SOFT_CAP_AT + (x - SOFT_CAP_AT) * SOFT_CAP_RATE


def tactical(team_lead, has_igl):
    """§9 Leadership 的全部作用：一个 Team Execution 修正，幅度由胜率目标定。"""
    if not has_igl:
        return NO_IGL_TACTICAL
    v = _lerp(team_lead, 65, TACTICAL_AT_65, 96, TACTICAL_AT_96)
    return max(-TACTICAL_CLAMP, min(TACTICAL_CLAMP, v))
