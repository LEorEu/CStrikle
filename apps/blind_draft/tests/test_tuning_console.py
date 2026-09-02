# -*- coding: utf-8 -*-
"""调参后台。只读地测,不碰 data/ 里的任何文件。

盯着两件事:

1. **`_trace` 说的和卡上的数必须是同一个数。** 后台整个卖点就是「页面显示的
   就是引擎读的那份」。一旦推导展示和最终值能对不上,这个后台就从「看清楚
   算法」退化成「看一个好看的假象」,而且不会有任何报错。

2. **人工层的元数据不许上卡。** `build_card` 以前是 `card.update(ov)`,于是
   override 里的 reason 会并进卡、再被卡带进 AI 名单和导出的网页——只有
   肉眼看 JSON 才发现得了。
"""
import unittest

from fastapi.testclient import TestClient

from blinddraft import cards as C
from bdserver import main as A


class TraceTests(unittest.TestCase):
    """`build_card(trace=True)` 的推导要和它自己算出来的卡一致。"""

    @classmethod
    def setUpClass(cls):
        cls.cards, cls.pending, cls.confirmed = C.generate(trace=True)

    def test_trace_final_matches_card(self):
        for c in self.cards:
            for key in C.ATTRS:
                self.assertEqual(
                    c["_trace"]["attrs"][key]["final"], c[key],
                    "%s 的 %s:推导说 %s,卡上是 %s" % (
                        c["page"], key, c["_trace"]["attrs"][key]["final"], c[key]))

    def test_trace_steps_add_up(self):
        """模板 + 履历 + 抖动 = 自动值(取整、并夹在 1..99)。"""
        for c in self.cards:
            for key in C.ATTRS:
                a = c["_trace"]["attrs"][key]
                want = max(1, min(99, round(a["base"] + a["delta"] + a["jitter"])))
                self.assertEqual(a["auto"], want,
                                 "%s 的 %s 三段加不回自动值" % (c["page"], key))

    def test_no_metadata_leaks_onto_cards(self):
        for c in self.cards:
            for junk in ("reason", "draft_exclude", "_note"):
                self.assertNotIn(junk, c,
                                 "%s:人工层的 %s 漏到卡上了" % (c["page"], junk))

    def test_generate_without_trace_is_clean(self):
        """不要 trace 时不许留痕——它绝不能进 draft_cards.json。"""
        cards, _, _ = C.generate()
        self.assertTrue(all("_trace" not in c for c in cards))


class OverrideValidationTests(unittest.TestCase):
    """人工层的入口校验。§21:算法算错了才覆盖,而且要留下为什么。"""

    def body(self, **kw):
        return A.OverrideBody(**kw)

    def test_reason_is_required(self):
        with self.assertRaises(Exception):
            A._clean(self.body(firepower=95))

    def test_empty_body_clears_override(self):
        self.assertEqual(A._clean(self.body()), {})

    def test_range_and_enum_are_enforced(self):
        for bad in (self.body(firepower=200, reason="x"),
                    self.body(firepower=0, reason="x"),
                    self.body(grade=9, reason="x"),
                    self.body(position="SNIPER", reason="x")):
            with self.assertRaises(Exception):
                A._clean(bad)

    def test_exclude_drops_the_numbers(self):
        """排除出卡池的人没有数值可言,别把一组孤儿数字留在文件里。"""
        out = A._clean(self.body(draft_exclude=True, firepower=95, reason="教练"))
        self.assertEqual(out, {"draft_exclude": True, "reason": "教练"})


class DiffTests(unittest.TestCase):
    def test_removed_card_explains_itself(self):
        """「消失」必须给出原因,否则没法判断该不该发布。"""
        cards = [{"page": "A", "nickname": "a", "firepower": 1, "leadership": 1,
                  "experience": 1, "stability": 1, "grade": 1,
                  "position": "RIFLER", "overall": 1.0}]
        real = A.published
        A.published = lambda: {"A": cards[0],
                               "B": dict(cards[0], page="B", nickname="b")}
        try:
            out = {d["nickname"]: d for d in
                   A.diff_against_published(cards, pending=["b"], confirmed=[])}
        finally:
            A.published = real
        self.assertEqual(out["b"]["kind"], "removed")
        self.assertIn("待定", out["b"]["why"])


class ApiSmokeTests(unittest.TestCase):
    """只打只读接口。写接口会落到真的 data/blind_draft/draft_overrides.json。"""

    def test_cards_endpoint(self):
        r = TestClient(A.app).get("/api/cards")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["cards"])
        self.assertEqual(d["card_version"], C.CARD_VERSION)
        one = d["cards"][0]
        for key in ("photo", "flag", "override", "_trace"):
            self.assertIn(key, one)
        for bucket in ("position", "grade"):
            self.assertTrue(d["stats"][bucket])

    def test_play_page_and_run_endpoint(self):
        client = TestClient(A.app)
        page = client.get("/play")
        self.assertEqual(page.status_code, 200)
        self.assertIn("开始 Run", page.text)
        cards = C.generate()[0]
        # 用最强的五张确保能取得席位；阵容合法性在 Match 内通过软惩罚表达。
        picked = sorted(cards, key=lambda c: -c["overall"])[:5]
        run = client.post("/api/run", json={
            "pages": [c["page"] for c in picked], "seed": 7})
        self.assertEqual(run.status_code, 200)
        self.assertGreaterEqual(len(run.json()["legs"]), 3)
        self.assertTrue(run.json()["stages"])


if __name__ == "__main__":
    unittest.main()
