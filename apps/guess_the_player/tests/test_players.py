import json
import tempfile
import unittest
from pathlib import Path

from playerdb import players
from server.game import GREEN, compare
from playerdb.players import ANSWER_ROLES, Player, PlayerDB
from playerdb.rankings import normalize_team_name


class PlayerDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = PlayerDB()

    def test_unresolved_stubs_are_removed(self):
        # 空壳条目(除昵称外全空)必须被剔除;具体数量随数据快照浮动,
        # 不做硬编码 —— 2026-07 重跑后上游已能全部解析,允许为 0。
        self.assertTrue(all(p.is_searchable for p in self.db.players))
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

    def test_only_head_coach_affiliation_becomes_game_team(self):
        friberg = self.db.lookup("friberg")
        neo = self.db.lookup("NEO")
        # Inactive Coach 显示自由身；当前主教练保留战队。
        self.assertEqual(friberg.primary_role, "Rifler")
        self.assertEqual(friberg.team, "")
        self.assertEqual(neo.primary_role, "Coach")
        self.assertEqual(neo.team, "Astralis")
        self.assertFalse(neo.is_active)

    def test_head_coach_and_assistant_coach_have_distinct_roles(self):
        self.assertEqual(self.db.lookup("NEO").primary_role, "Coach")
        self.assertEqual(self.db.lookup("gla1ve").primary_role, "Coach")
        self.assertEqual(self.db.lookup("zhokiNg").primary_role, "Coach")
        self.assertEqual(self.db.lookup("KrizzeN").primary_role, "Rifler")
        # 当前主教练保留组织，但不进入正式选手阵容。
        for nickname, team in (
            ("NEO", "Astralis"),
            ("gla1ve", "100 Thieves"),
            ("zhokiNg", "TYLOO"),
            ("mou", "HOTU"),
            ("AZR", "FlyQuest"),
            ("jR", "IC Esports"),      # 队史行仍是旧名 Inner Circle,靠别名归一
        ):
            player = self.db.lookup(nickname)
            self.assertEqual(player.team, team)
            self.assertEqual(player.primary_role, "Coach")
            self.assertFalse(player.is_active)
        # Liquipedia 顶层可能仍写 coach；当前队史是 Assistant Coach 时不能误判。
        # KrizzeN 是纯 assistant coach，kaze 是顶层 coach + 队史无主教练记录。
        krizzen = self.db.lookup("KrizzeN")
        kaze = self.db.lookup("kaze")
        self.assertFalse(krizzen.is_head_coach)
        self.assertEqual((krizzen.team, krizzen.primary_role), ("", "Rifler"))
        self.assertFalse(kaze.is_head_coach)
        self.assertEqual((kaze.team, kaze.primary_role), ("", "AWPer"))
        self.assertEqual(self.db.lookup("natu").team, "")
        # 但人工层显式指定 Coach 时以人工为准:上游只把 S0tF1k 记成 Spirit 的
        # Assistant Coach,人工确认他就是这队公认的教练,override 必须能推翻
        # 上面那条规则,否则会退化成"自由身教练"。
        s0tf1k = self.db.lookup("S0tF1k")
        self.assertTrue(s0tf1k.is_head_coach)
        self.assertEqual((s0tf1k.team, s0tf1k.primary_role), ("Spirit", "Coach"))

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

    def test_country_tables_stay_in_sync_across_python_and_js(self):
        """playerdb/regions.py 的赛区表和 static/countries.js 的中文名表必须
        逐键一致:少了中文名游戏里会显示英文原文,少了赛区则整个人退成
        Other。两张表分处两种语言,没有测试就只能靠人肉记得同时改。"""
        import re

        from playerdb.regions import REGION
        js = (Path(__file__).resolve().parent.parent
              / "static" / "countries.js").read_text(encoding="utf-8")
        body = js[js.index("{"):js.rindex("}")]
        cn = set(re.findall(r'"([^"]+)"\s*:', body))
        self.assertEqual(cn - set(REGION), set(), "有中文名但没有赛区")
        self.assertEqual(set(REGION) - cn, set(), "有赛区但没有中文名")

    def test_country_input_is_canonicalised(self):
        """线上手打过 'russia':大小写不符会同时打掉赛区、国旗和中文名,
        而且三处都不报错,所以入口必须归一。"""
        from playerdb.regions import canonical_country, region_of

        self.assertEqual(canonical_country("russia"), "Russia")
        self.assertEqual(canonical_country("  UNITED STATES "), "United States")
        self.assertEqual(canonical_country("southkorea"), "South Korea")
        self.assertIsNone(canonical_country("Wakanda"))
        self.assertEqual(region_of(canonical_country("russia")), "CIS")

    def test_renamed_org_collapses_to_its_current_name(self):
        """IC Esports 之前分裂成两支队:Liquipedia 把 Inner Circle Esports
        重定向到 IC Esports,但 jR 的队史行仍写着旧名 Inner Circle。缩写改名
        跨不过 normalize_team_name(它只吃掉 team/gaming/esports 这类词,
        innercircle 和 ic 不会归一),所以只能靠快照里的别名表兜住。"""
        ranking = self.db.ranking
        for name in ("IC Esports", "Inner Circle", "Inner Circle Esports"):
            self.assertEqual(ranking.canonical_name(name), "IC Esports", name)
        self.assertEqual(
            [p.team for p in self.db.players if p.team == "Inner Circle"], [])

    def test_every_ranking_alias_points_at_a_listed_team(self):
        """别名的目标不在 teams 列表里时会被静默丢弃,别名等于没写——
        和失效 override 一样是不报错的静默失败,所以这里守住。"""
        ranking = self.db.ranking
        dangling = {alias: target for alias, target in ranking.aliases.items()
                    if ranking.canonical_name(target) is None}
        self.assertEqual(dangling, {})

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
        # 助教保留选手身份并自由身；当前主教练保留 Coach 和所属战队。
        attacker = self.db.lookup("Attacker")
        zhoking = self.db.lookup("zhokiNg")
        gla1ve = self.db.lookup("gla1ve")
        self.assertEqual(attacker.primary_role, "Rifler")
        self.assertEqual(attacker.team or "", "")
        self.assertEqual(gla1ve.primary_role, "Coach")
        self.assertEqual(gla1ve.team, "100 Thieves")
        self.assertEqual(zhoking.primary_role, "Coach")
        self.assertEqual(zhoking.team, "TYLOO")

    def test_inactive_and_new_team_examples(self):
        # 这条断言的是**数据快照**,所以选人要选不会再变的:nota 原本在这里当
        # 「无队」样本,2026-09-01 那次刷新他加入了 CYBERSHOKE,测试才挂的——
        # 数据是对的,样本选错了。换成已退役的 cajunb。
        cajunb = self.db.lookup("cajunb")
        belchonokk = self.db.lookup("BELCHONOKK")
        xyp9x = self.db.lookup("Xyp9x")
        self.assertEqual((cajunb.team or "", cajunb.primary_role), ("", "Rifler"))
        # 队名归一层把 Liquipedia 的 "1w Team" 收敛回 "1win",这里断言的是
        # 归一之后的对外值,所以上游改名不该影响它
        self.assertEqual(
            (belchonokk.team, belchonokk.primary_role),
            ("1win", "Rifler"),
        )
        self.assertEqual((xyp9x.team or "", xyp9x.primary_role), ("", "Rifler"))

    def test_china_regions_share_nationality_and_flag(self):
        mainland = self.db.lookup("Attacker")
        hong_kong = self.db.lookup("Freeman")
        taiwan = self.db.lookup("Marek")

        self.assertEqual(mainland.brief()["country"], "中国")
        self.assertEqual(hong_kong.brief()["country"], "中国香港")
        self.assertEqual(taiwan.full()["country"], "中国台湾")
        # 图片 URL 带内容哈希(?v=),这里只关心三地共用同一面旗
        self.assertEqual(mainland.flag.split("?")[0], "/img/flags/cn.png")
        self.assertEqual(hong_kong.flag, mainland.flag)
        self.assertEqual(taiwan.flag, mainland.flag)

        self.assertEqual(compare(hong_kong, mainland)[0]["state"], GREEN)
        taiwan_cell = compare(taiwan, mainland)[0]
        self.assertEqual(taiwan_cell["state"], GREEN)
        self.assertEqual(taiwan_cell["value"], "中国台湾")


