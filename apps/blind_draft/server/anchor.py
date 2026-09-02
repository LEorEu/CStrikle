# -*- coding: utf-8 -*-
"""火力打锚台 —— 人工给一小批可信的现役选手定火力,把 1–99 这把尺子钉住。

**为什么是人工,而不是拿 rating 拟合一条线。**

拟合试过了,两次都错在同一个地方:数据先说话,人再去解释它。第一版用分位
对齐,把窄的 rating 分布强行摊成宽的火力分布,中段陡到 rating 差 0.08 要跨
21 点火力;第二版换回归,线是直了,但它只是在复述 5E 的排序,而 5E 的排序
本身还带着一个我们后来才查出来的污染(见 `bdtools/fetch_5e_stats.py` 文件头
第 3 条)。

所以顺序倒过来:**先由人回答「火力 90 是什么水平」,再让公式去拟合这批答案。**
40 个锚点足够让标尺浮出来,而且每一个都能追到一个具体的人和一条理由。

**这一页写的是人工层**(`data/blind_draft/firepower_anchors.json`),不碰任何
生成物。锚点将来是卡牌生成器的输入,不是它的输出。

两个字段要分开填,因为它们回答的是两个问题:

    peak       这个人**现在**是不是处在生涯巅峰?
               只有 peak=True 的人,他的近 12 个月 rating 才能当作
               「这个火力值对应的实测水平」。ax1le 这种伤病后远离一线的人,
               当前数据说明不了他的巅峰。
    firepower  他**巅峰时**的火力应该是多少。对 peak=True 的人这两件事重合,
               对别人则是一个纯粹的履历判断——所以后者不进曲线拟合。
"""
import json
import unicodedata
from datetime import date

from playerdb.paths import BLIND_DRAFT

from blinddraft import cards as C

ANCHOR_PATH = BLIND_DRAFT / "firepower_anchors.json"
SNAP_PATH = BLIND_DRAFT / "team_snapshot.json"
STATS_PATH = BLIND_DRAFT / "5e_player_stats.json"

#: 默认放进来的队伍数(按全球 VRS)。前 15 队 ≈ 75 个首发,打 40 个锚绰绰有余,
#: 而且这些队一年里不可能没有顶级赛事样本——覆盖率实测 100%。
DEFAULT_TEAMS = 15

#: 建议值用的分段折线,**只是提示**,填进去的数以人为准。
#:
#: 1.21 以上的四个点是讨论里直接给的,原样保留、不做平滑:
#:     kyousuke 1.21→86   m0NESY 1.33→90   ZywOo 1.41→94   donk 1.44→96
#: 那一段先平后陡(1.21–1.33 每 0.1 只涨 3.3,1.33–1.44 涨 5.5),因为按当时的
#: 说法 donk/ZywOo 是「论外」——这是人的判断,不是拟合出来的形状,不该抹平。
#:
#: 1.21 以下是延伸出来的,按**中段最陡、底部压缩**:
#:     1.00–1.21 每 0.1 涨 6.4–7.0   0.83–1.00 每 0.1 只涨 4.3–6.0
#: 底部要压是有实测依据的——队内五号位不管队伍强弱都是 0.93–0.97
#: (前 10 队 0.97 / 26–50 名 0.93),顶级赛场的下沿本来就被选择压窄了。
#: rating 0.90 的人不是菜,他是一线队里负责别的事的那个,不能线性掉下去。
HINT = [(0.78, 61), (0.83, 63), (0.90, 66), (1.00, 72), (1.10, 79),
        (1.21, 86), (1.33, 90), (1.41, 94), (1.44, 96), (1.50, 97)]

#: 九档语义。**它是打锚的输出,不是前提**——这里只做提示文案,
#: 等锚点够了要回来按实际打出来的分布改写。
BANDS = [(96, "世代级 · 历史前二"), (92, "超巨巅峰"),
         (88, "最顶级火力 · 能长期扛一线"), (83, "一线明星 / 极强输出手"),
         (77, "强一线"), (70, "顶级赛事正常主力"),
         (62, "一线偏弱 / 二线强手"), (52, "明显偏弱枪位 / 功能型"),
         (0, "枪法是明显短板")]


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace("%", "").replace("+", "").replace(",", ""))
    except ValueError:
        return None


def hint_for(rating, role=None):
    """线性内插 HINT。超出两端就取端点——不外推,外推正是上一轮翻车的地方。

    **指挥不给建议值。** 实测:枪手的「卡面火力 ~ rating」随样本量从 0.41
    爬到 0.67,指挥则在 0.15–0.22 之间原地不动——加样本显不出信号,说明
    本来就没有。少打枪是这个位置的工作内容,不是水平。原样按 rating 推,
    karrigan 会从 66 掉到 47,比 G1 指挥的模板底板还低。指挥的火力只能人判。
    """
    if rating is None or role == "IGL":
        return None
    if rating <= HINT[0][0]:
        return HINT[0][1]
    if rating >= HINT[-1][0]:
        return HINT[-1][1]
    for (x0, y0), (x1, y1) in zip(HINT, HINT[1:]):
        if x0 <= rating <= x1:
            return round(y0 + (y1 - y0) * (rating - x0) / (x1 - x0))
    return None


