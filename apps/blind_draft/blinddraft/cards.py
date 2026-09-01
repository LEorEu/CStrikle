# -*- coding: utf-8 -*-
"""Blind Draft:把选手库生成成固定选手卡(v0.2 设计稿 §27 的 Step 1/2/3/7)。

    .\.venv\Scripts\python -X utf8 -m blinddraft.cards            # 只体检,不写盘
    .\.venv\Scripts\python -X utf8 -m blinddraft.cards --sample NiKo s1mple
    .\.venv\Scripts\python -X utf8 -m blinddraft.cards --write    # 生成 data/blind_draft/draft_cards.json
    .\.venv\Scripts\python -X utf8 -m blinddraft.cards --spec     # 算法规格 -> 贴进 docs/blind-draft/卡牌与落地记录.md

设计稿 §16.1 要求「卡牌 RNG 只在生成时跑一次,之后永久固定」。这里不靠保存
随机状态来实现,而是让生成器**幂等**:每个人的随机数种子取自
`hash(page + CARD_VERSION)`,同一个人在同一版本下永远算出同一张卡。
否则重跑一次生成脚本,650 张卡会集体悄悄变样,玩家积累的认知全部作废,
而且不会有任何报错——这个项目已经栽过好几次这类静默失败。

改数值请改模板/修正函数,然后**手动 bump CARD_VERSION**,那是一次自觉的
全库重算;不 bump 就只有被改动的那部分公式生效,可以 diff 出来。
"""
import argparse
import collections
import hashlib
import json
import math
import random
import statistics as st
import sys
from pathlib import Path

from playerdb.paths import BLIND_DRAFT, DATA, ROOT
from playerdb.players import PlayerDB, overrides_path

CARD_VERSION = "v6"
OUT_PATH = BLIND_DRAFT / "draft_cards.json"
# 人工平衡层。和 player_overrides.json 并列放在可写卷里,线上后台改完不用重新部署。
OVERRIDE_PATH = BLIND_DRAFT / "draft_overrides.json"
TOP20_PATH = DATA / "hltv_top20.json"

# 设计稿 §17 的 Grade × Position 基础模板:(火力, 领导, 经验, 稳定)
# **AWPER 的火力底板与 RIFLER 持平**(设计稿原表是 +3)。原来的差值意味着同档
# 狙击手天然火力更高,结果是除 NiKo 外所有 G5 狙都压过所有 G5 步枪——一个由
# 模板而非履历造成的系统性错位。狙的特色留在稳定那一列。
TEMPLATE = {
    "RIFLER": {1: (52, 20, 20, 48), 2: (60, 22, 34, 56), 3: (70, 24, 48, 65),
               4: (80, 27, 62, 75), 5: (89, 30, 75, 84)},
    "AWPER":  {1: (52, 18, 20, 51), 2: (60, 20, 34, 60), 3: (70, 22, 48, 70),
               4: (80, 24, 62, 80), 5: (89, 26, 75, 88)},
    "IGL":    {1: (45, 56, 25, 50), 2: (49, 65, 38, 57), 3: (54, 75, 52, 64),
               4: (60, 84, 65, 71), 5: (66, 90, 76, 77)},
}
# 设计稿 §18 的位置权重,只用于内部估值/STEAL 判定,不驱动比赛模拟
# IGL 的领导力权重从 .45 降到 .35:指挥单开证据通道之后,IGL 的 overall 中位数
# 一度升到 53.6,压过步枪 51.5 和狙 52.0——三个位置里最高,和「IGL 限价 $4」
# 会凑成一个新的无脑最优解。降到 .35 后中位数回到 51.6,正好夹在两者之间。
# **这只是定价上的折价,不是说指挥不重要**:按设计文档,指挥的真正价值有一部分
# 在队伍层(Leadership → Map Pool / BP / 战术类 Buff),那部分现在还没实现。
# 等模拟层做出来,要回来重看这个权重,否则就是同一件事折价两次。
WEIGHT = {"RIFLER": (.55, .05, .20, .20),
          "AWPER":  (.45, .05, .20, .30),
          "IGL":    (.25, .35, .35, .05)}
ATTRS = ("firepower", "leadership", "experience", "stability")
# Top20 履历在**同档内**能拉开的火力幅度。档间距离由模板负责,修正项只管档内排序;
# 这个值调大就会侵蚀相邻档位,调到 0 则同档所有人火力只差随机抖动。
FIRE_SPREAD = 6.0

