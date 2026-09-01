# -*- coding: utf-8 -*-
"""Core guessing logic: compare a guess to the answer, manage game state."""
import hashlib
import random
import secrets
from datetime import date

from playerdb.players import Player, PlayerDB
from playerdb.rankings import normalize_team_name

GREEN, YELLOW, GRAY = "green", "yellow", "gray"

DEFAULT_SETTINGS = {
    "difficulty": "medium",      # easy | medium | hard | custom | top20
    "regions": [],               # empty = all
    "active_only": False,
    "year_from": None,           # Major-era window, e.g. 2013..2026
    "year_to": None,
    "max_guesses": 8,
    "game_seconds": None,        # 对战模式整局限时,None=不限
}


def normalize_settings(raw: dict | None) -> dict:
    s = dict(DEFAULT_SETTINGS)
    if raw:
        for k in s:
            if k in raw and raw[k] is not None:
                s[k] = raw[k]
    if s["difficulty"] not in ("easy", "medium", "hard", "custom", "top20"):
        s["difficulty"] = "medium"
    s["max_guesses"] = max(4, min(15, int(s["max_guesses"] or 8)))
    if s["regions"] and not isinstance(s["regions"], list):
        s["regions"] = [s["regions"]]
    for k in ("year_from", "year_to"):
        if s[k]:
            s[k] = max(2013, min(2030, int(s[k])))
        else:
            s[k] = None
    if s["game_seconds"]:
        s["game_seconds"] = max(60, min(3600, int(s["game_seconds"])))
    else:
        s["game_seconds"] = None
    return s


def compare(guess: Player, answer: Player, today: date | None = None) -> list:
    """One guess row: list of cells with value + state (+ direction hint)."""
    today = today or date.today()
    cells = []

    # nationality: 中国大陆、香港、澳门、台湾统一为中国；其他同国绿色、同区黄色
    if guess.nationality_key and guess.nationality_key == answer.nationality_key:
        st = GREEN
    elif guess.region != "Other" and guess.region == answer.region:
        st = YELLOW
    else:
        st = GRAY
    cells.append({"key": "nationality", "value": guess.display_country or "?",
                  "extra": guess.region, "state": st})

    # team: 归一化别名后比较;无战队的人统一算"自由身"互相判绿
    def team_cat(p):
        return normalize_team_name(p.team or "")
    st = GREEN if team_cat(guess) == team_cat(answer) else GRAY
    cells.append({"key": "team", "value": guess.team_label, "state": st})

    # age: green exact, yellow within 2, arrow = answer older/younger
    ga, aa = guess.age(today), answer.age(today)
    if ga is None or aa is None:
        cells.append({"key": "age", "value": ga if ga is not None else "?",
                      "state": GRAY, "dir": None})
    else:
        st = GREEN if ga == aa else (YELLOW if abs(ga - aa) <= 2 else GRAY)
        d = None if ga == aa else ("up" if aa > ga else "down")
        cells.append({"key": "age", "value": ga, "state": st, "dir": d})

    # role: green same primary, yellow if role sets overlap
    gr, ar = guess.primary_role, answer.primary_role
    if gr != "?" and gr == ar:
        st = GREEN
    elif guess.role_set & answer.role_set:
        st = YELLOW
    else:
        st = GRAY
    cells.append({"key": "role", "value": gr, "state": st})

    # majors: green exact, yellow within 1, arrow
    gm, am = guess.majors_count or 0, answer.majors_count or 0
    st = GREEN if gm == am else (YELLOW if abs(gm - am) <= 1 else GRAY)
    d = None if gm == am else ("up" if am > gm else "down")
    cells.append({"key": "majors", "value": gm, "state": st, "dir": d})

    # majors won: green exact, yellow within 1, arrow
    gw, aw = guess.majors_won, answer.majors_won
    st = GREEN if gw == aw else (YELLOW if abs(gw - aw) <= 1 else GRAY)
    d = None if gw == aw else ("up" if aw > gw else "down")
    cells.append({"key": "majors_won", "value": gw, "state": st, "dir": d})

    return cells


def feedback_text(cells: list) -> str:
    """Human/LLM readable summary of one guess row."""
    label = {"nationality": "国籍", "team": "战队", "age": "年龄",
             "role": "位置", "majors": "Major次数", "majors_won": "Major冠军数"}
    state = {"green": "✔正确", "yellow": "≈接近", "gray": "✘不对"}
    parts = []
    for c in cells:
        t = f"{label[c['key']]}={c['value']}:{state[c['state']]}"
        if c.get("dir") == "up":
            t += "(答案更大)"
        elif c.get("dir") == "down":
            t += "(答案更小)"
        parts.append(t)
    return " | ".join(parts)


class Game:
    """A single-player puzzle (daily or unlimited)."""

    def __init__(self, db: PlayerDB, settings: dict, answer: Player,
                 mode: str = "unlimited", daily_key: str | None = None):
        self.id = secrets.token_urlsafe(8)
        self.db = db
        self.settings = settings
        self.answer = answer
        self.mode = mode
        self.daily_key = daily_key
        self.guesses = []            # [{player: brief, cells: [...]}]
        self.status = "playing"      # playing | won | lost

    @classmethod
    def create(cls, db: PlayerDB, raw_settings: dict | None, mode="unlimited"):
        settings = normalize_settings(raw_settings)
        pool = db.filter_pool(settings)
        if len(pool) < 2:
            raise ValueError("筛选条件下候选选手不足(<2),请放宽范围")
        if mode == "daily":
            key = date.today().isoformat()
            settings = normalize_settings(None)   # daily is always default rules
            pool = db.filter_pool(settings)
            h = int(hashlib.sha256(f"cstrikle:{key}".encode()).hexdigest(), 16)
            answer = pool[h % len(pool)]
            return cls(db, settings, answer, mode="daily", daily_key=key)
        return cls(db, settings, random.choice(pool), mode=mode)

    @property
    def over(self) -> bool:
        return self.status != "playing"

    def guess(self, name: str) -> dict:
        if self.over:
            raise ValueError("对局已结束")
        p = self.db.lookup(name)
        if p is None:
            raise LookupError(f"选手库里没有「{name}」")
        if any(g["player"]["page"] == p.page for g in self.guesses):
            raise ValueError(f"已经猜过 {p.nickname} 了")
        cells = compare(p, self.answer)
        row = {"player": p.brief(), "cells": cells,
               "correct": p.page == self.answer.page}
        self.guesses.append(row)
        if row["correct"]:
            self.status = "won"
        elif len(self.guesses) >= self.settings["max_guesses"]:
            self.status = "lost"
        return row

    def serialize(self) -> dict:
        d = {
            "id": self.id,
            "mode": self.mode,
            "settings": self.settings,
            "status": self.status,
            "guesses": self.guesses,
            "remaining": self.settings["max_guesses"] - len(self.guesses),
            "pool_size": len(self.db.filter_pool(self.settings)),
        }
        if self.over:
            d["answer"] = self.answer.full()
        return d
