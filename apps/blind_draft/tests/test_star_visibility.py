# -*- coding: utf-8 -*-
"""§17 明星可见度 + Match Engine v0.3 的验收闸门。

明星可见度盯的不是胜负平衡，是**观感**。玩家花 $5 签下 donk，如果引擎系统性地
让 F50 的队友抢走 MVP，那这笔钱就白花了——`docs/blind-draft/1.txt` 把它定成
一条硬验收：F50 和 F96 的 MVP 率差不多，就判引擎坏了。

这个文件曾经分 v1 / v2 两组，同一条不变量各写一遍。v1（`blinddraft.match`）
已退役删除，所以现在只有一套断言，全部对着 `proto_match_v2`。原来 v1 独有的
四条（Carry 权重由卡面定死、逐项归因加得回 delta、输的一方也能拿 MVP、
不 Roll 时的强度等于 Entry）都翻译成了 v2 的口径，见 `MatchV2Tests`。
"""
import collections
import json
import random
import unittest

from blinddraft import draft as P
from blinddraft import proto_match_v2 as V2


class MatchV2Tests(unittest.TestCase):
    """Match Engine v0.3 原型的验收闸门。

    这一组盯的是设计稿里**写死了目标值**的那几条。系数一旦漂移，或者有人
    把 Map Residual 接进了 Player Story，这里先响。
    """

    @classmethod
    def setUpClass(cls):
        cls.V = V2

    def test_stability_distribution_matches_the_frozen_spec(self):
        """§6.3 冻结的那两组分位数。改 SIGMA_SCALE 会直接打破这条。"""
        V = self.V
        got = {}
        for s in (90, 50):
            rng = random.Random(1)
            vals = sorted(80 + V.form_delta(rng.random(), s)
                          for _ in range(20000))
            q = lambda p: vals[int(p * len(vals))]      # noqa: E731
            got[s] = (q(.05), q(.5), q(.95), q(.99))
        for want, have in zip((75, 81, 87, 90), got[90]):
            self.assertAlmostEqual(have, want, delta=1.5)
        for want, have in zip((63, 78, 93, 98), got[50]):
            self.assertAlmostEqual(have, want, delta=1.5)

    def test_pressure_reshapes_the_same_roll_not_a_new_one(self):
        """§8.3 给的三个例子，一个都不能变。"""
        V = self.V
        self.assertAlmostEqual(V.under_pressure(2, 82, 1.2)[0], 2.0, places=6)
        self.assertAlmostEqual(V.under_pressure(-7, 25, 1.2)[0], -11.0, delta=.2)
        self.assertAlmostEqual(V.under_pressure(-7, 90, 1.2)[0], -7.5, delta=.2)
        # 压力为 0 时完全不存在
        self.assertEqual(V.under_pressure(-9, 20, 0.0), (-9, 0.0))

    def test_leadership_hits_the_win_rate_targets(self):
        """§9.2：先定胜率差再反推 Strength。这条锁的是**胜率**，不是分数。"""
        V = self.V
        ref = V._probe("ref", 78, 60, igl_lead=65)
        elite = V._probe("elite", 78, 60, igl_lead=96)
        none = V._probe("none", 78, 60)
        gain = V.win_rate(elite, ref, 1, 0.0, 6000, 17) - 0.5
        loss = 0.5 - V.win_rate(none, ref, 1, 0.0, 6000, 17)
        self.assertGreater(gain, 0.03)          # 目标 4~6pt，留一点采样余量
        self.assertLess(gain, 0.07)
        self.assertGreater(loss, 0.05)          # 目标 6~10pt
        self.assertLess(loss, 0.11)

    def test_map_residual_never_touches_player_story(self):
        """§13.4：残差不能生成 MVP，也不能改任何人的有效火力。"""
        V = self.V
        a, b = V._probe("A", 80, 60), V._probe("B", 78, 60)
        rng = random.Random(3)
        for _ in range(200):
            m = V.play_map(a, b, rng, 0.0)
            everyone = list(m.da) + list(m.db)
            best = max(everyone, key=lambda t: t.eff)
            self.assertIs(m.mvp[0], best)               # MVP 只看有效火力
            for t in everyone:                          # 残差没有混进任何人
                self.assertAlmostEqual(t.eff - t.card["firepower"], t.delta,
                                       places=9)
            self.assertAlmostEqual(m.margin, (m.sa - m.sb) + m.residual,
                                   places=9)

    def test_the_star_is_the_mvp_and_the_weak_card_is_not(self):
        """和 v1 同一条硬线：F50 的 MVP 率不许接近 F96。"""
        V = self.V
        cards = {c["nickname"]: c for c in P.load_cards()}
        team = V.named_team("donk carry", V.FIXTURES["donk carry"], cards)
        rng = random.Random(7)
        mvp = {c["nickname"]: 0 for c in team.roster}
        for _ in range(4000):
            _s, d = team.play_map(rng, 0.0)
            mvp[max(d, key=lambda t: t.eff).card["nickname"]] += 1
        self.assertGreater(mvp["donk"] / 4000, 0.75)
        self.assertLess(mvp["spaze"] / 4000, 0.02)

    def test_bo3_is_safer_than_bo1_without_any_bo3_bonus(self):
        """§16：BO3 更稳必须是多掷几张图自然涌现的，引擎里没有 BO3 加成。"""
        V = self.V
        a, b = V._probe("A", 80, 70), V._probe("B", 70, 70)
        bo1 = V.win_rate(a, b, 1, 0.0, 6000, 11)
        bo3 = V.win_rate(a, b, 3, 0.0, 6000, 11)
        self.assertGreater(bo3, bo1)
        self.assertLess(bo1, 0.90)          # BO1 仍留得住爆冷
        self.assertGreater(bo1, 0.70)

    def test_entry_has_no_static_leadership_experience_stability(self):
        """§4.1：把这三维改成任何值，Entry 都不许动。"""
        V = self.V
        base = [V._fake("p%d" % i, 70, 60, exp=50, lead=30) for i in range(5)]
        moved = [dict(c, stability=95, experience=95, leadership=95)
                 for c in base]
        self.assertAlmostEqual(V.Team("a", base).entry(),
                               V.Team("b", moved).entry(), places=9)

    # ---- 下面四条是从退役的 v1 翻译过来的，口径换成 v2 ----

    def test_star_weight_is_fixed_by_the_card_not_by_todays_roll(self):
        """§4.2：椅子在开赛前定死，当天手热不改变队内定位。

        v1 那版的 bug 是按**当图掷骰结果**重排 .35/.25/.133，一次高 Roll 能
        既涨分又从后排跳到主枪位。v2 的 `Team.weights` 在构造时按卡面火力排定。
        """
        V = self.V
        ladder = [V._fake("F%d" % f, f, 60) for f in (96, 75, 68, 62, 55)]
        self.assertEqual(V.Team("t", ladder).weights,
                         [.35, .25, .40 / 3, .40 / 3, .40 / 3])
        # 顺序打乱后权重必须跟着人走，而不是跟着 roster 下标走
        shuffled = [ladder[3], ladder[0], ladder[4], ladder[2], ladder[1]]
        self.assertEqual(V.Team("t", shuffled).weights,
                         [.40 / 3, .35, .40 / 3, .40 / 3, .25])

    def test_per_player_attribution_adds_back_to_delta(self):
        """展示出来的解释必须是真的：逐项相加要精确等于 delta，无残差。

        v1 拆成「全队状态 + 个人状态 + 指挥挽回 + 经验挽回 + 软顶」；v2 只剩
        三项——§11 退役了 Team Shared Form，Leadership 也不再逐人挽回。
        """
        V = self.V
        a, b = V._probe("A", 80, 50), V._probe("B", 74, 90)
        rng = random.Random(6)
        for _ in range(200):
            m = V.play_map(a, b, rng, 1.2)          # 有压力才走得到 choke 那一项
            for t in list(m.da) + list(m.db):
                self.assertAlmostEqual(t.form + t.choke + t.capped, t.delta,
                                       places=9)

    def test_the_losing_side_can_still_hold_the_mvp(self):
        """「核心尽力了，队友带不动」必须讲得出来——v1 的旧口径永远讲不出。"""
        V = self.V
        strong = V.Team("S", [V._fake("ACE", 99, 99)] +
                        [V._fake("m%d" % i, 40, 99) for i in range(4)])
        weak = V.Team("W", [V._fake("w%d" % i, 45, 99) for i in range(5)])
        rng = random.Random(1)
        seen = sum(1 for _ in range(400)
                   if (lambda m: not m.winner_a and m.mvp[1])(
                       V.play_map(strong, weak, rng, 0.0)))
        self.assertGreater(seen, 0)

    def test_life_game_and_underperform_belong_to_the_volatile_ones(self):
        """MVP 归明星，爆种和崩盘归低稳定的人——两个故事各归各的，且都要有。"""
        V = self.V
        roster = [V._fake("F96", 96, 87), V._fake("F75", 75, 62),
                  V._fake("F68", 68, 57), V._fake("F62", 62, 50),
                  V._fake("F55", 55, 46)]
        team = V.Team("LADDER", roster)
        rng = random.Random(4)
        n = 8000
        mvp, life, under = (collections.Counter() for _ in range(3))
        for _ in range(n):
            _s, d = team.play_map(rng, 0.0)
            mvp[max(d, key=lambda t: t.eff).card["nickname"]] += 1
            hi = max(d, key=lambda t: t.delta)
            if hi.delta >= V.LIFE_GAME_AT:
                life[hi.card["nickname"]] += 1
            lo = min(d, key=lambda t: t.delta)
            if lo.delta <= V.UNDERPERFORM_AT:
                under[lo.card["nickname"]] += 1
        self.assertEqual(max(mvp, key=mvp.get), "F96")
        self.assertEqual(max(life, key=life.get), "F55")
        self.assertGreater(life["F55"], life["F96"])
        self.assertGreater(under["F55"], under["F96"])
        self.assertGreater(under["F55"], 0)

    def test_strength_has_no_source_beyond_entry_and_tactical(self):
        """v1 的老不变量「不 Roll 时强度 == Entry」在 v2 里的样子。

        v2 把战术执行（Leadership）从 Entry 里拿掉了（§4.1），所以它不再是
        恒等式，而是 entry() + tactical。两头都要钉：把当图发挥按住（delta=0）
        必须正好回到这个数；真掷一次，强度也只能是「逐人有效火力按权重加权
        + 战术执行 + 结构」，不许有第四个来源偷偷加分。
        """
        V = self.V
        rng = random.Random(12)
        for spec in V.FIXTURES:
            team = V.roster_team(spec)
            flat = sum(w * c["firepower"]
                       for w, c in zip(team.weights, team.roster))
            self.assertAlmostEqual(flat + team.tactical + team.structure,
                                   team.entry() + team.tactical, places=9)
            for _ in range(50):
                strength, rolls = team.play_map(rng, 0.0)
                self.assertAlmostEqual(
                    strength,
                    sum(t.weight * t.eff for t in rolls)
                    + team.tactical + team.structure, places=9)


