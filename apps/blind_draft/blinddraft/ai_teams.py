# -*- coding: utf-8 -*-
"""Blind Draft — AI 对手用「当前状态」，不是「生涯巅峰」。

这是和抽卡那边**故意分叉**的一层，分叉点只有一个：

    玩家抽到的卡  = 这个人生涯最好的样子（played_role + 巅峰四维）
    赛场上的 AI  = 这支队现在的样子（快照首发 + 当前角色 + 当前竞技证据）

为什么必须分叉：卡库把 magixx 判成步枪手，理由写在
`player_overrides.json` 里——「该届夺冠时队内指挥另有其人，他的生涯代表位置
是步枪手，后期才接手指挥」。这对抽卡完全正确；但 2026 年的 Spirit 里
magixx 就是在喊战术的那个人。同一张卡被两个系统用，而两个系统要的时间点不同。

当前权威路径 `build_pool_field()` 的三条口径：

  阵容/位置  team_snapshot.json 的真实首发与队内位置
  当前火力   5e_player_stats.json 的近 12 个月 S 级证据，经人工锚定标尺映射
  其余维度   玩家卡的生涯先验；卡库外真人使用有来源、低置信的角色先验

旧 `build_ai_field()` 仍保留作历史兼容（卡上 team + roles + 年龄衰减 + 占位人），
但 AI 页面、Major 和 Match 都不再调用它。

不改卡库、不改 `blinddraft/cards.py`、不写 `data/`（只读）。
"""
import argparse
import collections
import json
import os
import sys

from playerdb.paths import BLIND_DRAFT, DATA as DATA_DIR

from . import cards as G          # 只读:借它的位置模板,不改它
from . import draft as P
from . import major as M

RANKING = str(DATA_DIR / "hltv_top100.json")
PLAYERS = str(DATA_DIR / "players.json")
SNAPSHOT = DATA_DIR / "blind_draft" / "team_snapshot.json"
STATS = BLIND_DRAFT / "5e_player_stats.json"

FIELD_SIZE = 32

# 只影响火力（领导 / 经验 / 稳定不随年龄掉——老将的价值本来就在那三样）。
# loss = RATE * (age - KNEE) ** EXP
#   30 岁 -2.6   32 岁 -8.4   34 岁 -16.8   36 岁 -27.4   38 岁 -40.1
# 这条曲线是在「AI 对手名册」那一页上拖出来的，不是算出来的——库里没有任何
# 「这个人现在打得怎么样」的个人数据，所以只能设计。
#
# 它比第一版（30/0.30/1.6）陡得多：36 岁的 Snappi 火力 51→24。但赛场顺位几乎
# 没动（最大 -1.4 分、只有 4 支队各挪一位），原因值得记下来：全场 29 岁以上的
# 21 个人里有 13 个是**指挥**，而指挥本来就排在队内火力的最后一档，权重只有
# 13.3%（见下面 §45.2 那条聚合式）。这条曲线砍的正好是那一档。
AGE_KNEE = 28
AGE_RATE = 0.80
AGE_EXP = 1.7

# 当前角色 -> Draft 位置。`roles` 是**有序**的，第一个才是主位置：
# Dumau ['rifle','awp'] 是步枪手，Try ['awp'] 才是 Legacy 真正的狙。
# 按全局 IGL > AWPER > RIFLER 去扫会扫出「一队三个狙」。
ROLE_MAP = {"igl": "IGL", "awp": "AWPER",
            "rifle": "RIFLER", "rifler": "RIFLER", "entry": "RIFLER",
            "entryfragger": "RIFLER", "lurk": "RIFLER", "lurker": "RIFLER",
            "support": "RIFLER"}
NON_PLAYER = {"coach", "assistant coach", "manager", "analyst",
              "broadcast analyst", "commentator"}

# 改判位置 = 换整套模板，不是换一个标签。
#
# `blinddraft.cards.build_card` 的注释早就写明了这条：「位置的人工修正必须**在套
# 模板之前**生效；放在最后 update 只会换掉标签，四维仍旧来自被否掉的那套模板」。
# 这一层原本正是那个错的做法——只把领导力换成 IGL 档，火力照抄步枪手的，于是
# 造出 Magisk 火 90 / 领 90 这种卡（全库 648 张里，火≥85 且领≥80 的有 0 张）。
# 生成器管这叫**六边形怪物**（`blinddraft/cards.py:293`、设计稿 §11.1）。
#
# 生成器的解法照抄过来：档位模板决定水平，履历只在**档内**拉开 ±6 分，而
# **IGL 只继承 0.4 倍的火力履历**——「明星履历 + IGL 模板」不许叠加。
IGL_FIRE_SHARE = 0.4        # 和 blinddraft/cards.py:295 是同一个数


