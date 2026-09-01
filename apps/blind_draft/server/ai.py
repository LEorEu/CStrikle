# -*- coding: utf-8 -*-
"""AI 对手页的数据装配 —— 只读。

**这一页不提供编辑。** 卡牌页那边人工层是主角(算法算错了要有出口),这边
恰恰相反:AI 的"当前实力"以前只能靠一条手拖的年龄曲线,`blinddraft/ai_teams.py`
自己写着「库里没有任何『这个人现在打得怎么样』的个人数据,所以只能设计,
不能查」——而现在 `5e_player_stats.json` 里有 354 个人的近 12 个月实测数据。
在有证据的地方开一个手调数值的口子,等于把刚拿到的证据又换回骰子。

所以这一页的职责是**把三列摆在一起**,给之后那套映射算法当工作台:

    卡面(生涯巅峰)   ← blinddraft/cards.py,玩家抽到的那张
    现况(AI 用的)    ← 卡面 经 retemplate(位置改判) + age_loss(年龄衰减)
    5E 实测          ← rating / adr / kast / kd / kpr / dpr / hs,近 12 个月

第三列将来要取代第二列里"年龄衰减"那一段,但只取代得了**火力和稳定**:
5E 那套是竞技数据,对领导和经验几乎零信息量,那两维得继续走生涯侧的证据
(Major 次数、冠军、igl_score)。所以对应关系是逐维的,不是整卡替换。

队一级还摆了一个对照:我们算出来的 entry 顺位 vs HLTV 世界排名。
`blinddraft/major.py` 的注释里量过这两者的秩相关只有 0.53——那个数就是
这套映射要改善的东西,所以让它一直显示在页面上。
"""
import json

from playerdb.paths import BLIND_DRAFT, DATA

from blinddraft import ai_teams as A
from blinddraft import cards as C
from blinddraft import draft as P
from blinddraft import major as M

SNAP_PATH = BLIND_DRAFT / "team_snapshot.json"
STATS_PATH = BLIND_DRAFT / "5e_player_stats.json"
IMG5E_PATH = BLIND_DRAFT / "5e_images.json"
IMAGES_PATH = DATA / "images.json"

#: 5E 竞技数据里按数值用的字段。其余(first_blood / first_death / kddiff)是计数,
#: 单独走,不参与"越大越好"的着色。
STAT_NUM = ("rating", "adr", "kast", "kd", "kpr", "dpr", "win_rate")


def _load(path, default=None):
    if not path.exists():
        return default if default is not None else {}
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot_index() -> dict:
    """5eplay 队伍快照,按队名和缩写都建一份索引(都折叠大小写)。"""
    out = {}
    for t in _load(SNAP_PATH).get("teams", []):
        for key in (t.get("name"), t.get("abbr")):
            if key:
                out.setdefault(key.casefold(), t)
    return out


def stats_by_page() -> dict:
    """5E 个人数据,card_page -> 那一行(附带 5e_id,用来取照片)。

    没有 card_page 的行是卡库里查不到的人(从没打过 Major 的新人),
    AI 赛场上他们是 G1 占位卡,对不上号很正常。
    """
    out = {}
    for sid, row in _load(STATS_PATH).get("players", {}).items():
        page = row.get("card_page")
        if page:
            out[page] = dict(row, _id=sid)
    return out


def _num(v):
    try:
        return float(str(v).rstrip("%"))
    except (TypeError, ValueError):
        return None


def _photo(page, srow, img5e, lq):
    """优先 5E 的头像(当前世界的脸),没有就退回 Liquipedia 那套。"""
    if srow:
        p = img5e.get("players", {}).get(srow["_id"])
        if p:
            return "/bd/" + p
    p = lq.get("players", {}).get(page)
    return "/img/" + p if p else ""


def _spearman(pairs) -> float:
    """两个排名的秩相关。样本小(32 队),直接算,不引 scipy。"""
    n = len(pairs)
    if n < 3:
        return 0.0
    d2 = sum((a - b) ** 2 for a, b in pairs)
    return round(1 - 6 * d2 / (n * (n * n - 1)), 3)


