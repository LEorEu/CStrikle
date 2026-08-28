# -*- coding: utf-8 -*-
"""Blind Draft — Swiss Stage 比赛引擎原型(Match Engine v0.1)

设计稿:docs/blind-draft/比赛引擎_v0.1.md,这里落地的是 §14~§21、§24~§28、
§30~§32,以及 §34 那个第一里程碑。

核心口径(都不是我新发明的,是照着设计稿抄的):

  §15  不再造第二套 Overall。Match Strength 就是现有的 Base Team Score,
       只把每个人的 firepower 换成「今天这一张地图的实际发挥」。
       所以「不 Roll 的比赛强度」== Entry Rating,这条在 selftest 里断言。
  §16  Stability 只决定 Roll 的**宽度**,不再额外加一遍战力。
  §19  Experience 只在高压局缓冲**负** Roll,不是每场 +9。
  §20  Leadership 小幅缓冲全队负 Roll,任何压力下都生效。
  §25  BO3 按地图逐张打,不写「强队 BO3 +5」——多 Roll 几次自然回归均值。
  §27  Logistic 胜率,WIN_SCALE 是 P0 平衡参数。

暂时**没有**的(设计稿也说 v0.1 不做):Rogue Buff、Trait Buff、地图池、
Pick/Ban、比分、Playoffs。剩余预算也没有进 Match Rating——它是 Rogue Point
的替身,等 §23 做出来再接。
"""
import argparse
import collections
import os
import random
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proto_draft as P
import proto_major as M


# ------------------------------------------------------------------ 参数

WIN_SCALE = 13.0        # §27.1 P0:CS 到底有多容易爆冷。建议区间 12~15
EXP_BUFFER = 0.45       # §19.2 经验 100 + 压力 1 时,负 Roll 最多削掉 45%
LEAD_BUFFER = 0.15      # §20   领导力 100 时,负 Roll 削掉 15%
BUFFER_CAP = 0.60       # 缓冲总量的上限,别让高压局变成不会失常
SOFT_CAP_AT = 99.0      # §18
SOFT_CAP_RATE = 0.35

# 一支队今天整体的状态,和五个人各自的状态,占各自波动的多少。
# 五个人**独立**掷骰的话,队伍层面会被 sqrt(5) 抹平:个人 sigma=11 的神经刀
# 到队伍强度上只剩 1.2 分,而 WIN_SCALE 是 13——那样比赛结果几乎全部来自
# logistic 那一次抛硬币,四维就都不做功了(§14 开篇要避免的正是这个)。
# 这里做的是**方差分解**不是放大:每个人的边际分布和 §17 的例子一模一样,
# 只是把其中一部分变成全队共享的那一击。
TEAM_FORM_SHARE = 0.65

# §19「压力来了还能兑现多少」。只在高压局生效,常规 BO1(压力 0)完全不存在,
# 所以它不是「老哥每场固定 +分」。
#
# 为什么光靠缓冲负 Roll 不够:那条只是把均值抬高 0.34 分,而整届 Major 的实力
# 跨度是 36 分,在这个刻度上等于零(实测经验 92 打经验 30 只有 +0.8%)。缓冲那条
# 留着是因为它给的是叙事(某个老哥在生死局没崩),真正做功的是这条队伍级的。
CHOKE = 6.0             # 压力 1 时,经验 0 的队最多丢 6 分
CHOKE_LEAD_RELIEF = 0.4     # §20:好指挥让全队更容易兑现,最多免掉 40%

# §19.1 压力等级。Playoff / Final 先留着,v0.1 不打淘汰赛。
PRESSURE_BO1 = 0.0
PRESSURE_BO3 = 1.0
PRESSURE_DECIDER = 1.25     # 2-2 生死局

STAGE_WINS = 3
STAGE_LOSSES = 3


# ------------------------------------------------------------------ 一支队的静态部分

def soft_cap(x):
    """§18:卡面最高 99,比赛里可以超过,但超出部分打折。"""
    if x <= SOFT_CAP_AT:
        return x
    return SOFT_CAP_AT + (x - SOFT_CAP_AT) * SOFT_CAP_RATE


