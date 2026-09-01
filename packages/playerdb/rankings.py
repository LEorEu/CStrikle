# -*- coding: utf-8 -*-
"""Offline HLTV ranking snapshot used for stable team classification."""
import json
import re
import unicodedata
from pathlib import Path


from .paths import DATA

DATA_PATH = DATA / "hltv_top100.json"
_IGNORED_TEAM_WORDS = {"team", "gaming", "esport", "esports", "clan"}


def normalize_team_name(value: str) -> str:
    text = "".join(
        c for c in unicodedata.normalize("NFKD", value or "")
        if not unicodedata.combining(c)
    ).casefold()
    words = re.findall(r"[a-z0-9]+", text)
    return "".join(word for word in words if word not in _IGNORED_TEAM_WORDS)


class TeamRanking:
    def __init__(self, path: Path = DATA_PATH):
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.generated_at = raw["generated_at"]
        self.source_url = raw["source_url"]
        self.limit = int(raw.get("limit", 100))
        self.teams = list(raw["teams"])[:self.limit]
        self.aliases = dict(raw.get("aliases", {}))

        canonical = {normalize_team_name(name): name for name in self.teams}
        for alias, target in self.aliases.items():
            target_key = normalize_team_name(target)
            if target_key in canonical:
                canonical[normalize_team_name(alias)] = canonical[target_key]
        self._canonical = canonical

    def canonical_name(self, team: str) -> str | None:
        return self._canonical.get(normalize_team_name(team))

    def contains(self, team: str) -> bool:
        return self.canonical_name(team) is not None
