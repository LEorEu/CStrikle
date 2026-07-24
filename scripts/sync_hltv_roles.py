#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用普通本地浏览器采集 HLTV 角色证据，并生成可人工审核的建议。

HLTV 没有供本项目使用的稳定公开 API，普通 HTTP 请求也可能收到
Cloudflare 403。因此本工具只用于本地维护，默认打开可见 Chrome，
低速访问搜索页和选手主页。它不会在生产服务中运行，也不会自动覆盖
data/player_overrides.json。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote_plus, urljoin


ROOT = Path(__file__).resolve().parents[1]
PLAYERS_PATH = ROOT / "data" / "players.json"
OVERRIDES_PATH = ROOT / "data" / "player_overrides.json"
MAP_PATH = ROOT / "data" / "hltv_player_map.json"
CACHE_PATH = ROOT / ".cache" / "hltv" / "browser_cache.json"
REVIEW_PATH = ROOT / ".cache" / "hltv" / "role_review.json"

HLTV_ORIGIN = "https://www.hltv.org"
HLTV_PLAYER_RE = re.compile(r"/player/(\d+)/([^/?#]+)", re.IGNORECASE)
ROLE_VALUES = {"IGL", "AWPer", "Rifler", "Coach"}
IGL_KEYWORDS = (
    "igl",
    "in-game leader",
    "in game leader",
    "calling",
    "caller",
    "captain",
    "leadership",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def normalize(value: str | None) -> str:
    """大小写/变音符号/标点无关的身份匹配键。"""
    folded = "".join(
        char
        for char in unicodedata.normalize("NFKD", value or "")
        if not unicodedata.combining(char)
    ).casefold()
    return "".join(char for char in folded if char.isalnum())


def name_tokens(value: str | None) -> set[str]:
    folded = "".join(
        char
        for char in unicodedata.normalize("NFKD", value or "")
        if not unicodedata.combining(char)
    ).casefold()
    return {
        token
        for token in re.split(r"[^\w]+", folded, flags=re.UNICODE)
        if len(token) >= 2
    }


def token_overlap(left: str | None, right: str | None) -> float:
    a, b = name_tokens(left), name_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def token_coverage(expected: str | None, observed: str | None) -> float:
    """候选文本常含昵称等额外词，只要求本地真名 token 被完整覆盖。"""
    expected_tokens, observed_tokens = name_tokens(expected), name_tokens(observed)
    if not expected_tokens or not observed_tokens:
        return 0.0
    return len(expected_tokens & observed_tokens) / len(expected_tokens)


def parse_player_href(href: str) -> tuple[int, str] | None:
    match = HLTV_PLAYER_RE.search(href or "")
    if not match:
        return None
    return int(match.group(1)), match.group(2)


def score_candidate(local: dict, candidate: dict) -> float:
    """给 HLTV 搜索结果打身份分；昵称不能单独决定同名选手。"""
    local_nick = normalize(local.get("nickname"))
    local_real = local.get("real_name") or ""
    candidate_nick = normalize(candidate.get("nickname"))
    candidate_slug = normalize(candidate.get("slug"))
    candidate_text = candidate.get("text") or ""
    candidate_real = candidate.get("real_name") or ""

    score = 0.0
    if local_nick and local_nick in {candidate_nick, candidate_slug}:
        score += 0.55
    elif local_nick and local_nick in normalize(candidate_text):
        score += 0.30

    real_overlap = max(
        token_overlap(local_real, candidate_real),
        token_coverage(local_real, candidate_text),
    )
    score += 0.40 * real_overlap

    local_country = normalize(local.get("country"))
    candidate_country = normalize(candidate.get("country"))
    if local_country and candidate_country and local_country == candidate_country:
        score += 0.05
    return round(min(score, 1.0), 4)


def choose_candidate(
    local: dict,
    candidates: list[dict],
    min_score: float = 0.75,
    min_margin: float = 0.15,
) -> tuple[dict | None, str]:
    ranked = sorted(
        ((score_candidate(local, item), item) for item in candidates),
        key=lambda row: row[0],
        reverse=True,
    )
    if not ranked or ranked[0][0] < min_score:
        best = ranked[0][0] if ranked else 0
        return None, f"没有足够可信的匹配（最高分 {best:.2f}）"
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < min_margin:
        return None, (
            f"前两名分差不足（{ranked[0][0]:.2f} vs "
            f"{ranked[1][0]:.2f}）"
        )
    selected = dict(ranked[0][1])
    selected["match_score"] = ranked[0][0]
    return selected, "昵称与真实姓名匹配"


def identity_matches(
    local: dict,
    profile: dict,
    accepted_real_names: list[str] | None = None,
) -> bool:
    nick_ok = normalize(local.get("nickname")) == normalize(profile.get("nickname"))
    expected_names = [local.get("real_name") or "", *(accepted_real_names or [])]
    real_ok = any(
        token_overlap(expected, profile.get("real_name")) >= 0.5
        for expected in expected_names
    )
    return nick_ok and real_ok


def primary_role_from_local(local: dict) -> str:
    explicit = local.get("game_role")
    if explicit in ROLE_VALUES:
        return explicit
    roles = local.get("roles") or []
    if any(role in {"coach", "assistant coach"} for role in roles):
        return "Coach"
    if "igl" in roles:
        return "IGL"
    mapping = {
        "awp": "AWPer",
        "awper": "AWPer",
        "rifle": "Rifler",
        "rifler": "Rifler",
        "support": "Rifler",
        "lurk": "Rifler",
        "lurker": "Rifler",
        "entry": "Rifler",
        "entryfragger": "Rifler",
    }
    for role in roles:
        if role in mapping:
            return mapping[role]
    return "?"


def suggest_role(
    local: dict,
    profile: dict | None,
    igl_evidence: list[dict],
    existing_override: dict | None = None,
    *,
    min_recent_maps: int = 5,
    awper_score: int = 70,
    rifler_score: int = 30,
) -> dict:
    """分开判断指挥职责和武器角色，最后生成保守的主角色建议。"""
    existing_override = existing_override or {}
    local_roles = local.get("roles") or []
    current_role = primary_role_from_local(local)
    maps = profile.get("recent_maps") if profile else None
    sniping = profile.get("sniping_score") if profile else None

    weapon_role = None
    weapon_confidence = "unknown"
    weapon_reason = "HLTV 主页没有足够的近期地图数据"
    if (
        isinstance(maps, int)
        and maps >= min_recent_maps
        and isinstance(sniping, int)
    ):
        if sniping >= awper_score:
            weapon_role = "AWPer"
            weapon_confidence = "high"
            weapon_reason = (
                f"HLTV 近三个月 {maps} 张地图，Sniping {sniping}/100"
            )
        elif sniping <= rifler_score:
            weapon_role = "Rifler"
            weapon_confidence = "high"
            weapon_reason = (
                f"HLTV 近三个月 {maps} 张地图，Sniping {sniping}/100"
            )
        else:
            weapon_confidence = "mixed"
            weapon_reason = (
                f"HLTV 近三个月 {maps} 张地图，Sniping {sniping}/100，"
                "处于混合区"
            )

    if existing_override.get("game_role") in ROLE_VALUES:
        return {
            "suggested_role": existing_override["game_role"],
            "confidence": "protected",
            "reason": "已有 game_role 人工覆盖；同步工具不会自动替换",
            "weapon_role": weapon_role,
            "weapon_confidence": weapon_confidence,
            "weapon_reason": weapon_reason,
        }

    if "igl" in local_roles:
        evidence_note = (
            f"并找到 {len(igl_evidence)} 条 HLTV IGL/指挥语境"
            if igl_evidence
            else "；HLTV 主页本身没有结构化 IGL 字段"
        )
        return {
            "suggested_role": "IGL",
            "confidence": "high" if igl_evidence else "medium",
            "reason": f"Liquipedia 当前角色包含 IGL{evidence_note}",
            "weapon_role": weapon_role,
            "weapon_confidence": weapon_confidence,
            "weapon_reason": weapon_reason,
        }

    if weapon_role:
        return {
            "suggested_role": weapon_role,
            "confidence": weapon_confidence,
            "reason": weapon_reason,
            "weapon_role": weapon_role,
            "weapon_confidence": weapon_confidence,
            "weapon_reason": weapon_reason,
        }

    return {
        "suggested_role": None,
        "confidence": "manual",
        "reason": (
            f"当前本地推断为 {current_role}，但 {weapon_reason}；"
            "退役/历史选手需按其巅峰时期人工确认"
        ),
        "weapon_role": weapon_role,
        "weapon_confidence": weapon_confidence,
        "weapon_reason": weapon_reason,
    }


class BrowserCollector:
    """普通 Playwright 浏览器采集器；不包含代理或 challenge 绕过。"""

    def __init__(
        self,
        *,
        cache_path: Path,
        headless: bool,
        browser_channel: str | None,
        executable_path: str | None,
        min_interval: float,
        timeout_ms: int,
        cache_days: int,
        refresh: bool,
    ):
        self.cache_path = cache_path
        self.cache = load_json(cache_path, {"schema_version": 1, "entries": {}})
        self.cache.setdefault("entries", {})
        self.headless = headless
        self.browser_channel = browser_channel
        self.executable_path = executable_path
        self.min_interval = max(min_interval, 0.0)
        self.timeout_ms = timeout_ms
        self.cache_seconds = cache_days * 86400
        self.refresh = refresh
        self._last_request_at = 0.0
        self._playwright = self._browser = self._page = None

    def __enter__(self) -> "BrowserCollector":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "缺少本地维护依赖。请运行："
                r".\.venv\Scripts\pip install -r requirements-maintenance.txt"
            ) from exc
        self._playwright = sync_playwright().start()
        launch_args: dict[str, Any] = {"headless": self.headless}
        if self.executable_path:
            launch_args["executable_path"] = self.executable_path
        elif self.browser_channel:
            launch_args["channel"] = self.browser_channel
        try:
            self._browser = self._playwright.chromium.launch(**launch_args)
        except Exception as exc:
            self._playwright.stop()
            raise RuntimeError(
                "无法启动浏览器。可安装 Chrome，或运行 "
                "`python -m playwright install chromium` 后使用 "
                "`--browser-channel chromium`。"
            ) from exc
        context = self._browser.new_context(locale="en-US")
        self._page = context.new_page()
        self._page.set_default_timeout(self.timeout_ms)
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._save_cache()

    def _save_cache(self) -> None:
        self.cache["updated_at"] = utc_now()
        write_json(self.cache_path, self.cache)

    def _cached(self, key: str) -> Any | None:
        if self.refresh:
            return None
        entry = self.cache["entries"].get(key)
        if not entry:
            return None
        fetched = entry.get("fetched_unix", 0)
        if time.time() - fetched > self.cache_seconds:
            return None
        return entry.get("value")

    def _remember(self, key: str, value: Any) -> Any:
        self.cache["entries"][key] = {
            "fetched_at": utc_now(),
            "fetched_unix": time.time(),
            "value": value,
        }
        self._save_cache()
        return value

    def _throttle(self) -> None:
        remaining = self.min_interval - (time.monotonic() - self._last_request_at)
        if remaining > 0:
            time.sleep(remaining)

    def _goto(self, url: str) -> None:
        self._throttle()
        response = self._page.goto(url, wait_until="domcontentloaded")
        self._last_request_at = time.monotonic()
        status = response.status if response else None
        title = self._page.title()
        body_start = self._page.locator("body").inner_text()[:500].casefold()
        if status == 403 or "access denied" in body_start:
            raise RuntimeError(
                f"HLTV 返回 403/Access denied：{url}。保留现有数据，稍后重试。"
            )
        if status and status >= 400:
            raise RuntimeError(f"HLTV 返回 HTTP {status}：{url}")
        if "just a moment" in title.casefold():
            raise RuntimeError(
                "HLTV 要求浏览器人工验证。请使用默认可见模式完成验证后重试。"
            )

    def search_players(self, query: str) -> list[dict]:
        key = f"player-search:{normalize(query)}"
        cached = self._cached(key)
        if cached is not None:
            return cached
        self._goto(f"{HLTV_ORIGIN}/search?query={quote_plus(query)}")
        raw = self._page.locator('a[href*="/player/"]').evaluate_all(
            """
            (anchors) => anchors.map((a) => {
              let text = (a.innerText || a.textContent || '').trim();
              let node = a.parentElement;
              for (let i = 0; i < 3 && node; i++, node = node.parentElement) {
                const candidate = (node.innerText || '').trim();
                if (candidate.length > text.length && candidate.length < 300) {
                  text = candidate;
                }
              }
              return {
                href: a.getAttribute('href') || '',
                nickname: (a.innerText || a.textContent || '').trim(),
                text,
              };
            })
            """
        )
        results: dict[tuple[int, str], dict] = {}
        for item in raw:
            parsed = parse_player_href(item.get("href", ""))
            if not parsed:
                continue
            player_id, slug = parsed
            result = dict(item)
            result.update(
                {
                    "hltv_id": player_id,
                    "slug": slug,
                    "url": urljoin(HLTV_ORIGIN, item["href"]),
                }
            )
            results[(player_id, slug)] = result
        return self._remember(key, list(results.values()))

    def collect_profile(self, player_id: int, slug: str) -> dict:
        key = f"profile:{player_id}:{normalize(slug)}"
        cached = self._cached(key)
        if cached is not None:
            return cached
        url = f"{HLTV_ORIGIN}/player/{player_id}/{slug}"
        self._goto(url)
        value = self._page.evaluate(
            """
            () => {
              const text = (el) => (el?.innerText || el?.textContent || '').trim();
              const nickname = text(document.querySelector('h1.playerNickname'));
              const realBox = document.querySelector('.playerRealname');
              const country = realBox?.querySelector('img.flag')?.getAttribute('title')
                || realBox?.querySelector('img.flag')?.getAttribute('alt') || '';
              const realLines = text(realBox).split(/\\n+/)
                .map((line) => line.trim())
                .filter((line) => line && line !== country);
              let team = '';
              let teamUrl = '';
              for (const a of document.querySelectorAll('a[href^="/team/"]')) {
                const context = text(a.closest('.playerInfoRow, .player-info-box, tr, li, div'));
                if (/current team/i.test(context)) {
                  team = text(a);
                  teamUrl = a.getAttribute('href') || '';
                  break;
                }
              }
              const cards = [...document.querySelectorAll('.player-stat-top')];
              let sniping = null;
              for (const card of cards) {
                if (/sniping/i.test(text(card.querySelector('b')))) {
                  const found = text(card.querySelector('.statsVal')).match(/\\d+/);
                  if (found) sniping = Number(found[0]);
                }
              }
              const body = text(document.body);
              const period = body.match(/Past\\s+3\\s+months\\s*[•·-]\\s*(\\d+)\\s+maps?/i);
              return {
                nickname,
                real_name: realLines[0] || '',
                country,
                current_team: team,
                current_team_url: teamUrl,
                recent_period: 'Past 3 months',
                recent_maps: period ? Number(period[1]) : null,
                sniping_score: sniping,
              };
            }
            """
        )
        value.update(
            {
                "hltv_id": player_id,
                "slug": slug,
                "profile_url": url,
                "collected_at": utc_now(),
            }
        )
        if value.get("current_team_url"):
            value["current_team_url"] = urljoin(
                HLTV_ORIGIN, value["current_team_url"]
            )
        return self._remember(key, value)

    def collect_igl_evidence(self, nickname: str) -> list[dict]:
        key = f"igl-search:{normalize(nickname)}"
        cached = self._cached(key)
        if cached is not None:
            return cached
        self._goto(
            f"{HLTV_ORIGIN}/search?query={quote_plus(nickname + ' IGL')}"
        )
        raw = self._page.locator('a[href*="/news/"]').evaluate_all(
            """
            (anchors) => anchors.map((a) => ({
              title: (a.innerText || a.textContent || '').trim(),
              href: a.getAttribute('href') || '',
            }))
            """
        )
        seen, evidence = set(), []
        for item in raw:
            title = " ".join((item.get("title") or "").split())
            lowered = title.casefold()
            if not title or not any(word in lowered for word in IGL_KEYWORDS):
                continue
            url = urljoin(HLTV_ORIGIN, item.get("href") or "")
            if url in seen:
                continue
            seen.add(url)
            evidence.append({"title": title, "url": url})
        return self._remember(key, evidence[:8])


