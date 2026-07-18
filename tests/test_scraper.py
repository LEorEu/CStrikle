import unittest

from scraper.build_db import parse_infobox, unresolved_blast_titles
from server.major_results import apply_major_results


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


if __name__ == "__main__":
    unittest.main()
