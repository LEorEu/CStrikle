# -*- coding: utf-8 -*-
"""火力打锚台。

这一页存的是**人工判断**,比任何生成物都贵——重打一遍要人重新看 75 个人。
所以测的不是渲染,是那几条会让判断悄悄丢掉或串味的事:

  - `peak` 和 `firepower` 是两个问题,不许混。只有 peak=True 的人才进拟合,
    因为只有他们的当前 rating 能代表巅峰;kennyS 的 86 是履历判断,
    把它当成「rating 1.0x 对应 86」会直接把标尺拉歪。
  - 键必须真实存在。不校验的话一个 typo 会写进永远不显示的孤儿记录,
    文件里 count 在涨、页面上一个都不多——这个项目栽过好几次这种。
  - 指挥不给建议值。实测 rating 对指挥的火力没有信号(枪手的相关随样本
    从 0.41 爬到 0.67,指挥在 0.15–0.22 原地不动),给了就是引着人填错。
"""
import json
import unittest
from unittest import mock

from bdserver import anchor as A


class HintTests(unittest.TestCase):
    def test_igl_gets_no_hint(self):
        self.assertIsNone(A.hint_for(1.04, "IGL"))
        self.assertIsNotNone(A.hint_for(1.04, "RIFLER"))

    def test_hint_never_extrapolates(self):
        """两端取端点。外推正是上一轮翻车的地方(0.127 那个折扣)。"""
        self.assertEqual(A.hint_for(0.10), A.HINT[0][1])
        self.assertEqual(A.hint_for(9.99), A.HINT[-1][1])

    def test_hint_is_monotone(self):
        vals = [A.hint_for(0.80 + i * 0.01) for i in range(71)]
        self.assertEqual(vals, sorted(vals), "建议值不单调,rating 高的人反而被建议更低")

    def test_bottom_is_compressed_not_linear(self):
        """rating 0.90 的人不是菜,他是一线队里负责别的事的那个。

        实测:五号位到哪都是 0.93–0.97,顶级赛场的底部本来就被选择压过。
        所以底部每 0.1 rating 的落差必须**小于**中段,不能线性掉下去。
        """
        def slope(a, b):
            return (A.hint_for(b) - A.hint_for(a)) / (b - a)
        bottom, middle = slope(0.83, 1.00), slope(1.00, 1.21)
        self.assertLess(bottom, middle,
                        "底部比中段还陡,0.90 的人会被压得太狠"
                        "(底 %.1f / 中 %.1f,每 1.0 rating)" % (bottom, middle))


class ViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = A.build_view(5)

    def test_only_starters_with_a_team(self):
        self.assertEqual(len(self.v["teams"]), 5)
        for t in self.v["teams"]:
            self.assertTrue(t["vrs"], t["name"])
            self.assertTrue(1 <= len(t["roster"]) <= 5, t["name"])

    def test_every_row_carries_its_evidence(self):
        """人是照着证据下判断的。证据栏空了这一页就没用了。"""
        rows = [p for t in self.v["teams"] for p in t["roster"]]
        have = [p for p in rows if p["rating"] is not None]
        self.assertGreaterEqual(len(have), len(rows) - 1,
                                "前 5 队里有人没有 rating,多半是 id 那条线断了")
        for p in rows:
            self.assertIn("card_fire", p)
            self.assertIn("seat", p)

    def test_keys_are_unique(self):
        keys = [p["key"] for t in self.v["teams"] for p in t["roster"]]
        self.assertEqual(len(keys), len(set(keys)), "键撞了,一个锚会盖掉另一个")


class WriteTests(unittest.TestCase):
    """写盘的几条。用临时文件,不碰真的人工层。"""

    def setUp(self):
        self.tmp = A.ANCHOR_PATH.with_name("firepower_anchors.test.json")
        self.patch = mock.patch.object(A, "ANCHOR_PATH", self.tmp)
        self.patch.start()
        self.key = A.build_view(3)["teams"][0]["roster"][0]["key"]

    def tearDown(self):
        self.patch.stop()
        self.tmp.unlink(missing_ok=True)
        self.tmp.with_suffix(".json.tmp").unlink(missing_ok=True)

    def test_unknown_key_is_refused(self):
        with self.assertRaises(KeyError):
            A.put("这个人不存在", True, 90, "", teams=3)
        self.assertFalse(self.tmp.exists(), "被拒的写入不该留下文件")

    def test_round_trip(self):
        A.put(self.key, True, 91, "理由", teams=3)
        got = A.load_anchors()[self.key]
        self.assertEqual(got, {"peak": True, "firepower": 91, "note": "理由"})

    def test_all_empty_removes(self):
        A.put(self.key, True, 91, "理由", teams=3)
        A.put(self.key, None, None, "", teams=3)
        self.assertNotIn(self.key, A.load_anchors())

    def test_only_peak_players_enter_the_fit(self):
        """**这一条是整页的口径。**

        非巅峰的人也可以有火力锚(那是履历判断),但他的当前 rating 和那个
        火力没有对应关系。混进拟合等于宣称「rating 1.0x 对应 86」。
        """
        rs = A.build_view(3)["teams"][0]["roster"]
        A.put(rs[0]["key"], True, 90, "巅峰中", teams=3)
        A.put(rs[1]["key"], False, 88, "生涯判断,当前不在巅峰", teams=3)
        fit = {p["nickname"] for p in A.build_view(3)["fit"]}
        self.assertIn(rs[0]["nickname"], fit)
        self.assertNotIn(rs[1]["nickname"], fit,
                         "没勾巅峰的人进了拟合——他的 rating 说明不了那个火力")

    def test_file_says_what_the_fields_mean(self):
        """人工层要能脱离这份代码被读懂。半年后打开它的人只有那段 _note。"""
        A.put(self.key, True, 91, "理由", teams=3)
        raw = json.loads(self.tmp.read_text(encoding="utf-8"))
        self.assertIn("peak", raw["_note"])
        self.assertIn("巅峰", raw["_note"])


if __name__ == "__main__":
    unittest.main()