# --- 年度积分:名次分按几何衰减,巅峰权重远大于长寿 ---------------------------
# 上一版用「(6-最好名次)×1.4 + (上榜次数-1)×1.1」,两个毛病:名次只在前 6 有
# 区分度(第 7 和第 20 完全等价),而且次数权重几乎等于名次权重,于是 ZywOo 的
# 4 个年度第一算出来反而低于 s1mple 的 3 个第一 + 5 次中游。
# 现在按每次上榜给分 DECAY**(rank-1),最好的一年全额计入,其余年份只按
# DEPTH 折算——长寿本来就该由 Major 次数去证明 Experience,不该反过来抬火力。
TOP20_DECAY = 0.78          # #1=1.00 #2=.78 #3=.61 #5=.37 #10=.11 #20=.01
TOP20_DEPTH = 0.20          # 非最佳年份的折算权重

# 年代衰减:越久远的上榜记录权重略低。CS 的版本、赛制和对手强度都在变,
# 2013 年的年度第五和 2025 年的年度第五不是同一件事;但也不能压太狠,
# 否则等于给传奇判死刑,和 §14「按生涯代表版本评价」直接冲突——所以只是
# 「稍微低一点」:每早一年 -1.8%,并设 0.78 的地板(最老的 2013 年正好触底)。
# 参照年取快照里最新的年份而不是系统当前年,否则每跨一个自然年全库数值会
# 集体漂移一次,又是一次没有报错的静默变更。
TOP20_RECENCY = 0.018
TOP20_RECENCY_FLOOR = 0.78

# 拿满 FIRE_SPREAD 所需的年度积分,按档位分别锚定。
# 用固定锚点而不是「全库最高分归一化」,是为了保住幂等:按池内最高分归一化的话,
# 新入库一个更强的人会让所有旧卡悄悄变数值,正是这个脚本开头要避免的那种静默失败。
# 锚点是手工常量,改了要 bump CARD_VERSION。G5 锚在 ZywOo/s1mple 级别的履历;
# G4 按定义没有前五,锚点相应低很多,否则整档只能吃到一两点、卡与卡之间没有区别。
FIRE_ANCHOR = {5: 2.00, 4: 0.36, 3: 0.30, 2: 0.30, 1: 0.30}

# 有 Top20 履历的档位不掷骰子:证据已经足够排序,再叠 ±4 的抖动等于让运气盖过
# 履历(上一版 sh1ro 靠 +3.53 的抖动拿到 99,ZywOo 吃 -3.80 掉到 93)。
# G3 及以下证据本就不足,随机是这一档「高方差」定位的一部分,保留。
EVIDENCE_GRADES = (5, 4)

# --- 指挥的证据:另一把尺子 -------------------------------------------------
# HLTV Top20 是个人火力奖,结构性地排除指挥——全库 158 个 IGL 只有 9 个上过榜,
# 却有 20 个拿过 Major 冠军。拿 Top20 给指挥分档的结果是 gla1ve(4 冠)、
# karrigan(2 冠 6 决赛)、pronax(3 冠)全都落在 G3,而带着一个 igl 标签、
# 靠个人数据上榜的枪手占满 G4/G5。所以指挥改用团队荣誉计分:冠军最重,
# 决赛、四强递减,出场次数只作微量的长寿分。
# 这条只**上调**不下调:已经靠 Top20 拿到高档的指挥(FalleN/Snax/Dosia)不受影响。
IGL_TITLE = 1.0             # Major 冠军
IGL_FINAL = 0.4             # 打进决赛(与冠军累加)
IGL_SEMI = 0.2              # 打进四强
IGL_APPEARANCE = 0.02       # 每届出场,只做长寿微调
# (评分下限, 档位),自上而下取第一个满足的
IGL_GRADE_CUT = ((4.2, 5), (2.2, 4), (0.8, 3))
# 指挥的档内排序看领导力,和枪手看火力对称;同样用固定锚点保幂等。
LEAD_SPREAD = 6.0
LEAD_ANCHOR = {5: 6.5, 4: 3.5, 3: 1.6, 2: 1.0, 1: 1.0}


# ----------------------------------------------------------------- 数据准备
def load_top20():
    """-> ({page: [(年份, 名次), …]}, 快照里最新的年份)"""
    years = json.loads(TOP20_PATH.read_text(encoding="utf-8"))["years"]
    ranks = collections.defaultdict(list)
    for year, rows in years.items():
        for row in rows:
            ranks[row["page"]].append((int(year), row["rank"]))
    return ranks, max(int(y) for y in years)


