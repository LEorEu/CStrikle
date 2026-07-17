import unittest

from server.ai_player import AIPlayer
from server.players import PlayerDB


class _FailingCompletions:
    async def create(self, **_kwargs):
        raise RuntimeError("controlled model failure")


class _FailingClient:
    class _Chat:
        completions = _FailingCompletions()

    chat = _Chat()


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


if __name__ == "__main__":
    unittest.main()