def retemplate(card, new_pos):
    """把一张卡从它的卡面位置换算到 new_pos 的模板上。

    excess = 这张卡比它自己那档的模板高出多少（履历 + 年轻人加成 + 生成时的
    随机）。**它必须先还原成「步枪手口径」再换过去**——一张 IGL 卡上的 +2 火力
    背后是 +5 的履历，因为它当初只按 0.4 倍记进去；反向换算时要除回来，不然
    指挥改判成步枪手会被白扣一次。

    领导力两个方向都只取该档基准值，不继承。因为「他会不会喊」和「他枪法多好」
    没有关系——生成器给 IGL 的领导力走的是另一条证据通道（`igl_score`：以指挥
    身份拿过多少冠军），一个刚接手喊战术的枪男在那条通道上是空的。
    """
    g = card["grade"]
    old = G.TEMPLATE[card["position"]][g]
    new = G.TEMPLATE[new_pos][g]
    share = lambda pos: IGL_FIRE_SHARE if pos == "IGL" else 1.0
    out = dict(card)
    for i, key in enumerate(G.ATTRS):
        if key == "leadership":
            out[key] = new[i]
            continue
        excess = card[key] - old[i]
        if key == "firepower":
            excess = excess / share(card["position"]) * share(new_pos)
        out[key] = max(1, min(99, int(round(new[i] + excess))))
    return out

# 补位用的占位卡：G2 模板，**按要补的那个位置取**。它代表「这个位置上有个我们
# 数据库里没有的新人」——卡库只收打过 Major 的人，而现在一线队里确实有还没打过
# Major 的人。
#
# 早先这里写死了 RIFLER G2 的四维、只换 position 字段，于是补出来的「新秀指挥」
# 领导力是 22（步枪手档），比没有指挥还糟；「新秀狙」的稳定也是步枪手的。
# 和 retemplate 那处是同一个错：**换位置就得换整套模板**。
#
# 档位从 G2 降到 G1：占位卡代表的是「从没打过 Major 的人」，而 G2 火力 60 比
# 赛场下半区一半真人还高——实测「补位」因此变成了奖励，补过人的队平均比 HLTV
# 排名高 17 位，没补过的只差 0.7 位（§50）。G1（火 52）才是「我们对他一无所知」
# 那一档，而且它已经很宽容了：全库 G1 是真正打过 Major 的 306 个人。
FILLER_GRADE = 1
MAX_FILLER = 1          # 一支队最多补几个；补 2 个以上的队请在配置里手写

# Supporting 样本向先验收缩的强度。这个数来自 firepower.py 对逐图噪声的估计；
# 这里不是重新拟合一把尺子，只把同一份当前证据投影到 AI 当前卡。
SHRINK_MAPS = 31.0
# 当前赛场的职业首发火力下限。和 firepower.py 的世界定义一致；年龄回退不能
# 把 karrigan/FalleN 这类仍在一线首发的 IGL 算到 20–40。
CURRENT_FIRE_FLOOR = 50


# ------------------------------------------------------------------ 读数据

def load_players():
    return {p["page"]: p for p in
            json.load(open(PLAYERS, encoding="utf-8"))["players"]}


def load_stats():
    if not STATS.exists():
        return {}
    return json.loads(STATS.read_text(encoding="utf-8")).get("players", {})