def top20_points(rank: int) -> float:
    return TOP20_DECAY ** (max(int(rank), 1) - 1)


def recency_weight(year: int, ref_year: int) -> float:
    return max(TOP20_RECENCY_FLOOR, 1.0 - TOP20_RECENCY * max(ref_year - year, 0))


def top20_score(entries, ref_year: int) -> float:
    """一份 Top20 履历值多少分:最好的一年全额,其余年份按 TOP20_DEPTH 折算。

    「最好的一年」按年代加权后再比——一个刚拿的年度第三,可以压过十年前的
    年度第二,这正是年代衰减该起作用的地方。
    """
    if not entries:
        return 0.0
    pts = sorted((top20_points(rank) * recency_weight(year, ref_year)
                  for year, rank in entries), reverse=True)
    return pts[0] + TOP20_DEPTH * sum(pts[1:])


def champion_count(p):
    # placement 只记录前八名,空值即「9 名开外」——所以推不出冠军是正确结论,
    # 不是数据缺失。唯一的真缺口是 IEM Katowice 2019,补 data/major_results.json。
    return sum(1 for m in p.majors if str(m.get("placement")) == "1")


def best_major_placement(p) -> int:
    """生涯最好的 Major 名次;从没进过前八返回 99(上游只记录前八)。"""
    best = 99
    for m in (p.majors or []):
        head = str(m.get("placement") or "").split("-")[0]
        if head.isdigit():
            best = min(best, int(head))
    return best


def igl_score(p, ref_year) -> float:
    """指挥的履历分:冠军 > 决赛 > 四强,出场只做长寿微调。

    和 Top20 一样按年代加权:2014 年带队夺冠和 2025 年带队夺冠不是同一件事,
    但地板 0.78 保证老王朝不会被判死刑。
    """
    score = 0.0
    for m in (p.majors or []):
        head = str(m.get("placement") or "").split("-")[0]
        if not head.isdigit():
            continue
        n = int(head)
        w = recency_weight(int(m.get("year") or ref_year), ref_year)
        if n == 1:
            score += IGL_TITLE * w
        if n <= 2:
            score += IGL_FINAL * w
        if n <= 4:
            score += IGL_SEMI * w
    return score + IGL_APPEARANCE * (p.majors_count or 0)


def career_grade(p, ranks, champs, pos=None, ref_year=None):
    """设计稿 §3.2。自上而下互斥,一个人只落一档。

    分档只看「进没进过前五 / 上过几次」,不做年代衰减:Grade 是证据等级,
    2013 年的年度第三也是实打实的超巨证据。年代只影响档内的火力排序。
    指挥另有一套基于团队荣誉的通道,见 igl_score;两条通道取更高的那一档。
    """
    generic = _generic_grade(p, ranks, champs)
    if pos == "IGL" and ref_year is not None:
        score = igl_score(p, ref_year)
        for cut, grade in IGL_GRADE_CUT:
            if score >= cut:
                return max(generic, grade)
            # 分数不够就继续往下试更低的门槛
    return generic


def _generic_grade(p, ranks, champs):
    rs = [rank for _, rank in ranks.get(p.page, [])]
    if rs and min(rs) <= 5:
        return 5                                    # G5 超巨证据
    if len(rs) >= 2:
        return 4                                    # G4 持续高水平
    # G3-B 从「冠军」放宽到「打进过 Major 决赛」:同样是决赛打过一场,赢了升两档、
    # 输了一分不给,是一场 BO3 值 18 点底板火力。亚军也是顶级团队荣誉证据。
    if len(rs) == 1 or champs or best_major_placement(p) <= 2:
        return 3                                    # G3-A 昙花一现 / G3-B 决赛角色球员
    # G3-C 年轻潜力股:年龄本身不构成证据,必须另有 Major 深度。
    # 原规则只要「≤24 岁 + 有队 + Major≥3」就升 G3,占满了 G3 的 44%(48/110),
    # 而其中 36 人一次都没进过 Major 前八——对名额宽松的赛区几乎是白送。
    # 典型症状:TYLOO 的 Jee(21 岁 4 届全部止步 9 名开外)进 G3、底板火力 70,
    # 而同队同战绩的 JamYoung 只因为 25 岁就掉到 G1、底板 52,一个生日 18 点火力。
    # 年轻人该得的是 §15 的档内特色(火力上限 +、稳定 -),不是跨两档。
    if ((p.age() or 99) <= 24 and p.team and p.majors_count >= 3
            and best_major_placement(p) <= 8):
        return 3
    # G2 只看出勤,不看现役:是否在编是**当前状态**,不该改变**生涯证据等级**
    # (§14 一律按生涯代表版本评价)。带这个条件会让打过 4 届 Major 还拿过亚军的
    # 退役选手(JACKZ/nexa/steel/isak)掉到 G1,而 3 届、零深度、只是还在队的
    # 年轻人反而是 G2。
    if p.majors_count >= 3:
        return 2                                    # G2 Major 老兵
    return 1


