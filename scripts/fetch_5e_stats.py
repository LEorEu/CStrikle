#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓 5eplay 的选手当前竞技数据 -> data/5e_player_stats.json（本地维护工具）。

为什么需要它（设计稿 §48.2、§51）：卡库四维记的是**生涯成就**，HLTV 排名记的是
**现在在赢球**，两者秩相关只有 0.53。我们试过三条路把这道差补上——按"多久没进
top20"扣火力、按最近几年证据重判档位、按队伍排名锚定——全都不成立，因为都在
"没有个人当前 rating"的前提下硬造一个。而这个数是存在的。

口径（这几条是**指标的定义**，不是可以随便调的旋钮）：

  时间窗   近 12 个月。3 个月太稀疏——实测 Senzu 近 3 月 0 图、近 1 年 51 图，
           一个真在打比赛的人会整个消失。
  等级     Major + S+ + S。放宽到 A 级只多 2% 覆盖，相关性反而从 0.618 掉到
           0.573，因为低级别赛事炸鱼刷出来的 1.25 和 S 级的 1.25 不是一回事
           （asap S 级 1.09/11 图，含 A 级变 1.24/31 图）。
           **推论：查不到的人不是"数据缺失"，是"他没有顶级赛事样本"这件事本身**，
           对这种人应当回退卡面，而不是给他一个从 C 级赛事刷出来的数。
  样本量   必须按 map_count 往均值收缩。xKacpersky 近 3 月 1.52 是 6 张图打的。

两个接口的坑，踩过了写在这里：

  1. **翻排行榜会静默丢数据。** sort_key=rating 有大量并列，页边界每次都漂：
     抓 1494 行只有 1129 个唯一 id，而且两次抓漏的人不一样。改成**按 player_id
     逐人查**——那样根本不经过分页，返回恰好一行。id 表另外抓（见 fetch_ids）。
  2. **total_rows / total_page 不可信**，multidimension 那个接口永远返回 20/1。
     不要拿它判断进度或总数。

安全口径（`data/images.json` 那次教训）：**只合并，不删除。** 某个人这次抓失败，
保留他上一次的数据并标 stale，绝不从文件里消失；跑完打印 新增/更新/失败/未变
四个计数，失败非零就用非零退出码。

不在生产运行，不联网跑游戏——产物落盘，运行时只读文件。
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
CARDS_PATH = ROOT / "data" / "draft_cards.json"
OUT_PATH = ROOT / "data" / "5e_player_stats.json"
ALIAS_PATH = ROOT / "data" / "manual" / "5e_aliases.json"
IDS_CACHE = ROOT / ".cache" / "5e" / "player_ids.json"
SNAP_PATH = ROOT / "data" / "team_snapshot.json"

API = "https://esports-data.5eplaycdn.com/v1/api/csgo/mfilter/player/"
UA = "Mozilla/5.0 (compatible; cstrikle-local-tool)"

# —— 口径常量。改这里等于改指标的定义，不是调参 ——
WINDOW_MONTHS = 12
GRADES = ["1", "7", "2"]            # Major / S+ / S
GRADE_LABEL = "Major + S+ + S"
SLEEP = 0.25                        # 别把人家接口打疼

# 我们要留下来的字段。impact 恒为 0，dagger/v4/v5 太稀疏，都不收。
KEEP = ("rating", "adr", "kast", "kd", "kpr", "dpr", "hs_rate",
        "first_blood", "first_death", "map_count", "win_rate", "kddiff")

LEET = str.maketrans({"1": "i", "0": "o", "3": "e", "4": "a",
                      "$": "s", "5": "s", "7": "t"})


def norm(name: str) -> str:
    """昵称规整。5eplay 把 dev1ce 写成 device，所以 leet 要拉平。"""
    return re.sub(r"[^a-z]", "", name.casefold().translate(LEET))


def window_value(months: int = WINDOW_MONTHS) -> str:
    end = date.today()
    y, m = end.year, end.month - months
    while m <= 0:
        y, m = y - 1, m + 12
    return "%04d-%02d-01 00:00:00_%s 23:59:59" % (y, m, end.isoformat())


