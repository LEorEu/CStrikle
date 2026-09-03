# -*- coding: utf-8 -*-
"""Match Engine v2 原型 —— 四维各干一件事，一张图 11 个随机数。

落地的是设计稿 `比赛引擎_v0.3.md`。它要求
这一版做成独立原型而不是就地改 v1，所以这个文件**不碰** `match.py`，也不被它
import；只有 `--compare` 会临时借 v1 的 `win_prob` 画对照。§15 的 Pipeline：

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
        self.reset()

    def reset(self):
        self.w = self.l = 0
        self.opponents = []

    @property
    def record(self):
        return (self.w, self.l)

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

def field_teams(seed=1):
    """借 major 的赛场构成，但 Entry 一律用 v2 口径重算。"""
    cfg = M.load_config()
    cap = float(cfg.get("cohesion_cap", M.COHESION_CAP))
    rosters = P.load_rosters()
    return [Team(e.name, e.roster, min(e.rating["chem_raw"], cap))
            for e in M.make_field(random.Random(seed), cfg, rosters, cap)]


def named_team(label, nicknames, cards=None):
    cards = cards or {c["nickname"]: c for c in P.load_cards()}
    return Team(label, [cards[n] for n in nicknames], 0.0, is_player=True)


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


# ------------------------------------------------------------------ lab

def lab(runs=4000):
    """1.txt 结尾列的六项验收，一次跑完。"""
    cards = {c["nickname"]: c for c in P.load_cards()}
    field = {t.name: t for t in field_teams(1)}
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
    from . import match as V1                # 只在对比时用，引擎本身不依赖 v1
    print("=" * 74)
    print("§9 代价核对 — 同样的实力差，两版给出的胜率")
    print("=" * 74)
    print("  %-8s %12s %12s %12s" % ("差距", "v1 logistic", "v2 BO1", "v2 BO3"))
    for gap in (2, 5, 10, 20):
        a, b = _probe("A", 70 + gap, 65), _probe("B", 70, 65)
        print("  %-8s %11.1f%% %11.1f%% %11.1f%%"
              % ("+%d" % gap, 100 * V1.win_prob(gap, 0),
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


def demo(name="donk carry", seed=5):
    cards = {c["nickname"]: c for c in P.load_cards()}
    me = named_team(name, FIXTURES[name], cards)
    opp = min(field_teams(1), key=lambda t: abs(t.entry() - me.entry()))
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


def main():
    ap = argparse.ArgumentParser(description="Match Engine v2 原型")
    ap.add_argument("--lab", action="store_true", help="1.txt 结尾的六项验收")
    ap.add_argument("--compare", action="store_true", help="§9 删胜负骰的代价")
    ap.add_argument("--tune", action="store_true",
                    help="扫 SIGMA_SCALE / TEAM_RHO，看爆冷能不能撑住")
    ap.add_argument("--demo", default=None, metavar="阵容",
                    help="打一场看逐人账本，名字见 FIXTURES")
    ap.add_argument("--runs", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=5)
    args = ap.parse_args()
    if args.tune:
        tune(args.runs)
    elif args.compare:
        compare(args.runs)
    elif args.demo:
        demo(args.demo, args.seed)
    else:
        lab(args.runs)


if __name__ == "__main__":
    main()
