# -*- coding: utf-8 -*-
"""Blind Draft 比赛引擎 —— 四维各干一件事，一张图 11 个随机数。

落地的是设计稿 `比赛引擎_v0.3.md`。v1（`blinddraft.match`）已退役删除，
`lab.compare()` 画的那条历史曲线只剩一个常量。§15 的 Pipeline：

                     Firepower
                         │
                每人唯一一次 Roll          ← 10 个 Player RNG   roll.py
                         │
              ┌──────────┴─────────┐
              │                    │
          Stability            Pressure
         定义分布形状          Experience
              │                    │
              └──────────┬─────────┘
                         ↓
                Effective Firepower
                         ↓
                 固定角色权重聚合          ← 顺位按卡面定死（§4.2） team.py
                         ↓
                  Team Firepower
                         ↓
                  Leadership              ← 团队执行，按胜率反推（§9.2）
                  Chem / Structure
                         ↓
                 Team Performance
                         ↓
              + Map Residual              ← 第 11 个 RNG（§13）    play.py
                         ↓
                Final Map Margin
                         ↓
                  Margin > 0 获胜

和 v1 的五条硬差别：

  §4.1  Entry 不再有 Leadership/Experience/Stability 各 20% 的静态权重。
        Entry 就是「这五个人纸面有多能打」，量纲因此和 v1 完全不同
        （≈80 而不是 ≈65），两套 Entry 数字**不可直接比较**。
  §6    Stability 不再是对称正态的宽度，而是**兑现率**：决定分布往哪边偏、
        两条尾巴各有多长。高稳定的人正向结果更常见但幅度温和；低稳定的人
        更常打不出来，可正向尾巴更长——LIFE GAME 从这里来。
  §8    Pressure/Experience 不掷第二个骰子，只扭曲同一次 Player Roll，
        而且**逐人**发生，不再有队伍级 CHOKE 罚分。
  §12   Team Shared Form 退役（v1 的 TEAM_FORM_SHARE=0.65）。
  §13   最终 Bernoulli 胜负骰退役，换成 Map Residual：它代表这版引擎没有
        展开模拟的地图级内容，**不参与 Player Story**。

第一版原型曾按更早的复盘把 §13 那层也删掉，直接比 Team Performance 大小。
实测证明不行：+5 分就 89.7%、+10 分 99.4%，整届 Major 退化成按 Entry 排序的
表格。`lab.tune()` 里那张「三选二」的表就是这条结论的出处，设计稿 §13.5
采纳了它。

拆成一个包之前这些全在一个 1492 行的 `proto_match_v2.py` 里，于是「改一行
输出格式」和「改一条胜率系数」打开的是同一个文件。现在一个文件一件事：

    params.py       全部系数，以及由系数直接导出的曲线。**参数只有这一处**
    roll.py         一个人一张图的那一个随机数（§6 / §8）
    team.py         Team：静态 Entry + 五个 Roll 聚合成队伍强度（§4/§5/§9）
    play.py         一张图 / 一场 BO：Margin 与 Map Residual（§13）
    tournament.py   赛制外壳：赛场、三段 Swiss、玩家插队（§1~§2）
    roster.py       引擎与卡库之间唯一的接口；玩家磨合度也在这
    probes.py       形状受控的假队伍，只给验收和调参用
    run.py          玩家的一整届 -> 一个 JSON（网页和命令行共用）
    report.py       命令行打印层，只排版不算数
    lab.py          验收台与调参台（--lab / --tune / --duel / --stats）
    audit.py        两张只读审计表（--audit / --audit-cards）
    __main__.py     `python -m blinddraft.engine`

这个 `__init__` 只做转发，没有任何实现。外面一律
`from blinddraft import engine as V2`，不必知道东西具体在哪个文件里——
以后再切文件也不会波及调用方。
"""
from .params import (CHOKE_AMP, LIFE_GAME_AT, MAP_SCALE, NO_AWP_PENALTY,
                     NO_IGL_TACTICAL, PRESSURE, P_UP_AT_50, P_UP_AT_90,
                     REST_WEIGHT, SIGMA_DOWN_AT_50, SIGMA_DOWN_AT_90,
                     SIGMA_SCALE, SIGMA_UP_AT_50, SIGMA_UP_AT_90,
                     SOFT_CAP_AT, SOFT_CAP_RATE, STAR_WEIGHTS,
                     TACTICAL_AT_65, TACTICAL_AT_96, TACTICAL_CLAMP,
                     TEAM_RHO, UNDERPERFORM_AT, V1_WIN_SCALE, p_up, sigma_down,
                     sigma_up, soft_cap, tactical)
from .roll import NORM, Roll, form_delta, under_pressure
from .team import Team, entry_of
from .play import MapResult, MatchResult, map_residual, play_map, play_match
from .tournament import (FIELD_SIZE, STAGE_LOSSES, STAGE_WINS, Shove,
                         format_of, insert_player, major_field,
                         mid_stage_order, pair_group, run_major, run_stage)
from .roster import (FIXTURES, named_team, player_cohesion, roster_cards,
                     roster_team)
from .probes import entry_probe, fake_card, probe_team
from .run import player_run
from .report import show_field, show_map, show_run
from .lab import compare, demo, duel, lab, stats, tune, win_rate
from .audit import audit, audit_cards, card_bucket

__all__ = [
    # 系数（只读；要扫描或改写它们请直接用 `engine.params`，见那份文件的说明）
    "CHOKE_AMP", "LIFE_GAME_AT", "MAP_SCALE", "NO_AWP_PENALTY",
    "NO_IGL_TACTICAL", "PRESSURE", "P_UP_AT_50", "P_UP_AT_90", "REST_WEIGHT",
    "SIGMA_DOWN_AT_50", "SIGMA_DOWN_AT_90", "SIGMA_SCALE", "SIGMA_UP_AT_50",
    "SIGMA_UP_AT_90", "SOFT_CAP_AT", "SOFT_CAP_RATE", "STAR_WEIGHTS",
    "TACTICAL_AT_65", "TACTICAL_AT_96", "TACTICAL_CLAMP", "TEAM_RHO",
    "UNDERPERFORM_AT", "V1_WIN_SCALE",
    "p_up", "sigma_down", "sigma_up", "soft_cap", "tactical",
    # 一次 Roll / 一支队 / 一张图
    "NORM", "Roll", "form_delta", "under_pressure",
    "Team", "entry_of",
    "MapResult", "MatchResult", "map_residual", "play_map", "play_match",
    # 赛事外壳
    "FIELD_SIZE", "STAGE_LOSSES", "STAGE_WINS", "Shove", "format_of",
    "insert_player", "major_field", "mid_stage_order", "pair_group",
    "run_major", "run_stage",
    # 取阵容 / 探针 / 玩家的一届
    "FIXTURES", "named_team", "player_cohesion", "roster_cards", "roster_team",
    "entry_probe", "fake_card", "probe_team", "player_run",
    # 命令行那一侧
    "show_field", "show_map", "show_run",
    "compare", "demo", "duel", "lab", "stats", "tune", "win_rate",
    "audit", "audit_cards", "card_bucket",
]
