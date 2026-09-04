# -*- coding: utf-8 -*-
"""从卡库取真实阵容：昵称/page -> 五张卡 -> 一支队。

这里是引擎和卡库之间**唯一**的接口。玩家临时队的磨合度也在这儿算，因为
`/play` 和命令行必须是同一个口径——它们曾经不是（见 `player_cohesion`）。
"""
from .. import draft as P
from .. import major as M
from .team import Team


def named_team(label, nicknames, cards=None):
    cards = cards or {c["nickname"]: c for c in P.load_cards()}
    return Team(label, [cards[n] for n in nicknames], 0.0, is_player=True)


def roster_cards(spec):
    """"nick,nick,..." 或 FIXTURES 的名字 -> 五张卡。认昵称也认 page，不分大小写。

    从 v1 的 `pick_roster` 搬过来。有它才能拿任意一支真实阵容对着引擎跑，
    不然能上场的只有写死的 FIXTURES 那三支。
    """
    names = FIXTURES.get(spec)
    index = {}
    for c in P.load_cards():
        index.setdefault(c["page"].casefold(), c)
        index.setdefault(c["nickname"].casefold(), c)
    want = list(names) if names else [w.strip() for w in spec.split(",") if w.strip()]
    bad = [w for w in want if w.casefold() not in index]
    if bad:
        raise KeyError("卡库里没有：%s" % "、".join(bad))
    if len(want) != P.SLOTS:
        raise ValueError("要正好 %d 个人，给了 %d 个" % (P.SLOTS, len(want)))
    return [index[w.casefold()] for w in want]


def player_cohesion(roster, cfg=None):
    """玩家临时队的磨合度 = min(裸默契, COHESION_CAP)。

    以前这里写死 0.0，而 AI 一律吃满 cap——于是 `chemistry()` 算出来的那些东西
    （真队友重聚、同国、同代、两个指挥抢话）在选人页上写得清清楚楚，**却完全
    没有进比赛**。玩家页面显示「默契 −2.0」，引擎按 0 打；追一对真队友和不追
    打出来一模一样。v1 是算的，v2 接管 `/play` 时漏了。

    cap 调的是「草台班子税」有多重（§45.6），不是把玩家的默契一笔抹掉。
    """
    cfg = cfg if cfg is not None else M.load_config()
    cap = float(cfg.get("cohesion_cap", M.COHESION_CAP))
    return M.entry_rating(roster, M.load_rosters_cached(), cap)["cohesion"]


def roster_team(spec, label=None):
    """任意阵容 -> 一支玩家队。默契按 `/play` 的口径算，两处不许不一样。"""
    roster = roster_cards(spec)
    return Team(label or spec, roster, player_cohesion(roster), is_player=True)


# ------------------------------------------------------ 固定测试阵容
# 1.txt（`docs/blind-draft/archive/讨论/`）结尾点名要的三支。
# 存成常量，任何系数改动都对着同一批人跑。
FIXTURES = {
    "donk carry": ["donk", "molodoy", "tN1R", "Kvem", "spaze"],
    "ZywOo carry": ["ZywOo", "Kvem", "spaze", "tN1R", "molodoy"],
    "五个普通职业哥": ["susp", "allu", "KHRN", "VINI", "pronax"],
}
