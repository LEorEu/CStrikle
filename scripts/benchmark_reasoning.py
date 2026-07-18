# -*- coding: utf-8 -*-
"""Run one reproducible Grok reasoning-effort benchmark scenario."""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.ai_player import AIPlayer
from server.game import compare
from server.players import PlayerDB


SCENARIOS = [
    {"name": "opening", "answer": "s1mple", "guesses": []},
    {"name": "one_feedback", "answer": "s1mple", "guesses": ["ZywOo"]},
    {"name": "coach_feedback", "answer": "friberg", "guesses": ["NEO"]},
    {
        "name": "two_feedback",
        "answer": "AdreN",
        "guesses": ["refrezh", "ZywOo"],
    },
]


def build_rows(db: PlayerDB, answer_name: str, guess_names: list[str]) -> list[dict]:
    answer = db.lookup(answer_name)
    if answer is None:
        raise ValueError(f"unknown answer: {answer_name}")
    rows = []
    for name in guess_names:
        guess = db.lookup(name)
        if guess is None:
            raise ValueError(f"unknown guess: {name}")
        if guess.page == answer.page:
            raise ValueError(f"scenario guess unexpectedly solves answer: {name}")
        rows.append({
            "player": guess.brief(),
            "cells": compare(guess, answer),
            "correct": False,
        })
    return rows


async def run(effort: str, thinking: str, ai_level: str, scenario_index: int):
    scenario = SCENARIOS[scenario_index]
    db = PlayerDB()
    pool = db.difficulty_pool("medium")
    rows = build_rows(db, scenario["answer"], scenario["guesses"])
    guessed = {row["player"]["page"] for row in rows}
    guessed |= {row["player"]["nickname"].casefold() for row in rows}
    ai = AIPlayer(
        db,
        pool,
        "benchmark medium pool",
        max_guesses=8,
        reasoning_effort=effort,
        thinking_mode=thinking,
        ai_level=ai_level,
    )
    analysis = ai.solver.analyze(
        rows,
        max(1, 8 - len(rows)),
        {row["player"]["page"] for row in rows},
    )
    started = time.perf_counter()
    try:
        result = await ai.take_turn(
            rows,
            "benchmark opponent",
            guessed,
        )
        error = None
    except Exception as exc:
        result = None
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started
    events = result.events if result else []
    model_error = next(
        (event for event in events if event["type"] == "model_error"),
        None,
    )
    solver_event = next(
        (event for event in events if event["type"] == "solver"),
        None,
    )
    usage_events = [event for event in events if event["type"] == "usage"]
    print(json.dumps({
        "effort": effort,
        "thinking": thinking or "default",
        "ai_level": ai_level,
        "scenario": scenario["name"],
        "answer": scenario["answer"],
        "history_depth": len(rows),
        "candidate_count": (
            solver_event["candidate_count"]
            if solver_event else len(analysis.candidates)
        ),
        "recommended": (
            solver_event["recommended"]
            if solver_event else analysis.recommended.nickname
        ),
        "submitted_page": result.guess_name if result else None,
        "followed_solver": (
            result.guess_name == result.fallback_guess if result else False
        ),
        "elapsed_seconds": round(elapsed, 3),
        "error": (
            error
            or (
                f"{model_error['error']}: {model_error['message']}"
                if model_error else None
            )
        ),
        "searches": sum(e["type"] == "search" for e in events),
        "model_reasoning_chars": sum(
            len(e.get("text", ""))
            for e in events
            if e["type"] in ("reasoning", "thinking")
        ),
        "usage": {
            key: sum(event.get(key, 0) for event in usage_events)
            for key in (
                "prompt_tokens",
                "cached_tokens",
                "cache_miss_tokens",
                "completion_tokens",
                "total_tokens",
            )
        },
        "event_types": [e["type"] for e in events],
    }, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--effort",
        choices=("low", "medium", "high", "max"),
        required=True,
    )
    parser.add_argument(
        "--thinking",
        choices=("enabled", "disabled"),
        default="disabled",
    )
    parser.add_argument(
        "--ai-level",
        choices=("easy", "normal", "hard"),
        default="hard",
        help="hard is deterministic and is the recommended A/B benchmark level",
    )
    parser.add_argument(
        "--scenario",
        type=int,
        choices=range(len(SCENARIOS)),
        required=True,
    )
    args = parser.parse_args()
    asyncio.run(run(args.effort, args.thinking, args.ai_level, args.scenario))


if __name__ == "__main__":
    main()