class MajorShellTests(unittest.TestCase):
    """v2 的赛事外壳：VRS 名额、插队级联、三段 Swiss 的记账。"""

    def setUp(self):
        # 每个用例重建赛场：insert_player 会就地改 team.stage，共享一份会串味。
        from blinddraft import proto_match_v2 as V2
        self.V = V2
        self.field, self.asof = V2.major_field()

    def test_stage_comes_from_regional_vrs_slots(self):
        """§1.2 的区域名额表：8 / 8 / 16，且和 Entry 排名无关。"""
        V = self.V
        counts = collections.Counter(t.stage for t in self.field)
        self.assertEqual(dict(counts), {3: 8, 2: 8, 1: 16})
        # 关键回归：Stage 归属不许退化成「按 Entry 排名切 8/16/32」。
        by_entry = sorted(self.field, key=lambda t: -t.entry())
        as_rank = [3] * 8 + [2] * 8 + [1] * 16
        actual = [t.stage for t in by_entry]
        self.assertNotEqual(actual, as_rank,
                            "Stage 又变回按 Entry 排名切了，VRS 名额被绕过")

    def test_player_insert_cascades_one_tier_at_a_time(self):
        """挤进某一层 -> 该层最弱的降级 -> 级联 -> 第 33 掉出。"""
        V = self.V
        cards = {c["nickname"]: c for c in P.load_cards()}
        me = V.Team("YOU", [cards[n] for n in V.FIXTURES["donk carry"]],
                    0.0, is_player=True)
        field = [t for t in self.field]
        stage, shove, full = V.insert_player(field, me)
        self.assertIn(stage, (1, 2, 3))
        self.assertEqual(len(full), V.FIELD_SIZE)
        self.assertIn(me, full)
        self.assertIsNotNone(shove.dropped)
        self.assertNotIn(shove.dropped, full)
        # 每降一级都是恰好一级，而且层级人数守恒
        for _t, was, now in shove.demoted:
            self.assertEqual(was - now, 1)
        counts = collections.Counter(t.stage for t in full)
        self.assertEqual(dict(counts), {3: 8, 2: 8, 1: 16})

    def test_a_team_weaker_than_the_whole_field_fails_to_qualify(self):
        V = self.V
        junk = [V._fake("j%d" % i, 20, 50) for i in range(5)]
        stage, shove, full = V.insert_player(list(self.field),
                                             V.Team("JUNK", junk, 0.0, True))
        self.assertEqual(stage, 0)
        self.assertIsNone(shove.dropped)
        self.assertEqual(len(full), V.FIELD_SIZE)

    def test_a_full_major_books_every_team_to_three_wins_or_losses(self):
        V = self.V
        stages, logs = V.run_major([t for t in self.field], random.Random(7))
        for s in (1, 2, 3):
            teams, adv = stages[s]
            self.assertEqual(len(teams), 16)
            self.assertEqual(len(adv), 8)
            for t in teams:
                self.assertTrue(t.w >= 3 or t.l >= 3,
                                "%s 停在 %d-%d" % (t.name, t.w, t.l))
            # 晋级名单必须留着**本 Stage** 的战绩，不能被下一层 reset 掉
            for t in adv:
                self.assertGreaterEqual(t.w, 3)

    def test_advancers_carry_forward_as_fresh_objects(self):
        """晋级者带进下一层的是新实例，否则上一层的战绩会被擦掉。"""
        V = self.V
        stages, _logs = V.run_major([t for t in self.field], random.Random(5))
        s1_adv = stages[1][1]
        s2_teams = stages[2][0]
        for t in s1_adv:
            self.assertNotIn(t, s2_teams)
            self.assertGreaterEqual(t.w, 3)

    def test_format_and_pressure_follow_the_v03_ladder(self):
        """§2 + §8.1：晋级局和淘汰局不给同一个压力值。"""
        V = self.V
        self.assertEqual(V.format_of((0, 0)), (1, V.PRESSURE["swiss"]))
        self.assertEqual(V.format_of((2, 0)), (3, V.PRESSURE["advance"]))
        self.assertEqual(V.format_of((0, 2)), (3, V.PRESSURE["elim"]))
        self.assertEqual(V.format_of((2, 2)), (3, V.PRESSURE["decider"]))
        self.assertLess(V.PRESSURE["advance"], V.PRESSURE["elim"])

    def test_player_run_is_a_serializable_whole_tournament(self):
        V = self.V
        data = V.player_run(V.FIXTURES["donk carry"], seed=3)
        self.assertTrue(data["qualified"])
        self.assertIn(data["outcome"], ("eliminated", "playoffs"))
        self.assertTrue(data["legs"])
        self.assertEqual(data["wins"] + data["losses"], len(data["legs"]))
        for leg in data["legs"]:
            self.assertTrue(leg["maps"])
            for m in leg["maps"]:
                self.assertEqual(len(m["players"]), 5)
                self.assertEqual(len(m["opponents"]), 5)
                # 玩家永远在 a 位：margin 的符号要和玩家胜负一致
                self.assertEqual(m["margin"] > 0, m["player_won"])
        json.dumps(data, ensure_ascii=False)

if __name__ == "__main__":
    unittest.main()
