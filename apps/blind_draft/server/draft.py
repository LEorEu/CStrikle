# -*- coding: utf-8 -*-
"""`/api/draft` —— 把「选人」这一层也收进 Python。

网页只提交 `seed` 和一串**动作**(签第几张 / 放掉这个市场日)。发牌、报价、
球探区间、蓝图全部由 `blinddraft.draft` 算,前端一行玩法逻辑都不写。

**为什么要有这个东西。** 比赛那一层早就只有一份实现了(`/api/run` -> 引擎),
选人这一层没有:`templates/Blind_Draft.html` 里的 `draw()` 是 `Dealer._draw`
的第二次书写。两份规则相同、随机数流不同,同一个 seed 在命令行和网页跑出来
**不是同一局**,而 `test_web_matches_python.py` 只对齐了 Entry,没有任何东西
盯着这个差。新的前端外壳一律走这条 API,不再产生第三份。

**没有会话。** 一局完全由 `(seed, actions)` 决定,所以每次请求把它从头重放
一遍(读库 + 重放实测 ~50ms)。换来的是:服务端不存状态、seed 和命令行的
`--seed` 是同一局、任何一局都能靠一条链接复现。

**盲选的信息边界在这一层,不在前端。** 板面和已签名单只下发能公开的东西——
标价、位置、国籍、一条球探区间、一条身份线索。`page` / `nickname` / 档位 /
四维真值一概不给:前端拿不到,就不可能不小心显示出来,也不可能拿它算分。
签满五人之后才给 `pages`,交给 `/api/run` 跑这一届;揭晓要的完整卡面由那边
的 `roster` 返回,不在这里开第二个出口。
"""
import json
import random

from playerdb.paths import DATA

from blinddraft import draft as P

#: actions 里的「放掉这个市场日」。用 -1 而不是另开一个字段,是因为动作序列
#: 要能原样进 URL 和日志——一局就是 `seed` 加一串小整数。
PASS = -1

IMAGES_PATH = DATA / "images.json"


def _flags() -> dict:
    """国籍 -> 国旗。国籍本来就印在卡面上,给旗子不多泄露任何东西。"""
    if not IMAGES_PATH.exists():
        return {}
    doc = json.loads(IMAGES_PATH.read_text(encoding="utf-8"))
    return doc.get("flags", {})


def _face(card, index, flags) -> dict:
    """一张牌在盲选期能被看见的全部东西。

    真值不在这里出现——不是「前端别显示」,是**后端不发**。
    """
    attr = P.scout_attr(card)
    lo, hi = card["scout"]
    return {
        "index": index,
        "price": card["price"],
        "position": card["position"],
        "country": card["country"],
        "flag": flags.get(card["country"], ""),
        # 这个位置真正值得观察的那一维,只给区间(§球探报告)
        "scout": {"attr": attr, "label": P.ATTR_CN[attr], "lo": lo, "hi": hi},
        # 俱乐部 / Major 次数 / 年龄,三选一,同一个人固定
        "clue": P.identity_clue(card),
    }


#: 首页橱窗里那三张脸。挑他们不是玩法,是为了让人一眼看出库里是真选手。
SHOWCASE = ("S1mple", "ZywOo", "Donk")


def build_showcase() -> dict:
    """首页橱窗:几张**故意翻开**的牌。

    和这个文件里其他东西正好相反——盲选那一层拼命不下发身份,这里主动给
    nickname 和照片。两者不冲突,因为这几张牌**不属于任何一局**:不进 Dealer、
    不消耗卡池、不受 seed 影响,点开也不会改变你接下来会抽到什么。它只是首页
    最大那张卡背后站着谁。

    为什么写在后端而不是前端写死三行:这三个人的每一样东西前端都猜不准。
    `page` 和 `nickname` 大小写不一样(S1mple/s1mple、Donk/donk),照片路径只有
    `images.json` 知道,标价要先读档位。前端猜一次就得维护一份小型选手库,而
    选手库改个名它只会安静地碎掉——正是这个仓库删掉 `data/players.ts` 要躲的事。

    标价取这个档位**最可能**被报的价(不摇骰子),球探区间用固定 rng——橱窗
    每次刷新都换一组数字,会像页面在跳。
    """
    photos, flags = {}, {}
    if IMAGES_PATH.exists():
        doc = json.loads(IMAGES_PATH.read_text(encoding="utf-8"))
        photos, flags = doc.get("players", {}), doc.get("flags", {})

    by_page = {c["page"]: c for c in P.load_cards()}
    rng = random.Random(0)
    out = []
    for page in SHOWCASE:
        card = by_page.get(page)
        if card is None:
            continue                      # 选手库里没有就少一张,不编一个出来
        dist = P.Dealer.price_dist(card["grade"])
        price = max(dist, key=dist.get)
        attr = P.scout_attr(card)
        face = _face(dict(card, price=price,
                          scout=P.scout_range(card[attr], rng)),
                     len(out), flags)
        face["nickname"] = card["nickname"]
        face["photo"] = photos.get(page, "")
        out.append(face)
    return {"cards": out}


