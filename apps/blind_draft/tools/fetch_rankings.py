#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓队伍快照 -> data/blind_draft/team_snapshot.json，另抓一份官方 VRS 做交叉核对。

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

## 照片

队伍页那份响应里还带着 `portrait`（选手抠图，穿当前队服）和 `logo`（队标），
以前被丢掉了。现在 `--teams` 会把地址一起记进快照，`--photos` 再按快照把图下到
`data/blind_draft/img/`——**拿地址是零额外请求**，只有图片本体要下载。

用法:
    python bdtools/fetch_rankings.py --teams              # 5eplay 队伍快照（主）
    python bdtools/fetch_rankings.py --vrs                # 官方 VRS（交叉核对）
    python bdtools/fetch_rankings.py --photos             # 选手照片 + 队标
    python bdtools/fetch_rankings.py --teams --vrs --date 2026-09-01
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

from playerdb.paths import BLIND_DRAFT, DATA, ROOT

TEAMS_OUT = BLIND_DRAFT / "team_snapshot.json"
VRS_OUT = BLIND_DRAFT / "vrs_global.json"
IDS_CACHE = ROOT / ".cache" / "5e" / "team_ids.json"
STATS_PATH = BLIND_DRAFT / "5e_player_stats.json"
MANUAL_ROLES = BLIND_DRAFT / "team_roles.json"
IMG_ROOT = BLIND_DRAFT
IMG = IMG_ROOT / "img"
IMAGES_OUT = BLIND_DRAFT / "5e_images.json"

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