class MatchTeam(object):
    """把一支队里「每场都一样」的部分算一次存起来,只有火力逐图重算。

    拆开算而不是每张图调一次 P.score(),是因为默契要遍历 10 对队友,而它
    在一个 Stage 里永远不变。拆法必须和 P.score 逐项对齐,selftest 会查。
    """

    def __init__(self, entry, seed, chem_cap=M.CHEM_CAP):
        self.entry = entry
        self.name = entry.name
        self.roster = entry.roster
        self.seed = seed                      # Stage 内初始种子 1..16
        self.is_player = entry.is_player

        roster = self.roster
        igls = [c for c in roster if c["position"] == "IGL"]
        if igls:
            top = max(igls, key=lambda c: c["leadership"])
            others = [c["leadership"] if c["position"] != "IGL" else 25
                      for c in roster if c is not top]
            self.lead = top["leadership"] * .70 + st.mean(others) * .30
            # §20:多个 IGL 不叠加,只认最强的那个;ROLE CONFLICT 的罚分
            # 已经在 chemistry() 里扣过了,这里不再扣第二次。
            self.team_lead = top["leadership"]
        else:
            avg = st.mean(c["leadership"] for c in roster)
            self.lead = avg * .60
            self.team_lead = avg * .60        # §20:无 IGL,团队领导力明显降低

        self.exp = st.mean(c["experience"] for c in roster)
        self.stab = st.mean(c["stability"] for c in roster)
        self.no_awp = not any(c["position"] == "AWPER" for c in roster)
        self.chem = min(entry.rating["chem_raw"], chem_cap)
        # 除火力外的全部,和 P.score 的权重一致
        self.floor = (self.lead * .20 + self.exp * .20 + self.stab * .20
                      - (4.0 if self.no_awp else 0.0) + self.chem)

        # Stage 内的战绩状态(§11)
        self.reset()

    def reset(self):
        self.w = 0
        self.l = 0
        self.opponents = []

    @property
    def record(self):
        return (self.w, self.l)

    @property
    def difficulty(self):
        """§11:已交手对手的当前胜场总和 减 负场总和。"""
        return sum(o.w for o in self.opponents) - sum(o.l for o in self.opponents)

    @property
    def done(self):
        return self.w >= STAGE_WINS or self.l >= STAGE_LOSSES

    # ---------------------------------------------------------- 一张地图

    def play_map(self, rng, pressure):
        """§17:每人 Roll 状态,方差由自己的 Stability 决定。

        其中 TEAM_FORM_SHARE 那一份是全队共享的(今天这队状态好不好),
        剩下的才是个人的。共享的那一份不会被平均掉,所以队伍层面的波动
        才真的存在。
        """
        import math
        shared = math.sqrt(TEAM_FORM_SHARE)
        solo = math.sqrt(1.0 - TEAM_FORM_SHARE)
        z_team = rng.gauss(0.0, 1.0)
        rolled, detail = [], []
        for c in self.roster:
            sigma = (100 - c["stability"]) / 4.0
            r = sigma * (shared * z_team + solo * rng.gauss(0.0, 1.0))
            if r < 0.0:
                buf = (EXP_BUFFER * pressure * (c["experience"] / 100.0)
                       + LEAD_BUFFER * (self.team_lead / 100.0))
                r *= 1.0 - min(buf, BUFFER_CAP)
            eff = soft_cap(c["firepower"] + r)
            rolled.append(eff)
            detail.append((c, eff, eff - c["firepower"]))
        f = sorted(rolled, reverse=True)
        fire = f[0] * .35 + f[1] * .25 + st.mean(f[2:]) * .40
        return fire * .40 + self.floor - self.choke(pressure), detail

    def choke(self, pressure):
        if pressure <= 0.0:
            return 0.0
        relief = 1.0 - CHOKE_LEAD_RELIEF * (self.team_lead / 100.0)
        return CHOKE * pressure * (1.0 - self.exp / 100.0) * relief

    def baseline(self):
        """一个人都不 Roll 时的强度。应当等于 Entry Rating。"""
        f = sorted((c["firepower"] for c in self.roster), reverse=True)
        fire = f[0] * .35 + f[1] * .25 + st.mean(f[2:]) * .40
        return fire * .40 + self.floor


# ------------------------------------------------------------------ 一场比赛

