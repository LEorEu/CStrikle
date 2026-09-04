# -*- coding: utf-8 -*-
"""Road to Major 的赛制外壳（§1~§2）：赛场怎么来、三段 Swiss 怎么打、玩家怎么插进来。

**这一层是赛制，不是数值。** 它只在两个地方问引擎要数：配对种子按 Entry 排，
一场比赛的胜负交给 `play.play_match`。改赛制不该动到任何系数，反过来也一样。
"""
from .. import major as M
from . import params as PA
from .play import play_match
from .team import Team
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
        return 3, PA.PRESSURE["decider"]
    if w == 2:
        return 3, PA.PRESSURE["advance"]       # 赢了就晋级
    if l == 2:
        return 3, PA.PRESSURE["elim"]          # 输了就淘汰
    return 1, PA.PRESSURE["swiss"]


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
    from .. import ai_teams as A
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
