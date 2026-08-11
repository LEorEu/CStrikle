# -*- coding: utf-8 -*-
"""
Build the player database for cstrikle.

Sources:
  1. Liquipedia "Majors/Player Database" page  -> full pool of players who
     attended a CS:GO/CS2 Major, with nationality + per-Major entries.
  2. Liquipedia player infoboxes (batched, 50/req) -> birth_date, country,
     team, roles, status.
  3. blast.tv Counter-Strikle players.json (identity/search pool) -> marks the
     original puzzle pool; players not already in the Major pool are
     resolved to Liquipedia pages and added with majors_count=0.

Complies with Liquipedia API terms: descriptive UA, gzip, >=2.2s between
requests, action=query only (no action=parse).

Usage:
  python scraper/build_db.py            # full build -> data/players.json
  python scraper/build_db.py --no-blast # skip blast.tv merge
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

API = "https://liquipedia.net/counterstrike/api.php"
BLAST_PLAYERS_URL = "https://data.blast.tv/minigames/counterstrikle/players.json"
UA = "CStrikleDataBot/0.1 (personal wordle-like game project; contact: lbf186@gmail.com)"
RATE_SECONDS = 2.2
BATCH = 50

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.major_results import apply_major_results, load_major_results

_last_req = 0.0


def api_get(client: httpx.Client, params: dict) -> dict:
    global _last_req
    wait = RATE_SECONDS - (time.monotonic() - _last_req)
    if wait > 0:
        time.sleep(wait)
    p = {"format": "json", "formatversion": "2", **params}
    r = client.get(API, params=p)
    _last_req = time.monotonic()
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------- regions
# 表在 server/regions.py:管理页新增选手也要推赛区,而 scraper/ 不进镜像。
from server.regions import REGION, region_of  # noqa: E402,F401


# ------------------------------------------------- Majors/Player Database
PLAYER_TPL = re.compile(r"\{\{[Pp]layer\s*\|(.+?)\}\}")
TOURNEY_ROW = re.compile(r"^\|\s*\[\[([^\]|]+)(?:\|\s*([^\]]*))?\]\]")
TEAMPART = re.compile(r"\{\{TeamPart\|([^}|]+)(?:\|[^}]*)?\}\}", re.I)
PLACEMENT = re.compile(r"\{\{Placement\|([^}]+)\}\}", re.I)
CATEGORIES = re.compile(r'data-filter-categories="([^"]+)"')
YEAR = re.compile(r"(20\d\d)")


def parse_player_tpl(inner: str):
    """{{player|flag=ru|Dosia|link=...}} -> (page_title, display, flag)"""
    flag, name, link = None, None, None
    for part in inner.split("|"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            k, _, v = part.partition("=")
            k, v = k.strip().lower(), v.strip()
            if k == "flag":
                flag = v
            elif k == "link":
                link = v
        elif name is None:
            name = part
    if name is None:
        return None
    page = link or name
    return page, name, flag


def parse_major_db(wikitext: str) -> dict:
    """-> {page_title: {"nickname": display, "flag": xx, "majors": [entry...]}}"""
    players = {}
    current = None
    last_cats = ""
    for line in wikitext.splitlines():
        stripped = line.strip()
        if stripped.startswith("!"):
            m = PLAYER_TPL.search(stripped)
            if m:
                parsed = parse_player_tpl(m.group(1))
                if parsed:
                    page, display, flag = parsed
                    key = page[:1].upper() + page[1:] if page else page
                    current = players.setdefault(
                        key, {"nickname": display, "flag": flag, "majors": []}
                    )
            continue
        if stripped.startswith("|-"):
            m = CATEGORIES.search(stripped)
            last_cats = m.group(1) if m else ""
            continue
        if current is not None and stripped.startswith("|[["):
            m = TOURNEY_ROW.match(stripped)
            if not m:
                continue
            target, display = m.group(1).strip(), (m.group(2) or "").strip()
            event = display or target
            tm = TEAMPART.search(stripped)
            pm = PLACEMENT.search(stripped)
            ym = YEAR.findall(event)
            game = "cs2" if "cs2" in last_cats else ("csgo" if "csgo" in last_cats else "")
            current["majors"].append({
                "event": event,
                "page": target,
                "year": int(ym[-1]) if ym else None,
                "game": game,
                "team": tm.group(1).strip() if tm else "",
                "placement": pm.group(1).strip() if pm else "",
            })
    # drop stray entries without any tournament row (parsing noise)
    return {k: v for k, v in players.items() if v["majors"]}


# ---------------------------------------------------------------- infobox
INFOBOX_KEYS = ("id", "name", "romanized_name", "birth_date", "country",
                "status", "team", "roles", "role", "years_active")
CLEAN_REF = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", re.S)
CLEAN_TPL = re.compile(r"\{\{[^{}]*\}\}")
CLEAN_LINK = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]")
CLEAN_TAGS = re.compile(r"<[^>]+>")


def clean_value(v: str) -> str:
    v = CLEAN_REF.sub("", v)
    for _ in range(3):
        v = CLEAN_TPL.sub("", v)
    v = CLEAN_LINK.sub(r"\1", v)
    v = CLEAN_TAGS.sub("", v)
    v = v.replace("'''", "").replace("''", "")
    return v.strip()


INFOBOX_START = re.compile(r"\{\{Infobox\s+player", re.I)
PRESENT = re.compile(r"\bpresent\b", re.I)
STAFF_HISTORY_MARKERS = (
    "coach", "head coach", "assistant coach", "manager", "analyst",
    "broadcast analyst", "caster", "streamer", "content creator", "observer",
    "host",
)
NON_ROSTER_HISTORY_MARKERS = (
    "inactive", "benched", "bench", "substitute", "stand-in", "standin",
    "trial",
)
HEAD_COACH_ROLE_MARKERS = {"coach", "head coach"}
NON_HEAD_STAFF_ROLE_MARKERS = (
    set(STAFF_HISTORY_MARKERS) - HEAD_COACH_ROLE_MARKERS
) | {"inactive coach"}
RETIRED_STATUSES = {"retired"}


def _extract_templates(text: str, name: str) -> list[str]:
    """Extract balanced ``{{name|...}}`` templates, including nested templates."""
    start_re = re.compile(r"\{\{\s*" + re.escape(name) + r"\s*\|", re.I)
    templates = []
    offset = 0
    while match := start_re.search(text, offset):
        depth = 0
        cursor = match.start()
        while cursor < len(text) - 1:
            pair = text[cursor:cursor + 2]
            if pair == "{{":
                depth += 1
                cursor += 2
                continue
            if pair == "}}":
                depth -= 1
                cursor += 2
                if depth == 0:
                    templates.append(text[match.start() + 2:cursor - 2])
                    offset = cursor
                    break
                continue
            cursor += 1
        else:
            break
    return templates


def _split_template_args(inner: str) -> list[str]:
    """Split template arguments without splitting nested templates or links."""
    parts, current = [], []
    template_depth = link_depth = 0
    cursor = 0
    while cursor < len(inner):
        pair = inner[cursor:cursor + 2]
        if pair == "{{":
            template_depth += 1
            current.append(pair)
            cursor += 2
            continue
        if pair == "}}" and template_depth:
            template_depth -= 1
            current.append(pair)
            cursor += 2
            continue
        if pair == "[[":
            link_depth += 1
            current.append(pair)
            cursor += 2
            continue
        if pair == "]]" and link_depth:
            link_depth -= 1
            current.append(pair)
            cursor += 2
            continue
        char = inner[cursor]
        if char == "|" and not template_depth and not link_depth:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        cursor += 1
    parts.append("".join(current).strip())
    return parts


def parse_team_history(wikitext: str) -> list[dict]:
    """Parse Liquipedia ``TH`` rows while preserving their roster modifiers."""
    history = []
    for inner in _extract_templates(wikitext, "TH"):
        parts = _split_template_args(inner)
        if len(parts) < 3:
            continue
        period = clean_value(parts[1])
        team = clean_value(parts[2])
        details = []
        for raw in parts[3:]:
            if "=" in raw:
                key, _, value = raw.partition("=")
                if key.strip().casefold() not in {"role", "status", "type", "position"}:
                    continue
                raw = value
            value = clean_value(raw)
            if value:
                details.append(value)
        if period or team:
            history.append({
                "period": period,
                "team": team,
                "details": details,
            })
    return history


def _normalized_words(values) -> str:
    if isinstance(values, str):
        values = [values]
    text = " ".join(str(value or "") for value in values)
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def _team_key(value: str) -> str:
    return "".join(re.findall(r"[a-z0-9]+", (value or "").casefold()))


def _start_key(period: str) -> tuple[int, int, int]:
    match = re.search(r"(\d{4})-(\d{2}|\?\?)-(\d{2}|\?\?)", period or "")
    if not match:
        return (0, 0, 0)
    return tuple(0 if value == "??" else int(value) for value in match.groups())


def _history_kind(entry: dict) -> str:
    details = _normalized_words(entry.get("details", []))
    if any(marker in details for marker in NON_ROSTER_HISTORY_MARKERS):
        return "inactive"
    if "assistant coach" in details:
        return "assistant_coach"
    if "head coach" in details or "coach" in details:
        return "head_coach"
    if any(marker in details for marker in STAFF_HISTORY_MARKERS):
        return "staff"
    return "player"


def current_team_history(infobox: dict) -> list[dict]:
    return [
        entry
        for entry in infobox.get("_team_history", [])
        if PRESENT.search(entry.get("period", ""))
    ]


def _role_values(infobox: dict) -> set[str]:
    raw = str(infobox.get("roles") or infobox.get("role") or "")
    return {
        _normalized_words(value)
        for value in re.split(r"[,;/]", raw)
        if _normalized_words(value)
    }


def _resolve_current_team(
    candidates: list[dict],
    source_team: str,
    *,
    reason_suffix: str,
) -> tuple[str, str]:
    by_team = {}
    for entry in candidates:
        key = _team_key(entry.get("team", ""))
        previous = by_team.get(key)
        if previous is None or _start_key(entry.get("period", "")) > _start_key(
            previous.get("period", "")
        ):
            by_team[key] = entry
    candidates = list(by_team.values())
    if not candidates:
        return "", f"no_current_{reason_suffix}"
    if len(candidates) == 1:
        return candidates[0]["team"], f"single_current_{reason_suffix}"

    newest_key = max(_start_key(entry.get("period", "")) for entry in candidates)
    newest = [
        entry for entry in candidates
        if _start_key(entry.get("period", "")) == newest_key
    ]
    if len(newest) == 1:
        return newest[0]["team"], f"newest_current_{reason_suffix}"

    source_key = _team_key(source_team)
    source_matches = [
        entry for entry in newest
        if _team_key(entry.get("team", "")) == source_key
    ]
    if source_key and len(source_matches) == 1:
        return source_matches[0]["team"], "top_level_tiebreaker"
    teams = ", ".join(sorted({entry["team"] for entry in newest}))
    raise ValueError(f"无法消解多个当前正式队伍：{teams}")


def resolve_game_team(infobox: dict) -> tuple[str, str]:
    """Return the gameplay team and an auditable resolution reason.

    Active players and current head coaches retain a team. Assistant coaches,
    inactive/benched members, and other staff are teamless in gameplay.
    """
    source_team = infobox.get("team") or ""
    status = _normalized_words(infobox.get("status") or "")
    role_values = _role_values(infobox)
    current = current_team_history(infobox)
    head_coach_candidates = [
        entry for entry in current
        if _history_kind(entry) == "head_coach" and entry.get("team")
    ]

    if head_coach_candidates:
        return _resolve_current_team(
            head_coach_candidates,
            source_team,
            reason_suffix="head_coach_team",
        )
    if role_values & NON_HEAD_STAFF_ROLE_MARKERS:
        roles = " ".join(sorted(role_values))
        return "", f"staff_role:{roles}"
    if role_values & HEAD_COACH_ROLE_MARKERS:
        if not current and source_team:
            return source_team, "head_coach_top_level_fallback"
        return "", "no_current_head_coach_team"
    if status in RETIRED_STATUSES:
        return "", f"career_status:{status}"
    if not current:
        if status == "inactive":
            return "", "career_status:inactive"
        return source_team, "top_level_fallback"

    candidates = [
        entry for entry in current
        if _history_kind(entry) == "player" and entry.get("team")
    ]
    return _resolve_current_team(
        candidates,
        source_team,
        reason_suffix="player_roster",
    )


def parse_infobox(wikitext: str) -> dict:
    m = INFOBOX_START.search(wikitext)
    if not m:
        return {}
    section = wikitext[m.start():]
    cut = section.find("\n==")
    if cut > 0:
        section = section[:cut]
    out = {}
    for line in section.splitlines():
        m = re.match(r"^\|(\w+)\s*=\s*(.*)$", line.strip())
        if not m:
            continue
        k, v = m.group(1).lower(), m.group(2)
        if k in INFOBOX_KEYS and k not in out:
            out[k] = clean_value(v)
    out["_team_history"] = parse_team_history(section)
    return out


def fetch_infoboxes(client: httpx.Client, titles: list) -> dict:
    """Batched revisions query. -> {requested_title: infobox_dict_or_None}"""
    result = {}
    for i in range(0, len(titles), BATCH):
        chunk = titles[i:i + BATCH]
        d = api_get(client, {
            "action": "query",
            "titles": "|".join(chunk),
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
            "redirects": "1",
        })
        q = d.get("query", {})
        # map final title back to requested title
        back = {}
        for m in q.get("normalized", []) + q.get("redirects", []):
            back[m["to"]] = back.get(m["from"], m["from"])
        for page in q.get("pages", []):
            req = back.get(page["title"], page["title"])
            if page.get("missing"):
                result[req] = None
                continue
            try:
                content = page["revisions"][0]["slots"]["main"]["content"]
            except (KeyError, IndexError):
                result[req] = None
                continue
            ib = parse_infobox(content)
            if ib:
                ib["_final_title"] = page["title"]
                result[req] = ib
            else:
                result[req] = None
        done = min(i + BATCH, len(titles))
        print(f"  infobox batch {done}/{len(titles)}")
    return result


def opensearch(client: httpx.Client, term: str):
    d = api_get(client, {"action": "opensearch", "search": term, "limit": "3",
                         "namespace": "0"})
    hits = d[1] if isinstance(d, list) and len(d) > 1 else []
    return hits[0] if hits else None


def unresolved_blast_titles(pool: dict, blast: list[dict]) -> list[str]:
    """Return BLAST nicknames that are not already represented by a Major player."""
    known_titles = {title.casefold() for title in pool}
    known_nicks = {
        str(entry.get("nickname", "")).casefold()
        for entry in pool.values()
        if entry.get("nickname")
    }
    return [
        player["nickname"]
        for player in blast
        if player["nickname"].casefold() not in known_titles
        and player["nickname"].casefold() not in known_nicks
    ]


# ------------------------------------------------------------------ main
def build(include_blast: bool = True, out: Path | None = None):
    DATA.mkdir(exist_ok=True)
    with httpx.Client(headers={"User-Agent": UA, "Accept-Encoding": "gzip"},
                      timeout=60) as client:
        print("[1/4] fetching Majors/Player Database ...")
        d = api_get(client, {"action": "query", "titles": "Majors/Player Database",
                             "prop": "revisions", "rvprop": "content",
                             "rvslots": "main"})
        wikitext = d["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]
        pool = parse_major_db(wikitext)
        major_results = load_major_results()
        for entry in pool.values():
            entry["majors"] = apply_major_results(entry["majors"], major_results)
        print(f"  parsed {len(pool)} Major players")

        blast = []
        if include_blast:
            print("[2/4] fetching blast.tv Counter-Strikle identity list ...")
            r = client.get(BLAST_PLAYERS_URL)
            r.raise_for_status()
            blast = r.json()
            print(f"  {len(blast)} puzzle identities from blast.tv")
        blast_nicks = {p["nickname"] for p in blast}

        # blast players not in the Major pool -> resolve their liquipedia page
        extra_titles = unresolved_blast_titles(pool, blast)

        print("[3/4] fetching infoboxes ...")
        all_titles = list(pool.keys()) + extra_titles
        boxes = fetch_infoboxes(client, all_titles)

        # unresolved extras: try opensearch once
        misses = [t for t in extra_titles if boxes.get(t) is None]
        if misses:
            print(f"  resolving {len(misses)} blast players via opensearch ...")
            retry_map = {}
            for t in misses:
                hit = opensearch(client, t)
                if hit and boxes.get(hit) is None:
                    retry_map[t] = hit
            if retry_map:
                found = fetch_infoboxes(client, list(retry_map.values()))
                for orig, page in retry_map.items():
                    if found.get(page):
                        boxes[orig] = found[page]

    print("[4/4] assembling players.json ...")
    players = []
    seen_pages = set()

    def assemble(req_title, entry, majors):
        ib = boxes.get(req_title)
        if ib is None:
            return None
        final = ib.get("_final_title", req_title)
        if final in seen_pages:
            return "dup"
        seen_pages.add(final)
        country = ib.get("country", "")
        nickname = ib.get("id") or (entry or {}).get("nickname") or req_title
        roles_raw = ib.get("roles") or ib.get("role") or ""
        roles = [r.strip().lower() for r in roles_raw.split(",") if r.strip()]
        years = sorted({m["year"] for m in majors if m["year"]})
        team, team_resolution = resolve_game_team(ib)
        rec = {
            "page": final,
            "nickname": nickname,
            "real_name": ib.get("romanized_name") or ib.get("name") or "",
            "country": country,
            "region": region_of(country),
            "birth_date": ib.get("birth_date") or "",
            "team": team,
            "source_team": ib.get("team") or "",
            "current_team_history": current_team_history(ib),
            "team_resolution": team_resolution,
            "status": ib.get("status") or "",
            "roles": roles,
            "majors_count": len(majors),
            "first_major_year": years[0] if years else None,
            "last_major_year": years[-1] if years else None,
            "majors": majors,
            "in_blast_pool": nickname in blast_nicks or req_title in blast_nicks,
        }
        if country and rec["region"] == "Other":
            print(f"  ! unmapped country: {country} ({nickname})")
        return rec

    dup = miss = 0
    for title, entry in pool.items():
        rec = assemble(title, entry, entry["majors"])
        if rec == "dup":
            dup += 1
        elif rec:
            players.append(rec)
        else:
            miss += 1
            print(f"  ! no page for Major player: {title}")
    for t in extra_titles:
        rec = assemble(t, None, [])
        if rec == "dup":
            dup += 1
        elif rec:
            players.append(rec)
        else:
            miss += 1
            print(f"  ! no page for blast player: {t}")

    out_doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "liquipedia.net (CC-BY-SA 3.0) + blast.tv puzzle identity list",
        "count": len(players),
        "players": players,
    }
    path = out or (DATA / "players.json")
    path.write_text(json.dumps(out_doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"done: {len(players)} players -> {path}  (dups merged: {dup}, missing: {miss})")


def refresh_existing(path: Path = DATA / "players.json",
                     out: Path | None = None) -> None:
    """Refresh current role/team fields without rebuilding Major/manual records."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    players = raw.get("players")
    if not isinstance(players, list):
        raise ValueError(f"invalid players file: {path}")
    titles = [str(player.get("page") or "") for player in players]
    with httpx.Client(headers={"User-Agent": UA, "Accept-Encoding": "gzip"},
                      timeout=60) as client:
        boxes = fetch_infoboxes(client, titles)

    refreshed, missing = [], []
    for player in players:
        page = str(player.get("page") or "")
        infobox = boxes.get(page)
        if not infobox:
            missing.append(page)
            refreshed.append(player)
            continue
        roles_raw = infobox.get("roles") or infobox.get("role") or ""
        team, resolution = resolve_game_team(infobox)
        updated = dict(player)
        updated.update({
            "team": team,
            "source_team": infobox.get("team") or "",
            "current_team_history": current_team_history(infobox),
            "team_resolution": resolution,
            "status": infobox.get("status") or "",
            "roles": [
                role.strip().lower()
                for role in roles_raw.split(",")
                if role.strip()
            ],
        })
        refreshed.append(updated)

    raw["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    raw["players"] = refreshed
    target = out or path
    target.write_text(
        json.dumps(raw, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"refreshed: {len(refreshed) - len(missing)}/{len(refreshed)}")
    if missing:
        print(f"kept unchanged because page was unavailable: {len(missing)}")
        for page in missing:
            print(f"  - {page}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-blast", action="store_true", help="skip blast.tv identity merge"
    )
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="refresh current team/status/roles while preserving existing records",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write result to this path instead of data/players.json "
             "(staging workflow: --out data/players.staging.json)",
    )
    args = parser.parse_args(argv)
    if args.refresh_existing:
        refresh_existing(out=args.out)
    else:
        build(include_blast=not args.no_blast, out=args.out)


if __name__ == "__main__":
    main()
