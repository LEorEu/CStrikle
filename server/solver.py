# -*- coding: utf-8 -*-
"""Deterministic Counter-Strikle candidate filtering and move selection."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from math import log2

from .game import compare
from .players import Player, PlayerDB


FeedbackSignature = tuple[tuple[str, str, str | None], ...]


def feedback_signature(cells: list[dict]) -> FeedbackSignature:
    """Keep only answer-dependent feedback, never the guessed display value."""
    return tuple(
        (cell["key"], cell["state"], cell.get("dir"))
        for cell in cells
    )


@dataclass(frozen=True)
class MoveScore:
    player: Player
    expected_remaining: float
    worst_case: int
    entropy: float
    in_candidates: bool

    def prompt_line(self, rank: int) -> str:
        marker = "候选内" if self.in_candidates else "信息探针"
        return (
            f"{rank}. {self.player.nickname} ({marker}) — "
            f"期望剩余 {self.expected_remaining:.2f}, "
            f"最坏 {self.worst_case}, 信息熵 {self.entropy:.3f}"
        )


@dataclass(frozen=True)
class SolverAnalysis:
    candidates: tuple[Player, ...]
    moves: tuple[MoveScore, ...]
    recommended: Player
    mode: str
    exact_solve_probability: float | None = None

    def prompt_block(self) -> str:
        lines = [
            "## 本地确定性求解器",
            f"- 当前严格候选数: {len(self.candidates)}",
            f"- 决策模式: {self.mode}",
            f"- 本轮指定猜测: {self.recommended.nickname}",
        ]
        if self.exact_solve_probability is not None:
            lines.append(
                f"- 剩余回合内精确求解概率: "
                f"{self.exact_solve_probability * 100:.1f}%"
            )
        if len(self.candidates) <= 20:
            lines.append(
                "- 当前候选: "
                + ", ".join(player.nickname for player in self.candidates)
            )
        lines.append("- 信息增益排名:")
        lines.extend(move.prompt_line(i) for i, move in enumerate(self.moves, 1))
        lines.append(
            "本地数据库和求解器是判定真值。你必须提交“本轮指定猜测”，"
            "不要自行换人。"
        )
        return "\n".join(lines)


class PlayerSolver:
    def __init__(
        self,
        db: PlayerDB,
        answer_pool: list[Player],
        exact_threshold: int = 10,
        probe_limit: int = 8,
    ):
        self.db = db
        self.initial_candidates = tuple(answer_pool)
        self.guess_pool = tuple(db.answer_players)
        self.exact_threshold = max(2, exact_threshold)
        self.probe_limit = max(0, probe_limit)
        self._by_page = {player.page: player for player in self.guess_pool}

    @staticmethod
    def _partition(
        guess: Player,
        candidates: tuple[Player, ...] | list[Player],
    ) -> tuple[dict[FeedbackSignature, list[Player]], bool]:
        buckets: dict[FeedbackSignature, list[Player]] = defaultdict(list)
        hit = False
        for answer in candidates:
            if guess.page == answer.page:
                hit = True
                continue
            buckets[feedback_signature(compare(guess, answer))].append(answer)
        return buckets, hit

    def filter_candidates(self, rows: list[dict]) -> tuple[Player, ...]:
        candidates = list(self.initial_candidates)
        for row in rows:
            page = row.get("player", {}).get("page", "")
            guess = self.db.by_page.get(page) or self.db.lookup(page)
            if guess is None:
                continue
            observed = feedback_signature(row.get("cells", []))
            candidates = [
                answer for answer in candidates
                if answer.page != guess.page
                and feedback_signature(compare(guess, answer)) == observed
            ]
        return tuple(candidates)

    def rank_moves(
        self,
        candidates: tuple[Player, ...] | list[Player],
        guessed_pages: set[str] | frozenset[str] = frozenset(),
        limit: int = 5,
        action_pool: tuple[Player, ...] | list[Player] | None = None,
    ) -> tuple[MoveScore, ...]:
        candidates = tuple(candidates)
        if not candidates:
            return ()
        n = len(candidates)
        candidate_pages = {player.page for player in candidates}
        actions = action_pool if action_pool is not None else self.guess_pool
        scored = []
        for guess in actions:
            if guess.page in guessed_pages:
                continue
            buckets, hit = self._partition(guess, candidates)
            sizes = [len(bucket) for bucket in buckets.values()]
            expected = sum(size * size for size in sizes) / n
            worst = max(sizes, default=0)
            outcome_sizes = sizes + ([1] if hit else [])
            entropy = -sum(
                (size / n) * log2(size / n)
                for size in outcome_sizes
                if size
            )
            scored.append(
                MoveScore(
                    player=guess,
                    expected_remaining=expected,
                    worst_case=worst,
                    entropy=entropy,
                    in_candidates=guess.page in candidate_pages,
                )
            )
        scored.sort(
            key=lambda move: (
                move.expected_remaining,
                move.worst_case,
                -move.entropy,
                not move.in_candidates,
                -(move.player.majors_count or 0),
                move.player.nickname.casefold(),
            )
        )
        return tuple(scored[:max(1, limit)])

    def _exact_choice(
        self,
        candidates: tuple[Player, ...],
        remaining_turns: int,
        guessed_pages: set[str],
    ) -> tuple[Player, float]:
        """Maximise exact solve probability over the remaining finite horizon."""
        initial_pages = tuple(sorted(player.page for player in candidates))
        initial_blocked = frozenset(guessed_pages)

        @lru_cache(maxsize=None)
        def solve(
            state_pages: tuple[str, ...],
            turns: int,
            blocked: frozenset[str],
        ) -> tuple[float, str]:
            state = tuple(self._by_page[page] for page in state_pages)
            if not state or turns <= 0:
                return 0.0, ""
            if len(state) == 1:
                return 1.0, state[0].page

            probes = self.rank_moves(
                state,
                guessed_pages=set(blocked),
                limit=self.probe_limit,
            )
            action_map = {
                player.page: player
                for player in state
                if player.page not in blocked
            }
            for move in probes:
                if move.player.page not in blocked:
                    action_map.setdefault(move.player.page, move.player)

            best_probability = -1.0
            best_page = ""
            best_tiebreak = None
            n = len(state)
            for guess in action_map.values():
                buckets, hit = self._partition(guess, state)
                if not hit and len(buckets) == 1:
                    only_bucket = next(iter(buckets.values()))
                    if len(only_bucket) == n:
                        continue

                solved_weight = 1.0 if hit else 0.0
                if turns > 1:
                    next_blocked = blocked | {guess.page}
                    for bucket in buckets.values():
                        child_pages = tuple(sorted(p.page for p in bucket))
                        child_probability, _ = solve(
                            child_pages, turns - 1, next_blocked
                        )
                        solved_weight += len(bucket) * child_probability
                probability = solved_weight / n

                one_step = self.rank_moves(
                    state,
                    guessed_pages=set(blocked),
                    limit=1,
                    action_pool=(guess,),
                )[0]
                tiebreak = (
                    one_step.expected_remaining,
                    one_step.worst_case,
                    -one_step.entropy,
                    not one_step.in_candidates,
                    guess.nickname.casefold(),
                )
                if (
                    probability > best_probability + 1e-12
                    or (
                        abs(probability - best_probability) <= 1e-12
                        and (best_tiebreak is None or tiebreak < best_tiebreak)
                    )
                ):
                    best_probability = probability
                    best_page = guess.page
                    best_tiebreak = tiebreak
            return max(0.0, best_probability), best_page

        probability, page = solve(
            initial_pages,
            max(1, remaining_turns),
            initial_blocked,
        )
        if not page:
            return candidates[0], 0.0
        return self._by_page[page], probability

    def analyze(
        self,
        rows: list[dict],
        remaining_turns: int,
        guessed_pages: set[str] | None = None,
        top_n: int = 5,
    ) -> SolverAnalysis:
        guessed_pages = set(guessed_pages or ())
        candidates = self.filter_candidates(rows)
        if not candidates:
            # Bad or stale feedback should fail safely to the original answer pool.
            candidates = tuple(
                player for player in self.initial_candidates
                if player.page not in guessed_pages
            )
        moves = self.rank_moves(
            candidates,
            guessed_pages=guessed_pages,
            limit=top_n,
        )
        if not moves:
            raise ValueError("求解器没有可用猜测")

        if len(candidates) <= self.exact_threshold:
            recommended, probability = self._exact_choice(
                candidates,
                remaining_turns,
                guessed_pages,
            )
            mode = "小候选集合精确有限步求解"
        else:
            recommended = moves[0].player
            probability = None
            mode = "全局信息增益"

        return SolverAnalysis(
            candidates=candidates,
            moves=moves,
            recommended=recommended,
            mode=mode,
            exact_solve_probability=probability,
        )
