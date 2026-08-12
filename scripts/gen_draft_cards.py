# -*- coding: utf-8 -*-
"""Blind Draft:把选手库生成成固定选手卡(v0.2 设计稿 §27 的 Step 1/2/3/7)。

    .\.venv\Scripts\python -X utf8 scripts\gen_draft_cards.py            # 只体检,不写盘
    .\.venv\Scripts\python -X utf8 scripts\gen_draft_cards.py --sample NiKo s1mple
    .\.venv\Scripts\python -X utf8 scripts\gen_draft_cards.py --write    # 生成 data/draft_cards.json

设计稿 §16.1 要求「卡牌 RNG 只在生成时跑一次,之后永久固定」。这里不靠保存
随机状态来实现,而是让生成器**幂等**:每个人的随机数种子取自
`hash(page + CARD_VERSION)`,同一个人在同一版本下永远算出同一张卡。
否则重跑一次生成脚本,650 张卡会集体悄悄变样,玩家积累的认知全部作废,
而且不会有任何报错——这个项目已经栽过好几次这类静默失败。

改数值请改模板/修正函数,然后**手动 bump CARD_VERSION**,那是一次自觉的
全库重算;不 bump 就只有被改动的那部分公式生效,可以 diff 出来。
"""
import argparse
import collections
import hashlib
import json
import math
import random
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.players import PlayerDB          # noqa: E402

CARD_VERSION = "v0"
OUT_PATH = ROOT / "data" / "draft_cards.json"
# 人工平衡层。和 player_overrides.json 并列放在可写卷里,线上后台改完不用重新部署。
OVERRIDE_PATH = ROOT / "data" / "manual" / "draft_overrides.json"
TOP20_PATH = ROOT / "data" / "hltv_top20.json"

# 设计稿 §17 的 Grade × Position 基础模板:(火力, 领导, 经验, 稳定)
TEMPLATE = {
    "RIFLER": {1: (52, 20, 20, 48), 2: (60, 22, 34, 56), 3: (70, 24, 48, 65),
               4: (80, 27, 62, 75), 5: (89, 30, 75, 84)},
    "AWPER":  {1: (55, 18, 20, 51), 2: (64, 20, 34, 60), 3: (74, 22, 48, 70),
               4: (84, 24, 62, 80), 5: (92, 26, 75, 88)},
    "IGL":    {1: (45, 56, 25, 50), 2: (49, 65, 38, 57), 3: (54, 75, 52, 64),
               4: (60, 84, 65, 71), 5: (66, 90, 76, 77)},
}
# 设计稿 §18 的位置权重,只用于内部估值/STEAL 判定,不驱动比赛模拟
WEIGHT = {"RIFLER": (.55, .05, .20, .20),
          "AWPER":  (.45, .05, .20, .30),
          "IGL":    (.20, .45, .30, .05)}
ATTRS = ("firepower", "leadership", "experience", "stability")
# Top20 履历在**同档内**能拉开的火力幅度。档间距离由模板负责,修正项只管档内排序;
# 这个值调大就会侵蚀相邻档位,调到 0 则同档所有人火力只差随机抖动。
FIRE_SPREAD = 6.0


# ----------------------------------------------------------------- 数据准备
def load_top20():
    years = json.loads(TOP20_PATH.read_text(encoding="utf-8"))["years"]
    ranks = collections.defaultdict(list)
    for rows in years.values():
        for row in rows:
            ranks[row["page"]].append(row["rank"])
    return ranks


def champion_count(p):
    # placement 只记录前八名,空值即「9 名开外」——所以推不出冠军是正确结论,
    # 不是数据缺失。唯一的真缺口是 IEM Katowice 2019,补 data/major_results.json。
    return sum(1 for m in p.majors if str(m.get("placement")) == "1")


def career_grade(p, ranks, champs):
    """设计稿 §3.2。自上而下互斥,一个人只落一档。"""
    rs = ranks.get(p.page, [])
    if rs and min(rs) <= 5:
        return 5                                    # G5 超巨证据
    if len(rs) >= 2:
        return 4                                    # G4 持续高水平
    if len(rs) == 1 or champs:
        return 3                                    # G3-A 昙花一现 / G3-B 冠军角色球员
    if (p.age() or 99) <= 24 and p.team and p.majors_count >= 3:
        return 3                                    # G3-C 年轻潜力股
    if p.majors_count >= 5:
        return 2                                    # G2 Major 老兵
    return 1


