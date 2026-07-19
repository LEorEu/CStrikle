import unittest

from server.game import compare
from server.players import PlayerDB
from server.solver import PlayerSolver, feedback_signature


class PlayerSolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = PlayerDB()
        cls.pool = cls.db.difficulty_pool("medium")
        cls.solver = PlayerSolver(cls.db, cls.pool)

    def test_signature_ignores_display_values(self):
        answer = self.db.lookup("s1mple")
        guess = self.db.lookup("ZywOo")
        cells = compare(guess, answer)
        changed = [dict(cell, value="changed") for cell in cells]
        self.assertEqual(feedback_signature(cells), feedback_signature(changed))

    def test_filter_keeps_true_answer_and_removes_guessed_identity(self):
        answer = self.db.lookup("s1mple")
        guess = self.db.lookup("ZywOo")
        row = {
            "player": guess.brief(),
            "cells": compare(guess, answer),
            "correct": False,
        }
        candidates = self.solver.filter_candidates([row])
        pages = {player.page for player in candidates}
        self.assertIn(answer.page, pages)
        self.assertNotIn(guess.page, pages)

    def test_information_gain_move_is_valid(self):
        analysis = self.solver.analyze([], 8, set())
        self.assertEqual(len(analysis.candidates), len(self.pool))
        self.assertIn(analysis.recommended, self.db.answer_players)
        self.assertGreater(analysis.moves[0].entropy, 0)

    def test_exact_solver_finishes_small_candidate_set(self):
        small = self.pool[:6]
        solver = PlayerSolver(self.db, small, exact_threshold=10)
        analysis = solver.analyze([], 3, set())
        self.assertEqual(analysis.mode, "小候选集合精确有限步求解")
        self.assertEqual(analysis.exact_solve_probability, 1.0)

    def test_single_candidate_is_selected(self):
        answer = self.db.lookup("s1mple")
        solver = PlayerSolver(self.db, [answer], exact_threshold=10)
        analysis = solver.analyze([], 1, set())
        self.assertEqual(analysis.recommended.page, answer.page)
        self.assertEqual(analysis.exact_solve_probability, 1.0)

if __name__ == "__main__":
    unittest.main()
