# -*- coding: utf-8 -*-
"""网页算的 Entry 必须和 `/api/run` 返回的那个数逐分一致。

选人页在浏览器里就要给出「这是支什么队」，而同一支队的 Entry 会在下一屏由
Python 再算一遍（`run.entry`）。两处各写一份公式，就会出现同一个名字两个数
——实测过一次：揭晓页写「纸面火力 78.3」，Run 页写「你 81.8」，差的 3.5 正
好是玩家队的磨合度，页面上没有任何东西解释这 3.5 是什么。

所以系数全部由 `export_web` 从 `engine` 注入（`D.engine`），JS 里的
`entryOf()` 和 Python 的 `entry_of(roster, player_cohesion(roster))` 是同一
条式子的两次书写，这个测试把它们对齐到小数点后 9 位。没装 node 就跳过。
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
from blinddraft import engine as V2
from bdtools.export_web import render_html

NODE = shutil.which("node")

# (正则, 是否跨行)。渲染之后 /*__DATA__*/ 已经换成一整行 JSON，取单行常量时
# 不能开 DOTALL，否则 `.` 会一路吃到文件末尾。
WANT = ((r"^const D = .*$", False),
        (r"^const CARDS = .*$", False),
        (r"^const ENG=.*$", False),
        (r"^const PAIR=new Map.*?^\}$", True),
        (r"^const mean=.*$", False),
        (r"^function chemistry\(r\)\{.*?^\}$", True),
        (r"^const cohesionOf=.*$", False),
        (r"^function fireAgg\(r\)\{.*$", False),
        (r"^const noAwpOf=.*$", False),
        (r"^function entryOf\(r\)\{.*$", False))

# 随机抽的阵容里只有约 1.4% 的裸默契会超过封顶，靠运气覆盖不到——而封顶正好
# 是两边最容易错开的一处（一边按 9 显示、一边按 4 打）。所以钉死几支。
# 写的是 page（卡的主键），不是 nickname——两者大小写可以不一样（Sh1ro / sh1ro）。
CAPPED = (["Sh1ro", "ImoRR", "Magixx", "DemQQ", "Woxic"],          # 裸默契 9.0
          ["GuardiaN", "ZehN", "NBK-", "Daps", "KioShiMa"],        # 6.5
          ["JW", "Spiidi", "Desi", "Rallen", "Olofmeister"])       # 6.5

# 整个 bundle 带着 648 张卡的 JSON，塞不进 Windows 的命令行长度限制，
# 所以脚本和用例都落成临时文件再让 node 读。
HARNESS = """
const fs = require("fs");
const byPage = new Map(CARDS.map(c => [String(c.id), c]));
const cases = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
console.log(JSON.stringify(cases.map(pages => {
  const r = pages.map(p => byPage.get(String(p)));
  return [entryOf(r), fireAgg(r), cohesionOf(r), chemistry(r)];
})));
"""


@unittest.skipUnless(NODE, "没装 node，跳过网页与 Python 的对齐检查")
class WebEntryMatchesPython(unittest.TestCase):
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
        cases = [list(team) for team in CAPPED]
        cases += [[c["page"] for c in rng.sample(self.cards, P.SLOTS)]
                  for _ in range(40)]

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

        cap = P.cohesion_cap()
        for pages, (js_entry, js_fire, js_coh, js_chem) in zip(
                cases, json.loads(res.stdout)):
            roster = [by_page[p] for p in pages]
            who = "、".join(c["nickname"] for c in roster)
            coh = V2.player_cohesion(roster)
            entry = V2.entry_of(roster, coh)
            if pages in [list(team) for team in CAPPED]:
                self.assertGreater(js_chem, cap, "%s 这支本该触发封顶" % who)
            self.assertAlmostEqual(
                coh, js_coh, places=9,
                msg="磨合度对不上：Python %.6f，JS %.6f；阵容 %s" % (coh, js_coh, who))
            self.assertAlmostEqual(
                entry, js_entry, places=9,
                msg="Entry 对不上：Python %.6f，JS %.6f；阵容 %s"
                    % (entry, js_entry, who))
            # 火力聚合单拎出来对一次：Entry 相等但两项互相抵消的情况骗不过去
            self.assertAlmostEqual(
                V2.entry_of(roster) - (V2.NO_AWP_PENALTY if not any(
                    c["position"] == "AWPER" for c in roster) else 0.0),
                js_fire, places=9, msg="火力聚合对不上；阵容 %s" % who)

    def test_the_engine_constants_are_injected_not_hardcoded(self):
        """JS 里不许再出现写死的引擎系数——那正是以前会错开的原因。"""
        body = self._js_bundle()
        for banned in ("*.35", "*.25", "-=4", "v-=4", "*.40"):
            self.assertNotIn(banned, body, "JS 又把引擎系数写死了：%s" % banned)
        d = json.loads(re.search(r"^const D = (\{.*\});$", self.html, re.M).group(1))
        eng = d["engine"]
        self.assertEqual(tuple(eng["star"]), V2.STAR_WEIGHTS)
        self.assertEqual(eng["restWeight"], V2.REST_WEIGHT)
        self.assertEqual(eng["noAwp"], V2.NO_AWP_PENALTY)
        self.assertEqual(eng["noIgl"], V2.NO_IGL_TACTICAL)
        self.assertEqual(eng["clamp"], V2.TACTICAL_CLAMP)
        self.assertEqual(eng["cohesionCap"], P.cohesion_cap())


if __name__ == "__main__":
    unittest.main()
