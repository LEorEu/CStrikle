import unittest

from playerdb.scrape.build_db import (
    parse_infobox,
    parse_team_history,
    resolve_game_team,
    unresolved_blast_titles,
)
from playerdb.major_results import apply_major_results


class ScraperTests(unittest.TestCase):
    def test_non_player_page_is_not_an_infobox(self):
        self.assertEqual(parse_infobox("== Disambiguation ==\n* [[ALEX]]"), {})

    def test_blast_nickname_matches_existing_disambiguated_major_player(self):
        pool = {
            "ALEX (British player)": {
                "nickname": "ALEX",
                "majors": [{"year": 2019}],
            },
            "AdreN (Kazakh player)": {
                "nickname": "AdreN",
                "majors": [{"year": 2017}],
            },
        }
        blast = [
            {"nickname": "ALEX"},
            {"nickname": "adren"},
            {"nickname": "newPlayer"},
        ]
        self.assertEqual(unresolved_blast_titles(pool, blast), ["newPlayer"])

    def test_verified_major_result_fills_missing_upstream_placement(self):
        majors = [
            {"page": "Event/2026", "team": "Falcons", "placement": ""},
            {"page": "Event/2026", "team": "FURIA", "placement": ""},
        ]
        events = {
            "Event/2026": {
                "placements": {"falcons": "1"},
            }
        }
        corrected = apply_major_results(majors, events)
        self.assertEqual(corrected[0]["placement"], "1")
        self.assertEqual(corrected[1]["placement"], "")
        self.assertEqual(majors[0]["placement"], "")  # 不原地污染解析结果

    def test_inactive_current_team_resolves_to_free_agent(self):
        source = """
{{Infobox player
|id=nota
|team=PARIVISION
|status=Active
|roles=rifle
|team_history=
{{TH|2025-01-13 — 2026-06-19|PARIVISION}}
{{TH|2026-06-19 — '''Present'''|PARIVISION|Inactive}}
}}
"""
        infobox = parse_infobox(source)
        self.assertEqual(resolve_game_team(infobox), (
            "",
            "no_current_player_roster",
        ))

    def test_inactive_old_team_does_not_override_new_active_team(self):
        source = """
{{Infobox player
|id=BELCHONOKK
|team=TDK
|status=Active
|roles=rifle
|team_history=
{{TH|2026-06-17 — '''Present'''|PARIVISION|Inactive}}
{{TH|2026-07-17 — '''Present'''|TDK}}
}}
"""
        infobox = parse_infobox(source)
        self.assertEqual(
            [entry["team"] for entry in parse_team_history(source)],
            ["PARIVISION", "TDK"],
        )
        self.assertEqual(resolve_game_team(infobox), (
            "TDK",
            "single_current_player_roster",
        ))

    def test_head_coach_history_retains_current_team(self):
        source = """
{{Infobox player
|id=head-coach
|team=Example
|status=Active
|roles=Coach
|team_history=
{{TH|2026-01-01 — '''Present'''|Example|Coach}}
}}
"""
        self.assertEqual(resolve_game_team(parse_infobox(source)), (
            "Example",
            "single_current_head_coach_team",
        ))

    def test_non_head_staff_history_never_produces_game_team(self):
        for role in ("Assistant Coach", "Inactive Coach", "Analyst"):
            source = f"""
{{{{Infobox player
|id=staff
|team=Example
|status=Active
|roles={role}
|team_history=
{{{{TH|2026-01-01 — '''Present'''|Example|{role}}}}}
}}}}
"""
            team, reason = resolve_game_team(parse_infobox(source))
            self.assertEqual(team, "", role)
            self.assertIn(
                reason,
                {"no_current_head_coach_team", f"staff_role:{role.casefold()}"},
                role,
            )

    def test_duplicate_current_rows_for_same_team_are_not_ambiguous(self):
        source = """
{{Infobox player
|id=duplicate
|team=EYEBALLERS
|status=Active
|roles=rifle
|team_history=
{{TH|2025-01-01 — '''Present'''|EYEBALLERS}}
{{TH|2026-01-01 — '''Present'''|EYEBALLERS}}
}}
"""
        self.assertEqual(resolve_game_team(parse_infobox(source)), (
            "EYEBALLERS",
            "single_current_player_roster",
        ))

    def test_active_team_history_wins_over_top_level_inactive_status(self):
        source = """
{{Infobox player
|id=moved
|team=New Team
|status=Inactive
|roles=rifle
|team_history=
{{TH|2026-01-01 — '''Present'''|Old Team|Inactive}}
{{TH|2026-07-01 — '''Present'''|New Team}}
}}
"""
        self.assertEqual(resolve_game_team(parse_infobox(source)), (
            "New Team",
            "single_current_player_roster",
        ))

    def test_unresolved_two_team_conflict_fails_instead_of_guessing(self):
        source = """
{{Infobox player
|id=ambiguous
|status=Active
|roles=rifle
|team_history=
{{TH|2026-07-01 — '''Present'''|Team A}}
{{TH|2026-07-01 — '''Present'''|Team B}}
}}
"""
        with self.assertRaisesRegex(ValueError, "多个当前正式队伍"):
            resolve_game_team(parse_infobox(source))


if __name__ == "__main__":
    unittest.main()
