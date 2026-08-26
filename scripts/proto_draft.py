# -*- coding: utf-8 -*-
"""Blind Draft 的命令行原型:不做 UI、不做比赛模拟,只回答「这套选人有没有决策」。

跑法:
    .\.venv\Scripts\python -X utf8 scripts\proto_draft.py           # 盲选一局
    .\.venv\Scripts\python -X utf8 scripts\proto_draft.py --open    # 明牌(直接给档位和四维)
    .\.venv\Scripts\python -X utf8 scripts\proto_draft.py --seed 7  # 复现同一局

v3 的取向:**一切为有趣服务**。v1/v2 八局实测(见 DESIGN_DRAFT_PROTOTYPE.md)证明
「五档选手 + 匿名线索 + 预算」撑不起游戏——价格直接播报档位,于是认出名人就等于
知道答案。v3 把游戏要问的问题从「这是谁」换成「这个资产值不值这个价」:

- **价格与档位分离(Market Roll)。** 每批牌的价格是市场开出来的,不再是 $5..$1
  各一张。一张卡的档位在它标价的上下一档之间浮动:$1 有 25% 其实是 G2,$5 有 25%
  只是 G4。抄底和买贵第一次真实存在,而且它说的是真话——一个 G3 卖 $1,他真的
  就是 G3。**抄底的快感来自价格错了,不需要靠编造「这个人偷偷更强」去买。**
- **Quality Offset 只从真实证据里推。** 同档确实该有好货坏货,但那个差异必须挖
  出来而不是掷出来:HLTV top100 队伍排名、近年是否还在打、Major 前八次数、生涯
  跨度。G2/G3 的证据足够推出真差异;G1 有三分之二什么证据都没有,那批就老实持平
  ——**「查无此人」本身就是可玩的信息:$1 没有球探数据 = 真彩票。**
- **卡面给一个真实四维数字。** 实测整形之后一个火力数字横跨 2~3 档(火力 70 →
  G2 53% / G3 47%),所以它把候选收敛成一个区间而不是一个点,正是设计稿 §7.4 想要
  的「线索应该瞄准区间」。同时它告诉玩家**游戏真正关心什么**。
- **按剩余预算发牌。** 五张牌的标价全部落在你买得起的区间里,后期不再塌缩成
  两张;缺的位置提高权重,只在最后一两个位置才硬保底。
- **剩下的钱有出口。** 每剩 $1 折成全队火力 +3(兑换率是扫出来的中性点)。这是为了让「$5 明星 vs
  $1 选手 + $4 资源」第一次成为真的取舍——在此之前跳过和留钱都是假决策。
- **结算分维度**:选牌准度 / 预算管理 / 阵容契合 / 最大抄底,而不是甩一个名次。
"""
import argparse
import collections
import itertools
import json
import random
import statistics as st
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS_PATH = ROOT / "data" / "draft_cards.json"
PLAYERS_PATH = ROOT / "data" / "players.json"
TOP100_PATH = ROOT / "data" / "hltv_top100.json"
LOG_PATH = ROOT / ".cache" / "proto_draft_runs.jsonl"

BUDGET = 15
SLOTS = 5
TURNS = 7                        # 7 轮机会填 5 个位置 → 自带 2 次跳过
GRADES = (5, 4, 3, 2, 1)
WEIGHTS = {"RIFLER": (0.55, 0.05, 0.20, 0.20),
           "AWPER": (0.45, 0.05, 0.20, 0.30),
           "IGL": (0.25, 0.35, 0.35, 0.05)}   # 与 gen_draft_cards.py §18 一致

# 标价 → 档位的浮动。delta 是「档位 − 标价」:−1 = 买贵了,+1 = 抄到底。
MARKET_ROLL = ((-1, 0.25), (0, 0.50), (1, 0.25))