def load_local_players(path: Path) -> list[dict]:
    raw = load_json(path)
    if not isinstance(raw, dict) or not isinstance(raw.get("players"), list):
        raise ValueError(f"无效的 players 数据：{path}")
    return raw["players"]


def load_stable_map(path: Path) -> dict[str, dict]:
    raw = load_json(path, {"players": {}})
    players = raw.get("players", {}) if isinstance(raw, dict) else {}
    return players if isinstance(players, dict) else {}


def select_local_players(
    players: list[dict],
    selectors: list[str] | None,
    stable_map: dict[str, dict],
    select_all: bool,
) -> list[dict]:
    if select_all:
        return players
    if not selectors:
        raise ValueError("请使用 --players 指定选手，或显式使用 --all")
    indexes: dict[str, list[dict]] = {}
    for player in players:
        for value in (player.get("page"), player.get("nickname")):
            if value:
                indexes.setdefault(normalize(value), []).append(player)
    for page, mapped in stable_map.items():
        local = next((p for p in players if p.get("page") == page), None)
        if not local:
            continue
        for alias in mapped.get("aliases", []):
            indexes.setdefault(normalize(alias), []).append(local)

    selected = []
    for selector in selectors:
        hits = list({p["page"]: p for p in indexes.get(normalize(selector), [])}.values())
        if not hits:
            raise ValueError(f"本地数据库找不到选手：{selector}")
        if len(hits) > 1:
            pages = ", ".join(player["page"] for player in hits)
            raise ValueError(f"选手名有歧义：{selector} -> {pages}")
        if hits[0] not in selected:
            selected.append(hits[0])
    return selected