def band_of(fire):
    if fire is None:
        return ""
    for lo, label in BANDS:
        if fire >= lo:
            return label
    return ""


def _age(birthday, asof):
    try:
        d = date.fromisoformat(str(birthday)[:10])
    except (TypeError, ValueError):
        return None
    return asof.year - d.year - ((asof.month, asof.day) < (d.month, d.day))


def load_anchors() -> dict:
    if not ANCHOR_PATH.exists():
        return {}
    raw = json.loads(ANCHOR_PATH.read_text(encoding="utf-8"))
    return raw.get("anchors", {})


def save_anchors(anchors: dict) -> None:
    """原子写。半个 JSON 会让下一次读取直接崩,而这是人工判断,重打一遍很贵。"""
    payload = {
        "_note": ("火力打锚:人工给可信的现役选手定 1–99 这把尺子。"
                  "**人工层,勿由脚本覆盖。** peak 说的是『他现在是否处在生涯巅峰』,"
                  "只有 peak=true 的人,近 12 个月 rating 才能当作这个火力值对应的"
                  "实测水平;firepower 一律是**巅峰时**的判断。"
                  "键是卡库的 page(没有卡的人用 5e:<id>)。"),
        "count": len(anchors),
        "anchors": dict(sorted(anchors.items())),
    }
    tmp = ANCHOR_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    tmp.replace(ANCHOR_PATH)


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").casefold()


#: 「补缺口」模式看的 rating 区段。每段至少要有 GAP_TARGET 个锚,
#: 否则标尺在那一段就是外推——而外推正是这个项目栽过两次的地方。
GAP_BANDS = [(0.80, 0.90), (0.90, 0.95), (0.95, 1.00), (1.00, 1.05),
             (1.05, 1.10), (1.10, 1.15), (1.15, 1.20), (1.20, 1.30), (1.30, 1.50)]
GAP_TARGET = 3
#: 补缺口时的样本下限。图数太少的人打了锚也不能用来定标尺。
GAP_MIN_MAPS = 40


def band_gaps(rows) -> list:
    """-> [{lo, hi, have, need}],每段现有多少锚、还差多少。"""
    out = []
    for lo, hi in GAP_BANDS:
        have = sum(1 for p in rows
                   if p["fire"] is not None and p["role"] != "IGL"
                   and p["rating"] is not None and lo <= p["rating"] < hi)
        out.append({"lo": lo, "hi": hi, "have": have,
                    "need": max(0, GAP_TARGET - have)})
    return out


def anchored_rows(anchors, by_id, by_page, by_nick) -> list:
    """已存的锚点 + 它们的 rating,用来算区段缺口。和当前视图无关。"""
    stat_by_page = {r["card_page"]: r for r in by_id.values() if r.get("card_page")}
    out = []
    for page, a in anchors.items():
        card = by_page.get(page) or by_nick.get(_fold(page))
        row = stat_by_page.get(page)
        if not card or not row:
            continue
        rating = None
        try:
            rating = float(str(row.get("rating")).replace("+", ""))
        except (TypeError, ValueError):
            pass
        out.append({"fire": a.get("firepower"), "role": card["position"],
                    "rating": rating})
    return out


