# -*- coding: utf-8 -*-
"""Blind Draft 的命令行原型:不做 UI、不做比赛模拟,只回答「这套选人有没有决策」。

跑法:
    .\.venv\Scripts\python -X utf8 scripts\proto_draft.py           # 盲选一局
    .\.venv\Scripts\python -X utf8 scripts\proto_draft.py --open    # 明牌(四维给数字)
    .\.venv\Scripts\python -X utf8 scripts\proto_draft.py --seed 7  # 复现同一局

v2 相对 v1 改了什么(都来自 v1 的五局实测,见 .cache/proto_draft_runs.jsonl):

- **同价位内做出形状差异。** v1 最大的问题不是线索弱,是同一档的卡本来就是克隆人
  (生成器给的是模板 + 抖动,G1 步枪一律 52/20/20/48±4),所以「捡漏」在数据结构上
  就不存在。这里做一次**零和整形**:同价位不拉开强弱、只拉开形状,加权 overall
  逐张守恒。整形只发生在原型里,不回写 data/draft_cards.json。
- **卡面换成球探报告。** 去掉年龄和 Major 次数——实测这两条在同价位内和价值的
  相关性是噪声级(≤0.6 分),而人一定会拿屏幕上有的东西建立直觉,所以它们不是
  弱线索,是**有害线索**。改成给算分真正用到的维度,而且只给两条,留一条不说。
- **跳过 = 换一批牌。** 7 轮机会填 5 个位置,跳过一轮就重新发牌。剩下的钱允许
  留着,赛后直接给「留钱亏多少」的曲线。
- **第二个 IGL 不再加领导力**(v1 里塞两个指挥能把「其余四人」那项顶上去,是漏洞),
  改成扣默契:两个指挥抢话。
- **发牌保证位置可覆盖**:每批牌至少有一个 AWP 和一个 IGL,不再出现躲不掉的 −4。
- **赛后自动给逐轮后悔值**,不用我事后重放你才知道亏在哪。
"""
import argparse
import collections
import itertools
import json
import random
import statistics as st
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS_PATH = ROOT / "data" / "draft_cards.json"
PLAYERS_PATH = ROOT / "data" / "players.json"
LOG_PATH = ROOT / ".cache" / "proto_draft_runs.jsonl"

BUDGET = 15
SLOTS = 5
TURNS = 7                        # 7 轮机会填 5 个位置 → 自带 2 次跳过
TIERS = (5, 4, 3, 2, 1)          # 每批牌每档各一张,档位即价格
WEIGHTS = {"RIFLER": (0.55, 0.05, 0.20, 0.20),
           "AWPER": (0.45, 0.05, 0.20, 0.30),
           "IGL": (0.25, 0.35, 0.35, 0.05)}   # 与 gen_draft_cards.py §18 一致

RULES = """\
算分(全部公开,没有隐藏项):

  火力   最高 ×0.35 + 次高 ×0.25 + 其余三人均值 ×0.40   明星主导,不是求平均
  领导   只算队里最强的那个 IGL ×0.70 + 其余四人 ×0.30;没有 IGL 则整项 ×0.60
  经验   五人均值
  稳定   五人均值(同时决定发挥波动幅度,不只是加分)

  基础分 = 火力 ×0.40 + 领导 ×0.20 + 经验 ×0.20 + 稳定 ×0.20
           没有 AWP 再 −4

  默契   真实队友(同一届 Major 同队)   每对 +2,同队 ≥5 届再 +1
         同国籍                        每多一个同胞 +1.5
         同代    年龄差 ≤5 → +2   ≥12 → −2
         两个指挥                      −3(抢话)

  总分 = 基础分 + 默契        单场发挥 ≈ 总分 ± (100 − 稳定) / 4

同价位的卡强度相同、形状不同:火力高的稳定就低。没有免费的午餐,
只有「这张形状适不适合我现在这套阵容」。
"""


# ----------------------------------------------------------------- 数据

def overall(c):
    wf, wl, we, ws = WEIGHTS[c["position"]]
    return (c["firepower"] * wf + c["leadership"] * wl
            + c["experience"] * we + c["stability"] * ws)


