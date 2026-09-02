# -*- coding: utf-8 -*-
"""Blind Draft — Major 入场层原型(Match Engine v0.1 的第一步)

这一步**不含任何比赛计算**,只回答三个问题:

    1. 这届 Major 的 32 支真实队,按我们自己的卡库排下来是什么样?
    2. 玩家抽出来的这五个人插进去排第几、挤掉了谁、从哪个 Stage 进场?
    3. 进场那个 Stage 的 16 个种子和首轮 8 场对阵是什么?

对应设计稿 docs/blind-draft/比赛引擎_v0.1.md 的 §1~§3、§8、§9。
之所以先做这一层:它一个随机数都不需要,对错肉眼可判;而 Swiss 循环和胜率
函数(§34)全都建在它上面。

不改卡库、不改 data/players.json,只读它和 proto_draft 的评分函数。
唯一写进 data/ 的是人工配置 data/blind_draft/major_field.json——按 §21
「Algorithm First, Override Last」,和已有的 draft_overrides.json 同一套规矩。
"""
import argparse
import collections
import json
import os
import random
import statistics as st
import sys
from pathlib import Path

from playerdb.paths import BLIND_DRAFT, DATA as DATA_DIR

from . import draft as P

DATA = str(DATA_DIR / "players.json")

DEFAULT_EVENT = "IEM Cologne 2026"

# 磨合度(Team Cohesion)= min(裸默契, COHESION_CAP)。
#
# 名字从 CHEM_CAP 改过来,是因为它早就不在做「封顶默契」这件事:真实队的裸默契
# 是 19.5~32(当前阵容口径 4~28),几乎全员顶格,只有玩家临时队落在 0~4 这一段。
# 也就是说全场只有玩家一个人站在这条斜坡上——这个数调的是**草台班子税有多重**,
# 而不是真队之间谁更磨合(§44.1、§45.6)。叫「磨合度」比「默契封顶」准确。
#
# 默认值跟 data/blind_draft/major_field.json 保持一致(§45.6 的结论:8 太重,普通打法
# 41% 进不了 Major)。这里只是配置文件缺失时的兜底。
COHESION_CAP = 4.0

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

def entry_rating(roster, rosters, cohesion_cap=COHESION_CAP):
    """§4:赛前评价。基础分 + 封顶后的先天默契,不含 Form / 高压 / Rogue。

    money 固定传 0 是有意的——省下的预算是 Rogue Point 的替身,而 §4 明说
    Rogue Buff 不参与 Entry Rating,不能让人靠留钱买到一张 Stage 3 邀请函。
    """
    s = P.score(roster, rosters, 0)
    chem = min(s["chem"], cohesion_cap)
    return {"base": s["base"], "chem_raw": s["chem"], "cohesion": chem,
            "entry": s["base"] + chem, "notes": s["notes"]}


class Entry(object):
    """赛场上的一支队。is_player 决定它在表里怎么显示。

    `adjust` 是人工层直接加在分上的偏移(teams.<队>.adjust),默认 0。

    为什么需要这个出口、为什么加在分上而不是改火力:卡面四维量的是**生涯成就**,
    HLTV 排名量的是**现在在赢球**,两者秩相关只有 0.53,而且这不是某个参数没调好
    ——实测给「距上次进 top20 的年数」加衰减,要把两年没进榜的人火力清零才能把
    rho 抬到 0.61(§48)。剩下的差距只能人工填。改火力太钝:BC.Game 全队 -24 火力
    只挪 3 位,因为火力权重 0.40 还要摊进那条排序加权的聚合式。

    MatchTeam 会把这一笔加进 floor,所以「不 Roll 的强度 == Entry Rating」那条
    不变量仍然成立(selftest 会查)。
    """

    adjust = 0.0

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


def real_field(event, rosters, cohesion_cap=COHESION_CAP):
    """32 支真实队,按 Entry Rating 从高到低。"""
    teams, missing = load_major(event)
    full = {t: r for t, r in teams.items() if len(r) == 5}
    field = [Entry(t, r, entry_rating(r, rosters, cohesion_cap))
             for t, r in full.items()]
    field.sort(key=lambda e: -e.entry)
    dropped = {t: len(r) for t, r in teams.items() if len(r) != 5}
    return field, dropped, missing


