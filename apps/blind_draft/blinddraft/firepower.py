# -*- coding: utf-8 -*-
"""Firepower v7 —— 把火力从 Grade 模板里解耦出来。

按《Draft 四维重构工作指南 v0.1》Phase 1:**这一轮只重算 firepower**,
只处理现役 G1/G2/G3,输出预览文件供人工审核,不写 draft_cards.json。

    python -m blinddraft.firepower              # 打印 diff 报告
    python -m blinddraft.firepower --write      # 另写 firepower_v7_preview.json

三个概念的分工(指南 §1),这个模块只碰第二个:

    Grade       生涯被证明到什么程度   —— 本轮不动
    Firepower   巅峰版本能打多高       —— 本轮重算
    Experience  大赛压力下经历过多少   —— 本轮不动,也**不做配重补偿**

## 标尺从哪来

不是从 rating 拟合出来的,是**人打的**。`data/blind_draft/firepower_anchors.json`
里 29 个枪手锚(指挥不进,见下)定义了"rating 1.20 在这个游戏里意味着多少火力"。
这个模块只做一件事:把那些锚连成一条单调曲线,然后用它去评没有锚的人。

**曲线只在锚点覆盖的区间内有效。** 锚点最低 rating 1.02,而现役 G1/G2/G3 里
有 41% 的人在 1.02 以下——二次外推到 0.83 会给出 42.4,到 0.78 给出 33.4,
都是凭空捏的。所以下沿以外**一律判为"无可靠证据"、回退模板**,
不是"给个大概的数"。这个项目已经栽过一次一模一样的:LOW_TIER_DISCOUNT
是从 82% 外推到 100% 的,后来整条路都作废了。

## 指挥不进这条通道

实测:枪手的「卡面火力 ~ 实测 rating」秩相关随样本量从 0.41 爬到 0.67,
指挥则在 0.15–0.22 之间原地不动——加样本显不出信号,说明本来就没有。
少打枪是这个位置的工作内容,不是水平。所以指挥的火力这一轮不动。
"""
import argparse
import json
import sys

from playerdb.paths import BLIND_DRAFT, DATA

# **不在顶层 import cards。** cards.generate() 现在要反过来调这里的 apply(),
# 顶层互相 import 会直接死循环。需要卡牌的函数一律由调用方传进来,
# 只有命令行入口那条路才懒加载一次。

ANCHOR_PATH = BLIND_DRAFT / "firepower_anchors.json"
STATS_PATH = BLIND_DRAFT / "5e_player_stats.json"
SNAP_PATH = BLIND_DRAFT / "team_snapshot.json"
TOP20_PATH = DATA / "hltv_top20.json"
OUT_PATH = BLIND_DRAFT / "firepower_v7_preview.json"

#: 证据强度的两条门槛(指南 §3.2 只要三档,不做复杂评分)。
#: 收缩常数 k≈31 图是量出来的(var(n) = 真实差异 + 噪声/n),所以:
#:   80 图 → 权重 0.72   30 图 → 0.49   这两个数就是下面两条线的由来。
STRONG_MAPS = 80
SUPPORTING_MAPS = 30

#: Supporting 只做**有上限的向上校正**(指南 §4.2.B)。上限取 6 点:
#: 相当于旧模板里 FIRE_SPREAD 的一整格,再多就等于让弱证据顶掉模板。
SUPPORTING_CAP = 6

#: 本轮处理的档位。G4/G5 默认不自动下修(指南 §4.2.A),只做 sanity check。
ACTIVE_GRADES = (1, 2, 3)

#: **这个世界的地板:rating 0.70 = 火力 50。对所有人,包括指挥。**
#:
#: 这是人给的定义,不是从数据推的:一整年打到 0.70 就是职业赛场的下沿,
#: 再低的选手不会还坐在首发位上。karrigan 的 0.83 → 55 是这条线上的另一个点,
#: 两者一致。
#:
#: 注意它约束的是**赛季均值**。单场当然可以低于 0.70——那是 stability
#: 管的方差,不是 firepower 管的均值。
FLOOR_ANCHOR = (0.70, 50)
FLOOR = FLOOR_ANCHOR[1]


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace("%", "").replace("+", "").replace(",", ""))
    except ValueError:
        return None