def draft_position(p):
    """设计稿 §9/§10:只保留三职位,IGL > AWPER > RIFLER。

    教练走 played_role(选手期位置)回退——后台编辑器里那一行就是干这个的,
    已经标了 86 人。回退不到的教练返回 None,不进卡池:让一个教练顶着
    RIFLER 的火力模板上场,是买回去必坑的死牌。
    """
    role = p.primary_role
    if role in ("IGL", "AWPer", "Rifler"):
        return {"IGL": "IGL", "AWPer": "AWPER", "Rifler": "RIFLER"}[role]
    for raw in (p.roles or []):                     # 少数教练的 roles 里还留着位置
        low = raw.lower()
        if "igl" in low:
            return "IGL"
        if "awp" in low or "snip" in low:
            return "AWPER"
        if "rifle" in low or low in ("entry", "lurker", "support"):
            return "RIFLER"
    return None


# ------------------------------------------------------------------- 生成
def _rng(page):
    seed = hashlib.blake2b(f"{page}|{CARD_VERSION}".encode("utf-8"),
                           digest_size=8).hexdigest()
    return random.Random(int(seed, 16))


def corrections(p, grade, pos, ranks, champs):
    """设计稿 §20:在基础模板上做有限修正,只定方向不追求还原真实 rating。

    返回四维的增量。原则:Top20 证明火力、Major 证明经验、冠军证明经验与
    (IGL 的)领导、年轻人换的是上限与不稳定。
    """
    rs = ranks.get(p.page, [])
    d = dict.fromkeys(ATTRS, 0.0)

    # Top20 已经参与了 Grade 判定,这里只在同档内拉开,不能重复计一次大的。
    # 关键是**归一化后再乘一个固定档内幅度**:直接按名次线性加分会让 G5
    # (基础火力 89,离上限只剩 10 点)集体顶到 99,档内差异全被削平。
    if rs:
        best, times = min(rs), len(rs)
        raw = (6 - min(best, 6)) * 1.4 + (times - 1) * 1.1     # 0 ~ 约 17
        # IGL 只继承一部分,避免「明星历史 + IGL 模板」叠成六边形怪物(§11.1)
        d["firepower"] += (min(raw, 17.0) / 17.0) * FIRE_SPREAD * (
            0.4 if pos == "IGL" else 1.0)

    # Major 参加次数 → 经验,log 曲线做边际递减:2→5 次意义明显,18→22 次几乎没有
    if p.majors_count:
        d["experience"] += 9 * math.log1p(p.majors_count) / math.log(21)

    # 冠军 → 经验;IGL 额外小幅领导
    if champs:
        d["experience"] += min(champs, 4) * 1.5
        if pos == "IGL":
            d["leadership"] += min(champs, 4) * 1.0

    # §15:年轻人拿到的是特色而不是老人拿惩罚——上限更高,兑现更飘
    age = p.age()
    if age is not None and age <= 22:
        d["firepower"] += 2.5
        d["stability"] -= 5.0
    return d


def build_card(p, grade, pos, ranks, champs, overrides):
    base = TEMPLATE[pos][grade]
    delta = corrections(p, grade, pos, ranks, champs)
    rng = _rng(p.page)
    card = {}
    for i, key in enumerate(ATTRS):
        # 同一张卡的随机只在这里发生一次,种子来自 page + 版本号,可重现
        jitter = rng.uniform(-4, 4) if key == "firepower" else rng.uniform(-3, 3)
        card[key] = max(1, min(99, round(base[i] + delta[key] + jitter)))
    card.update(page=p.page, nickname=p.nickname, position=pos, grade=grade,
                country=p.country, team=p.team, age=p.age(),
                majors=p.majors_count, champions=champs)
    card.update(overrides.get(p.page, {}))          # Algorithm First, Override Last (§21)
    card["overall"] = round(sum(card[k] * w for k, w in zip(ATTRS, WEIGHT[pos])), 1)
    return card