# ------------------------------------------------------------------ 可配置赛场

# 改组时这里一度还写着 data/manual/,而文件已经搬到 data/blind_draft/。
# load_config 把 IOError 咽掉、静默退回 DEFAULT_CONFIG,于是整个人工层
# (teams 里的 adjust / caller / max_filler,以及 regional_slots、candidate_pool)
# 全都不生效,而页面照常渲染——正是 playerdb/paths.py 开头警告的那种错法。
# 所以路径只从 BLIND_DRAFT 取,不再自己拼。
CONFIG_PATH = str(BLIND_DRAFT / "major_field.json")

DEFAULT_CONFIG = {
    "pool": [DEFAULT_EVENT, "BLAST Austin 2025", "StarLadder Budapest 2025"],
    "field_size": FIELD_SIZE,
    "locked_top": 8,
    "weight_decay": 0.95,
    "roster_mode": "latest",
    "field_source": "current",
    "max_filler": 1,
    "cohesion_cap": COHESION_CAP,
    "teams": {},
}


def load_config(path=None):
    """读 data/blind_draft/major_field.json,缺什么用 DEFAULT_CONFIG 补。"""
    cfg = dict(DEFAULT_CONFIG)
    try:
        raw = json.loads(Path(path or CONFIG_PATH).read_text(encoding="utf-8"))
    except (IOError, OSError):
        return cfg
    cfg.update({k: v for k, v in raw.items() if not k.startswith("_")})
    if "chem_cap" in raw:                         # 改名前的旧键,仍然认
        cfg["cohesion_cap"] = raw.pop("chem_cap")
    return cfg


def build_pool(cfg, rosters, cohesion_cap=COHESION_CAP):
    """把 pool 里几届 Major 摊成 {队名: [(赛事, 五张卡, Entry Rating), ...]}。

    版本按 cfg["pool"] 的顺序排,所以第 0 个就是「最近一届的阵容」。
    同一支队在不同届之间平均换 1.8 个人(28 支重复队里 24 支换过),
    所以「哪一届的它」是一个真的变量,不是换皮。
    """
    pool = collections.defaultdict(list)
    for event in cfg["pool"]:
        teams, _ = load_major(event)
        for name, roster in teams.items():
            if len(roster) == 5:
                pool[name].append((event, roster,
                                   entry_rating(roster, rosters, cohesion_cap)))
    return dict(pool)


def rank_names(pool, cfg):
    """全局顺位:按一支队各版本 Entry Rating 的均值排。

    用均值而不是「当前版本」,是为了让顺位在不同 roster_mode 下都稳定——
    locked_top 每局锁的必须是同一批队,否则「标尺」就没意义了。
    """
    over = cfg.get("teams", {})
    names = [n for n in pool if over.get(n, {}).get("weight", 1.0) > 0]
    names.sort(key=lambda n: -st.mean(v[2]["entry"] for v in pool[n]))
    out = []
    for i, n in enumerate(names, 1):
        w = over.get(n, {}).get("weight")
        out.append((n, i, cfg["weight_decay"] ** (i - 1) if w is None else float(w)))
    return out


def roll_seats(ranked, cfg, rng):
    """ranked = [(队名, 顺位, 权重), ...],已按顺位排好。

    前 locked_top 支必在(它们是标尺,不该每局换人),其余席位按权重**不放回**抽。
    两种赛场来源共用这一段——「哪些队来」和「这些队怎么算分」是两件事。
    """
    n = int(cfg["field_size"])
    chosen = [r[0] for r in ranked[:int(cfg["locked_top"])]]
    rest = [(r[0], r[2]) for r in ranked[int(cfg["locked_top"]):]]
    for _ in range(min(n - len(chosen), len(rest))):
        total = sum(w for _, w in rest)
        x = rng.random() * total
        for i, (name, w) in enumerate(rest):
            x -= w
            if x <= 0:
                chosen.append(name)
                rest.pop(i)
                break
    return chosen


def _pick_version(name, versions, cfg, rng):
    pin = cfg.get("teams", {}).get(name, {}).get("roster")
    if isinstance(pin, str):                      # 钉死某一届
        for v in versions:
            if v[0] == pin:
                return v
    if cfg["roster_mode"] == "roll" and len(versions) > 1:
        return versions[rng.randrange(len(versions))]
    return versions[0]                            # latest


