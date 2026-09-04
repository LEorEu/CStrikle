# -*- coding: utf-8 -*-
"""`web/` 那个转播前端**只是外壳**,不许再长回第二个游戏。

这个仓库为「同一件事两份实现」付过一次代价:`web/src/game/engine.ts` 曾经是
578 行独立比赛引擎 + 78 张虚构选手卡,赛制、队伍维度、阵容加成和后端全不一样,
而且没有任何东西拦着有人照着它改数值。接线时那两个文件删掉了,这里盯着它们
别回来,也盯着新的外壳不要偷偷把公式抄进 TS。

盯三条:

1. 退役的两个文件不许复活;
2. 玩法数据只能从 `/api/draft` 和 `/api/run` 来——外壳里不许出现别的接口;
3. 引擎系数不许出现在 TS 里(和 `test_web_matches_python.py` 对老页面的那条
   同一个理由:抄一份常量,引擎一改就静默错开)。

`playByPlay.ts` 是**表演层**,允许有自己的数(把 margin 映射成比分的斜率、
一个回合几个人头)。它们不参与任何判定,删掉这个文件比赛结果一分不变。
所以第 3 条只禁引擎那几个系数,不禁「TS 里出现任何数字」。
"""
import re
import unittest

from playerdb.paths import ROOT

WEB = ROOT / "apps" / "blind_draft" / "web" / "src"

#: 接完线就该消失的两个文件。
RETIRED = ("game/engine.ts", "data/players.ts")

#: 外壳允许调的接口。多一个就说明玩法在别处又开了一个口子。
#:
#: `/api/showcase` 是首页橱窗那几张翻开的牌,它**不是玩法**:不属于任何一局、
#: 不进 Dealer、不受 seed 影响,给出来的身份也不参与任何判定。它在这张名单上
#: 是因为那三个人的 page 大小写、照片路径、标价都只有后端知道——不开这个口子,
#: 前端就得在 TS 里写死一份小型选手库,那才是这份测试真正要拦的东西。
ALLOWED_ENDPOINTS = {"/api/draft", "/api/run", "/api/showcase"}

#: 引擎里的系数。它们只有一处出处(`blinddraft/engine/params.py`),
#: 抄进 TS 就等于埋了个迟早对不上的第二实现。
FORBIDDEN = (
    (r"\b0\.35\b.*\b0\.25\b", "Carry 权重 (.35/.25)"),
    (r"NO_AWP|noAwp|no_awp", "无狙罚"),
    (r"MAP_SCALE|mapScale", "Map Residual 的 scale"),
    (r"SIGMA_UP|SIGMA_DOWN|sigmaUp|sigmaDown", "Player Roll 的 sigma"),
    (r"TACTICAL_AT|tacticalAt", "战术执行曲线"),
    (r"cohesionCap|COHESION_CAP", "磨合度上限"),
)


def sources():
    """外壳的全部 TS/TSX 源码,(相对路径, 文本)。"""
    return [(p.relative_to(WEB).as_posix(), p.read_text(encoding="utf-8"))
            for p in sorted(WEB.rglob("*.ts*"))]


class ShellIsAShellTests(unittest.TestCase):
    def test_the_second_engine_stays_dead(self):
        for rel in RETIRED:
            self.assertFalse(
                (WEB / rel).exists(),
                f"{rel} 又出现了——它是另一套比赛引擎/选手库，"
                f"玩法只能有一份，在 Python 那边")

    def test_the_shell_only_talks_to_draft_and_run(self):
        found = set()
        for _rel, text in sources():
            found.update(re.findall(r"[\"'](/api/[a-z_/]+)[\"']", text))
        self.assertTrue(found, "一个接口都没找到——client.ts 是不是被改没了?")
        self.assertEqual(
            found - ALLOWED_ENDPOINTS, set(),
            "外壳调了计划外的接口:玩法数据只该走 /api/draft 和 /api/run")

    def test_no_engine_coefficient_is_copied_into_typescript(self):
        for rel, text in sources():
            for pattern, what in FORBIDDEN:
                self.assertIsNone(
                    re.search(pattern, text),
                    f"{rel} 里出现了{what}——引擎系数只有 "
                    f"blinddraft/engine/params.py 一处出处，"
                    f"页面要用就让后端把算好的数发过来")

    def test_the_derived_layer_says_out_loud_that_it_does_not_count(self):
        """表演层必须自己声明它不算数,否则下一个人会拿它当真数据接着盖楼。"""
        text = (WEB / "game" / "playByPlay.ts").read_text(encoding="utf-8")
        self.assertIn("不参与", text)
        self.assertIn("演绎", text)


if __name__ == "__main__":
    unittest.main()