# 同档实力差的上限。证据越少的档给得越宽,但**只填到证据支持的程度**;
# 一点证据都没有的人 offset 恒为 0(而不是掷一个)。
QUALITY_CAP = {5: 2.0, 4: 3.0, 3: 5.0, 2: 6.0, 1: 7.0}

# 每剩 $1 -> 全队火力 +3。兑换率是扫出来的中性点:R=3.0 时「留钱的最优」与
# 「花满的最优」平均只差 -0.01 分,留钱更优的板面占 57%——正好是硬币两面。
# 低了(R=1.5)留钱恒错,高了(R=4.0)留钱恒对,两种都不是决策。
#
# 只加火力、不让玩家选维度:火力在基础分里权重 0.40,其余三维都是 0.20,
# 「砸哪一维」永远是火力——那是个假决策,而假决策正是这一版要拆掉的东西。
SAVE_RATE = 3.0
SAVE_ATTR = "firepower"

MONEY_ATTRS = ("firepower", "stability", "experience", "leadership")
ATTR_CN = {"firepower": "火力", "stability": "稳定",
           "experience": "经验", "leadership": "领导"}

RULES = """\
算分(全部公开,没有隐藏项):

  火力   最高 x0.35 + 次高 x0.25 + 其余三人均值 x0.40   明星主导,不是求平均
  领导   只算队里最强的那个 IGL x0.70 + 其余四人 x0.30;没有 IGL 则整项 x0.60
  经验   五人均值
  稳定   五人均值(同时决定发挥波动幅度,不只是加分)

  基础分 = 火力 x0.40 + 领导 x0.20 + 经验 x0.20 + 稳定 x0.20
           没有 AWP 再 -4

  默契   真实队友(同一届 Major 同队)   每对 +2,同队 >=5 届再 +1
         同国籍                        每多一个同胞 +1.5
         同代    年龄差 <=5 -> +2   >=12 -> -2
         两个指挥                      -3(抢话)

  余钱   每剩 $1 -> 全队火力 +3(赛后自动折算)

  总分 = 基础分 + 默契 + 余钱   单场发挥 ~ 总分 +- (100 - 稳定) / 4

**标价不等于档位。** 一张卡的真实档位在标价的上下一档之间:$1 有 25% 其实是 G2,
$5 有 25% 只是 G4。卡面给你一个真实的四维数字 —— 用它去判断这张牌值不值这个价。
"""


# ----------------------------------------------------------------- 基础

def overall(c):
    wf, wl, we, ws = WEIGHTS[c["position"]]
    return (c["firepower"] * wf + c["leadership"] * wl
            + c["experience"] * we + c["stability"] * ws)


def _bump(card, delta):
    """四维同加 delta —— 位置权重和为 1,等于 overall 加 delta。"""
    for k in MONEY_ATTRS:
        card[k] = max(1, min(99, card[k] + delta))


# ----------------------------------------------------------------- 证据 -> Quality

def load_evidence():
    """page -> (原始证据分, 有没有证据)。全部取自仓库里已有的真实数据。"""
    ranks = {t: i + 1 for i, t in
             enumerate(json.loads(TOP100_PATH.read_text(encoding="utf-8"))["teams"])}
    db = json.loads(PLAYERS_PATH.read_text(encoding="utf-8"))["players"]
    out = {}
    for p in db:
        majors = p.get("majors", [])
        top8 = sum(1 for m in majors if m.get("placement"))
        first, last = p.get("first_major_year"), p.get("last_major_year")
        span = (last - first) if (first and last) else 0
        rank = ranks.get(p.get("team", ""))

        signals, have = [], False
        if rank:                       # 现在在多强的队里
            signals.append(1.0 - (rank - 1) / 100.0); have = True
        if top8:                       # 进过几次 Major 前八
            signals.append(min(1.0, top8 / 4.0)); have = True
        if last and last >= 2024:      # 近年还在打
            signals.append(min(1.0, (last - 2023) / 3.0)); have = True
        if span >= 2:                  # 在这行活了多久
            signals.append(min(1.0, span / 8.0)); have = True
        out[p["page"]] = (st.mean(signals) if signals else 0.0, have)
    return out