LP_PATH = DATA / "players.json"
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

    人工层 `data/blind_draft/team_roles.json` 压在最上面，格式
    `{"队名": {"IGL": "昵称", "AWPER": "昵称"}}`。同一人可以同时是
    IGL 和 AWPER：武器位置仍记 AWPER，另写 `caller=true`。

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
        pinned = manual.get(t["name"]) or manual.get(t.get("abbr") or "") or {}
        left, taken = [], set()

        def named(pos):
            want = pinned.get(pos)
            if not want:
                return None
            return next((r for r in starters
                         if r["name"].casefold() == str(want).casefold()), None)

        # 人工层不是“只补缺口”，它是当前真值覆盖。先把武器位置落好，再单独
        # 记录 caller；同一个 Maka 因此可以是 AWPER + caller，而 Graviti 回步枪。
        manual_awp, manual_igl = named("AWPER"), named("IGL")
        if manual_awp:
            for r in starters:
                if r is not manual_awp and r["role"] == "AWPER":
                    r["role"] = "RIFLER"
            manual_awp["role"] = "AWPER"
            manual_awp["role_source"] = "manual"
            taken.add(manual_awp["id"])
            gaps = [g for g in gaps if g != "AWPER"]
            filled.append([t["name"], "AWPER", manual_awp["name"], "manual"])
        if manual_igl:
            for r in starters:
                if r is not manual_igl and r["role"] == "IGL":
                    r["role"] = "RIFLER"
            if manual_igl is not manual_awp:
                manual_igl["role"] = "IGL"
                manual_igl["role_source"] = "manual"
            gaps = [g for g in gaps if g != "IGL"]
            filled.append([t["name"], "IGL", manual_igl["name"], "manual"])

        def riflers():
            return [(r, stats[r["id"]]) for r in starters
                    if r["role"] == "RIFLER" and r["id"] not in taken
                    and r["id"] in stats]

        for pos in sorted(set(gaps)):
            got = src = None
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
        caller = manual_igl or next((r for r in starters if r["role"] == "IGL"), None)
        for r in starters:
            r["caller"] = r is caller
            if r is caller and manual_igl:
                r["caller_source"] = "manual"
            else:
                r.pop("caller_source", None)
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
            "portrait": p.get(PORTRAIT_FIELD) or None,
        })
    return {
        "id": tid, "name": info["disp_name"], "abbr": info.get("disp_abbr"),
        "region": info.get("region_name"), "coach": info.get("coach") or None,
        "logo": info.get("logo") or None,
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
        "_note": ("5eplay 队伍快照,由 bdtools/fetch_rankings.py --teams 生成,勿手改。"
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


# ------------------------------------------------------------------ 照片

# 照片地址是 `teams/<id>/overview` **顺手就给的**——抓阵容那一趟已经把整份响应
# 拿在手里，portrait / team_info.logo 只是以前被 fetch_team() 扔掉的字段。所以
# 拿地址是零额外请求，只有图片本体需要下载。
#
# 选手有两个变体，都是 300×300 透明底抠图、穿**当前队服**（这正是它比
# Liquipedia 那批照片更适合 AI 对手阵容卡的原因——那边混着各年代各队的旧图）：
#
#     portrait       头肩紧裁，脸占满画面   ← 阵容卡用这个
#     half_portrait  半身，人物更小
#
# 命名反直觉：`portrait` 才是近的那张。别看名字想当然对调。
PORTRAIT_FIELD = "portrait"
PHOTO_WORKERS = 3          # 和 fetch_images.py 一个量级,别把人家 CDN 打疼
WEBP_QUALITY = 82
LOGO_ALPHA_DIFF = 10      # 两半剪影平均差(%)高于它就是真·宽字标,不切


def backfill_photo_urls(snap: dict) -> int:
    """给缺 portrait/logo 的队补地址，就地改快照。

    只有跑在**这次改动之前**生成的旧快照上才会真的动——那时 fetch_team() 还在
    丢这两个字段。补过一次之后，往后每次 --teams 都自带地址，这里就是空转。

    判「缺」看的是**键在不在**，不是值真不真。源站本来就有 4% 的选手没照片,
    他们的 `portrait` 永远是 null;要是按 falsy 判,这些队每跑一次 --photos 就
    被重抓一遍,永远停不下来。
    """
    todo = [t for t in snap["teams"]
            if "logo" not in t or any("portrait" not in p for p in t["roster"])]
    if not todo:
        return 0
    print("旧快照缺图片地址，回填 %d 支队…" % len(todo))
    fixed = 0
    for i, t in enumerate(todo, 1):
        try:
            d = get(E5 + "teams/%s/overview" % t["id"]).get("data") or {}
        except RuntimeError as exc:
            print("  %s 回填失败：%s" % (t["name"], exc))
            continue
        finally:
            time.sleep(SLEEP)
        t["logo"] = (d.get("team_info") or {}).get("logo") or None
        by_id = {x.get("id"): x
                 for x in (d.get("overview") or {}).get("players") or []}
        for pl in t["roster"]:
            pl["portrait"] = (by_id.get(pl["id"]) or {}).get(PORTRAIT_FIELD) or None
        fixed += 1
        if i % 50 == 0:
            print("  [%d/%d]…" % (i, len(todo)))
    return fixed


def split_dual_logo(path: Path) -> bool:
    """队标常是「深色版|浅色版」拼成的一张宽图，切出适合深色界面的那半。

    Spirit 的 logo 是 600×300：左半纯黑、右半纯白，同一个剪影。直接整张存下来，
    界面上就是一个左边隐形、右边发白的怪东西。抽样 60 支队里 17 张是这种宽图，
    不是个别现象。

    判据用**剪影**，不用别的两个看起来更顺手的信号:

      URL 里的 `merge_`  —— 4 张拼图里只有 2 张带它,漏一半。
      两半的亮度差       —— FaZe 两半只有星星一黑一白、红字标完全一样,
                            亮度差只有 15,会被漏掉。

    同一个标画两遍,**alpha 剪影必然几乎重合**。实测 16 张拼图的剪影平均差
    ≤7.5%(其中 15 张 ≤2.5%),而唯一一张真·宽字标(MANS NOT HOT,100×50)是
    24.9%——中间隔着三倍,阈值放 10% 很安全。切错一张真宽标就是把人家 logo
    砍掉一半,所以宁可漏切。

    亮度只用来决定**取哪半**:取亮的那半配深色界面。左右顺序不固定
    (Spirit / Vitality 左深右浅,ex-RUBY / rottweilers 恰好反过来),所以只认
    亮度不认位置。
    """
    if path.suffix.lower() != ".png" or not path.exists():
        return False
    try:
        from PIL import Image
    except ImportError:
        return False
    from PIL import ImageChops, ImageStat
    try:
        with Image.open(path) as im:
            im = im.convert("RGBA")
            if im.width != im.height * 2:
                return False
            half = im.width // 2
            left = im.crop((0, 0, half, im.height))
            right = im.crop((half, 0, im.width, im.height))

            diff = ImageChops.difference(left.getchannel("A"),
                                         right.getchannel("A"))
            if ImageStat.Stat(diff).mean[0] / 255 * 100 > LOGO_ALPHA_DIFF:
                return False                      # 剪影对不上 -> 本来就宽的字标

            def lum(part):
                px = [q for q in part.getdata() if q[3] > 128]
                if not px:
                    return None
                return sum((q[0] + q[1] + q[2]) / 3 for q in px) / len(px)

            ll, lr = lum(left), lum(right)
            if ll is None or lr is None:
                return False                      # 有一半是全透明,不像拼图
            (right if lr > ll else left).save(path, "PNG")
    except Exception as exc:                                      # noqa: BLE001
        print("  ! 队标拆分失败 %s：%s" % (path.name, exc))
        return False
    return True


def to_webp(path: Path) -> Path:
    """PNG 就地转同尺寸 WebP，返回最终路径。

    不能转 JPEG：5E 给的是抠图，带 alpha，转了会变成黑底方块。Pillow 只在
    requirements-maintenance.txt 里，没装就保留 PNG——照片照样能用，只是体积
    大四五倍。转完比原图还大的极少数图也退回 PNG。
    """
    if path.suffix.lower() != ".png" or not path.exists():
        return path
    try:
        from PIL import Image
    except ImportError:
        return path
    dest = path.with_suffix(".webp")
    try:
        with Image.open(path) as im:
            im.convert("RGBA").save(dest, "WEBP", quality=WEBP_QUALITY, method=6)
    except Exception as exc:                                      # noqa: BLE001
        print("  ! webp 转换失败 %s：%s" % (path.name, exc))
        dest.unlink(missing_ok=True)
        return path
    if dest.stat().st_size >= path.stat().st_size:
        dest.unlink(missing_ok=True)
        return path
    path.unlink()
    return dest


def download(job):
    url, dest = job
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
    except (urllib.error.URLError, OSError) as exc:
        print("  ! 下载失败 %s：%r" % (dest.name, exc))
        return None
    dest.write_bytes(data)
    time.sleep(0.15)
    return dest


def fetch_photos(force: bool = False) -> dict:
    """按快照下选手照片和队标 -> data/blind_draft/img/，清单写 data/blind_draft/5e_images.json。

    可重复跑：已经在盘上的文件直接跳过（--photos-force 才重下）。清单**只合并
    不删除**（和 fetch_5e_stats.py 同一条口径）——某个人这次抓失败，不该把他
    上次抓到的照片从清单里抹掉；只有文件真的不在盘上了才剔出去。
    """
    if not TEAMS_OUT.exists():
        raise SystemExit("没有 %s，先跑 --teams" % TEAMS_OUT.relative_to(ROOT))
    snap = json.loads(TEAMS_OUT.read_text(encoding="utf-8"))
    if backfill_photo_urls(snap):
        TEAMS_OUT.write_text(
            json.dumps(snap, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("  图片地址已写回快照")

    for sub in ("players", "teams"):
        (IMG / sub).mkdir(parents=True, exist_ok=True)

    jobs, players_map, teams_map, missing = [], {}, {}, []

    def plan(key, url, sub, bucket):
        if not url:
            missing.append(key)
            return
        ext = ".png" if ".png" in url.lower().split("?")[0] else ".jpg"
        dest = IMG / sub / (key + ext)
        webp = dest.with_suffix(".webp")
        if webp.exists() and not force:
            bucket[key] = "img/%s/%s" % (sub, webp.name)   # 上轮转过了,别重下 PNG
            return
        if force or not dest.exists():
            jobs.append((url, dest))
        bucket[key] = "img/%s/%s" % (sub, dest.name)

    seen = set()
    for t in snap["teams"]:
        plan(t["id"], t.get("logo"), "teams", teams_map)
        for pl in t["roster"]:
            if pl["id"] in seen:     # 阵容过期时同一个人会挂在两支队,只下一次
                continue
            seen.add(pl["id"])
            plan(pl["id"], pl.get("portrait"), "players", players_map)

    print("待下载 %d 张（选手 %d / 队标 %d，源站没图 %d）"
          % (len(jobs), len(players_map), len(teams_map), len(missing)))
    got = 0
    with ThreadPoolExecutor(PHOTO_WORKERS) as ex:
        for i, res in enumerate(ex.map(download, jobs), 1):
            got += res is not None
            if i % 100 == 0:
                print("  [%d/%d]…" % (i, len(jobs)))

    converted = halved = 0
    for bucket, sub in ((players_map, "players"), (teams_map, "teams")):
        for key, rel in list(bucket.items()):
            path = IMG_ROOT / rel
            if sub == "teams":
                halved += split_dual_logo(path)   # 必须在转 WebP 之前
            new = to_webp(path)
            if new.name != Path(rel).name:
                bucket[key] = "img/%s/%s" % (sub, new.name)
                converted += 1
    if halved:
        print("  队标拆出单变体 %d 张" % halved)
    if converted:
        print("  转成 WebP %d 张" % converted)

    old = (json.loads(IMAGES_OUT.read_text(encoding="utf-8"))
           if IMAGES_OUT.exists() else {})
    players_map = {**(old.get("players") or {}), **players_map}
    teams_map = {**(old.get("teams") or {}), **teams_map}
    players_map = {k: v for k, v in players_map.items() if (IMG_ROOT / v).exists()}
    teams_map = {k: v for k, v in teams_map.items() if (IMG_ROOT / v).exists()}

    payload = {
        "_note": ("5eplay 选手照片与队标清单，由 bdtools/fetch_rankings.py --photos "
                  "生成，勿手改。键是 5E 的 id（csgo_pl_* / csgo_tm_*，和 "
                  "team_snapshot.json 对得上），值是相对 data/blind_draft/ 的路径——和 "
                  "images.json 同一口径，但那份是 Liquipedia 侧、键是选手 page，"
                  "两份不要混用。选手图是穿当前队服的透明底抠图（AI 对手用"
                  "「现在的样子」，见 blinddraft/ai_teams.py 开头那条分叉）。"
                  "队标源图有一部分是「深色版|浅色版」拼成的宽图，已经切成"
                  "适合深色界面的那半，见 split_dual_logo。"),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
        "snapshot_date": snap.get("snapshot_date"),
        "source": E5 + "teams/<id>/overview",
        "counts": {"players": len(players_map), "teams": len(teams_map),
                   "downloaded": got, "no_image": len(missing),
                   "logos_split": halved},
        "players": players_map,
        "teams": teams_map,
    }
    IMAGES_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                          encoding="utf-8")
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
    ap.add_argument("--photos", action="store_true",
                    help="按快照下选手照片和队标 -> data/blind_draft/img/（地址是抓阵容时"
                         "顺带拿到的，不额外请求接口）")
    ap.add_argument("--photos-force", action="store_true",
                    help="连已经在盘上的照片也重下（换队服/换队标时用）")
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

    if not (args.teams or args.vrs or args.discover or args.photos
            or args.photos_force):
        ap.error("至少给一个 --teams / --vrs / --discover / --photos")
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
    if args.photos or args.photos_force:
        p = fetch_photos(force=args.photos_force)
        c = p["counts"]
        print("照片 -> %s / %s" % ((IMG / "players").relative_to(ROOT),
                                   IMAGES_OUT.relative_to(ROOT)))
        print("  选手 %d 张,队标 %d 张,本次新下 %d 张,源站没图 %d"
              % (c["players"], c["teams"], c["downloaded"], c["no_image"]))
    if args.vrs:
        p = fetch_vrs(asof)
        print("官方 VRS %s（快照日 %s）-> %s，%d 支队"
              % (p["standings_date"], p["snapshot_date"],
                 VRS_OUT.relative_to(ROOT), p["count"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
