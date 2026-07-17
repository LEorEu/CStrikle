import unittest

from server.players import ANSWER_ROLES, PlayerDB


class PlayerDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = PlayerDB()

    def test_unresolved_stubs_are_removed(self):
        self.assertEqual(self.db.excluded_stubs, 7)
        pages = set(self.db.by_page)
        self.assertNotIn("ALEX", pages)
        self.assertNotIn("AdreN", pages)

    def test_common_nicknames_resolve_to_complete_famous_profile(self):
        alex = self.db.lookup("alex")
        adren = self.db.lookup("AdreN")
        self.assertEqual(alex.page, "ALEX (British player)")
        self.assertEqual(alex.country, "United Kingdom")
        self.assertEqual(adren.page, "AdreN (Kazakh player)")
        self.assertEqual(adren.primary_role, "Rifler")

    def test_legitimate_same_nickname_profiles_remain_searchable(self):
        self.assertEqual(len(self.db.by_nick["alex"]), 2)
        self.assertEqual(len(self.db.by_nick["adren"]), 2)

    def test_coach_team_uses_hltv_top100_snapshot(self):
        friberg = self.db.lookup("friberg")
        neo = self.db.lookup("NEO")
        # 无上榜战队的教练回退到选手时期位置;有上榜战队的教练保持 Coach
        self.assertEqual(friberg.primary_role, "Rifler")
        self.assertEqual(friberg.team, "")
        self.assertEqual(neo.primary_role, "Coach")
        self.assertEqual(neo.team, "Astralis")

    def test_teamless_coach_falls_back_to_playing_role(self):
        self.assertEqual(self.db.lookup("GuardiaN").primary_role, "AWPer")
        self.assertEqual(self.db.lookup("Golden").primary_role, "IGL")
        self.assertEqual(self.db.lookup("kRYSTAL").primary_role, "IGL")
        # 全库不再存在"Free Agent + Coach"的自相矛盾组合
        for p in self.db.players:
            if p.primary_role == "Coach":
                self.assertTrue(p.team, p.page)

    def test_every_answer_has_comparable_attributes(self):
        self.assertGreater(len(self.db.answer_players), 0)
        for player in self.db.answer_players:
            self.assertTrue(player.country, player.page)
            self.assertTrue(player.birth_date, player.page)
            self.assertIn(player.primary_role, ANSWER_ROLES, player.page)
            self.assertTrue(player.is_game_ready, player.page)

    def test_every_difficulty_pool_contains_only_game_ready_answers(self):
        for difficulty in ("easy", "medium", "hard"):
            pool = self.db.difficulty_pool(difficulty)
            self.assertGreaterEqual(len(pool), 2)
            self.assertTrue(all(player.is_game_ready for player in pool))


if __name__ == "__main__":
    unittest.main()
