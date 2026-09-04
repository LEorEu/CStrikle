# -*- coding: utf-8 -*-
"""命令行入口：`python -m blinddraft.engine [--lab|--major ...]`。

这里只做参数解析和分发，一行计算都没有——想知道某个开关干了什么，直接去
`lab.py` / `audit.py` / `report.py` 看那个函数。
"""
import argparse

from .audit import audit, audit_cards
from .lab import compare, demo, duel, lab, stats, tune
from .report import show_field, show_run
from .roster import roster_cards
from .run import player_run


def main():
    ap = argparse.ArgumentParser(
        prog="python -m blinddraft.engine",
        description="Blind Draft 比赛引擎（设计稿 v0.3）")
    ap.add_argument("--lab", action="store_true", help="设计稿收敛稿结尾列的六项验收")
    ap.add_argument("--compare", action="store_true", help="§9 删胜负骰的代价")
    ap.add_argument("--tune", action="store_true",
                    help="扫 SIGMA_SCALE / TEAM_RHO，看爆冷能不能撑住")
    ap.add_argument("--demo", default=None, metavar="阵容",
                    help="打一场看逐人账本；FIXTURES 的名字或 \"nick,nick,...\"")
    ap.add_argument("--major", default=None, metavar="阵容",
                    help="跑完整一届 Road to Major；同上，也认 page")
    ap.add_argument("--field", action="store_true",
                    help="只看这一届 32 支队的 VRS 名额与层内种子")
    ap.add_argument("--audit", action="store_true",
                    help="列出 VRS 排名和 Entry 差得远的队，人工分辨原因")
    ap.add_argument("--audit-cards", action="store_true",
                    help="AI 当前卡的证据覆盖：谁的四维是猜的，逐队逐人")
    ap.add_argument("--thin-only", action="store_true",
                    help="--audit-cards 只印薄数据/无数据两张名单")
    ap.add_argument("--stats", action="store_true",
                    help="整届分布：进 Playoffs 的概率、按实力差的强队胜率")
    ap.add_argument("--duel", nargs=2, type=float, metavar=("HIGH", "LOW"),
                    help="两个 Entry 之间的胜率锚（实测，不是算出来的）")
    ap.add_argument("--duel-runs", type=int, default=20000)
    ap.add_argument("--label", default=None, help="--demo / --major 的队名")
    ap.add_argument("--runs", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=5)
    args = ap.parse_args()
    if args.audit_cards:
        audit_cards(args.thin_only)
    elif args.audit:
        audit()
    elif args.duel:
        duel(args.duel[0], args.duel[1], args.duel_runs)
    elif args.stats:
        stats(args.runs if args.runs != 4000 else 200)
    elif args.field:
        show_field(args.seed)
    elif args.major:
        show_run(player_run(pages=[c["page"] for c in roster_cards(args.major)],
                            seed=args.seed))
    elif args.tune:
        tune(args.runs)
    elif args.compare:
        compare(args.runs)
    elif args.demo:
        demo(args.demo, args.seed, args.label)
    else:
        lab(args.runs)


if __name__ == "__main__":
    main()