def apply_quality(cards, evidence):
    """同档内按真实证据拉开实力差,证据推不出来的人保持在基线上。

    做法:在同一档里,对**有证据的那批人**做 z 分数,映射到 +-QUALITY_CAP[档];
    没有任何证据的人 offset 恒为 0,并打上 unknown 标记(卡面显示「无球探数据」)。
    """
    for grade, group in itertools.groupby(sorted(cards, key=lambda c: c["grade"]),
                                          key=lambda c: c["grade"]):
        group = list(group)
        scored = [(c,) + evidence.get(c["page"], (0.0, False)) for c in group]
        known = [s for _, s, have in scored if have]
        mu = st.mean(known) if known else 0.0
        sd = (st.pstdev(known) or 1.0) if len(known) > 1 else 1.0
        cap = QUALITY_CAP[grade]
        for c, raw, have in scored:
            if not have:
                c["quality"] = 0.0
                c["unknown"] = True
                continue
            z = max(-2.0, min(2.0, (raw - mu) / sd))
            q = z / 2.0 * cap
            # 顶到 99 的卡就分不出 donk 和 ZywOo 了,所以按余量收一下再加
            room = min(99 - c[k] for k in MONEY_ATTRS)
            floor = min(c[k] for k in MONEY_ATTRS) - 1
            c["quality"] = round(max(-floor, min(room, q)), 1)
            c["unknown"] = False
            _bump(c, c["quality"])


# ----------------------------------------------------------------- 形状

def shape_cards(cards):
    """零和整形:同档内拉开形状,不拉开强弱(强弱交给上面的 Quality)。

    形状取自真实履历而不是随机:年轻 -> 火力高/稳定低(打得凶但飘),
    Major 与冠军多 -> 经验高/火力让一点(老兵)。整完之后给全卡加一个常数,
    把加权 overall 拉回整形前的值。
    """
    for grade, group in itertools.groupby(sorted(cards, key=lambda c: c["grade"]),
                                          key=lambda c: c["grade"]):
        group = list(group)
        ages = [c["age"] for c in group if c["age"]]
        mu_a, sd_a = st.mean(ages), (st.pstdev(ages) or 1)
        mjs = [c["majors"] for c in group]
        mu_m, sd_m = st.mean(mjs), (st.pstdev(mjs) or 1)

        # 第一遍:算出每张卡的形变量 g。整完要加的那个常数(把加权 overall 拉回
        # 原值)本身也和形变量成正比,所以整条形变对缩放因子 s 是线性的:
        #     final_k = base_k + s * g_k
        shifts = {}
        for c in group:
            clamp = lambda v: max(-2.0, min(2.0, v))
            aggression = clamp(-((c["age"] or mu_a) - mu_a) / sd_a)
            veterancy = clamp((c["majors"] - mu_m) / sd_m + 0.5 * min(c["champions"], 4))

            d = {"firepower": 6.0 * aggression - 3.0 * veterancy,
                 "stability": -5.0 * aggression + 2.0 * veterancy,
                 "experience": 6.0 * veterancy - 2.0 * aggression,
                 "leadership": 0.0}
            wf, wl, we, ws = WEIGHTS[c["position"]]
            w = {"firepower": wf, "leadership": wl, "experience": we, "stability": ws}
            fix_unit = -sum(d[k] * w[k] for k in d)
            shifts[id(c)] = {k: d[k] + fix_unit for k in d}

        # 第二遍:全档共用一个 s。**不能各算各的**——那样几张顶级火力卡会各自
        # "正好"落到 99,还是分不开;顶格等于让 donk 和 ZywOo 变成同一张卡,
        # 而那正是 v6 花力气消掉的东西。统一缩放则档内的相对差距完整保留,
        # 最多只有最紧的那一张碰到天花板。
        s = 1.0
        for c in group:
            for k, gk in shifts[id(c)].items():
                if gk > 1e-9:
                    s = min(s, (99 - c[k]) / gk)
                elif gk < -1e-9:
                    s = min(s, (c[k] - 1) / -gk)
        s = max(0.0, s)

        for c in group:
            for k in MONEY_ATTRS:
                c[k] = max(1, min(99, round(c[k] + s * shifts[id(c)][k])))
            c["overall"] = round(overall(c), 1)