def shape_cards(cards):
    """零和整形:同价位内拉开形状,不拉开强弱。

    形状取自真实履历而不是随机:年轻 → 火力高/稳定低(打得凶但飘),
    Major 与冠军多 → 经验高/火力让一点(老兵)。整完之后给全卡加一个常数,
    把加权 overall 拉回原值——位置权重和为 1,所以四维同加 c 等于 overall 加 c。
    """
    out = []
    for grade, group in itertools.groupby(sorted(cards, key=lambda c: c["grade"]),
                                          key=lambda c: c["grade"]):
        group = list(group)
        ages = [c["age"] for c in group if c["age"]]
        mu_a, sd_a = st.mean(ages), (st.pstdev(ages) or 1)
        mjs = [c["majors"] for c in group]
        mu_m, sd_m = st.mean(mjs), (st.pstdev(mjs) or 1)

        for c in group:
            z = lambda v: max(-2.0, min(2.0, v))
            aggression = z(-((c["age"] or mu_a) - mu_a) / sd_a)
            veterancy = z((c["majors"] - mu_m) / sd_m + 0.5 * min(c["champions"], 4))

            n = dict(c)
            before = overall(c)
            n["firepower"] = c["firepower"] + 6.0 * aggression - 3.0 * veterancy
            n["stability"] = c["stability"] - 5.0 * aggression + 2.0 * veterancy
            n["experience"] = c["experience"] + 6.0 * veterancy - 2.0 * aggression
            fix = before - overall(n)
            for k in ("firepower", "leadership", "experience", "stability"):
                n[k] = max(1, min(99, round(n[k] + fix)))
            n["overall"] = round(overall(n), 1)
            out.append(n)
    return out


def load_cards():
    cards = json.loads(CARDS_PATH.read_text(encoding="utf-8"))["cards"]
    return shape_cards([c for c in cards if c.get("position")])


def load_rosters():
    """page -> {(赛事, 战队)},用来判定两个人是不是真的同过队。

    players.json 的 majors[] 每一条都带当届的 team,不只是冠军,所以这张图覆盖
    全库 645/648 个人(含 G1 的 306 个),便宜卡也吃得到默契。
    """
    db = json.loads(PLAYERS_PATH.read_text(encoding="utf-8"))["players"]
    out = {}
    for p in db:
        seen = {(m["event"], m["team"]) for m in p.get("majors", []) if m.get("team")}
        if seen:
            out[p["page"]] = seen
    return out


# ----------------------------------------------------------------- 卡面

def bands(cards):
    """同价位内的分位 → 星级/高中低。这是「这张卡在它这个价位里是什么形状」。"""
    tab = {}
    for grade in TIERS:
        grp = [c for c in cards if c["grade"] == grade]
        for key in ("firepower", "stability", "experience", "leadership"):
            vals = sorted(c[key] for c in grp)
            tab[(grade, key)] = vals
    return tab