GAME_TO_DRAFT = {"IGL": "IGL", "AWPer": "AWPER", "Rifler": "RIFLER"}


def played_role_map() -> dict:
    """人工层里标好的选手期位置,按 page 折叠大小写。

    **当前主教练拿不到这个回退**:`playerdb/players.py` 只对助教/分析师/解说
    等非主教练做 played_role 回退,主教练一律保留 Coach(线上要显示他现在
    带哪支队)。所以 gla1ve 这类人在运行时永远是 Coach,人工标好的选手期
    位置对生成器不可见——必须在这里自己读一遍,否则后台已经填过的 12 个人
    会被白白排除。
    """
    raw = json.loads(overrides_path().read_text(encoding="utf-8"))
    return {k.casefold(): v.get("played_role") for k, v in raw.items()
            if isinstance(v, dict) and v.get("played_role")}


def draft_position(p, played_roles: dict | None = None):
    """设计稿 §9/§10:只保留三职位,IGL > AWPER > RIFLER。

    优先级是 **played_role > primary_role > roles 裸标签**,顺序不能反。
    主游戏的 `game_role` 是「当前身份」(Magisk 现在是 BC.Game 的指挥、
    gla1ve 现在是 100T 的教练),而 Draft 按 §14 Career Peak Rule 要的是
    「生涯代表版本」(Magisk = Astralis 时期的步枪手)。人工层里 `played_role`
    这个字段的语义正好就是选手期位置,所以它在这里必须压过 game_role;
    反过来读会让所有转型选手拿到错的模板。
    回退不到的教练返回 None,不进卡池:让一个教练顶着 RIFLER 的火力模板
    上场,是买回去必坑的死牌。
    """
    manual = (played_roles or {}).get((p.page or "").casefold())
    if manual in GAME_TO_DRAFT:
        return GAME_TO_DRAFT[manual]
    role = p.primary_role
    if role in GAME_TO_DRAFT:
        return GAME_TO_DRAFT[role]
    for raw in (p.roles or []):                     # 少数教练的 roles 里还留着位置
        low = raw.lower()
        if "igl" in low:
            return "IGL"
        if "awp" in low or "snip" in low:
            return "AWPER"
        if "rifle" in low or low in ("entry", "lurker", "support"):
            return "RIFLER"
    return None


# ------------------------------------------------------------------- 生成
def _rng(page):
    seed = hashlib.blake2b(f"{page}|{CARD_VERSION}".encode("utf-8"),
                           digest_size=8).hexdigest()
    return random.Random(int(seed, 16))


def corrections(p, grade, pos, ranks, champs, ref_year):
    """设计稿 §20:在基础模板上做有限修正,只定方向不追求还原真实 rating。

    返回四维的增量。原则:Top20 证明火力、Major 证明经验、冠军证明经验与
    (IGL 的)领导、年轻人换的是上限与不稳定。
    """
    entries = ranks.get(p.page, [])
    d = dict.fromkeys(ATTRS, 0.0)

    # Top20 已经参与了 Grade 判定,这里只在同档内拉开,不能重复计一次大的。
    if entries:
        # IGL 只继承一部分,避免「明星历史 + IGL 模板」叠成六边形怪物(§11.1)
        share = min(top20_score(entries, ref_year) / FIRE_ANCHOR[grade], 1.0)
        d["firepower"] += share * FIRE_SPREAD * (0.4 if pos == "IGL" else 1.0)

    # Major 参加次数 → 经验,log 曲线做边际递减:2→5 次意义明显,18→22 次几乎没有
    if p.majors_count:
        d["experience"] += 9 * math.log1p(p.majors_count) / math.log(21)

    # 冠军 → 经验
    if champs:
        d["experience"] += min(champs, 4) * 1.5

    # 指挥的档内排序看领导力,和枪手看火力对称:同档之内,带队夺冠越多、
    # 进决赛越多的指挥领导力越高。原来只按「冠军数 × 1」加,封顶 4 点,
    # karrigan(2 冠 6 决赛)和一个 1 冠 1 决赛的人几乎没有区别。
    if pos == "IGL":
        share = min(igl_score(p, ref_year) / LEAD_ANCHOR[grade], 1.0)
        d["leadership"] += share * LEAD_SPREAD

    # §15:年轻人拿到的是特色而不是老人拿惩罚——上限更高,兑现更飘。
    # 火力加成只给证据不足的档:G5/G4 的上限已经被 Top20 证明过了,再加一次
    # 「可能还会更强」就是同一件事记两遍(上一版 m0NESY 因此算到 100.0 被截断,
    # 顶到天花板等于和任何更强的人都不可区分)。波动惩罚对所有档都保留——
    # 年轻人打得飘是事实,和证据多少无关。
    age = p.age()
    if age is not None and age <= 22:
        if grade not in EVIDENCE_GRADES:
            d["firepower"] += 2.5
        d["stability"] -= 5.0
    return d


