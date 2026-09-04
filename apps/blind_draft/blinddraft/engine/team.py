# -*- coding: utf-8 -*-
"""一支队：静态的 Entry，以及把五个 Roll 聚合成一张图的队伍强度（§4 / §5 / §9）。

Team 同时是赛事外壳的节点（战绩、种子、Buchholz），所以 `tournament.py` 用的
那几个字段也在这儿；它们不参与任何数值计算，纯粹是赛制记账。
"""
from . import params as PA
from .params import soft_cap, tactical
from .roll import NORM, Roll, form_delta, under_pressure


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
        for i, w in zip(order, PA.STAR_WEIGHTS):
            self.weights[i] = w
        for i in rest:
            self.weights[i] = PA.REST_WEIGHT / len(rest)

        self.no_awp = not any(c["position"] == "AWPER" for c in roster)
        self.structure = (PA.NO_AWP_PENALTY if self.no_awp else 0.0) + chem
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
        z_team = rng.gauss(0.0, 1.0) if PA.TEAM_RHO > 0.0 else 0.0
        rho = min(0.999, max(0.0, PA.TEAM_RHO))
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


def entry_of(roster, chem=0.0, adjust=0.0):
    """**Entry 的唯一定义**：纯火力 + 默契 + 结构修正（§4.1）。

    项目里只有这一个东西叫 Entry。曾经并存的 `major.entry_rating` 是 v1 口径
    （火力 40% + L/E/S 各 20%，量纲 ≈65），它对同一批 32 支队给出的名次和这个
    差最多 15 位——FUT 在那把尺子上是全场第 22，在这把上是第 7。页面显示一套、
    比赛读另一套，人一定会被绕晕，所以那个复合值已经删掉。

    赛场那一侧（`/ai`、`ai_teams`、`major` 的赛场列表）通过这个函数取值，
    不再自己算一份。
    """
    t = Team("", roster, chem)
    t.structure += adjust
    return t.entry()
