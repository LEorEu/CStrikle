# -*- coding: utf-8 -*-
"""Match Engine v2 原型 —— 四维各干一件事，一张图 11 个随机数。

落地的是设计稿 `比赛引擎_v0.3.md`。它要求
这一版做成独立原型而不是就地改 v1，所以这个文件**不碰** `match.py`，也不被它
import。v1 已退役删除，`--compare` 画的那条历史曲线只剩一个常量。§15 的 Pipeline：

                     Firepower
                         │
                每人唯一一次 Roll          ← 10 个 Player RNG
                         │
              ┌──────────┴─────────┐
              │                    │
          Stability            Pressure
         定义分布形状          Experience
              │                    │
              └──────────┬─────────┘
                         ↓
                Effective Firepower
                         ↓
                 固定角色权重聚合          ← 顺位按卡面定死（§4.2）
                         ↓
                  Team Firepower
                         ↓
                  Leadership              ← 团队执行，按胜率反推（§9.2）
                  Chem / Structure
                         ↓
                 Team Performance
                         ↓
              + Map Residual              ← 第 11 个 RNG（§13）
                         ↓
                Final Map Margin
                         ↓
                  Margin > 0 获胜

和 v1 的五条硬差别：

  §4.1  Entry 不再有 Leadership/Experience/Stability 各 20% 的静态权重。
        Entry 就是「这五个人纸面有多能打」，量纲因此和 v1 完全不同
        （≈80 而不是 ≈65），两套 Entry 数字**不可直接比较**。
  §6    Stability 不再是对称正态的宽度，而是**兑现率**：决定分布往哪边偏、
        两条尾巴各有多长。高稳定的人正向结果更常见但幅度温和；低稳定的人
        更常打不出来，可正向尾巴更长——LIFE GAME 从这里来。
  §8    Pressure/Experience 不掷第二个骰子，只扭曲同一次 Player Roll，
        而且**逐人**发生，不再有队伍级 CHOKE 罚分。
  §12   Team Shared Form 退役（v1 的 TEAM_FORM_SHARE=0.65）。
  §13   最终 Bernoulli 胜负骰退役，换成 Map Residual：它代表这版引擎没有
        展开模拟的地图级内容，**不参与 Player Story**。

第一版原型曾按更早的复盘把 §13 那层也删掉，直接比 Team Performance 大小。
实测证明不行：+5 分就 89.7%、+10 分 99.4%，整届 Major 退化成按 Entry 排序的
表格。`--tune` 里那张「三选二」的表就是这条结论的出处，设计稿 §13.5 采纳了它。

所有系数都在下面集中，并且注明了各自的来源——要么从设计稿给的例子反推
（Stability 分布、Choke 幅度），要么从胜率目标反推（Leadership）。§6.3 已经
**冻结** Stability 分布：以后爆冷不够只调 MAP_SCALE，不要再动个人波动。
"""
import argparse
import collections
import math
import random
import statistics as st

from . import draft as P
from . import major as M

NORM = st.NormalDist()


# ------------------------------------------------------------------ 参数

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


# ------------------------------------------------------------------ 一次 Roll

def form_delta(u, stability):
    """§6.2：一个 uniform 反演出一条非对称分布，每人每图**恰好一个 Player RNG**。

    u < p_down 落在负半支，否则落在正半支；两支各自有自己的宽度。这样
    「往哪边偏」和「偏多少」共用同一个 u，不需要先掷方向再掷幅度。
    """
    pu = p_up(stability)
    pd = 1.0 - pu
    if u < pd:                                  # 负半支：u/pd 映到 (0, .5)
        q = max(1e-9, u / pd) * 0.5
        return sigma_down(stability) * NORM.inv_cdf(q)
    q = 0.5 + min(1.0 - 1e-9, (u - pd) / pu) * 0.5    # 正半支
    return sigma_up(stability) * NORM.inv_cdf(q)


def under_pressure(delta, experience, pressure):
    """§8.3：压力不掷新骰子，只把**负面**结果按经验放大。正向发挥不受影响。"""
    if pressure <= 0.0 or delta >= 0.0:
        return delta, 0.0
    amp = 1.0 + CHOKE_AMP * pressure * (1.0 - experience / 100.0)
    return delta * amp, delta * amp - delta     # (新值, 因压力多丢的分)


class Roll(object):
    """一个人这张图的完整账本，逐项可加回 delta。"""

    __slots__ = ("card", "eff", "delta", "form", "choke", "capped", "weight")

    def __init__(self, card, eff, delta, form, choke, capped, weight):
        self.card, self.eff, self.delta = card, eff, delta
        self.form, self.choke, self.capped = form, choke, capped
        self.weight = weight


# ------------------------------------------------------------------ 一支队

class Team(object):
    """v2 的一支队。静态部分只剩火力、默契和结构修正（§4.1）。"""

    def __init__(self, name, roster, chem=0.0, is_player=False):
        self.name, self.roster, self.chem = name, roster, chem
        self.is_player = is_player

        igls = [c for c in roster if c.get("caller", c["position"] == "IGL")]
        self.has_igl = bool(igls)
        self.team_lead = max(c["leadership"] for c in igls) if igls else 0.0
        self.tactical = tactical(self.team_lead, self.has_igl)

        # §4.2 顺位按卡面火力定死
        order = sorted(range(len(roster)), key=lambda i: -roster[i]["firepower"])
        rest = order[2:]
        self.weights = [0.0] * len(roster)
        for i, w in zip(order, STAR_WEIGHTS):
            self.weights[i] = w
        for i in rest:
            self.weights[i] = REST_WEIGHT / len(rest)

        self.no_awp = not any(c["position"] == "AWPER" for c in roster)
        self.structure = (NO_AWP_PENALTY if self.no_awp else 0.0) + chem
        # 赛事外壳用的字段：stage 由区域 VRS 名额定，seed 是 Stage 内的种子。
        self.stage = None
        self.seed = 0
        self.vrs = self.hltv = None
        self.reset()

    def reset(self):
        self.w = self.l = 0
        self.opponents = []

    @property
    def record(self):
        return (self.w, self.l)

    def fork(self):
        """给晋级者做一个新实例带进下一个 Stage。

        必须新建而不是复用：`run_stage` 开局会 reset 战绩，直接把同一个对象
        传下去会把上一层的最终战绩擦掉，`stages[1]` 里的晋级名单就会显示成
        下一层的比分（曾经真的出现过「Stage 1 晋级 MIBR(1-3)」）。
        """
        t = Team(self.name, self.roster, self.chem, self.is_player)
        t.structure = self.structure          # 保住人工 adjust
        t.stage, t.vrs, t.hltv = self.stage, self.vrs, self.hltv
        return t

    @property
    def difficulty(self):
        """§2.3 Buchholz：已交手对手的胜场总和减负场总和。"""
        return sum(o.w for o in self.opponents) - sum(o.l for o in self.opponents)

    @property
    def done(self):
        return self.w >= 3 or self.l >= 3

    def entry(self):
        """§4.1 Entry = 纸面火力 + 默契 + 结构修正。没有 L/E/S 的静态权重。

        注意量纲：这个数在 80 上下，v1 的 Entry 在 65 上下，两者不可比。
        """
        return (sum(w * c["firepower"] for w, c in zip(self.weights, self.roster))
                + self.structure)

    def play_map(self, rng, pressure):
        """一张图：五个人各一个随机数，聚合，加战术执行。"""
        detail = []
        # TEAM_RHO=0 时这就是 §11 要的「每人恰好一个随机数」；调大它会多掷
        # 一个全队共用的 z，代价是每图 11 个随机数而不是 10 个。
        z_team = rng.gauss(0.0, 1.0) if TEAM_RHO > 0.0 else 0.0
        rho = min(0.999, max(0.0, TEAM_RHO))
        for w, c in zip(self.weights, self.roster):
            if rho > 0.0:
                z = (rho ** .5) * z_team + ((1.0 - rho) ** .5) * rng.gauss(0, 1)
                u = NORM.cdf(z)
            else:
                u = rng.random()
            raw = form_delta(u, c["stability"])
            after, choke = under_pressure(raw, c["experience"], pressure)
            eff = soft_cap(c["firepower"] + after)
            capped = eff - (c["firepower"] + after)
            detail.append(Roll(c, eff, eff - c["firepower"],
                               raw, choke, capped, w))
        fire = sum(t.weight * t.eff for t in detail)
        return fire + self.tactical + self.structure, detail