#: 人工层允许覆盖的字段。`grade`/`position` 在套模板之前生效,四维在之后替换;
#: 其余键(reason / draft_exclude)是**元数据,不上卡**。
OVERRIDABLE = ATTRS + ("grade", "position")


def build_card(p, grade, pos, ranks, champs, overrides, ref_year, trace=False):
    """Algorithm First, Override Last(§21)。

    位置和档位的人工修正必须**在套模板之前**生效:放在最后 update 只会换掉
    标签,四维仍旧来自被否掉的那套模板——Magisk 改成 RIFLER 却还顶着 IGL
    模板的领导 97,是最难发现的一种错。
    位置真值优先在 `data/manual/player_overrides.json` 的 `played_role` 里改
    (那个字段就是选手期位置,且不影响主游戏显示);这里的 position 只是
    平衡层的应急出口。

    `trace=True` 时额外挂一份 `_trace`,记下每一维是怎么算出来的
    (模板 → 履历修正 → 抖动 → 人工覆盖)以及背后的证据。后台的卡牌页靠它
    展示推导过程——**必须走这条同一份代码**,在服务端另抄一遍公式就等于
    埋了一个迟早会和生成器对不上的第二实现。`_trace` 不写进 draft_cards.json。
    """
    ov = dict(overrides.get(p.page, {}))
    auto_grade, auto_pos = grade, pos
    grade = int(ov.pop("grade", grade))
    pos = ov.pop("position", pos)
    base = TEMPLATE[pos][grade]
    delta = corrections(p, grade, pos, ranks, champs, ref_year)
    rng = _rng(p.page)
    evidence = grade in EVIDENCE_GRADES
    card, steps = {}, {}
    for i, key in enumerate(ATTRS):
        # 同一张卡的随机只在这里发生一次,种子来自 page + 版本号,可重现
        if evidence:
            jitter = 0.0
        else:
            jitter = rng.uniform(-4, 4) if key == "firepower" else rng.uniform(-3, 3)
        card[key] = max(1, min(99, round(base[i] + delta[key] + jitter)))
        # 不在这里四舍五入:trace 里存原值,显示端自己截位。存成两位小数的话
        # 「模板 + 履历 + 抖动」在边界上会加不回自动值,而这份 trace 的全部
        # 意义就是让人能把这笔账算平。
        steps[key] = {"base": base[i], "delta": delta[key],
                      "jitter": jitter, "auto": card[key]}
    card.update(page=p.page, nickname=p.nickname, position=pos, grade=grade,
                country=p.country, team=p.team, age=p.age(),
                majors=p.majors_count, champions=champs,
                titles=[(m["event"], (m.get("team") or "").lower())
                        for m in (p.majors or []) if str(m.get("placement")) == "1"])
    # 只让四维参与覆盖。原先是 `card.update(ov)`,于是 override 里的 reason
    # 会一路并进卡、再被卡带进 AI 名单和导出的网页——一个只在肉眼看 JSON 时
    # 才发现得了的污染。
    for key in ATTRS:
        if key in ov:
            card[key] = max(1, min(99, int(ov[key])))
    card["overall"] = round(sum(card[k] * w for k, w in zip(ATTRS, WEIGHT[pos])), 1)
    if trace:
        for key in ATTRS:
            steps[key]["override"] = ov.get(key)
            steps[key]["final"] = card[key]
        card["_trace"] = {
            "grade": {"auto": auto_grade, "final": grade},
            "position": {"auto": auto_pos, "final": pos},
            "attrs": steps,
            "weight": dict(zip(ATTRS, WEIGHT[pos])),
            "jitter": not evidence,
            "evidence": {
                "top20": sorted(ranks.get(p.page, []), reverse=True),
                "top20_score": round(top20_score(ranks.get(p.page, []), ref_year), 3),
                "fire_anchor": FIRE_ANCHOR[grade],
                "igl_score": round(igl_score(p, ref_year), 3),
                "lead_anchor": LEAD_ANCHOR[grade],
                "majors": p.majors_count, "champions": champs,
                "best_placement": best_major_placement(p), "age": p.age(),
            },
            "reason": ov.get("reason", ""),
        }
    return card


