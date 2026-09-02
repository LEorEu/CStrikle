# -*- coding: utf-8 -*-
"""AI 对手页装配的数据。只读,不写任何文件。

这一页把三列摆在一起(卡面 / 现况 / 5E 实测),而它的价值全在于**三列各自
是什么、差在哪能说清楚**。所以测的不是"渲染出来了",是:

  - 现况和卡面不一样的地方,必须有一条改动说明兜着。没有说明的差值意味着
    有一条没人记得的规则在改数,而这一页正是拿来找那种规则的。
  - 卡库里没有的人不许被填成有:那一整块留白是**结论本身**——当前世界装得下
    生涯世界没有的人,而四维的映射还没做。以前这里补的是 G1 占位卡,
    等于把 The MongolZ 的三个真人换成三个虚构的人。
  - 名额、余量、entry 算不算得动,这几件事必须分得开。
"""
import unittest

from blinddraft import cards as C
from blinddraft import major as M
from bdserver import ai


class ConfigTests(unittest.TestCase):
    """人工层必须真的被读到。

    仓库改组时 `CONFIG_PATH` 还指着搬走之前的 data/manual/,而 `load_config`
    把 IOError 咽掉、静默退回默认值——整个 teams 段(adjust / caller / max_filler)
    和 regional_slots、candidate_pool 全部失效,页面却照常渲染。
    「读到的是不存在的路径,表现为数据是空的而不是报错」正是
    packages/playerdb/paths.py 开头警告的那种错法,所以钉一条断言在这里。
    """

    def test_config_file_is_actually_read(self):
        cfg = M.load_config()
        self.assertTrue(cfg.get("teams"),
                        "major_field.json 没读到——CONFIG_PATH 又指错了?")
        self.assertIn("regional_slots", cfg)
        self.assertIn("candidate_pool", cfg)

    def test_slots_add_up_to_a_major(self):
        s = M.load_config()["regional_slots"]
        self.assertEqual(sum(v["stage1"] for v in s.values()), 16)
        self.assertEqual(sum(v["stage2"] for v in s.values()), 8)
        self.assertEqual(sum(v["stage3"] for v in s.values()), 8)


class ViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = ai.build_view()

    def test_pool_is_bigger_than_the_field(self):
        """候选池要比名额多。多出来的是余量,不是能上场的队。"""
        teams = self.v["teams"]
        seats = sum(v["stage1"] + v["stage2"] + v["stage3"]
                    for v in M.load_config()["regional_slots"].values())
        picked = [t for t in teams if t["stage"]]
        self.assertEqual(len(picked), seats)
        self.assertGreater(len(teams), seats, "候选池没有余量,VRS 一动就得重抓")

    def test_roster_comes_from_the_snapshot(self):
        """首发人数以队伍快照为准。不满五人就是不满,不补人。"""
        for t in self.v["teams"]:
            self.assertTrue(1 <= len(t["roster"]) <= 5, t["name"])
            self.assertTrue(t["region"], t["name"])
            self.assertTrue(t["seat"], t["name"])

    def test_our_order_is_dense_among_scored_teams(self):
        """entry 只在五人全有卡的队上算得动,那些队之间的顺位要连续。

        算不动的队 our 必须是 None——**不能给一个残缺的名次**,
        那会让它和别人排在一起,看起来像可比的。
        """
        got = sorted(t["our"] for t in self.v["teams"] if t["our"] is not None)
        self.assertEqual(got, list(range(1, self.v["scored"] + 1)))
        for t in self.v["teams"]:
            if t["our"] is None:
                self.assertIsNone(t["entry"])
                self.assertIsNone(t["delta"])
            else:
                self.assertEqual(t["real"], 5)

    def test_delta_is_within_the_scored_subset(self):
        """顺位分歧要在同一批队里算。

        HLTV 的名次是全球 1..100,这里只取了其中一部分;直接拿全球名次做差
        会被中间跳过的队污染,分歧看起来永远偏大。
        """
        scored = [t for t in self.v["teams"] if t["our"] is not None]
        orders = sorted(t["hltv_order"] for t in scored if t["hltv_order"])
        self.assertEqual(orders, list(range(1, len(orders) + 1)))
        for t in scored:
            if t["hltv_order"]:
                self.assertEqual(t["delta"], t["hltv_order"] - t["our"])

    def test_every_change_has_a_note(self):
        for t in self.v["teams"]:
            for p in t["roster"]:
                if not p["card"] or not p["cur"]:
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

    def test_nocard_players_are_blank_not_invented(self):
        """卡库里没有的人:卡面和现况两块都必须是空的。

        以前这里补 G1 占位卡,那等于宣称"我们知道他有多强,他很弱"。
        实际情况是"我们对他的生涯一无所知,但知道他现在打得怎么样"——
        所以左边留白、右边有数,才是这一页要表达的东西。
        """
        nc = [p for t in self.v["teams"] for p in t["roster"] if p["nocard"]]
        self.assertTrue(nc, "一个卡库外的人都没有?候选池怕是没接上快照")
        for p in nc:
            self.assertIsNone(p["card"])
            self.assertIsNone(p["cur"])
            self.assertIsNone(p["grade"])
            self.assertIsNone(p["page"])

    def test_nocard_players_still_have_evidence(self):
        """他们进来的**理由**就是右边那一列。全空的话这一页白扩。"""
        nc = [p for t in self.v["teams"] for p in t["roster"] if p["nocard"]]
        have = [p for p in nc if p["stat"]]
        self.assertGreaterEqual(len(have), len(nc) - 5,
                                "卡库外的人大批没有 5E 数据,那扩池就没意义了")

    def test_everyone_is_covered_by_5e(self):
        """查不到 5E 数据的人要极少。

        查不到不一定是 bug(确实有人没样本),但数量一旦变大就说明 id 那条线
        断了,而它断掉的表现只是数据悄悄变空——bLitz 就这么丢过一次。
        """
        miss = [p["nickname"] for t in self.v["teams"] for p in t["roster"]
                if not p["stat"]]
        self.assertLessEqual(len(miss), 5, "查不到 5E 数据的人太多了:%s" % miss)

    def test_low_tier_rows_are_labelled(self):
        """折算过的 rating 必须自报家门,不能和实测混在一起。"""
        for t in self.v["teams"]:
            for p in t["roster"]:
                s = p["stat"]
                if s and s["tier"] == "all":
                    self.assertIsNotNone(s["conv"], p["nickname"])

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
