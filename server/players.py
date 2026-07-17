# -*- coding: utf-8 -*-
"""Player database loading, indexing and pool filtering."""
import json
import unicodedata
from datetime import date
from pathlib import Path

from .rankings import TeamRanking


def _fold(s: str) -> str:
    """小写 + 去变音符号(Kovač -> kovac),让本名匹配不挑输入法。"""
    return "".join(c for c in unicodedata.normalize("NFKD", s or "")
                   if not unicodedata.combining(c)).lower()

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "players.json"
IMAGES_PATH = Path(__file__).resolve().parent.parent / "data" / "images.json"
OVERRIDES_PATH = Path(__file__).resolve().parent.parent / "data" / "player_overrides.json"

ROLE_LABEL = {
    "igl": "IGL",
    "awp": "AWPer", "awper": "AWPer",
    "rifle": "Rifler", "rifler": "Rifler", "lurker": "Rifler",
    "lurk": "Rifler", "entry": "Rifler", "entryfragger": "Rifler",
    "support": "Rifler",
    "coach": "Coach", "assistant coach": "Coach",
    "analyst": "Analyst", "broadcast analyst": "Analyst",
}
ANSWER_ROLES = {"IGL", "AWPer", "Rifler", "Coach"}
COACH_ROLES = {"coach", "assistant coach"}
# 非选手职务:干这些的(且没有现役战队)视为已退出选手身份
STAFF_ROLES = COACH_ROLES | {"manager", "analyst", "broadcast analyst",
                             "caster", "interviewer", "host", "observer"}

REGIONS = ["Europe", "CIS", "North America", "South America", "Asia",
           "Oceania", "Middle East & Africa", "Other"]

DIFFICULTIES = ("easy", "medium", "hard")

# 保留上游原始国籍值用于数据追踪，对外按中国大陆版本显示。
CHINA_COUNTRY_LABELS = {
    "China": "中国",
    "Hong Kong": "中国香港",
    "Macau": "中国澳门",
    "Macao": "中国澳门",
    "Taiwan": "中国台湾",
    "Chinese Taipei": "中国台湾",
}


def _img(rel: str | None) -> str | None:
    return f"/img/{rel}" if rel else None


def _age(birth_date: str, today: date) -> int | None:
    if not birth_date:
        return None
    try:
        y, m, d = (int(x) for x in birth_date.split("-")[:3])
        return today.year - y - ((today.month, today.day) < (m, d))
    except (ValueError, TypeError):
        return None