def load_cards():
    cards = [dict(c) for c in
             json.loads(CARDS_PATH.read_text(encoding="utf-8"))["cards"]
             if c.get("position")]
    apply_quality(cards, load_evidence())
    shape_cards(cards)
    return cards


def load_rosters():
    """page -> {(赛事, 战队)},用来判定两个人是不是真的同过队。

    players.json 的 majors[] 每一条都带当届的 team,不只是冠军,所以这张图覆盖
    全库 645/648 个人(含 G1 的 306 个),便宜卡也吃得到默契。
    """
    db = json.loads(PLAYERS_PATH.read_text(encoding="utf-8"))["players"]
    out = {}
    for p in db:
        seen = {(m["event"], m["team"]) for m in p.get("majors", []) if m.get("team")}
        if seen:
            out[p["page"]] = seen
    return out


def mate_index(rosters):
    """page -> {真实队友的 page},预先算好,发牌时要按它加权。"""
    pages = list(rosters)
    idx = collections.defaultdict(set)
    for a, b in itertools.combinations(pages, 2):
        if rosters[a] & rosters[b]:
            idx[a].add(b); idx[b].add(a)
    return idx


# ----------------------------------------------------------------- 卡面

# 卡面给哪一维,按位置加权:只展示这个位置真正值得观察的属性。
# (非 IGL 的 leadership 在生成器里是常数模板,展示了等于死线索,所以不发。)
ATTR_WEIGHT = {
    "RIFLER": (("firepower", 45), ("stability", 30), ("experience", 25)),
    "AWPER": (("firepower", 40), ("stability", 35), ("experience", 25)),
    "IGL": (("leadership", 45), ("experience", 30), ("firepower", 25)),
}


def _pick(page, salt, options):
    """按权重挑一项,同一个人永远挑到同一项(跨进程稳定)。"""
    h = zlib.crc32(f"{page}|{salt}".encode("utf-8")) % sum(w for _, w in options)
    for opt, w in options:
        if h < w:
            return opt
        h -= w
    return options[-1][0]


def scout_attr(card):
    return _pick(card["page"], "attr", ATTR_WEIGHT[card["position"]])


def identity_clue(card):
    """帮助认人的那一条:俱乐部 / Major 次数 / 年龄,三选一,同一个人固定。"""
    opts = []
    if card["team"]:
        opts.append(("club", 34))
    if card["majors"]:
        opts.append(("majors", 33))
    if card["age"]:
        opts.append(("age", 33))
    if not opts:
        return "无公开资料"
    kind = _pick(card["page"], "id", tuple(opts))
    if kind == "club":
        return card["team"]
    if kind == "majors":
        return f"Major x{card['majors']}"
    return f"{card['age']} 岁"


def face(card, open_mode):
    k = scout_attr(card)
    bits = [f"{ATTR_CN[k]} {card[k]}", card["country"], identity_clue(card)]
    if card.get("unknown"):
        bits.append("无球探数据")
    if open_mode:
        bits.append(f"[G{card['grade']} 火{card['firepower']} 领{card['leadership']} "
                    f"经{card['experience']} 稳{card['stability']} q{card['quality']:+.1f}]")
    return f"${card['price']}  {card['position']:<6}  " + "  ·  ".join(bits)


# ----------------------------------------------------------------- 算分

