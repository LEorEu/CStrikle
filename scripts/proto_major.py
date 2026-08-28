# -*- coding: utf-8 -*-
"""Blind Draft — Major 入场层原型(Match Engine v0.1 的第一步)

这一步**不含任何比赛计算**,只回答三个问题:

    1. 这届 Major 的 32 支真实队,按我们自己的卡库排下来是什么样?
    2. 玩家抽出来的这五个人插进去排第几、挤掉了谁、从哪个 Stage 进场?
    3. 进场那个 Stage 的 16 个种子和首轮 8 场对阵是什么?

对应设计稿 docs/blind-draft/比赛引擎_v0.1.md 的 §1~§3、§8、§9。
之所以先做这一层:它一个随机数都不需要,对错肉眼可判;而 Swiss 循环和胜率
函数(§34)全都建在它上面。

不改卡库、不写 data/,只读 data/players.json 和 proto_draft 的评分函数。
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proto_draft as P

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "players.json")

DEFAULT_EVENT = "IEM Cologne 2026"

# §5:真实队的裸默契是 19.5~32,玩家临时队只有 0~5。不封顶的话 Entry Rating
# 就只在回答「你是不是一支真队」。实测 CAP=8 时 32 支真队全部顶格,所以它调的
# 其实是「草台班子税」有多重,而不是真队之间谁更磨合(§44.1)。
CHEM_CAP = 8.0

FIELD_SIZE = 32          # 一届 Major 的席位数
STAGE_SIZE = 16          # 每个 Swiss Stage 的队数


# ------------------------------------------------------------------ 真实赛场

def load_major(event):
    """读一届 Major 的参赛队 -> {队名: [5 张卡]}。缺卡的人会被单独报出来。"""
    cards = {c["page"]: c for c in P.load_cards()}
    teams = collections.defaultdict(list)
    missing = collections.defaultdict(list)
    for p in json.load(open(DATA, encoding="utf-8"))["players"]:
        for m in p.get("majors", []):
            if m["event"] != event:
                continue
            if p["page"] in cards:
                teams[m["team"]].append(cards[p["page"]])
            else:
                missing[m["team"]].append(p["page"])
    return dict(teams), dict(missing)


def list_events(top=12):
    """按年份列最近的几届,方便 --event 挑一个真的存在的。"""
    seen = collections.Counter()
    year = {}
    for p in json.load(open(DATA, encoding="utf-8"))["players"]:
        for m in p.get("majors", []):
            seen[m["event"]] += 1
            year[m["event"]] = m.get("year", 0)
    rows = sorted(seen.items(), key=lambda kv: (-year.get(kv[0], 0), kv[0]))
    return rows[:top]


# ------------------------------------------------------------------ Entry Rating

def entry_rating(roster, rosters, chem_cap=CHEM_CAP):
    """§4:赛前评价。基础分 + 封顶后的先天默契,不含 Form / 高压 / Rogue。

    money 固定传 0 是有意的——省下的预算是 Rogue Point 的替身,而 §4 明说
    Rogue Buff 不参与 Entry Rating,不能让人靠留钱买到一张 Stage 3 邀请函。
    """
    s = P.score(roster, rosters, 0)
    chem = min(s["chem"], chem_cap)
    return {"base": s["base"], "chem_raw": s["chem"], "chem": chem,
            "entry": s["base"] + chem, "notes": s["notes"]}


class Entry(object):
    """赛场上的一支队。is_player 决定它在表里怎么显示。"""

    def __init__(self, name, roster, rating, is_player=False):
        self.name = name
        self.roster = roster
        self.rating = rating
        self.is_player = is_player

    @property
    def entry(self):
        return self.rating["entry"]

    def __repr__(self):
        return "<Entry %s %.1f>" % (self.name, self.entry)


def real_field(event, rosters, chem_cap=CHEM_CAP):
    """32 支真实队,按 Entry Rating 从高到低。"""
    teams, missing = load_major(event)
    full = {t: r for t, r in teams.items() if len(r) == 5}
    field = [Entry(t, r, entry_rating(r, rosters, chem_cap))
             for t, r in full.items()]
    field.sort(key=lambda e: -e.entry)
    dropped = {t: len(r) for t, r in teams.items() if len(r) != 5}
    return field, dropped, missing


# ------------------------------------------------------------------ 玩家插入

def insert_player(field, player):
    """§3.1:玩家按 Entry Rating 插进去,**原本站在那个名次上的真实队被挤出**。

    不是踢掉最弱的那支——踢掉的是你刚好越过去的那一支,这样「你挤掉了 XXX」
    才是一句有名字的话。玩家排到第 33(比全场最弱还弱)时返回 rank=33、
    displaced=None,那就是 RUN END — Failed to qualify。
    """
    rank = sum(1 for e in field if e.entry > player.entry) + 1
    if rank > FIELD_SIZE:
        return FIELD_SIZE + 1, None, list(field)
    out = field[rank - 1]
    new = list(field)
    new[rank - 1] = player
    return rank, out, new


def stage_of(rank):
    """§3.2"""
    if rank <= 8:
        return 3
    if rank <= 16:
        return 2
    if rank <= FIELD_SIZE:
        return 1
    return 0                                    # 未能晋级


# ------------------------------------------------------------------ 种子与首轮

def stage_seeds(field, stage):
    """§8:某个 Stage 开赛时手上已知的种子。

    Stage 1 是完整的 16 支(全场第 17~32);Stage 2 / 3 开赛前只知道 8 支直邀
    (种子 1~8),另外 8 个位置要等上一个 Stage 打完才填得上——这一步还没有
    比赛引擎,所以那 8 个位置是空的,这正是下一步要补的东西。
    """
    if stage == 1:
        return field[16:32], []
    if stage == 2:
        return field[8:16], [None] * 8
    if stage == 3:
        return field[0:8], [None] * 8
    return [], []


def round1(direct, advancers):
    """§9:Seed i 打 Seed i+8。advancers 里的 None 表示待定。"""
    top = list(direct)
    bottom = list(advancers) if advancers else []
    if not bottom:                              # Stage 1:16 支一起排种子
        top, bottom = direct[:8], direct[8:]
    return [(i + 1, top[i], i + 9, bottom[i]) for i in range(8)]


# ------------------------------------------------------------------ 一个陪跑的玩家

def bot_draft(seed, cards, rosters, mates):
    """一个按性价比买、先补狙和指挥的普通打法,用来生成一支玩家队。

    它不是 AI 对手——AI 对手用的是真实五人阵容(§29)。它只是让这个脚本
    不必等网页版就能端到端跑一遍。
    """
    import random
    rng = random.Random(seed)
    dealer = P.Dealer(cards, rng, mates)
    left, slots, owned = P.BUDGET, P.SLOTS, []
    for _ in range(P.TURNS):
        if slots == 0:
            break
        board = dealer.board(left, slots, owned)
        aff = [c for c in board if P.affordable(c["price"], left, slots)]
        if not aff:
            continue
        need = {p for p in ("AWPER", "IGL")
                if not any(x["position"] == p for x in owned)}
        pick = max(aff, key=lambda c: (2.0 if c["position"] in need else 1.0)
                   * ((c["scout"][0] + c["scout"][1]) / 2) / (c["price"] + 0.5))
        owned.append(pick)
        left -= pick["price"]
        slots -= 1
    return owned, left


# ------------------------------------------------------------------ 输出

def name_of(entry):
    if entry is None:
        return "(待上一 Stage 决出)"
    return ("*** " + entry.name + " ***") if entry.is_player else entry.name


def print_field(field, player_rank, displaced, event, chem_cap):
    print("=" * 70)
    print("%s  —  Projected Seeding(模拟种子,不是历史真实 VRS)" % event)
    print("Entry Rating = 基础分 + min(先天默契, %.1f)" % chem_cap)
    print("=" * 70)
    last = None
    for i, e in enumerate(field, 1):
        stage = stage_of(i)
        if stage != last:
            print("  ---- Stage %d ----" % stage)
            last = stage
        mark = ">>>" if e.is_player else "   "
        print("%s %2d  %-22s  %5.1f   基础 %5.1f  默契 %4.1f (裸 %4.1f)"
              % (mark, i, e.name, e.entry, e.rating["base"],
                 e.rating["chem"], e.rating["chem_raw"]))
    print()
    if player_rank > FIELD_SIZE:
        print("RUN END — Failed to qualify(第 %d,连最后一个席位都没挤进去)"
              % player_rank)
    elif displaced is not None:
        print("你以 Projected Seed #%d 拿到席位,挤掉了 %s(%.1f)。"
              % (player_rank, displaced.name, displaced.entry))
        print("起始位置:Stage %d" % stage_of(player_rank))


def print_round1(field, stage):
    direct, adv = stage_seeds(field, stage)
    print()
    print("-" * 70)
    print("Stage %d 首轮对阵" % stage)
    print("-" * 70)
    if stage in (2, 3):
        print("(直邀 8 支是种子 1-8;种子 9-16 由 Stage %d 晋级填入)" % (stage - 1))
    for a, ea, b, eb in round1(direct, adv):
        print("  Seed %2d  %-22s  vs  Seed %2d  %s"
              % (a, name_of(ea), b, name_of(eb)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", default=DEFAULT_EVENT)
    ap.add_argument("--seed", type=int, default=None,
                    help="给一个种子就顺便抽一支玩家队插进去")
    ap.add_argument("--cap", type=float, default=CHEM_CAP)
    ap.add_argument("--events", action="store_true", help="列出可用的 Major")
    args = ap.parse_args()

    if args.events:
        for ev, n in list_events():
            print("%-34s %3d 人次" % (ev, n))
        return

    rosters = P.load_rosters()
    field, dropped, missing = real_field(args.event, rosters, args.cap)
    if not field:
        print("没找到 %s 的完整参赛队。用 --events 看有哪些。" % args.event)
        return
    if dropped:
        print("跳过(不是 5 人): %s" % dropped)
    if missing:
        print("在 Major 名单里但卡库没有: %s" % dict(list(missing.items())[:5]))

    rank, displaced = FIELD_SIZE + 1, None
    if args.seed is not None:
        cards = P.load_cards()
        mates = P.mate_index(rosters)
        roster, left = bot_draft(args.seed, cards, rosters, mates)
        if len(roster) < P.SLOTS:
            print("这局没凑齐 5 个人,换一个 --seed")
            return
        me = Entry("YOUR TEAM", roster, entry_rating(roster, rosters, args.cap),
                   is_player=True)
        print("你的五个人(seed %d,剩 $%d):" % (args.seed, left))
        for c in roster:
            print("   %-7s %-14s %-12s G%d" % (c["position"], c["nickname"],
                                               c["country"], c["grade"]))
        print()
        rank, displaced, field = insert_player(field, me)

    print_field(field, rank, displaced, args.event, args.cap)
    if 1 <= stage_of(rank) <= 3:
        print_round1(field, stage_of(rank))


if __name__ == "__main__":
    main()