def win_prob(sa, sb, scale=WIN_SCALE):
    """§27。差 0 分 -> 50%,差 5 分 -> 明显优势,差很多仍留一点爆冷。"""
    import math
    return 1.0 / (1.0 + math.exp(-(sa - sb) / scale))


class MapResult(object):
    def __init__(self, sa, sb, p, winner_a, mvp):
        self.sa, self.sb, self.p = sa, sb, p
        self.winner_a = winner_a
        self.mvp = mvp                        # (card, eff, delta) 本图最超常的人


def play_map(a, b, rng, pressure):
    sa, da = a.play_map(rng, pressure)
    sb, db = b.play_map(rng, pressure)
    p = win_prob(sa, sb)
    winner_a = rng.random() < p
    top = max(da if winner_a else db, key=lambda t: t[2])
    return MapResult(sa, sb, p, winner_a, top)


class MatchResult(object):
    """§32:一场比赛该记下来的东西。"""

    def __init__(self, a, b, bo, pressure, maps, before):
        self.a, self.b, self.bo, self.pressure, self.maps = a, b, bo, pressure, maps
        self.before = before                  # 赛前战绩(同战绩配对,双方一样)
        self.a_maps = sum(1 for m in maps if m.winner_a)
        self.b_maps = len(maps) - self.a_maps
        self.winner = a if self.a_maps > self.b_maps else b
        self.loser = b if self.winner is a else a
        # 赛前胜率:用不 Roll 的基准强度算,这是玩家在比赛前看得到的那个数
        self.pre = win_prob(a.baseline(), b.baseline())


def play_match(a, b, rng, bo, pressure):
    before = a.record
    maps, aw, bw = [], 0, 0
    need = bo // 2 + 1
    while aw < need and bw < need:
        m = play_map(a, b, rng, pressure)
        maps.append(m)
        if m.winner_a:
            aw += 1
        else:
            bw += 1
    return MatchResult(a, b, bo, pressure, maps, before)


def format_of(record):
    """§10.2:2 胜或 2 负的那一场是 BO3,其余 BO1。"""
    w, l = record
    if w == 2 and l == 2:
        return 3, PRESSURE_DECIDER
    if w == 2 or l == 2:
        return 3, PRESSURE_BO3
    return 1, PRESSURE_BO1


# ------------------------------------------------------------------ Swiss

def pair_group(group, avoid_rematch=True):
    """组内高种子打低种子,尽量避开重复对手(§11.2)。

    group 已经按 mid-stage seed 从好到差排好。取最好的那支,从最差的往回找
    第一个没打过的对手,递归;整组都配不出来才允许 rematch。
    """
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
    if got is None:
        return pair_group(group, avoid_rematch=False)
    return got


def mid_stage_order(teams):
    """§11.1:当前战绩 -> Difficulty -> 初始种子。"""
    return sorted(teams, key=lambda t: (-t.w, t.l, -t.difficulty, t.seed))


def run_stage(teams, rng):
    """跑完一个 16 队 Swiss Stage。

    返回 (晋级的 8 支(已按最终种子排序), [(轮次, 该轮全部比赛), ...])。
    §28:每轮全场 8 场都要打,因为下一轮的配对取决于所有队的战绩和 Difficulty。
    """
    for t in teams:
        t.reset()
    rounds = []

    for rnd in range(1, 6):
        alive = [t for t in teams if not t.done]
        if not alive:
            break
        if rnd == 1:
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
    # §8:晋级队按本 Stage 最终表现排,3-0 在 3-1 前面
    adv.sort(key=lambda t: (t.l, -t.difficulty, t.seed))
    return adv, rounds


def _by_record(alive):
    """按战绩分组,好的在前。"""
    groups = collections.defaultdict(list)
    for t in alive:
        groups[t.record].append(t)
    return sorted(groups.items(), key=lambda kv: (-kv[0][0], kv[0][1]))


# ------------------------------------------------------------------ 一届 Major