def generate():
    db = PlayerDB()
    ranks = load_top20()
    overrides = (json.loads(OVERRIDE_PATH.read_text(encoding="utf-8"))
                 if OVERRIDE_PATH.exists() else {})
    cards, dropped = [], []
    for p in db.players:
        pos = draft_position(p)
        if pos is None:
            dropped.append(p.nickname)
            continue
        champs = champion_count(p)
        cards.append(build_card(p, career_grade(p, ranks, champs), pos,
                                ranks, champs, overrides))
    return cards, dropped


# ------------------------------------------------------------------- 体检
def audit(cards, dropped):
    print("=" * 72)
    print(f"卡池 {len(cards)} 张 | 排除 {len(dropped)} 人(教练且查不到选手期位置)")
    print("=" * 72)

    grid = collections.Counter((c["grade"], c["position"]) for c in cards)
    cols = ("RIFLER", "AWPER", "IGL")
    print(f"{'':4s}" + "".join(f"{c:>9s}" for c in cols) + f"{'合计':>8s}")
    for g in (5, 4, 3, 2, 1):
        n = sum(grid[(g, c)] for c in cols)
        print(f"G{g}  " + "".join(f"{grid[(g, c)]:9d}" for c in cols) + f"{n:8d}")

    print("\n各档四维分布(中位数)与 overall 区间:")
    print(f"{'':4s}{'火力':>7s}{'领导':>7s}{'经验':>7s}{'稳定':>7s}"
          f"{'overall 最低~中位~最高':>26s}")
    for g in (5, 4, 3, 2, 1):
        grp = [c for c in cards if c["grade"] == g]
        med = [st.median([c[k] for c in grp]) for k in ATTRS]
        ov = sorted(c["overall"] for c in grp)
        print(f"G{g}  " + "".join(f"{m:7.0f}" for m in med)
              + f"{ov[0]:14.1f} ~{st.median(ov):6.1f} ~{ov[-1]:6.1f}")

    print("\n各位置 overall 中位(检查 AWP 是否统治 / IGL 是否被火力压死):")
    for pos in cols:
        grp = [c["overall"] for c in cards if c["position"] == pos]
        print(f"  {pos:7s} n={len(grp):3d}  中位 {st.median(grp):5.1f}  "
              f"最高 {max(grp):5.1f}")

    print("\noverall 前 15(眼睛过一遍,认不出来的名字越多说明公式越可疑):")
    for c in sorted(cards, key=lambda x: -x["overall"])[:15]:
        print(f"  {c['overall']:5.1f}  G{c['grade']} {c['position']:6s} "
              f"{c['nickname']:16s} 火{c['firepower']:3d} 领{c['leadership']:3d} "
              f"经{c['experience']:3d} 稳{c['stability']:3d}")

    g1 = [c["overall"] for c in cards if c["grade"] == 1]
    g5 = [c["overall"] for c in cards if c["grade"] == 5]
    print(f"\n经济锚点:G5 中位 {st.median(g5):.1f} / G1 中位 {st.median(g1):.1f} "
          f"= {st.median(g5) / st.median(g1):.2f} 倍(价格差 5 倍)")
    print("  → 每 1 块钱换到的 overall,决定 Rogue Buff 的定价上限")
    if dropped:
        print(f"\n排除名单({len(dropped)}):{'、'.join(dropped[:20])}"
              + (" …" if len(dropped) > 20 else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="写出 data/draft_cards.json")
    ap.add_argument("--sample", nargs="*", metavar="ID", help="只看这几个人的卡")
    args = ap.parse_args()

    cards, dropped = generate()
    if args.sample:
        want = {s.casefold() for s in args.sample}
        for c in cards:
            if c["nickname"].casefold() in want or c["page"].casefold() in want:
                print(json.dumps(c, ensure_ascii=False, indent=2))
        return
    audit(cards, dropped)
    if args.write:
        OUT_PATH.write_text(json.dumps(
            {"card_version": CARD_VERSION, "count": len(cards), "cards": cards},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n已写入 {OUT_PATH.relative_to(ROOT)}")
    else:
        print("\n(只体检,没写盘。确认没问题后加 --write)")


if __name__ == "__main__":
    main()
