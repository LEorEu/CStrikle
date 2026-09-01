# -*- coding: utf-8 -*-
"""AI 对手页装配的数据。只读,不写任何文件。

这一页把三列摆在一起(卡面 / 现况 / 5E 实测),而它的价值全在于**三列各自
是什么、差在哪能说清楚**。所以测的不是"渲染出来了",是:

  - 现况和卡面不一样的地方,必须有一条改动说明兜着。没有说明的差值意味着
    有一条没人记得的规则在改数,而这一页正是拿来找那种规则的。
  - 占位新秀不许伪装成真人:它在卡库里没有对应的人,那一列就该是空的,
    不能拿现况去填——两列一样会看起来像个结论。
"""
import unittest

from blinddraft import cards as C
from bdserver import ai


class ViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = ai.build_view()

    def test_field_shape(self):
        self.assertEqual(len(self.v["teams"]), 32)
        for t in self.v["teams"]:
            self.assertEqual(len(t["roster"]), 5, t["name"])

    def test_our_order_is_dense(self):
        self.assertEqual([t["our"] for t in self.v["teams"]],
                         list(range(1, len(self.v["teams"]) + 1)))

    def test_delta_is_within_the_field(self):
        """顺位分歧要在同一批队里算。

        HLTV 的名次是全球 1..100,这个赛场只取了其中 32 支;直接拿全球名次
        做差会被中间跳过的队污染,分歧看起来永远偏大。
        """
        n = len(self.v["teams"])
        orders = sorted(t["hltv_order"] for t in self.v["teams"])
        self.assertEqual(orders, list(range(1, n + 1)))
        for t in self.v["teams"]:
            self.assertEqual(t["delta"], t["hltv_order"] - t["our"])

    def test_every_change_has_a_note(self):
        for t in self.v["teams"]:
            for p in t["roster"]:
                if not p["card"]:
                    continue
                changed = [k for k in C.ATTRS if p["cur"][k] != p["card"][k]]
                if changed:
                    self.assertTrue(
                        p["notes"],
                        "%s 的 %s 变了(%s)却没有任何说明——有一条没人记得的"
                        "规则在改数" % (t["name"], p["nickname"], changed))

    def test_position_changes_are_declared(self):
        """位置改判要换整套模板,所以它必须写进改动说明。"""
        for t in self.v["teams"]:
            for p in t["roster"]:
                if p["card"] and p["position"] != p["card"]["position"]:
                    self.assertTrue(any("位置" in s for s in p["notes"]),
                                    "%s 的位置改判没写进说明" % p["nickname"])

    def test_filler_has_no_career_card(self):
        fillers = [p for t in self.v["teams"] for p in t["roster"] if p["filler"]]
        self.assertTrue(fillers, "赛场上一个占位都没有?那这条断言就白写了")
        for p in fillers:
            self.assertIsNone(p["card"])
            self.assertIsNone(p["stat"])
            self.assertEqual(p["grade"], 1)      # G1 = 「我们对他一无所知」

    def test_real_players_are_covered_by_5e(self):
        """非占位的人应该全都查得到 5E 数据。

        查不到不一定是 bug(5E 那边确实有极少数人没样本),但数量一旦变大就说明
        名字匹配那条线断了,而它断掉的表现只是数据悄悄变空。
        """
        miss = [p["nickname"] for t in self.v["teams"] for p in t["roster"]
                if not p["filler"] and not p["stat"]]
        self.assertLessEqual(len(miss), 5, "查不到 5E 数据的人太多了:%s" % miss)

    def test_missing_snapshot_team_is_flagged_not_silently_blank(self):
        """5eplay 快照里没有的队要标出来,否则页面上只表现为「队标图挂了」。"""
        for t in self.v["teams"]:
            if not t["in_5e"]:
                self.assertEqual(t["logo"], "")

    def test_photo_paths_are_servable(self):
        for t in self.v["teams"]:
            for p in t["roster"]:
                if p["photo"]:
                    self.assertTrue(p["photo"].startswith(("/bd/img/", "/img/")),
                                    p["photo"])


class SpearmanTests(unittest.TestCase):
    def test_known_values(self):
        self.assertEqual(ai._spearman([(1, 1), (2, 2), (3, 3), (4, 4)]), 1.0)
        self.assertEqual(ai._spearman([(1, 4), (2, 3), (3, 2), (4, 1)]), -1.0)
        self.assertEqual(ai._spearman([(1, 1)]), 0.0)     # 样本不够就别给数


if __name__ == "__main__":
    unittest.main()