class Player:
    _FIELDS = ("page", "nickname", "real_name", "country", "region",
               "birth_date", "team", "status", "roles", "majors_count",
               "first_major_year", "last_major_year", "majors", "in_blast_pool",
               "game_role")
    __slots__ = _FIELDS + ("photo", "team_logo", "flag", "majors_won")

    def __init__(self, rec: dict):
        for k in self._FIELDS:
            setattr(self, k, rec.get(k))
        self.roles = self.roles or []
        self.photo = self.team_logo = self.flag = None
        self.majors_won = sum(1 for m in (self.majors or [])
                              if m.get("placement") == "1")

    @property
    def primary_role(self) -> str:
        if self.game_role in ANSWER_ROLES:
            return self.game_role
        # 当前明确是教练时保留 Coach；其余按 IGL、AWP、步枪优先级归一化。
        if any(r in COACH_ROLES for r in self.roles):
            return "Coach"
        if "igl" in self.roles:
            return "IGL"
        if any(ROLE_LABEL.get(r) == "AWPer" for r in self.roles):
            return "AWPer"
        if any(ROLE_LABEL.get(r) == "Rifler" for r in self.roles):
            return "Rifler"
        if any(ROLE_LABEL.get(r) == "Analyst" for r in self.roles):
            return "Analyst"
        return "?"

    @property
    def role_set(self) -> set:
        roles = {ROLE_LABEL[r] for r in self.roles if r in ROLE_LABEL}
        if self.game_role:
            roles.add(self.game_role)
        return roles

    @property
    def is_coach(self) -> bool:
        return any(r in COACH_ROLES for r in self.roles)

    @property
    def played_role(self) -> str:
        """选手时期的打法位置(忽略教练/经理等职务角色)。"""
        if "igl" in self.roles:
            return "IGL"
        if any(ROLE_LABEL.get(r) == "AWPer" for r in self.roles):
            return "AWPer"
        if any(ROLE_LABEL.get(r) == "Rifler" for r in self.roles):
            return "Rifler"
        return ""

    @property
    def is_searchable(self) -> bool:
        """Reject all-empty unresolved nickname stubs, but keep real profiles."""
        return bool(
            self.nickname
            and (
                self.real_name
                or self.country
                or self.birth_date
                or self.roles
                or self.majors_count
            )
        )

    @property
    def is_game_ready(self) -> bool:
        """Minimum attribute completeness required for becoming a puzzle answer."""
        return bool(
            self.nickname
            and self.country
            and self.birth_date
            and self.primary_role in ANSWER_ROLES
        )

    def age(self, today: date | None = None) -> int | None:
        return _age(self.birth_date, today or date.today())

    @property
    def is_active(self) -> bool:
        return self.in_blast_pool or (self.status or "").lower() == "active"

    @property
    def is_retired_like(self) -> bool:
        """已退出选手身份:官方标退役/不活跃,或当前干的是教练/经理/解说等职务。
        像 degster 那种还能打但没队要的现役选手才算"未签约"。"""
        if (self.status or "").lower() in ("retired", "inactive"):
            return True
        return any(r in STAFF_ROLES for r in self.roles)

    @property
    def team_label(self) -> str:
        """无战队时区分"退役"和"未签约/已下放"。"""
        return self.team or ("退役" if self.is_retired_like else "未签约")

    @property
    def display_country(self) -> str:
        return CHINA_COUNTRY_LABELS.get(self.country, self.country or "")

    @property
    def nationality_key(self) -> str:
        """用于游戏判定的国籍；港澳台与中国大陆统一判定为中国。"""
        if self.country in CHINA_COUNTRY_LABELS:
            return "China"
        return self.country or ""

    @property
    def flag_country(self) -> str:
        """国籍栏使用国旗；中国大陆、香港、澳门、台湾统一使用中国国旗。"""
        if self.country in CHINA_COUNTRY_LABELS:
            return "China"
        return self.country or ""

    def brief(self) -> dict:
        """What the autocomplete list needs."""
        return {
            "page": self.page,
            "nickname": self.nickname,
            "real_name": self.real_name,
            "country": self.display_country,
            "team": self.team,
            "majors_count": self.majors_count or 0,
            "majors_won": self.majors_won,
            "photo": self.photo,
            "flag": self.flag,
            "team_logo": self.team_logo,
        }

    def full(self, today: date | None = None) -> dict:
        return {
            "page": self.page,
            "nickname": self.nickname,
            "real_name": self.real_name,
            "country": self.display_country,
            "region": self.region,
            "age": self.age(today),
            "team": self.team or "",
            "team_label": self.team_label,
            "role": self.primary_role,
            "majors_count": self.majors_count or 0,
            "majors_won": self.majors_won,
            "status": self.status,
            "active": self.is_active,
            "photo": self.photo,
            "flag": self.flag,
            "team_logo": self.team_logo,
        }


