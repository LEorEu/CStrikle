# -*- coding: utf-8 -*-
"""§17 明星可见度：比赛叙事必须认得出谁是这支队的核心。

这一组盯的不是胜负平衡，是**观感**。玩家花 $5 签下 donk，如果引擎系统性地
让 F50 的队友抢走 MVP，那这笔钱就白花了——`docs/blind-draft/1.txt` 把它定成
一条硬验收：F50 和 F96 的 MVP 率差不多，就判引擎坏了。
"""
import collections
import json
import random
import unittest

from blinddraft import draft as P
from blinddraft import major as M
from blinddraft import match as X


def _fake(nick, fire, stab, exp=60, lead=25, pos="RIFLER"):
    return {"nickname": nick, "position": pos, "firepower": fire,
            "stability": stab, "experience": exp, "leadership": lead,
            "caller": pos == "IGL"}


class _Bare(object):
    """只喂 MatchTeam 需要的字段，绕开卡库和默契，保证是控制变量。"""

    def __init__(self, name, roster):
        self.name, self.roster = name, roster
        self.is_player = False
        self.rating = {"chem_raw": 0.0}


def _team(roster, cap=0.0):
    return X.MatchTeam(_Bare("LAB", roster), 1, cap)


# 1.txt 指定的形状：一个真明星，一路铺到边缘轮换。
LADDER = [_fake("F96", 96, 87), _fake("F75", 75, 62), _fake("F68", 68, 57),
          _fake("F62", 62, 50), _fake("F55", 55, 46)]

# 你实际抽到过的那把，直接存成回归样本。
STAR_CARRY = [_fake("donk", 96, 87, exp=82, lead=30),
              _fake("molodoy", 87, 62, exp=53, lead=22, pos="AWPER"),
              _fake("tN1R", 75, 57, exp=39, lead=23),
              _fake("Kvem", 59, 46, exp=25, lead=18),
              _fake("spaze", 50, 47, exp=27, lead=56, pos="IGL")]


def _tally(roster, n=8000, seed=4):
    """跑 n 张图，统计每人拿 MVP / LIFE GAME / UNDERPERFORM 的比例。"""
    team = _team(roster)
    rng = random.Random(seed)
    mvp = {c["nickname"]: 0 for c in roster}
    life = dict(mvp)
    under = dict(mvp)
    for _ in range(n):
        _s, detail = team.play_map(rng, 0.0)
        mvp[max(detail, key=lambda t: t[1])[0]["nickname"]] += 1
        top = max(detail, key=lambda t: t[2])
        if top[2] >= X.LIFE_GAME_AT:
            life[top[0]["nickname"]] += 1
        low = min(detail, key=lambda t: t[2])
        if low[2] <= X.UNDERPERFORM_AT:
            under[low[0]["nickname"]] += 1
    f = lambda d: {k: v / n for k, v in d.items()}      # noqa: E731
    return f(mvp), f(life), f(under)


class StarVisibilityTests(unittest.TestCase):
    def test_the_star_is_the_clear_mvp_favourite(self):
        mvp, _life, _under = _tally(LADDER)
        self.assertEqual(max(mvp, key=mvp.get), "F96")
        # 「明显最多」而不是「多一点」：至少是第二名的两倍。
        rest = sorted((v for k, v in mvp.items() if k != "F96"), reverse=True)
        self.assertGreater(mvp["F96"], 2 * rest[0])
        self.assertGreater(mvp["F96"], 0.55)

    def test_weak_cards_never_out_mvp_the_star(self):
        """1.txt 的硬验收线。改坏引擎时这条必须先响。"""
        mvp, _life, _under = _tally(STAR_CARRY)
        self.assertGreater(mvp["donk"], 4 * mvp["spaze"])
        self.assertGreater(mvp["donk"], mvp["Kvem"])

    def test_life_game_belongs_to_the_volatile_ones(self):
        """MVP 归明星，爆种归低稳定的人——两个故事各归各的。"""
        mvp, life, _under = _tally(LADDER)
        self.assertEqual(max(life, key=life.get), "F55")
        self.assertGreater(life["F55"], life["F96"])
        self.assertEqual(mvp and max(mvp, key=mvp.get), "F96")

    def test_low_stability_swings_both_ways(self):
        """低稳定既容易爆种也容易崩，不能只有好的一面。"""
        _mvp, life, under = _tally(LADDER)
        self.assertGreater(under["F55"], under["F96"])
        self.assertGreater(life["F55"], 0.0)
        self.assertGreater(under["F55"], 0.0)

    def test_star_weight_is_fixed_by_the_card_not_by_todays_roll(self):
        """§17.1：椅子在开赛前定死，当天手热不改变队内定位。"""
        team = _team(LADDER)
        self.assertEqual(team.star_w, [.35, .25, .40 / 3, .40 / 3, .40 / 3])
        # 顺序打乱后，权重必须跟着人走，而不是跟着 roster 下标走。
        shuffled = [LADDER[3], LADDER[0], LADDER[4], LADDER[2], LADDER[1]]
        self.assertEqual(_team(shuffled).star_w,
                         [.40 / 3, .35, .40 / 3, .40 / 3, .25])

    def test_baseline_still_equals_entry_rating(self):
        """固定权重不许动「不 Roll 时强度 == Entry」这条老不变量。"""
        cards = P.load_cards()
        rosters = P.load_rosters()
        mates = P.mate_index(rosters)
        for seed in (7, 50296, 156515):
            roster, _left = M.bot_draft(seed, cards, rosters, mates)
            entry = M.Entry("T", roster, M.entry_rating(roster, rosters,
                                                        M.COHESION_CAP))
            team = X.MatchTeam(entry, 1, M.COHESION_CAP)
            self.assertAlmostEqual(team.baseline(), entry.entry, places=6)


class MapStoryTests(unittest.TestCase):
    def test_the_losing_side_can_still_hold_the_mvp(self):
        """「载物尽力了，队友带不动」必须讲得出来——旧口径永远讲不出。"""
        strong = _team([_fake("ACE", 99, 99)] + [_fake("m%d" % i, 40, 99)
                                                 for i in range(4)])
        weak = _team([_fake("w%d" % i, 45, 99) for i in range(5)])
        rng = random.Random(1)
        seen = 0
        for _ in range(400):
            m = X.play_map(strong, weak, rng, 0.0)
            if not m.winner_a and m.mvp[1]:
                seen += 1
        self.assertGreater(seen, 0)

    def test_mvp_reads_performance_and_life_game_reads_deviation(self):
        rng = random.Random(2)
        a, b = _team(LADDER), _team(STAR_CARRY)
        for _ in range(300):
            m = X.play_map(a, b, rng, 0.0)
            # MVP 是全场有效火力最高的那个，不是偏离最大的那个。
            self.assertGreaterEqual(m.mvp[0].eff, m.life[0].eff)
            self.assertGreaterEqual(m.life[0].delta, m.under[0].delta)
            for t in m.da + m.db:
                # 归因必须逐项加得回 delta，否则展示出来的解释是假的。
                self.assertAlmostEqual(
                    t.team + t.solo + t.exp_gain + t.lead_gain + t.capped,
                    t.delta, places=9)



class MatchV2Tests(unittest.TestCase):
    """Match Engine v0.3 原型的验收闸门。

    这一组盯的是设计稿里**写死了目标值**的那几条。系数一旦漂移，或者有人
    把 Map Residual 接进了 Player Story，这里先响。
    """

    @classmethod
    def setUpClass(cls):
        from blinddraft import proto_match_v2 as V2
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