def run_major(field, rng, chem_cap=M.CHEM_CAP):
    """§7:Stage 1 -> Stage 2 -> Stage 3。Playoffs(§12)v0.1 不打。

    Stage 2 / 3 的种子 9-16 必须由上一个 Stage 决出,所以哪怕玩家直接从
    Stage 3 进场,下面两个 Stage 也得先跑——这不是多做的功能,是正确性。
    """
    mk = lambda e, s: MatchTeam(e, s, chem_cap)
    logs = {}

    s1 = [mk(e, i + 1) for i, e in enumerate(field[16:32])]
    adv1, logs[1] = run_stage(s1, rng)

    s2 = [mk(e, i + 1) for i, e in enumerate(field[8:16])]
    s2 += [MatchTeam(t.entry, 9 + i, chem_cap) for i, t in enumerate(adv1)]
    adv2, logs[2] = run_stage(s2, rng)

    s3 = [mk(e, i + 1) for i, e in enumerate(field[0:8])]
    s3 += [MatchTeam(t.entry, 9 + i, chem_cap) for i, t in enumerate(adv2)]
    adv3, logs[3] = run_stage(s3, rng)

    return {1: (s1, adv1), 2: (s2, adv2), 3: (s3, adv3)}, logs


def player_path(stages):
    """玩家在每个 Stage 的战绩,以及最后走到哪儿。"""
    out = []
    for stage in (1, 2, 3):
        teams, adv = stages[stage]
        me = next((t for t in teams if t.is_player), None)
        if me is None:
            continue
        out.append((stage, me, me in adv))
    return out


# ------------------------------------------------------------------ 输出

def show_match(r, rnd, stage):
    """§26 的那个比赛面板,先做成文本。"""
    a, b = r.a, r.b
    print()
    print("STAGE %d — ROUND %d" % (stage, rnd))
    print("  %s  vs  %s" % (a.name, b.name))
    print("  Record: %d-%d      Format: BO%d%s"
          % (r.before[0], r.before[1], r.bo,
             "  (2-2 生死局)" if r.pressure >= PRESSURE_DECIDER else
             ("  (晋级局)" if r.bo == 3 and r.before[0] == 2 else
              ("  (淘汰局)" if r.bo == 3 else ""))))
    print("  Pre-match Win Chance: %.0f%%" % (100 * r.pre))
    print("  RESULT: %s  (%d-%d)"
          % ("WIN" if r.winner is a else "LOSS", r.a_maps, r.b_maps))
    for i, m in enumerate(r.maps, 1):
        c, eff, d = m.mvp
        tag = "  LIFE GAME" if d >= 12 else ""
        print("    Map %d  %5.1f : %-5.1f  %s  MVP %s %d -> %d%s"
              % (i, m.sa, m.sb, "A" if m.winner_a else "B",
                 c["nickname"], c["firepower"], round(eff), tag))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", default=None,
                    help="只用这一届的 32 队,绕过 major_field.json")
    ap.add_argument("--field-seed", type=int, default=None,
                    help="赛场随机种子(默认同 --seed)")
    ap.add_argument("--seed", type=int, default=1, help="抽卡种子")
    ap.add_argument("--sim", type=int, default=None, help="比赛随机种子(默认同 --seed)")
    ap.add_argument("--cap", type=float, default=None,
                    help="覆盖 major_field.json 里的 chem_cap")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--lab", action="store_true")
    ap.add_argument("--runs", type=int, default=200)
    ap.add_argument("--scale", type=float, default=None)
    args = ap.parse_args()

    if args.cap is None:
        args.cap = float(M.load_config().get("chem_cap", M.CHEM_CAP))
    if args.scale is not None:
        global WIN_SCALE
        WIN_SCALE = args.scale
    if args.selftest:
        selftest(args)
        return
    if args.stats:
        stats(args, args.runs)
        return
    if args.lab:
        lab(args)
        return

    rosters = P.load_rosters()
    cards = P.load_cards()
    mates = P.mate_index(rosters)
    if args.event:
        field = _fixed_field(args, rosters)
        print("赛场:%s(单届,固定)" % args.event)
    else:
        cfg = M.load_config()
        field = M.build_field(random.Random(args.field_seed
                                            if args.field_seed is not None
                                            else args.seed),
                              cfg, rosters, args.cap)
        print("赛场:%d 支队,池子 %s,前 %d 固定,阵容 %s"
              % (len(field), " + ".join(cfg["pool"]), cfg["locked_top"],
                 cfg["roster_mode"]))

    roster, left = M.bot_draft(args.seed, cards, rosters, mates)
    if len(roster) < P.SLOTS:
        print("这局没凑齐 5 个人,换一个 --seed")
        return
    me = M.Entry("YOUR TEAM", roster, M.entry_rating(roster, rosters, args.cap),
                 is_player=True)
    rank, shove, field = M.insert_player(field, me)
    print("你的五个人(seed %d,剩 $%d):" % (args.seed, left))
    for c in roster:
        print("   %-7s %-14s %-12s G%d  火力%3d 稳定%3d 经验%3d"
              % (c["position"], c["nickname"], c["country"], c["grade"],
                 c["firepower"], c["stability"], c["experience"]))
    if rank > M.FIELD_SIZE:
        print()
        print("RUN END — Failed to qualify(第 %d)" % rank)
        return
    print()
    print("Projected Seed #%d,从 Stage %d 进场。"
          % (rank, M.stage_of(rank)))
    for team, was, now in shove.demoted:
        print("   你把 %s 从 Stage %d 挤到了 Stage %d。" % (team.name, was, now))
    if shove.dropped is not None:
        print("   %s 掉到第 33 位,失去席位。" % shove.dropped.name)

    rng = random.Random(args.sim if args.sim is not None else args.seed)
    stages, logs = run_major(field, rng, args.cap)

    for stage, me_t, advanced in player_path(stages):
        print()
        print("=" * 70)
        print("STAGE %d   (Stage 内种子 #%d)" % (stage, me_t.seed))
        print("=" * 70)
        for rnd, results in logs[stage]:
            for r in results:
                if r.a is me_t:
                    show_match(r, rnd, stage)
                elif r.b is me_t:
                    show_match(_flip(r), rnd, stage)
        print()
        print("  Stage %d 结束:%d-%d  ->  %s"
              % (stage, me_t.w, me_t.l, "晋级" if advanced else "淘汰"))
        if not advanced:
            break
    else:
        print()
        print("八强(进入 Playoffs,v0.1 不模拟):")
        for i, t in enumerate(stages[3][1], 1):
            print("  %d. %s%s" % (i, t.name, "   <<< 你" if t.is_player else ""))