def mapped_candidate(local: dict, stable_map: dict[str, dict]) -> dict | None:
    mapped = stable_map.get(local.get("page", ""))
    if not mapped:
        return None
    return {
        "hltv_id": int(mapped["hltv_id"]),
        "slug": mapped["slug"],
        "nickname": mapped.get("nickname", ""),
        "real_name": mapped.get("real_name", ""),
        "url": (
            f"{HLTV_ORIGIN}/player/{int(mapped['hltv_id'])}/{mapped['slug']}"
        ),
        "match_score": 1.0,
        "match_source": "data/hltv_player_map.json",
        "accepted_real_names": mapped.get("hltv_real_names", []),
        "role_evidence": mapped.get("role_evidence", []),
    }


def collect_one(
    collector: BrowserCollector,
    local: dict,
    stable_map: dict[str, dict],
    overrides: dict,
    with_igl_news: bool,
) -> dict:
    candidate = mapped_candidate(local, stable_map)
    match_reason = "使用已人工确认的稳定映射"
    search_error = None
    if not candidate:
        try:
            candidates = collector.search_players(
                local.get("nickname") or local["page"]
            )
            candidate, match_reason = choose_candidate(local, candidates)
        except RuntimeError as exc:
            # 搜索页被拒不能中断整批采集；按人记录错误，交给熔断器统计。
            candidate, match_reason = None, f"HLTV 搜索失败：{exc}"
            search_error = str(exc)
    base = {
        "local_page": local.get("page"),
        "nickname": local.get("nickname"),
        "real_name": local.get("real_name"),
        "country": local.get("country"),
        "team": local.get("team") or "",
        "status": local.get("status") or "",
        "local_roles": local.get("roles") or [],
        "current_inference": primary_role_from_local(local),
        "match": candidate,
        "match_reason": match_reason,
        "profile": None,
        "igl_evidence": [
            item
            for item in (candidate or {}).get("role_evidence", [])
            if item.get("kind") in {"igl", "igl_awper"}
        ],
        "manual_evidence": (candidate or {}).get("role_evidence", []),
        "igl_evidence_error": None,
        "suggestion": None,
        "decision": None,
        "decision_field": "game_role",
        "error": None,
    }
    if not candidate:
        base["error"] = search_error
        base["suggestion"] = {
            "suggested_role": None,
            "confidence": "manual",
            "reason": match_reason,
        }
        return base
    try:
        profile = collector.collect_profile(
            int(candidate["hltv_id"]), candidate["slug"]
        )
        base["profile"] = profile
        if not identity_matches(
            local, profile, candidate.get("accepted_real_names", [])
        ):
            raise RuntimeError(
                "HLTV 主页身份与本地昵称/真实姓名不一致，拒绝自动采用"
            )
        if with_igl_news and "igl" in (local.get("roles") or []):
            try:
                extra_evidence = collector.collect_igl_evidence(
                    local.get("nickname") or local["page"]
                )
                seen_urls = {
                    item.get("url") for item in base["igl_evidence"]
                }
                base["igl_evidence"].extend(
                    item
                    for item in extra_evidence
                    if item.get("url") not in seen_urls
                )
            except Exception as exc:
                # 新闻搜索只是 IGL 的补充证据，失败不能抹掉已成功的主页证据。
                base["igl_evidence_error"] = str(exc)
        base["suggestion"] = suggest_role(
            local,
            profile,
            base["igl_evidence"],
            overrides.get(local["page"], {}),
        )
    except Exception as exc:
        base["error"] = str(exc)
        base["suggestion"] = {
            "suggested_role": None,
            "confidence": "manual",
            "reason": f"采集失败，保留当前推断：{exc}",
        }
    return base


