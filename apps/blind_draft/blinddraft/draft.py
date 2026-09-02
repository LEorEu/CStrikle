# -*- coding: utf-8 -*-
"""Blind Draft 的命令行原型:不做 UI、不做比赛模拟,只回答「这套选人有没有决策」。

跑法:
    .\.venv\Scripts\python -X utf8 -m blinddraft.draft           # 盲选一局
    .\.venv\Scripts\python -X utf8 -m blinddraft.draft --open    # 明牌(直接给档位和四维)
    .\.venv\Scripts\python -X utf8 -m blinddraft.draft --seed 7  # 复现同一局

取向:**一切为有趣服务**。v1/v2 八局实测(见 docs/blind-draft/原型实测记录.md)证明
「五档选手 + 匿名线索 + 预算」撑不起游戏——价格直接播报了档位,于是认出名人就等于
知道答案。这一版把游戏要问的问题从「这是谁」换成「这个资产值不值这个价」。

**下面分成两类,不要混着读。**

正式机制(要进最终游戏的):

- **选手卡是固定的。** 四维和档位取自已提交的 `data/blind_draft/draft_cards.json`(v6),
  按生涯代表版本评价,不随局变化。原型**不再对卡做任何加工**。
- **市场会错价(Market Price)。** 顺序是 **先抽到人 -> 读他固定的档位 ->
  为这一局给他报个价**,价格在档位上下一档之间浮动。所以抄底说的是真话:
  一个 G3 这局卖 $1,他真的就是 G3,只是市场报错了。
  *(反过来做——先定价格再从价格附近生成档位——会让 34 个 G5 被反复回收:
  实测板面上 G5 占 21%,而他们只占卡池 5%,放大 4.1 倍,星卡就不稀有了。)*
- **卡面三层**:标价 / 位置 + 一维的**球探区间**(真值一定在里面,但不一定在中间,
  宽度也不固定) / 国籍 + 一条身份线索(俱乐部、Major 次数、年龄三选一)。
- **阵容标签**:DOUBLE AWP / REUNION / MONEYBALL 之类,**只命名不算分**,
  加减分早就在默契里算过了。看得见的那一半(位置、国籍、标价判定的)在**选人时**
  就常驻显示,告诉你这一局可以去追什么、还差几个人。
- **散场时每一张牌都翻开**:七个市场日 35 张,当时卡面写了什么 -> 他实际是谁,
  并标出错过的抄底。这也是「老哥太多、都不认识」的解药——重复出现是学习曲线的
  前提,前提是每局结束能对一次答案。
- **按剩余预算发牌**:标价全部落在买得起的区间;缺的位置提高权重,
  只在最后一两个位置才硬保底;已有队员的真实队友权重 x2(不硬塞)。

原型测试桩(**不是玩法,只是为了让这一层能被验证**):

- **剩余的钱记作 Rogue Points。** 正式设计里它买的是 Buff、走另一条构筑路线;
  Buff 系统还没做,所以原型暂时按「1 点 = 全队火力 +1.5」折算进分数,只为回答
  「如果余钱有价值,省钱会不会变成真决策」。**这个折算不是玩法。**
- **赛后穷举同一批牌能组出的全部阵容给名次**,用来判断「选什么都一样」与否。
"""
import argparse
import collections
import itertools
import json
import random
import re
import statistics as st
import zlib
from pathlib import Path

from playerdb.paths import BLIND_DRAFT, DATA, ROOT

CARDS_PATH = BLIND_DRAFT / "draft_cards.json"
PLAYERS_PATH = DATA / "players.json"
LOG_PATH = ROOT / ".cache" / "proto_draft_runs.jsonl"

BUDGET = 15
SLOTS = 5
TURNS = 7                        # 7 个「市场日」里完成 5 次签约(不是「白送两次刷新」)
GRADES = (5, 4, 3, 2, 1)
WEIGHTS = {"RIFLER": (0.55, 0.05, 0.20, 0.20),
           "AWPER": (0.45, 0.05, 0.20, 0.30),
           "IGL": (0.25, 0.35, 0.35, 0.05)}   # 与 blinddraft/cards.py §18 一致

