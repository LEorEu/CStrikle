# -*- coding: utf-8 -*-
"""两张只读的审计表，回答的是同一件事的两层。

`audit()`：哪支队的 VRS 排名和我们的 Entry 差得远——**这个偏差是现实原因还是
数据原因**。`audit_cards()`：那 32 支队里有多少人的四维根本没有当前证据。
两个一起看才分得清「它真的弱」和「我们不知道它多强」。什么都不改。
"""
import collections

from .. import major as M
from .team import Team
from .tournament import major_field


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


def card_bucket(card):
    """一名 AI 选手的当前火力站在哪一档证据上。

    `career_age_fallback` 有两种完全不同的成因，混在一起看不出该做什么：
    有 5E 行但样本不够（重抓或调门槛能救），和连行都没有（救不回，只能人工）。
    """
    src = (card.get("_sources") or {}).get("firepower") or {}
    name = src.get("source") or ""
    if name == "current_performance":
        return "strong", src
    if name == "current_performance_shrunk":
        return "supporting", src
    if name == "igl_career_prior":
        return "igl", src
    return ("thin" if src.get("maps") else "no_data"), src


_BUCKET_MARK = {"strong": "强", "supporting": "中", "igl": "指",
                "thin": "薄", "no_data": "无"}


def audit_cards(thin_only=False):
    """P1：AI 当前卡的证据覆盖。只读，什么都不改。

    `--audit` 回答「哪支队的 VRS 和 Entry 对不上」；这个回答上一层的问题——
    **那 32 支队里，有多少人的四维根本没有当前证据**。两个一起看才分得清
    「它真的弱」和「我们不知道它多强」。
    """
    from .. import ai_teams as A
    cfg = M.load_config()
    pool, asof = A.build_pool_field(cfg)
    rosters = M.load_rosters_cached()
    cap = float(cfg.get("cohesion_cap", M.COHESION_CAP))
    teams = {}
    for t in pool:
        r = A.entry_of(t, rosters, cap)
        teams[t["name"]] = Team(t["name"], t["roster"], min(r["chem_raw"], cap))
        teams[t["name"]].stage = t.get("stage")
        teams[t["name"]].vrs = t.get("vrs")
    field = [t for t in pool if t.get("stage")]
    bench = [t for t in pool if not t.get("stage")]

    def tally(group):
        c = collections.Counter()
        for t in group:
            for p in t["roster"]:
                c[card_bucket(p)[0]] += 1
        return c

    print("=" * 78)
    print("AI 当前卡证据覆盖      快照 %s" % (asof or "?"))
    print("=" * 78)
    print("%-18s %5s %7s %11s %6s %7s %7s" %
          ("", "人数", "strong", "supporting", "IGL", "薄数据", "无数据"))
    for label, grp in (("本届正赛 %d 席" % len(field), field),
                       ("候选池替补 %d 支" % len(bench), bench),
                       ("合计 %d 支" % len(pool), pool)):
        c, n = tally(grp), len(grp) * 5
        print("%-18s %5d %7d %11d %6d %7d %7d" %
              (label, n, c["strong"], c["supporting"], c["igl"],
               c["thin"], c["no_data"]))
    blind = tally(field)["thin"] + tally(field)["no_data"]
    print()
    print("正赛 %d 人里 %d 人（%.0f%%）的火力没有任何当前证据，全部回退生涯先验。"
          % (len(field) * 5, blind, 100.0 * blind / (len(field) * 5)))
    print("IGL 不算缺数据——设计上就不用 rating 推火力（§AI 当前卡）。")

    if thin_only:
        _audit_thin(pool)
        return
    ent = {t["name"]: i for i, t in enumerate(
        sorted(field, key=lambda x: -teams[x["name"]].entry()), 1)}
    print()
    print("-" * 78)
    print("正赛 32 队 · 有几个人的四维是猜的")
    print("-" * 78)
    print("%-22s %5s %5s %6s %6s  %s" %
          ("队", "Stage", "VRS", "Entry位", "无证据", "五人证据"))
    rows = []
    for t in field:
        marks = [_BUCKET_MARK[card_bucket(p)[0]] for p in t["roster"]]
        n = sum(1 for p in t["roster"]
                if card_bucket(p)[0] in ("thin", "no_data"))
        rows.append((n, t, "".join(marks)))
    for n, t, marks in sorted(rows, key=lambda r: (-r[0], r[1].get("vrs") or 999)):
        print("%-22s %5d %5s %6d %6d  %s%s" %
              (t["name"], t["stage"], t.get("vrs") or "-", ent[t["name"]], n,
               marks, "  <<<" if n >= 3 else ""))
    _audit_thin(pool)
    print()
    print("-" * 78)
    print("卡库外真人：Firepower 之外三维**全部是角色模板**，不是推导")
    print("-" * 78)
    nocard = [(t, p) for t in pool for p in t["roster"] if p.get("_nocard")]
    inf = [(t, p) for t, p in nocard if t.get("stage")]
    print("候选池 %d 人，本届正赛首发 %d 人（正赛 %d 席的 %.0f%%）"
          % (len(nocard), len(inf), len(field) * 5,
             100.0 * len(inf) / (len(field) * 5)))
    print("%-14s %-20s %5s %6s %5s %5s %5s %5s  %s" %
          ("选手", "队", "Stage", "位置", "火力", "指挥", "经验", "稳定", "火力证据"))
    for t, p in sorted(inf, key=lambda x: (x[0].get("vrs") or 999,
                                           x[1]["nickname"])):
        k, src = card_bucket(p)
        print("%-14s %-20s %5s %6s %5d %5d %5d %5d  %s" %
              (p["nickname"], t["name"], t["stage"], p["position"],
               p["firepower"], p["leadership"], p["experience"], p["stability"],
               _BUCKET_MARK[k] + ("(%s图)" % src["maps"] if k == "thin" else "")))


