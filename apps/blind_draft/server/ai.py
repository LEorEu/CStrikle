# -*- coding: utf-8 -*-
"""AI 对手页的数据装配 —— 只读。

**这一页不提供编辑。** 卡牌页那边人工层是主角(算法算错了要有出口),这边
恰恰相反:AI 的"当前实力"以前只能靠一条手拖的年龄曲线,`blinddraft/ai_teams.py`
自己写着「库里没有任何『这个人现在打得怎么样』的个人数据,所以只能设计,
不能查」——而现在 `5e_player_stats.json` 已有候选池近 12 个月的实测数据。
在有证据的地方开一个手调数值的口子,等于把刚拿到的证据又换回骰子。

所以这一页的职责是**把三列摆在一起**,给之后那套映射算法当工作台:

    卡面(生涯巅峰)   ← blinddraft/cards.py,玩家抽到的那张
    现况(AI 用的)    ← 当前角色 + 5E 当前火力 + 逐维生涯先验
    5E 实测          ← rating / adr / kast / kd / kpr / dpr / hs,近 12 个月

5E 当前证据现在只接管 Firepower；Leadership / Experience 继续走生涯证据，
Stability 在取得逐图方差前保留低置信先验。对应关系是逐维的，不是整卡替换。

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


def stats_index() -> tuple:
    """5E 个人数据。返回 (按 5e_id, 按 card_page) 两份索引。

    **主键是 5e_id**,因为当前世界里本来就有卡库没有的人——53 个候选池首发
    没有 card_page,按 page 索引就整批查不到。card_page 那份只是给还在按卡
    走的老路径用的桥。
    """
    by_id, by_page = {}, {}
    for sid, row in _load(STATS_PATH).get("players", {}).items():
        r = dict(row, _id=sid)
        by_id[sid] = r
        if row.get("card_page"):
            by_page[row["card_page"]] = r
    return by_id, by_page


def _num(v):
    try:
        return float(str(v).rstrip("%"))
    except (TypeError, ValueError):
        return None


def _photo(page, sid, img5e, lq):
    """优先 5E 的头像(当前世界的脸),没有就退回 Liquipedia 那套。"""
    if sid:
        p = img5e.get("players", {}).get(sid)
        if p:
            return "/bd/" + p
    p = lq.get("players", {}).get(page) if page else None
    return "/img/" + p if p else ""


def _spearman(pairs) -> float:
    """两个排名的秩相关。样本小(32 队),直接算,不引 scipy。"""
    n = len(pairs)
    if n < 3:
        return 0.0
    d2 = sum((a - b) ** 2 for a, b in pairs)
    return round(1 - 6 * d2 / (n * (n * n - 1)), 3)


def build_view(size=None) -> dict:
    """候选池 45 支队,阵容和位置直接来自队伍快照。

    以前这里是 `build_ai_field`:按 HLTV top100 挑队、从卡上的 `team` 字段拼
    阵容、位置靠猜、凑不满就补 G1 占位。三处都换掉了——**占位卡尤其**:
    The MongolZ 现在首发里三个人没打过 Major,补三张占位卡等于把这支队换成
    三个虚构的人。现在他们以本人身份进来,只是四维那一侧空着。

    卡库外真人现在也有 AI 专属的透明先验，所以每支五人完整的队都能计算 entry；
    他们的玩家卡一栏仍留白，不会因此进入玩家抽卡库。
    """
    cfg = M.load_config()
    snap_raw = _load(SNAP_PATH)
    cap = float(cfg.get("cohesion_cap", 4.0))
    idx = P.load_rosters()
    field, asof = A.build_pool_field(cfg)

    by_id, _by_page = stats_index()
    img5e = _load(IMG5E_PATH)
    lq = _load(IMAGES_PATH, {"players": {}, "flags": {}})
    career = {c["page"]: c for c in P.load_cards()}
    snap = snapshot_index()

    # 每个人现在都有 AI 当前四维；只有快照本身不满五人的队不能计算 entry。
    scored = []
    for t in field:
        if len(t["roster"]) == 5:
            r = A.entry_of(t, idx, cap)
            scored.append((r["entry"], t["name"], r))
    scored.sort(key=lambda x: -x[0])
    our = {name: i for i, (_e, name, _r) in enumerate(scored, 1)}
    rate = {name: r for _e, name, r in scored}
    # HLTV 顺位也只在同一批队里比：这个池子是按大区配额挑的,中间跳过的队
    # 会污染名次做差。
    hltv_order = {t["name"]: i for i, t in enumerate(
        sorted([t for t in field if t["name"] in our and t["rank"]],
               key=lambda t: t["rank"]), 1)}

    teams, ranks = [], []
    covered = total = nocard = 0
    for t in field:
        st = snap.get(t["name"].casefold()) or {}
        logo = img5e.get("teams", {}).get(t["id"], "") or img5e.get(
            "teams", {}).get(st.get("id", ""), "")
        roster = []
        for c in t["roster"]:
            sid = c.get("_5e_id")
            srow = by_id.get(sid or "")
            base = career.get(c.get("page") or "")
            total += 1
            if srow:
                covered += 1
            if c.get("_nocard"):
                nocard += 1
            roster.append({
                "page": c.get("page"), "nickname": c["nickname"],
                "position": c["position"], "grade": c.get("grade"),
                "caller": bool(c.get("caller", c["position"] == "IGL")),
                "age": c.get("age"), "country": c.get("country", ""),
                "nocard": bool(c.get("_nocard")),
                "role_src": c.get("_role_src"),
                "notes": c.get("_notes") or [],
                "cur": {k: c[k] for k in C.ATTRS} | {"overall": c["overall"],
                                                           "sources": c.get("_sources") or {}},
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
                "photo": _photo(c.get("page"), sid, img5e, lq),
                "flag": ("/img/" + lq["flags"][c["country"]]
                         if c.get("country") in lq.get("flags", {}) else ""),
            })
        pos = our.get(t["name"])
        r = rate.get(t["name"])
        ho = hltv_order.get(t["name"])
        evidence = {k: sum(1 for c in t["roster"]
                           if (c.get("_sources", {}).get("firepower", {})
                               .get("confidence")) == k)
                    for k in ("strong", "supporting", "low")}
        teams.append({
            "name": t["name"], "hltv": t["rank"], "vrs": t["vrs"],
            "region": t["region"], "seat": t["seat"], "stage": t["stage"],
            "our": pos, "hltv_order": ho,
            "delta": (ho - pos) if (ho and pos) else None,
            "entry": round(r["entry"], 1) if r else None,
            "evidence": evidence,
            "chem": round(r["chem_raw"], 1) if r else None,
            "cohesion": round(r["cohesion"], 1) if r else None,
            "adjust": t.get("adjust") or 0.0,
            "real": t["real"], "source": t["source"],
            "gaps": t.get("gaps"), "conflicts": t.get("conflicts"),
            "logo": "/bd/" + logo if logo else "",
            "roster": roster,
        })
        if ho and pos:
            ranks.append((ho, pos))

    slots = cfg.get("regional_slots") or {}
    return {
        "teams": teams,
        "skipped": [],
        "asof": asof,
        "cap": cap,
        "rho": _spearman(ranks),
        "scored": len(our),
        "coverage": {"with_stats": covered, "total": total, "nocard": nocard},
        "slots": {k: v for k, v in slots.items()},
        "pool": cfg.get("candidate_pool") or {},
        "snapshot_date": snap_raw.get("snapshot_date", ""),
        "partial_refresh_at": snap_raw.get("partial_refresh_at", ""),
        "partial_refresh_ids": snap_raw.get("partial_refresh_ids") or [],
        "age_curve": {"knee": A.AGE_KNEE, "rate": A.AGE_RATE, "exp": A.AGE_EXP},
        "stats_window": (_load(STATS_PATH).get("window") or {}).get("value", ""),
        "stats_grade": _load(STATS_PATH).get("grade_label", ""),
    }