def build_field(rng, cfg=None, rosters=None, cohesion_cap=COHESION_CAP, pool=None):
    """生成一届赛场:顺位前 locked_top 支必在,其余席位按权重不放回抽。

    人工层(data/blind_draft/major_field.json 的 teams 段)在这里全部生效:
    weight 0 = 永不出现、weight 很大 = 几乎必在、roster 填赛事名 = 钉死那一届
    的阵容、roster 填五个人 = 手写阵容。
    """
    cfg = cfg or load_config()
    rosters = rosters if rosters is not None else load_rosters_cached()
    pool = pool if pool is not None else build_pool(cfg, rosters, cohesion_cap)

    # 手写阵容既可以顶掉某支真实队的五人,也可以凭空加一支池子里没有的队。
    # 后者得先进池子,否则它永远不会被选中。
    hand = _hand_written(cfg, cohesion_cap, rosters)
    if hand:
        pool = dict(pool)
        for name, ver in hand.items():
            pool[name] = [ver]
    ranked = rank_names(pool, cfg)

    chosen = roll_seats(ranked, cfg, rng)

    field = []
    for name in chosen:
        if name in hand:
            event, roster, rating = hand[name]
        else:
            event, roster, rating = _pick_version(name, pool[name], cfg, rng)
        e = Entry(name, roster, rating)
        e.event = event
        field.append(e)
    field.sort(key=lambda e: -e.entry)
    return field


def build_current_field(rng, cfg=None, rosters=None, cohesion_cap=COHESION_CAP):
    """AI 赛场：区域 VRS 名额 + 快照首发 + 逐维 AI 当前卡。

    和 build_field 的分工:
      build_field          队和阵容都来自 pool 里那几届 Major 的参赛名单
      build_current_field  队和阵容来自 team_snapshot,四维来自 AI current projection

    `build_pool_field` 已按 regional_slots 标出本届 32 个席位；candidate_pool 多出
    的 13 支只是 VRS 变动余量，不是每局重新抽签。进入正赛后仍按我们的 Entry
    Rating 排全局种子，让玩家按同一把尺子插入。
    """
    from . import ai_teams as A           # 延迟导入:A 反过来要用本模块
    cfg = cfg or load_config()
    rosters = rosters if rosters is not None else load_rosters_cached()

    teams, asof = A.build_pool_field(cfg)
    qualified = [t for t in teams if t.get("stage")]
    broken = [(t["name"], len(t["roster"])) for t in qualified
              if len(t["roster"]) != 5]
    if broken:
        raise ValueError("正赛席位的快照首发不满五人：%s" % broken)
    if len(qualified) != FIELD_SIZE:
        raise ValueError("regional_slots 应产生 %d 席，实际 %d" %
                         (FIELD_SIZE, len(qualified)))

    field = []
    for t in qualified:
        rating = A.entry_of(t, rosters, cohesion_cap)
        e = Entry(t["name"], t["roster"], rating)
        if t.get("adjust"):
            e.adjust = float(t["adjust"])
        e.event = "当前阵容 @ %s" % (asof or "?")
        e.hltv = t["rank"]
        e.vrs = t.get("vrs")
        e.regional_stage = t["stage"]
        field.append(e)
    field.sort(key=lambda e: -e.entry)
    return field


def make_field(rng, cfg=None, rosters=None, cohesion_cap=COHESION_CAP):
    """按 cfg["field_source"] 选一种赛场来源。默认 current(§46)。"""
    cfg = cfg or load_config()
    if str(cfg.get("field_source", "current")) == "major_pool":
        return build_field(rng, cfg, rosters, cohesion_cap)
    return build_current_field(rng, cfg, rosters, cohesion_cap)


def field_label(cfg, field):
    """一行字说清这届赛场是怎么来的——两种来源的口径完全不同,不能不写。"""
    if str(cfg.get("field_source", "current")) == "major_pool":
        return ("%d 支队 · 池子 %s · 前 %d 固定 · 阵容 %s"
                % (len(field), " + ".join(cfg["pool"]), cfg["locked_top"],
                   cfg["roster_mode"]))
    inferred = sum(1 for e in field for c in e.roster if c.get("_nocard"))
    return ("%d 支队 · 区域 VRS 名额 + 快照首发 + AI 当前四维 · "
            "卡库外真人先验 %d 人" % (len(field), inferred))