# 市场为这个人报价时的浮动。**delta 是「标价 − 档位」**(代码里 price = 档位 + delta):
# −1 = 报便宜了 = 抄到底,+1 = 报贵了 = 坑货。
# (这里以前的注释把符号写反了。25/50/25 对称,所以看不出来;一旦改成不对称,
#  照着旧注释写就会把两头调反。)
#
# 不对称是有意的:**好货不常打折,坑货倒是不少。** 25/50/25 的时候,一个看不见档位的
# 玩家到手的五张里有 2 张以上抄底的概率是 58%、一张都没有只有 13%——抄底成了每局
# 稳定发放的奖励,不是故事。改成 12/70/18 之后是 0 张 38% / 1 张 41% / 2 张+ 21%。
#
# (轮次一度收到 6 轮 1 跳,又改回来了:6 轮是在**旧发牌器**上得出的结论,而新发牌器
#  按预算控价、缺位提权、后期保底,6/1 从来没单独验证过。实测第一局就打出反例——
#  跳掉第三轮之后第四轮只有一张步枪,那不是「选哪个步枪」,是「只有这一个还能怎么办」。)
MARKET_ROLL = ((-1, 0.12), (0, 0.70), (1, 0.18))

# 板面的「进货结构」。卡池是 47.7% G1 / 5.2% G5,照原样抽的话板面几乎全是便宜货、
# 预算永远花不掉;所以按档位调一个进货权重。**这只影响谁被摆上货架,不影响他的
# 档位和四维**——价格仍然是抽到人之后才为他报的。
GRADE_WEIGHT = {5: 1.5, 4: 2.2, 3: 1.6, 2: 1.1, 1: 0.6}

# **测试桩,不是玩法。** 正式设计里剩下的钱买的是 Buff(Rogue Build),
# 走的是另一条构筑路线;Buff 还没做,所以原型暂时把 1 点 Rogue Point 折算成
# 全队火力 +1.5,只为回答「如果余钱有价值,省钱会不会变成真决策」。
#
# 兑换率在新发牌下重扫过:R=1.5 时最优打法平均留 $1.5、比"花满"高 1.26 分
# (R=0 时也有 +0.80,因为板面不总能正好花完 $15),再高就变成囤钱恒对。
# 上限 4 点:正式设计里 Buff 位有限,这里也借这个理由挡住"全买 $1 囤一堆钱"
# 的退化解——不设的话,一局留 $9 就能换全队火力 +27。
SAVE_RATE = 1.5
SAVE_CAP = 4
SAVE_ATTR = "firepower"

# 球探区间。**不能用「真值 ±5」**——那只是把数字换个写法,玩两把就知道中点是真值,
# 档位照样被反推出去。要的是:宽度随机、真值在区间里的位置也随机,只保证一定落在
# 区间内。于是相邻档位在球探报告这一层真正重叠:真实 69 和真实 75 都可能显示
# 「68-78」,玩家只能算概率,算不出答案。
#
# 参数是扫出来的。决定「能推断多准」的**不是宽度,是真值允许落在区间里的位置范围**:
# 可推断窗口 = (位置上限 - 位置下限) x 宽度。把位置锁在 30%~70% 的话,窗口只有 ~4 点,
# 比档位带(约 10 点宽)还窄,88% 的区间照样只对应一个档位——等于白改。
#
#   宽 8-14 · 位置 30-70%   平均 1.12 档   只对应 1 档 88%   窗口 ~4 点
#   宽 8-14 · 位置  5-95%   平均 1.37 档   只对应 1 档 63%   窗口 ~10 点
#   宽 12-18 · 位置 5-95%   平均 1.61 档   只对应 1 档 39%   窗口 ~13 点  <- 采用
#
# 代价是真值可能贴着区间的边,球探偶尔"很不准"——但那正好让 Reveal 的
# 「超出预期 / 贴着下沿」有了意义。区间每次发牌重摇,不跟着卡走:固定在卡上的话,
# 区间本身会变成这个人的指纹,又能查表了。
SCOUT_WIDTH = (12, 18)
SCOUT_POS = (0.05, 0.95)          # 真值落在区间的哪个位置

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

  余钱   每剩 $1 = 1 Rogue Point(最多算 4 点)。正式设计里它买 Buff(还没做),
         原型暂按 1 点 = 全队火力 +1.5 折算进分数 —— 这是测试桩,不是玩法

  总分 = 基础分 + 默契 + Rogue 折算   单场发挥 ~ 总分 +- (100 - 稳定) / 4

