# -*- coding: utf-8 -*-
"""Blind Draft 调参后台 —— 卡牌页。

    uvicorn bdserver.main:app --host 127.0.0.1 --port 8621

这是**本地工具**,不上线,不进任何镜像(`.dockerignore` 已经整个排掉
`apps/blind_draft`)。它解决的是一个具体问题:卡牌数值以前只能靠命令行
`python -m blinddraft.cards --sample NiKo` 一个个看,想调一个数得手改 JSON、
重跑、再肉眼比对全库有没有被带歪。

三条设计约束,都是从 `blinddraft/cards.py` 的注释里直接继承的:

1. **不写生成物。** 后台只写人工层 `draft_overrides.json`,`draft_cards.json`
   永远由 `cards.generate()` 产出。手填进生成物的数会在下一次 `--write`
   时静默消失——这个项目已经栽过好几次这类静默失败。

2. **每次请求实时重算,不存中间态。** 实测全库 647 张 0.15s。页面显示的
   就是引擎读的那份,结构上不可能漂。反过来说,**已提交的
   `draft_cards.json` 会和实时结果不一致**(选手库刷新过、公式改过),
   所以有一个「待发布」清单专门盯这个差。

3. **推导过程要看得见。** 每一维展开成 模板 → 履历修正 → 抖动 → 人工覆盖,
   数据来自 `build_card(trace=True)` 这条**同一份代码**。在服务端另抄一遍
   公式就等于埋了个迟早对不上的第二实现。

改人工层要填理由(§21 Algorithm First, Override Last):算法算错了才覆盖,
不是逐个人工打分。理由为空的写入会被拒绝。
"""
import json
import os
import statistics as st
import threading
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from playerdb.paths import BLIND_DRAFT, DATA, IMG
from blinddraft import cards as C

from . import ai as AI
from . import anchor as AN

STATIC = Path(__file__).resolve().parents[1] / "static"
IMAGES_PATH = DATA / "images.json"

#: 可选口令。本地工具默认不开;要在局域网里开给别人看就设上。
TOKEN = os.environ.get("BD_TOKEN", "")

#: 发布对比只看这些字段——`titles` 之类的派生列表跟着选手库走,不是调参的对象。
PUBLISHED = ("firepower", "leadership", "experience", "stability",
             "grade", "position", "overall")

app = FastAPI(title="blind-draft-admin")
_lock = threading.Lock()
_cache: dict = {"key": None, "cards": None, "pending": None, "confirmed": None}


# --------------------------------------------------------------- 实时重算
def _mtimes() -> tuple:
    """缓存键:任何一个输入文件动过就重算。

    比「保存后手动失效」可靠——`players.json` 是被别的进程(爬虫、猜选手的
    管理页)改的,后台自己不知道。
    """
    out = []
    for p in (C.OVERRIDE_PATH, C.TOP20_PATH, DATA / "players.json",
              DATA / "manual" / "player_overrides.json"):
        out.append(p.stat().st_mtime_ns if p.exists() else 0)
    return tuple(out)


def live():
    """-> (cards, pending, confirmed),带 `_trace`。"""
    with _lock:
        key = _mtimes()
        if _cache["key"] != key:
            cards, pending, confirmed = C.generate(trace=True)
            _cache.update(key=key, cards=cards, pending=pending,
                          confirmed=confirmed)
        return _cache["cards"], _cache["pending"], _cache["confirmed"]


def published() -> dict:
    """已提交的 draft_cards.json,page -> 卡。"""
    if not C.OUT_PATH.exists():
        return {}
    doc = json.loads(C.OUT_PATH.read_text(encoding="utf-8"))
    return {c["page"]: c for c in doc.get("cards", [])}