def build_view(teams: int = DEFAULT_TEAMS, mode: str = "teams") -> dict:
    """-> 候选选手 + 已打的锚 + 拟合用的散点。只读,不写。

    mode="teams" 按全球 VRS 取前 N 支队(默认,适合系统性地过一遍)。
    mode="gaps"  **按 rating 区段补缺口**:哪一段锚点不够就从全池捞人,
                 不管他在哪支队。标尺的有效区间由锚点的 rating 跨度决定,
                 而不是由队伍排名决定——需要补下沿的人往往在 VRS 30 名开外。
    """
    snap = json.loads(SNAP_PATH.read_text(encoding="utf-8"))
    stats = json.loads(STATS_PATH.read_text(encoding="utf-8"))
    by_id = stats["players"]
    cards, _, _ = C.generate()
    by_page = {c["page"]: c for c in cards}
    by_nick = {_fold(c["nickname"]): c for c in cards}
    anchors = load_anchors()

    try:
        asof = date.fromisoformat(str(snap.get("snapshot_date"))[:10])
    except (TypeError, ValueError):
        asof = date.today()

    ranked = sorted((t for t in snap["teams"] if t.get("vrs_rank")),
                    key=lambda t: t["vrs_rank"])
    if mode != "gaps":
        ranked = ranked[:max(1, teams)]

    out = []
    for t in ranked:
        roster = []
        for m in t["roster"]:
            if not m.get("starter"):
                continue
            srow = by_id.get(m["id"]) or {}
            card = by_page.get(m["name"]) or by_nick.get(_fold(m["name"]))
            key = card["page"] if card else "5e:" + m["id"]
            rating = _num(srow.get("rating"))
            saved = anchors.get(key) or {}
            roster.append({
                "key": key,
                "nickname": m["name"],
                "page": card["page"] if card else None,
                "role": m.get("role"),
                "age": _age(m.get("birthday"), asof),
                "grade": card["grade"] if card else None,
                "card_fire": card["firepower"] if card else None,
                "card_pos": card["position"] if card else None,
                "rating": rating,
                "maps": int(_num(srow.get("map_count")) or 0) if srow else 0,
                "adr": _num(srow.get("adr")),
                "kast": _num(srow.get("kast")),
                "kd": _num(srow.get("kd")),
                "hint": hint_for(rating, m.get("role")),
                "peak": saved.get("peak"),
                "fire": saved.get("firepower"),
                "note": saved.get("note", ""),
            })
        # 队内座次按 rating 排:大哥是谁、五号位是谁,是判断巅峰状态的重要背景
        order = sorted((p for p in roster if p["rating"] is not None),
                       key=lambda p: -p["rating"])
        for i, p in enumerate(order, 1):
            p["seat"] = i
        for p in roster:
            p.setdefault("seat", None)
        out.append({"name": t["name"], "vrs": t.get("vrs_rank"),
                    "region": t.get("region"), "roster": roster})

    if mode == "gaps":
        # 全池摊平,按缺口区段挑人:每段先挑图数最足的,凑够 need 的三倍备选,
        # 已经打过锚的人也留着(要能看到那一段现在长什么样)。
        flat = [p for t in out for p in t["roster"]]
        gaps = band_gaps(flat)
        picked, seen = [], set()
        for band in gaps:
            pool = [p for p in flat
                    if p["rating"] is not None and band["lo"] <= p["rating"] < band["hi"]
                    and p["role"] != "IGL" and p["maps"] >= GAP_MIN_MAPS]
            pool.sort(key=lambda p: (p["fire"] is not None, -p["maps"]))
            take = pool[:max(band["need"] * 3, 3)] if band["need"] else pool[:2]
            for p in take:
                if p["key"] not in seen:
                    seen.add(p["key"])
                    picked.append(dict(p, band="%.2f–%.2f" % (band["lo"], band["hi"]),
                                       band_need=band["need"]))
        picked.sort(key=lambda p: (p["rating"] or 0))
        out = [{"name": "缺锚点的区段 · rating %s" % b, "vrs": None, "region": "",
                "roster": [p for p in picked if p["band"] == b]}
               for b in sorted({p["band"] for p in picked})]
        out = [g for g in out if g["roster"]]

    # 拟合用的点:**只收 peak=True 且填了火力的**。别人的火力是履历判断,
    # 和当前 rating 不构成对应关系,混进去会把线拉歪。
    fit = [{"nickname": p["nickname"], "rating": p["rating"], "fire": p["fire"],
            "maps": p["maps"], "role": p["role"]}
           for t in out for p in t["roster"]
           if p["peak"] and p["fire"] is not None and p["rating"] is not None]

    done = sum(1 for t in out for p in t["roster"] if p["fire"] is not None)
    total = sum(len(t["roster"]) for t in out)
    return {"teams": out, "fit": fit, "bands": BANDS, "hint": HINT,
            # 缺口按**已存的全部锚点**算,不按当前视图——否则切模式会让缺口
            # 自己把自己填满,而缺口的意义正是「标尺在哪一段还是外推」。
            "gaps": band_gaps(anchored_rows(anchors, by_id, by_page, by_nick)),
            "mode": mode,
            "snapshot_date": snap.get("snapshot_date"),
            "counts": {"players": total, "anchored": done, "in_fit": len(fit),
                       "saved": len(anchors)},
            "team_count": len(out)}


def put(key: str, peak, firepower, note: str, teams: int = DEFAULT_TEAMS) -> dict:
    """写一个锚。三项全空 = 撤销。

    **键必须是候选集里真实存在的人**,拼错要报错而不是照收。不校验的话
    一个 typo 会写进一条永远不显示的孤儿记录:文件里 count 在涨,页面上
    却一个都没多——这个项目已经栽过好几次这种「数据悄悄去了别处」。
    """
    known = {p["key"] for m in ("teams", "gaps")
             for t in build_view(teams, m)["teams"] for p in t["roster"]}
    if key not in known:
        raise KeyError(key)
    anchors = load_anchors()
    if peak is None and firepower is None and not (note or "").strip():
        anchors.pop(key, None)
    else:
        entry = {}
        if peak is not None:
            entry["peak"] = bool(peak)
        if firepower is not None:
            entry["firepower"] = int(firepower)
        if (note or "").strip():
            entry["note"] = note.strip()
        anchors[key] = entry
    save_anchors(anchors)
    return anchors.get(key, {})
