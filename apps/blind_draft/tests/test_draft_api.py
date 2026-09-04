# -*- coding: utf-8 -*-
"""`/api/draft`:选人这一层的唯一权威入口。

这个文件盯三件事,每一件都是这条 API 存在的理由:

1. **它不是第二份发牌实现。** 同一个 seed,API 重放出来的板面必须和命令行
   `Dealer` 逐张相同——否则 `--seed 7` 和网页上的 seed 7 又变成两局,而这
   正是老页面那份 JS `draw()` 已经犯过的错(规则同、随机数流不同,没有任何
   测试盯着)。
2. **盲选的信息边界在后端。** 板面上不许出现 `page` / `nickname` / 档位 /
   四维真值。「前端不显示」不算数:发下去了就等于发下去了。
3. **回放不许安静地滑过去。** 动作比市场日多、放不该放的一天、签不存在的
   牌,都要报错;静默忽略会让一局的状态和玩家看到的对不上,而且查不出来。
"""
import json
import random
import unittest

from blinddraft import draft as P
from bdserver import draft as D
from bdserver import run as R

SEED = 7
#: 板面上一律不许出现的键。真值只在盲选结束后由 `/api/run` 的 roster 给。
SECRET = ("page", "nickname", "grade", "firepower", "leadership",
          "experience", "stability", "overall", "team", "age", "majors")


def sign_until_done(seed=SEED, choice=0):
    """一路签板面上的第 `choice` 张,直到签满五人。返回最终状态。"""
    acts = []
    while True:
        state = D.build_draft(seed, acts)
        if state["done"]:
            return state
        acts.append(min(choice, len(state["board"]) - 1))


class ReplayTests(unittest.TestCase):
    """同一个 seed 必须是同一局,而且和命令行是同一局。"""

    def test_the_first_board_is_the_cli_dealers_first_board(self):
        rosters = P.load_rosters()
        dealer = P.Dealer(P.load_cards(), random.Random(SEED),
                          P.mate_index(rosters))
        want = dealer.board(P.BUDGET, P.SLOTS, [])
        got = D.build_draft(SEED)["board"]
        self.assertEqual([c["price"] for c in want], [c["price"] for c in got])
        self.assertEqual([c["position"] for c in want],
                         [c["position"] for c in got])
        self.assertEqual([c["country"] for c in want], [c["country"] for c in got])
        self.assertEqual([list(c["scout"]) for c in want],
                         [[c["scout"]["lo"], c["scout"]["hi"]] for c in got])

    def test_the_same_actions_replay_to_the_same_state(self):
        a = D.build_draft(SEED, [0, -1, 2])
        b = D.build_draft(SEED, [0, -1, 2])
        self.assertEqual(a, b)

    def test_a_different_seed_is_a_different_game(self):
        self.assertNotEqual(D.build_draft(SEED)["board"],
                            D.build_draft(SEED + 1)["board"])

    def test_signing_advances_the_turn_and_spends_the_price(self):
        first = D.build_draft(SEED)
        price = first["board"][0]["price"]
        after = D.build_draft(SEED, [0])
        self.assertEqual(after["turn"], 2)
        self.assertEqual(after["left"], P.BUDGET - price)
        self.assertEqual(after["spent"], price)
        self.assertEqual(len(after["owned"]), 1)
        # 已签的那张在名单里还是同一张牌
        self.assertEqual(after["owned"][0]["price"], price)

    def test_passing_costs_a_market_day_but_no_money(self):
        after = D.build_draft(SEED, [-1])
        self.assertEqual(after["turn"], 2)
        self.assertEqual(after["left"], P.BUDGET)
        self.assertEqual(after["passed"], [1])
        self.assertEqual(after["passes_left"], 1)


class BlindnessTests(unittest.TestCase):
    """发下去的东西里不许有真值。"""

    def test_the_board_carries_no_identity_and_no_true_attributes(self):
        state = D.build_draft(SEED, [0, 2])
        for row in state["board"] + state["owned"]:
            for key in SECRET:
                self.assertNotIn(key, row)

    def test_no_nickname_survives_anywhere_in_the_payload(self):
        """连夹带都不许:把这一局真牌的昵称拿来在整份 JSON 里搜。"""
        rosters = P.load_rosters()
        dealer = P.Dealer(P.load_cards(), random.Random(SEED),
                          P.mate_index(rosters))
        names = [c["nickname"] for c in dealer.board(P.BUDGET, P.SLOTS, [])]
        blob = json.dumps(D.build_draft(SEED), ensure_ascii=False)
        for name in names:
            self.assertNotIn(f'"{name}"', blob)

    def test_pages_appear_only_after_the_draft_is_over(self):
        self.assertNotIn("pages", D.build_draft(SEED))
        self.assertNotIn("pages", D.build_draft(SEED, [0]))
        done = sign_until_done()
        self.assertEqual(len(done["pages"]), P.SLOTS)
        self.assertEqual(len(set(done["pages"])), P.SLOTS)


class RulesTests(unittest.TestCase):
    """预算和市场日的约束由后端兜住,不靠前端自觉。"""

    def test_every_card_on_the_board_is_affordable(self):
        acts = []
        for _ in range(P.TURNS):
            state = D.build_draft(SEED, acts)
            if state["done"]:
                break
            for row in state["board"]:
                self.assertTrue(P.affordable(row["price"], state["left"],
                                             state["slots_left"]),
                                f"${row['price']} 买不起:剩 ${state['left']}、"
                                f"还要签 {state['slots_left']} 人")
            acts.append(0)

    def test_a_finished_draft_never_runs_out_of_money(self):
        done = sign_until_done()
        self.assertEqual(len(done["owned"]), P.SLOTS)
        self.assertGreaterEqual(done["left"], 0)
        self.assertEqual(done["board"], [])
        self.assertFalse(done["can_pass"])

    def test_passing_stops_when_the_market_days_run_out(self):
        """七天签五人,最多只能放两天;第三次必须被拒。"""
        self.assertTrue(D.build_draft(SEED, [-1, -1])["can_pass"] is False)
        with self.assertRaises(ValueError):
            D.build_draft(SEED, [-1, -1, -1])

    def test_bad_actions_are_rejected_instead_of_ignored(self):
        with self.assertRaises(ValueError):
            D.build_draft(SEED, [9])                 # 板面上没有第 10 张
        with self.assertRaises(ValueError):
            D.build_draft(SEED, [-2])                # 不是 PASS 也不是编号
        with self.assertRaises(ValueError):
            D.build_draft(SEED, [0, 0, 0, 0, 0, 0])  # 签满了还接着给动作


class HandoffTests(unittest.TestCase):
    """盲选的出口只有一个:五个 page 交给 `/api/run`。"""

    def test_the_five_pages_are_a_roster_the_engine_accepts(self):
        done = sign_until_done()
        run = R.build_run(done["pages"], seed=SEED)
        self.assertEqual([c["page"] for c in run["roster"]], done["pages"])
        # 揭晓要的完整卡面从这边来,盲选那条 API 不开第二个出口
        self.assertTrue(all(c["nickname"] for c in run["roster"]))


if __name__ == "__main__":
    unittest.main()
