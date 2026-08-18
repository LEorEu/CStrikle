# -*- coding: utf-8 -*-
"""把 proto_draft.py 的卡与默契数据注进网页模板,产出一个自包含的单文件页面。

    .\.venv\Scripts\python -X utf8 scripts\export_draft_web.py
    .\.venv\Scripts\python -X utf8 scripts\export_draft_web.py 输出.html

模板是 scripts/proto_draft_web.html(里面有 /*__DATA__*/ 占位符)。数据取自
proto_draft.py **整形之后**的卡,所以网页版和命令行版算出来的分逐分一致;
改了 proto_draft.py 的公式,重新跑一次这个脚本即可。
"""
import itertools
import json
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import proto_draft as P   # noqa: E402

TEMPLATE = ROOT / "scripts" / "proto_draft_web.html"
out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ".cache" / "proto_draft_web.html"

cards = P.load_cards()
rosters = P.load_rosters()

rows = [{
    "n": c["nickname"], "p": c["position"][0], "g": c["grade"], "c": c["country"],
    "t": c["team"], "a": c["age"], "m": c["majors"], "w": c["champions"],
    "f": c["firepower"], "l": c["leadership"], "e": c["experience"],
    "s": c["stability"], "o": c["overall"],
    # 卡面第二条属性给哪一项,和命令行版共用同一个跨进程稳定的哈希
    "b": P.SECOND[zlib.crc32(c["page"].encode("utf-8")) % 3][0],
} for c in cards]

pairs = []
for i, j in itertools.combinations(range(len(cards)), 2):
    bonus, info = P.pair_bonus(cards[i], cards[j], rosters)
    if bonus:
        pairs.append([i, j, info[0], info[1]])

data = json.dumps({"cards": rows, "pairs": pairs}, ensure_ascii=False,
                  separators=(",", ":"))

tpl = TEMPLATE.read_text(encoding="utf-8")
if "/*__DATA__*/" not in tpl:
    raise SystemExit(f"{TEMPLATE} 里找不到 /*__DATA__*/ 占位符")
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(tpl.replace("/*__DATA__*/", data), encoding="utf-8")

print(f"{len(rows)} 张卡 / {len(pairs)} 对队友 → {out_path} "
      f"({out_path.stat().st_size / 1024:.0f} KB)")