# ------------------------------------------------------------------ 标尺
def _cards():
    """懒加载,只给命令行那条路用。库内调用一律把卡牌传进来。

    **apply_perf=False**:要的是套火力层之前的模板值。拿套过层的卡当基线,
    diff 会恒为空,而那看起来像"没什么要改的"。
    """
    from . import cards as C
    return C.generate(apply_perf=False)[0]


def load_anchor_points(cards=None):
    """-> [(rating, firepower, nickname, maps)],只收枪手、只收填了火力的。"""
    if not ANCHOR_PATH.exists():
        return []
    anchors = json.loads(ANCHOR_PATH.read_text(encoding="utf-8")).get("anchors", {})
    stats = json.loads(STATS_PATH.read_text(encoding="utf-8"))["players"]
    by_page = {r["card_page"]: r for r in stats.values() if r.get("card_page")}
    cards = {c["page"]: c for c in (cards if cards is not None else _cards())}
    out = []
    for page, a in anchors.items():
        card, row = cards.get(page), by_page.get(page)
        if not card or not row or a.get("firepower") is None:
            continue
        if card["position"] == "IGL":
            continue                      # 指挥不进,见模块注释
        rating = _num(row.get("rating"))
        if rating is None:
            continue
        out.append((rating, float(a["firepower"]), card["nickname"],
                    int(_num(row.get("map_count")) or 0)))
    out.sort()
    return out


