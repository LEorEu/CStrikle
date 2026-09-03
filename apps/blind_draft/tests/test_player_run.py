# -*- coding: utf-8 -*-
"""`/api/run` 这条线：网页提交五个 page，Python 跑完一整届并返回可序列化的 JSON。

这个文件原来叫 `test_match_quick.py`，盯的是 v1 的 `--quick-run`（固定三场、
对手取 Entry 最接近的三支）。v1 已退役删除，`--quick-run` 想回答的
「四维有没有存在感」现在由 `proto_match_v2 --lab` 的六项验收回答，胜率锚由
`--duel` 实测。剩下这一条是别处都没有的：**后台这个 HTTP 入口本身**。
"""
import json
import unittest

from blinddraft import draft as P
from blinddraft import major as M
from blinddraft import proto_match_v2 as V2
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


if __name__ == "__main__":
    unittest.main()