_HAND_CACHE = {}


def _hand_written(cfg, cohesion_cap, rosters):
    """teams.<队>.roster 是一个五人列表时,直接用它拼一支队。

    人手写 JSON 的时候不该被迫记住 Liquipedia 页面名的大小写,所以昵称和
    页面名都认,且不分大小写。结果缓存,免得每生成一次赛场就重报一次警告。
    """
    key = json.dumps(cfg.get("teams", {}), sort_keys=True) + str(cohesion_cap)
    if key in _HAND_CACHE:
        return _HAND_CACHE[key]
    out = {}
    index = None
    for name, spec in cfg.get("teams", {}).items():
        wanted = spec.get("roster")
        if not isinstance(wanted, list):
            continue
        if index is None:
            index = {}
            for c in P.load_cards():
                index.setdefault(c["page"].casefold(), c)
                index.setdefault(c["nickname"].casefold(), c)
        roster = [index[w.casefold()] for w in wanted if w.casefold() in index]
        if len(roster) == 5:
            out[name] = ("(手写)", roster, entry_rating(roster, rosters, cohesion_cap))
        else:
            bad = [w for w in wanted if w.casefold() not in index]
            print("手写阵容 %s 忽略:卡库里没有 %s%s"
                  % (name, bad, "" if bad else "(要正好 5 个人)"))
    _HAND_CACHE[key] = out
    return out


_ROSTERS = []


def load_rosters_cached():
    if not _ROSTERS:
        _ROSTERS.append(P.load_rosters())
    return _ROSTERS[0]


# ------------------------------------------------------------------ 玩家插入

class Shove(object):
    """玩家挤进来之后,谁被挤到了哪儿。"""

    def __init__(self, dropped=None, demoted=()):
        self.dropped = dropped          # 掉到第 33、失去席位的那支
        self.demoted = list(demoted)    # [(队, 原 Stage, 现 Stage)]


def insert_player(field, player):
    """§3.1:玩家按 Entry Rating 插进去,**下面全体顺延一位**。

    设计稿那一节自己是矛盾的(一边说踢掉「原本在 #12 的队」,一边把它画在
    #13)。正确的是顺延:一届 Major 就是 32 个席位,你占一个,下面每支退一位,
    第 33 位掉出去。

    顺延的叙事也更好。踢人只有一句话,顺延有三句,而且全在关键位置上——
    跨过第 8 名的那支要多打一个瑞士轮,跨过第 16 名的那支得从 Stage 1 爬,
    第 32 名直接失去席位。**你的加入让三支队各降一级**,这是名额守恒本来
    就该产生的级联。

    玩家排到第 33(比全场最弱还弱)时 rank=33,那就是 Failed to qualify。
    """
    rank = sum(1 for e in field if e.entry > player.entry) + 1
    if rank > FIELD_SIZE:
        return FIELD_SIZE + 1, Shove(), list(field)
    new = field[:rank - 1] + [player] + field[rank - 1:]
    shove = Shove(dropped=new[FIELD_SIZE])
    for edge in (8, 16):
        if rank <= edge:
            # 原本第 edge 名的那支现在是第 edge+1 名,掉了一个 Stage
            shove.demoted.append((new[edge], stage_of(edge), stage_of(edge + 1)))
    return rank, shove, new[:FIELD_SIZE]


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

def sweep_field(args):
    """扫 weight_decay:每局赛场翻新多少支,以及池子本身的容量。"""
    rosters = P.load_rosters()
    cfg = load_config()
    pool = build_pool(cfg, rosters, args.cap or cfg.get("cohesion_cap", COHESION_CAP))
    print("池子:%s" % " + ".join(cfg["pool"]))
    ver = collections.Counter(len(v) for v in pool.values())
    print("不同队名 %d 支,其中出现 %s"
          % (len(pool), "、".join("%d 届的 %d 支" % (k, ver[k]) for k in sorted(ver))))
    print("每局 %d 席,前 %d 固定,剩 %d 席从 %d 支里抽"
          % (cfg["field_size"], cfg["locked_top"],
             cfg["field_size"] - cfg["locked_top"], len(pool) - cfg["locked_top"]))
    print()
    print("decay   两局之间平均差几支   最弱一支的出场率")
    for decay in (1.0, 0.98, 0.95, 0.90, 0.85, 0.75):
        c = dict(cfg, weight_decay=decay)
        rng = random.Random(4242)
        seen, last, diffs = collections.Counter(), None, []
        for _ in range(400):
            names = {e.name for e in build_field(rng, c, rosters, args.cap, pool)}
            seen.update(names)
            if last is not None:
                diffs.append(len(names - last))
            last = names
        weakest = rank_names(pool, c)[-1][0]
        print("%.2f          %4.1f 支            %s %.0f%%"
              % (decay, st.mean(diffs), weakest, 100.0 * seen[weakest] / 400))


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