def build_scale(points=None, cards=None):
    """把锚点连成一条**单调**曲线。

    做法:先按 rating 分箱取中位数,再用 PAVA 把箱值压成单调,最后线性内插。

    为什么不直接拟合多项式:二次拟合在锚点区间内很贴(R² 0.922),但它在区间外
    掉头向下,而且没有任何东西保证单调——一条"rating 更高、火力更低"的尺子
    是荒谬的,而这种荒谬只在外推时才暴露。分箱 + PAVA 没有形状假设,
    单调是构造出来的,不是碰巧的。

    -> (fn, lo, hi):fn(rating) 只在 [lo, hi] 内有意义,调用方必须自己挡住边界。
    """
    pts = points if points is not None else load_anchor_points(cards)
    if len(pts) < 6:
        raise ValueError("锚点太少(%d 个),标尺立不住" % len(pts))
    # 地板是人给的定义,和人工锚点同等地位。有了它,下沿以下不再是外推。
    if not any(abs(r - FLOOR_ANCHOR[0]) < 1e-9 for r, *_ in pts):
        pts = sorted(pts + [(FLOOR_ANCHOR[0], float(FLOOR_ANCHOR[1]),
                             "地板(人给的定义)", 0)])

    lo, hi = pts[0][0], pts[-1][0]
    # 等频分箱:每箱至少 3 个人,箱数随锚点数长
    nbin = max(3, min(8, len(pts) // 4))
    size = len(pts) / nbin
    bins = []
    for i in range(nbin):
        chunk = pts[int(i * size):int((i + 1) * size)] or None
        if not chunk:
            continue
        rs = sorted(p[0] for p in chunk)
        fs = sorted(p[1] for p in chunk)
        mid = len(fs) // 2
        med = fs[mid] if len(fs) % 2 else (fs[mid - 1] + fs[mid]) / 2
        bins.append([sum(rs) / len(rs), med, len(chunk)])

    # PAVA:相邻箱违反单调就合并成加权均值,直到全程不降
    i = 0
    while i < len(bins) - 1:
        if bins[i][1] > bins[i + 1][1]:
            w = bins[i][2] + bins[i + 1][2]
            bins[i] = [(bins[i][0] * bins[i][2] + bins[i + 1][0] * bins[i + 1][2]) / w,
                       (bins[i][1] * bins[i][2] + bins[i + 1][1] * bins[i + 1][2]) / w, w]
            del bins[i + 1]
            i = max(0, i - 1)
        else:
            i += 1

    # 两端各钉一个真实锚点,免得边缘那一箱把最强/最弱的人拉平
    knots = [(lo, min(p[1] for p in pts if p[0] == lo))]
    knots += [(b[0], b[1]) for b in bins if lo < b[0] < hi]
    knots.append((hi, max(p[1] for p in pts if p[0] == hi)))
    knots = sorted(set(knots))
    # 钉完两端仍要保证单调
    for i in range(1, len(knots)):
        if knots[i][1] < knots[i - 1][1]:
            knots[i] = (knots[i][0], knots[i - 1][1])

    def fn(r):
        if r <= knots[0][0]:
            return knots[0][1]
        if r >= knots[-1][0]:
            return knots[-1][1]
        for (x0, y0), (x1, y1) in zip(knots, knots[1:]):
            if x0 <= r <= x1:
                t = 0.0 if x1 == x0 else (r - x0) / (x1 - x0)
                return y0 + (y1 - y0) * t
        return knots[-1][1]

    fn.knots = knots
    return fn, lo, hi


# ------------------------------------------------------------------ 证据
def evidence_of(row, lo, hi):
    """-> (强度, 一句为什么)。指南 §3.2 的三档,不做复杂评分。"""
    if not row:
        return "none", "这一年没有 Major/S+/S 级样本"
    rating, maps = _num(row.get("rating")), int(_num(row.get("map_count")) or 0)
    if rating is None or not maps:
        return "none", "有行但没有可用的 rating/图数"
    if rating < lo:
        return "none", "rating %.2f 低于锚点下沿 %.2f，标尺在这里是外推" % (rating, lo)
    if rating > hi:
        return "none", "rating %.2f 高于锚点上沿 %.2f，标尺在这里是外推" % (rating, hi)
    if maps >= STRONG_MAPS:
        return "strong", "%d 图，S 级口径，落在锚点覆盖区间内" % maps
    if maps >= SUPPORTING_MAPS:
        return "supporting", "%d 图，样本偏少，只做有上限的向上校正" % maps
    return "none", "只有 %d 图，样本不足以支撑一个数值" % maps


# ------------------------------------------------------------------ 重算
def apply(cards, overrides=None):
    """-> {page: {"firepower", "source", "floored", ...}},给 cards.generate() 用。

    **只返回改动,不写卡。** 由生成器决定怎么落地(它还要重算 overall、
    还要让人工层最后生效)。这样这份逻辑只有一处实现,后台展示的推导和
    引擎读的数不可能漂。

    锚点不足时抛 ValueError 由调用方吞掉——一个还没打锚的仓库应该照常
    生成 v6 卡,而不是崩在启动上。
    """
    return {r["page"]: r for r in preview(cards, overrides or {})["rows"]
            if r["new_firepower"] != r["old_firepower"]}


def preview(cards=None, overrides=None):
    """-> {"rows": [...], "scale": {...}, "counts": {...}}。只读,不写文件。"""
    if cards is None:
        from . import cards as _C
        cards = _C.generate(apply_perf=False)[0]
        overrides = _C.load_overrides()
    if overrides is None:
        from . import cards as _C
        overrides = _C.load_overrides()
    fn, lo, hi = build_scale(cards=cards)
    stats = json.loads(STATS_PATH.read_text(encoding="utf-8"))["players"]
    snap = json.loads(SNAP_PATH.read_text(encoding="utf-8"))
    top20 = {r["page"] for rows in
             json.loads(TOP20_PATH.read_text(encoding="utf-8"))["years"].values()
             for r in rows}
    by_page = {c["page"]: c for c in cards}
    by_nick = {c["nickname"].casefold(): c for c in cards}
    hand = {}
    if ANCHOR_PATH.exists():
        hand = {k: v.get("firepower") for k, v in
                json.loads(ANCHOR_PATH.read_text(encoding="utf-8")).get("anchors", {}).items()
                if v.get("firepower") is not None}

    active = {}
    for t in snap["teams"]:
        for m in t["roster"]:
            if m.get("starter"):
                active[m["id"]] = (m["name"], t.get("name"), t.get("vrs_rank"))

    rows = []
    for pid, (name, team, vrs) in active.items():
        card = by_page.get(name) or by_nick.get(name.casefold())
        if not card:
            continue                      # 卡库外的人这一轮不管(那是 AI 侧)
        row = stats.get(pid)
        strength, why = evidence_of(row, lo, hi)
        rating = _num((row or {}).get("rating"))
        maps = int(_num((row or {}).get("map_count")) or 0)
        old = card["firepower"]
        target = round(fn(rating)) if (rating is not None and lo <= rating <= hi) else None
        manual = "firepower" in (overrides.get(card["page"]) or {})

        new, src = old, "template"
        if card["page"] in hand:
            # **人手打的数是最高权威。** 它比任何从它拟出来的曲线都高一级,
            # 也不受档位、位置、样本量的任何限制——那些规则是用来评没打过锚
            # 的人的。曾经这里没有这一支,于是 31 个锚里有 21 个被规则算掉了
            # (luchov 打 85 变成 60,因为 51 图被判"弱证据"只准涨 6 点)。
            new, src = hand[card["page"]], "hand_anchor"
        elif card["position"] == "IGL":
            src = "igl_untouched"                     # 指挥不进通道
        elif manual:
            src = "manual_override"                   # 人工层优先,算法不覆盖
        elif card["grade"] not in ACTIVE_GRADES:
            # G4/G5 里**没打过锚的人**:默认不自动下修,只允许强证据往上刷新
            # (指南 §4.1 / §4.2.A)。打过锚的人上面那一支已经接管了——
            # 这条规则保护的是生涯巅峰不被统计估计抹掉,不是不被人的判断改。
            if strength == "strong" and target is not None and target > old:
                new, src = target, "performance_up_only"
            else:
                src = "career_kept"
        elif strength == "strong":
            new, src = target, "performance_evidence"
            if card["page"] in top20 and new < old:
                # 已被证明过的历史 Peak 不许被当前低迷抹掉(指南 §4.1)
                new, src = old, "career_peak_protected"
        elif strength == "supporting":
            if target is not None and target > old:
                new = min(target, old + SUPPORTING_CAP)
                src = "performance_supporting"
            else:
                src = "career_kept"                   # Supporting 只向上
        # 地板最后生效,盖过上面所有分支——**包括人工锚点和指挥**。
        # 它不是"没数据就给个数",是这个世界的定义:没有比 0.70 rating 更差
        # 的职业选手还坐在首发位上。
        floored = False
        if new < FLOOR:
            new, floored = FLOOR, True
            if src in ("template", "career_kept", "igl_untouched"):
                src = "floor"
        rows.append({
            "player": card["nickname"], "page": card["page"], "grade": card["grade"],
            "role": card["position"], "team": team, "vrs": vrs,
            "old_firepower": old, "new_firepower": int(new), "delta": int(new) - old,
            "evidence_source": src, "evidence_strength": strength, "why": why,
            "sample_count": maps, "rating": rating,
            "scale_target": target, "manual_override": manual,
            "floored": floored, "top20": card["page"] in top20,
        })
    # 快照里有人同时挂在两支队上,而且是**两个不同的 5e id**(NiKo 在 Falcons
    # 和 Millennium、buster 在 DEPO 和 BOGATYRI)——所以按 id 去重碰不到,
    # 必须在解析出卡之后按 page 去。不去重的话最后按 page 收敛时「哪一条证据
    # 生效」取决于遍历顺序,两条证据不同时结果就是随机的。
    # 取排名更高的那支队:一队的样本才是他现在的水平,VRS=0 多半是旧条目。
    best = {}
    for r in rows:
        prev = best.get(r["page"])
        if prev is None or (r["vrs"] or 9999) < (prev["vrs"] or 9999):
            best[r["page"]] = r
    rows = list(best.values())
    rows.sort(key=lambda r: (-abs(r["delta"]), r["player"]))
    counts = {"players": len(rows), "moved": sum(1 for r in rows if r["delta"]),
              "floored": sum(1 for r in rows if r["floored"]),
              "hand": sum(1 for r in rows if r["evidence_source"] == "hand_anchor")}
    for k in ("strong", "supporting", "none"):
        counts[k] = sum(1 for r in rows if r["evidence_strength"] == k)
    return {"rows": rows, "counts": counts,
            "scale": {"knots": [[round(x, 3), round(y, 1)] for x, y in fn.knots],
                      "valid_from": lo, "valid_to": hi,
                      "floor": FLOOR, "floor_rating": FLOOR_ANCHOR[0],
                      "anchors": len(load_anchor_points(cards))}}


HAND = {}


def flags(rows):
    """指南 §Phase 2 要人工过目的几类。**这一步不自动修。**"""
    out = []
    for r in rows:
        for tag, hit in (
                ("涨 10 以上", r["delta"] >= 10),
                ("跌 8 以上", r["delta"] <= -8),
                ("和人工锚差 3 以上", r["evidence_source"] != "hand_anchor"
                 and r["page"] in HAND and abs(r["new_firepower"] - HAND[r["page"]]) >= 3),
                ("有 Top20 却被下修", r["top20"] and r["delta"] < 0),
                # 托底是**有文档的机制**,不是异常。混进这一行会让 75 个正常的
                # 托底把真正该看的东西淹掉。
                ("无可靠证据却变了", r["evidence_strength"] == "none"
                 and r["delta"] and not r["floored"]),
                ("被下限托上来", r["floored"])):
            if hit:
                out.append((tag, r))
    return out


def write_preview(data) -> str:
    from . import cards as C
    payload = {
        "_note": ("Firepower v7 预览 —— 现在已经接进 cards.generate(),"
                  "这份文件是**审核用的账**,不是数据源。"
                  "按《四维重构工作指南 v0.1》Phase 1,只重算现役 G1/G2/G3 的火力,"
                  "供人工审核。标尺来自 firepower_anchors.json 的人工锚点,"
                  "只在 valid_from..valid_to 之间有效;区间外一律判 none、回退模板。"),
        "card_version": C.CARD_VERSION,
        "scale": data["scale"], "counts": data["counts"], "rows": data["rows"],
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    return str(OUT_PATH)


def main():
    ap = argparse.ArgumentParser(description="Firepower v7 预览(Phase 1)")
    ap.add_argument("--write", action="store_true", help="另写 firepower_v7_preview.json")
    ap.add_argument("--top", type=int, default=20, help="报告里列出变动最大的前 N 个")
    args = ap.parse_args()

    data = preview()
    s, c = data["scale"], data["counts"]
    print("标尺:%d 个人工锚,%d 个折点,有效区间 rating %.2f–%.2f"
          % (s["anchors"], len(s["knots"]), s["valid_from"], s["valid_to"]))
    print("   " + "  ".join("%.2f→%.0f" % (x, y) for x, y in s["knots"]))
    print()
    print("现役卡 %d 张:强证据 %d / 弱证据 %d / 无可靠证据 %d;动了 %d 张"
          % (c["players"], c["strong"], c["supporting"], c["none"], c["moved"]))
    print("   人工锚直接生效 %d 张;被地板(rating %.2f = 火力 %d)托上来 %d 张"
          % (c["hand"], FLOOR_ANCHOR[0], FLOOR, c["floored"]))
    print()
    print("%-13s %-4s %-7s %5s %5s %6s  %s"
          % ("选手", "档", "位置", "旧", "新", "变动", "依据"))
    for r in data["rows"][:args.top]:
        if not r["delta"]:
            continue
        print("%-13s G%-3d %-7s %5d %5d %+6d  %s (%d 图)"
              % (r["player"], r["grade"], r["role"], r["old_firepower"],
                 r["new_firepower"], r["delta"], r["evidence_source"], r["sample_count"]))
    # 档位和火力已经解耦,所以「他的火力像哪一档」这个问题本身不成立了
    # ——G5 的火力不一定高于 G4。真正值得看的是**同档之内谁被拉开了**。
    print()
    print("同档之内跨度最大的几档(解耦之后这才是要看的东西):")
    for g in (5, 4, 3, 2, 1):
        sub_ = [r for r in data["rows"] if r["grade"] == g and r["role"] != "IGL"]
        if len(sub_) < 3:
            continue
        hi = max(sub_, key=lambda r: r["new_firepower"])
        lo = min(sub_, key=lambda r: r["new_firepower"])
        print("   G%d  %d–%d   最高 %s   最低 %s"
              % (g, lo["new_firepower"], hi["new_firepower"], hi["player"], lo["player"]))

    HAND.update({k: v.get("firepower") for k, v in
                 (json.loads(ANCHOR_PATH.read_text(encoding="utf-8")).get("anchors", {})
                  if ANCHOR_PATH.exists() else {}).items()
                 if v.get("firepower") is not None})
    fl = flags(data["rows"])
    print()
    print("需要人工过目的 %d 条(Phase 2,不自动修):" % len(fl))
    seen = {}
    for tag, r in fl:
        seen.setdefault(tag, []).append(r["player"])
    for tag, who in seen.items():
        print("   %-18s %2d 人  %s" % (tag, len(who), " ".join(who[:6])))
    if args.write:
        print("\n写入 %s" % write_preview(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