def pair_bonus(a, b, rosters):
    shared = rosters.get(a["page"], set()) & rosters.get(b["page"], set())
    if not shared:
        return 0.0, None
    team = collections.Counter(t for _, t in shared).most_common(1)[0][0]
    return 2.0 + (1.0 if len(shared) >= 5 else 0.0), (len(shared), team)


def chemistry(roster, rosters):
    notes, total = [], 0.0

    for a, b in itertools.combinations(roster, 2):
        bonus, info = pair_bonus(a, b, rosters)
        if bonus:
            n, team = info
            total += bonus
            notes.append(f"队友 {a['nickname']} + {b['nickname']}  同队 {n} 届 Major"
                         f"({team})  +{bonus:.1f}")

    for country, n in collections.Counter(c["country"] for c in roster).items():
        if n >= 2:
            total += 1.5 * (n - 1)
            notes.append(f"同国籍 {country} x{n}  +{1.5 * (n - 1):.1f}")

    ages = [c["age"] for c in roster if c["age"]]
    if len(ages) >= 2:
        spread = max(ages) - min(ages)
        if spread <= 5:
            total += 2.0
            notes.append(f"同代  年龄差 {spread} 岁  +2.0")
        elif spread >= 12:
            total -= 2.0
            notes.append(f"跨代拼凑  年龄差 {spread} 岁  -2.0")

    n_igl = sum(1 for c in roster if c["position"] == "IGL")
    if n_igl >= 2:
        total -= 3.0 * (n_igl - 1)
        notes.append(f"{n_igl} 个指挥抢话  -{3.0 * (n_igl - 1):.1f}")

    return total, notes


def score(roster, rosters, money=0):
    """money = 剩余预算,按固定兑换率折成全队火力。"""
    boost = money * SAVE_RATE
    get = lambda c, k: c[k] + (boost if k == SAVE_ATTR else 0.0)

    f = sorted((get(c, "firepower") for c in roster), reverse=True)
    fire = f[0] * .35 + f[1] * .25 + st.mean(f[2:]) * .40

    igls = [c for c in roster if c["position"] == "IGL"]
    if igls:
        top = max(igls, key=lambda c: c["leadership"])
        # 只有最强的那个 IGL 算指挥;其余四人按步枪的领导力算,多塞指挥不是加成
        others = [get(c, "leadership") if c["position"] != "IGL" else 25
                  for c in roster if c is not top]
        lead = get(top, "leadership") * .70 + st.mean(others) * .30
    else:
        lead = st.mean(get(c, "leadership") for c in roster) * .60

    exp = st.mean(get(c, "experience") for c in roster)
    stab = st.mean(get(c, "stability") for c in roster)

    base = fire * .40 + lead * .20 + exp * .20 + stab * .20
    no_awp = not any(c["position"] == "AWPER" for c in roster)
    if no_awp:
        base -= 4.0

    chem, notes = chemistry(roster, rosters)
    return {"fire": fire, "lead": lead, "exp": exp, "stab": stab, "no_awp": no_awp,
            "base": base, "chem": chem, "notes": notes, "money": money,
            "total": base + chem, "swing": (100 - stab) / 4}


# ----------------------------------------------------------------- 发牌

FREE_AGENT_WEIGHT = {5: 1.0, 4: 0.8, 3: 0.35, 2: 0.25, 1: 0.20}
VETERAN_WEIGHT = {5: 1.0, 4: 0.9, 3: 0.50, 2: 0.40, 1: 0.35}
NEED_BOOST = 2.5        # 还缺的位置
MATE_BOOST = 2.0        # 已有队员的真实队友(实测把出现率从 39% 抬到 57%)


