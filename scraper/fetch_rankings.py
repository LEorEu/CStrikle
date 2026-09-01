#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓队伍快照 -> data/team_snapshot.json，另抓一份官方 VRS 做交叉核对。

## 为什么阵容必须来自 5eplay，而不是 VRS 或卡库

踩过的坑，写在最前面：

  **VRS 是月更的。** Valve 那份 standings_global_2026_08_03.md 到 9 月 1 日已经
  落后近一个月——它把 mzinho 同时列在 The MongolZ 和 BC.Game 两支队里，G2 写的是
  SunPayus（实际是 r1nkle），100 Thieves 少了换人。**同一个人出现在两支队里就是
  数据过期的直接证据**，不是需要去重的脏数据。

  **卡库的 `team` 字段来自 Liquipedia**，同样滞后，而且它只说"这个人属于哪支队"，
  说不出"他现在是首发还是替补"、"他在这支队里打什么位置"。

5eplay 的 `teams/<id>/overview` 一个接口全给了：

  当前五人 + 首发/替补 + **队内实际位置**（指挥/狙击手/步枪手/自由人）
  HLTV 排名与积分（rank / points）
  VRS 排名与积分（v_club_rank / v_club_integral，周更，比 Valve 的月更文件还新）
  教练、平均年龄、每周排名历史

位置这一项尤其值钱，但**不能单独用**：它不排他（Legacy 三个人都标狙击手），
也有缺口（FaZe 五个人没一个标指挥，而 Twistzz 就是指挥）。所以 `resolve_roles`
拿它和 Liquipedia 的生涯角色一起判——队内角色优先，生涯角色兜底。

## 快照

所有产出都盖 `snapshot_date`。VRS 取**不晚于快照日的最新一版**，所以同一个
快照日重复跑结果一样。5eplay 是实时的，只能盖抓取时间——这是它比 VRS 新的代价。

用法:
    python scraper/fetch_rankings.py --teams              # 5eplay 队伍快照（主）
    python scraper/fetch_rankings.py --vrs                # 官方 VRS（交叉核对）
    python scraper/fetch_rankings.py --teams --vrs --date 2026-09-01
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEAMS_OUT = ROOT / "data" / "team_snapshot.json"
VRS_OUT = ROOT / "data" / "vrs_global.json"
IDS_CACHE = ROOT / ".cache" / "5e" / "team_ids.json"
STATS_PATH = ROOT / "data" / "5e_player_stats.json"
MANUAL_ROLES = ROOT / "data" / "manual" / "team_roles.json"

E5 = "https://esports-data.5eplaycdn.com/v1/api/csgo/"
GH_API = ("https://api.github.com/repos/ValveSoftware/"
          "counter-strike_regional_standings/contents/live/%d")
RAW = ("https://raw.githubusercontent.com/ValveSoftware/"
       "counter-strike_regional_standings/main/live/%d/%s")
UA = "cstrikle-local-tool (personal project)"
SLEEP = 0.2

# 队伍页写的是中文位置。「自由人」是 lurker、「辅助」是 support,在我们只有三个
# 位置的口径里都算步枪手。
ROLE = {"指挥": "IGL", "狙击手": "AWPER", "步枪手": "RIFLER", "自由人": "RIFLER",
        "辅助": "RIFLER", "突破手": "RIFLER", "突破": "RIFLER"}
COACH = "教练"   # positions 里出现它就不是队员——教练顶掉一个位置是 §46.4 那个坑
STARTER = "首发"


LP_PATH = ROOT / "data" / "players.json"
LEET = str.maketrans({"1": "i", "0": "o", "3": "e", "4": "a",
                      "$": "s", "5": "s", "7": "t"})
_LP_CACHE = {}


def norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", (s or "").casefold().translate(LEET))


