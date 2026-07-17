import unittest

from scraper.build_db import parse_infobox, unresolved_blast_titles


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


if __name__ == "__main__":
    unittest.main()
