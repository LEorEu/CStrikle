# -*- coding: utf-8 -*-
"""Blind Draft — AI 对手用「当前状态」，不是「生涯巅峰」

这是和抽卡那边**故意分叉**的一层，分叉点只有一个：

    玩家抽到的卡  = 这个人生涯最好的样子（played_role + 巅峰四维）
    赛场上的 AI  = 这支队现在的样子（roles + 当前阵容 + 年龄衰减）

为什么必须分叉：卡库把 magixx 判成步枪手，理由写在
`player_overrides.json` 里——「该届夺冠时队内指挥另有其人，他的生涯代表位置
是步枪手，后期才接手指挥」。这对抽卡完全正确；但 2026 年的 Spirit 里
magixx 就是在喊战术的那个人。同一张卡被两个系统用，而两个系统要的时间点不同。

三条口径，数据都是现成的：

  阵容   卡上的 `team` 字段（当前所属队），剔掉教练/领队/解说和已退役的人
  位置   players.json 的 `roles`（当前角色）。它是有序的，第一个是主位置
  排名   data/hltv_top100.json 是**当前 HLTV 世界队伍排名**,不是选手榜。
         设计稿 §2 一直写着「当前 VRS 种子无法还原」——其实它一直在库里。

唯一凭空定的是年龄衰减曲线：库里没有任何「这个人现在打得怎么样」的个人数据
（top20 是历年个人奖，top100 是队伍排名），所以只能设计，不能查。

不改卡库、不改 `gen_draft_cards.py`、不写 `data/`（只读）。
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_draft_cards as G          # 只读:借它的位置模板,不改它
import proto_draft as P
import proto_major as M

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RANKING = os.path.join(ROOT, "data", "hltv_top100.json")
PLAYERS = os.path.join(ROOT, "data", "players.json")

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
# `gen_draft_cards.build_card` 的注释早就写明了这条：「位置的人工修正必须**在套
# 模板之前**生效；放在最后 update 只会换掉标签，四维仍旧来自被否掉的那套模板」。
# 这一层原本正是那个错的做法——只把领导力换成 IGL 档，火力照抄步枪手的，于是
# 造出 Magisk 火 90 / 领 90 这种卡（全库 648 张里，火≥85 且领≥80 的有 0 张）。
# 生成器管这叫**六边形怪物**（`gen_draft_cards.py:293`、设计稿 §11.1）。
#
# 生成器的解法照抄过来：档位模板决定水平，履历只在**档内**拉开 ±6 分，而
# **IGL 只继承 0.4 倍的火力履历**——「明星履历 + IGL 模板」不许叠加。
IGL_FIRE_SHARE = 0.4        # 和 gen_draft_cards.py:295 是同一个数


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


# ------------------------------------------------------------------ 读数据

def load_players():
    return {p["page"]: p for p in
            json.load(open(PLAYERS, encoding="utf-8"))["players"]}


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


def settle(card):
    """全队仲裁完之后，把位置落到卡上，领导力跟着换。"""
    c = dict(card)
    notes = []
    pos = c.pop("_pos")
    if pos != card["position"]:
        c = retemplate(c, pos)
        c["position"] = pos
        notes.append("位置 %s→%s，火 %d→%d 领 %d→%d 稳 %d→%d"
                     % (card["position"], pos, card["firepower"], c["firepower"],
                        card["leadership"], c["leadership"],
                        card["stability"], c["stability"]))

    loss = age_loss(card.get("age"))
    if loss > 0.05:
        was = c["firepower"]
        c["firepower"] = max(int(round(was - loss)), 1)
        notes.append("%d 岁，火力 %d→%d" % (card["age"], was, c["firepower"]))

    c["_notes"] = notes
    c["_filler"] = False
    c["overall"] = P.overall(c)
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
    r = M.entry_rating(team["roster"], rosters_idx, cohesion_cap)
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
    field, skipped, asof = build_ai_field(args.size, cfg=cfg)

    if args.changes:
        for t in field:
            for c in t["roster"]:
                if c["_notes"]:
                    print("%-20s %-12s %s" % (t["name"], c["nickname"],
                                              " · ".join(c["_notes"])))
        return

    print("AI 赛场 — 按 HLTV 世界排名（%s），当前阵容 + 当前位置 + 年龄衰减" % asof)
    print("=" * 78)
    rated = []
    for t in field:
        r = entry_of(t, idx, cap)
        rated.append((r["entry"], t, r))
    rated.sort(key=lambda x: -x[0])
    for i, (e, t, r) in enumerate(rated, 1):
        flag = "" if t["real"] == 5 else "  [补 %d 人]" % (5 - t["real"])
        if t.get("adjust"):
            flag += "  [人工 %+.0f]" % t["adjust"]
        print("%2d  %-20s HLTV #%-3d  评分 %5.1f  默契 %4.1f%s"
              % (i, t["name"], t["rank"], e, r["chem_raw"], flag))
        print("      " + "  ".join(
            "%s(%s%s)" % (c["nickname"], c["position"][:3],
                          "*" if c["_notes"] else "") for c in t["roster"]))
    print()
    print("跳过（现役队员不足，需要在 major_field.json 里手写阵容）:")
    for rank, name, n in skipped[:12]:
        print("   HLTV #%-3d %-22s 只有 %d 人" % (rank, name, n))


if __name__ == "__main__":
    main()
