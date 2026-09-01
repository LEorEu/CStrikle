# -*- coding: utf-8 -*-
"""Benchmark an OpenAI-compatible text provider with real game candidates.

The API key is read from a JSON config file and is never included in output.
This script does not use the project's active .env, so provider experiments
cannot accidentally consume the production AI route.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest


from server.game import compare
from playerdb.players import PlayerDB
from server.solver import PlayerSolver, feedback_signature


ACTION_RE = re.compile(r'\{[^\r\n]*"action"[^\r\n]*\}')


def _read_key(path: Path, field: str) -> str:
    raw = json.loads(path.read_text(encoding="utf-8"))
    key = raw
    for part in field.split("."):
        if not isinstance(key, dict) or part not in key:
            raise ValueError(f"missing key field: {field}")
        key = key[part]
    if not isinstance(key, str) or not key.strip():
        raise ValueError(f"empty key field: {field}")
    return key.strip()


def _scenario(db: PlayerDB, pool: list, index: int, candidate_limit: int = 30) -> dict:
    guess = pool[(index * 47 + 11) % len(pool)]
    buckets: dict[tuple, list] = defaultdict(list)
    for answer in pool:
        if answer.page != guess.page:
            buckets[feedback_signature(compare(guess, answer))].append(answer)
    ambiguous = [bucket for bucket in buckets.values() if len(bucket) >= 2]
    if not ambiguous:
        raise ValueError(f"no ambiguous feedback bucket for {guess.nickname}")
    # Prefer a compact but genuinely ambiguous state. It resembles the normal
    # mode's post-feedback decision while keeping provider input bounded.
    compact = [bucket for bucket in ambiguous if len(bucket) <= 30]
    candidates_for_answer = max(compact or ambiguous, key=len)
    answer = candidates_for_answer[0]
    row = {
        "player": guess.brief(),
        "cells": compare(guess, answer),
        "correct": False,
    }
    candidates = list(PlayerSolver(db, pool).filter_candidates([row]))
    if not candidates:
        raise ValueError(
            f"scenario produced no candidates: {answer.nickname}/{guess.nickname}"
        )
    shown = candidates[:candidate_limit]
    return {
        "index": index,
        "answer": answer.nickname,
        "previous_guess": guess.nickname,
        "candidate_count": len(candidates),
        "candidates": shown,
    }


def _prompt(scenario: dict) -> list[dict]:
    lines = []
    for player in scenario["candidates"]:
        age = player.age()
        lines.append(
            f"- {player.nickname}: {player.country} / {player.team_label} / "
            f"{player.primary_role} / {age if age is not None else '?'} 岁 / "
            f"Major {player.majors_count or 0} 次 / 冠军 {player.majors_won}"
        )
    candidates = "\n".join(lines)
    system = (
        "你正在玩猜 CS 职业选手游戏。请从用户给出的候选名单中挑一个你喜欢的。"
        "不要搜索，不要解释过程，只输出一行 JSON："
        '{"action":"guess","nickname":"选手ID","reason":"一句简短中文理由"}。'
    )
    user = (
        f"上一轮猜了 {scenario['previous_guess']}。"
        f"根据真实反馈，当前共有 {scenario['candidate_count']} 名可能人选，"
        f"下面列出本轮允许提交的 {len(scenario['candidates'])} 人：\n"
        f"{candidates}\n请立即选择。"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_action(content: str) -> dict | None:
    content = (content or "").strip()
    candidates = [content]
    match = ACTION_RE.search(content)
    if match and match.group(0) != content:
        candidates.append(match.group(0))
    for raw in candidates:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("action") == "guess":
            return value
    return None


def _request(
    base_url: str,
    model: str,
    scenario: dict,
    key: str,
    timeout: float,
) -> dict:
    started = time.perf_counter()
    try:
        payload = json.dumps({
            "model": model,
            "messages": _prompt(scenario),
            "stream": False,
        }, ensure_ascii=False).encode("utf-8")
        request = urlrequest.Request(
            f"{base_url.rstrip('/')}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlrequest.urlopen(request, timeout=timeout) as response:
            status = response.status
            body = json.loads(response.read().decode("utf-8"))
        elapsed = time.perf_counter() - started
        content = body["choices"][0]["message"].get("content") or ""
        action = _parse_action(content)
        nickname = str((action or {}).get("nickname", "")).strip()
        selected = next(
            (
                player
                for player in scenario["candidates"]
                if player.nickname.casefold() == nickname.casefold()
                or player.page.casefold() == nickname.casefold()
            ),
            None,
        )
        return {
            "scenario": scenario["index"],
            "candidate_count": scenario["candidate_count"],
            "shown_count": len(scenario["candidates"]),
            "elapsed_seconds": round(elapsed, 3),
            "http_status": status,
            "json_action": action is not None,
            "valid_choice": selected is not None,
            "nickname": selected.nickname if selected else nickname[:80],
            "error": None if selected else "invalid_or_outside_candidates",
        }
    except Exception as exc:
        return {
            "scenario": scenario["index"],
            "candidate_count": scenario["candidate_count"],
            "shown_count": len(scenario["candidates"]),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "http_status": exc.code if isinstance(exc, urlerror.HTTPError) else None,
            "json_action": False,
            "valid_choice": False,
            "nickname": "",
            "error": f"{type(exc).__name__}: {str(exc)[:240]}",
        }


def _list_models(base_url: str, key: str, timeout: float) -> None:
    request = urlrequest.Request(
        f"{base_url.rstrip('/')}/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    with urlrequest.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    models = sorted(
        str(item.get("id", ""))
        for item in body.get("data", [])
        if isinstance(item, dict) and item.get("id")
    )
    print(json.dumps({"models": models}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model")
    parser.add_argument("--list-models", action="store_true")
    parser.add_argument("--key-config", type=Path, required=True)
    parser.add_argument("--key-field", default="auth-key")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--candidate-limit", type=int, default=30)
    args = parser.parse_args()

    key = _read_key(args.key_config, args.key_field)
    if args.list_models:
        _list_models(args.base_url, key, args.timeout)
        return
    if not args.model:
        parser.error("--model is required unless --list-models is used")
    db = PlayerDB()
    pool = db.difficulty_pool("medium")
    results = []
    for index in range(args.start, args.start + args.samples):
        result = _request(
            args.base_url,
            args.model,
            _scenario(db, pool, index, max(2, min(30, args.candidate_limit))),
            key,
            args.timeout,
        )
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)

    elapsed = [item["elapsed_seconds"] for item in results]
    ordered = sorted(elapsed)
    p95_index = max(0, min(len(ordered) - 1, round(len(ordered) * 0.95) - 1))
    summary = {
        "model": args.model,
        "samples": len(results),
        "valid": sum(item["valid_choice"] for item in results),
        "json_actions": sum(item["json_action"] for item in results),
        "errors": sum(bool(item["error"]) for item in results),
        "p50_seconds": round(statistics.median(elapsed), 3),
        "p95_seconds": round(ordered[p95_index], 3),
        "max_seconds": round(max(elapsed), 3),
    }
    print(json.dumps({"summary": summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
