import json
import tempfile
import unittest
from pathlib import Path

from gtptools.sync_hltv_roles import (
    apply_review,
    choose_candidate,
    identity_matches,
    score_candidate,
    select_local_players,
    suggest_role,
)


class HltvMatchingTests(unittest.TestCase):
    def setUp(self):
        self.smithzz = {
            "page": "SmithZz",
            "nickname": "SmithZz",
            "real_name": "Edouard Dubourdeaux",
            "country": "France",
            "roles": ["support", "awp"],
        }

    def test_match_uses_nickname_and_real_name(self):
        right = {
            "nickname": "SmithZz",
            "slug": "smithzz",
            "text": "Edouard 'SmithZz' Dubourdeaux",
            "hltv_id": 7170,
        }
        wrong = {
            "nickname": "SmithZz",
            "slug": "smithzz",
            "text": "Someone 'SmithZz' Else",
            "hltv_id": 99999,
        }
        self.assertGreater(score_candidate(self.smithzz, right), 0.9)
        chosen, reason = choose_candidate(self.smithzz, [wrong, right])
        self.assertEqual(chosen["hltv_id"], 7170)
        self.assertIn("真实姓名", reason)

    def test_ambiguous_candidates_require_manual_review(self):
        candidates = [
            {
                "nickname": "ALEX",
                "slug": "alex",
                "text": "Alex 'ALEX' One",
                "hltv_id": 1,
            },
            {
                "nickname": "ALEX",
                "slug": "alex",
                "text": "Alex 'ALEX' Two",
                "hltv_id": 2,
            },
        ]
        local = {"nickname": "ALEX", "real_name": "Alex Unknown"}
        chosen, reason = choose_candidate(local, candidates)
        self.assertIsNone(chosen)
        self.assertIn("分差不足", reason)

    def test_profile_identity_must_match_real_name(self):
        self.assertTrue(
            identity_matches(
                self.smithzz,
                {"nickname": "SmithZz", "real_name": "Edouard Dubourdeaux"},
            )
        )
        self.assertFalse(
            identity_matches(
                self.smithzz,
                {"nickname": "SmithZz", "real_name": "Someone Else"},
            )
        )
        self.assertTrue(
            identity_matches(
                {"nickname": "Stewie2K", "real_name": "Jacky Yip"},
                {"nickname": "Stewie2K", "real_name": "Jake Yip"},
                ["Jake Yip"],
            )
        )

    def test_2k_alias_selects_stewie_not_woro(self):
        players = [
            {"page": "Stewie2K", "nickname": "Stewie2K"},
            {"page": "Woro2k", "nickname": "Woro2k"},
        ]
        stable_map = {
            "Stewie2K": {
                "hltv_id": 8797,
                "slug": "stewie2k",
                "aliases": ["2k"],
            }
        }
        selected = select_local_players(players, ["2k"], stable_map, False)
        self.assertEqual([p["page"] for p in selected], ["Stewie2K"])


class HltvSuggestionTests(unittest.TestCase):
    def test_maka_keeps_igl_and_records_secondary_awp_signal(self):
        local = {"roles": ["igl", "awp"]}
        profile = {"recent_maps": 22, "sniping_score": 81}
        evidence = [{"title": "Maka on wearing both hats, IGL and AWP"}]
        result = suggest_role(local, profile, evidence)
        self.assertEqual(result["suggested_role"], "IGL")
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["weapon_role"], "AWPer")

    def test_active_sniping_extremes_can_suggest_weapon_role(self):
        awper = suggest_role(
            {"roles": ["rifle"]},
            {"recent_maps": 15, "sniping_score": 82},
            [],
        )
        rifler = suggest_role(
            {"roles": ["awp"]},
            {"recent_maps": 15, "sniping_score": 12},
            [],
        )
        self.assertEqual(awper["suggested_role"], "AWPer")
        self.assertEqual(rifler["suggested_role"], "Rifler")

    def test_smithzz_without_recent_maps_stays_manual(self):
        result = suggest_role(
            {"roles": ["support", "awp"]},
            {"recent_maps": None, "sniping_score": None},
            [],
        )
        self.assertIsNone(result["suggested_role"])
        self.assertEqual(result["confidence"], "manual")
        self.assertIn("巅峰时期", result["reason"])

    def test_existing_game_role_is_protected(self):
        result = suggest_role(
            {"roles": ["rifle"]},
            {"recent_maps": 20, "sniping_score": 90},
            [],
            {"game_role": "Rifler"},
        )
        self.assertEqual(result["suggested_role"], "Rifler")
        self.assertEqual(result["confidence"], "protected")


class HltvApplyTests(unittest.TestCase):
    def test_apply_requires_decision_and_write(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            review = root / "review.json"
            overrides = root / "overrides.json"
            review.write_text(
                json.dumps(
                    {
                        "players": [
                            {
                                "local_page": "Maka",
                                "decision": "IGL",
                                "decision_field": "game_role",
                                "suggestion": {"reason": "verified"},
                                "profile": {
                                    "profile_url": "https://www.hltv.org/player/13138/maka"
                                },
                            },
                            {
                                "local_page": "SmithZz",
                                "decision": None,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            overrides.write_text("{}\n", encoding="utf-8")

            changed, _ = apply_review(
                review, overrides, write=False, replace_existing=False
            )
            self.assertEqual(changed, 1)
            self.assertEqual(json.loads(overrides.read_text()), {})

            changed, _ = apply_review(
                review, overrides, write=True, replace_existing=False
            )
            self.assertEqual(changed, 1)
            applied = json.loads(overrides.read_text(encoding="utf-8"))
            self.assertEqual(applied["Maka"]["game_role"], "IGL")
            self.assertIn("hltv.org/player/13138/maka", applied["Maka"]["hltv_profile"])


if __name__ == "__main__":
    unittest.main()