def _audit_thin(pool):
    """薄数据和无数据的逐人名单——要人工定四维的就是这两批。"""
    print()
    print("-" * 78)
    print("薄数据：有 5E 行但样本不够，火力回退（重抓或调门槛可能救回）")
    print("-" * 78)
    print("%-14s %-20s %5s %7s %6s %7s %6s %6s" %
          ("选手", "队", "Stage", "位置", "图数", "rating", "火力", "稳定"))
    thin = [(t, p, card_bucket(p)[1]) for t in pool for p in t["roster"]
            if card_bucket(p)[0] == "thin"]
    for t, p, src in sorted(thin, key=lambda x: (-(x[2].get("maps") or 0),
                                                 x[0].get("vrs") or 999)):
        print("%-14s %-20s %5s %7s %6s %7s %6d %6d" %
              (p["nickname"], t["name"], t.get("stage") or "-", p["position"],
               src.get("maps") or 0, src.get("rating") or "-",
               p["firepower"], p["stability"]))
    print()
    print("  门槛放宽到   还能覆盖")
    have = [src["maps"] for _t, _p, src in thin if src.get("maps")]
    for th in (25, 20, 15, 10, 5, 1):
        print("  ≥%-4d 图     %3d 人" % (th, sum(1 for m in have if m >= th)))

    print()
    print("-" * 78)
    print("无数据：连 5E 行都没有（重抓救不回，只能人工或接受先验）")
    print("-" * 78)
    print("%-14s %-20s %5s %7s %5s %5s %5s %5s  %s" %
          ("选手", "队", "Stage", "位置", "火力", "指挥", "经验", "稳定", "来源"))
    for t in pool:
        for p in t["roster"]:
            if card_bucket(p)[0] != "no_data":
                continue
            print("%-14s %-20s %5s %7s %5d %5d %5d %5d  %s" %
                  (p["nickname"], t["name"], t.get("stage") or "-",
                   p["position"], p["firepower"], p["leadership"],
                   p["experience"], p["stability"],
                   "卡库外真人（四维全模板）" if p.get("_nocard")
                   else "卡库内，无当前数据"))


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
