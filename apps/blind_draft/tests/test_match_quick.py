# -*- coding: utf-8 -*-
import random
import unittest

from blinddraft import draft as P
from blinddraft import major as M
from blinddraft import match as X


class QuickRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = M.load_config()
        cls.cap = float(cls.cfg["cohesion_cap"])
        cls.rosters = P.load_rosters()
        cls.field = M.make_field(random.Random(1), cls.cfg, cls.rosters, cls.cap)
        cls.player = cls.field[15]

    def test_three_scenes_use_real_match_rules(self):
        legs = X.quick_run(self.player, self.field, random.Random(2), self.cap)
        self.assertEqual([(x["bo"], x["pressure"]) for x in legs],
                         [(1, X.PRESSURE_BO1), (3, X.PRESSURE_BO3),
                          (3, X.PRESSURE_DECIDER)])
        self.assertEqual(len({x["opponent"].name for x in legs}), 3)
        self.assertTrue(all(x["result"].maps for x in legs))

    def test_opponents_are_near_the_player(self):
        legs = X.quick_run(self.player, self.field, random.Random(3), self.cap)
        nearest = sorted(abs(e.entry - self.player.entry) for e in self.field
                         if e is not self.player)[:3]
        got = sorted(abs(x["opponent"].entry - self.player.entry) for x in legs)
        self.assertEqual(got, nearest)

    def test_large_gap_is_not_certain_but_bo3_is_safer(self):
        rates = X.duel_entry_rates(80, 50, runs=6000, seed=9)
        self.assertGreater(rates[1], 0.87)
        self.assertLess(rates[1], 0.95)
        self.assertGreater(rates[3], rates[1])
        self.assertLess(rates[3], 1.0)


if __name__ == "__main__":
    unittest.main()
