# -*- coding: utf-8 -*-
"""M2 玩家 Run 的结构化装配。

网页只提交五个 player page 和随机种子；选卡真值、AI 赛场、Entry、对手选择、
Form Roll 和压力机制全部在 Python 这一侧完成。前端不复制任何比赛公式。
"""
import random

from blinddraft import draft as P
from blinddraft import major as M
from blinddraft import match as X


def _card_row(c):
    return {k: c.get(k) for k in (
        "page", "nickname", "position", "grade", "country", "team", "age",
        "firepower", "leadership", "experience", "stability", "overall")}


def _standout(entry):
    """(Roll, 是不是玩家这边) -> JSON。"""
    t, mine = entry
    return dict(_roll_row(t), side="player" if mine else "opponent")


def _roll_row(t):
    """一个人这张图的火力账本：变了多少，以及每一分变化来自哪里。

    team + solo + exp_gain + lead_gain + capped == delta，前端直接摊开显示，
    不需要自己再推一遍公式。
    """
    return {
        "nickname": t.card["nickname"],
        "position": t.card["position"],
        "base_firepower": t.card["firepower"],
        "effective_firepower": round(t.eff, 1),
        "delta": round(t.delta, 1),
        "carry_weight": round(t.weight, 4),
        "swing": round(t.sigma, 2),            # σ，由 Stability 决定
        "why": {"team_form": round(t.team, 1),
                "own_form": round(t.solo, 1),
                "leadership_saved": round(t.lead_gain, 1),
                "experience_saved": round(t.exp_gain, 1),
                "soft_capped": round(t.capped, 1)},
    }


def _match_row(r, label, stage, rnd):
    """玩家已被放在 a 位的 MatchResult -> JSON。"""
    won = r.winner is r.a
    maps = []
    for i, m in enumerate(r.maps, 1):
        maps.append({
            "number": i,
            "player_strength": round(m.sa, 1),
            "opponent_strength": round(m.sb, 1),
            "player_won": bool(m.winner_a),
            "win_probability": round(m.p, 4),
            # 三条叙事各有各的口径，见 match.MapResult。mvp 一定有，
            # life_game / underperform 过阈值才出现，且可能落在对手身上。
            "mvp": _standout(m.mvp),
            "life_game": (_standout(m.life)
                          if m.life[0].delta >= X.LIFE_GAME_AT else None),
            "underperform": (_standout(m.under)
                             if m.under[0].delta <= X.UNDERPERFORM_AT else None),
            # 十个人的完整账本，按 Carry 顺位排。标签只是它的摘要。
            "players": [_roll_row(t) for t in
                        sorted(m.da, key=lambda t: -t.weight)],
            "opponents": [_roll_row(t) for t in
                          sorted(m.db, key=lambda t: -t.weight)],
            "player_fire": round(X.fire_sum(m.da), 1),
            "opponent_fire": round(X.fire_sum(m.db), 1),
            # 指挥这张图实际换来多少队伍强度（救回的火力已按 Carry 权重折算）。
            "leadership_gain": round(X.lead_effect(m.da), 2),
            "opponent_leadership_gain": round(X.lead_effect(m.db), 2),
        })
    return {
        "label": label, "stage": stage, "round": rnd,
        "bo": r.bo, "pressure": r.pressure,
        "opponent": {"name": r.b.name, "entry": round(r.b.baseline(), 1)},
        "pre_match_win_probability": round(r.pre, 4),
        "won": won, "player_maps": r.a_maps, "opponent_maps": r.b_maps,
        "player_pressure_penalty": round(r.a.choke(r.pressure), 2),
        "opponent_pressure_penalty": round(r.b.choke(r.pressure), 2),
        "maps": maps,
    }


def _label(stage, rnd, result):
    if result.pressure >= X.PRESSURE_DECIDER:
        scene = "2-2 高压生死局"
    elif result.bo == 3 and result.before[0] == 2:
        scene = "晋级 BO3"
    elif result.bo == 3:
        scene = "淘汰 BO3"
    else:
        scene = "BO1"
    return "Stage %d · Round %d · %s" % (stage, rnd, scene)


def build_run(pages, seed=1):
    """跑玩家在真实三段 Swiss 里的路径并返回 JSON；不写文件。"""
    pages = [str(p) for p in pages]
    if len(pages) != P.SLOTS or len(set(pages)) != P.SLOTS:
        raise ValueError("阵容必须是五张不重复的玩家卡")
    cards = P.load_cards()
    by_page = {c["page"]: c for c in cards}
    missing = [p for p in pages if p not in by_page]
    if missing:
        raise KeyError("卡库里没有：%s" % "、".join(missing))

    roster = [by_page[p] for p in pages]
    cfg = M.load_config()
    cap = float(cfg.get("cohesion_cap", M.COHESION_CAP))
    rosters = P.load_rosters()
    field = M.make_field(random.Random(seed), cfg, rosters, cap)
    player = M.Entry("YOUR TEAM", roster, M.entry_rating(roster, rosters, cap),
                     is_player=True)
    rank, shove, inserted = M.insert_player(field, player)
    base = {
        "seed": int(seed), "roster": [_card_row(c) for c in roster],
        "entry": round(player.entry, 1), "projected_seed": rank,
        "qualified": rank <= M.FIELD_SIZE,
        "stage": M.stage_of(rank),
        "field": M.field_label(cfg, field),
        "demoted": [{"team": t.name, "from_stage": was, "to_stage": now}
                     for t, was, now in shove.demoted],
        "dropped": shove.dropped.name if shove.dropped else None,
    }
    if rank > M.FIELD_SIZE:
        return base | {"wins": 0, "losses": 0, "outcome": "not_qualified",
                       "reached_playoffs": False, "stages": [], "legs": []}

    stages, logs = X.run_major(inserted, random.Random(seed), cap)
    rows, stage_rows = [], []
    for stage in (1, 2, 3):
        teams, advancers = stages[stage]
        me = next((t for t in teams if t.is_player), None)
        if me is None:
            continue
        for rnd, results in logs[stage]:
            for result in results:
                view = (result if result.a is me else X._flip(result)
                        if result.b is me else None)
                if view is not None:
                    rows.append(_match_row(view, _label(stage, rnd, view), stage, rnd))
        advanced = me in advancers
        stage_rows.append({"stage": stage, "wins": me.w, "losses": me.l,
                           "advanced": advanced})
        if not advanced:
            break
    reached = any(t.is_player for t in stages[3][1])
    wins = sum(leg["won"] for leg in rows)
    return base | {"wins": wins, "losses": len(rows) - wins,
                   "outcome": "playoffs" if reached else "eliminated",
                   "reached_playoffs": reached, "stages": stage_rows, "legs": rows}