**标价不等于档位。** 每个人的档位是他自己固定的,市场只是这一局给他报了个价;
报价可能比他真实的档位低一档(抄底)或高一档(买贵)。

**卡面给的是球探报告,不是完整属性。** 那一维给的是一个区间,真值一定在区间内,
但不一定在中间,宽度也不固定 —— 你能判断他大概多强,但推不出他的确切档位。
签下来之后(Reveal)才看到精确数字。
"""


# ----------------------------------------------------------------- 基础

def overall(c):
    wf, wl, we, ws = WEIGHTS[c["position"]]
    return (c["firepower"] * wf + c["leadership"] * wl
            + c["experience"] * we + c["stability"] * ws)


def load_cards():
    """原样读已提交的 v6 卡,**不做任何加工**。

    早先的版本在这里加过两层:按队伍排名/活跃度推的 Quality Offset,和把
    年龄换成火力的零和整形。两层都撤了,原因写在 docs/blind-draft/原型实测记录.md:

    - Quality Offset 用「近年是否还在打」当正分,直接违反 §14「一律按生涯代表
      版本评价」——一个退役传奇不该因为退役而掉数值;而「所在队 Top100 排名」
      是队伍指标,好选手在烂队、角色球员在强队都很常见。这等于在没有 Rating 的
      情况下用代理指标重造一个隐藏 Rating,正是这个项目当初主动放弃的那条路。
    - 零和整形要求同档 overall 守恒,可 overall 只是内部估值工具,不是守恒量。
      一个又强又稳又有经验的人本来就该三项都高,没有理由让经验 +8 去还 -4 的火力。
      而且它让年龄成了火力的主要驱动(donk 和 dev1ce 光生日就差 6 点火力),
      和 41df824 骂过的「一个生日值 18 点火力」是同一个毛病。

    同档内部的差异现在**只由市场错价提供**:同样 $2,一个是 G1、一个可能是 G3。
    """
    return [dict(c) for c in
            json.loads(CARDS_PATH.read_text(encoding="utf-8"))["cards"]
            if c.get("position")]


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


def scout_range(value, rng):
    """真值 -> 球探区间,保证 lo <= value <= hi。"""
    width = rng.randint(*SCOUT_WIDTH)
    lo = round(value - width * rng.uniform(*SCOUT_POS))
    lo, hi = max(1, lo), max(1, lo) + width
    if hi > 99:
        hi, lo = 99, max(1, 99 - width)
    return lo, hi


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
    lo, hi = card["scout"]
    bits = [f"{ATTR_CN[k]} {lo}-{hi}", card["country"], identity_clue(card)]
    if open_mode:
        bits.append(f"[G{card['grade']} 火{card['firepower']} 领{card['leadership']} "
                    f"经{card['experience']} 稳{card['stability']}]")
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
            same = sum(1 for _, t in
                       rosters[a["page"]] & rosters[b["page"]] if t == team)
            total += bonus
            where = f"({team} {same} 届)" if same < n else f"({team})"
            notes.append(f"队友 {a['nickname']} + {b['nickname']}  同队 {n} 届 Major"
                         f"{where}  +{bonus:.1f}")

    for country, n in collections.Counter(c["country"] for c in roster).items():
        # 卡库外真人暂时没有国籍时是空字符串；未知不能被当成“同国籍”。
        if country and n >= 2:
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

    n_igl = sum(1 for c in roster
                if c.get("caller", c["position"] == "IGL"))
    if n_igl >= 2:
        total -= 3.0 * (n_igl - 1)
        notes.append(f"{n_igl} 个指挥抢话  -{3.0 * (n_igl - 1):.1f}")

    return total, notes


def score(roster, rosters, money=0):
    """money = 剩余预算,按固定兑换率折成全队火力。"""
    boost = min(money, SAVE_CAP) * SAVE_RATE
    get = lambda c, k: c[k] + (boost if k == SAVE_ATTR else 0.0)

    f = sorted((get(c, "firepower") for c in roster), reverse=True)
    fire = f[0] * .35 + f[1] * .25 + st.mean(f[2:]) * .40

    igls = [c for c in roster if c.get("caller", c["position"] == "IGL")]
    if igls:
        top = max(igls, key=lambda c: c["leadership"])
        # 只有最强的那个 IGL 算指挥;其余四人按步枪的领导力算,多塞指挥不是加成
        others = [get(c, "leadership")
                  if not c.get("caller", c["position"] == "IGL") else 25
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

# 一支队自然只要一个狙、一个指挥、三个步枪。**位置已经满了的牌就是废牌**:
# 实测拿齐 AWP + IGL 之后,板面上仍有 35.6% 的牌是你不再需要的位置,五张里有两张
# 以上废位的局占 59%——「一批五张」实际上只有三张能选,这就是「可选择的不够多」。
# 降权是软的,不是禁:双狙、双指挥仍然摸得到(那是 DOUBLE AWP 这类标签的前提),
# 只是不会在你已经有 s1mple 之后再连发三个狙。
POSITION_QUOTA = {"AWPER": 1, "IGL": 1, "RIFLER": 3}
FULL_PENALTY = 0.45


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

    @staticmethod
    def price_dist(grade):
        """这一档的人这局可能被报什么价 -> {价格: 概率}(夹在 $1-$5)。"""
        out = collections.defaultdict(float)
        for delta, w in MARKET_ROLL:
            out[max(1, min(5, grade + delta))] += w
        return out

    def _draw(self, max_price, need, want, full=frozenset(), position=None):
        """**先抽到人**,再读他固定的档位,为他报这一局的价。

        抽人的权重里带一项「他这局的报价买得起的概率」——这是「从卡池里抽一个人,
        条件是他这局的价你付得起」的准确写法。反过来做(先定价格、再从价格附近
        生成一个档位的人)会让 34 个 G5 被反复回收:实测板面上 G5 占 21%,
        而他们只占卡池 5.2%,放大 4.1 倍,星卡就不稀有了。
        """
        cand, w = [], []
        for g in GRADES:
            afford = sum(v for pr, v in self.price_dist(g).items() if pr <= max_price)
            if afford <= 0:
                continue
            for c in self.pool[g]:
                if position is not None and c["position"] != position:
                    continue
                cand.append(c)
                w.append(draw_weight(c) * GRADE_WEIGHT[g] * afford
                         * (NEED_BOOST if c["position"] in need else 1.0)
                         * (FULL_PENALTY if c["position"] in full else 1.0)
                         * (MATE_BOOST if c["page"] in want else 1.0))
        if not cand:
            return None
        pick = self.rng.choices(cand, weights=w, k=1)[0]
        self.pool[pick["grade"]].remove(pick)

        dist = {pr: v for pr, v in self.price_dist(pick["grade"]).items()
                if pr <= max_price}
        price = self.rng.choices(list(dist), weights=list(dist.values()), k=1)[0]
        # 球探区间每次发牌重摇:固定在卡上的话,区间本身就成了这个人的指纹
        return dict(pick, price=price,
                    scout=scout_range(pick[scout_attr(pick)], self.rng))

    def board(self, left, slots_left, owned):
        """五张牌,标价都落在买得起的区间;缺的位置提权,最后才硬保底。"""
        max_price = max(1, min(5, left - (slots_left - 1)))
        have = collections.Counter(c["position"] for c in owned)
        need = {p for p in ("AWPER", "IGL") if not have[p]}
        full = {p for p, q in POSITION_QUOTA.items() if have[p] >= q}
        want = {m for c in owned for m in self.mates.get(c["page"], ())}

        board = []
        for i in range(5):
            force = None
            if need and slots_left <= 2 and i == 4 \
                    and not any(c["position"] in need for c in board):
                force = sorted(need)[0]
            c = self._draw(max_price, need, want, full, force)
            if c is not None:
                board.append(c)
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
        print(f"\n-- 第 {turn}/{TURNS} 个市场日    预算 ${left}    还要签 {slots_left} 人"
              f"    {'可以放掉 %d 个市场日' % (turns_left - slots_left) if can_pass else '接下来每天都必须签人'} --")
        if picked:
            print("   已有:", "  ".join(f"${c['price']} {c['position']}({c['country']})"
                                        for c in picked))
            have = {c["position"] for c in picked}
            missing = [p for p in ("IGL", "AWPER") if p not in have]
            if missing:
                print("   还缺:", " / ".join(missing),
                      " (缺 AWP 扣 4 分,缺 IGL 领导力打六折)")

        bp = blueprints(picked, slots_left)
        if bp:
            print("   可以去追:  " + "   ".join(
                "[%s] %s%s" % (t, note, " ✓" if done else "") for t, note, done in bp))

        for i, c in enumerate(board, 1):
            print(f"  {i}) {face(c, open_mode)}")
        if can_pass:
            print("  s) 放掉这个市场日,换一批新牌")

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


def why_better(mine, mine_left, alt, alt_left, rosters):
    """「更该拿 X」得说出为什么。

    第一次实测里两条建议(jambo、Vexite)都是**同国籍默契**——正是玩家自己在做的
    事——可面板只报了一个名字和一个数,读起来像在说「你该省钱」。
    """
    a, m = score(alt, rosters, alt_left), score(mine, rosters, mine_left)
    money = ((a["total"] - score(alt, rosters, 0)["total"])
             - (m["total"] - score(mine, rosters, 0)["total"]))
    chem = a["chem"] - m["chem"]
    card = (a["total"] - m["total"]) - money - chem
    # 只说「多了什么 / 少了什么」里最重的那一条。默契变好可能是因为多了一条加分,
    # 也可能是因为**少了**一条罚分(比如不再是三个指挥抢话)——两种说法不能混。
    val = lambda n: float(re.search(r"[-+]\d+(?:\.\d+)?$", n).group())
    gained = sorted((n for n in a["notes"] if n not in m["notes"]), key=val)
    lost = sorted((n for n in m["notes"] if n not in a["notes"]), key=val)
    why = ""
    if gained and val(gained[-1]) > 0:
        why = "多了「%s」" % gained[-1]
    elif lost and val(lost[0]) < 0:
        why = "少了「%s」" % lost[0]
    bits = []
    if abs(chem) >= 0.05:
        bits.append("默契 %+.1f%s" % (chem, "  " + why if why else ""))
    if abs(card) >= 0.05:
        bits.append("卡本身 %+.1f" % card)
    if abs(money) >= 0.05:
        bits.append("余钱 %+.1f" % money)
    return " · ".join(bits)


def blueprints(picked, slots_left):
    """选人时就能看见的「这一局你可以去追什么」。

    这是**蓝图 v0:零新机制、不加分**。aim 标签本来就只用卡面看得见的东西
    (位置、国籍、标价)判定,所以它天然就是一张「你现在可以朝这走」的清单;
    这里只是把它从赛后搬到赛中,并算出还差几个人。

    为什么先做这个不做回报:第二局实测里玩家自己想组「独联体青春风暴」,
    板面上料是够的(25 张牌里 6 个独联体人,4 个 24 岁以下),他也真凑出了
    UKRAINE CORE——**问题不是牌不给,是组成了也没有任何东西承认这件事**。
    如果连「看得见」都不能让人产生想追的欲望,加分也救不了它。加回报和
    SCOUTING FOCUS(主动把方向盘拨一下)都要等这一步的结果。

    返回 [(标签, 进度说明, 是否已达成)],已达成的排前面,已经不可能的不返回。
    """
    out = []
    pos = collections.Counter(c["position"] for c in picked)
    ctry = collections.Counter(c["country"] for c in picked)
    prices = [c["price"] for c in picked]

    def add(tag, have, want, unit, dead=False):
        if dead or have + slots_left < want:
            return
        out.append((tag, "已达成" if have >= want else f"还差 {want - have} {unit}",
                    have >= want))

    add("DOUBLE AWP", min(pos["AWPER"], 2), 2, "个狙")
    if pos["AWPER"] >= 2:
        add("AWP OVERLOAD", pos["AWPER"], 3, "个狙")
    add("TWO CALLERS", pos["IGL"], 2, "个指挥")
    if ctry:
        top_c, n_c = ctry.most_common(1)[0]
        add(f"{top_c.upper()} CORE", n_c, 3, f"个 {top_c} 人")
    elif slots_left >= 3:
        out.append(("同国三人", "任选一国凑满 3 个", False))
    if not any(x > 2 for x in prices):
        out.append(("MONEYBALL", "已达成" if len(picked) == SLOTS
                    else "接着只买 $1-2 的牌", len(picked) == SLOTS))
    add("GALACTICOS", sum(1 for x in prices if x == 5), 2, "张 $5")
    out.sort(key=lambda t: (not t[2],))
    return out[:5]


def roster_traits(picked, rosters):
    """给这五个人一个「这是支什么队」的答案。

    **不新加任何数值。** 位置冲突、同国、同代、真队友这些的加减分早就在 chemistry
    里算了,这里只是把同一件事从流水账(「同国籍 Denmark x2  +1.5」)换成一个名字
    (「DANISH CORE」)。多加一个旋钮就又多一个没验证过的变量。

    分两类,这个区分是有用的:
    - aim   —— 只用卡面看得见的东西(位置、国籍、标价)判定,所以**选人的时候就能
               朝它走**:手里已经两个 AWP 了,第三个买不买?
    - blind —— 要身份揭晓才知道,选的时候看不见,是撞上的。
    """
    out = []
    def add(kind, tag, note):
        out.append({"kind": kind, "tag": tag, "note": note})

    pos = collections.Counter(c["position"] for c in picked)
    n_awp, n_igl = pos["AWPER"], pos["IGL"]
    if n_awp == 0:
        add("aim", "RIFLE ONLY", "五个人没人架狙")
    elif n_awp == 2:
        add("aim", "DOUBLE AWP", "双狙体系,火力上限高,谁让位是问题")
    elif n_awp >= 3:
        add("aim", "AWP OVERLOAD", f"{n_awp} 个主狙抢同一把枪")
    if n_igl == 0:
        add("aim", "NO CALLER", "没人指挥")
    elif n_igl >= 2:
        add("aim", "TWO CALLERS", f"{n_igl} 个指挥抢话")

    ctry = collections.Counter(c["country"] for c in picked)
    top_c, n_c = ctry.most_common(1)[0]
    if n_c >= 3:
        add("aim", f"{top_c.upper()} CORE", f"{n_c} 个 {top_c} 人的班底")

    prices = sorted((c["price"] for c in picked), reverse=True)
    if prices[0] <= 2:
        add("aim", "MONEYBALL", f"全队最贵的一张只要 ${prices[0]}")
    elif prices[1] == 5:
        add("aim", "GALACTICOS", "两张 $5 摆在同一队")

    # ↓ 以下选人时看不见:身份是盖着的
    #
    # 队名要挑「一起打过最多届 Major 的那一支」,不能挑「最多人待过的那一支」:
    # 后者会把 dev1ce + Xyp9x 报成 dignitas(两人早年确实都在,但同队一届),
    # 而不是 astralis(同队八届)。同队届数才是这段关系的分量。
    together = collections.Counter()          # 战队 -> 队内同队届数合计
    involved = collections.defaultdict(set)   # 战队 -> 涉及到的人
    for a, b in itertools.combinations(picked, 2):
        shared = rosters.get(a["page"], set()) & rosters.get(b["page"], set())
        for _, t in shared:
            together[t] += 1
            involved[t] |= {a["nickname"], b["nickname"]}
    if together:
        top_t, n_t = together.most_common(1)[0]
        if len(involved[top_t]) >= 3:
            add("blind", f"{top_t.upper()} CORE",
                f"{len(involved[top_t])} 个人一起在 {top_t} 打过 Major")
        else:
            add("blind", "REUNION", f"{top_t} 的老队友又凑到一起了(同队 {n_t} 届 Major)")
    elif len(ctry) == 5:
        # 五个国家、五个人互相没打过 —— 这才算「拼凑」,不是「国际班底」。
        # (光看「五个国家」会有 57% 的局命中,那不是身份,是噪音。)
        add("blind", "INTERNATIONAL MIX", "五个国家,五个人互相没打过")

    champs = sum(c["champions"] for c in picked)
    if champs >= 4:
        add("blind", "MAJOR WINNERS", f"队内 Major 冠军合计 {champs} 座")

    ages = [c["age"] for c in picked if c["age"]]
    if len(ages) >= 2:
        spread = max(ages) - min(ages)
        if spread <= 5:
            add("blind", "SAME GENERATION", f"年龄差只有 {spread} 岁")
        elif spread >= 14:
            add("blind", "GENERATION GAP", f"最老最小差 {spread} 岁")

    steals = sum(1 for c in picked if tier_gap(c) > 0)
    dupes = sum(1 for c in picked if tier_gap(c) < 0)
    if steals >= 2:
        add("blind", "BARGAIN BIN", f"{steals} 张的档位高于标价")
    if dupes >= 3:
        add("blind", "FLEECED", f"{dupes} 张买贵了")

    return out


def reveal(picked, boards, left, rosters, passed):
    print("\n" + "=" * 78)
    print("REVEAL")
    print("=" * 78)

    for c in picked:
        g = tier_gap(c)
        tag = f"抄底 +{g} 档" if g > 0 else (f"买贵 {g} 档" if g < 0 else "标价合理")
        k = scout_attr(c)
        lo, hi = c["scout"]
        where = (c[k] - lo) / max(1, hi - lo)
        hit = ("超出预期(卡在上沿)" if where >= 0.72 else
               ("低于预期(贴着下沿)" if where <= 0.28 else "球探准"))
        print(f"  ${c['price']} {c['position']:<6} {c['nickname']:<13} {c['country']:<12}"
              f" {(c['team'] or '自由身/退役'):<20} G{c['grade']} "
              f"火{c['firepower']:<3} 领{c['leadership']:<3} 经{c['experience']:<3} "
              f"稳{c['stability']:<3} {tag}")
        print(f"       球探报告 {ATTR_CN[k]} {lo}-{hi}  ->  实际 {c[k]}  {hit}")

    traits = roster_traits(picked, rosters)
    if traits:
        print("\n  这是一支什么队:")
        for t in traits:
            mark = "选的时候看得见" if t["kind"] == "aim" else "撞上的"
            print(f"    [{t['tag']}]  {t['note']}   ({mark})")

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
    print("\n  事后最优(**上帝视角,不是说你选错了**):")
    print("    用的是揭晓后的完整真值——精确四维、组合出来的默契、便宜一块留下的")
    print("    Rogue Point——全都是你当时看不到的。在信息不全时判断,本来就是这个玩法。")
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
        tail = ("当时那批牌里这张就是最优" if regret < .05 else
                "事后最优 $%d %s %s" % (alts[0][1]["price"], alts[0][1]["position"],
                                      alts[0][1]["nickname"]))
        print(f"    ${c['price']} {c['position']:<6} {c['nickname']:<12} "
              f"差 {regret:5.1f}   {tail}")
        if regret >= .05:
            combo = list(picked); combo[k] = alts[0][1]
            why = why_better(picked, left, combo,
                             BUDGET - sum(x["price"] for x in combo), rosters)
            if why:
                print(f"    {'':>27}   {why}")

    spend_me = BUDGET - left
    same_spend = [t for t, _, sp in ranked if sp == spend_me] or [mine]
    best_steal = max(picked, key=tier_gap)
    missed = max((c for b in boards for c in b if c not in picked),
                 key=tier_gap, default=None)

    print("\n  " + "-" * 74)
    print(f"  选牌准度   与事后最优的差值合计 {sum(regrets):5.1f}   "
          f"(上帝视角;0 = 每一轮都撞上了当时那批牌的最优)")
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

    # WHAT YOU MISSED:每个市场日、每一张牌全部翻开。
    # 不翻开的话,反复出现的那 69 张 G4/G5 面孔只是噪音;翻开之后,「上次就是这哥
    # 把我坑了」才会变成下一局的记忆。也是「老哥太多、都不认识」最自然的解药。
    print("\n  " + "-" * 74)
    print("  你错过了谁 —— 当时卡面上写的是什么,他实际上是谁")
    for bi, b in enumerate(boards, 1):
        mine = next((c for c in b if c in picked), None)
        head = ("你放掉了这天" if bi in passed else
                (f"你签下 {mine['nickname']} (${mine['price']})" if mine else "—"))
        print(f"\n  第 {bi} 个市场日 · {head}")
        for c in b:
            g = tier_gap(c)
            mark = ("<- 你签下" if c is mine else
                    (f"[抄底] 错过 +{g} 档" if g > 0 else
                     (f"[虚高] 标价高 {-g} 档" if g < 0 else "")))
            k = scout_attr(c)
            lo, hi = c["scout"]
            print(f"    ${c['price']} {c['position']:<6} "
                  f"{ATTR_CN[k]} {lo}-{hi} · {c['country'][:12]:<12} · "
                  f"{identity_clue(c)[:16]:<16} -> {c['nickname']:<13} G{c['grade']} "
                  f"{c['firepower']}/{c['leadership']}/{c['experience']}/"
                  f"{c['stability']:<3} {mark}")
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
    print(f"Blind Draft 原型 v3.4  预算 ${BUDGET} · 签 {SLOTS} 人 · {TURNS} 个市场日    "
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
                           "p": c["position"]} for c in picked],
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