# ------------------------------------------------------------------ 一张图 / 一场

def map_residual(rng, scale=None):
    """§13.3 Logistic(0, MAP_SCALE) 的逆变换采样。一张图掷一次。"""
    scale = MAP_SCALE if scale is None else scale
    if scale <= 0.0:
        return 0.0
    u = min(1.0 - 1e-12, max(1e-12, rng.random()))
    return scale * math.log(u / (1.0 - u))


class MapResult(object):
    def __init__(self, sa, sb, da, db, a, b, residual=0.0):
        self.sa, self.sb, self.da, self.db = sa, sb, da, db
        self.a, self.b = a, b
        self.residual = residual
        # §13.2 Final Margin = 双方表现差 + Map Residual，正者获胜。
        # 没有第二次 Bernoulli——残差本身就是那层随机。
        self.margin = (sa - sb) + residual
        self.winner_a = self.margin > 0

    def _pick(self, key, chooser):
        ta, tb = chooser(self.da, key=key), chooser(self.db, key=key)
        return ((ta, True) if chooser(key(ta), key(tb)) == key(ta)
                else (tb, False))

    @property
    def mvp(self):                        # §0.5 打得最好 = 最终有效火力最高
        return self._pick(lambda t: t.eff, max)

    @property
    def life(self):                       # §0.5 最超常
        return self._pick(lambda t: t.delta, max)

    @property
    def under(self):                      # §0.5 最崩
        return self._pick(lambda t: t.delta, min)


def play_map(a, b, rng, pressure, scale=None):
    sa, da = a.play_map(rng, pressure)
    sb, db = b.play_map(rng, pressure)
    return MapResult(sa, sb, da, db, a, b, map_residual(rng, scale))


class MatchResult(object):
    def __init__(self, a, b, bo, pressure, maps):
        self.a, self.b, self.bo, self.pressure, self.maps = a, b, bo, pressure, maps
        self.a_maps = sum(1 for m in maps if m.winner_a)
        self.b_maps = len(maps) - self.a_maps
        self.winner = a if self.a_maps > self.b_maps else b
        self.loser = b if self.winner is a else a


def play_match(a, b, rng, bo, pressure, scale=None):
    maps, aw, bw = [], 0, 0
    need = bo // 2 + 1
    while aw < need and bw < need:
        m = play_map(a, b, rng, pressure, scale)
        maps.append(m)
        if m.winner_a:
            aw += 1
        else:
            bw += 1
    return MatchResult(a, b, bo, pressure, maps)


# ------------------------------------------------------------------ 取数
#
# 赛场只有一个来源：下面的 `major_field`（区域 VRS 名额）。曾经这里还有一个
# `field_teams`，走 `major.make_field`，于是 --lab / --demo 和 /play 拿的是两个
# 不同的赛场。今天两者恰好一致（field_source=current 时 make_field 也绕回
# build_pool_field），所以谁都没发现；但把配置翻成 major_pool，验收就会在历史
# 阵容上跑，而玩家仍然面对 VRS 名额那 32 支——不报错，只是量的不是同一个游戏。
# 已删除，全部走 major_field。


def named_team(label, nicknames, cards=None):
    cards = cards or {c["nickname"]: c for c in P.load_cards()}
    return Team(label, [cards[n] for n in nicknames], 0.0, is_player=True)


def roster_cards(spec):
    """"nick,nick,..." 或 FIXTURES 的名字 -> 五张卡。认昵称也认 page，不分大小写。

    从 v1 的 `pick_roster` 搬过来。有它才能拿任意一支真实阵容对着引擎跑，
    不然能上场的只有写死的 FIXTURES 那三支。
    """
    names = FIXTURES.get(spec)
    index = {}
    for c in P.load_cards():
        index.setdefault(c["page"].casefold(), c)
        index.setdefault(c["nickname"].casefold(), c)
    want = list(names) if names else [w.strip() for w in spec.split(",") if w.strip()]
    bad = [w for w in want if w.casefold() not in index]
    if bad:
        raise KeyError("卡库里没有：%s" % "、".join(bad))
    if len(want) != P.SLOTS:
        raise ValueError("要正好 %d 个人，给了 %d 个" % (P.SLOTS, len(want)))
    return [index[w.casefold()] for w in want]


def roster_team(spec, label=None):
    return Team(label or spec, roster_cards(spec), 0.0, is_player=True)


# ------------------------------------------------------------------ 固定测试阵容

# 1.txt 结尾点名要的三支。存成常量，任何系数改动都对着同一批人跑。
FIXTURES = {
    "donk carry": ["donk", "molodoy", "tN1R", "Kvem", "spaze"],
    "ZywOo carry": ["ZywOo", "Kvem", "spaze", "tN1R", "molodoy"],
    "五个普通职业哥": ["susp", "allu", "KHRN", "VINI", "pronax"],
}


def _fake(nick, fire, stab, exp=60, lead=25, pos="RIFLER"):
    return {"nickname": nick, "position": pos, "firepower": fire,
            "stability": stab, "experience": exp, "leadership": lead,
            "caller": pos == "IGL"}


def _probe(label, fire, stab, exp=60, lead=25, igl_lead=None):
    """形状受控的探针队：五个人同参数，只有要考察的那一维在动。"""
    roster = [_fake("%s%d" % (label, i), fire, stab, exp, lead)
              for i in range(4)]
    roster.append(_fake("%sIGL" % label, fire, stab, exp,
                        igl_lead if igl_lead is not None else lead,
                        "IGL" if igl_lead is not None else "RIFLER"))
    return Team(label, roster)


def win_rate(a, b, bo, pressure, runs, seed=1, scale=None):
    rng = random.Random(seed)
    return sum(play_match(a, b, rng, bo, pressure, scale).winner is a
               for _ in range(runs)) / runs


