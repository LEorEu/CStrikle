# -*- coding: utf-8 -*-
"""Versioned Major result corrections applied on top of upstream player rows."""
import json
from pathlib import Path

from .rankings import normalize_team_name


DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "major_results.json"


def load_major_results(path: Path = DATA_PATH) -> dict:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw.get("events", {})


def apply_major_results(majors: list | None, events: dict) -> list:
    """Return copied Major rows with verified event/team placements overlaid."""
    corrected = []
    for original in majors or []:
        row = dict(original)
        event = events.get(row.get("page", ""))
        if event:
            placements = event.get("placements", {})
            team_key = normalize_team_name(row.get("team", ""))
            for team, placement in placements.items():
                if normalize_team_name(team) == team_key:
                    row["placement"] = str(placement)
                    break
        corrected.append(row)
    return corrected