def diff_against_published(cards, pending=(), confirmed=()) -> list:
    """实时结果和已提交文件的差。

    差的来源有两种,页面上要分得清:改了人工层(意料之中,等着发布),
    以及选手库在背后刷新过(意料之外——Ultimate 多打了一届 Major 就升了
    一档,而卡库文件还停在上一次 --write)。

    「消失」尤其要给出原因。一张卡从卡库里没了只有两条路径:选手库那边的
    位置判不出来了(落进 pending),或者被人工排除。光报一个「steel 消失」
    没法判断该不该发布。
    """
    old = published()
    out = []
    for c in cards:
        o = old.get(c["page"])
        if o is None:
            out.append({"page": c["page"], "nickname": c["nickname"],
                        "kind": "added", "fields": [], "why": ""})
            continue
        fields = [{"key": k, "was": o.get(k), "now": c.get(k)}
                  for k in PUBLISHED if o.get(k) != c.get(k)]
        if fields:
            out.append({"page": c["page"], "nickname": c["nickname"],
                        "kind": "changed", "fields": fields, "why": ""})
    live_pages = {c["page"] for c in cards}
    pend = {n.casefold() for n in pending}
    conf = {n.casefold() for n in confirmed}
    for page, o in old.items():
        if page in live_pages:
            continue
        nick = o.get("nickname", page)
        if nick.casefold() in pend:
            why = "位置判不出来,落进「待定」——选手库里的 roles 变了"
        elif nick.casefold() in conf:
            why = "人工排除出卡池(draft_exclude)"
        else:
            why = "选手库里已经没有这个人了"
        out.append({"page": page, "nickname": nick, "kind": "removed",
                    "fields": [], "why": why})
    return out


def stats(cards) -> dict:
    """全库分布。调一张卡很容易把整档带歪,所以这几个数得一直在眼前。

    `cards.py` 的注释里反复在用这组数字做判断(「IGL 的 overall 中位数一度
    升到 53.6,压过步枪 51.5」),以前得手写脚本才算得出来。
    """
    by_pos, by_grade = {}, {}
    for c in cards:
        by_pos.setdefault(c["position"], []).append(c["overall"])
        by_grade.setdefault(c["grade"], []).append(c["overall"])
    fmt = lambda d: {str(k): {"n": len(v), "median": round(st.median(v), 1),
                              "max": max(v), "min": min(v)}
                     for k, v in sorted(d.items(), key=lambda x: str(x[0]))}
    return {"position": fmt(by_pos), "grade": fmt(by_grade), "total": len(cards)}


# ------------------------------------------------------------------- 人工层
def _load_raw() -> dict:
    return C.load_overrides()


def _save_raw(data: dict) -> None:
    """原子写。半个 JSON 文件会让 `cards.generate()` 直接崩,而它同时是
    命令行和后台的入口——两边一起坏。"""
    tmp = C.OVERRIDE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    tmp.replace(C.OVERRIDE_PATH)


def require_admin(token: str = "") -> None:
    if TOKEN and token != TOKEN:
        raise HTTPException(status_code=403, detail="口令不对")


class AnchorBody(BaseModel):
    #: 他**现在**是不是处在生涯巅峰。只有 True 的人才进曲线拟合。
    peak: bool | None = None
    #: 他**巅峰时**的火力。和 peak 分开填——见 bdserver/anchor.py。
    firepower: int | None = None
    note: str = ""
    teams: int = AN.DEFAULT_TEAMS


class OverrideBody(BaseModel):
    grade: int | None = None
    position: str | None = None
    firepower: int | None = None
    leadership: int | None = None
    experience: int | None = None
    stability: int | None = None
    draft_exclude: bool = False
    reason: str = ""


def _clean(body: OverrideBody) -> dict:
    ov = {}
    if body.grade is not None:
        if body.grade not in C.TEMPLATE["RIFLER"]:
            raise HTTPException(400, "grade 只能是 1-5")
        ov["grade"] = body.grade
    if body.position is not None:
        if body.position not in C.TEMPLATE:
            raise HTTPException(400, "position 只能是 RIFLER / AWPER / IGL")
        ov["position"] = body.position
    for key in C.ATTRS:
        v = getattr(body, key)
        if v is not None:
            if not 1 <= v <= 99:
                raise HTTPException(400, f"{key} 只能是 1-99")
            ov[key] = v
    if body.draft_exclude:
        ov = {"draft_exclude": True}          # 排除了就没有数值可言
    if ov and not body.reason.strip():
        # §21:算法明显算错了才覆盖。留不下理由的覆盖,三个月后没人知道
        # 能不能删,于是永远删不掉,算法就这么一点点被架空。
        raise HTTPException(400, "要填理由:算法哪里算错了")
    if ov:
        ov["reason"] = body.reason.strip()
    return ov


# -------------------------------------------------------------------- 路由
@app.get("/")
def index():
    return FileResponse(STATIC / "cards.html")


@app.get("/ai")
def ai_page():
    return FileResponse(STATIC / "ai.html")