def build_view(size=None) -> dict:
    cfg = M.load_config()
    cap = float(cfg.get("cohesion_cap", 4.0))
    idx = P.load_rosters()
    field, skipped, asof = A.build_ai_field(
        size if size is not None else A.FIELD_SIZE, cfg=cfg)

    snap = snapshot_index()
    srows = stats_by_page()
    img5e = _load(IMG5E_PATH)
    lq = _load(IMAGES_PATH, {"players": {}, "flags": {}})
    career = {c["page"]: c for c in P.load_cards()}
    aliases = (_load(DATA / "hltv_top100.json").get("aliases") or {})

    rated = []
    for t in field:
        r = A.entry_of(t, idx, cap)
        rated.append((r["entry"], t, r))
    rated.sort(key=lambda x: -x[0])

    # 两条顺位在同一批队里比较:HLTV 的名次是全球 1..100,这个赛场只取了
    # 其中 32 支,直接拿名次做差会被"中间跳过的队"污染。
    by_hltv = {t["name"]: i for i, (_, t, _) in
               enumerate(sorted(rated, key=lambda x: x[1]["rank"]), 1)}

    teams, ranks = [], []
    covered = total = 0
    for pos, (entry, t, r) in enumerate(rated, 1):
        st = snap.get(t["name"].casefold()) or snap.get(
            (aliases.get(t["name"], "") or "").casefold()) or {}
        logo = img5e.get("teams", {}).get(st.get("id", ""), "")
        roster = []
        for c in t["roster"]:
            srow = srows.get(c["page"])
            base = career.get(c["page"])
            total += 1
            if srow:
                covered += 1
            roster.append({
                "page": c["page"], "nickname": c["nickname"],
                "position": c["position"], "grade": c["grade"],
                "age": c.get("age"), "country": c.get("country", ""),
                "filler": c.get("_filler", False), "notes": c.get("_notes") or [],
                "cur": {k: c[k] for k in C.ATTRS} | {"overall": c["overall"]},
                # 卡面。占位卡在卡库里本来就没有对应的人,给 None 让页面留白,
                # 而不是拿现况去填——那会让"两列一样"看起来像个结论。
                "card": ({k: base[k] for k in C.ATTRS} | {"overall": base["overall"],
                          "position": base["position"], "grade": base["grade"]}
                         if base else None),
                "stat": ({k: _num(srow.get(k)) for k in STAT_NUM}
                         | {"hs_rate": _num(srow.get("hs_rate")),
                            "maps": _num(srow.get("map_count")),
                            "tier": srow.get("tier", ""),
                            "fb": _num(srow.get("first_blood")),
                            "fd": _num(srow.get("first_death"))}
                         if srow else None),
                "photo": _photo(c["page"], srow, img5e, lq),
                "flag": ("/img/" + lq["flags"][c["country"]]
                         if c.get("country") in lq.get("flags", {}) else ""),
            })
        teams.append({
            "name": t["name"], "hltv": t["rank"], "our": pos,
            "hltv_order": by_hltv[t["name"]],
            "delta": by_hltv[t["name"]] - pos,
            "entry": round(entry, 1), "chem": round(r["chem_raw"], 1),
            "cohesion": round(r["cohesion"], 1), "adjust": t.get("adjust") or 0.0,
            "real": t["real"], "source": t["source"],
            "region": st.get("region", ""), "vrs": st.get("vrs_rank"),
            # 这支队在 5eplay 的队伍快照里有没有。两份数据的口径和日期都不同
            # (赛场按 HLTV top100 挑队,快照来自 5eplay,两者差着好几周),
            # 对不上的队不是名字配错了,是那边真的没有这支队——不标出来的话,
            # 页面上只表现为"队标图挂了"。
            "in_5e": bool(st),
            "logo": "/bd/" + logo if logo else "",
            "roster": roster,
        })
        ranks.append((by_hltv[t["name"]], pos))

    return {
        "teams": teams,
        "skipped": [{"rank": rk, "name": nm, "have": n} for rk, nm, n in skipped],
        "asof": asof,
        "cap": cap,
        "rho": _spearman(ranks),
        "coverage": {"with_stats": covered, "total": total},
        "snapshot_date": _load(SNAP_PATH).get("snapshot_date", ""),
        "age_curve": {"knee": A.AGE_KNEE, "rate": A.AGE_RATE, "exp": A.AGE_EXP},
        "stats_window": (_load(STATS_PATH).get("window") or {}).get("value", ""),
        "stats_grade": _load(STATS_PATH).get("grade_label", ""),
    }