def collect_command(args: argparse.Namespace) -> int:
    players = load_local_players(args.players_path)
    stable_map = load_stable_map(args.map_path)
    overrides = load_json(args.overrides_path, {})
    selected = select_local_players(players, args.players, stable_map, args.all)
    old_review = load_json(args.output, {"players": []})
    old_decisions = {
        row.get("local_page"): (
            row.get("decision"),
            row.get("decision_field", "game_role"),
        )
        for row in old_review.get("players", [])
        if row.get("local_page")
    }

    results = []
    consecutive_blocks = 0
    stopped_early = False
    browser_channel = (args.browser_channel or "").strip()
    if browser_channel.casefold() in {"bundled", "none"}:
        browser_channel = None
    with BrowserCollector(
        cache_path=args.cache_path,
        headless=args.headless,
        browser_channel=browser_channel,
        executable_path=args.browser_executable,
        min_interval=args.min_interval,
        timeout_ms=args.timeout * 1000,
        cache_days=args.cache_days,
        refresh=args.refresh,
    ) as collector:
        for index, local in enumerate(selected, 1):
            print(
                f"[{index}/{len(selected)}] {local.get('nickname')} "
                f"({local.get('real_name')})"
            )
            row = collect_one(
                collector,
                local,
                stable_map,
                overrides,
                args.with_igl_news,
            )
            if local["page"] in old_decisions:
                row["decision"], row["decision_field"] = old_decisions[local["page"]]
            results.append(row)
            if "403/Access denied" in (row.get("error") or ""):
                consecutive_blocks += 1
            else:
                consecutive_blocks = 0
            if (
                args.max_consecutive_blocks > 0
                and consecutive_blocks >= args.max_consecutive_blocks
                and index < len(selected)
            ):
                stopped_early = True
                print(
                    "连续收到 HLTV 拒绝，已提前熔断；请稍后重跑，"
                    "成功页面会直接使用缓存。"
                )
                break

    report = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "source": "HLTV normal browser player pages and search results",
        "requested_count": len(selected),
        "processed_count": len(results),
        "stopped_early": stopped_early,
        "policy": {
            "default_read_only": True,
            "min_recent_maps": 5,
            "awper_sniping_min": 70,
            "rifler_sniping_max": 30,
            "note": (
                "IGL 与武器角色分开保存证据；退役、无近期地图和混合区"
                "必须人工审核。"
            ),
        },
        "players": results,
    }
    write_json(args.output, report)
    auto = sum(
        1
        for row in results
        if row.get("suggestion", {}).get("confidence") in {"high", "medium"}
    )
    manual = len(results) - auto
    print(f"审核报告：{args.output}")
    print(f"可参考建议 {auto}，需人工复核 {manual}；未修改 overrides。")
    return 0


