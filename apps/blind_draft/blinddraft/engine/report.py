# -*- coding: utf-8 -*-
"""命令行的打印层。只把已经算好的东西排版，不做任何计算。

单独一个文件是为了让「改一行输出格式」不必打开引擎——以前 `show_map` 夹在
`compare` 和 `demo` 中间，看着像调参台的一部分。
"""
from . import params as PA
from .tournament import major_field


def show_map(m, indent="    "):
    """一张图的逐人账本；v2 的每一分变化都能拆到底。"""
    out = []
    for detail, side, team, total in ((m.da, "你", m.a, m.sa),
                                      (m.db, "对手", m.b, m.sb)):
        out.append("%s%s %s — 火力聚合 %.1f  战术执行 %+.2f  结构 %+.1f  = %.1f"
                   % (indent, side, team.name,
                      sum(t.weight * t.eff for t in detail),
                      team.tactical, team.structure, total))
        for t in sorted(detail, key=lambda t: -t.weight):
            why = ["状态 %+.1f" % t.form]
            if t.choke:
                why.append("压力 %+.1f" % t.choke)
            if round(t.capped, 1):
                why.append("软顶 %+.1f" % t.capped)
            out.append("%s  %-12s x%.2f  %3d -> %5.1f  %+6.1f = %s%s"
                       % (indent, t.card["nickname"], t.weight,
                          t.card["firepower"], t.eff, t.delta, "，".join(why),
                          "  LIFE GAME" if t.delta >= PA.LIFE_GAME_AT else
                          ("  UNDERPERFORM" if t.delta <= PA.UNDERPERFORM_AT
                           else "")))
    out.append("%s表现差 %+.1f  Map Residual %+.1f（未建模的地图/经济/timing）"
               "  ->  Margin %+.1f  %s"
               % (indent, m.sa - m.sb, m.residual, m.margin,
                  "你赢" if m.winner_a else "对手赢"))
    if (m.sa > m.sb) != m.winner_a:
        out.append("%s  ↳ 表现更好的一方输了——这张图是被未建模因素翻掉的"
                   % indent)
    return "\n".join(out)


def show_run(data):
    """命令行版的一届。"""
    print("=" * 74)
    print("Match Engine v2 — Road to Major   快照 %s" % (data["snapshot"] or "?"))
    print("=" * 74)
    print("你的五个人（Entry %.1f，纯火力口径）:" % data["entry"])
    for c in data["roster"]:
        print("   %-7s %-14s %-16s 火力 %2d 稳定 %2d 经验 %2d 领导 %2d"
              % (c["position"], c["nickname"], c["country"] or "",
                 c["firepower"], c["stability"], c["experience"],
                 c["leadership"]))
    if not data["qualified"]:
        print("\n未取得席位：你比 Stage 1 最弱的一支还弱。")
        return
    print("\n按 Entry 挤进 Stage %d。" % data["stage"])
    for d in data["demoted"]:
        print("   %s 从 Stage %d 掉到 Stage %d" %
              (d["team"], d["from_stage"], d["to_stage"]))
    if data["dropped"]:
        print("   %s 失去席位。" % data["dropped"])
    for leg in data["legs"]:
        print()
        print("%s" % leg["label"])
        print("  对手 %-18s Entry %.1f · VRS %s · 本届 Stage %s"
              % (leg["opponent"]["name"], leg["opponent"]["entry"],
                 leg["opponent"]["vrs"] or "-", leg["opponent"]["stage"]))
        print("  %s  %d:%d   压力 %.1f"
              % ("WIN" if leg["won"] else "LOSS", leg["player_maps"],
                 leg["opponent_maps"], leg["pressure"]))
        for m in leg["maps"]:
            tags = []
            if m["life_game"]:
                g = m["life_game"]
                tags.append("LIFE GAME %s %d→%.0f%s"
                            % (g["nickname"], g["base_firepower"],
                               g["effective_firepower"],
                               "" if g["side"] == "player" else "(对手)"))
            if m["underperform"]:
                u = m["underperform"]
                tags.append("UNDERPERFORM %s %d→%.0f%s"
                            % (u["nickname"], u["base_firepower"],
                               u["effective_firepower"],
                               "" if u["side"] == "player" else "(对手)"))
            v = m["mvp"]
            print("    Map %d  表现 %.1f : %.1f  Residual %+.1f  ->  %s"
                  " · MVP %s %d→%.0f%s%s"
                  % (m["number"], m["player_strength"], m["opponent_strength"],
                     m["residual"], "你赢" if m["player_won"] else "对手赢",
                     v["nickname"], v["base_firepower"],
                     v["effective_firepower"],
                     "" if v["side"] == "player" else "(对手)",
                     ("  " + " · ".join(tags)) if tags else ""))
    print()
    for s in data["stages"]:
        print("Stage %d  %d-%d  %s"
              % (s["stage"], s["wins"], s["losses"],
                 "晋级" if s["advanced"] else "淘汰"))
    print("RUN RESULT  %d-%d · %s"
          % (data["wins"], data["losses"],
             "进入 Playoffs" if data["reached_playoffs"] else "被淘汰"))


def show_field(seed=1):
    """这一届 32 支队是怎么来的：VRS 名额定 Stage，Entry 定层内种子。"""
    field, asof = major_field(seed)
    print("Road to Major 赛场 · 快照 %s" % (asof or "?"))
    print("  Stage 归属由区域 VRS 名额决定；Entry 只排 Stage 内的种子。")
    for stage in (3, 2, 1):
        tier = sorted((t for t in field if t.stage == stage),
                      key=lambda t: -t.entry())
        print("\nStage %d 直邀 %d 支" % (stage, len(tier)))
        for i, t in enumerate(tier, 1):
            print("  种子 %-3d %-18s Entry %6.1f  VRS %-4s HLTV %s"
                  % (i, t.name, t.entry(), t.vrs or "-", t.hltv or "-"))