def draw_weight(c):
    """出场权重:只改出场率,不改任何卡的数值,人也都还在库里。

    没队伍的人和大龄选手在低档大幅降权(全库 52% 没队、44% 在 30 岁以上,不压的话
    板面永远是十年前的无名老哥);$5/$4 不打折——那一档没队的是 f0rest、olofmeister、
    dupreeh,恰恰最好认。<=24 岁的自由身只打一半折扣:年轻没队的可能正是厉害人。
    """
    g, age = c["grade"], c["age"]
    w = 1.0
    if not c["team"]:
        w *= FREE_AGENT_WEIGHT[g]
        if (age or 99) <= 24:
            w = (w + 1.0) / 2
    if (age or 0) >= 30:
        w *= VETERAN_WEIGHT[g]
    return w


class Dealer:
    def __init__(self, cards, rng, mates):
        self.rng, self.mates = rng, mates
        self.pool = collections.defaultdict(list)
        for c in cards:
            self.pool[c["grade"]].append(c)

    def _draw(self, grade, need, want, position=None):
        """从这一档里抽一张;抽干了就往邻近档退。"""
        for g in sorted(GRADES, key=lambda x: abs(x - grade)):
            cand = [c for c in self.pool[g]
                    if position is None or c["position"] == position]
            if not cand:
                continue
            w = [draw_weight(c)
                 * (NEED_BOOST if c["position"] in need else 1.0)
                 * (MATE_BOOST if c["page"] in want else 1.0)
                 for c in cand]
            pick = self.rng.choices(cand, weights=w, k=1)[0]
            self.pool[pick["grade"]].remove(pick)
            return pick
        return None

    def board(self, left, slots_left, owned):
        """五张牌,标价全部落在买得起的区间里;缺的位置提权,最后才硬保底。"""
        # 标价既要买得起,又不能越出 $1-$5 这套刻度
        max_price = max(1, min(5, left - (slots_left - 1)))
        need = {p for p in ("AWPER", "IGL")
                if not any(c["position"] == p for c in owned)}
        want = {m for c in owned for m in self.mates.get(c["page"], ())}

        # 标价:一张顶格的,其余在 [1, max_price] 里随机 —— 价格组合本身就是抽卡
        prices = [max_price] + [self.rng.randint(1, max_price) for _ in range(4)]
        self.rng.shuffle(prices)

        board = []
        for i, p in enumerate(prices):
            delta = self.rng.choices([d for d, _ in MARKET_ROLL],
                                     weights=[w for _, w in MARKET_ROLL], k=1)[0]
            grade = max(1, min(5, p + delta))
            # 只剩最后一两个位置还缺 AWP/IGL 时,最后一张硬保底
            force = None
            if need and slots_left <= 2 and i == len(prices) - 1 \
                    and not any(c["position"] in need for c in board):
                force = sorted(need)[0]
            c = self._draw(grade, need, want, force)
            if c is not None:
                board.append(dict(c, price=p))
        return board


def affordable(price, left, slots_left):
    return price <= left - (slots_left - 1)


# ----------------------------------------------------------------- 一局

def play(dealer, open_mode):
    picked, boards, left, hesitated, passed = [], [], BUDGET, [], []

    for turn in range(1, TURNS + 1):
        slots_left = SLOTS - len(picked)
        if slots_left == 0:
            break
        turns_left = TURNS - turn + 1
        can_pass = turns_left > slots_left

        board = dealer.board(left, slots_left, picked)
        boards.append(board)
        print(f"\n-- 第 {turn}/{TURNS} 轮    预算 ${left}    还要选 {slots_left} 人"
              f"    {'还能跳过 %d 次' % (turns_left - slots_left) if can_pass else '不能再跳过了'} --")
        if picked:
            print("   已有:", "  ".join(f"${c['price']} {c['position']}({c['country']})"
                                        for c in picked))
            have = {c["position"] for c in picked}
            missing = [p for p in ("IGL", "AWPER") if p not in have]
            if missing:
                print("   还缺:", " / ".join(missing),
                      " (缺 AWP 扣 4 分,缺 IGL 领导力打六折)")

        for i, c in enumerate(board, 1):
            print(f"  {i}) {face(c, open_mode)}")
        if can_pass:
            print("  s) 跳过这轮,换一批新牌")

        while True:
            raw = input("选哪张? (编号 / s 跳过,加 ? 表示这轮你犹豫过,如 3?) > ").strip()
            hes = raw.endswith("?")
            raw = raw.rstrip("?").strip().lower()
            if raw == "s" and can_pass:
                passed.append(turn); card = None; break
            if raw.isdigit() and 1 <= int(raw) <= len(board):
                card = board[int(raw) - 1]; break
            print("   无效,再来一次。")

        if hes:
            hesitated.append(turn)
        if card is not None:
            picked.append(card)
            left -= card["price"]

    return picked, boards, left, hesitated, passed


