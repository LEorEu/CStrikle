# -*- coding: utf-8 -*-
"""验收台与调参台：每个宏观结论后面都要跟着产生它的那组数字。

**胜率只能实测。** §13.3 说 Map Residual 与经典 logistic「统计意义上等价」，
那只在双方 Team Performance 是常数时成立；实际曲线是 Player 波动和 Residual
的卷积，等效 scale 随分差从 7.1 漂到 6.4。所以动完任何系数都要来这里重跑，
不许从系数上算。
"""
import collections
import math
import random
import statistics as st

from .. import draft as P
from . import params as PA
from .play import play_match
from .roll import form_delta
from .probes import entry_probe, probe_team
from .report import show_map
from .roster import FIXTURES, named_team, roster_team
from .tournament import major_field, run_major


def win_rate(a, b, bo, pressure, runs, seed=1, scale=None):
    rng = random.Random(seed)
    return sum(play_match(a, b, rng, bo, pressure, scale).winner is a
               for _ in range(runs)) / runs


def duel(high, low, runs=20000, stab=70, seed=20260902):
    """两个 Entry 之间的胜率锚。从 v1 的 --duel 搬过来，口径换成 v2。

    §13.3：MAP_SCALE 只控制 Residual 那一层，胜率**只能实测**。所以每次动
    MAP_SCALE / SIGMA_SCALE / 任何队伍层 modifier 之后，都要重新跑这个数，
    不能从系数上算。
    """
    a, b = entry_probe("HI", high, stab), entry_probe("LO", low, stab)
    print("Entry %.1f vs %.1f（纯火力口径，稳定同为 %d，各 %d 次）"
          % (a.entry(), b.entry(), stab, runs))
    out = {}
    for bo in (1, 3):
        out[bo] = win_rate(a, b, bo, 0.0, runs, seed)
        print("  BO%d  强队胜率 %.1f%%" % (bo, 100.0 * out[bo]))
    print("  MAP_SCALE=%.1f  SIGMA_SCALE=%.2f"
          % (PA.MAP_SCALE, PA.SIGMA_SCALE))
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
    print("整届分布  快照 %s  %d 届  MAP_SCALE=%.1f" % (asof or "?", runs, PA.MAP_SCALE))
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
            if top.delta >= PA.LIFE_GAME_AT:
                life[top.card["nickname"]] += 1
        head = label
        for c in sorted(team.roster, key=lambda c: -c["firepower"]):
            n = c["nickname"]
            print("  %-14s %-10s %5d %6d %7.1f%% %7.1f%%"
                  % (head, n, c["firepower"], c["stability"],
                     100 * mvp[n] / runs, 100 * life[n] / runs))
            head = ""

    print("\n【3】BO1 / BO3 爆冷差（同稳定，火力差 10 分）")
    strong, weak = probe_team("强", 80, 70), probe_team("弱", 70, 70)
    for bo in (1, 3):
        r = 1 - win_rate(strong, weak, bo, 0.0, runs, seed=11)
        print("  BO%d  弱队爆冷 %.1f%%" % (bo, 100 * r))

    print("\n【4】低经验队在高压局的变化（同火力同稳定，只差经验）")
    ref = probe_team("ref", 78, 60, exp=60)
    for exp in (25, 55, 90):
        t = probe_team("E%d" % exp, 78, 60, exp=exp)
        base = win_rate(t, ref, 1, PA.PRESSURE["swiss"], runs, seed=13)
        hot = win_rate(t, ref, 1, PA.PRESSURE["decider"], runs, seed=13)
        print("  经验 %2d   普通轮 %.1f%%  ->  生死局 %.1f%%   (%+.1f)"
              % (exp, 100 * base, 100 * hot, 100 * (hot - base)))

    print("\n【5】顶级 IGL 的实际胜率差（同五个人，只换 IGL 的领导力）")
    ref2 = probe_team("ref", 78, 60, igl_lead=65)
    for lead, tag in ((96, "gla1ve 级"), (65, "普通"), (50, "弱")):
        t = probe_team("L%d" % lead, 78, 60, igl_lead=lead)
        print("  领导力 %2d %-9s 战术执行 %+.2f   对普通 IGL 队胜率 %.1f%%"
              % (lead, tag, t.tactical, 100 * win_rate(t, ref2, 1, 0.0, runs, 17)))
    no_igl = probe_team("无IGL", 78, 60)
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
    v1_logistic = lambda gap: 1.0 / (1.0 + math.exp(-gap / PA.V1_WIN_SCALE))  # noqa: E731
    print("=" * 74)
    print("§9 代价核对 — 同样的实力差，两版给出的胜率")
    print("=" * 74)
    print("  %-8s %12s %12s %12s" % ("差距", "v1 logistic", "v2 BO1", "v2 BO3"))
    for gap in (2, 5, 10, 20):
        a, b = probe_team("A", 70 + gap, 65), probe_team("B", 70, 65)
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


