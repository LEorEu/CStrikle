# -*- coding: utf-8 -*-
"""Player database loading, indexing and pool filtering."""
import json
import unicodedata
from datetime import date
from pathlib import Path


def _fold(s: str) -> str:
    """小写 + 去变音符号(Kovač -> kovac),让本名匹配不挑输入法。"""
    return "".join(c for c in unicodedata.normalize("NFKD", s or "")
                   if not unicodedata.combining(c)).lower()

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "players.json"
IMAGES_PATH = Path(__file__).resolve().parent.parent / "data" / "images.json"

ROLE_LABEL = {
    "igl": "IGL", "awp": "AWPer", "rifle": "Rifler", "rifler": "Rifler",
    "lurker": "Rifler", "entry": "Rifler", "support": "Rifler",
    "coach": "Coach", "analyst": "Analyst",
}

REGIONS = ["Europe", "CIS", "North America", "South America", "Asia",
           "Oceania", "Middle East & Africa", "Other"]

DIFFICULTIES = ("easy", "medium", "hard")


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
               "first_major_year", "last_major_year", "majors", "in_blast_pool")
    __slots__ = _FIELDS + ("photo", "team_logo", "flag")

    def __init__(self, rec: dict):
        for k in self._FIELDS:
            setattr(self, k, rec.get(k))
        self.roles = self.roles or []
        self.photo = self.team_logo = self.flag = None

    @property
    def primary_role(self) -> str:
        # IGL 优先(队内唯一性最强),其余按 infobox 顺序取第一个
        if "igl" in self.roles:
            return ROLE_LABEL["igl"]
        for r in self.roles:
            if r in ROLE_LABEL:
                return ROLE_LABEL[r]
        return "?"

    @property
    def role_set(self) -> set:
        return {ROLE_LABEL.get(r) for r in self.roles if r in ROLE_LABEL}

    def age(self, today: date | None = None) -> int | None:
        return _age(self.birth_date, today or date.today())

    @property
    def is_active(self) -> bool:
        return self.in_blast_pool or (self.status or "").lower() == "active"

    def brief(self) -> dict:
        """What the autocomplete list needs."""
        return {
            "page": self.page,
            "nickname": self.nickname,
            "real_name": self.real_name,
            "country": self.country,
            "team": self.team,
            "majors_count": self.majors_count or 0,
            "photo": self.photo,
            "flag": self.flag,
            "team_logo": self.team_logo,
        }

    def full(self, today: date | None = None) -> dict:
        return {
            "page": self.page,
            "nickname": self.nickname,
            "real_name": self.real_name,
            "country": self.country,
            "region": self.region,
            "age": self.age(today),
            "team": self.team or "",
            "role": self.primary_role,
            "majors_count": self.majors_count or 0,
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
        if IMAGES_PATH.exists():
            img = json.loads(IMAGES_PATH.read_text(encoding="utf-8"))
        else:
            img = {}
        self.photo_map = img.get("players", {})
        self.team_logo_map = img.get("teams", {})
        self.flag_map = img.get("flags", {})
        self.players = [Player(r) for r in raw["players"]]
        for p in self.players:
            p.photo = _img(self.photo_map.get(p.page))
            p.team_logo = _img(self.team_logo_map.get(p.team or ""))
            p.flag = _img(self.flag_map.get(p.country or ""))
        self.by_page = {p.page: p for p in self.players}
        self.by_nick: dict[str, list] = {}
        for p in self.players:
            self.by_nick.setdefault(p.nickname.lower(), []).append(p)

    @staticmethod
    def _fame(p) -> tuple:
        return (p.majors_count or 0, p.in_blast_pool)

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
            return [p for p in self.players
                    if (p.majors_count or 0) >= 4
                    or (p.in_blast_pool and (p.majors_count or 0) >= 2)]
        if difficulty == "medium":
            return [p for p in self.players
                    if (p.majors_count or 0) >= 2 or p.in_blast_pool]
        return list(self.players)

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