# ----------------------------------------------------------------- 复盘

def all_lineups(boards, rosters):
    """穷举:从看过的每批牌里挑 5 批、每批一张,预算合法,余钱按最优维度折算。"""
    out = []
    for chosen in itertools.combinations(range(len(boards)), SLOTS):
        for combo in itertools.product(*(boards[i] for i in chosen)):
            spend = sum(c["price"] for c in combo)
            if spend <= BUDGET:
                out.append((score(combo, rosters, BUDGET - spend)["total"],
                            combo, spend))
    out.sort(key=lambda x: -x[0])
    return out


def tier_gap(c):
    return c["grade"] - c["price"]


def reveal(picked, boards, left, rosters, passed):
    print("\n" + "=" * 78)
    print("REVEAL")
    print("=" * 78)

    for c in picked:
        g = tier_gap(c)
        tag = f"抄底 +{g} 档" if g > 0 else (f"买贵 {g} 档" if g < 0 else "标价合理")
        print(f"  ${c['price']} {c['position']:<6} {c['nickname']:<13} {c['country']:<12}"
              f" {(c['team'] or '自由身/退役'):<20} G{c['grade']} "
              f"火{c['firepower']:<3} 领{c['leadership']:<3} 经{c['experience']:<3} "
              f"稳{c['stability']:<3} {tag}")

    s = score(picked, rosters, left)
    if left:
        print(f"\n  没花完的 ${left} 折成全队火力 +{left * SAVE_RATE:.0f}")

    print(f"\n  火力 {s['fire']:.1f}   领导 {s['lead']:.1f}   经验 {s['exp']:.1f}"
          f"   稳定 {s['stab']:.1f}   基础分 {s['base']:.1f}")
    if s["no_awp"]:
        print("    (没有 AWP,基础分已扣 4)")
    print("  默契:" + ("" if s["notes"] else " 无 —— 五个人互相没打过、也不同国"))
    for n in s["notes"]:
        print("    " + n)
    print(f"  默契合计 {s['chem']:+.1f}")
    print(f"\n  总分 {s['total']:.1f}   单场发挥 {s['total'] - s['swing']:.1f} ~ "
          f"{s['total'] + s['swing']:.1f}")

    ranked = all_lineups(boards, rosters)
    totals = [t for t, _, _ in ranked]
    mine = s["total"]
    better = sum(1 for t in totals if t > mine + 1e-9)

    regrets = []
    print("\n  逐轮后悔(其余四人不动,只换这一张能到多少分):")
    for k, c in enumerate(picked):
        bi = next(i for i, b in enumerate(boards) if c in b)
        alts = []
        for alt in boards[bi]:
            combo = list(picked); combo[k] = alt
            spend = sum(x["price"] for x in combo)
            if spend <= BUDGET:
                alts.append((score(combo, rosters, BUDGET - spend)["total"], alt))
        alts.sort(key=lambda x: -x[0])
        regret = alts[0][0] - mine
        regrets.append(regret)
        tail = ("这轮没选错" if regret < .05 else
                "更该拿 $%d %s %s" % (alts[0][1]["price"], alts[0][1]["position"],
                                      alts[0][1]["nickname"]))
        print(f"    ${c['price']} {c['position']:<6} {c['nickname']:<12} "
              f"后悔 {regret:5.1f}   {tail}")

    spend_me = BUDGET - left
    same_spend = [t for t, _, sp in ranked if sp == spend_me] or [mine]
    best_steal = max(picked, key=tier_gap)
    missed = max((c for b in boards for c in b if c not in picked),
                 key=tier_gap, default=None)

    print("\n  " + "-" * 74)
    print(f"  选牌准度   逐轮后悔合计 {sum(regrets):5.1f}   "
          f"(0 = 每一轮在当时的牌里都选对了)")
    print(f"  预算管理   你花了 ${spend_me};同样花 ${spend_me} 的阵容最高 "
          f"{max(same_spend):.1f},你 {mine:.1f}")
    print(f"  阵容契合   默契 {s['chem']:+.1f}"
          f"{'  (没有 AWP,-4)' if s['no_awp'] else ''}")
    print(f"  最大抄底   ${best_steal['price']} 买到 G{best_steal['grade']} "
          f"{best_steal['nickname']} ({tier_gap(best_steal):+d} 档)")
    if missed is not None and tier_gap(missed) > tier_gap(best_steal):
        print(f"  错过的     ${missed['price']} 的 G{missed['grade']} "
              f"{missed['nickname']} ({tier_gap(missed):+d} 档) 你没拿")
    print("  " + "-" * 74)
    print(f"  同样这 {len(boards)} 批牌,合法阵容共 {len(ranked)} 套")
    print(f"    你           {mine:6.1f}   第 {better + 1} 名"
          f"(前 {100 * (better + 1) / len(ranked):.0f}%)")
    print(f"    最优         {totals[0]:6.1f}   "
          f"{'  '.join('$%d %s' % (c['price'], c['nickname']) for c in ranked[0][1])}")
    print(f"    随便瞎点均值 {st.mean(totals):6.1f}   标准差 {st.pstdev(totals):.1f}")
    if passed:
        print(f"    跳过了第 {passed} 轮;穷举把跳过的那几批也算进去了")
    return s, ranked, better, regrets