def _flip(r):
    """玩家在 b 位时,把比赛结果翻过来显示,免得面板永远从对手视角写。"""
    f = MatchResult.__new__(MatchResult)
    f.a, f.b, f.bo, f.pressure, f.before = r.b, r.a, r.bo, r.pressure, r.before
    f.maps = [MapResult(m.sb, m.sa, 1 - m.p, not m.winner_a, m.mvp) for m in r.maps]
    f.a_maps, f.b_maps = r.b_maps, r.a_maps
    f.winner, f.loser = r.winner, r.loser
    f.pre = 1 - r.pre
    return f


# ------------------------------------------------------------------ selftest

def _fixed_field(args, rosters):
    """selftest / stats / lab 要一个不变的赛场,否则量的是赛场在抖。"""
    return M.real_field(args.event or M.DEFAULT_EVENT, rosters, args.cap)[0]


def selftest(args):
    """不 Roll 的强度必须等于 Entry Rating(§15:不许有第二套 Overall)。"""
    rosters = P.load_rosters()
    field = _fixed_field(args, rosters)
    bad = 0
    for i, e in enumerate(field):
        t = MatchTeam(e, i + 1, args.cap)
        if abs(t.baseline() - e.entry) > 1e-9:
            print("MISMATCH %s  %.6f vs %.6f" % (e.name, t.baseline(), e.entry))
            bad += 1
    print("baseline == Entry Rating: %d/%d 支队通过" % (len(field) - bad, len(field)))

    # Swiss 记账:每个 Stage 必须恰好 8 支 3 胜、8 支 3 负
    rng = random.Random(7)
    ok = 0
    for _ in range(50):
        stages, _ = run_major(field, rng, args.cap)
        for s in (1, 2, 3):
            teams, adv = stages[s]
            assert len(teams) == 16, len(teams)
            assert len(adv) == 8, len(adv)
            assert all(t.w == 3 or t.l == 3 for t in teams)
            assert all(len(t.opponents) == t.w + t.l for t in teams)
        ok += 1
    print("Swiss 记账(16 队 / 8 晋 8 汰 / 场次对齐): %d/50 局通过" % ok)


# ------------------------------------------------------------------ 验收(§35)