def write_cards(cards) -> Path:
    """写出生成物。`_trace` 只服务于后台展示,不进文件。"""
    clean = [{k: v for k, v in c.items() if k != "_trace"} for c in cards]
    OUT_PATH.write_text(json.dumps(
        {"card_version": CARD_VERSION, "count": len(clean), "cards": clean},
        ensure_ascii=False, indent=1), encoding="utf-8")
    return OUT_PATH


def load_overrides() -> dict:
    return (json.loads(OVERRIDE_PATH.read_text(encoding="utf-8"))
            if OVERRIDE_PATH.exists() else {})


def generate(trace=False):
    """-> (卡牌, 待定位置的人, 人工确认排除的人)

    「待定」和「确认排除」必须分开:前者是还没人看过、看完可能进池的,后者是
    人工判定过就不该进池的(纯教练、彩蛋角色)。混在一起的话每次体检都要重新
    辨认哪些已经处理过,时间一长就没人看了。
    """
    db = PlayerDB()
    ranks, ref_year = load_top20()
    played = played_role_map()
    overrides = load_overrides()
    excluded = {k for k, v in overrides.items()
                if isinstance(v, dict) and v.get("draft_exclude")}
    cards, pending, confirmed = [], [], []
    for p in db.players:
        if p.page in excluded:
            confirmed.append(p.nickname)
            continue
        pos = draft_position(p, played)
        if pos is None:
            pending.append(p.nickname)
            continue
        champs = champion_count(p)
        cards.append(build_card(p, career_grade(p, ranks, champs, pos, ref_year),
                                pos, ranks, champs, overrides, ref_year, trace))
    return cards, pending, confirmed


# ------------------------------------------------------------------- 规格
SPEC_BEGIN = "<!-- SPEC:BEGIN 由 blinddraft/cards.py --spec 生成,勿手改 -->"
SPEC_END = "<!-- SPEC:END -->"


