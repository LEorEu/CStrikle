import collections
import json
import unittest
from datetime import datetime
from pathlib import Path

from blinddraft.cards import (
    ATTRS,
    SPEC_BEGIN,
    SPEC_END,
    TEMPLATE,
    build_card,
    career_grade,
    champion_count,
    draft_position,
    generate,
    load_top20,
    played_role_map,
    spec_markdown,
)
from blinddraft.firepower import round_target
from playerdb.players import PlayerDB

from playerdb.paths import ROOT

DESIGN_DOC = ROOT / "docs" / "blind-draft" / "卡牌与落地记录.md"


class SpecInSyncTests(unittest.TestCase):
    """文档里的算法规格必须和代码里的常量一字不差。

    手抄一份常量到设计文档里,迟早会和实现对不上,而且不会有任何报错——玩家看到的
    数值和文档描述的规则悄悄分家,是这个项目反复踩到的那类静默失败。所以规格块由
    `--spec` 生成,这条测试盯着两边一致;改了常量就重新跑一次 `--spec` 贴回去。
    """

    def test_design_doc_contains_generated_spec(self):
        doc = DESIGN_DOC.read_text(encoding="utf-8")
        self.assertIn(SPEC_BEGIN, doc, "docs/blind-draft/卡牌与落地记录.md 里找不到规格块起始标记")
        self.assertIn(SPEC_END, doc, "docs/blind-draft/卡牌与落地记录.md 里找不到规格块结束标记")
        start = doc.index(SPEC_BEGIN)
        end = doc.index(SPEC_END) + len(SPEC_END)
        embedded = doc[start:end].replace("\r\n", "\n").strip()
        self.assertEqual(
            embedded,
            spec_markdown().strip(),
            "文档里的算法规格和代码不一致;重新执行 "
            "`python blinddraft/cards.py --spec` 并把输出贴回 docs/blind-draft/卡牌与落地记录.md",
        )


class CardGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards, cls.pending, cls.confirmed = generate()

    def test_pool_is_not_empty(self):
        self.assertGreater(len(self.cards), 500)

    def test_attributes_stay_in_range(self):
        for card in self.cards:
            for key in ATTRS:
                self.assertGreaterEqual(card[key], 1, card["nickname"])
                self.assertLessEqual(card[key], 99, card["nickname"])

    def test_generation_is_idempotent(self):
        """同一版本重跑必须逐字段一致,否则玩家积累的认知会在一次部署后全部作废。"""
        again, _, _ = generate()
        self.assertEqual(
            [{k: v for k, v in c.items() if k != "titles"} for c in self.cards],
            [{k: v for k, v in c.items() if k != "titles"} for c in again],
        )

    def test_published_file_matches_generator(self):
        """已发布文件就是运行时读取的真值，不许和实时生成器静默分叉。"""
        from blinddraft.cards import OUT_PATH

        published = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        # JSON 会把 titles 里的 tuple 写成 list；先走同一次序列化再比较结构。
        live = json.loads(json.dumps(
            [{k: v for k, v in c.items() if k != "_trace"} for c in self.cards],
            ensure_ascii=False,
        ))
        self.assertEqual(published["card_version"], __import__(
            "blinddraft.cards", fromlist=["CARD_VERSION"]).CARD_VERSION)
        self.assertEqual(published["count"], len(live))
        self.assertEqual(
            published["cards"], live,
            "draft_cards.json 与实时生成结果不同；运行 "
            "`python -m blinddraft.cards --write` 后审查并提交生成物",
        )

    def test_firepower_half_rounding_is_not_a_float_coin_flip(self):
        """数学上的 x.5 不能因插值毛刺在两个整数间翻转。"""
        self.assertEqual(round_target(84.5), 85)
        self.assertEqual(round_target(84.50000000000003), 85)
        self.assertEqual(round_target(84.49999999999997), 84)

    def test_card_ages_are_frozen_to_player_database_snapshot(self):
        db = PlayerDB()
        asof = datetime.fromisoformat(db.generated_at).date()
        players = {p.page: p for p in db.players}
        for card in self.cards:
            self.assertEqual(card["age"], players[card["page"]].age(asof),
                             card["nickname"])

    def test_champion_squads_have_one_igl(self):
        """一支冠军阵容不可能有两个指挥。

        Liquipedia 只要这人生涯里指挥过就打 igl 标签,分不出「巅峰是指挥」和
        「后来当过指挥」,靠人眼看名单必然会漏。
        """
        squads = collections.defaultdict(list)
        for card in self.cards:
            for event, team in card.get("titles", []):
                squads[(event, team)].append((card["nickname"], card["position"]))
        offenders = {
            key: [name for name, pos in members if pos == "IGL"]
            for key, members in squads.items()
        }
        offenders = {k: v for k, v in offenders.items() if len(v) > 1}
        self.assertEqual(offenders, {}, f"冠军阵容出现多个指挥:{offenders}")

    def test_pending_and_excluded_are_disjoint(self):
        self.assertEqual(set(self.pending) & set(self.confirmed), set())


class OverrideTests(unittest.TestCase):
    """位置/档位的人工修正必须在套模板之前生效。

    放在最后 update 只会换掉标签,四维仍旧来自被否掉的那套模板——Magisk 改成
    RIFLER 却还顶着 IGL 模板的领导 97,是最难发现的一种错。
    """

    @classmethod
    def setUpClass(cls):
        cls.db = PlayerDB()
        cls.ranks, cls.ref_year = load_top20()
        cls.played = played_role_map()

    def _card(self, nickname, overrides):
        player = self.db.lookup(nickname)
        pos = draft_position(player, self.played)
        champs = champion_count(player)
        grade = career_grade(player, self.ranks, champs, pos, self.ref_year)
        return build_card(player, grade, pos, self.ranks, champs, overrides,
                          self.ref_year)

    def test_position_override_switches_the_template(self):
        player = self.db.lookup("NiKo")
        forced = self._card("NiKo", {player.page: {"position": "IGL"}})
        self.assertEqual(forced["position"], "IGL")
        # IGL 模板的领导力底板远高于步枪,换模板才会体现出来
        self.assertGreater(forced["leadership"], TEMPLATE["RIFLER"][5][1] + 20)

    def test_attribute_override_replaces_the_value(self):
        player = self.db.lookup("NiKo")
        forced = self._card("NiKo", {player.page: {"firepower": 42}})
        self.assertEqual(forced["firepower"], 42)
        # overall 必须按覆盖后的值重算
        plain = self._card("NiKo", {})
        self.assertLess(forced["overall"], plain["overall"])


if __name__ == "__main__":
    unittest.main()