def lp_roles() -> dict:
    """Liquipedia 的生涯角色表,给 5eplay 的位置做第二个证据源。"""
    if not _LP_CACHE and LP_PATH.exists():
        raw = json.loads(LP_PATH.read_text(encoding="utf-8"))
        for x in (raw.get("players") if isinstance(raw, dict) else raw):
            _LP_CACHE.setdefault(norm(x.get("nickname")),
                                 set(x.get("roles") or []) - {"coach"})
    return _LP_CACHE


TAGS = {"IGL": ("指挥", "igl"), "AWPER": ("狙击手", "awp")}


def resolve_roles(players):
    """定位置。两个源都不够用,必须一起看。

    `positions` 是**无序集合**不是"主位置在前"(ZywOo 是 ['步枪手','狙击手']),
    这是 §46.2 那个坑。但队内角色表也不够——实测两种失效方式:

      **不排他**:Legacy 的 latto / dumau / try 三个人都标了「狙击手」。
      **有缺口**:FaZe 五个人没有一个标「指挥」,而 Twistzz 就是指挥。

    所以规则是"5eplay 优先、Liquipedia 兜底、独占者优先":

      1. 有人标了该 tag -> 只在这些人里挑;都没标 -> 才拿 Liquipedia 的
         生涯角色兜底。队内角色永远压过生涯角色,因为前者说的是"现在"。
      2. 同 tag 多人时,按"该源里只有这一个 tag"决胜——`try` 只标狙,
         latto 标了步枪+狙,所以狙是 try 的。两边都平才看 top20 次数。
      3. 两个位置都找不到人时**如实留空**(Inner Circle 全队没人标指挥),
         写进 role_gaps,不假装。
    """
    lp = lp_roles()
    notes = {"conflicts": [], "gaps": [], "fallback": []}
    out = {p["id"]: "RIFLER" for p in players}
    taken = set()

    def lp_of(p):
        return lp.get(norm(p.get("name")), set())

    for pos, (tag, key) in TAGS.items():
        cands = [p for p in players if tag in (p.get("positions") or [])]
        src = "5e"
        if not cands:
            cands = [p for p in players if key in lp_of(p)]
            src = "lp"
        cands = [p for p in cands if p["id"] not in taken] or cands
        if not cands:
            notes["gaps"].append(pos)
            continue
        if len(cands) > 1:
            notes["conflicts"].append([pos, [p["name"] for p in cands]])
        cands.sort(key=lambda p: (
            set(p.get("positions") or []) == {tag},      # 5e 里独占该 tag
            key in lp_of(p),                             # Liquipedia 也这么说
            lp_of(p) == {key},                           # 且它那边也独占
            as_int(p.get("top20_num")) or 0,
        ), reverse=True)
        out[cands[0]["id"]] = pos
        taken.add(cands[0]["id"])
        if src == "lp":
            notes["fallback"].append([pos, cands[0]["name"]])
    return out, notes