# ----------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--open", action="store_true", dest="open_mode",
                    help="明牌:卡面直接给档位和四维")
    ap.add_argument("--no-log", action="store_true")
    args = ap.parse_args()

    seed = args.seed if args.seed is not None else random.randrange(1 << 30)
    rng = random.Random(seed)
    cards, rosters = load_cards(), load_rosters()
    dealer = Dealer(cards, rng, mate_index(rosters))

    print("=" * 78)
    print(f"Blind Draft 原型 v3    预算 ${BUDGET} / {SLOTS} 人 / {TURNS} 轮机会    "
          f"{'明牌' if args.open_mode else '盲选'}    seed={seed}")
    print("=" * 78)
    print(RULES)

    picked, boards, left, hesitated, passed = play(dealer, args.open_mode)
    s, ranked, better, regrets = reveal(picked, boards, left, rosters, passed)

    extra = input("\n这局哪里最难受 / 最有意思?(一句话,可留空) > ").strip()

    if not args.no_log:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "v": 3, "seed": seed, "open": args.open_mode,
                "picks": [{"n": c["nickname"], "price": c["price"], "grade": c["grade"],
                           "p": c["position"], "q": c["quality"]} for c in picked],
                "passed": passed, "hesitated": hesitated, "spent": BUDGET - left,
                "total": round(s["total"], 2),
                "chem": round(s["chem"], 2), "regret_sum": round(sum(regrets), 2),
                "rank": better + 1, "of": len(ranked),
                "best": round(ranked[0][0], 2),
                "mean": round(st.mean(t for t, _, _ in ranked), 2),
                "comment": extra,
            }, ensure_ascii=False) + "\n")
        print(f"\n已记到 {LOG_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