def demo(name="donk carry", seed=5, label=None):
    me = roster_team(name, label)
    name = me.name
    opp = min(major_field(1)[0], key=lambda t: abs(t.entry() - me.entry()))
    rng = random.Random(seed)
    for bo, tag in ((1, "swiss"), (3, "decider")):
        r = play_match(me, opp, rng, bo, PA.PRESSURE[tag])
        print("\n%s  vs %s  (BO%d, pressure %.1f)  %s %d:%d"
              % (name, opp.name, bo, PA.PRESSURE[tag],
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
            a, b = probe_team("A", 70 + gap, 70), probe_team("B", 70, 70)
            row.append(100 * win_rate(a, b, 1, 0.0, runs, 41, scale))
        a, b = probe_team("A", 80, 70), probe_team("B", 70, 70)
        upset = 100 * (1 - win_rate(a, b, 1, 0.0, runs, 41, scale))
        c, d = probe_team("C", 75, 70), probe_team("D", 70, 70)
        bo3 = 100 * win_rate(c, d, 3, 0.0, runs, 43, scale)
        star = " <- 当前" if scale == PA.MAP_SCALE else ""
        print("  %-7d %7.1f%% %7.1f%% %7.1f%% %7.1f%% | %10.1f%% %9.1f%%%s"
              % (scale, *row, upset, bo3, star))

    print("\n  设计稿 §13.3 说 Map Residual 与经典 logistic「统计意义上等价」——")
    print("  近似而已。SA/SB 本身含 Player 波动，残差叠上去会把曲线再抹平一层：")
    print("  %-7s %10s %10s" % ("SCALE", "实测 +5", "纯 logistic"))
    for scale in (4, 6):
        c, d = probe_team("C", 75, 70), probe_team("D", 70, 70)
        got = 100 * win_rate(c, d, 1, 0.0, runs, 43, scale)
        pure = 100 / (1 + pow(2.718281828, -5.0 / scale))
        print("  %-7d %9.1f%% %9.1f%%" % (scale, got, pure))
    print("  所以同样的手感，MAP_SCALE 可以取得比按纯 logistic 反推的更小。")

    print("\n" + "-" * 78)
    print("§13.5 三选二（历史证据，说明 Map Residual 为什么必须存在）")
    print("-" * 78)
    keep = (PA.SIGMA_SCALE, PA.TEAM_RHO)
    A, B = probe_team("A", 80, 70), probe_team("B", 70, 70)

    def upset_no_residual():
        return 1 - win_rate(A, B, 1, 0.0, runs, 11, 0.0)   # scale=0 → 无残差

    print("  若删掉 Map Residual，只让 Player Roll 决定胜负：")
    print("  %-24s %10s %s" % ("", "+10 爆冷", "代价"))
    PA.TEAM_RHO = 0.0
    for k in (1.0, 2.0, 4.0):
        PA.SIGMA_SCALE = k
        lo = 80 + form_delta(0.05, 50)
        hi = 80 + form_delta(0.95, 50)
        print("  放大个人波动 x%-9.1f %9.1f%%  F80/S50 单图 %.0f~%.0f"
              % (k, 100 * upset_no_residual(), lo, hi))
    PA.SIGMA_SCALE = 1.0
    for rho in (0.5, 0.8):
        PA.TEAM_RHO = rho
        print("  队内相关性 rho=%-8.2f %9.1f%%  整队一起爆/一起崩"
              % (rho, 100 * upset_no_residual()))
    PA.SIGMA_SCALE, PA.TEAM_RHO = keep
    print("\n  两条路都不通：放大波动毁掉 Player Story，相关性只对齐不放大。")
    print("  所以队伍级的未建模随机必须单独有个出口，这就是 Map Residual。")
