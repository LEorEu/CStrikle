# -*- coding: utf-8 -*-
"""M2 玩家 Run 的结构化装配。

网页只提交五个 player page 和随机种子；选卡真值、AI 赛场、Entry、对手选择、
Form Roll 和压力机制全部在 Python 这一侧完成。前端不复制任何比赛公式。

**引擎是 v2**（`blinddraft.engine`，实现设计稿 v0.3）。装配逻辑整个在
`engine.run.player_run`，这里只剩一层薄封装，因为赛事外壳、玩家插队和逐人
账本在 v2 里是一体的，拆开反而要在两处维护同一套字段。

和已退役的 v1 相比，前端能看见的口径差有三处（旧截图和旧文档还留着 v1 的数）：

  - Entry 是**纯火力**（≈80），不是 v1 那个含 L/E/S 的 ≈65，两者不可比；
  - Stage 归属由**区域 VRS 名额**定，不再按 Entry 排名切 8/16/32；
  - **没有「赛前胜率」了**。v0.3 §13.3 的结论是胜率只能 Monte Carlo 实测、
    不能由 MAP_SCALE 解析推导，所以页面上给一个算出来的百分比是错的。
    改成摊开 Entry / VRS / 本届 Stage，让玩家自己判断这场硬不硬。

v1（`blinddraft.match`）已退役删除，比赛引擎现在只有一处。
"""
import json

from playerdb.paths import DATA

from blinddraft import draft as P
from blinddraft import engine as V2

IMAGES_PATH = DATA / "images.json"

#: 这一层唯一允许往引擎输出里加的东西:图片地址。
#:
#: 照片和国旗是**显示**,不是比赛数据——引擎不该为了让页面好看去读
#: `images.json`,否则命令行跑一局也要顺带打开图片索引。反过来,比赛的每个数
#: 都必须原样来自引擎:`test_player_run.py` 按这个白名单校验,加进来的键只能
#: 是这两个,已有的键一个都不许动。
PRESENTATION_KEYS = ("photo", "flag")


def _images() -> tuple:
    """(page -> 照片, 国籍 -> 国旗)。路径是相对的,前端自己拼 /img/。"""
    if not IMAGES_PATH.exists():
        return {}, {}
    doc = json.loads(IMAGES_PATH.read_text(encoding="utf-8"))
    return doc.get("players", {}), doc.get("flags", {})


def build_run(pages, seed=1):
    """跑玩家在真实三段 Swiss 里的路径并返回 JSON；不写文件。"""
    pages = [str(p) for p in pages]
    if len(pages) != P.SLOTS or len(set(pages)) != P.SLOTS:
        raise ValueError("阵容必须是五张不重复的玩家卡")
    known = {c["page"] for c in P.load_cards()}
    missing = [p for p in pages if p not in known]
    if missing:
        raise KeyError("卡库里没有：%s" % "、".join(missing))

    data = V2.player_run(pages=pages, seed=seed)
    photos, flags = _images()
    # 身份已经翻开了才配照片——盲选期那条线在 `bdserver/draft.py`,那边一张都不发。
    roster = [c | {"photo": photos.get(c["page"], ""),
                   "flag": flags.get(c["country"], "")}
              for c in data["roster"]]
    return data | {"roster": roster}