def _entry_probe(label, target, stab=70):
    """造一支 entry() 正好等于 target 的探针队。

    entry() 对火力是斜率 1 的线性函数（权重和为 1），所以一次修正就精确。
    """
    t = _probe(label, 70.0, stab)
    return _probe(label, 70.0 + (target - t.entry()), stab)


def duel(high, low, runs=20000, stab=70, seed=20260902):
    """两个 Entry 之间的胜率锚。从 v1 的 --duel 搬过来，口径换成 v2。

    §13.3：MAP_SCALE 只控制 Residual 那一层，胜率**只能实测**。所以每次动
    MAP_SCALE / SIGMA_SCALE / 任何队伍层 modifier 之后，都要重新跑这个数，
    不能从系数上算。
    """
    a, b = _entry_probe("HI", high, stab), _entry_probe("LO", low, stab)
    print("Entry %.1f vs %.1f（纯火力口径，稳定同为 %d，各 %d 次）"
          % (a.entry(), b.entry(), stab, runs))
    out = {}
    for bo in (1, 3):
        out[bo] = win_rate(a, b, bo, 0.0, runs, seed)
        print("  BO%d  强队胜率 %.1f%%" % (bo, 100.0 * out[bo]))
    print("  MAP_SCALE=%.1f  SIGMA_SCALE=%.2f" % (MAP_SCALE, SIGMA_SCALE))
    return out