def build_draft(seed: int = 1, actions=()) -> dict:
    """把一局盲选重放到当前状态并返回 JSON;不写文件,不留会话。

    `actions[i]` 是第 i+1 个市场日做的事:`0..4` 签板面上的第几张,
    `PASS` 放掉这一天。动作比市场日多、放不该放的一天、签不存在的牌,
    都在这里挡下并报 400,不会安静地滑过去。
    """
    acts = [int(a) for a in actions]
    rng = random.Random(int(seed))
    cards, rosters = P.load_cards(), P.load_rosters()
    dealer = P.Dealer(cards, rng, P.mate_index(rosters))

    picked, left, passed, used = [], P.BUDGET, [], 0
    board, turn = None, 0
    for i in range(P.TURNS):
        slots_left = P.SLOTS - len(picked)
        if slots_left == 0:
            break
        turn = i + 1
        dealt = dealer.board(left, slots_left, picked)
        if used >= len(acts):
            board = dealt          # 停在这批牌上:玩家现在要看的就是它
            break
        a = acts[used]
        used += 1
        if a == PASS:
            if not P.can_pass(turn, slots_left):
                raise ValueError(f"第 {turn} 个市场日不能放:剩下的市场日"
                                 f"刚好够签满 {slots_left} 人")
            passed.append(turn)
        elif 0 <= a < len(dealt):
            picked.append(dealt[a])
            left -= dealt[a]["price"]
        else:
            raise ValueError(f"第 {turn} 个市场日只有 {len(dealt)} 张牌,"
                             f"没有第 {a + 1} 张")
    if used < len(acts):
        raise ValueError(f"动作比市场日多:这局在第 {used} 个动作之后就结束了")

    done = board is None
    slots_left = P.SLOTS - len(picked)
    have = {c["position"] for c in picked}
    flags = _flags()
    out = {
        "seed": int(seed),
        "actions": acts,
        "turn": turn, "turns": P.TURNS,
        "budget": P.BUDGET, "left": left, "spent": P.BUDGET - left,
        "slots": P.SLOTS, "slots_left": slots_left,
        # 本轮上限:后面每个空位至少留 $1。板面已经按它发过牌,给出来是为了
        # 让页面能解释「为什么这批全是便宜卡」
        "max_price": P.max_spend(left, slots_left) if not done else 0,
        "can_pass": (not done) and P.can_pass(turn, slots_left),
        "passes_left": (max(0, P.TURNS - turn + 1 - slots_left) if not done else 0),
        "passed": passed,
        # 缺 AWP 扣分、缺 IGL 拿不到战术执行分,页面要在签人之前就说出来
        "missing": [p for p in ("IGL", "AWPER") if p not in have],
        "board": [_face(c, i, flags) for i, c in enumerate(board or ())],
        "owned": [_face(c, i, flags) for i, c in enumerate(picked)],
        # 引擎给的就是 {tag, note, done, have, want},原样转发
        "blueprints": P.blueprints(picked, slots_left),
        "done": done,
    }
    if done and len(picked) == P.SLOTS:
        # 这里是盲选结束、身份可以翻开的那一刻,也是唯一下发 page 的地方
        out["pages"] = [c["page"] for c in picked]
    return out