def _num(v):
    try:
        return float(str(v).replace("%", "").replace("+", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


MAP_FLOOR = 10          # 结构性信号不需要大样本，20 会把 Jorko(15 图)挡在外面
AWP_HS_MAX = 40.0       # 狙的爆头率上限：47 个已知狙的 90% 分位是 40.2%


def fill_role_gaps(teams):
    """把 role_gaps 补上。**一支真实队伍不可能没有指挥。**

    队伍页的 tag 有缺口（前 50 名里 11 支缺指挥或缺狙），生涯角色也兜不住
    ——dex 根本不在 players.json 里，那是 Major 名单，而当前世界本来就装得下
    卡库没有的人。所以第四档拿竞技数据兜底。两条判据的强度**差得很远**，
    不该混为一谈：

    **狙 = 爆头率结构性地低。** 这几乎是条定理：AWP 一枪毙命，不靠爆头。
    47 个已知狙 hs_rate 中位 33.9%，148 个步枪 53.1%，两个分布几乎不重叠
    （狙的 90% 分位 40.2%，步枪的 10% 分位 42.8%）。所以判据不是"队里最低"
    而是**绝对阈值 40%**：低于它才认，全队都高于它就如实留空。38 支已知队里
    有 37 支的狙确实是队内最低，低出中位 13 个百分点。

    **指挥 = 开火少。** 弱得多：33 支已知队里只有 22 支（67%）的指挥是队内
    kpr 最低的人。所以它只是个**猜测**，标成 `kpr?`，而且要求他至少低于队内
    步枪的中位数，否则宁可留空。真在乎的队请写进人工层。

    人工层 `data/manual/team_roles.json` 压在最上面，格式
    `{"队名": {"IGL": "昵称", "AWPER": "昵称"}}`。

    这一步是**幂等**的：先把上一次兜底判的位置退回去，再重判。
    """
    stats = {}
    if STATS_PATH.exists():
        for v in (json.loads(STATS_PATH.read_text(encoding="utf-8"))
                  .get("players") or {}).values():
            if v.get("5e_id") and (_num(v.get("map_count")) or 0) >= MAP_FLOOR:
                stats[v["5e_id"]] = v
    manual = {}
    if MANUAL_ROLES.exists():
        manual = {k: v for k, v in
                  json.loads(MANUAL_ROLES.read_text(encoding="utf-8")).items()
                  if not k.startswith("_")}

    filled = []
    for t in teams:
        starters = [r for r in t["roster"] if r.get("starter")]
        # 幂等：退回上一次兜底的判定，缺口重新算
        gaps = list(t.get("role_gaps") or [])
        for r in starters:
            if r.pop("role_source", None):
                gaps.append(r["role"])
                r["role"] = "RIFLER"
        if not gaps:
            continue
        pinned = manual.get(t["name"]) or manual.get(t.get("abbr") or "") or {}
        left, taken = [], set()

        def riflers():
            return [(r, stats[r["id"]]) for r in starters
                    if r["role"] == "RIFLER" and r["id"] not in taken
                    and r["id"] in stats]

        for pos in sorted(set(gaps)):
            got = src = None
            want = pinned.get(pos)
            if want:
                got = next((r for r in starters
                            if r["name"].casefold() == str(want).casefold()), None)
                src = "manual"
            if got is None:
                cand = riflers()
                if pos == "AWPER" and cand:
                    r, v = min(cand, key=lambda x: _num(x[1]["hs_rate"]))
                    if _num(v["hs_rate"]) < AWP_HS_MAX:
                        got, src = r, "hs_rate"
                elif pos == "IGL" and cand:
                    r, v = min(cand, key=lambda x: _num(x[1]["kpr"]))
                    ks = sorted(_num(x[1]["kpr"]) for x in cand)
                    if _num(v["kpr"]) <= ks[len(ks) // 2]:
                        got, src = r, "kpr?"      # 问号是认真的：只有 67% 对
            if got is None:
                left.append(pos)
                continue
            got["role"] = pos
            got["role_source"] = src
            taken.add(got["id"])
            filled.append([t["name"], pos, got["name"], src])
        t["role_gaps"] = left or None
    return filled


def get(url: str, as_json: bool = True, tries: int = 3):
    last = None
    for i in range(tries):
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "application/vnd.github+json" if "api.github" in url else "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r) if as_json else r.read().decode("utf-8")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last = exc
            time.sleep(1.5 * (i + 1))
    raise RuntimeError("请求失败 %s: %r" % (url, last))


def post(url: str, body: dict, tries: int = 3):
    data = json.dumps(body).encode("utf-8")
    last = None
    for i in range(tries):
        req = urllib.request.Request(url, data=data, headers={
            "Content-Type": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last = exc
            time.sleep(1.5 * (i + 1))
    raise RuntimeError("请求失败 %s: %r" % (url, last))


# ------------------------------------------------------------------ 队伍 id 表

def fetch_team_ids(max_pages: int = 20) -> dict:
    seen = {}
    for page in range(1, max_pages + 1):
        d = post(E5 + "mfilter/team/list",
                 {"dimension": "top", "sort_value": "desc", "sort_key": "kd",
                  "team_options": {"time_value": "", "grade": [], "team_id": "",
                                   "time_type": "", "tt_series": [], "maps": [],
                                   "page": page}})
        items = (d.get("data") or {}).get("items") or []
        if not items:
            break
        for it in items:
            seen[it["team_id"]] = it["team_name"]
        time.sleep(SLEEP)
    return seen


def discover_team_ids(player_ids: dict) -> dict:
    """从选手页反查队伍 id。

    队伍列表接口(`mfilter/team/list`)只收录近期有比赛数据的队,实测 238 支里
    没有 The MongolZ 和 BC.Game——而它们都在赛场上。选手页 `players/<id>` 的
    `basic_info.team_id` 是权威当前队伍,所以反过来走:我们关心哪些选手,
    就能发现哪些队。这样发现集合天然等于"卡库里的人现在所在的队"。
    """
    out = {}
    for i, pid in enumerate(sorted(player_ids), 1):
        try:
            b = (get(E5 + "players/%s" % pid).get("data") or {}).get("basic_info") or {}
        except RuntimeError:
            continue
        finally:
            time.sleep(SLEEP)
        if b.get("team_id") and b.get("team_name"):
            out[b["team_id"]] = b["team_name"]
        if i % 100 == 0:
            print("  [%d/%d] 已发现 %d 支队…" % (i, len(player_ids), len(out)))
    return out


# ------------------------------------------------------------------ 逐队详情

def as_int(v):
    try:
        return int(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def fetch_team(tid: str, unknown_roles: set) -> dict | None:
    d = get(E5 + "teams/%s/overview" % tid).get("data") or {}
    info = d.get("team_info") or {}
    players = (d.get("overview") or {}).get("players") or []
    if not info.get("disp_name"):
        return None
    # 教练也会出现在 players 里,必须先剔掉:让教练占掉一个首发位置,
    # 就是 §46.4 记的那个坑(gla1ve 挂 coach 却被算成 100T 的队员)。
    players = [p for p in players if COACH not in (p.get("positions") or [])]
    starters = [p for p in players if p.get("position") == STARTER] or players
    roles, notes = resolve_roles(starters)
    roster = []
    for p in players:
        for raw in (p.get("positions") or []):
            if raw not in ROLE:
                unknown_roles.add(raw)
        roster.append({
            "id": p.get("id"), "name": p.get("name"),
            "role": roles.get(p.get("id"), "RIFLER"),
            "roles_raw": p.get("positions") or [],
            "starter": p.get("position") == STARTER,
            "birthday": p.get("birthday") or None,
            "top20": as_int(p.get("top20_num")),
        })
    return {
        "id": tid, "name": info["disp_name"], "abbr": info.get("disp_abbr"),
        "region": info.get("region_name"), "coach": info.get("coach") or None,
        "avg_age": as_int(info.get("average_player_age")),
        "hltv_rank": as_int(info.get("rank")), "hltv_points": as_int(info.get("points")),
        "vrs_rank": as_int(info.get("v_club_rank")),
        "vrs_points": as_int(info.get("v_club_integral")),
        "roster": roster,
        "role_conflicts": notes["conflicts"] or None,
        "role_gaps": notes["gaps"] or None,
        "role_fallback": notes["fallback"] or None,
    }


def repair_roles():
    """只跑补位这一步，直接改已有的快照——不重抓 288 支队。

    存在的理由是先后顺序：位置兜底要用竞技数据，而竞技数据的 id 来自快照，
    所以只能 快照 -> 抓数据 -> 回头补位 这么走。
    """
    raw = json.loads(TEAMS_OUT.read_text(encoding="utf-8"))
    teams = raw["teams"]
    before = sum(len(t.get("role_gaps") or []) for t in teams)
    filled = fill_role_gaps(teams)
    after = sum(len(t.get("role_gaps") or []) for t in teams)
    rank = {t["name"]: t.get("hltv_rank") or 999 for t in teams}
    for name, pos, who, src in sorted(filled, key=lambda f: rank[f[0]]):
        print("  #%-4s %-18s %-6s <- %-14s (%s)"
              % (rank[name], name, pos, who, src))
    print("位置缺口 %d -> %d，补上 %d 处" % (before, after, len(filled)))
    raw["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    TEAMS_OUT.write_text(json.dumps(raw, ensure_ascii=False, indent=1) + "\n",
                         encoding="utf-8")
    print("写回 %s" % TEAMS_OUT.relative_to(ROOT))


def fetch_teams(asof: date, refresh_ids: bool):
    if refresh_ids or not IDS_CACHE.exists():
        print("抓队伍 id 表…")
        ids = fetch_team_ids()
        IDS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        IDS_CACHE.write_text(json.dumps(ids, ensure_ascii=False), encoding="utf-8")
    else:
        ids = json.loads(IDS_CACHE.read_text(encoding="utf-8"))
    print("队伍 id %d 支（--refresh-ids 重抓）" % len(ids))

    unknown, out, failed = set(), [], 0
    for i, tid in enumerate(sorted(ids), 1):
        try:
            t = fetch_team(tid, unknown)
        except RuntimeError as exc:
            failed += 1
            print("  %s 失败：%s" % (tid, exc))
            continue
        finally:
            time.sleep(SLEEP)
        if t:
            out.append(t)
        if i % 50 == 0:
            print("  [%d/%d]…" % (i, len(ids)))

    filled = fill_role_gaps(out)
    if filled:
        print("  位置缺口补上 %d 处（人工层 > 竞技数据兜底，见 fill_role_gaps）" % len(filled))

    # 有排名的排前面,没排名的按名字。排名缺失是常态(小队伍不进榜)。
    out.sort(key=lambda t: (t["hltv_rank"] is None, t["hltv_rank"] or 0, t["name"]))
    ranked = [t for t in out if t["hltv_rank"]]
    five = [t for t in out if len([p for p in t["roster"] if p["starter"]]) == 5]
    payload = {
        "_note": ("5eplay 队伍快照,由 scraper/fetch_rankings.py --teams 生成,勿手改。"
                  "阵容/位置/首发都来自队伍页,是**当前事实**——不要用 VRS 的阵容"
                  "(那份月更,实测会把同一个人列在两支队里),也不要用卡库的 team 字段"
                  "(Liquipedia 滞后,而且说不出首发和队内位置)。"
                  "hltv_* 和 vrs_* 是两套排名,都只做参考不当种子(设计稿 §51.2)。"),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
        "snapshot_date": asof.isoformat(),
        "source": E5 + "teams/<id>/overview",
        "counts": {"teams": len(out), "with_hltv_rank": len(ranked),
                   "five_starters": len(five), "failed": failed},
        "teams": out,
    }
    TEAMS_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                         encoding="utf-8")
    if unknown:
        print("  没见过的位置字符串（补进 ROLE 表）：%s" % "、".join(sorted(unknown)))
    return payload


# ------------------------------------------------------------------ 官方 VRS

ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|")


def pick_file(asof: date) -> tuple[int, str]:
    for year in (asof.year, asof.year - 1):
        try:
            names = [x["name"] for x in get(GH_API % year)
                     if x.get("name", "").startswith("standings_global_")]
        except Exception:
            continue
        good = [n for n in sorted(names)
                if (m := re.search(r"(\d{4})_(\d{2})_(\d{2})", n))
                and date(*map(int, m.groups())) <= asof]
        if good:
            return year, good[-1]
    raise RuntimeError("在 %s 之前没找到任何 VRS 版本" % asof)


def fetch_vrs(asof: date):
    year, name = pick_file(asof)
    md = get(RAW % (year, name), as_json=False)
    rows = []
    for line in md.splitlines():
        m = ROW.match(line)
        if not m or not m.group(3).strip() or m.group(3).strip().startswith(":"):
            continue
        rows.append({"rank": int(m.group(1)), "points": int(m.group(2)),
                     "team": m.group(3).strip(),
                     "roster": [p.strip() for p in m.group(4).split(",") if p.strip()]})
    if not rows:
        raise RuntimeError("解析出 0 支队,%s 的表格格式可能变了" % name)
    stamp = re.search(r"(\d{4})_(\d{2})_(\d{2})", name)
    payload = {
        "_note": ("Valve Regional Standings 官方全球榜,**只做交叉核对**。"
                  "它每月发一版,到快照日可能已经落后数周——实测 2026-08-03 那版把 mzinho "
                  "同时列在两支队里、G2 写的还是 SunPayus。**阵容一律以 team_snapshot.json "
                  "为准**,这份只用来核对积分与名次口径。"),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
        "snapshot_date": asof.isoformat(),
        "standings_date": "%s-%s-%s" % stamp.groups(),
        "source_url": RAW % (year, name),
        "count": len(rows), "teams": rows,
    }
    VRS_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8")
    return payload


def main():
    ap = argparse.ArgumentParser(description="抓队伍快照与排名")
    ap.add_argument("--teams", action="store_true", help="5eplay 队伍快照（阵容以此为准）")
    ap.add_argument("--vrs", action="store_true", help="官方 VRS（只做交叉核对）")
    ap.add_argument("--refresh-ids", action="store_true", help="重抓队伍 id 表")
    ap.add_argument("--discover", action="store_true",
                    help="从 .cache/5e/player_ids.json 的选手页反查队伍 id 并并入缓存"
                         "（队伍列表接口漏掉 MongolZ / BC.Game 这类队，只能这么补）")
    ap.add_argument("--fill-roles", action="store_true",
                    help="只补 role_gaps，就地改已有快照（要先抓过竞技数据）")
    ap.add_argument("--date", default=None, help="快照日期 YYYY-MM-DD,默认今天")
    args = ap.parse_args()
    if args.fill_roles:
        repair_roles()
        return 0

    if not (args.teams or args.vrs or args.discover):
        ap.error("至少给一个 --teams / --vrs / --discover")
    asof = (datetime.strptime(args.date, "%Y-%m-%d").date()
            if args.date else date.today())

    if args.discover:
        cache = ROOT / ".cache" / "5e" / "player_ids.json"
        pids = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
        print("从 %d 个选手页反查队伍…" % len(pids))
        found = discover_team_ids(pids)
        old_ids = json.loads(IDS_CACHE.read_text(encoding="utf-8")) if IDS_CACHE.exists() else {}
        merged = {**old_ids, **found}
        IDS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        IDS_CACHE.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
        print("  发现 %d 支，id 表 %d -> %d" % (len(found), len(old_ids), len(merged)))
    if args.teams:
        p = fetch_teams(asof, args.refresh_ids)
        c = p["counts"]
        print("队伍快照 -> %s" % TEAMS_OUT.relative_to(ROOT))
        print("  %d 支,其中有 HLTV 名次的 %d 支,首发满 5 人的 %d 支,失败 %d"
              % (c["teams"], c["with_hltv_rank"], c["five_starters"], c["failed"]))
        for t in p["teams"][:5]:
            print("    HLTV #%-3s VRS #%-3s %-16s %s"
                  % (t["hltv_rank"], t["vrs_rank"], t["name"],
                     " ".join("%s(%s)" % (x["name"], x["role"][:3])
                              for x in t["roster"] if x["starter"])))
    if args.vrs:
        p = fetch_vrs(asof)
        print("官方 VRS %s（快照日 %s）-> %s，%d 支队"
              % (p["standings_date"], p["snapshot_date"],
                 VRS_OUT.relative_to(ROOT), p["count"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