@app.get("/anchor")
def anchor_page():
    return FileResponse(STATIC / "anchor.html")


@app.get("/api/anchor")
def api_anchor(teams: int = AN.DEFAULT_TEAMS):
    """打锚台。**这一页写人工层**——和只读的 AI 页不同,理由见 bdserver/anchor.py。"""
    return AN.build_view(teams)


@app.put("/api/anchor/{key:path}")
def api_anchor_put(key: str, body: AnchorBody,
                   x_admin_token: str = Header(default="", alias="X-Admin-Token")):
    require_admin(x_admin_token)
    try:
        saved = AN.put(key, body.peak, body.firepower, body.note, body.teams)
    except KeyError:
        raise HTTPException(404, f"候选集里没有 {key}——键拼错了?")
    return {"ok": True, "key": key, "anchor": saved,
            "counts": AN.build_view(body.teams)["counts"]}


@app.get("/api/ai")
def api_ai():
    """AI 对手赛场。只读——理由写在 `bdserver/ai.py` 的模块注释里。"""
    return AI.build_view()


@app.get("/api/cards")
def api_cards():
    cards, pending, confirmed = live()
    ov = _load_raw()
    images = (json.loads(IMAGES_PATH.read_text(encoding="utf-8"))
              if IMAGES_PATH.exists() else {"players": {}, "flags": {}})
    rows = []
    for c in cards:
        row = dict(c)
        row["override"] = {k: v for k, v in ov.get(c["page"], {}).items()
                           if k != "_note"}
        row["photo"] = images.get("players", {}).get(c["page"], "")
        row["flag"] = images.get("flags", {}).get(c["country"], "")
        rows.append(row)
    excluded = [{"page": k, "reason": v.get("reason", "")}
                for k, v in ov.items()
                if isinstance(v, dict) and v.get("draft_exclude")]
    return {"cards": rows, "pending": pending, "confirmed": confirmed,
            "excluded": excluded, "stats": stats(cards),
            "diff": diff_against_published(cards, pending, confirmed),
            "card_version": C.CARD_VERSION,
            "template": C.TEMPLATE, "weight": C.WEIGHT, "attrs": list(C.ATTRS),
            "locked": bool(TOKEN)}


@app.put("/api/card/{page:path}")
def api_put(page: str, body: OverrideBody,
            x_admin_token: str = Header(default="", alias="X-Admin-Token")):
    require_admin(x_admin_token)
    cards, _, _ = live()
    if page not in {c["page"] for c in cards} and not body.draft_exclude:
        raise HTTPException(404, f"卡库里没有 {page}")
    raw = _load_raw()
    ov = _clean(body)
    if ov:
        raw[page] = ov
    else:
        raw.pop(page, None)               # 全填空 = 撤销覆盖
    _save_raw(raw)
    return _one(page)


@app.delete("/api/card/{page:path}")
def api_delete(page: str,
               x_admin_token: str = Header(default="", alias="X-Admin-Token")):
    require_admin(x_admin_token)
    raw = _load_raw()
    if raw.pop(page, None) is None:
        raise HTTPException(404, f"{page} 本来就没有覆盖")
    _save_raw(raw)
    return _one(page)


def _one(page: str) -> dict:
    cards, pending, confirmed = live()
    card = next((c for c in cards if c["page"] == page), None)
    return {"card": card, "override": _load_raw().get(page, {}),
            "stats": stats(cards),
            "diff": diff_against_published(cards, pending, confirmed)}


@app.post("/api/publish")
def api_publish(x_admin_token: str = Header(default="", alias="X-Admin-Token")):
    require_admin(x_admin_token)
    cards, pending, confirmed = live()
    path = C.write_cards(cards)
    return {"ok": True, "count": len(cards), "path": str(path),
            "diff": diff_against_published(cards, pending, confirmed)}


app.mount("/static", StaticFiles(directory=STATIC), name="static")
if IMG.is_dir():
    app.mount("/img", StaticFiles(directory=IMG), name="img")
# 5E 那套照片和队标。只挂 img 子目录,不挂整个 data/blind_draft——
# 那底下全是人工层和快照 JSON,没有理由顺着 HTTP 发出去。
if (BLIND_DRAFT / "img").is_dir():
    app.mount("/bd/img", StaticFiles(directory=BLIND_DRAFT / "img"), name="bdimg")