def spec_markdown() -> str:
    """把全部常量和判定顺序导出成 Markdown,嵌进设计文档。

    手抄一份常量到文档里,迟早会和代码对不上,而且不会有任何报错——这个项目
    今晚一路修的就是这类静默漂移。所以文档里那一块由本函数生成,
    `tests/test_draft_cards.py` 会断言两边一字不差。
    """
    def tbl(d, keys):
        rows = []
        for k in keys:
            rows.append("| " + str(k) + " | " + " | ".join(str(x) for x in d[k]) + " |")
        return "\n".join(rows)

    lines = [SPEC_BEGIN, "", f"**CARD_VERSION = `{CARD_VERSION}`**", "",
             "### 判定顺序", "", "```"]
    lines += [
        "1. 位置    played_role(人工层) > primary_role(主游戏) > roles 裸标签",
        "           三者都拿不到 → 不进卡池(待定);draft_exclude 命中 → 确认排除",
        "2. 档位    通用通道 与 指挥通道 取更高的一档",
        "3. 模板    TEMPLATE[位置][档位] 给出四维底板",
        "4. 修正    corrections() 的增量(见下)",
        "5. 抖动    档位 ∈ EVIDENCE_GRADES 时为 0;否则火力 ±4、其余 ±3",
        "           种子 = blake2b(page + CARD_VERSION),同一版本下永远同一张卡",
        "6. 取整    round() 后夹在 [1, 99]",
        "7. 覆盖    draft_overrides.json;其中 grade/position 在第 3 步之前生效,",
        "           四维为直接替换。overall 最后按覆盖后的值重算",
        "```", "",
        "### 通用档位(自上而下互斥,取第一个满足的)", "", "```",
        "G5  HLTV Top20 进过前五",
        "G4  Top20 上榜 >= 2 次",
        "G3  上榜 1 次 或 有 Major 冠军 或 打进过 Major 决赛(最好名次 <= 2)",
        "G3  或 年龄 <= 24 且 当前有队 且 Major >= 3 且 最好名次 <= 8",
        "G2  Major >= 3 次",
        "G1  其余",
        "",
        "名次取自 majors[].placement。上游只记录前八名,空值即「9 名开外」,",
        "所以「推不出冠军」是正确结论而不是数据缺失。",
        "```", "",
        "### 指挥通道(只上调,不下调)", "", "```",
        f"igl_score = Σ(冠军 {IGL_TITLE} + 决赛 {IGL_FINAL} + 四强 {IGL_SEMI}) × 年代权重",
        f"            + 出场次数 × {IGL_APPEARANCE}",
        "门槛      " + "   ".join(f">= {cut} → G{g}" for cut, g in IGL_GRADE_CUT),
        "```", "",
        "### 年代权重(Top20 与指挥通道共用)", "", "```",
        f"weight(年份) = max({TOP20_RECENCY_FLOOR}, 1 - {TOP20_RECENCY} × (参照年 - 年份))",
        "参照年 = hltv_top20.json 快照里最新的年份,不用系统当前年——否则每跨一个",
        "自然年全库数值会集体漂移一次。",
        "```", "",
        "### 四维修正 corrections()", "", "```",
        f"火力   有 Top20 时: min(top20_score / FIRE_ANCHOR[档], 1) × {FIRE_SPREAD}",
        "       其中 top20_score = 最好一年的名次分 + 其余年份 × " + str(TOP20_DEPTH),
        f"       名次分 = {TOP20_DECAY} ^ (名次 - 1),再乘年代权重",
        "       位置为 IGL 时只继承 0.4 倍(避免明星履历 + IGL 模板叠成六边形怪物)",
        "经验   Major 次数 → 9 × log1p(次数) / log(21)   边际递减",
        "       每个冠军 +1.5(最多计 4 个)",
        f"领导   位置为 IGL 时: min(igl_score / LEAD_ANCHOR[档], 1) × {LEAD_SPREAD}",
        "火力   年龄 <= 22 且档位不在 EVIDENCE_GRADES: +2.5",
        "稳定   年龄 <= 22: -5(不分档位,打得飘是事实,和证据多少无关)",
        "```", "",
        "### 常量", "",
        "| 常量 | 值 | 作用 |",
        "|---|---|---|",
        f"| `FIRE_SPREAD` | {FIRE_SPREAD} | Top20 履历在同档内能拉开的火力幅度 |",
        f"| `LEAD_SPREAD` | {LEAD_SPREAD} | 团队荣誉在同档内能拉开的领导力幅度 |",
        f"| `TOP20_DECAY` | {TOP20_DECAY} | 名次分几何衰减,#1=1.00 #5={TOP20_DECAY**4:.2f} #10={TOP20_DECAY**9:.2f} |",
        f"| `TOP20_DEPTH` | {TOP20_DEPTH} | 非最佳年份的折算权重 |",
        f"| `TOP20_RECENCY` | {TOP20_RECENCY} | 每早一年的衰减 |",
        f"| `TOP20_RECENCY_FLOOR` | {TOP20_RECENCY_FLOOR} | 年代权重地板 |",
        f"| `FIRE_ANCHOR` | {FIRE_ANCHOR} | 拿满 FIRE_SPREAD 所需的年度积分 |",
        f"| `LEAD_ANCHOR` | {LEAD_ANCHOR} | 拿满 LEAD_SPREAD 所需的指挥分 |",
        f"| `EVIDENCE_GRADES` | {EVIDENCE_GRADES} | 这些档位不掷骰子 |",
        "",
        "锚点是**固定常量**而不是「池内最高分」:按池内最高归一化的话,将来入库一个",
        "更强的人会让全库旧卡悄悄变数值。改这些值要手动 bump `CARD_VERSION`。", "",
        "### Grade × Position 模板 (火力/领导/经验/稳定)", "",
        "| 档 | " + " | ".join(TEMPLATE) + " |",
        "|---|" + "---|" * len(TEMPLATE),
    ]
    for g in (5, 4, 3, 2, 1):
        lines.append(f"| G{g} | " + " | ".join(
            "/".join(str(x) for x in TEMPLATE[pos][g]) for pos in TEMPLATE) + " |")
    lines += ["", "### 位置权重(只用于内部估值 / STEAL 判定,不驱动比赛模拟)", "",
              "| 位置 | 火力 | 领导 | 经验 | 稳定 |", "|---|---|---|---|---|",
              tbl(WEIGHT, list(WEIGHT)), "", SPEC_END]
    return "\n".join(lines)


