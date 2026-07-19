import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from server.ai_player import AIPlayer
from server.game import compare
from server.players import PlayerDB


class _FailingCompletions:
    def __init__(self):
        self.calls = 0

    async def create(self, **_kwargs):
        self.calls += 1
        raise RuntimeError("controlled model failure")


class _SubmittingCompletions:
    def __init__(self):
        self.ai = None
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        page = sorted(self.ai._allowed_guess_pages)[-1]
        nickname = self.ai.db.by_page[page].nickname
        say_call = SimpleNamespace(
            id="call-say",
            function=SimpleNamespace(
                name="say",
                arguments=json.dumps({
                    "message": "范围已经不大了，这手我很有感觉。",
                }),
            ),
        )
        submit_call = SimpleNamespace(
            id="call-submit",
            function=SimpleNamespace(
                name="submit_guess",
                arguments=json.dumps({
                    "nickname": nickname,
                    "reason": "这名选手最符合我对剩余线索的直觉。",
                }),
            ),
        )

        class Message:
            content = None
            reasoning_content = None
            tool_calls = [say_call, submit_call]

        return SimpleNamespace(
            choices=[SimpleNamespace(message=Message())],
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
                prompt_tokens_details=None,
                prompt_cache_hit_tokens=64,
            ),
        )


class _EasySubmittingCompletions:
    def __init__(self, nickname):
        self.nickname = nickname
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        say_call = SimpleNamespace(
            id="call-easy-say",
            function=SimpleNamespace(
                name="say",
                arguments=json.dumps({
                    "message": "这手我就凭老玩家的直觉来了。",
                }),
            ),
        )
        submit_call = SimpleNamespace(
            id="call-easy-submit",
            function=SimpleNamespace(
                name="submit_guess",
                arguments=json.dumps({
                    "nickname": self.nickname,
                    "reason": "我看了上一手反馈，但还是想凭印象试试他。",
                }),
            ),
        )

        class Message:
            content = "这组线索让我想到一位熟悉的选手。"
            reasoning_content = None
            tool_calls = [say_call, submit_call]

        return SimpleNamespace(
            choices=[SimpleNamespace(message=Message())],
            usage=None,
        )


class _SayingCompletions:
    def __init__(self):
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        say_call = SimpleNamespace(
            id="call-fixed-say",
            function=SimpleNamespace(
                name="say",
                arguments=json.dumps({
                    "message": "这手已经算清楚了，你跟得上吗？",
                }),
            ),
        )

        class Message:
            content = None
            reasoning_content = None
            tool_calls = [say_call]

        return SimpleNamespace(
            choices=[SimpleNamespace(message=Message())],
            usage=None,
        )


def _client(completions):
    return SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )


def _feedback_row(db, guess_name="k0nfig", answer_name="GeT_RiGhT"):
    guess = db.lookup(guess_name)
    answer = db.lookup(answer_name)
    return {
        "player": guess.brief(),
        "cells": compare(guess, answer),
        "correct": False,
    }