def apply_review(
    review_path: Path,
    overrides_path: Path,
    *,
    write: bool,
    replace_existing: bool,
) -> tuple[int, list[str]]:
    review = load_json(review_path)
    if not isinstance(review, dict) or not isinstance(review.get("players"), list):
        raise ValueError(f"无效的审核文件：{review_path}")
    overrides = load_json(overrides_path, {})
    changed = 0
    messages = []
    for row in review["players"]:
        decision = row.get("decision")
        if not decision:
            continue
        field = row.get("decision_field", "game_role")
        if field not in {"game_role", "played_role"}:
            raise ValueError(f"{row.get('local_page')}: 不支持字段 {field}")
        if decision not in ROLE_VALUES:
            raise ValueError(f"{row.get('local_page')}: 无效角色 {decision}")
        page = row.get("local_page")
        if not page:
            raise ValueError("审核项缺少 local_page")
        entry = dict(overrides.get(page, {}))
        if field in entry and entry[field] != decision and not replace_existing:
            messages.append(
                f"跳过 {page}：已有 {field}={entry[field]}，"
                "如确需替换请加 --replace-existing"
            )
            continue
        if entry.get(field) == decision:
            messages.append(f"跳过 {page}：{field} 已是 {decision}")
            continue
        entry[field] = decision
        suggestion = row.get("suggestion") or {}
        entry["reason"] = (
            f"HLTV role review confirmed {utc_now()[:10]}: "
            f"{suggestion.get('reason') or 'manual decision'}"
        )
        profile = row.get("profile") or {}
        if profile.get("profile_url"):
            entry["hltv_profile"] = profile["profile_url"]
        overrides[page] = entry
        changed += 1
        messages.append(f"{'将更新' if not write else '已更新'} {page}: {field}={decision}")
    if write and changed:
        write_json(overrides_path, overrides)
    return changed, messages


