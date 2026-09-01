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

位置这一项尤其值钱：原来要从 Liquipedia 的 `roles` 猜主位置、再全队去重、
再人工钉 caller/awper（设计稿 §46.6），现在是队伍页直接写着的事实。

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


def resolve_roles(players):
    """定位置。`positions` 是**无序的角色集合**,不是"主位置在前"。

    ZywOo 是 ['步枪手','狙击手']、FalleN 是 ['步枪手','指挥'],取第一个会把
    他们判成步枪手——和 §46.2 踩的是同一个坑,只是换了个数据源。

    但这次的输入好得多:它是**队内**角色表,不是生涯角色。所以规则很直接——
    一支队里谁列了「指挥」谁就是指挥,谁列了「狙击手」谁就是狙。两个人都列的
    极少,真遇到就按 top20 次数多的那个留(打得更久的那个更可能是定位角色),
    并把冲突报出来让人看见。
    """
    conflicts = []
    out = {p["id"]: "RIFLER" for p in players}
    for tag, pos in (("指挥", "IGL"), ("狙击手", "AWPER")):
        cands = [p for p in players if tag in (p.get("positions") or [])]
        if len(cands) > 1:
            conflicts.append((pos, [p["name"] for p in cands]))
            cands.sort(key=lambda p: -(as_int(p.get("top20_num")) or 0))
        if cands:
            out[cands[0]["id"]] = pos
    return out, conflicts


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
    roles, conflicts = resolve_roles(starters)
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
        "role_conflicts": conflicts or None,
    }


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
    ap.add_argument("--date", default=None, help="快照日期 YYYY-MM-DD,默认今天")
    args = ap.parse_args()
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
