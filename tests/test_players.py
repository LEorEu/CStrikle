import unittest

from server.game import GREEN, compare
from server.players import ANSWER_ROLES, Player, PlayerDB


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

    def test_primary_role_inference_mechanism(self):
        # 断言推断"机制"而非具体选手的争议结论(SmithZz/pashaBiceps 该是狙还是
        # 步枪交给数据层和 player_overrides.json 去定,不写死在测试里)。
        def role_of(roles, game_role=None):
            return Player({"roles": roles, "game_role": game_role}).primary_role

        # 1) game_role 人工覆盖优先级最高,短路一切启发式
        self.assertEqual(role_of(["rifle"], game_role="AWPer"), "AWPer")
        self.assertEqual(role_of(["awp"], game_role="Rifler"), "Rifler")
        # 2) 有 IGL 标签就判指挥,不论其位置
        self.assertEqual(role_of(["rifle", "igl"]), "IGL")
        self.assertEqual(role_of(["igl", "awp"]), "IGL")
        # 3) 狙 vs 步枪按 Liquipedia 原始顺序取第一个(启发式,非绝对规则),
        #    不再固定把 AWP 提到步枪之前
        self.assertEqual(role_of(["support", "awp"]), "Rifler")
        self.assertEqual(role_of(["awp", "rifle"]), "AWPer")
        # 4) support / lurk / entry / rifle 一族都归 Rifler
        for tag in ("support", "lurk", "lurker", "entry", "rifle", "rifler"):
            self.assertEqual(role_of([tag]), "Rifler", tag)

    def test_primary_role_smoke_undisputed_players(self):
        # 只用没争议的真人做冒烟:coldzera 明显步枪、ZywOo 明显狙。
        self.assertEqual(self.db.lookup("coldzera").primary_role, "Rifler")
        self.assertEqual(self.db.lookup("ZywOo").primary_role, "AWPer")

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

    def test_china_regions_share_nationality_and_flag(self):
        mainland = self.db.lookup("Attacker")
        hong_kong = self.db.lookup("Freeman")
        taiwan = self.db.lookup("Marek")

        self.assertEqual(mainland.brief()["country"], "中国")
        self.assertEqual(hong_kong.brief()["country"], "中国香港")
        self.assertEqual(taiwan.full()["country"], "中国台湾")
        self.assertEqual(mainland.flag, "/img/flags/cn.png")
        self.assertEqual(hong_kong.flag, mainland.flag)
        self.assertEqual(taiwan.flag, mainland.flag)

        self.assertEqual(compare(hong_kong, mainland)[0]["state"], GREEN)
        taiwan_cell = compare(taiwan, mainland)[0]
        self.assertEqual(taiwan_cell["state"], GREEN)
        self.assertEqual(taiwan_cell["value"], "中国台湾")


if __name__ == "__main__":
    unittest.main()
