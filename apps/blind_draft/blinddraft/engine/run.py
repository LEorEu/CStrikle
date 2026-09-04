# -*- coding: utf-8 -*-
"""玩家的一整届：选人 -> 插队 -> 三段 Swiss -> 一个 JSON。

这里**只组装，不定规则**。字段和 `bdserver.run.build_run` 对齐，网页要接的
时候不用再翻译一次；`test_player_run.py` 钉着这两边逐字段相等。
"""
import random

from .. import draft as P
from . import params as PA
from .roster import player_cohesion
from .team import Team
from .tournament import insert_player, major_field, run_major


def player_run(nicknames=None, pages=None, seed=1, cfg=None):
    """从选人到淘汰的一整届：VRS 赛场 -> 插队 -> 三段 Swiss -> 玩家路径。

    返回一个 dict，字段和 `bdserver.run.build_run` 对齐，网页要接的时候不用
    再翻译一次。这里只组装，比赛规则全在上面。
    """
    cards = {c["nickname"]: c for c in P.load_cards()}
    if pages:
        by_page = {c["page"]: c for c in P.load_cards()}
        roster = [by_page[str(x)] for x in pages]
    else:
        roster = [cards[n] for n in nicknames]
    me = Team("YOUR TEAM", roster, player_cohesion(roster, cfg), is_player=True)

    field, asof = major_field(seed, cfg)
    stage, shove, full = insert_player(field, me)
    base = {
        "seed": int(seed), "snapshot": asof,
        "entry": round(me.entry(), 1),
        "roster": [{k: c.get(k) for k in
                    ("page", "nickname", "position", "grade", "country",
                     "team", "age", "firepower", "leadership", "experience",
                     "stability")} for c in roster],
        "stage": stage,
        "qualified": stage > 0,
        # v2 没有「全场种子」——Stage 归属由 VRS 名额定，这里给的是玩家 Entry
        # 在 32 支正赛队里的位次，只作参考。
        "entry_rank": sum(1 for t in field if t.entry() > me.entry()) + 1,
        # 位次说的是「排第几」,平均说的是「差多少」。光有位次答不了「第 9 算
        # 强还是算一般」——32 支正赛队本来就都不弱,前后差多少要看这个数。
        "entry_field_avg": round(sum(t.entry() for t in field) / len(field), 1),
        "demoted": [{"team": t.name, "from_stage": a, "to_stage": b}
                    for t, a, b in shove.demoted],
        "dropped": shove.dropped.name if shove.dropped else None,
    }
    if not stage:
        return base | {"outcome": "not_qualified", "wins": 0, "losses": 0,
                       "reached_playoffs": False, "stages": [], "legs": []}

    stages, logs = run_major(full, random.Random(seed))
    legs, stage_rows, alive = [], [], me
    for s in (stage, stage + 1, 3):
        if s > 3:
            break
        teams, adv = stages[s]
        here = next((t for t in teams if t.is_player), None)
        if here is None:
            break
        for rnd, results in logs[s]:
            for r in results:
                if r.a is here or r.b is here:
                    legs.append(_leg_row(r, here, s, rnd))
        advanced = any(t.is_player for t in adv)
        stage_rows.append({"stage": s, "wins": here.w, "losses": here.l,
                           "advanced": advanced})
        if not advanced:
            break
        alive = here
    reached = any(t.is_player for t in stages[3][1])
    wins = sum(1 for x in legs if x["won"])
    return base | {"wins": wins, "losses": len(legs) - wins,
                   "outcome": "playoffs" if reached else "eliminated",
                   "reached_playoffs": reached,
                   "stages": stage_rows, "legs": legs}


def _leg_row(r, me, stage, rnd):
    """一场比赛 -> JSON。玩家永远摆在 a 位，免得面板从对手视角写。"""
    mine_is_a = r.a is me
    opp = r.b if mine_is_a else r.a
    scene = ("2-2 高压生死局" if r.pressure >= PA.PRESSURE["decider"]
             else "晋级 BO3" if r.bo == 3 and r.pressure == PA.PRESSURE["advance"]
             else "淘汰 BO3" if r.bo == 3 else "BO1")
    maps = []
    for i, m in enumerate(r.maps, 1):
        sa, sb = (m.sa, m.sb) if mine_is_a else (m.sb, m.sa)
        da, db = (m.da, m.db) if mine_is_a else (m.db, m.da)
        won = m.winner_a if mine_is_a else not m.winner_a
        mvp, mvp_a = m.mvp
        life, life_a = m.life
        under, under_a = m.under
        side = lambda flag: ("player" if flag == mine_is_a else "opponent")
        me_t, opp_t = (m.a, m.b) if mine_is_a else (m.b, m.a)
        maps.append({
            "number": i,
            "player_strength": round(sa, 1), "opponent_strength": round(sb, 1),
            "player_won": bool(won),
            "residual": round(m.residual if mine_is_a else -m.residual, 1),
            "margin": round(m.margin if mine_is_a else -m.margin, 1),
            # 队伍层的三笔账，网页要摊开给玩家看
            "player_fire": round(sum(t.weight * t.eff for t in da), 1),
            "opponent_fire": round(sum(t.weight * t.eff for t in db), 1),
            "player_tactical": round(me_t.tactical, 2),
            "opponent_tactical": round(opp_t.tactical, 2),
            "player_structure": round(me_t.structure, 1),
            "opponent_structure": round(opp_t.structure, 1),
            # 压力在 v2 是逐人的：这里汇总本图因压力多丢了多少火力
            "player_choke": round(sum(t.choke for t in da), 1),
            "opponent_choke": round(sum(t.choke for t in db), 1),
            "mvp": _roll_json(mvp, side(mvp_a)),
            "life_game": (_roll_json(life, side(life_a))
                          if life.delta >= PA.LIFE_GAME_AT else None),
            "underperform": (_roll_json(under, side(under_a))
                             if under.delta <= PA.UNDERPERFORM_AT else None),
            "players": [_roll_json(t, "player")
                        for t in sorted(da, key=lambda t: -t.weight)],
            "opponents": [_roll_json(t, "opponent")
                          for t in sorted(db, key=lambda t: -t.weight)],
        })
    return {
        "label": "Stage %d · Round %d · %s" % (stage, rnd, scene),
        "stage": stage, "round": rnd, "bo": r.bo, "pressure": r.pressure,
        "opponent": {"name": opp.name, "entry": round(opp.entry(), 1),
                     "vrs": opp.vrs, "stage": opp.stage},
        "won": r.winner is me,
        "player_maps": r.a_maps if mine_is_a else r.b_maps,
        "opponent_maps": r.b_maps if mine_is_a else r.a_maps,
        "maps": maps,
    }


def _roll_json(t, side):
    return {"nickname": t.card["nickname"], "position": t.card["position"],
            "side": side,
            "base_firepower": t.card["firepower"],
            "effective_firepower": round(t.eff, 1),
            "delta": round(t.delta, 1),
            "carry_weight": round(t.weight, 4),
            "why": {"form": round(t.form, 1), "pressure": round(t.choke, 1),
                    "soft_capped": round(t.capped, 1)}}
