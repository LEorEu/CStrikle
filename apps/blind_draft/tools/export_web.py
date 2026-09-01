# -*- coding: utf-8 -*-
"""把 blinddraft/draft.py 的卡与默契数据注进网页模板,产出一个自包含的单文件页面。

    python -m bdtools.export_web
    python -m bdtools.export_web 输出.html

模板是 apps/blind_draft/templates/draft_web.html(里面有 /*__DATA__*/ 占位符)。数据取自
blinddraft/draft.py 读到的**已提交的 v6 卡(不再做任何加工)**,所以网页版和命令行版算出来的分逐分
一致;改了 blinddraft/draft.py 的公式,重新跑一次这个脚本即可。

卡面要展示的球探项和身份线索也在这里算好(它们由 page 的稳定哈希决定,不该在
JS 里重写一遍),网页只负责显示。
"""
import itertools
import json
import sys
from pathlib import Path

from playerdb.paths import ROOT

from blinddraft import draft as P

TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "draft_web.html"
DEFAULT_OUT = ROOT / ".cache" / "proto_draft_web.html"


def build(out_path: Path) -> Path:
    cards = P.load_cards()
    rosters = P.load_rosters()

    rows = []
    for c in cards:
        attr = P.scout_attr(c)
        rows.append({
            "n": c["nickname"], "p": c["position"][0], "g": c["grade"],
            "c": c["country"], "t": c["team"], "a": c["age"], "m": c["majors"],
            "ch": c["champions"],
            "f": c["firepower"], "l": c["leadership"], "e": c["experience"],
            "s": c["stability"], "o": c["overall"],
            "sa": P.ATTR_CN[attr], "sv": c[attr],     # 球探报告给的那一维
            "ic": P.identity_clue(c),                  # 身份线索(俱乐部/Major/年龄)
        })

    pairs = []
    for i, j in itertools.combinations(range(len(cards)), 2):
        bonus, info = P.pair_bonus(cards[i], cards[j], rosters)
        if bonus:
            # info[0] 是两人一共同队几届(chemistry 的 >=5 加成用的是这个数),
            # 但阵容标签要的是「在被点名的那支队一起打了几届」——两人先后待过两支队时
            # 这两个数不一样(dev1ce + Xyp9x 一共 15 届,其中 astralis 8 届)。
            shared = rosters[cards[i]["page"]] & rosters[cards[j]["page"]]
            same = sum(1 for _, t in shared if t == info[1])
            pairs.append([i, j, info[0], info[1], same])

    data = json.dumps({
        "cards": rows, "pairs": pairs,
        "budget": P.BUDGET, "slots": P.SLOTS, "turns": P.TURNS,
        "saveRate": P.SAVE_RATE, "saveCap": P.SAVE_CAP,
        "scoutWidth": list(P.SCOUT_WIDTH), "scoutPos": list(P.SCOUT_POS),
        "marketRoll": [list(x) for x in P.MARKET_ROLL],
        "gradeW": P.GRADE_WEIGHT, "freeW": P.FREE_AGENT_WEIGHT, "vetW": P.VETERAN_WEIGHT,
        "needBoost": P.NEED_BOOST, "mateBoost": P.MATE_BOOST,
        "quota": P.POSITION_QUOTA, "fullPenalty": P.FULL_PENALTY,
    }, ensure_ascii=False, separators=(",", ":"))

    tpl = TEMPLATE.read_text(encoding="utf-8")
    if "/*__DATA__*/" not in tpl:
        raise SystemExit(f"{TEMPLATE} 里找不到 /*__DATA__*/ 占位符")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(tpl.replace("/*__DATA__*/", data), encoding="utf-8")

    print(f"{len(rows)} 张卡 / {len(pairs)} 对队友 → {out_path} "
          f"({out_path.stat().st_size / 1024:.0f} KB)")
    return out_path


# 包装成函数、放进 main guard,是因为这个模块以前一 import 就落盘。拆包之后
# 「把每个模块 import 一遍」是最基本的冒烟检查,而一个会写文件的 import
# 会让那种检查本身产生副作用。
if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT)