def band_of(card, key, tab, levels):
    vals = tab[(card["grade"], key)]
    i = sum(1 for v in vals if v < card[key])
    return min(levels - 1, i * levels // max(1, len(vals)))


STARS = ("★☆☆☆☆", "★★☆☆☆", "★★★☆☆", "★★★★☆", "★★★★★")
LEVEL3 = ("低", "中", "高")
SECOND = ("stability", "experience", "leadership")
LABEL = {"stability": "稳定", "experience": "经验", "leadership": "领导"}


def face(card, tab, open_mode):
    """玩家看到的球探报告:价格、位置、国籍 + 火力星级 + 另一条(轮换,留一条不说)。"""
    fire = STARS[band_of(card, "firepower", tab, 5)]
    key = SECOND[zlib.crc32(card["page"].encode("utf-8")) % 3]   # 跨进程稳定
    lvl = LEVEL3[band_of(card, key, tab, 3)]
    bits = [f"火力 {fire}", f"{LABEL[key]} {lvl}", card["country"]]
    if open_mode:
        bits.append(f"[火{card['firepower']} 领{card['leadership']} "
                    f"经{card['experience']} 稳{card['stability']}]")
    return f"${card['grade']}  {card['position']:<6}  " + "  ·  ".join(bits)


# ----------------------------------------------------------------- 算分

def pair_bonus(a, b, rosters):
    shared = rosters.get(a["page"], set()) & rosters.get(b["page"], set())
    if not shared:
        return 0.0, None
    team = collections.Counter(t for _, t in shared).most_common(1)[0][0]
    return 2.0 + (1.0 if len(shared) >= 5 else 0.0), (len(shared), team)


def chemistry(roster, rosters):
    notes, total = [], 0.0

    for a, b in itertools.combinations(roster, 2):
        bonus, info = pair_bonus(a, b, rosters)
        if bonus:
            n, team = info
            total += bonus
            notes.append(f"队友 {a['nickname']} + {b['nickname']}  同队 {n} 届 Major"
                         f"({team})  +{bonus:.1f}")

    for country, n in collections.Counter(c["country"] for c in roster).items():
        if n >= 2:
            total += 1.5 * (n - 1)
            notes.append(f"同国籍 {country} ×{n}  +{1.5 * (n - 1):.1f}")

    ages = [c["age"] for c in roster if c["age"]]
    if len(ages) >= 2:
        spread = max(ages) - min(ages)
        if spread <= 5:
            total += 2.0
            notes.append(f"同代  年龄差 {spread} 岁  +2.0")
        elif spread >= 12:
            total -= 2.0
            notes.append(f"跨代拼凑  年龄差 {spread} 岁  −2.0")

    n_igl = sum(1 for c in roster if c["position"] == "IGL")
    if n_igl >= 2:
        total -= 3.0 * (n_igl - 1)
        notes.append(f"{n_igl} 个指挥抢话  −{3.0 * (n_igl - 1):.1f}")

    return total, notes


def score(roster, rosters):
    fires = sorted((c["firepower"] for c in roster), reverse=True)
    fire = fires[0] * 0.35 + fires[1] * 0.25 + st.mean(fires[2:]) * 0.40

    igls = [c for c in roster if c["position"] == "IGL"]
    if igls:
        best = max(igls, key=lambda c: c["leadership"])
        # 只有最强的那个 IGL 算指挥;其余四人按步枪的领导力算,多塞指挥不再是加成
        others = [c["leadership"] if c["position"] != "IGL" else 25
                  for c in roster if c is not best]
        lead = best["leadership"] * 0.70 + st.mean(others) * 0.30
    else:
        lead = st.mean(c["leadership"] for c in roster) * 0.60

    exp = st.mean(c["experience"] for c in roster)
    stab = st.mean(c["stability"] for c in roster)

    base = fire * 0.40 + lead * 0.20 + exp * 0.20 + stab * 0.20
    if not any(c["position"] == "AWPER" for c in roster):
        base -= 4.0

    chem, notes = chemistry(roster, rosters)
    return {"fire": fire, "lead": lead, "exp": exp, "stab": stab,
            "base": base, "chem": chem, "notes": notes,
            "total": base + chem, "swing": (100 - stab) / 4}


# ----------------------------------------------------------------- 发牌

# 出场权重:全库 648 张卡里 52% 没队伍、44% 在 30 岁以上,板面因此长期被
# 「十年前的无名老哥」占满。这里只改**出场率**,不改任何卡的数值,人也都还在库里。
#
# 两条独立的折扣,相乘:
# - 没队伍(退役/自由身)。G5/G4 不打折——那一档没队的是 f0rest、olofmeister、
#   dupreeh 这些,恰恰是最好认的;G3 往下才是问题。
# - 年龄 ≥30。同理只在低档收紧。
# 唯一的例外:**≤24 岁的自由身是潜力股**,折扣只打一半——年轻没队的说不定
#   正是没被认出来的厉害人,不该跟退役老哥一起沉底。
FREE_AGENT_WEIGHT = {5: 1.0, 4: 0.8, 3: 0.35, 2: 0.25, 1: 0.20}
VETERAN_WEIGHT = {5: 1.0, 4: 0.9, 3: 0.50, 2: 0.40, 1: 0.35}


def draw_weight(c):
    g, age = c["grade"], c["age"]
    w = 1.0
    if not c["team"]:
        w *= FREE_AGENT_WEIGHT[g]
        if (age or 99) <= 24:
            w = (w + 1.0) / 2
    if (age or 0) >= 30:
        w *= VETERAN_WEIGHT[g]
    return w


class Dealer:
    """每批牌 $5..$1 各一张,全局不重复,且保证至少有一个 AWP 和一个 IGL。"""

    def __init__(self, cards, rng):
        self.rng, self.pool = rng, collections.defaultdict(list)
        for c in cards:
            self.pool[c["grade"]].append(c)
        for g in self.pool:
            self._weighted_shuffle(self.pool[g])

    def _weighted_shuffle(self, group):
        """带权无放回抽样(Efraimidis–Spirakis):key = u^(1/w),大的先出。

        列表按 key 升序放好,后面 pop() 拿的就是权重最高的那批,和原来
        「洗牌 + pop」的用法完全一样。
        """
        group.sort(key=lambda c: self.rng.random() ** (1.0 / draw_weight(c)))

    def _draw(self):
        return [self.pool[g].pop() for g in TIERS]

    def board(self):
        for _ in range(40):
            board = self._draw()
            got = {c["position"] for c in board}
            if "AWPER" in got and "IGL" in got:
                return board
            for c in board:                       # 不合格就放回去重洗
                self.pool[c["grade"]].append(c)
            for g in self.pool:                   # 重洗也要带权,否则权重被冲掉
                self._weighted_shuffle(self.pool[g])
        return self._draw()


def affordable(price, left, slots_left):
    """买了这张之后,剩下的席位还得每个至少留 $1。"""
    return price <= left - (slots_left - 1)


# ----------------------------------------------------------------- 一局

def play(dealer, tab, open_mode):
    picked, boards, left, hesitated, passed = [], [], BUDGET, [], []

    for turn in range(1, TURNS + 1):
        slots_left = SLOTS - len(picked)
        if slots_left == 0:
            break
        turns_left = TURNS - turn + 1
        can_pass = turns_left > slots_left

        board = dealer.board()
        boards.append(board)
        print(f"\n── 第 {turn}/{TURNS} 轮    预算 ${left}    还要选 {slots_left} 人"
              f"    {'还能跳过 %d 次' % (turns_left - slots_left) if can_pass else '不能再跳过了'} ──")
        if picked:
            print("   已有:", "  ".join(f"${c['grade']} {c['position']}({c['country']})"
                                        for c in picked))
            have = {c["position"] for c in picked}
            missing = [p for p in ("IGL", "AWPER") if p not in have]
            if missing:
                print("   还缺:", " / ".join(missing),
                      " (缺 AWP 扣 4 分,缺 IGL 领导力打六折)")

        options = []
        for c in board:
            ok = affordable(c["grade"], left, slots_left)
            options.append((c, ok))
            mark = f"  {len(options)})" if ok else "   ✗ "
            print(f"{mark} {face(c, tab, open_mode)}" + ("" if ok else "   预算不够"))
        print(f"  {'s) 跳过这轮,换一批新牌' if can_pass else ''}")

        while True:
            raw = input("选哪张? (编号 / s 跳过,加 ? 表示这轮你犹豫过,如 3?) > ").strip()
            hes = raw.endswith("?")
            raw = raw.rstrip("?").strip().lower()
            if raw == "s" and can_pass:
                passed.append(turn)
                card = None
                break
            if raw.isdigit() and 1 <= int(raw) <= len(options):
                card, ok = options[int(raw) - 1]
                if ok:
                    break
            print("   无效,再来一次。")

        if hes:
            hesitated.append(turn)
        if card is not None:
            picked.append(card)
            left -= card["grade"]

    return picked, boards, left, hesitated, passed


# ----------------------------------------------------------------- 复盘

def all_lineups(boards, rosters):
    """穷举:从看过的每批牌里挑 5 批、每批一张,预算合法。

    跳过的那批牌也在里面——所以「你跳过的那轮到底该不该跳」是能算出来的。
    """
    out = []
    for chosen in itertools.combinations(range(len(boards)), SLOTS):
        for combo in itertools.product(*(boards[i] for i in chosen)):
            if sum(c["grade"] for c in combo) <= BUDGET:
                out.append((score(combo, rosters)["total"], combo))
    out.sort(key=lambda x: -x[0])
    return out


def reveal(picked, boards, left, rosters, cards, passed):
    print("\n" + "=" * 74)
    print("REVEAL")
    print("=" * 74)

    med = {g: st.median([c["overall"] for c in cards if c["grade"] == g]) for g in TIERS}
    for c in picked:
        gap = c["overall"] - med[c["grade"]]
        team = c["team"] or "自由身/退役"
        print(f"  ${c['grade']} {c['position']:<6} {c['nickname']:<13} {c['country']:<12}"
              f" {team:<20} 火{c['firepower']:<3} 领{c['leadership']:<3} "
              f"经{c['experience']:<3} 稳{c['stability']:<3} ({gap:+.1f} vs 同价位)")

    s = score(picked, rosters)
    print(f"\n  火力 {s['fire']:.1f}   领导 {s['lead']:.1f}   经验 {s['exp']:.1f}"
          f"   稳定 {s['stab']:.1f}   基础分 {s['base']:.1f}")
    if not any(c["position"] == "AWPER" for c in picked):
        print("    (没有 AWP,基础分已扣 4)")
    print("  默契:" + ("" if s["notes"] else " 无 —— 五个人互相没打过、也不同国"))
    for n in s["notes"]:
        print("    " + n)
    print(f"  默契合计 {s['chem']:+.1f}")
    print(f"\n  总分 {s['total']:.1f}   单场发挥 {s['total'] - s['swing']:.1f} ~ "
          f"{s['total'] + s['swing']:.1f}   剩余预算 ${left}")

    ranked = all_lineups(boards, rosters)
    totals = [t for t, _ in ranked]
    mine = s["total"]
    better = sum(1 for t in totals if t > mine + 1e-9)

    # ---- 逐轮后悔:其余不变,只换这一轮
    print("\n  逐轮后悔(其余四人不动,只换这一张能到多少分):")
    idx = {id(c): i for i, b in enumerate(boards) for c in b}
    for k, c in enumerate(picked):
        bi = idx[id(c)]
        alts = []
        for alt in boards[bi]:
            combo = list(picked); combo[k] = alt
            if sum(x["grade"] for x in combo) <= BUDGET:
                alts.append((score(combo, rosters)["total"], alt))
        alts.sort(key=lambda x: -x[0])
        regret = alts[0][0] - mine
        best = alts[0][1]
        flag = "   <<< 这张亏最多" if regret > 3 else ""
        print(f"    ${c['grade']} {c['position']:<6} {c['nickname']:<12} 后悔 {regret:5.1f}"
              f"   更该拿 ${best['grade']} {best['position']} {best['nickname']}{flag}")

    # ---- 留钱到底亏多少
    spend = collections.defaultdict(list)
    for t, combo in ranked:
        spend[sum(c["grade"] for c in combo)].append(t)
    print("\n  花掉多少钱 → 那一档的最高分 / 平均分:")
    for money in sorted(spend, reverse=True):
        v = spend[money]
        mark = "  ← 你" if money == BUDGET - left else ""
        print(f"    ${money:<3} 最高 {max(v):5.1f}   平均 {st.mean(v):5.1f}   ({len(v)} 套){mark}")

    print("\n" + "-" * 74)
    print(f"同样这 {len(boards)} 批牌,合法阵容共 {len(ranked)} 套")
    print(f"  你           {mine:6.1f}   第 {better + 1} 名（前 {100 * (better + 1) / len(ranked):.0f}%）")
    print(f"  最优         {totals[0]:6.1f}   "
          f"{'  '.join('$%d %s' % (c['grade'], c['nickname']) for c in ranked[0][1])}")
    print(f"  随便瞎点均值 {st.mean(totals):6.1f}   最差 {totals[-1]:.1f}   标准差 {st.pstdev(totals):.1f}")
    if passed:
        print(f"  你跳过了第 {passed} 轮;上面的穷举把跳过的那几批牌也算进去了,"
              f"所以名次已经把「该不该跳」算在内。")
    print("-" * 74)
    return s, ranked, better


# ----------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None, help="复现同一局板面")
    ap.add_argument("--open", action="store_true", dest="open_mode",
                    help="明牌:卡面直接给四维数字")
    ap.add_argument("--no-log", action="store_true")
    args = ap.parse_args()

    seed = args.seed if args.seed is not None else random.randrange(1 << 30)
    rng = random.Random(seed)
    cards, rosters = load_cards(), load_rosters()
    tab = bands(cards)
    dealer = Dealer(cards, rng)

    print("=" * 74)
    print(f"Blind Draft 原型 v2    预算 ${BUDGET} / {SLOTS} 人 / {TURNS} 轮机会    "
          f"{'明牌' if args.open_mode else '盲选'}    seed={seed}")
    print("=" * 74)
    print(RULES)
    print("每轮 $5..$1 各一张,选一张或跳过。身份赛后揭晓。")

    picked, boards, left, hesitated, passed = play(dealer, tab, args.open_mode)
    s, ranked, better = reveal(picked, boards, left, rosters, cards, passed)

    extra = input("\n这局哪里最难受 / 最有意思?(一句话,可留空) > ").strip()

    if not args.no_log:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "v": 2, "seed": seed, "open": args.open_mode,
                "picks": [{"nickname": c["nickname"], "grade": c["grade"],
                           "position": c["position"]} for c in picked],
                "passed_rounds": passed, "hesitated_rounds": hesitated,
                "spent": BUDGET - left, "total": round(s["total"], 2),
                "chem": round(s["chem"], 2), "rank": better + 1, "of": len(ranked),
                "best": round(ranked[0][0], 2),
                "mean": round(st.mean(t for t, _ in ranked), 2),
                "comment": extra,
            }, ensure_ascii=False) + "\n")
        print(f"\n已记到 {LOG_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
