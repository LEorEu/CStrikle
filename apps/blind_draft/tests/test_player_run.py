# -*- coding: utf-8 -*-
"""`/api/run` 这条线：网页提交五个 page，Python 跑完一整届并返回可序列化的 JSON。

这个文件原来叫 `test_match_quick.py`，盯的是 v1 的 `--quick-run`（固定三场、
对手取 Entry 最接近的三支）。v1 已退役删除，`--quick-run` 想回答的
「四维有没有存在感」现在由 `engine --lab` 的六项验收回答，胜率锚由
`--duel` 实测。剩下这一条是别处都没有的：**后台这个 HTTP 入口本身**。
"""
import json
import unittest

from blinddraft import draft as P
from blinddraft import major as M
from blinddraft import engine as V2
from bdserver import run as R


class PlayerRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rosters = P.load_rosters()
        cards = P.load_cards()
        mates = P.mate_index(cls.rosters)
        cls.roster, _left = M.bot_draft(50296, cards, cls.rosters, mates)

    def test_web_payload_is_structured_and_serializable(self):
        data = R.build_run([c["page"] for c in self.roster], seed=50296)
        self.assertTrue(data["qualified"])
        self.assertGreaterEqual(len(data["legs"]), 3)
        self.assertTrue(data["stages"])
        self.assertIn(data["outcome"], ("eliminated", "playoffs"))
        self.assertTrue(all(x["maps"] for x in data["legs"]))
        json.dumps(data, ensure_ascii=False)       # FastAPI 必须能直接序列化

    def test_build_run_is_a_thin_wrapper_over_player_run(self):
        """后台不许自己再算一遍比赛——同样的输入必须逐字段等于引擎的输出。"""
        pages = [c["page"] for c in self.roster]
        self.assertEqual(R.build_run(pages, seed=7),
                         V2.player_run(pages=pages, seed=7))

    def test_a_bad_roster_is_rejected_before_the_engine_runs(self):
        pages = [c["page"] for c in self.roster]
        with self.assertRaises(ValueError):
            R.build_run(pages[:4], seed=1)
        with self.assertRaises(ValueError):
            R.build_run(pages[:4] + pages[:1], seed=1)     # 有重复
        with self.assertRaises(KeyError):
            R.build_run(pages[:4] + ["NoSuchPlayer"], seed=1)


class OneRulerTests(unittest.TestCase):
    """散场那页给的分，必须就是引擎真正用来打这张图的分。

    以前 `draft.score()` 是 `火力40% + 指挥20% + 经验20% + 稳定20%`，而 v0.3
    §4.1 之后引擎只认纯火力 + 战术执行 + 磨合。于是 Reveal 会说「选 A 比选 B
    好 2 分」，引擎却不按这个数打——后悔值和实际后果是脱节的。
    """

    @classmethod
    def setUpClass(cls):
        cls.rosters = P.load_rosters()
        cards = P.load_cards()
        mates = P.mate_index(cls.rosters)
        cls.rosters_sample = [M.bot_draft(seed, cards, cls.rosters, mates)[0]
                              for seed in (7, 50296, 156515, 4242)]
        # 随机阵容几乎碰不到磨合度封顶，而那正是两把尺子最容易错开的地方
        by_page = {c["page"]: c for c in cards}
        cls.capped = [by_page[p] for p in
                      ("Sh1ro", "ImoRR", "Magixx", "DemQQ", "Woxic")]
        cls.rosters_sample.append(cls.capped)

    def test_the_reveal_score_is_the_engine_ruler(self):
        for roster in self.rosters_sample:
            s = P.score(roster, self.rosters)
            team = V2.Team("x", roster, V2.player_cohesion(roster))
            self.assertAlmostEqual(s["total"], team.entry() + team.tactical,
                                   places=9)

    def test_the_cap_applies_on_both_sides_of_the_ruler(self):
        """裸默契 9 分的阵容，页面和引擎都必须按封顶后的 4 算。"""
        cap = P.cohesion_cap()
        s = P.score(self.capped, self.rosters)
        self.assertGreater(s["chem"], cap)
        self.assertTrue(s["capped"])
        self.assertAlmostEqual(s["cohesion"], cap, places=9)
        team = V2.Team("x", self.capped, V2.player_cohesion(self.capped))
        self.assertAlmostEqual(s["total"], team.entry() + team.tactical,
                               places=9)

    def test_leadership_reaches_the_score_only_through_tactical(self):
        """改领导力只能通过 tactical 影响总分，不许有第二条路。"""
        roster = self.rosters_sample[1]
        moved = [dict(c, experience=95, stability=95) for c in roster]
        self.assertAlmostEqual(P.score(roster, self.rosters)["total"],
                               P.score(moved, self.rosters)["total"], places=9)

    def test_chemistry_actually_reaches_the_match(self):
        """默契不能只印在选人页上。

        `player_run` 曾经把玩家的磨合度写死成 0，而 AI 一律吃满 cap——追一对
        真队友和不追，打出来一模一样。
        """
        cap = float(M.load_config().get("cohesion_cap", M.COHESION_CAP))
        got = [V2.player_cohesion(r) for r in self.rosters_sample]
        self.assertTrue(any(abs(x) > 1e-9 for x in got),
                        "所有样本阵容的磨合度都是 0，默契没进比赛")
        for x in got:
            self.assertLessEqual(x, cap + 1e-9)
        # 而且 Run 里那支队用的就是这个数
        roster = self.rosters_sample[1]
        d = R.build_run([c["page"] for c in roster], seed=1)
        team = V2.Team("x", roster, V2.player_cohesion(roster))
        self.assertAlmostEqual(d["entry"], round(team.entry(), 1), places=6)


if __name__ == "__main__":
    unittest.main()