def stats(runs=200, seed=20260828):
    """整届分布：强队是不是更容易晋级但不是必进？BO1 是不是更容易爆冷？

    从 v1 的 --stats 搬过来（设计稿 v0.1 §35 的 Q1/Q2）。两处口径变了：

      - v1 按 Projected Seed #1~32 排，那是 Entry 分层的世界；v2 的 Stage 由
        区域 VRS 名额定，所以这里按 Entry 排但**把 Stage 一起印出来**，
        两把尺子的错位在这张表上是看得见的，不是被排序抹平的。
      - v1 的实力差用 baseline()（含 L/E/S）；v2 用 entry()（纯火力）。
    """
    field, asof = major_field(1)
    rng = random.Random(seed)
    playoffs = collections.Counter()
    gap = collections.defaultdict(lambda: [0, 0])       # (bo, 档) -> [场次, 强队赢]
    for _ in range(runs):
        stages, logs = run_major(field, rng)
        for t in stages[3][1]:
            playoffs[t.name] += 1
        for stage in (1, 2, 3):
            for _rnd, results in logs[stage]:
                for r in results:
                    ea, eb = r.a.entry(), r.b.entry()
                    strong = r.a if ea >= eb else r.b
                    key = (r.bo, min(int(abs(ea - eb) // 5) * 5, 20))
                    gap[key][0] += 1
                    gap[key][1] += 1 if r.winner is strong else 0

    print("=" * 74)
    print("整届分布  快照 %s  %d 届  MAP_SCALE=%.1f" % (asof or "?", runs, MAP_SCALE))
    print("=" * 74)
    print()
    print("[Q1] 进 Playoffs 的概率（Stage 归属由区域 VRS 名额定，不是 Entry）")
    print("  %-22s %5s %5s %6s %9s" % ("队", "Stage", "VRS", "Entry", "Playoffs"))
    for t in sorted(field, key=lambda t: -t.entry()):
        print("  %-22s %5d %5s %6.1f %8.1f%%"
              % (t.name, t.stage, t.vrs or "-", t.entry(),
                 100.0 * playoffs[t.name] / runs))
    print()
    print("[Q2] 强的一方赢了多少（实力差按 Entry 分档）")
    print("        实力差     BO1 强队胜率        BO3 强队胜率")
    for g in (0, 5, 10, 15, 20):
        row = []
        for bo in (1, 3):
            n, w = gap[(bo, g)]
            row.append("%5.1f%% (n=%5d)" % (100.0 * w / n, n) if n
                       else "      -        ")
        lab_ = "%2d~%-2d" % (g, g + 5) if g < 20 else " 20+ "
        print("        %s      %s  %s" % (lab_, row[0], row[1]))


# ------------------------------------------------------------------ lab

def lab(runs=4000):
    """1.txt 结尾列的六项验收，一次跑完。"""
    cards = {c["nickname"]: c for c in P.load_cards()}
    field = {t.name: t for t in major_field(1)[0]}
    top5 = sorted(field.values(), key=lambda t: -t.entry())[:5]
    mid = min(field.values(), key=lambda t: abs(t.entry() - 80.0))

    print("=" * 74)
    print("Match Engine v2 — lab")
    print("=" * 74)
    print("注意：v2 的 Entry 是纯火力口径（≈80），和 v1 的 ≈65 不可直接比较。")

    print("\n【1】超级明星 MVP 占比 / 【2】低卡 LIFE GAME 占比")
    print("  %-14s %-10s %5s %6s %8s %8s" %
          ("阵容", "选手", "火力", "稳定", "MVP", "LIFE"))
    for label, names in FIXTURES.items():
        team = named_team(label, names, cards)
        rng = random.Random(7)
        mvp = {c["nickname"]: 0 for c in team.roster}
        life = dict(mvp)
        for _ in range(runs):
            _s, d = team.play_map(rng, 0.0)
            mvp[max(d, key=lambda t: t.eff).card["nickname"]] += 1
            top = max(d, key=lambda t: t.delta)
            if top.delta >= LIFE_GAME_AT:
                life[top.card["nickname"]] += 1
        head = label
        for c in sorted(team.roster, key=lambda c: -c["firepower"]):
            n = c["nickname"]
            print("  %-14s %-10s %5d %6d %7.1f%% %7.1f%%"
                  % (head, n, c["firepower"], c["stability"],
                     100 * mvp[n] / runs, 100 * life[n] / runs))
            head = ""

    print("\n【3】BO1 / BO3 爆冷差（同稳定，火力差 10 分）")
    strong, weak = _probe("强", 80, 70), _probe("弱", 70, 70)
    for bo in (1, 3):
        r = 1 - win_rate(strong, weak, bo, 0.0, runs, seed=11)
        print("  BO%d  弱队爆冷 %.1f%%" % (bo, 100 * r))

    print("\n【4】低经验队在高压局的变化（同火力同稳定，只差经验）")
    ref = _probe("ref", 78, 60, exp=60)
    for exp in (25, 55, 90):
        t = _probe("E%d" % exp, 78, 60, exp=exp)
        base = win_rate(t, ref, 1, PRESSURE["swiss"], runs, seed=13)
        hot = win_rate(t, ref, 1, PRESSURE["decider"], runs, seed=13)
        print("  经验 %2d   普通轮 %.1f%%  ->  生死局 %.1f%%   (%+.1f)"
              % (exp, 100 * base, 100 * hot, 100 * (hot - base)))

    print("\n【5】顶级 IGL 的实际胜率差（同五个人，只换 IGL 的领导力）")
    ref2 = _probe("ref", 78, 60, igl_lead=65)
    for lead, tag in ((96, "gla1ve 级"), (65, "普通"), (50, "弱")):
        t = _probe("L%d" % lead, 78, 60, igl_lead=lead)
        print("  领导力 %2d %-9s 战术执行 %+.2f   对普通 IGL 队胜率 %.1f%%"
              % (lead, tag, t.tactical, 100 * win_rate(t, ref2, 1, 0.0, runs, 17)))
    no_igl = _probe("无IGL", 78, 60)
    print("  无 IGL             战术执行 %+.2f   对普通 IGL 队胜率 %.1f%%"
          % (no_igl.tactical, 100 * win_rate(no_igl, ref2, 1, 0.0, runs, 17)))

    print("\n【6】donk + molodoy + tN1R 到底是不是 Favorite 了")
    me = named_team("donk carry", FIXTURES["donk carry"], cards)
    print("  你的 Entry %.1f（纯火力口径）" % me.entry())
    print("  对中游 %-14s Entry %.1f   BO1 %.1f%%   BO3 %.1f%%"
          % (mid.name, mid.entry(), 100 * win_rate(me, mid, 1, 0.0, runs, 19),
             100 * win_rate(me, mid, 3, 0.0, runs, 19)))
    for t in top5:
        print("  对 Top5 %-13s Entry %.1f   BO1 %.1f%%   BO3 %.1f%%"
              % (t.name, t.entry(), 100 * win_rate(me, t, 1, 0.0, runs, 19),
                 100 * win_rate(me, t, 3, 0.0, runs, 19)))


def compare(runs=4000):
    """§9 的代价：把「直接比大小」和 v1 的 logistic 摆在一起看。

    这是这一版最容易翻车的地方——删掉胜负骰会让胜负高度确定，弱队再也没有
    「今天状态好就偷一张图」的空间。改任何分布系数都先看这张表。
    """
    # v1 退役了，但它那条参照曲线是个纯公式（§27 的 logistic，WIN_SCALE=13），
    # 抄一行常量比为了画对照留着整个 v1 引擎便宜。这是历史刻度，不参与任何计算。
    v1_logistic = lambda gap: 1.0 / (1.0 + math.exp(-gap / V1_WIN_SCALE))  # noqa: E731
    print("=" * 74)
    print("§9 代价核对 — 同样的实力差，两版给出的胜率")
    print("=" * 74)
    print("  %-8s %12s %12s %12s" % ("差距", "v1 logistic", "v2 BO1", "v2 BO3"))
    for gap in (2, 5, 10, 20):
        a, b = _probe("A", 70 + gap, 65), _probe("B", 70, 65)
        print("  %-8s %11.1f%% %11.1f%% %11.1f%%"
              % ("+%d" % gap, 100 * v1_logistic(gap),
                 100 * win_rate(a, b, 1, 0.0, runs, 23),
                 100 * win_rate(a, b, 3, 0.0, runs, 23)))
    print()
    print("  v1 的差值是 Entry 分（含 L/E/S），v2 是纯火力分，刻度本就不同；")
    print("  这张表要看的是**曲线陡不陡**，不是同一行两个数谁大。")
    print("  判据：v2 的 BO1 若在 +5 分处就压过 85%，说明分布太窄、爆冷没了。")

    print("\n  当图强度的离散程度（v2 里爆冷的唯一来源）：")
    cards = {c["nickname"]: c for c in P.load_cards()}
    for label, names in FIXTURES.items():
        team = named_team(label, names, cards)
        rng = random.Random(29)
        s = [team.play_map(rng, 0.0)[0] for _ in range(runs)]
        print("    %-14s 均值 %.1f  σ %.2f" % (label, st.mean(s), st.pstdev(s)))


def show_map(m, indent="    "):
    """一张图的逐人账本；v2 的每一分变化都能拆到底。"""
    out = []
    for detail, side, team, total in ((m.da, "你", m.a, m.sa),
                                      (m.db, "对手", m.b, m.sb)):
        out.append("%s%s %s — 火力聚合 %.1f  战术执行 %+.2f  结构 %+.1f  = %.1f"
                   % (indent, side, team.name,
                      sum(t.weight * t.eff for t in detail),
                      team.tactical, team.structure, total))
        for t in sorted(detail, key=lambda t: -t.weight):
            why = ["状态 %+.1f" % t.form]
            if t.choke:
                why.append("压力 %+.1f" % t.choke)
            if round(t.capped, 1):
                why.append("软顶 %+.1f" % t.capped)
            out.append("%s  %-12s x%.2f  %3d -> %5.1f  %+6.1f = %s%s"
                       % (indent, t.card["nickname"], t.weight,
                          t.card["firepower"], t.eff, t.delta, "，".join(why),
                          "  LIFE GAME" if t.delta >= LIFE_GAME_AT else
                          ("  UNDERPERFORM" if t.delta <= UNDERPERFORM_AT
                           else "")))
    out.append("%s表现差 %+.1f  Map Residual %+.1f（未建模的地图/经济/timing）"
               "  ->  Margin %+.1f  %s"
               % (indent, m.sa - m.sb, m.residual, m.margin,
                  "你赢" if m.winner_a else "对手赢"))
    if (m.sa > m.sb) != m.winner_a:
        out.append("%s  ↳ 表现更好的一方输了——这张图是被未建模因素翻掉的"
                   % indent)
    return "\n".join(out)


def demo(name="donk carry", seed=5, label=None):
    me = roster_team(name, label)
    name = me.name
    opp = min(major_field(1)[0], key=lambda t: abs(t.entry() - me.entry()))
    rng = random.Random(seed)
    for bo, tag in ((1, "swiss"), (3, "decider")):
        r = play_match(me, opp, rng, bo, PRESSURE[tag])
        print("\n%s  vs %s  (BO%d, pressure %.1f)  %s %d:%d"
              % (name, opp.name, bo, PRESSURE[tag],
                 "WIN" if r.winner is me else "LOSS", r.a_maps, r.b_maps))
        for i, m in enumerate(r.maps, 1):
            mvp, mine = m.mvp
            print("  Map %d  强度 %.1f : %.1f   MVP %s %d->%.0f%s"
                  % (i, m.sa, m.sb, mvp.card["nickname"],
                     mvp.card["firepower"], mvp.eff, "" if mine else " (对手)"))
            print(show_map(m))

def tune(runs=6000):
    """§13.3 指定的 MAP_SCALE 扫描，对着 §13.3 自己写的四条验收目标。

    Stability 分布已被 §6.3 冻结，所以这是现在**唯一**该动的宏观旋钮。
    表下半部分保留当年那张「三选二」，它是 §13 存在的理由，别删。
    """
    print("=" * 78)
    print("§13.3  MAP_SCALE 扫描 — 唯一该调的宏观旋钮")
    print("=" * 78)
    print("目标： +2 只是小优 / +5 明显优势但远非必胜")
    print("       +10 强 Favorite 但 BO1 仍可爆冷 / +20 极难翻但不机械 100%")
    print()
    print("  %-7s %8s %8s %8s %8s | %11s %10s"
          % ("SCALE", "+2", "+5", "+10", "+20", "+10爆冷", "BO3(+5)"))
    for scale in (4, 5, 6, 7, 9):
        row = []
        for gap in (2, 5, 10, 20):
            a, b = _probe("A", 70 + gap, 70), _probe("B", 70, 70)
            row.append(100 * win_rate(a, b, 1, 0.0, runs, 41, scale))
        a, b = _probe("A", 80, 70), _probe("B", 70, 70)
        upset = 100 * (1 - win_rate(a, b, 1, 0.0, runs, 41, scale))
        c, d = _probe("C", 75, 70), _probe("D", 70, 70)
        bo3 = 100 * win_rate(c, d, 3, 0.0, runs, 43, scale)
        star = " <- 当前" if scale == MAP_SCALE else ""
        print("  %-7d %7.1f%% %7.1f%% %7.1f%% %7.1f%% | %10.1f%% %9.1f%%%s"
              % (scale, *row, upset, bo3, star))

    print("\n  设计稿 §13.3 说 Map Residual 与经典 logistic「统计意义上等价」——")
    print("  近似而已。SA/SB 本身含 Player 波动，残差叠上去会把曲线再抹平一层：")
    print("  %-7s %10s %10s" % ("SCALE", "实测 +5", "纯 logistic"))
    for scale in (4, 6):
        c, d = _probe("C", 75, 70), _probe("D", 70, 70)
        got = 100 * win_rate(c, d, 1, 0.0, runs, 43, scale)
        pure = 100 / (1 + pow(2.718281828, -5.0 / scale))
        print("  %-7d %9.1f%% %9.1f%%" % (scale, got, pure))
    print("  所以同样的手感，MAP_SCALE 可以取得比按纯 logistic 反推的更小。")

    print("\n" + "-" * 78)
    print("§13.5 三选二（历史证据，说明 Map Residual 为什么必须存在）")
    print("-" * 78)
    global SIGMA_SCALE, TEAM_RHO
    keep = (SIGMA_SCALE, TEAM_RHO)
    A, B = _probe("A", 80, 70), _probe("B", 70, 70)

    def upset_no_residual():
        return 1 - win_rate(A, B, 1, 0.0, runs, 11, 0.0)   # scale=0 → 无残差

    print("  若删掉 Map Residual，只让 Player Roll 决定胜负：")
    print("  %-24s %10s %s" % ("", "+10 爆冷", "代价"))
    TEAM_RHO = 0.0
    for k in (1.0, 2.0, 4.0):
        SIGMA_SCALE = k
        lo = 80 + form_delta(0.05, 50)
        hi = 80 + form_delta(0.95, 50)
        print("  放大个人波动 x%-9.1f %9.1f%%  F80/S50 单图 %.0f~%.0f"
              % (k, 100 * upset_no_residual(), lo, hi))
    SIGMA_SCALE = 1.0
    for rho in (0.5, 0.8):
        TEAM_RHO = rho
        print("  队内相关性 rho=%-8.2f %9.1f%%  整队一起爆/一起崩"
              % (rho, 100 * upset_no_residual()))
    SIGMA_SCALE, TEAM_RHO = keep
    print("\n  两条路都不通：放大波动毁掉 Player Story，相关性只对齐不放大。")
    print("  所以队伍级的未建模随机必须单独有个出口，这就是 Map Residual。")

# ------------------------------------------------------------------ 玩家的一届

def player_run(nicknames=None, pages=None, seed=1, cfg=None):
    """从选人到淘汰的一整届：VRS 赛场 -> 插队 -> 三段 Swiss -> 玩家路径。

    返回一个 dict，字段和 `bdserver.run.build_run` 对齐，网页要接的时候不用
    再翻译一次。这里只组装，比赛规则全在上面。
    """
    cards = {c["nickname"]: c for c in P.load_cards()}
    if pages:
        by_page = {c["page"]: c for c in P.load_cards()}
        roster = [by_page[str(x)] for x in pages]
    else:
        roster = [cards[n] for n in nicknames]
    me = Team("YOUR TEAM", roster, 0.0, is_player=True)

    field, asof = major_field(seed, cfg)
    stage, shove, full = insert_player(field, me)
    base = {
        "seed": int(seed), "snapshot": asof,
        "entry": round(me.entry(), 1),
        "roster": [{k: c.get(k) for k in
                    ("page", "nickname", "position", "grade", "country",
                     "team", "age", "firepower", "leadership", "experience",
                     "stability")} for c in roster],
        "stage": stage,
        "qualified": stage > 0,
        # v2 没有「全场种子」——Stage 归属由 VRS 名额定，这里给的是玩家 Entry
        # 在 32 支正赛队里的位次，只作参考。
        "entry_rank": sum(1 for t in field if t.entry() > me.entry()) + 1,
        "demoted": [{"team": t.name, "from_stage": a, "to_stage": b}
                    for t, a, b in shove.demoted],
        "dropped": shove.dropped.name if shove.dropped else None,
    }
    if not stage:
        return base | {"outcome": "not_qualified", "wins": 0, "losses": 0,
                       "reached_playoffs": False, "stages": [], "legs": []}

    stages, logs = run_major(full, random.Random(seed))
    legs, stage_rows, alive = [], [], me
    for s in (stage, stage + 1, 3):
        if s > 3:
            break
        teams, adv = stages[s]
        here = next((t for t in teams if t.is_player), None)
        if here is None:
            break
        for rnd, results in logs[s]:
            for r in results:
                if r.a is here or r.b is here:
                    legs.append(_leg_row(r, here, s, rnd))
        advanced = any(t.is_player for t in adv)
        stage_rows.append({"stage": s, "wins": here.w, "losses": here.l,
                           "advanced": advanced})
        if not advanced:
            break
        alive = here
    reached = any(t.is_player for t in stages[3][1])
    wins = sum(1 for x in legs if x["won"])
    return base | {"wins": wins, "losses": len(legs) - wins,
                   "outcome": "playoffs" if reached else "eliminated",
                   "reached_playoffs": reached,
                   "stages": stage_rows, "legs": legs}


def _leg_row(r, me, stage, rnd):
    """一场比赛 -> JSON。玩家永远摆在 a 位，免得面板从对手视角写。"""
    mine_is_a = r.a is me
    opp = r.b if mine_is_a else r.a
    scene = ("2-2 高压生死局" if r.pressure >= PRESSURE["decider"]
             else "晋级 BO3" if r.bo == 3 and r.pressure == PRESSURE["advance"]
             else "淘汰 BO3" if r.bo == 3 else "BO1")
    maps = []
    for i, m in enumerate(r.maps, 1):
        sa, sb = (m.sa, m.sb) if mine_is_a else (m.sb, m.sa)
        da, db = (m.da, m.db) if mine_is_a else (m.db, m.da)
        won = m.winner_a if mine_is_a else not m.winner_a
        mvp, mvp_a = m.mvp
        life, life_a = m.life
        under, under_a = m.under
        side = lambda flag: ("player" if flag == mine_is_a else "opponent")
        me_t, opp_t = (m.a, m.b) if mine_is_a else (m.b, m.a)
        maps.append({
            "number": i,
            "player_strength": round(sa, 1), "opponent_strength": round(sb, 1),
            "player_won": bool(won),
            "residual": round(m.residual if mine_is_a else -m.residual, 1),
            "margin": round(m.margin if mine_is_a else -m.margin, 1),
            # 队伍层的三笔账，网页要摊开给玩家看
            "player_fire": round(sum(t.weight * t.eff for t in da), 1),
            "opponent_fire": round(sum(t.weight * t.eff for t in db), 1),
            "player_tactical": round(me_t.tactical, 2),
            "opponent_tactical": round(opp_t.tactical, 2),
            "player_structure": round(me_t.structure, 1),
            "opponent_structure": round(opp_t.structure, 1),
            # 压力在 v2 是逐人的：这里汇总本图因压力多丢了多少火力
            "player_choke": round(sum(t.choke for t in da), 1),
            "opponent_choke": round(sum(t.choke for t in db), 1),
            "mvp": _roll_json(mvp, side(mvp_a)),
            "life_game": (_roll_json(life, side(life_a))
                          if life.delta >= LIFE_GAME_AT else None),
            "underperform": (_roll_json(under, side(under_a))
                             if under.delta <= UNDERPERFORM_AT else None),
            "players": [_roll_json(t, "player")
                        for t in sorted(da, key=lambda t: -t.weight)],
            "opponents": [_roll_json(t, "opponent")
                          for t in sorted(db, key=lambda t: -t.weight)],
        })
    return {
        "label": "Stage %d · Round %d · %s" % (stage, rnd, scene),
        "stage": stage, "round": rnd, "bo": r.bo, "pressure": r.pressure,
        "opponent": {"name": opp.name, "entry": round(opp.entry(), 1),
                     "vrs": opp.vrs, "stage": opp.stage},
        "won": r.winner is me,
        "player_maps": r.a_maps if mine_is_a else r.b_maps,
        "opponent_maps": r.b_maps if mine_is_a else r.a_maps,
        "maps": maps,
    }


def _roll_json(t, side):
    return {"nickname": t.card["nickname"], "position": t.card["position"],
            "side": side,
            "base_firepower": t.card["firepower"],
            "effective_firepower": round(t.eff, 1),
            "delta": round(t.delta, 1),
            "carry_weight": round(t.weight, 4),
            "why": {"form": round(t.form, 1), "pressure": round(t.choke, 1),
                    "soft_capped": round(t.capped, 1)}}


def show_run(data):
    """命令行版的一届。"""
    print("=" * 74)
    print("Match Engine v2 — Road to Major   快照 %s" % (data["snapshot"] or "?"))
    print("=" * 74)
    print("你的五个人（Entry %.1f，纯火力口径）:" % data["entry"])
    for c in data["roster"]:
        print("   %-7s %-14s %-16s 火力 %2d 稳定 %2d 经验 %2d 领导 %2d"
              % (c["position"], c["nickname"], c["country"] or "",
                 c["firepower"], c["stability"], c["experience"],
                 c["leadership"]))
    if not data["qualified"]:
        print("\n未取得席位：你比 Stage 1 最弱的一支还弱。")
        return
    print("\n按 Entry 挤进 Stage %d。" % data["stage"])
    for d in data["demoted"]:
        print("   %s 从 Stage %d 掉到 Stage %d" %
              (d["team"], d["from_stage"], d["to_stage"]))
    if data["dropped"]:
        print("   %s 失去席位。" % data["dropped"])
    for leg in data["legs"]:
        print()
        print("%s" % leg["label"])
        print("  对手 %-18s Entry %.1f · VRS %s · 本届 Stage %s"
              % (leg["opponent"]["name"], leg["opponent"]["entry"],
                 leg["opponent"]["vrs"] or "-", leg["opponent"]["stage"]))
        print("  %s  %d:%d   压力 %.1f"
              % ("WIN" if leg["won"] else "LOSS", leg["player_maps"],
                 leg["opponent_maps"], leg["pressure"]))
        for m in leg["maps"]:
            tags = []
            if m["life_game"]:
                g = m["life_game"]
                tags.append("LIFE GAME %s %d→%.0f%s"
                            % (g["nickname"], g["base_firepower"],
                               g["effective_firepower"],
                               "" if g["side"] == "player" else "(对手)"))
            if m["underperform"]:
                u = m["underperform"]
                tags.append("UNDERPERFORM %s %d→%.0f%s"
                            % (u["nickname"], u["base_firepower"],
                               u["effective_firepower"],
                               "" if u["side"] == "player" else "(对手)"))
            v = m["mvp"]
            print("    Map %d  表现 %.1f : %.1f  Residual %+.1f  ->  %s"
                  " · MVP %s %d→%.0f%s%s"
                  % (m["number"], m["player_strength"], m["opponent_strength"],
                     m["residual"], "你赢" if m["player_won"] else "对手赢",
                     v["nickname"], v["base_firepower"],
                     v["effective_firepower"],
                     "" if v["side"] == "player" else "(对手)",
                     ("  " + " · ".join(tags)) if tags else ""))
    print()
    for s in data["stages"]:
        print("Stage %d  %d-%d  %s"
              % (s["stage"], s["wins"], s["losses"],
                 "晋级" if s["advanced"] else "淘汰"))
    print("RUN RESULT  %d-%d · %s"
          % (data["wins"], data["losses"],
             "进入 Playoffs" if data["reached_playoffs"] else "被淘汰"))


def show_field(seed=1):
    """这一届 32 支队是怎么来的：VRS 名额定 Stage，Entry 定层内种子。"""
    field, asof = major_field(seed)
    print("Road to Major 赛场 · 快照 %s" % (asof or "?"))
    print("  Stage 归属由区域 VRS 名额决定；Entry 只排 Stage 内的种子。")
    for stage in (3, 2, 1):
        tier = sorted((t for t in field if t.stage == stage),
                      key=lambda t: -t.entry())
        print("\nStage %d 直邀 %d 支" % (stage, len(tier)))
        for i, t in enumerate(tier, 1):
            print("  种子 %-3d %-18s Entry %6.1f  VRS %-4s HLTV %s"
                  % (i, t.name, t.entry(), t.vrs or "-", t.hltv or "-"))
def _spearman(xs, ys):
    n = len(xs)
    rx = {v: i for i, v in enumerate(sorted(xs))}
    ry = {v: i for i, v in enumerate(sorted(ys))}
    d2 = sum((rx[a] - ry[b]) ** 2 for a, b in zip(xs, ys))
    return 1 - 6 * d2 / (n * (n * n - 1))


def _evidence(team):
    """五个人的当前火力各自站在什么证据上。"""
    tally = collections.Counter()
    for c in team.roster:
        src = (c.get("_sources") or {}).get("firepower") or {}
        conf = src.get("confidence")
        if c.get("_nocard"):
            tally["卡库外"] += 1
        elif conf == "strong":                 # >=80 图，直接读当前火力标尺
            tally["强"] += 1
        elif conf == "supporting":             # 30~79 图，向生涯先验收缩
            tally["中"] += 1
        elif (src.get("source") or "") == "igl_career_prior":
            tally["IGL"] += 1                  # 指挥本来就不走当前 rating
        else:
            tally["弱/回退"] += 1
    return tally


def audit(threshold=10):
    """§13 之外的另一件事：VRS 排名和我们的 Entry 差得远的队，逐支列出来。

    这不是要把两条曲线拟到一起——VRS 回答「现实里已经挣到什么位置」，Entry
    回答「今天这五个人有多能打」，两者本来就允许背离：刚换阵容、近期状态暴跌、
    积分还没掉下来，都会让一支队 VRS 高而 Entry 低。FUT 这种「靠履历直进
    Stage 3，进来被狠狠干」反而有现实味。

    这张表只回答一个问题：**这个偏差是现实原因，还是数据/模型原因？**

      现实原因（保留）：刚换人、近期爆发、排名滞后
      数据原因（要修 Entry）：漏人、角色识别错、当前统计没覆盖、fallback 太低

    所以每行都带上火力证据的构成。一支队如果五个人里三四个都踩在
    `career_age_fallback` 上，那它的 Entry 低多半是我们没数据，不是它真的弱。
    """
    field, asof = major_field()
    ranked = sorted(field, key=lambda t: -t.entry())
    erank = {t.name: i for i, t in enumerate(ranked, 1)}
    have_vrs = [t for t in field if t.vrs]
    vrank = {t.name: i for i, t in
             enumerate(sorted(have_vrs, key=lambda t: t.vrs), 1)}

    print("=" * 78)
    print("VRS × Entry 偏差审计   快照 %s" % (asof or "?"))
    print("=" * 78)
    rho = _spearman([t.vrs for t in have_vrs],
                    [-t.entry() for t in have_vrs])
    print("秩相关 ρ = %.3f（v1 的 Entry 口径是 0.631；拿掉 L/E/S 静态权重后升上来的）"
          % rho)
    print("两把尺子本来就允许背离，这里只挑 |Δ| >= %d 的人工过一遍。" % threshold)
    print()
    print("  %-18s %5s %6s %6s %8s  %s"
          % ("队", "VRS位", "Entry位", "Δ", "Entry", "五人火力证据"))
    rows = []
    for t in have_vrs:
        d = vrank[t.name] - erank[t.name]
        if abs(d) >= threshold:
            rows.append((abs(d), d, t))
    for _, d, t in sorted(rows, reverse=True, key=lambda r: r[0]):
        ev = _evidence(t)
        desc = " ".join("%s%d" % (k, v) for k, v in
                        sorted(ev.items(), key=lambda kv: -kv[1]))
        flag = ""
        if ev["弱/回退"] + ev["卡库外"] >= 3:
            flag = "  <- 多数人没有当前证据，先查数据再谈实力"
        print("  %-18s %5d %6d %+6d %8.1f  %s%s"
              % (t.name, vrank[t.name], erank[t.name], d, t.entry(), desc, flag))
    if not rows:
        print("  （没有超过阈值的）")
    print()
    print("Δ 为正 = VRS 比我们的 Entry 更看好它；为负 = 我们比 VRS 更看好它。")
    print("不要为了让两列对齐去改单个选手的四维——那会把系统做串（§『当前明确不做』）。")

def main():
    ap = argparse.ArgumentParser(description="Match Engine v2 原型")
    ap.add_argument("--lab", action="store_true", help="1.txt 结尾的六项验收")
    ap.add_argument("--compare", action="store_true", help="§9 删胜负骰的代价")
    ap.add_argument("--tune", action="store_true",
                    help="扫 SIGMA_SCALE / TEAM_RHO，看爆冷能不能撑住")
    ap.add_argument("--demo", default=None, metavar="阵容",
                    help="打一场看逐人账本；FIXTURES 的名字或 \"nick,nick,...\"")
    ap.add_argument("--major", default=None, metavar="阵容",
                    help="跑完整一届 Road to Major；同上，也认 page")
    ap.add_argument("--field", action="store_true",
                    help="只看这一届 32 支队的 VRS 名额与层内种子")
    ap.add_argument("--audit", action="store_true",
                    help="列出 VRS 排名和 Entry 差得远的队，人工分辨原因")
    ap.add_argument("--stats", action="store_true",
                    help="整届分布：进 Playoffs 的概率、按实力差的强队胜率")
    ap.add_argument("--duel", nargs=2, type=float, metavar=("HIGH", "LOW"),
                    help="两个 Entry 之间的胜率锚（实测，不是算出来的）")
    ap.add_argument("--duel-runs", type=int, default=20000)
    ap.add_argument("--label", default=None, help="--demo / --major 的队名")
    ap.add_argument("--runs", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=5)
    args = ap.parse_args()
    if args.audit:
        audit()
    elif args.duel:
        duel(args.duel[0], args.duel[1], args.duel_runs)
    elif args.stats:
        stats(args.runs if args.runs != 4000 else 200)
    elif args.field:
        show_field(args.seed)
    elif args.major:
        show_run(player_run(pages=[c["page"] for c in roster_cards(args.major)],
                            seed=args.seed))
    elif args.tune:
        tune(args.runs)
    elif args.compare:
        compare(args.runs)
    elif args.demo:
        demo(args.demo, args.seed, args.label)
    else:
        lab(args.runs)




# ================================================================== 赛事外壳
#
# §1~§2 的 Road to Major。这一层是**赛制**不是数值，所以它和 v1 讲的是同一套
# 规则；但故意在 v2 里独立实现，不 import match.py——v1 退役时不用拆依赖。
#
# 和 v1 的一处**行为差异**，写在这里免得以后有人当成 bug：
#
#   v1 的 run_major 按 Entry 排名切 field[0:8] / [8:16] / [16:32] 决定谁在哪个
#   Stage，`regional_stage` 算出来了却没人用。实测 32 支里有 13 支对不上——
#   FUT 的 VRS 排名是全球第 4、按区域名额本该 Stage 3 直邀，却因为我们的 Entry
#   只有 59.8（第 22）被扔进 Stage 1；FlyQuest VRS 第 51，反而进了 Stage 2。
#
#   v0.3 §1.2 把区域名额表写死了（EU 8/6/6、AM 5/1/2、AS 3/1/0），所以 v2 里
#   **Stage 归属听 VRS，Stage 内的种子顺序才按 Entry 排**。两把尺子各管各的：
#   VRS 回答「凭什么拿到这个席位」，Entry 回答「同一层里谁更强」。

STAGE_WINS = 3
STAGE_LOSSES = 3
FIELD_SIZE = 32


def format_of(record):
    """§2 的赛制 + §8.1 的压力分级。

    v1 只有三档（BO1 0 / BO3 1.0 / 生死局 1.25）。v0.3 §8.1 要求 Format 和
    Pressure 分开，晋级局和淘汰局的心理压力不一样——赢一场就出线，和输一场就
    回家，不该给同一个数。
    """
    w, l = record
    if w == 2 and l == 2:
        return 3, PRESSURE["decider"]
    if w == 2:
        return 3, PRESSURE["advance"]       # 赢了就晋级
    if l == 2:
        return 3, PRESSURE["elim"]          # 输了就淘汰
    return 1, PRESSURE["swiss"]


def _by_record(alive):
    """按 (胜, 负) 分池，战绩好的池子先配。"""
    pools = {}
    for t in alive:
        pools.setdefault(t.record, []).append(t)
    return sorted(pools.items(), key=lambda kv: (-kv[0][0], kv[0][1]))


def mid_stage_order(teams):
    """§2.3：当前 W-L -> Difficulty -> Stage 初始种子。"""
    return sorted(teams, key=lambda t: (-t.w, t.l, -t.difficulty, t.seed))


def pair_group(group, avoid_rematch=True):
    """组内高种子打低种子，尽量避开重复对手（§2 「尽量避免同 Stage 重赛」）。"""
    def rec(pool):
        if not pool:
            return []
        a, rest = pool[0], pool[1:]
        for i in range(len(rest) - 1, -1, -1):
            b = rest[i]
            if avoid_rematch and b in a.opponents:
                continue
            sub = rec(rest[:i] + rest[i + 1:])
            if sub is not None:
                return [(a, b)] + sub
        return None

    got = rec(list(group))
    return pair_group(group, False) if got is None else got


def run_stage(teams, rng):
    """一个 16 队 Swiss Stage：3 胜晋级、3 负淘汰。

    返回 (晋级的 8 支（按本 Stage 最终表现排）, [(轮次, 该轮全部比赛), ...])。
    每轮全场都要打，因为下一轮配对取决于所有队的战绩和 Difficulty。
    """
    for t in teams:
        t.reset()
    rounds = []
    for rnd in range(1, 6):
        alive = [t for t in teams if not t.done]
        if not alive:
            break
        if rnd == 1:                       # §2.1  1v9 2v10 ... 8v16
            order = sorted(teams, key=lambda t: t.seed)
            pairs = [(order[i], order[i + 8]) for i in range(8)]
        else:
            pairs = []
            for _, grp in _by_record(alive):
                pairs.extend(pair_group(mid_stage_order(grp)))
        results = []
        for a, b in pairs:
            bo, pressure = format_of(a.record)
            r = play_match(a, b, rng, bo, pressure)
            r.winner.w += 1
            r.loser.l += 1
            a.opponents.append(b)
            b.opponents.append(a)
            results.append(r)
        rounds.append((rnd, results))
    adv = [t for t in teams if t.w >= STAGE_WINS]
    adv.sort(key=lambda t: (t.l, -t.difficulty, t.seed))
    return adv, rounds


def run_major(field, rng):
    """§2：Stage 1 -> 2 -> 3。Playoffs（§2.4）暂不打。

    哪怕玩家直接从 Stage 3 进场，下面两个 Stage 也得先跑——Stage 2/3 的种子
    9-16 必须由上一个 Stage 决出，这不是多做的功能，是正确性。
    """
    logs, stages = {}, {}
    carry = []
    for stage in (1, 2, 3):
        direct = sorted((t for t in field if t.stage == stage),
                        key=lambda t: -t.entry())
        for i, t in enumerate(direct, 1):
            t.seed = i                     # Stage 内种子按 Entry，§2.2
        for i, t in enumerate(carry, 9):
            t.seed = i                     # 上一层晋级者按上一层 Final Seed
        teams = direct + carry
        adv, logs[stage] = run_stage(teams, rng)
        stages[stage] = (teams, adv)
        carry = [t.fork() for t in adv]
    return stages, logs


# ------------------------------------------------------------------ 赛场与插队

class Shove(object):
    """玩家挤进来之后，谁被挤到了哪儿。"""

    def __init__(self, dropped=None, demoted=()):
        self.dropped = dropped
        self.demoted = list(demoted)       # [(队, 原 Stage, 现 Stage)]


def major_field(seed=1, cfg=None, cohesion_cap=None):
    """VRS 席位 + 快照首发 + v2 口径的 Entry。

    席位和 Stage 归属整个来自 `ai_teams.build_pool_field`（区域 VRS 名额），
    这一层**不依赖 Entry 口径**，所以 v1 / v2 拿到的是同一批队、同样的分层。
    换掉的只是每支队的 Entry 怎么算——v2 是纯火力（§4.1）。
    """
    from . import ai_teams as A
    cfg = cfg if cfg is not None else M.load_config()
    cap = (float(cfg.get("cohesion_cap", M.COHESION_CAP))
           if cohesion_cap is None else float(cohesion_cap))
    rosters = M.load_rosters_cached()
    teams, asof = A.build_pool_field(cfg)
    out = []
    for t in teams:
        if not t.get("stage"):
            continue
        rating = A.entry_of(t, rosters, cap)
        team = Team(t["name"], t["roster"], min(rating["chem_raw"], cap))
        team.stage = t["stage"]
        team.vrs = t.get("vrs")
        team.hltv = t.get("rank")
        if t.get("adjust"):
            team.structure += float(t["adjust"])
        out.append(team)
    if len(out) != FIELD_SIZE:
        raise ValueError("regional_slots 应产生 %d 席，实际 %d"
                         % (FIELD_SIZE, len(out)))
    return out, asof


def insert_player(field, player):
    """玩家按 Entry 在**全场**排名定 Stage，再按名额守恒级联降级。

    两把尺子在这里分工，不能混用：

      AI 的 Stage  由区域 VRS 名额定（§1.2）——「你凭历史积分拿到这个席位」
      玩家的 Stage 由 Entry 全场排名定——玩家是临时组的队，没有 VRS 积分，
                   能衡量他的只有纸面实力

    一开始试过「逐层挤」（Entry 高过某层最弱的就进那层），实测不成立：两把
    尺子的秩相关只有 0.63，层间 Entry 重叠得很厉害——本届 Stage 2 最弱的 BIG
    只有 61.5，而 Stage 1 最强的 Astralis 有 81.4。那样一支 62 分的队能挤进
    Stage 2，却比 Stage 1 半数队都弱。

    定下 Stage 之后仍然名额守恒、逐级级联：该层最弱的掉一级，下一层因此多
    一支、最弱的再掉一级，Stage 1 多出来的那支失去席位。「你的加入让下面
    几支各降一级」这个叙事保住了。
    """
    rank = sum(1 for t in field if t.entry() > player.entry()) + 1
    if rank > FIELD_SIZE:
        return 0, Shove(), list(field)
    stage = 3 if rank <= 8 else 2 if rank <= 16 else 1
    player.stage = stage

    tiers = {s: sorted((t for t in field if t.stage == s),
                       key=lambda t: -t.entry()) for s in (3, 2, 1)}
    tiers[stage] = tiers[stage][:-1] + [player]
    shove = Shove()
    falling = sorted((t for t in field if t.stage == stage),
                     key=lambda t: -t.entry())[-1]
    for lower in range(stage - 1, 0, -1):
        shove.demoted.append((falling, falling.stage, lower))
        falling.stage = lower
        tiers[lower] = sorted(tiers[lower] + [falling],
                              key=lambda t: -t.entry())
        falling = tiers[lower][-1]
        tiers[lower] = tiers[lower][:-1]
    shove.dropped = falling
    return stage, shove, [t for s in (3, 2, 1) for t in tiers[s]]


if __name__ == "__main__":
    main()