def post(path: str, body: dict, tries: int = 3) -> dict:
    data = json.dumps(body).encode("utf-8")
    last = None
    for i in range(tries):
        req = urllib.request.Request(
            API + path, data=data,
            headers={"Content-Type": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last = exc
            time.sleep(1.5 * (i + 1))
    raise RuntimeError("请求失败 %s: %r" % (path, last))


def options(player_id: str = "", page: int = 1, time_value: str = "",
            grades=None) -> dict:
    return {"tt_ids": [], "time_value": time_value, "grade": grades or [],
            "player_id": player_id, "time_type": "recent" if time_value else "",
            "tt_series": [], "maps": [], "page": page}


# ------------------------------------------------------------------ 第一步：id 表

def fetch_ids(max_pages: int = 70) -> dict:
    """全量选手 id 表。

    这一步**只能**翻榜（逐人查需要先有 id），所以正序倒序各扫一遍取并集——
    rating 并列会让页边界漂，单向扫必漏。实测双向并集拿到 1196 人，
    赛场现役选手覆盖 98%。
    """
    seen = {}
    for direction in ("desc", "asc"):
        empty = 0
        for page in range(1, max_pages + 1):
            d = post("list", {"dimension": "top", "sort_value": direction,
                              "sort_key": "rating",
                              "player_options": options(page=page)})
            items = (d.get("data") or {}).get("items") or []
            if not items:
                empty += 1
                if empty >= 3:
                    break
                continue
            empty = 0
            for it in items:
                seen[it["player_id"]] = it["player_name"]
            time.sleep(SLEEP)
    return seen


# ------------------------------------------------------------------ 第二步：对名字

def load_cards():
    return json.loads(CARDS_PATH.read_text(encoding="utf-8"))["cards"]


def load_aliases() -> dict:
    if not ALIAS_PATH.exists():
        return {}
    raw = json.loads(ALIAS_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def snapshot_teams() -> list:
    if not SNAP_PATH.exists():
        return []
    return json.loads(SNAP_PATH.read_text(encoding="utf-8")).get("teams") or []


def snapshot_ids(teams=None) -> dict:
    """队伍快照里的 id。**权威层**：它来自 `teams/<id>/overview`,是队伍页自己
    列出来的人,根本不经过名字匹配,所以不可能配错人。"""
    out = {}
    for t in (teams if teams is not None else snapshot_teams()):
        for r in t.get("roster") or []:
            if r.get("id") and r.get("name"):
                out[r["id"]] = r["name"]
    return out


def pool_targets(teams, top: int) -> dict:
    """**当前世界的选手池**：排名前 `top` 的队伍的现役队员，id -> 名字。

    和卡库（生涯世界）是两个池子,故意不取交集——当前世界里本来就该有卡库里
    没有的人(tikuak、DarkMeister 从没打过 Major,但他们现在就在 The MongolZ
    首发)。原来只抓"卡库里有队的人",于是前 50 名的 238 个首发里有 58 个
    既没有卡也没有数据,AI 层只能拿 G1 占位去顶——那已经不是这支队了。
    """
    out = {}
    for t in teams:
        rk = t.get("hltv_rank") or t.get("vrs_rank")
        if not rk or rk > top:
            continue
        for r in t.get("roster") or []:
            if r.get("id") and r.get("name"):
                out[r["id"]] = r["name"]
    return out


def build_index(*layers):
    """按名字查 id 的索引。三档由严到宽，每档内部撞名的键整个丢掉。

    原来只有 leet 规整这一档，而规整会**撞名**：`BL1TZ` 和 `bLitz` 归一后
    都是 `blitz`，实测 29 组，NiKo/niko、b1t/BIT、frozen/FROZ3N 全在里面。
    先到先得的 `setdefault` 让 bLitz 拿到了另一个人的 id，查出来没有顶级赛事
    样本，于是被记成"这人没打过 S 级赛"。**静默配错人比漏掉更糟**，
    因为它看起来像一条正常数据。

    三档是：原名 -> 忽略大小写 -> leet 规整。`NiKo` 和 `niko` 在第一档就
    分开了，根本不必走到会撞的那一档；只有真同名（两个 `Lucky`）才落到
    人工别名表。层与层之间：队伍快照先进，它来自队伍页，不经过名字匹配。
    """
    keys = (lambda n: n, lambda n: n.casefold(), norm)
    index, dropped = [{} for _ in keys], []
    for layer in layers:
        for tier, keyf in enumerate(keys):
            cand = {}
            for pid, name in layer.items():
                cand.setdefault(keyf(name), set()).add((pid, name))
            for k, v in cand.items():
                if k in index[tier]:
                    continue
                if len(v) > 1:
                    if tier == len(keys) - 1:
                        dropped.append(sorted(n for _, n in v))
                        continue
                    continue
                index[tier][k] = next(iter(v))
    # 上面按档收集的 dropped 里，大部分在更严的那档已经分开了（NiKo/niko）——
    # 只有一个成员都没进原名档的组才是真丢了。
    dropped = [g for g in dropped if not any(n in index[0] for n in g)]
    return index, dropped


def match(cards, index: list, aliases: dict):
    """卡库昵称 -> 5eplay player_id。别名表优先，其次 leet 规整后精确匹配。

    故意**不做模糊匹配**：实测 cmtry→try、jks→jokes 这类近似全是不同的人，
    宁可漏一个让人工补别名，也不能悄悄配错人。
    """
    hit, miss = {}, []
    for c in cards:
        nick = c["nickname"]
        want = aliases.get(nick) or aliases.get(c["page"])
        if want:
            if str(want).startswith(("csgo_pl_", "cg_pl_", "hltv_pl_")):
                hit[c["page"]] = (want, nick)
                continue
            nick = str(want)
        got = next((ix[k] for ix, k in
                    zip(index, (nick, nick.casefold(), norm(nick))) if k in ix), None)
        if got:
            hit[c["page"]] = got
        else:
            miss.append(c)
    return hit, miss


# ------------------------------------------------------------------ 第三步：逐人查

def fetch_one(player_id: str, time_value: str) -> dict | None:
    d = post("multidimension/list",
             {"dimension": "top", "sort_value": "desc", "sort_key": "kddiff",
              "player_options": options(player_id, 1, time_value, GRADES)})
    items = (d.get("data") or {}).get("items") or []
    if not items:
        return None
    fv = items[0].get("field_values") or {}
    # 没有顶级赛事样本时接口返回的是**一行全零**,不是空列表。存下来的话
    # rating 0.00 会被当成"打得极差",而事实是"这一年没在 S 级赛事出现过"。
    # 这两件事后果完全相反:前者该削弱他,后者该回退卡面。
    if not to_num(fv.get("map_count")):
        return None
    row = {k: fv.get(k) for k in KEEP if fv.get(k) is not None}
    row["5e_name"] = items[0].get("player_name")
    return row


def to_num(v):
    if v is None:
        return None
    s = str(v).replace("%", "").replace("+", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


# ------------------------------------------------------------------ 落盘

def load_existing() -> dict:
    """按 5eplay player_id 存。

    原来是按卡库的 `page` 存的——那是**生涯世界的主键**，当前世界里根本没有
    卡的人存不进去。换主键的时候把老文件迁一遍（老行里带着 `5e_id`），
    只合并不删除这条不受影响。
    """
    if not OUT_PATH.exists():
        return {}
    raw = json.loads(OUT_PATH.read_text(encoding="utf-8")).get("players") or {}
    out = {}
    for k, v in raw.items():
        pid = v.get("5e_id")
        if not pid:                       # 迁不过来的行不丢，原样保留
            out[k] = v
            continue
        v.setdefault("card_page", k if not k.startswith("csgo_pl_") else None)
        out[pid] = v
    return out


def write_out(players: dict, tv: str, stats: dict):
    payload = {
        "_note": ("5eplay 的选手当前竞技数据，由 scripts/fetch_5e_stats.py 生成，勿手改。"
                  "口径是**指标定义**不是旋钮：近 %d 个月 + %s。map_count 少的人"
                  "必须按 n/(n+k) 往均值收缩后再用（xKacpersky 1.52 是 6 张图打的）。"
                  "查不到的人不是数据缺失，是他没有顶级赛事样本——应当回退卡面。"
                  "人工别名写在 data/manual/5e_aliases.json。详见设计稿 §51。"
                  % (WINDOW_MONTHS, GRADE_LABEL)),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
        "source": API + "multidimension/list",
        "window": {"months": WINDOW_MONTHS, "value": tv},
        "grades": GRADES, "grade_label": GRADE_LABEL,
        "counts": stats,
        "players": dict(sorted(players.items())),
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")


# ------------------------------------------------------------------ 入口

def main():
    ap = argparse.ArgumentParser(description="抓 5eplay 当前竞技数据（本地工具）")
    ap.add_argument("--refresh-ids", action="store_true",
                    help="重抓全量 id 表（约 140 次请求）；默认用 .cache 里的")
    ap.add_argument("--all", action="store_true",
                    help="抓全部 648 张卡；默认只抓当前有队的人（AI 层只用得到这些）")
    ap.add_argument("--limit", type=int, default=0, help="只抓前 N 个，用来试跑")
    ap.add_argument("--pool-top", type=int, default=60,
                    help="当前世界池取排名前几的队伍（默认 60，够铺满一个 Major 名册）")
    ap.add_argument("--dry-run", action="store_true", help="只报匹配情况，不发查询、不写文件")
    args = ap.parse_args()

    if args.refresh_ids or not IDS_CACHE.exists():
        print("抓 id 表…（正序倒序各一遍，rating 并列会让单向扫漏人）")
        ids = fetch_ids()
        IDS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        IDS_CACHE.write_text(json.dumps(ids, ensure_ascii=False), encoding="utf-8")
        print("  拿到 %d 个 id -> %s" % (len(ids), IDS_CACHE.relative_to(ROOT)))
    else:
        ids = json.loads(IDS_CACHE.read_text(encoding="utf-8"))
        print("用缓存的 id 表 %d 人（--refresh-ids 重抓）" % len(ids))

    teams = snapshot_teams()
    snap = snapshot_ids(teams)
    print("队伍快照 id %d 个（权威层，来自队伍页，不经过名字）" % len(snap))
    index, dropped = build_index(snap, ids)
    if dropped:
        print("  三档都分不开、只能丢掉 %d 组（在别名表里直接钉 player_id 可救）：\n     %s"
              % (len(dropped), "  ".join("/".join(v) for v in dropped[:12])))

    cards = load_cards()
    target = cards if args.all else [c for c in cards if c.get("team")]
    hit, miss = match(target, index, load_aliases())
    print("匹配：%d/%d = %.0f%%（%s）"
          % (len(hit), len(target), 100.0 * len(hit) / max(len(target), 1),
             "全部卡" if args.all else "当前有队的人"))
    if miss:
        print("  对不上的 %d 人（在 data/manual/5e_aliases.json 里补别名）：\n     %s"
              % (len(miss), "  ".join(c["nickname"] for c in miss)))
    # 两个池子并起来：生涯世界按名字对到的人 + 当前世界前 N 名队伍的现役队员。
    # 后者会带进卡库里根本没有的人，那正是要的。
    pool = pool_targets(teams, args.pool_top)
    page_of = {pid: page for page, (pid, _n) in hit.items()}
    todo = dict(pool)
    for page, (pid, name5e) in hit.items():
        todo.setdefault(pid, name5e)
    print("当前世界池：前 %d 名队伍现役 %d 人，其中卡库里没有的 %d 人"
          % (args.pool_top, len(pool), sum(1 for i in pool if i not in page_of)))
    print("本次要查 %d 人（两池并集）" % len(todo))
    if args.dry_run:
        return 0

    tv = window_value()
    print("查询窗口 %s，等级 %s" % (tv, GRADE_LABEL))
    players = load_existing()
    before = {k: dict(v) for k, v in players.items()}
    items = sorted(todo.items(), key=lambda kv: kv[1].casefold())
    if args.limit:
        items = items[:args.limit]

    added = updated = unchanged = nodata = failed = 0
    for i, (pid, name5e) in enumerate(items, 1):
        try:
            row = fetch_one(pid, tv)
        except RuntimeError as exc:
            # 只合并不删除：抓失败的人保留旧数据并标 stale
            failed += 1
            if pid in players:
                players[pid]["stale"] = True
            print("  [%d/%d] %-14s 失败：%s" % (i, len(items), name5e, exc))
            continue
        finally:
            time.sleep(SLEEP)
        if row is None:
            nodata += 1
            continue                       # 没有顶级赛事样本，本来就该回退卡面
        row["5e_id"] = pid
        row["card_page"] = page_of.get(pid)      # 当前世界的人不一定有卡
        row.pop("stale", None)
        old = before.get(pid)
        players[pid] = row
        if old is None:
            added += 1
        elif {k: v for k, v in old.items() if k != "stale"} != row:
            updated += 1
        else:
            unchanged += 1
        if i % 25 == 0:
            print("  [%d/%d] …%s rating %s（%s 图）"
                  % (i, len(items), name5e, row.get("rating"), row.get("map_count")))

    stats = {"card_matched": len(hit), "pool": len(pool), "queried": len(items),
             "added": added, "updated": updated,
             "unchanged": unchanged, "no_top_tier_sample": nodata, "failed": failed}
    write_out(players, tv, stats)
    print("\n写入 %s" % OUT_PATH.relative_to(ROOT))
    print("  新增 %d  更新 %d  未变 %d  无顶级样本 %d  失败 %d（失败的人保留旧值并标 stale）"
          % (added, updated, unchanged, nodata, failed))
    print("  文件里现有 %d 人（只合并不删除——比对 HEAD 应当只增不减）" % len(players))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