def apply_command(args: argparse.Namespace) -> int:
    changed, messages = apply_review(
        args.review,
        args.overrides_path,
        write=args.write,
        replace_existing=args.replace_existing,
    )
    for message in messages:
        print(message)
    if not args.write:
        print(f"预览完成：{changed} 项可更新；未写文件。确认后追加 --write。")
    else:
        print(f"完成：写入 {changed} 项到 {args.overrides_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="采集并生成只读审核报告")
    collect.add_argument("--players", nargs="+", help="本地 page、昵称或稳定别名")
    collect.add_argument("--all", action="store_true", help="显式采集整个数据库")
    collect.add_argument("--with-igl-news", action="store_true", help="额外搜索 IGL 新闻证据")
    collect.add_argument("--headless", action="store_true", help="无头模式；默认打开可见浏览器")
    collect.add_argument(
        "--browser-channel",
        default="chrome",
        help="Playwright 浏览器 channel；用 bundled 启动 Playwright 自带 Chromium",
    )
    collect.add_argument("--browser-executable", help="浏览器可执行文件绝对路径")
    collect.add_argument("--min-interval", type=float, default=8.0, help="页面访问最小间隔秒数")
    collect.add_argument("--timeout", type=int, default=30, help="单页面超时秒数")
    collect.add_argument("--cache-days", type=int, default=7, help="缓存有效天数")
    collect.add_argument(
        "--max-consecutive-blocks",
        type=int,
        default=2,
        help="连续多少次 403 后提前停止；0 表示禁用熔断",
    )
    collect.add_argument("--refresh", action="store_true", help="忽略缓存重新采集")
    collect.add_argument("--players-path", type=Path, default=PLAYERS_PATH)
    collect.add_argument("--overrides-path", type=Path, default=OVERRIDES_PATH)
    collect.add_argument("--map-path", type=Path, default=MAP_PATH)
    collect.add_argument("--cache-path", type=Path, default=CACHE_PATH)
    collect.add_argument("--output", type=Path, default=REVIEW_PATH)
    collect.set_defaults(func=collect_command)

    apply_parser = subparsers.add_parser("apply", help="预览或应用人工审核决定")
    apply_parser.add_argument("--review", type=Path, default=REVIEW_PATH)
    apply_parser.add_argument("--overrides-path", type=Path, default=OVERRIDES_PATH)
    apply_parser.add_argument("--write", action="store_true", help="确认实际写入")
    apply_parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="允许替换已有人工角色；默认保护",
    )
    apply_parser.set_defaults(func=apply_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "all", False) and getattr(args, "players", None):
        parser.error("--all 与 --players 不能同时使用")
    try:
        return args.func(args)
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
