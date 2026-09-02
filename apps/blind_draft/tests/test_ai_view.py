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
        """他们进来的**理由**就是右边那一列。大部分全空的话这一页白扩。

        门槛从「最多缺 5 个」放宽到「至少七成」,因为口径收紧了:删掉低等级
        兜底之后,「没有行」是一个正当结论(他这一年真的没打过 Major/S+/S),
        不再是抓取失败。卡库外的人恰恰最容易落在这一类。
        """
        nc = [p for t in self.v["teams"] for p in t["roster"] if p["nocard"]]
        have = [p for p in nc if p["stat"]]
        self.assertGreaterEqual(len(have), 0.7 * len(nc),
                                "卡库外的人大批没有 S 级样本(%d/%d),那扩池就没意义了"
                                % (len(have), len(nc)))

    def test_top_teams_are_fully_covered(self):
        """**全球 VRS 前 10 的队,首发必须人人有数。**

        这条是 id 那条线的哨兵:id 对错了的表现不是报错,是数据悄悄变空——
        bLitz 就这么丢过一次(BL1TZ / bLitz 撞了 leet 归一)。

        为什么只盯前 10:口径收紧到只认 Major/S+/S 之后,「查不到」对中下游
        队伍是**正常结论**(整池 92%、名额内 96%、50 名开外只有 64%)。
        拿全池覆盖率当断言,就是把一个真实的空当成故障;而前 10 的队一年里
        不可能一场顶级赛事都没打,那里一旦出现空白,一定是我们这边断了。
        """
        miss = [(t["name"], p["nickname"]) for t in self.v["teams"]
                for p in t["roster"] if not p["stat"] and (t["vrs"] or 9999) <= 10]
        self.assertEqual(miss, [], "前 10 队里有人查不到 S 级数据,多半是 id 断了:%s" % miss)

    def test_every_row_is_top_tier(self):
        """页面上出现的每一个数,都必须来自 Major/S+/S。

        曾经有一条兜底:查不到 S 级样本就退一档查全等级、减掉一个折扣当作
        S 级口径。它错在源头——5eplay 的 `grade: []` 不是「所有赛事等级」而是
        「完全不筛」,会把网页上根本不显示的那一档也算进来。Ax1Le 这一年
        S 级 0 图,却被记成 252 图 / rating 1.23(其中 155 图来自那一档)。

        错的形状是「一个看着像实测的数字」,比缺数据危险得多——**留白是结论,
        折算不是**。所以这里钉死:没有 tier 之外的行。
        """
        seen = {p["stat"]["tier"] for t in self.v["teams"] for p in t["roster"]
                if p["stat"]}
        self.assertEqual(seen, {"S"}, "混进了非 S 级口径的行:%s" % (seen - {"S"}))

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