def _num(v):
    try:
        return float(str(v).replace("%", "").replace("+", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def load_ranking():
    d = json.load(open(RANKING, encoding="utf-8"))
    return d["teams"], (d.get("aliases") or {}), d.get("generated_at", "")


def current_rosters(cards, players):
    """卡上的 `team` -> 当前阵容，剔掉非选手和已退役的。"""
    out = collections.defaultdict(list)
    for c in cards:
        team = c.get("team")
        if not team:
            continue
        p = players.get(c["page"], {})
        roles = {r.lower() for r in (p.get("roles") or [])}
        if roles & NON_PLAYER:
            continue                      # 教练算在队里会顶掉一个真选手的位置
        if (p.get("status") or "").lower() == "retired":
            continue
        out[team.casefold()].append(c)
    return out


def resolve(name, aliases, rosters):
    """HLTV 的队名 -> 我们卡上的队名。"""
    for key in (name, aliases.get(name, "")):
        if key and key.casefold() in rosters:
            return rosters[key.casefold()]
    plain = name.casefold().replace("team ", "")
    for key, v in rosters.items():
        if key.replace("team ", "") == plain:
            return v
    return []


# ------------------------------------------------------------------ 当前化

def current_position(card, players):
    """取 roles 里第一个认得的角色。没有 roles 的人保留卡面位置。

    一条例外:**生涯就是干这个的、而且现在还挂着这个角色，就还算他干这个。**
    blameF 的 roles 是 ['lurk','igl']——按「第一个是主位置」他会变成步枪手，
    BIG 就没指挥了、掉 10 分，可他现实里就是 BIG 的指挥。roles 的顺序不总是
    按重要性排的，这条例外挡掉的正是那种情况。
    """
    roles = [r.lower() for r in (players.get(card["page"], {}).get("roles") or [])]
    for key, pos in (("igl", "IGL"), ("awp", "AWPER")):
        if card["position"] == pos and key in roles:
            return pos
    for r in roles:
        pos = ROLE_MAP.get(r)
        if pos:
            return pos
    return card["position"]


def dedupe_positions(roster, pinned=None):
    """一支队只留一个狙、一个指挥，多出来的降成步枪。

    `roles` 记的是这个人打过的角色，不是他在这支队里的分工——HEROIC 的
    Chr1zN 和 Brollan 都当过指挥，但同一支队里只有一个人在喊。
    留谁:卡面位置本来就是这个位置的优先(生涯就干这个的)，其次比领导力/火力。

    pinned 是人工指定，来自 major_field.json 的 teams.<队>.caller / .awper。
    自动规则大概能对九成，剩下一成靠这个出口——AI 选手页就是拿来找那一成的。
    """
    pinned = pinned or {}
    for pos, field, rank in (
            ("IGL", "caller", lambda c: (c["position"] == "IGL", c["leadership"],
                                         c["experience"])),
            ("AWPER", "awper", lambda c: (c["position"] == "AWPER", c["firepower"]))):
        want = pinned.get(field)
        if want:
            for c in roster:
                hit = c["nickname"].casefold() == want.casefold()
                if hit:
                    c["_pos"] = pos
                elif c["_pos"] == pos:
                    c["_pos"] = "RIFLER"
        same = [c for c in roster if c["_pos"] == pos]
        if len(same) > 1:
            keep = max(same, key=rank)
            for c in same:
                if c is not keep:
                    c["_pos"] = "RIFLER"
    return roster


def age_loss(age):
    if not age or age <= AGE_KNEE:
        return 0.0
    return AGE_RATE * (age - AGE_KNEE) ** AGE_EXP


def to_current(card, players):
    """先只算年龄衰减和候选位置;位置最终定案要等 dedupe_positions 看过全队。"""
    c = dict(card)
    c["_pos"] = current_position(card, players)
    c["_notes"] = []
    c["_filler"] = False
    return c


def _performance_firepower(card, row, scale):
    """把当前竞技证据投影到一张 AI 卡；无可靠证据时保留传入的先验。

    Strong 直接读标尺；Supporting 按图数向先验收缩。IGL 不走这条线——rating
    对指挥的相关性没有随样本增长，测到的是资源分配而不是他的生涯枪法水平。
    """
    prior = card["firepower"]
    out = {"value": prior, "source": "career_age_fallback", "confidence": "low"}
    if card["position"] == "IGL":
        out.update(source="igl_career_prior",
                   why="IGL 的当前 rating 不用于推火力")
        return out
    if not row or not scale:
        out["why"] = "没有可用的当前 S 级证据"
        return out

    fn, lo, hi = scale
    rating = _num(row.get("rating"))
    maps = int(_num(row.get("map_count")) or 0)
    if rating is None or not (lo <= rating <= hi) or maps < 30:
        out["why"] = ("当前证据不在标尺内或不足 30 图"
                      if rating is not None else "当前数据没有 rating")
        out.update(rating=rating, maps=maps)
        return out

    target = int(round(fn(rating)))
    if maps >= 80:
        value, source, confidence = target, "current_performance", "strong"
        why = "%d 图 S 级样本，直接读取当前火力标尺" % maps
    else:
        weight = maps / (maps + SHRINK_MAPS)
        value = int(round(prior + (target - prior) * weight))
        source, confidence = "current_performance_shrunk", "supporting"
        why = "%d 图 S 级样本，按 %.0f%% 权重向生涯先验收缩" % (maps, 100 * weight)
    out.update(value=max(1, min(99, value)), source=source, confidence=confidence,
               why=why, rating=rating, maps=maps, target=target)
    return out


def settle(card, stat=None, scale=None, caller=None):
    """全队仲裁完后落当前位置，再逐维生成 AI 当前卡。

    没传 stat/scale 时保留旧行为，供历史命令和人工阵容使用；队伍快照路径会传入
    当前证据，并把四维来源留在 `_sources`，让页面和 Match 共用同一笔账。
    """
    c = dict(card)
    notes = []
    pos = c.pop("_pos")
    career_lead = card["leadership"]
    if pos != card["position"]:
        c = retemplate(c, pos)
        c["position"] = pos
        notes.append("位置 %s→%s，火 %d→%d 领 %d→%d 稳 %d→%d"
                     % (card["position"], pos, card["firepower"], c["firepower"],
                        card["leadership"], c["leadership"],
                        card["stability"], c["stability"]))

    is_caller = (pos == "IGL") if caller is None else bool(caller)
    if is_caller and pos != "IGL":
        # 指挥狙/指挥枪男保留武器位置，同时用 caller 身份提供领导力。生涯卡本来
        # 就是 IGL 时保留那份履历；否则至少给当前档的 IGL 模板，不凭空造荣誉。
        grade = int(c.get("grade") or 1)
        want = (career_lead if card["position"] == "IGL"
                else max(c["leadership"], G.TEMPLATE["IGL"][grade][1]))
        if want != c["leadership"]:
            notes.append("兼任 caller，领导 %d→%d" % (c["leadership"], want))
            c["leadership"] = want
    c["caller"] = is_caller

    loss = age_loss(card.get("age"))
    if loss > 0.05:
        was = c["firepower"]
        c["firepower"] = max(int(round(was - loss)), CURRENT_FIRE_FLOOR)
        notes.append("%d 岁，火力 %d→%d" % (card["age"], was, c["firepower"]))

    # 当前位置重套 IGL G1 模板也可能把火力放到 45；职业首发地板在所有回退之后、
    # 当前证据之前统一生效。
    if c["firepower"] < CURRENT_FIRE_FLOOR:
        was = c["firepower"]
        c["firepower"] = CURRENT_FIRE_FLOOR
        notes.append("当前职业首发地板 %d→%d" % (was, CURRENT_FIRE_FLOOR))

    perf = _performance_firepower(c, stat, scale)
    if perf["value"] != c["firepower"]:
        was = c["firepower"]
        c["firepower"] = perf["value"]
        notes.append("当前火力 %d→%d：%s" % (was, c["firepower"], perf["why"]))

    c["_notes"] = notes
    c["_filler"] = False
    c["_sources"] = {
        "firepower": perf,
        "leadership": {"source": ("career_evidence_current_caller" if is_caller
                                    else "career_evidence_current_role"),
                       "confidence": "medium"},
        "experience": {"source": "career_evidence", "confidence": "high"},
        "stability": {"source": "career_prior", "confidence": "low",
                      "why": "现有聚合 KAST 不能代表逐图方差"},
    }
    c["overall"] = round(P.overall(c), 1)
    return c


def make_current_player(row, team, age, stat, scale):
    """给卡库外的真人生成 AI 专属低置信先验，不让他进入玩家卡库。"""
    pos = row.get("role") if row.get("role") in G.TEMPLATE else "RIFLER"
    base = G.TEMPLATE[pos][1]
    c = dict(zip(G.ATTRS, base))
    c["firepower"] = max(c["firepower"], 50)
    is_caller = bool(row.get("caller", pos == "IGL"))
    if is_caller and pos != "IGL":
        c["leadership"] = G.TEMPLATE["IGL"][1][1]
    c.update({
        "page": None, "nickname": row["name"], "position": pos,
        "grade": None, "country": "", "team": team, "age": age,
        "majors": 0, "champions": 0, "titles": [],
        "_notes": ["卡库外真人：其生涯没有进入玩家卡库，AI 四维使用透明先验"],
        "caller": is_caller, "_filler": False, "_nocard": True,
    })
    perf = _performance_firepower(c, stat, scale)
    c["firepower"] = perf["value"]
    if perf["source"].startswith("current_performance"):
        c["_notes"].append("当前火力 %d：%s" % (c["firepower"], perf["why"]))
    c["_sources"] = {
        "firepower": perf,
        "leadership": {"source": ("caller_template_g1" if is_caller
                                    else "role_template_g1"), "confidence": "low"},
        "experience": {"source": "unknown_career_g1", "confidence": "low"},
        "stability": {"source": "role_template_g1", "confidence": "low"},
    }
    c["overall"] = round(P.overall(c), 1)
    return c


def make_filler(team, need_pos, n):
    c = dict(zip(G.ATTRS, G.TEMPLATE[need_pos][FILLER_GRADE]))
    c.update({"grade": FILLER_GRADE, "age": 21,
              "page": "_filler_%s_%d" % (team, n), "nickname": "新秀",
              "position": need_pos, "country": "", "team": team,
              "majors": 0, "champions": 0, "titles": [],
              "_notes": ["卡库里没有这个人：只收打过 Major 的选手"], "_filler": True})
    c["overall"] = P.overall(c)
    return c


def fill(roster, team):
    """按位置缺口补人。一支队要一个狙一个指挥，剩下步枪。"""
    have = collections.Counter(c["position"] for c in roster)
    out = list(roster)
    n = 0
    while len(out) < 5:
        n += 1
        if not have["AWPER"]:
            pos = "AWPER"
        elif not have["IGL"]:
            pos = "IGL"
        else:
            pos = "RIFLER"
        have[pos] += 1
        out.append(make_filler(team, pos, n))
    return out


# ------------------------------------------------------------ 候选池(当前世界)

def _pool_spec(cfg):
    pool = dict(cfg.get("candidate_pool") or {"欧洲": 30, "美洲": 10, "亚洲": 5})
    pin = {str(x).casefold() for x in (pool.pop("pin", None) or [])}
    return {k: v for k, v in pool.items() if isinstance(v, int)}, pin


def _age_at(birthday, asof):
    """快照日那天多大。生日缺失就返回 None——别拿卡上的年龄冒充。"""
    if not birthday or not asof:
        return None
    try:
        b = [int(x) for x in str(birthday).split("-")[:3]]
        a = [int(x) for x in str(asof).split("-")[:3]]
    except ValueError:
        return None
    if len(b) < 3 or len(a) < 3:
        return None
    return a[0] - b[0] - ((a[1], a[2]) < (b[1], b[2]))


def build_pool_field(cfg=None):
    """**当前世界的候选池**：快照阵容 + 逐维 AI 当前卡。

    和 `build_ai_field` 的区别不是参数，是**证据来源**：

        build_ai_field   HLTV top100 排名 + 卡上的 `team` 字段 + 猜位置 + G1 占位
        build_pool_field 队伍快照的当前首发 + 队内位置 + 当前竞技证据

    不补占位人是关键。卡库只收打过 Major 的人，而当前世界本来就装得下卡库
    没有的人——The MongolZ 现在首发里有三个从没打过 Major。这里让他们以本人
    身份进来：有 S 级当前证据就生成当前火力，其余维度使用明确标低置信度的 G1
    位置先验。这些值只服务 AI 赛场，不会把人写进玩家卡库。

    名额（`regional_slots`）决定谁入选 32 席，候选池（`candidate_pool`）
    比它大 13 支——余量是留给 VRS 变动的，不是多打几场。
    """
    cfg = cfg if cfg is not None else M.load_config()
    keep, pin = _pool_spec(cfg)
    slots = cfg.get("regional_slots") or {}
    raw = json.loads(SNAPSHOT.read_text(encoding="utf-8")) if SNAPSHOT.exists() else {}
    asof = raw.get("snapshot_date", "")
    card_rows = P.load_cards()
    by_nick = {c["nickname"].casefold(): c for c in card_rows}
    by_page = {c["page"]: c for c in card_rows}
    stats = load_stats()
    try:
        from . import firepower as F
        scale = F.build_scale(cards=card_rows)
    except (ValueError, OSError):
        scale = None

    ranked = {}
    for t in raw.get("teams", []):
        if t.get("vrs_rank"):
            ranked.setdefault(t.get("region") or "?", []).append(t)
    for v in ranked.values():
        v.sort(key=lambda t: t["vrs_rank"])

    picked, seen = [], set()
    for reg, n in keep.items():
        for i, t in enumerate(ranked.get(reg, [])[:n], 1):
            seen.add(t["id"])
            picked.append((t, reg, i))
    for t in raw.get("teams", []):                     # pin 里点名的队掉出去也留着
        if t["id"] not in seen and (t["name"].casefold() in pin
                                    or (t.get("abbr") or "").casefold() in pin):
            reg = t.get("region") or "?"
            after = len(ranked.get(reg, []))
            picked.append((t, reg, after + 1))

    # 区域名额只在五名真实首发完整的队之间顺延。不满五人的队仍保留在候选池
    # 页面里供排查，但不能靠虚构占位人拿走正赛席位；该区下一支完整队递补。
    eligible_seat = {}
    eligible_count = collections.Counter()
    for t, reg, _seat in picked:
        starters = [r for r in t.get("roster", []) if r.get("starter")]
        if len(starters) == 5:
            eligible_count[reg] += 1
            eligible_seat[t["id"]] = eligible_count[reg]

    field = []
    for t, reg, seat in sorted(picked, key=lambda x: x[0].get("vrs_rank") or 9999):
        s = slots.get(reg) or {}
        n3, n2, n1 = s.get("stage3", 0), s.get("stage2", 0), s.get("stage1", 0)
        qseat = eligible_seat.get(t["id"])
        stage = (3 if qseat and qseat <= n3
                 else 2 if qseat and qseat <= n3 + n2
                 else 1 if qseat and qseat <= n3 + n2 + n1 else None)
        roster, real = [], 0
        for r in t.get("roster", []):
            if not r.get("starter"):
                continue
            stat = stats.get(r.get("id") or "")
            base = (by_page.get((stat or {}).get("card_page"))
                    or by_nick.get(r["name"].casefold()))
            age = _age_at(r.get("birthday"), asof)
            if base:
                real += 1
                c = dict(base)
                c["_pos"] = r["role"]
                if age:
                    c["age"] = age
                c = settle(c, stat, scale, r.get("caller", r["role"] == "IGL"))
                c["_nocard"] = False
            else:
                c = make_current_player(r, t["name"], age, stat, scale)
            c["_5e_id"] = r.get("id")
            c["_role_src"] = r.get("role_source")
            roster.append(c)
        field.append({
            "name": t["name"], "id": t["id"], "region": reg, "seat": seat,
            "qualified_seat": qseat, "stage": stage,
            "vrs": t.get("vrs_rank"), "rank": t.get("hltv_rank"),
            "roster": roster, "real": real, "carded": real, "source": "队伍快照",
            "adjust": float(((cfg.get("teams") or {}).get(t["name"]) or {}).get("adjust") or 0.0),
            "gaps": t.get("role_gaps"), "conflicts": t.get("role_conflicts"),
        })
    return field, asof


# ------------------------------------------------------------------ 赛场

def build_ai_field(size=FIELD_SIZE, max_filler=MAX_FILLER, cfg=None):
    """按 HLTV 当前排名取前 size 支能凑齐的队。

    「能凑齐」= 现役非教练队员 >= 5 - max_filler。差得更多的队（FaZe 现在只剩
    三个人）需要在 major_field.json 里手写阵容，不然它这一届就是没进 Major。
    """
    cfg = cfg if cfg is not None else M.load_config()
    cards = P.load_cards()
    players = load_players()
    rosters = current_rosters(cards, players)
    ranking, aliases, asof = load_ranking()
    hand = _hand_rosters(cfg, cards)

    field, skipped = [], []
    for rank, name in enumerate(ranking, 1):
        if len(field) >= size:
            break
        if name.casefold() in hand:
            raw, source = hand[name.casefold()], "手写"
        else:
            raw, source = resolve(name, aliases, rosters), "当前名单"
        spec = (cfg.get("teams", {}).get(name, {}) or {})
        # 逐队可以放宽:FaZe / The MongolZ 这类高人气但卡库只查得到三个人的队,
        # 单独开到 2 个占位。全局放宽会把一堆没人关心的队一起放进来。
        mf = int(spec.get("max_filler", max_filler))
        if len(raw) < 5 - mf:
            skipped.append((rank, name, len(raw)))
            continue
        pinned = {k: spec.get(k) for k in ("caller", "awper")}
        cur = [settle(c) for c in
               dedupe_positions([to_current(c, players) for c in raw[:5]], pinned)]
        team = {"name": name, "rank": rank, "roster": fill(cur, name),
                "source": source, "real": len(cur),
                # 人工层直接加在「分」上的偏移。放在队上而不是各自去读配置,
                # 是为了让这张报表和真正开赛的赛场读同一个数。
                "adjust": float(spec.get("adjust") or 0.0)}
        field.append(team)
    return field, skipped, asof


def _hand_rosters(cfg, cards):
    """major_field.json 里手写的阵容。名字认昵称也认 page，不分大小写；
    写一个卡库里没有的名字就当新秀占位。"""
    index = {}
    for c in cards:
        index.setdefault(c["page"].casefold(), c)
        index.setdefault(c["nickname"].casefold(), c)
    out = {}
    for name, spec in (cfg.get("teams") or {}).items():
        want = spec.get("roster")
        if not isinstance(want, list):
            continue
        got = []
        for w in want:
            c = index.get(w.casefold())
            got.append(c if c else {"_want": w})
        out[name.casefold()] = got
    return out


def entry_of(team, rosters_idx, cohesion_cap):
    """当前真实队固定吃满磨合度；玩家临时队仍由历史关系计算。

    卡库外新人没有 Major 队友历史，若仍按玩家队的 chemistry() 算，会因为“我们
    不知道”而把一支每天训练的真实队判成没有磨合。当前队的差异不靠这项排名，
    它只表达玩家草台班子相对真队的税。
    """
    r = M.entry_rating(team["roster"], rosters_idx, cohesion_cap)
    r = dict(r, chem_raw=max(r["chem_raw"], cohesion_cap),
             cohesion=cohesion_cap, entry=r["base"] + cohesion_cap)
    adj = team.get("adjust") or 0.0
    return dict(r, entry=r["entry"] + adj, adjust=adj) if adj else r


# ------------------------------------------------------------------ 输出

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=float, default=None)
    ap.add_argument("--size", type=int, default=FIELD_SIZE)
    ap.add_argument("--changes", action="store_true", help="只列被改动的选手")
    args = ap.parse_args()

    cfg = M.load_config()
    cap = args.cap if args.cap is not None else float(cfg.get("cohesion_cap", 4.0))
    idx = P.load_rosters()
    pool, asof = build_pool_field(cfg)
    field = [t for t in pool if t.get("stage")][:args.size]

    if args.changes:
        for t in field:
            for c in t["roster"]:
                if c["_notes"]:
                    print("%-20s %-12s %s" % (t["name"], c["nickname"],
                                              " · ".join(c["_notes"])))
        return

    print("AI 赛场 — 区域 VRS 名额（%s），快照首发 + AI 当前四维" % asof)
    print("=" * 78)
    rated = []
    for t in field:
        r = entry_of(t, idx, cap)
        rated.append((r["entry"], t, r))
    rated.sort(key=lambda x: -x[0])
    for i, (e, t, r) in enumerate(rated, 1):
        flag = "" if t["real"] == 5 else "  [AI先验 %d 人]" % (5 - t["real"])
        if t.get("adjust"):
            flag += "  [人工 %+.0f]" % t["adjust"]
        print("%2d  %-20s VRS #%-3s  评分 %5.1f  磨合 %4.1f%s"
              % (i, t["name"], t.get("vrs") or "-", e, r["cohesion"], flag))
        print("      " + "  ".join(
            "%s(%s%s)" % (c["nickname"], c["position"][:3],
                          "*" if c["_notes"] else "") for c in t["roster"]))


if __name__ == "__main__":
    main()