class AIPlayerTests(unittest.IsolatedAsyncioTestCase):
    async def test_easy_reads_feedback_and_freely_uses_model_without_solver(self):
        db = PlayerDB()
        row = _feedback_row(db)
        matching_pages = {
            player.page
            for player in AIPlayer(
                db,
                db.difficulty_pool("top20"),
                "test pool",
            ).solver.filter_candidates([row])
        }
        free_choice = next(
            player
            for player in db.answer_players
            if player.page not in matching_pages
            and player.page != db.lookup("k0nfig").page
        )
        completions = _EasySubmittingCompletions(free_choice.nickname)
        ai = AIPlayer(
            db,
            db.difficulty_pool("top20"),
            "test pool",
            ai_level="easy",
        )
        ai.client = _client(completions)

        with (
            patch.object(
                ai.solver,
                "analyze",
                side_effect=AssertionError("easy must not call solver"),
            ),
            patch("server.ai_player.config.AI_SEARCH_ENABLED", True),
        ):
            result = await ai.take_turn(
                [row],
                "对手已经猜了 1 次",
                {"k0nfig", db.lookup("k0nfig").page},
            )

        self.assertEqual(result.guess_name, free_choice.page)
        self.assertIsNone(ai._allowed_guess_pages)
        self.assertIsNone(ai._required_guess)
        self.assertEqual(len(completions.requests), 1)
        request = completions.requests[0]
        prompt = "\n".join(
            message["content"] for message in request["messages"]
        )
        self.assertIn("k0nfig", prompt)
        self.assertIn("对手已经猜了 1 次", prompt)
        self.assertIn("服务器不会给你候选名单", prompt)
        self.assertEqual(
            [tool["function"]["name"] for tool in request["tools"]],
            ["ddgs_search", "say", "submit_guess"],
        )
        decision = result.events[0]
        self.assertEqual(decision["type"], "decision")
        self.assertEqual(decision["strategy"], "下饭")
        self.assertIn("凭自己的 CS 印象", decision["summary"])
        self.assertEqual(decision["shortlist"], [])
        self.assertTrue(any(
            event["type"] == "say" for event in result.events
        ))

    async def test_easy_first_turn_does_not_offer_search(self):
        db = PlayerDB()
        completions = _EasySubmittingCompletions("s1mple")
        ai = AIPlayer(
            db,
            db.difficulty_pool("top20"),
            "test pool",
            ai_level="easy",
        )
        ai.client = _client(completions)

        result = await ai.take_turn([], "test opponent", set())

        self.assertTrue(result.guess_name)
        self.assertEqual(
            [tool["function"]["name"]
             for tool in completions.requests[0]["tools"]],
            ["say", "submit_guess"],
        )

    async def test_easy_does_not_offer_ddgs_when_project_search_is_disabled(self):
        db = PlayerDB()
        completions = _EasySubmittingCompletions("s1mple")
        ai = AIPlayer(
            db,
            db.difficulty_pool("top20"),
            "test pool",
            ai_level="easy",
        )
        ai.client = _client(completions)
        row = _feedback_row(db)

        with patch("server.ai_player.config.AI_SEARCH_ENABLED", False):
            result = await ai.take_turn(
                [row],
                "test opponent",
                {"k0nfig", db.lookup("k0nfig").page},
            )

        self.assertTrue(result.guess_name)
        request = completions.requests[0]
        self.assertEqual(
            [tool["function"]["name"] for tool in request["tools"]],
            ["say", "submit_guess"],
        )
        self.assertIn(
            "项目不提供额外搜索工具",
            request["messages"][0]["content"],
        )

    async def test_easy_model_failure_returns_random_fallback(self):
        db = PlayerDB()
        failing = _FailingCompletions()
        ai = AIPlayer(
            db,
            db.difficulty_pool("top20"),
            "test pool",
            ai_level="easy",
        )
        ai.client = _client(failing)

        result = await ai.take_turn([], "test opponent", set())

        self.assertIsNone(result.guess_name)
        self.assertTrue(result.fallback_guess)
        self.assertEqual(failing.calls, 1)
        self.assertEqual(
            [event["type"] for event in result.events].count("model_error"),
            1,
        )
        self.assertIn("备用人选", result.events[0]["summary"])

    async def test_normal_opening_keeps_top_five_when_chat_fails(self):
        db = PlayerDB()
        failing = _FailingCompletions()
        ai = AIPlayer(
            db,
            db.difficulty_pool("top20"),
            "test pool",
            ai_level="normal",
        )
        ai.client = _client(failing)
        analysis = ai.solver.analyze([], 8, set())
        top_five = {
            move.player.page
            for move in ai.solver.rank_moves(analysis.candidates, limit=5)
        }

        result = await ai.take_turn([], "test opponent", set())

        self.assertIn(result.guess_name, top_five)
        self.assertEqual(failing.calls, 1)
        self.assertEqual(result.events[0]["strategy"], "普通")
        self.assertEqual(len(result.events[0]["shortlist"]), 5)
        self.assertTrue(any(
            event["type"] == "chat_error" for event in result.events
        ))

    async def test_normal_after_feedback_lets_model_choose_from_candidates(self):
        db = PlayerDB()
        ai = AIPlayer(
            db,
            db.difficulty_pool("top20"),
            "test pool",
            reasoning_effort="high",
            thinking_mode="disabled",
            ai_level="normal",
        )
        completions = _SubmittingCompletions()
        completions.ai = ai
        ai.client = _client(completions)

        result = await ai.take_turn(
            [_feedback_row(db)],
            "test opponent",
            {"k0nfig", db.lookup("k0nfig").page},
        )

        self.assertEqual(len(completions.requests), 1)
        request = completions.requests[0]
        self.assertEqual(request["reasoning_effort"], "high")
        self.assertEqual(
            request["extra_body"],
            {"thinking": {"type": "disabled"}},
        )
        self.assertEqual(
            [tool["function"]["name"] for tool in request["tools"]],
            ["say", "submit_guess"],
        )
        self.assertEqual(request["tool_choice"], "required")
        self.assertIn(result.guess_name, ai._allowed_guess_pages)
        usage = next(event for event in result.events if event["type"] == "usage")
        decision = next(
            event for event in result.events if event["type"] == "decision"
        )
        self.assertEqual(usage["cached_tokens"], 64)
        self.assertEqual(usage["cache_miss_tokens"], 36)
        self.assertEqual(usage["completion_tokens"], 20)
        self.assertEqual(decision["strategy"], "普通")
        self.assertIn("AI 自己选择", decision["summary"])
        thinking = next(
            event for event in result.events if event["type"] == "thinking"
        )
        self.assertIn("直觉", thinking["text"])
        self.assertTrue(any(
            event["type"] == "say" for event in result.events
        ))

    async def test_normal_model_failure_returns_fast_candidate_fallback(self):
        db = PlayerDB()
        failing = _FailingCompletions()
        ai = AIPlayer(
            db,
            db.difficulty_pool("top20"),
            "test pool",
            ai_level="normal",
        )
        ai.client = _client(failing)

        result = await ai.take_turn(
            [_feedback_row(db)],
            "test opponent",
            {"k0nfig", db.lookup("k0nfig").page},
        )

        self.assertIsNone(result.guess_name)
        self.assertTrue(result.fallback_guess)
        self.assertEqual(failing.calls, 1)
        event_types = [event["type"] for event in result.events]
        self.assertEqual(event_types.count("model_error"), 1)
        decision = next(
            event for event in result.events if event["type"] == "decision"
        )
        self.assertIn("改用备用人选", decision["summary"])

    async def test_hard_solver_guess_survives_chat_failure(self):
        db = PlayerDB()
        failing = _FailingCompletions()
        ai = AIPlayer(
            db,
            db.difficulty_pool("top20"),
            "test pool",
            ai_level="hard",
        )
        ai.client = _client(failing)
        expected = ai.solver.analyze([], 8, set()).recommended.page

        result = await ai.take_turn([], "test opponent", set())

        self.assertEqual(result.guess_name, expected)
        self.assertEqual(result.guess_name, result.fallback_guess)
        self.assertEqual(failing.calls, 1)
        self.assertEqual(result.events[0]["strategy"], "作弊")
        self.assertTrue(any(
            event["type"] == "chat_error" for event in result.events
        ))

    async def test_hard_uses_say_tool_without_changing_solver_guess(self):
        db = PlayerDB()
        completions = _SayingCompletions()
        chats = []

        async def on_say(message):
            chats.append(message)

        ai = AIPlayer(
            db,
            db.difficulty_pool("top20"),
            "test pool",
            ai_level="hard",
            on_say=on_say,
        )
        ai.client = _client(completions)
        expected = ai.solver.analyze([], 8, set()).recommended.page

        result = await ai.take_turn([], "test opponent", set())

        self.assertEqual(result.guess_name, expected)
        self.assertEqual(len(completions.requests), 1)
        request = completions.requests[0]
        self.assertEqual(
            [tool["function"]["name"] for tool in request["tools"]],
            ["say"],
        )
        self.assertEqual(
            request["tool_choice"]["function"]["name"],
            "say",
        )
        self.assertEqual(chats, ["这手已经算清楚了，你跟得上吗？"])
        self.assertTrue(any(
            event["type"] == "say" for event in result.events
        ))

    async def test_normal_status_uses_player_language_without_name(self):
        db = PlayerDB()
        statuses = []

        async def on_status(state, detail):
            statuses.append((state, detail))

        ai = AIPlayer(
            db,
            db.difficulty_pool("top20"),
            "test pool",
            ai_level="normal",
            on_status=on_status,
        )
        completions = _SubmittingCompletions()
        completions.ai = ai
        ai.client = _client(completions)

        result = await ai.take_turn(
            [_feedback_row(db)],
            "test opponent",
            {"k0nfig", db.lookup("k0nfig").page},
        )

        self.assertTrue(result.guess_name)
        self.assertGreaterEqual(len(statuses), 2)
        self.assertIn("整理上一手线索", statuses[0][1])
        self.assertIn("可能人选", statuses[1][1])
        self.assertNotIn(
            db.by_page[result.guess_name].nickname,
            statuses[1][1],
        )


if __name__ == "__main__":
    unittest.main()
