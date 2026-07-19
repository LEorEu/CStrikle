import unittest

from server.game import GREEN, compare
from server.players import ANSWER_ROLES, Player, PlayerDB
from server.rankings import normalize_team_name


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

    def test_staff_affiliation_never_becomes_game_team(self):
        friberg = self.db.lookup("friberg")
        neo = self.db.lookup("NEO")
        # team 只表示正式选手席位；主教练也显示自由身。
        self.assertEqual(friberg.primary_role, "Coach")
        self.assertEqual(friberg.team, "")
        self.assertEqual(neo.primary_role, "Coach")
        self.assertEqual(neo.team, "")

    def test_head_coach_and_assistant_coach_have_distinct_roles(self):
        self.assertEqual(self.db.lookup("GuardiaN").primary_role, "Coach")
        self.assertEqual(self.db.lookup("Golden").primary_role, "Coach")
        self.assertEqual(self.db.lookup("kRYSTAL").primary_role, "Coach")
        self.assertEqual(self.db.lookup("KrizzeN").primary_role, "Rifler")
        # 当前主教练保留 Coach，但所有 staff 的 team 都为空。
        for p in self.db.players:
            if p.primary_role == "Coach":
                self.assertEqual(p.team or "", "", p.page)

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
        # 5) 只有主教练算 Coach；助教必须依赖 played_role/人工覆盖。
        self.assertEqual(role_of(["coach"]), "Coach")
        self.assertEqual(role_of(["assistant coach"]), "?")

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

    def test_role_set_whitelist_combinations(self):
        # 黄色重叠只允许白名单组合;指挥默认持步枪,IGL 不与 Rifler 构成混合
        def role_set_of(roles, game_role=None):
            return Player({"roles": roles, "game_role": game_role}).role_set

        self.assertEqual(role_set_of(["igl", "entry"]), {"IGL"})
        self.assertEqual(role_set_of(["igl", "awp"]), {"IGL", "AWPer"})
        self.assertEqual(role_set_of(["awp", "rifle"]), {"AWPer", "Rifler"})
        self.assertEqual(role_set_of(["support", "awp"]), {"Rifler", "AWPer"})
        self.assertEqual(role_set_of(["coach"]), {"Coach"})
        self.assertEqual(role_set_of(["broadcast analyst"]), set())
        # 覆盖 game_role 后按覆盖值参与白名单
        self.assertEqual(role_set_of(["support", "awp"], game_role="AWPer"),
                         {"AWPer", "Rifler"})

    def test_teamless_players_share_free_agent_category(self):
        # 退役/未签约/玩票不再是不同状态:无战队的人统一"自由身"互相判绿
        fer = self.db.lookup("fer")          # 实质退役
        degster = self.db.lookup("degster")  # 未签约现役
        self.assertEqual(fer.team or "", "")
        self.assertEqual(degster.team or "", "")
        self.assertEqual(fer.team_label, "自由身")
        team_cell = next(c for c in compare(fer, degster) if c["key"] == "team")
        self.assertEqual(team_cell["state"], GREEN)

    def test_team_aliases_use_one_identity_and_canonical_label(self):
        s1mple = self.db.lookup("s1mple")
        senzu = self.db.lookup("Senzu")
        self.assertEqual(s1mple.team, "BC.Game")
        self.assertEqual(senzu.team, "BC.Game")
        self.assertEqual(s1mple.team_logo, senzu.team_logo)
        team_cell = next(
            c for c in compare(s1mple, senzu) if c["key"] == "team")
        self.assertEqual(team_cell["state"], GREEN)

    def test_all_runtime_team_aliases_have_one_canonical_label(self):
        labels_by_key = {}
        for player in self.db.players:
            if not player.team:
                continue
            key = normalize_team_name(player.team)
            labels_by_key.setdefault(key, set()).add(player.team)
        conflicts = {
            key: labels
            for key, labels in labels_by_key.items()
            if len(labels) > 1
        }
        self.assertEqual(conflicts, {})

    def test_cologne_2026_falcons_players_receive_champion_placement(self):
        nicknames = ("m0NESY", "kyousuke", "karrigan", "TeSeS", "NiKo")
        for nickname in nicknames:
            player = self.db.lookup(nickname)
            cologne = next(
                m for m in player.majors
                if m["page"] == "Intel_Extreme_Masters/2026/Cologne")
            self.assertEqual(cologne["placement"], "1", nickname)
        self.assertEqual(self.db.lookup("NiKo").majors_won, 1)

    def test_recently_retired_staff_keep_playing_identity(self):
        # 助教保留选手身份；当前主教练使用 Coach；两者均为自由身。
        attacker = self.db.lookup("Attacker")
        zhoking = self.db.lookup("zhokiNg")
        gla1ve = self.db.lookup("gla1ve")
        self.assertEqual(attacker.primary_role, "Rifler")
        self.assertEqual(attacker.team or "", "")
        self.assertEqual(gla1ve.primary_role, "Coach")
        self.assertEqual(gla1ve.team or "", "")
        self.assertEqual(zhoking.primary_role, "Coach")
        self.assertEqual(zhoking.team or "", "")

    def test_inactive_and_new_team_examples(self):
        nota = self.db.lookup("nota")
        belchonokk = self.db.lookup("BELCHONOKK")
        xyp9x = self.db.lookup("Xyp9x")
        self.assertEqual((nota.team or "", nota.primary_role), ("", "Rifler"))
        self.assertEqual(
            (belchonokk.team, belchonokk.primary_role),
            ("TDK", "Rifler"),
        )
        self.assertEqual((xyp9x.team or "", xyp9x.primary_role), ("", "Rifler"))

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
