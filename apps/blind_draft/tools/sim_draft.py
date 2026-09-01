# -*- coding: utf-8 -*-
"""盲选组队玩法的桌面推演:不碰前端,只回答「这套规则成不成立」。

跑法:
    .\.venv\Scripts\python -X utf8 -m bdtools.sim_draft            # 档位体检 + 3 个样例池
    .\.venv\Scripts\python -X utf8 -m bdtools.sim_draft --pools 200 # 只跑体检,加大样本

看三件事:
1. 五档人数和位置分布 —— 有没有哪档凑不出人,IGL/AWP 够不够分
2. 抽出来的池子长什么样 —— 玩家实际看到的信息够不够做决策
3. 有没有无脑最优解 —— 穷举每个池子的最优阵容,看价格组合是不是永远同一套
"""
import argparse
import collections
import itertools
import json
import random
import statistics as st
import sys
from pathlib import Path

from playerdb.players import PlayerDB

BUDGET = 15
LINEUP = {"Rifler": 3, "AWPer": 1, "IGL": 1}   # 合法阵容
# 每档发几张牌。3 块档给得多,因为它是三合一、方差最大的一档。
DEAL = {5: 3, 4: 3, 3: 4, 2: 4, 1: 5}
CLUE = {5: "Major 参加", 4: "Major 冠军", 3: "Major 参加", 2: "国籍", 1: "俱乐部"}


def build_tiers(db):
    """自上而下互斥分配:一个人只会落进一档。"""
    top = json.loads((Path(__file__).resolve().parent.parent
                      / "data" / "hltv_top20.json").read_text(encoding="utf-8"))["years"]
    ranks = collections.defaultdict(list)
    for year in top.values():
        for row in year:
            ranks[row["page"]].append(row["rank"])

    def champs(p):
        return sum(1 for m in p.majors if str(m.get("placement")) == "1")

    tiers = {5: [], 4: [], 3: [], 2: [], 1: []}
    for p in db.players:
        rs = ranks.get(p.page, [])
        age = p.age() or 99
        if rs and min(rs) <= 5:
            tier = 5
        elif len(rs) >= 2:
            tier = 4
        elif len(rs) == 1:
            tier = 3                                    # 只上过一次榜
        elif champs(p):
            tier = 3                                    # 冠军队角色球员
        elif age <= 24 and p.team and p.majors_count >= 3:
            tier = 3                                    # 年轻潜力股
        elif p.majors_count >= 5:
            tier = 2
        else:
            tier = 1
        tiers[tier].append(p)
    return tiers, ranks


def power(p, ranks):
    """战力 v0(待调):历年 top20 名次加权 + Major 参加次数。"""
    return sum(21 - r for r in ranks.get(p.page, [])) + p.majors_count * 2


def clue_of(p, tier, ranks):
    if tier in (5, 3):
        return f"打过 {p.majors_count} 届 Major"
    if tier == 4:
        n = sum(1 for m in p.majors if str(m.get("placement")) == "1")
        return f"{n} 个 Major 冠军"
    if tier == 2:
        return p.country or "国籍不明"
    return p.team or "自由身"


def deal_pool(tiers, rng):
    """发牌。位置在整池层面兜底,避免抽出一个凑不出合法阵容的死局。"""
    for _ in range(200):
        pool = []
        for tier, n in DEAL.items():
            pool += [(tier, p) for p in rng.sample(tiers[tier], min(n, len(tiers[tier])))]
        have = collections.Counter(p.primary_role for _, p in pool)
        if all(have[r] >= n for r, n in LINEUP.items()):
            return pool
    raise RuntimeError("发不出合法池子,DEAL 配置要调")


def best_lineup(pool, ranks):
    """穷举预算内战力最高的合法阵容。用来检测无脑最优解。"""
    by_role = collections.defaultdict(list)
    for tier, p in pool:
        by_role[p.primary_role].append((tier, p))
    best = None
    combos = [itertools.combinations(by_role.get(role, []), n)
              for role, n in LINEUP.items()]
    for picks in itertools.product(*combos):
        flat = [c for group in picks for c in group]
        cost = sum(t for t, _ in flat)
        if cost > BUDGET:
            continue
        score = sum(power(p, ranks) for _, p in flat)
        if best is None or score > best[0]:
            best = (score, cost, flat)
    return best


def audit(tiers, ranks):
    print("=" * 74)
    print("档位体检")
    print("=" * 74)
    for tier in (5, 4, 3, 2, 1):
        g = tiers[tier]
        roles = collections.Counter(p.primary_role for p in g)
        vals = sorted(power(p, ranks) for p in g) or [0]
        print(f"{tier} 块  {len(g):3d} 人 | 战力 中位 {st.median(vals):5.1f} "
              f"最低 {vals[0]:3d} 最高 {vals[-1]:3d} | "
              + " ".join(f"{k}={v}" for k, v in roles.most_common()))
    print()


def show_pool(pool, ranks, idx):
    print("=" * 74)
    print(f"样例池 #{idx} —— 玩家看到的")
    print("=" * 74)
    for tier, p in sorted(pool, key=lambda x: -x[0]):
        print(f"  {tier} 块 | {p.primary_role:6s} | {clue_of(p, tier, ranks)}")
    best = best_lineup(pool, ranks)
    print("-" * 74)
    print("揭晓(战力 v0):")
    for tier, p in sorted(pool, key=lambda x: -x[0]):
        print(f"  {tier} 块 | {p.primary_role:6s} | {p.nickname:14s} "
              f"战力 {power(p, ranks):3d}"
              + ("  ← 最优解选中" if best and (tier, p) in best[2] else ""))
    if best:
        score, cost, flat = best
        combo = "+".join(str(t) for t, _ in sorted(flat, key=lambda x: -x[0]))
        print(f"\n  最优阵容: 花费 {cost} 块 ({combo}) 战力合计 {score}")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pools", type=int, default=3, help="生成几个池子")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    db = PlayerDB()
    tiers, ranks = build_tiers(db)
    audit(tiers, ranks)

    patterns = collections.Counter()
    for i in range(args.pools):
        pool = deal_pool(tiers, rng)
        if i < 3:
            show_pool(pool, ranks, i + 1)
        best = best_lineup(pool, ranks)
        if best:
            patterns["+".join(str(t) for t, _ in sorted(best[2], key=lambda x: -x[0]))] += 1

    print("=" * 74)
    print(f"最优阵容的价格组合分布({args.pools} 个池子)")
    print("=" * 74)
    for combo, n in patterns.most_common(10):
        print(f"  {combo:14s} {n:4d} 次  {n / args.pools:5.1%}")


if __name__ == "__main__":
    main()