class PlayerDB:
    def __init__(self, path: Path = DATA_PATH):
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.generated_at = raw.get("generated_at", "")
        self.ranking = TeamRanking()
        if OVERRIDES_PATH.exists():
            override_raw = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
            overrides = {k.casefold(): v for k, v in override_raw.items()}
        else:
            overrides = {}
        if IMAGES_PATH.exists():
            img = json.loads(IMAGES_PATH.read_text(encoding="utf-8"))
        else:
            img = {}
        self.photo_map = img.get("players", {})
        self.team_logo_map = img.get("teams", {})
        self.flag_map = img.get("flags", {})
        self.excluded_stubs = 0
        self.players = []
        for rec in raw["players"]:
            merged = dict(rec)
            override = overrides.get(str(rec.get("page", "")).casefold(), {})
            for key in ("team", "status", "game_role"):
                if key in override:
                    merged[key] = override[key]
            p = Player(merged)
            if p.is_coach and p.team and not self.ranking.contains(p.team):
                p.team = ""
            if (p.game_role not in ANSWER_ROLES
                    and p.primary_role not in ("IGL", "AWPer", "Rifler")
                    and not (p.is_coach and p.team)):
                # 除了带上榜战队的现任教练,其余职务人员(教练/分析师/经理/解说)
                # 和空角色老选手都回退到选手时期的打法位置
                fallback = override.get("played_role") or p.played_role
                if fallback:
                    p.game_role = fallback
            if not p.is_searchable:
                self.excluded_stubs += 1
                continue
            self.players.append(p)
        self.answer_players = [p for p in self.players if p.is_game_ready]
        for p in self.players:
            p.photo = _img(self.photo_map.get(p.page))
            p.team_logo = _img(self.team_logo_map.get(p.team or ""))
            p.flag = _img(self.flag_map.get(p.flag_country))
        self.by_page = {p.page: p for p in self.players}
        self.by_nick: dict[str, list] = {}
        for p in self.players:
            self.by_nick.setdefault(p.nickname.lower(), []).append(p)

    @staticmethod
    def _fame(p) -> tuple:
        return (p.is_game_ready, p.majors_count or 0, p.in_blast_pool)

    def lookup(self, name: str) -> Player | None:
        """Resolve a guess string (page id or nickname) to a player.

        同名时优先知名度高的(Major 场次多 / 现役)。
        """
        if not name:
            return None
        name = name.strip()
        if name in self.by_page:
            return self.by_page[name]
        key = name.lower()
        hits = self.by_nick.get(key)
        if hits:
            return max(hits, key=self._fame)
        page_hits = [p for p in self.players if p.page.lower() == key]
        if page_hits:
            return page_hits[0]
        # 用真实姓名猜:输入的每个词都要出现在选手本名里(至少两个词,防误匹配)
        qt = _fold(name).split()
        if len(qt) >= 2:
            real_hits = [p for p in self.players
                         if set(qt) <= set(_fold(p.real_name).split())]
            if real_hits:
                return max(real_hits, key=self._fame)
        pref = [p for p in self.players if p.nickname.lower().startswith(key)]
        if pref:
            if len({p.page for p in pref}) == 1:
                return pref[0]
            return None
        return None

    # ------------------------------------------------------------- pools
    def difficulty_pool(self, difficulty: str) -> list:
        if difficulty == "easy":
            return [p for p in self.answer_players
                    if (p.majors_count or 0) >= 4
                    or (p.in_blast_pool and (p.majors_count or 0) >= 2)]
        if difficulty == "medium":
            return [p for p in self.answer_players
                    if (p.majors_count or 0) >= 2 or p.in_blast_pool]
        return list(self.answer_players)

    def filter_pool(self, settings: dict) -> list:
        pool = self.difficulty_pool(settings.get("difficulty", "medium"))
        regions = settings.get("regions") or []
        if regions:
            pool = [p for p in pool if p.region in regions]
        if settings.get("active_only"):
            pool = [p for p in pool if p.is_active]
        y0 = settings.get("year_from")
        y1 = settings.get("year_to")
        if y0 or y1:
            def in_era(p):
                a = p.first_major_year or 2026   # blast-only rookies: current era
                b = p.last_major_year or 2026
                return (not y1 or a <= y1) and (not y0 or b >= y0)
            pool = [p for p in pool if in_era(p)]
        # a puzzle needs at least a couple of candidates
        return pool
