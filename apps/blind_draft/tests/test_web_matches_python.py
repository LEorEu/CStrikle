# -*- coding: utf-8 -*-
"""网页算的阵容分必须和 Python 逐分一致。

选人页在浏览器里算分（散场那页要枚举成千上万种替代阵容，来回请求服务端不
现实），所以 `templates/draft_web.html` 里有一份 JS 实现。以前它和
`draft.score()` 是**两边各抄一遍公式**——`.35/.25/.40`、无狙 −4 都写死在 JS
里，引擎一改就静默错开，而且错开的正好是「你本可以选谁」那个数。

现在系数全部由 `export_web` 从 `proto_match_v2` 注入（`D.engine`），这个测试
再把两边跑同一批阵容对齐到小数点后 9 位。没装 node 就跳过。
"""
import io
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import unittest

from blinddraft import draft as P
from bdtools.export_web import render_html

NODE = shutil.which("node")

# (正则, 是否跨行)。渲染之后 /*__DATA__*/ 已经换成一整行 JSON，取单行常量时
# 不能开 DOTALL，否则 `.` 会一路吃到文件末尾。
WANT = ((r"^const D = .*$", False),
        (r"^const CARDS = .*$", False),
        (r"^const BUDGET = .*$", False),
        (r"^const RATE = .*$", False),
        (r"^const ENG = .*$", False),
        (r"^const PAIR = new Map.*?^\}$", True),
        (r"^const mean = .*$", False),
        (r"^function chemistry\(r\)\{.*?^\}$", True),
        (r"^function carryWeights\(n\)\{.*?^\}$", True),
        (r"^function tactical\(r\)\{.*?^\}$", True),
        (r"^function sigma\(stab.*?^\}$", True),
        (r"^function score\(r, money\)\{.*?^\}$", True))

FIELDS = ("total", "fire", "chem", "cohesion", "tactical",
          "swing_down", "swing_up")
JS_FIELDS = ("total", "fire", "chem", "cohesion", "tactical",
             "swingDown", "swingUp")

# 随机抽 40 支阵容里只有约 1.4% 的裸默契会超过封顶，靠运气覆盖不到——而这
# 正好是两边最容易错开的一处（一边按 9 显示、一边按 4 打）。所以钉死几支。
CAPPED = (["Sh1ro", "ImoRR", "Magixx", "DemQQ", "Woxic"],          # 裸默契 9.0
          ["GuardiaN", "ZehN", "NBK-", "Daps", "KioShiMa"],        # 6.5
          ["JW", "Spiidi", "Desi", "Rallen", "Olofmeister"])       # 6.5

# 整个 bundle 带着 648 张卡的 JSON，塞不进 Windows 的命令行长度限制，
# 所以脚本和用例都落成临时文件再让 node 读。
HARNESS = """
const fs = require("fs");
const byPage = new Map(CARDS.map(c => [String(c.id), c]));
const cases = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
console.log(JSON.stringify(cases.map(([pages, money]) => {
  const s = score(pages.map(p => byPage.get(String(p))), money);
  return [s.total, s.fire, s.chem, s.cohesion, s.tactical,
          s.swingDown, s.swingUp];
})));
"""


@unittest.skipUnless(NODE, "没装 node，跳过网页与 Python 的对齐检查")
class WebScoreMatchesPython(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render_html()[0]
        cls.cards = P.load_cards()
        cls.rosters = P.load_rosters()

    def _js_bundle(self):
        out = []
        for pat, dotall in WANT:
            m = re.search(pat, self.html, re.M | (re.S if dotall else 0))
            self.assertIsNotNone(m, "模板里找不到 %s；改了名字就要同步这里" % pat)
            out.append(m.group(0) + "\n")
        return "".join(out)

    def test_the_two_implementations_agree_to_nine_places(self):
        rng = random.Random(20260904)
        by_page = {c["page"]: c for c in self.cards}
        cases = [(list(pages), money)
                 for pages in CAPPED for money in (0, 4)]
        cases += [([c["page"] for c in rng.sample(self.cards, P.SLOTS)],
                   rng.randint(0, 6)) for _ in range(40)]

        with tempfile.TemporaryDirectory() as tmp:
            js_path = os.path.join(tmp, "bundle.js")
            arg_path = os.path.join(tmp, "cases.json")
            with io.open(js_path, "w", encoding="utf-8") as fh:
                fh.write(self._js_bundle() + HARNESS)
            with io.open(arg_path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(cases))
            res = subprocess.run([NODE, js_path, arg_path], capture_output=True,
                                 text=True, encoding="utf-8")
        self.assertEqual(res.returncode, 0, res.stderr)

        for (pages, money), row in zip(cases, json.loads(res.stdout)):
            roster = [by_page[p] for p in pages]
            s = P.score(roster, self.rosters, money)
            if pages in [list(x) for x in CAPPED]:
                self.assertTrue(s["capped"], "这几支本该触发封顶")
            for key, jkey, got in zip(FIELDS, JS_FIELDS, row):
                self.assertAlmostEqual(
                    s[key], got, places=9,
                    msg="%s / %s 对不上：Python %.6f，JS %.6f；阵容 %s，余钱 %d"
                        % (key, jkey, s[key], got,
                           "、".join(c["nickname"] for c in roster), money))

    def test_the_engine_constants_are_injected_not_hardcoded(self):
        """JS 里不许再出现写死的引擎系数——那正是以前会错开的原因。"""
        from blinddraft import proto_match_v2 as V2
        body = self._js_bundle()
        for banned in ("*.35", "*.25", "base -= 4", "fire*.40"):
            self.assertNotIn(banned, body, "JS 又把引擎系数写死了：%s" % banned)
        d = json.loads(re.search(r"^const D = (\{.*\});$", self.html, re.M).group(1))
        eng = d["engine"]
        self.assertEqual(tuple(eng["star"]), V2.STAR_WEIGHTS)
        self.assertEqual(eng["restWeight"], V2.REST_WEIGHT)
        self.assertEqual(eng["noAwp"], V2.NO_AWP_PENALTY)
        self.assertEqual(eng["noIgl"], V2.NO_IGL_TACTICAL)
        self.assertEqual(eng["clamp"], V2.TACTICAL_CLAMP)


if __name__ == "__main__":
    unittest.main()
