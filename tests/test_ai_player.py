import json
import unittest
from types import SimpleNamespace

from server.ai_player import AIPlayer
from server.players import PlayerDB


class _FailingCompletions:
    async def create(self, **_kwargs):
        raise RuntimeError("controlled model failure")


class _FailingClient:
    class _Chat:
        completions = _FailingCompletions()

    chat = _Chat()


class _SubmittingCompletions:
    def __init__(self):
        self.ai = None
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        nickname = self.ai._required_guess.nickname
        tool_call = SimpleNamespace(
            id="call-submit",
            function=SimpleNamespace(
                name="submit_guess",
                arguments=json.dumps({"nickname": nickname}),
            ),
        )

        class Message:
            content = None
            reasoning_content = None
            tool_calls = [tool_call]

            @staticmethod
            def model_dump(**_kwargs):
                return {
                    "role": "assistant",
                    "tool_calls": [{
                        "id": "call-submit",
                        "type": "function",
                        "function": {
                            "name": "submit_guess",
                            "arguments": json.dumps({"nickname": nickname}),
                        },
                    }],
                }

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


class AIPlayerTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_failure_returns_solver_fallback_without_retry_loop(self):
        db = PlayerDB()
        ai = AIPlayer(
            db,
            db.difficulty_pool("medium"),
            "test pool",
            max_guesses=8,
            reasoning_effort="low",
        )
        ai.client = _FailingClient()
        result = await ai.take_turn([], "test opponent", set())

        self.assertIsNone(result.guess_name)
        self.assertTrue(result.fallback_guess)
        event_types = [event["type"] for event in result.events]
        self.assertIn("solver", event_types)
        self.assertIn("model_error", event_types)
        self.assertEqual(event_types.count("model_error"), 1)

    async def test_thinking_mode_and_usage_are_forwarded_and_recorded(self):
        db = PlayerDB()
        ai = AIPlayer(
            db,
            db.difficulty_pool("medium"),
            "test pool",
            reasoning_effort="high",
            thinking_mode="disabled",
            ai_level="hard",
        )
        completions = _SubmittingCompletions()
        completions.ai = ai
        ai.client = SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        )

        result = await ai.take_turn([], "test opponent", set())

        self.assertEqual(len(completions.requests), 1)
        request = completions.requests[0]
        self.assertEqual(request["reasoning_effort"], "high")
        self.assertEqual(
            request["extra_body"],
            {"thinking": {"type": "disabled"}},
        )
        usage = next(event for event in result.events if event["type"] == "usage")
        solver = next(event for event in result.events if event["type"] == "solver")
        self.assertEqual(usage["cached_tokens"], 64)
        self.assertEqual(usage["cache_miss_tokens"], 36)
        self.assertEqual(usage["completion_tokens"], 20)
        self.assertEqual(result.guess_name, result.fallback_guess)
        self.assertTrue(solver["explanation"])
        self.assertIsNotNone(solver["selected_metrics"])
        self.assertIn("previous_candidate_count", solver)

    async def test_status_exposes_safe_solver_stage_without_player_name(self):
        db = PlayerDB()
        statuses = []

        async def on_status(state, detail):
            statuses.append((state, detail))

        ai = AIPlayer(
            db,
            db.difficulty_pool("medium"),
            "test pool",
            reasoning_effort="medium",
            ai_level="hard",
            on_status=on_status,
        )
        completions = _SubmittingCompletions()
        completions.ai = ai
        ai.client = SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        )

        result = await ai.take_turn([], "test opponent", set())

        self.assertEqual(result.guess_name, result.fallback_guess)
        self.assertGreaterEqual(len(statuses), 2)
        self.assertIn("筛选严格候选", statuses[0][1])
        self.assertIn("严格候选", statuses[1][1])
        self.assertNotIn(ai._required_guess.nickname, statuses[1][1])


if __name__ == "__main__":
    unittest.main()