class ManualLayerTests(unittest.TestCase):
    """人工层(新增选手 / override)与爬虫生成物的合并规则。"""

    def _db(self, tmp, scraped, manual):
        data = Path(tmp) / "players.json"
        data.write_text(json.dumps({"generated_at": "", "players": scraped}),
                        encoding="utf-8")
        players.MANUAL_PLAYERS_PATH = Path(tmp) / "manual.json"
        players.MANUAL_PLAYERS_PATH.write_text(
            json.dumps({"players": manual}), encoding="utf-8")
        return PlayerDB(data)

    def setUp(self):
        self._old = (players.MANUAL_PLAYERS_PATH, players.OVERRIDES_PATH,
                     players.LEGACY_OVERRIDES_PATH)

    def tearDown(self):
        (players.MANUAL_PLAYERS_PATH, players.OVERRIDES_PATH,
         players.LEGACY_OVERRIDES_PATH) = self._old

    def _rec(self, page, **kw):
        rec = {"page": page, "nickname": page, "country": "Denmark",
               "birth_date": "1998-01-01", "roles": ["rifle"], "status": "Active"}
        rec.update(kw)
        return rec

    def test_manual_player_is_appended(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self._db(tmp, [self._rec("A")], [self._rec("Egg")])
            self.assertEqual(sorted(db.by_page), ["A", "Egg"])
            self.assertTrue(db.by_page["Egg"].is_manual)
            self.assertFalse(db.by_page["A"].is_manual)

    def test_manual_record_replaces_scraped_page_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self._db(tmp,
                          [self._rec("A"), self._rec("B"), self._rec("C")],
                          [self._rec("B", team="Manual FC")])
            self.assertEqual([p.page for p in db.players], ["A", "B", "C"])
            self.assertEqual(db.by_page["B"].team, "Manual FC")
            self.assertTrue(db.by_page["B"].is_manual)

    def test_overrides_fall_back_to_pre_migration_path(self):
        """老位置的 player_overrides.json 仍然认——找不到就当零条人工修正,
        会一次性作废上百条已确认结论。"""
        with tempfile.TemporaryDirectory() as tmp:
            players.OVERRIDES_PATH = Path(tmp) / "manual" / "overrides.json"
            players.LEGACY_OVERRIDES_PATH = Path(tmp) / "legacy.json"
            players.LEGACY_OVERRIDES_PATH.write_text(
                json.dumps({"A": {"game_role": "AWPer"}}), encoding="utf-8")
            db = self._db(tmp, [self._rec("A")], [])
            self.assertEqual(db.by_page["A"].primary_role, "AWPer")


if __name__ == "__main__":
    unittest.main()
