# -*- coding: utf-8 -*-
"""M2 玩家 Run 的结构化装配。

网页只提交五个 player page 和随机种子；选卡真值、AI 赛场、Entry、对手选择、
Form Roll 和压力机制全部在 Python 这一侧完成。前端不复制任何比赛公式。

**引擎已切到 v2**（`blinddraft.proto_match_v2`，实现设计稿 v0.3）。装配逻辑
整个搬进了 `proto_match_v2.player_run`，这里只剩一层薄封装，因为赛事外壳、
玩家插队和逐人账本在 v2 里是一体的，拆开反而要在两处维护同一套字段。

和 v1 的口径差别，前端能看见的有三处：

  - Entry 是**纯火力**（≈80），不是 v1 那个含 L/E/S 的 ≈65，两者不可比；
  - Stage 归属由**区域 VRS 名额**定，不再按 Entry 排名切 8/16/32；
  - **没有「赛前胜率」了**。v0.3 §13.3 的结论是胜率只能 Monte Carlo 实测、
    不能由 MAP_SCALE 解析推导，所以页面上给一个算出来的百分比是错的。
    改成摊开 Entry / VRS / 本届 Stage，让玩家自己判断这场硬不硬。

v1 的 `blinddraft.match` 没有下线，命令行入口还在用它。
"""
from blinddraft import draft as P
from blinddraft import proto_match_v2 as V2


def build_run(pages, seed=1):
    """跑玩家在真实三段 Swiss 里的路径并返回 JSON；不写文件。"""
    pages = [str(p) for p in pages]
    if len(pages) != P.SLOTS or len(set(pages)) != P.SLOTS:
        raise ValueError("阵容必须是五张不重复的玩家卡")
    known = {c["page"] for c in P.load_cards()}
    missing = [p for p in pages if p not in known]
    if missing:
        raise KeyError("卡库里没有：%s" % "、".join(missing))
    return V2.player_run(pages=pages, seed=seed)