# ------------------------------------------------------------------- 体检
def audit(cards, pending, confirmed):
    print("=" * 72)
    print(f"卡池 {len(cards)} 张 | 待定位置 {len(pending)} 人 | "
          f"人工确认排除 {len(confirmed)} 人")
    print("=" * 72)

    grid = collections.Counter((c["grade"], c["position"]) for c in cards)
    cols = ("RIFLER", "AWPER", "IGL")
    print(f"{'':4s}" + "".join(f"{c:>9s}" for c in cols) + f"{'合计':>8s}")
    for g in (5, 4, 3, 2, 1):
        n = sum(grid[(g, c)] for c in cols)
        print(f"G{g}  " + "".join(f"{grid[(g, c)]:9d}" for c in cols) + f"{n:8d}")

    print("\n各档四维分布(中位数)与 overall 区间:")
    print(f"{'':4s}{'火力':>7s}{'领导':>7s}{'经验':>7s}{'稳定':>7s}"
          f"{'overall 最低~中位~最高':>26s}")
    for g in (5, 4, 3, 2, 1):
        grp = [c for c in cards if c["grade"] == g]
        med = [st.median([c[k] for c in grp]) for k in ATTRS]
        ov = sorted(c["overall"] for c in grp)
        print(f"G{g}  " + "".join(f"{m:7.0f}" for m in med)
              + f"{ov[0]:14.1f} ~{st.median(ov):6.1f} ~{ov[-1]:6.1f}")

    print("\n各位置 overall 中位(检查 AWP 是否统治 / IGL 是否被火力压死):")
    for pos in cols:
        grp = [c["overall"] for c in cards if c["position"] == pos]
        print(f"  {pos:7s} n={len(grp):3d}  中位 {st.median(grp):5.1f}  "
              f"最高 {max(grp):5.1f}")

    print("\noverall 前 15(眼睛过一遍,认不出来的名字越多说明公式越可疑):")
    for c in sorted(cards, key=lambda x: -x["overall"])[:15]:
        print(f"  {c['overall']:5.1f}  G{c['grade']} {c['position']:6s} "
              f"{c['nickname']:16s} 火{c['firepower']:3d} 领{c['leadership']:3d} "
              f"经{c['experience']:3d} 稳{c['stability']:3d}")

    squads = collections.defaultdict(list)
    for c in cards:
        for ev, team in c.get("titles", []):
            squads[(ev, team)].append((c["nickname"], c["position"]))
    multi = {k: [n for n, pos in v if pos == "IGL"] for k, v in squads.items()}
    multi = {k: v for k, v in multi.items() if len(v) > 1}
    if multi:
        print("\n⚠ 冠军阵容多指挥(一支队不可能有两个指挥,说明有人位置标错):")
        for (ev, team), names in sorted(multi.items()):
            print(f"  {ev[:38]:38s} {team:14s} {'、'.join(names)}")
    else:
        print("\n冠军阵容指挥唯一性检查:通过")

    g1 = [c["overall"] for c in cards if c["grade"] == 1]
    g5 = [c["overall"] for c in cards if c["grade"] == 5]
    print(f"\n经济锚点:G5 中位 {st.median(g5):.1f} / G1 中位 {st.median(g1):.1f} "
          f"= {st.median(g5) / st.median(g1):.2f} 倍(价格差 5 倍)")
    print("  → 每 1 块钱换到的 overall,决定 Rogue Buff 的定价上限")
    if pending:
        print(f"\n待定位置({len(pending)}):{'、'.join(pending)}"
              "  ← 在人工层填 played_role 就会自动进池")
    if confirmed:
        print(f"人工确认排除({len(confirmed)}):{'、'.join(confirmed)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="写出 data/blind_draft/draft_cards.json")
    ap.add_argument("--sample", nargs="*", metavar="ID", help="只看这几个人的卡")
    ap.add_argument("--spec", action="store_true",
                    help="打印算法规格(Markdown),嵌进 docs/blind-draft/卡牌与落地记录.md")
    args = ap.parse_args()

    if args.spec:
        print(spec_markdown())
        return

    cards, pending, confirmed = generate()
    if args.sample:
        want = {s.casefold() for s in args.sample}
        for c in cards:
            if c["nickname"].casefold() in want or c["page"].casefold() in want:
                print(json.dumps(c, ensure_ascii=False, indent=2))
        return
    audit(cards, pending, confirmed)
    if args.write:
        print(f"\n已写入 {write_cards(cards).relative_to(ROOT)}")
    else:
        print("\n(只体检,没写盘。确认没问题后加 --write)")


if __name__ == "__main__":
    main()