def print_field(field, player_rank, shove, event, cohesion_cap):
    print("=" * 70)
    print("%s  —  Projected Seeding(模拟种子,不是历史真实 VRS)" % event)
    print("Entry Rating = 基础分 + 磨合度,磨合度 = min(裸默契, %.1f)" % cohesion_cap)
    print("=" * 70)
    last = None
    show_event = len({getattr(e, "event", None) for e in field}) > 1
    for i, e in enumerate(field, 1):
        stage = stage_of(i)
        if stage != last:
            print("  ---- Stage %d ----" % stage)
            last = stage
        mark = ">>>" if e.is_player else "   "
        tail = ("   [%s]" % e.event) if show_event and getattr(e, "event", None) else ""
        print("%s %2d  %-22s  %5.1f   基础 %5.1f  磨合 %4.1f (裸默契 %4.1f)%s"
              % (mark, i, e.name, e.entry, e.rating["base"],
                 e.rating["cohesion"], e.rating["chem_raw"], tail))
    print()
    if player_rank > FIELD_SIZE:
        print("RUN END — Failed to qualify(第 %d,连最后一个席位都没挤进去)"
              % player_rank)
        return
    print("你以 Projected Seed #%d 拿到席位,起始位置 Stage %d。"
          % (player_rank, stage_of(player_rank)))
    for team, was, now in shove.demoted:
        print("   你把 %s 从 Stage %d 挤到了 Stage %d,他们要多打一个瑞士轮。"
              % (team.name, was, now))
    if shove.dropped is not None:
        print("   %s 掉到第 33 位,失去了这届 Major 的席位。" % shove.dropped.name)


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
    ap.add_argument("--event", default=None,
                    help="只用这一届的 32 队,绕过 major_field.json")
    ap.add_argument("--seed", type=int, default=None,
                    help="给一个种子就顺便抽一支玩家队插进去")
    ap.add_argument("--field-seed", type=int, default=None,
                    help="赛场随机种子(默认同 --seed)")
    ap.add_argument("--cap", type=float, default=None,
                    help="覆盖配置里的 cohesion_cap")
    ap.add_argument("--events", action="store_true", help="列出可用的 Major")
    ap.add_argument("--sweep-field", action="store_true",
                    help="扫 weight_decay:两局之间会差几支队")
    args = ap.parse_args()

    if args.events:
        for ev, n in list_events():
            print("%-34s %3d 人次" % (ev, n))
        return
    if args.sweep_field:
        sweep_field(args)
        return

    cfg = load_config()
    if args.cap is None:
        args.cap = float(cfg.get("cohesion_cap", COHESION_CAP))
    rosters = P.load_rosters()
    if args.event:
        label = args.event
        field, dropped, missing = real_field(args.event, rosters, args.cap)
        if not field:
            print("没找到 %s 的完整参赛队。用 --events 看有哪些。" % args.event)
            return
        if dropped:
            print("跳过(不是 5 人): %s" % dropped)
        if missing:
            print("在 Major 名单里但卡库没有: %s" % dict(list(missing.items())[:5]))
    else:
        rng = random.Random(args.field_seed if args.field_seed is not None
                            else args.seed)
        field = make_field(rng, cfg, rosters, args.cap)
        label = field_label(cfg, field)

    rank, shove = FIELD_SIZE + 1, Shove()
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
        rank, shove, field = insert_player(field, me)

    print_field(field, rank, shove, label, args.cap)
    if 1 <= stage_of(rank) <= 3:
        print_round1(field, stage_of(rank))


if __name__ == "__main__":
    main()