def _all_matches(logs):
    for stage in (1, 2, 3):
        for rnd, results in logs[stage]:
            for r in results:
                yield stage, rnd, r


def stats(args, runs=200):
    """§35 的第 1、2 问:强队是不是更容易晋级但不是必进?BO1 是不是更容易爆冷?"""
    rosters = P.load_rosters()
    field = _fixed_field(args, rosters)
    rng = random.Random(20260828)

    top8 = collections.Counter()
    fav = collections.Counter()      # (bo, 冷门?) -> 次数
    gap_bucket = collections.defaultdict(lambda: [0, 0])
    for _ in range(runs):
        stages, logs = run_major(field, rng, args.cap)
        for t in stages[3][1]:
            top8[t.name] += 1
        for stage, rnd, r in _all_matches(logs):
            da, db = r.a.baseline(), r.b.baseline()
            strong, weak = (r.a, r.b) if da >= db else (r.b, r.a)
            upset = r.winner is weak
            fav[(r.bo, upset)] += 1
            g = abs(da - db)
            key = (r.bo, min(int(g // 5) * 5, 20))
            gap_bucket[key][0] += 1
            gap_bucket[key][1] += 0 if upset else 1

    print("WIN_SCALE=%.1f  CHEM_CAP=%.1f  %d 届 Major" % (WIN_SCALE, args.cap, runs))
    print()
    print("[Q1] 进八强的概率(按 Projected Seed)")
    for i, e in enumerate(field, 1):
        if i in (1, 2, 3, 4, 8, 9, 12, 16, 17, 20, 24, 28, 32):
            print("   #%-2d %-20s %5.1f   八强率 %5.1f%%"
                  % (i, e.name, e.entry, 100.0 * top8[e.name] / runs))
    print()
    print("[Q2] 强的一方赢了多少")
    for bo in (1, 3):
        w = fav[(bo, False)]
        t = w + fav[(bo, True)]
        print("   BO%d  %5.1f%%   (n=%d)" % (bo, 100.0 * w / t, t))
    print()
    print("        实力差    BO1 强队胜率   BO3 强队胜率")
    for g in (0, 5, 10, 15, 20):
        row = []
        for bo in (1, 3):
            n, w = gap_bucket[(bo, g)]
            row.append("%5.1f%% (n=%5d)" % (100.0 * w / n, n) if n else "     -      ")
        lab = "%2d~%-2d" % (g, g + 5) if g < 20 else " 20+ "
        print("        %s     %s  %s" % (lab, row[0], row[1]))


# ------------------------------------------------------------------ 控制变量

def _fake(nick, pos, fire, lead, exp, stab):
    return {"nickname": nick, "page": nick, "position": pos, "firepower": fire,
            "leadership": lead, "experience": exp, "stability": stab,
            "country": "Nowhere", "grade": 3, "age": 25}


def _lab_team(name, fire, stab, exp, lead=70):
    roster = [_fake(name + str(i), p, fire, lead if p == "IGL" else 40, exp, stab)
              for i, p in enumerate(("IGL", "AWPER", "RIFLER", "RIFLER", "RIFLER"))]
    e = M.Entry(name, roster, {"base": 0.0, "chem_raw": 0.0, "chem": 0.0,
                               "entry": 0.0, "notes": []})
    return MatchTeam(e, 1, 0.0)


def lab(args, n=40000):
    """§35 的第 3、4 问。两支队 Entry Rating 强行调成完全一样,只差一个属性。

    这是真实赛场量不出来的:32 支真队里稳定和火力是相关的,拆不开。
    """
    print("对照实验:两支合成队,基准强度调到完全相等,只差一个变量。")
    print()

    def duel(x, y, bo, pressure, rounds=n):
        rng = random.Random(99)
        wx = 0
        for _ in range(rounds):
            if play_match(x, y, rng, bo, pressure).winner is x:
                wx += 1
        return 100.0 * wx / rounds

    # --- Q3 稳定 ---
    hi = _lab_team("HI", 80, 88, 60)
    lo = _tune(_lab_team("LO", 80, 55, 60), hi.baseline(), 55, 60)
    print("[Q3] 高稳定 vs 神经刀(基准 %.2f vs %.2f)"
          % (hi.baseline(), lo.baseline()))
    print("     BO1 高稳定胜率 %.1f%%    BO3 高稳定胜率 %.1f%%"
          % (duel(hi, lo, 1, 0.0), duel(hi, lo, 3, 0.0)))
    _spread(hi, lo)
    _stage_spread(args, hi, lo)

    # --- Q4 经验 ---
    # 经验差 62 点直接值 12.4 分基础分,补不回来,所以反过来压高经验队的火力
    le = _lab_team("LE", 80, 70, 30)
    he = _tune(_lab_team("HE", 80, 70, 92), le.baseline(), 70, 92)
    print()
    print("[Q4] 高经验 vs 低经验(基准 %.2f vs %.2f)"
          % (he.baseline(), le.baseline()))
    print("     常规 BO1(压力 0)   高经验胜率 %.1f%%"
          % duel(he, le, 1, PRESSURE_BO1))
    print("     生死 BO3(压力 1)   高经验胜率 %.1f%%"
          % duel(he, le, 3, PRESSURE_BO3))
    print("     2-2  BO3(压力 1.25)高经验胜率 %.1f%%"
          % duel(he, le, 3, PRESSURE_DECIDER))


def _stage_spread(args, hi, lo):  # noqa: C901
    """§16.1 的真正问法:稳定不该带来胜率优势,该带来**更窄的结果分布**。

    把这两支基准强度相同的队塞进同一个 Stage 1 打 400 次,看战绩分布。
    高稳定应该更少 3-0 也更少 0-3。
    """
    rosters = P.load_rosters()
    field = _fixed_field(args, rosters)
    rest = field[16:30]
    # 两支对照队必须调到这个 Stage 的中位强度,否则一起 3-0,什么也量不出来
    target = st.median([e.entry for e in rest])
    hi = _tune(hi, target, 88, 60)
    lo = _tune(lo, target, 55, 60)
    print("     (对照队调到 Stage 1 中位强度 %.1f)" % target)
    rng = random.Random(11)
    rec = {hi.name: collections.Counter(), lo.name: collections.Counter()}
    for it in range(6000):
        teams = [MatchTeam(e, i + 1, args.cap) for i, e in enumerate(rest)]
        # 首轮是 seed i 打 seed i+8,种子 16 系统性地抽到更弱的对手,
        # 所以两支对照队每局对调一次座位
        for t in (hi, lo):
            t2 = MatchTeam(t.entry, (15 if t is hi else 16) if it % 2 else
                           (16 if t is hi else 15), 0.0)
            t2.floor, t2.exp, t2.stab = t.floor, t.exp, t.stab
            t2.team_lead = t.team_lead
            teams.append(t2)
        run_stage(teams, rng)
        for t in teams[14:]:
            rec[t.name][(t.w, t.l)] += 1
    print("     同一个 Stage 打 6000 次的战绩分布:")
    for name, lab_ in ((hi.name, "高稳定"), (lo.name, "神经刀")):
        c = rec[name]
        n = sum(c.values())
        adv = sum(v for k, v in c.items() if k[0] == 3)
        print("       %s  3-0 %4.1f%%   晋级 %4.1f%%   0-3 %4.1f%%"
              % (lab_, 100.0 * c[(3, 0)] / n, 100.0 * adv / n,
                 100.0 * c[(0, 3)] / n))


def _tune(team, target, stab, exp):
    """二分火力,把这支队的基准强度顶到和对照组一模一样。"""
    lo, hi = 0.0, 99.0
    for _ in range(60):
        mid = (lo + hi) / 2
        t = _lab_team(team.name, mid, stab, exp)
        if t.baseline() < target:
            lo = mid
        else:
            hi = mid
    return _lab_team(team.name, (lo + hi) / 2, stab, exp)


def _spread(hi, lo):
    """同一张图上,两支队各自的实际发挥分布有多宽。"""
    rng = random.Random(5)
    for t, lab_ in ((hi, "高稳定"), (lo, "神经刀")):
        xs = sorted(t.play_map(rng, 0.0)[0] for _ in range(20000))
        print("     %s 单图发挥  10%%分位 %.1f   中位 %.1f   90%%分位 %.1f  (宽 %.1f)"
              % (lab_, xs[2000], xs[10000], xs[18000], xs[18000] - xs[2000]))


if __name__ == "__main__":
    main()
