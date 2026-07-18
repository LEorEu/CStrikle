# -*- coding: utf-8 -*-
"""cstrikle server: REST + WebSocket + static frontend."""
import json
import logging
import secrets
import threading
import time
from collections import deque
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .game import Game, normalize_settings
from .players import REGIONS, PlayerDB
from .rooms import RoomStore

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="cstrikle")

db = PlayerDB()
rooms = RoomStore(db)
games: dict[str, tuple[float, Game]] = {}
_ai_room_attempts: dict[str, deque[float]] = {}
_feedback_attempts: dict[str, deque[float]] = {}

# 玩家反馈要保证进 docker logs:root logger 默认无 handler 会丢 INFO,
# 这里给专用 logger 显式挂 stderr handler。
_feedback_log = logging.getLogger("cstrikle.feedback")
if not _feedback_log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
    _feedback_log.addHandler(_h)
    _feedback_log.setLevel(logging.INFO)
    _feedback_log.propagate = False


def _cleanup_games(max_age=12 * 3600):
    now = time.time()
    for gid in [g for g, (ts, _) in games.items() if now - ts > max_age]:
        games.pop(gid, None)


def _consume_quota(store: dict, client_ip: str, limit: int, window: float,
                   what: str, now: float | None = None):
    """In-memory sliding-window rate limit, shared by AI rooms and feedback."""
    now = time.time() if now is None else now
    cutoff = now - window

    for ip, attempts in list(store.items()):
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if not attempts:
            store.pop(ip, None)

    attempts = store.setdefault(client_ip, deque())
    if len(attempts) >= limit:
        retry_after = max(1, int(attempts[0] + window - now) + 1)
        raise HTTPException(
            429,
            f"{what}太频繁,请 {retry_after} 秒后再试",
            headers={"Retry-After": str(retry_after)},
        )
    attempts.append(now)


def _consume_ai_room_quota(client_ip: str, now: float | None = None):
    _consume_quota(_ai_room_attempts, client_ip, config.AI_ROOM_RATE_LIMIT,
                   config.AI_ROOM_RATE_WINDOW_SECONDS, "AI 房间创建", now)


# ------------------------------------------------------------------ meta
@app.get("/api/meta")
def meta():
    return {
        "db_generated_at": db.generated_at,
        "player_count": len(db.players),
        "answer_player_count": len(db.answer_players),
        "excluded_stubs": db.excluded_stubs,
        "team_ranking_date": db.ranking.generated_at,
        "regions": REGIONS[:-1],
        "pool_sizes": {d: len(db.difficulty_pool(d))
                       for d in ("easy", "medium", "hard", "top20")},
        "ai_enabled": config.AI_ENABLED,
        "ai_model": config.AI_MODEL if config.AI_ENABLED else None,
    }


@app.get("/api/players")
def players():
    return [p.brief() for p in db.players]


class PoolQuery(BaseModel):
    settings: dict | None = None


@app.post("/api/pool_count")
def pool_count(body: PoolQuery):
    """设置面板实时显示当前筛选条件下的候选人数。"""
    return {"count": len(db.filter_pool(normalize_settings(body.settings)))}


# -------------------------------------------------------------- feedback
class FeedbackBody(BaseModel):
    page: str = ""           # 被纠错的选手 page id,可为空(整体反馈)
    message: str
    context: str = ""        # 来源场景,如 "daily" / "room GO4B"


@app.post("/api/feedback")
def feedback(body: FeedbackBody, request: Request):
    message = body.message.strip()
    if not message:
        raise HTTPException(400, "反馈内容不能为空")
    client_ip = request.client.host if request.client else "unknown"
    _consume_quota(_feedback_attempts, client_ip, config.FEEDBACK_RATE_LIMIT,
                   config.FEEDBACK_RATE_WINDOW_SECONDS, "反馈提交")
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "ip": client_ip,
        "page": body.page.strip()[:80],
        "message": message[:500],
        "context": body.context.strip()[:120],
    }
    line = json.dumps(record, ensure_ascii=False)
    # 日志始终记录;文件写失败(只读容器等)不影响玩家侧成功反馈
    _feedback_log.info(line)
    try:
        config.FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(config.FEEDBACK_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    return {"ok": True}


# ------------------------------------------------------------------ solo
class NewGame(BaseModel):
    mode: str = "unlimited"          # daily | unlimited
    settings: dict | None = None


class GuessBody(BaseModel):
    name: str


@app.post("/api/game")
def new_game(body: NewGame):
    _cleanup_games()
    mode = body.mode if body.mode in ("daily", "unlimited") else "unlimited"
    try:
        g = Game.create(db, body.settings, mode=mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    games[g.id] = (time.time(), g)
    return g.serialize()


@app.get("/api/game/{gid}")
def get_game(gid: str):
    if gid not in games:
        raise HTTPException(404, "对局不存在或已过期")
    return games[gid][1].serialize()


@app.post("/api/game/{gid}/guess")
def game_guess(gid: str, body: GuessBody):
    if gid not in games:
        raise HTTPException(404, "对局不存在或已过期")
    g = games[gid][1]
    try:
        g.guess(body.name)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return g.serialize()


# ----------------------------------------------------------- matchmaking
# 随机匹配:固定常规难度 + 2 分钟整局限时的人人对战。
# 单等待位内存实现:等待者靠轮询保活,超时自动出队。
MATCH_SETTINGS = {"difficulty": "medium", "game_seconds": 120}
MATCH_WAIT_TTL = 15          # 秒:超过没轮询就当他关页走人了
MATCH_RESULT_TTL = 300

_match_lock = threading.Lock()
_match_waiter: dict | None = None          # {ticket, name, last_seen}
_match_results: dict[str, dict] = {}       # ticket -> {code, token, ts}


class MatchJoin(BaseModel):
    name: str = "玩家"


def _purge_match_state(now: float):
    global _match_waiter
    if _match_waiter and now - _match_waiter["last_seen"] > MATCH_WAIT_TTL:
        _match_waiter = None
    for t in [t for t, r in _match_results.items()
              if now - r["ts"] > MATCH_RESULT_TTL]:
        _match_results.pop(t, None)


@app.post("/api/match/join")
async def match_join(body: MatchJoin):
    global _match_waiter
    name = body.name.strip()[:20] or "路人玩家"
    now = time.time()
    with _match_lock:
        _purge_match_state(now)
        if _match_waiter is None:
            ticket = secrets.token_urlsafe(12)
            _match_waiter = {"ticket": ticket, "name": name, "last_seen": now}
            return {"matched": False, "ticket": ticket}
        waiter = _match_waiter
        _match_waiter = None
        if name == waiter["name"]:
            name += "2"          # 同名会让胜负判定文案分不清人
        room = rooms.create(dict(MATCH_SETTINGS), waiter["name"], vs_ai=False)
        seat = room.join(name)
        room.start_clock()
        _match_results[waiter["ticket"]] = {
            "code": room.code, "token": room.host.token, "ts": now,
        }
        return {"matched": True, "code": room.code, "token": seat.token}


@app.get("/api/match/poll/{ticket}")
async def match_poll(ticket: str):
    global _match_waiter
    now = time.time()
    with _match_lock:
        _purge_match_state(now)
        result = _match_results.pop(ticket, None)
        if result:
            return {"matched": True, "code": result["code"],
                    "token": result["token"]}
        if _match_waiter and _match_waiter["ticket"] == ticket:
            _match_waiter["last_seen"] = now
            return {"matched": False}
    raise HTTPException(404, "匹配已过期,请重新开始")


@app.delete("/api/match/{ticket}")
async def match_cancel(ticket: str):
    global _match_waiter
    with _match_lock:
        if _match_waiter and _match_waiter["ticket"] == ticket:
            _match_waiter = None
        _match_results.pop(ticket, None)
    return {"ok": True}


# ----------------------------------------------------------------- rooms
class NewRoom(BaseModel):
    name: str = "玩家1"
    settings: dict | None = None
    vs_ai: bool = False
    ai_level: str = "normal"     # easy | normal | hard


class JoinRoom(BaseModel):
    name: str = "玩家2"


@app.post("/api/room")
async def create_room(body: NewRoom, request: Request):
    if body.vs_ai and not config.AI_ENABLED:
        raise HTTPException(400, "服务端未配置 AI:请在 .env 设置 AI_BASE_URL / AI_API_KEY / AI_MODEL")
    if body.vs_ai:
        client_ip = request.client.host if request.client else "unknown"
        _consume_ai_room_quota(client_ip)
    try:
        room = rooms.create(body.settings, body.name.strip()[:20], body.vs_ai,
                            body.ai_level)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if body.vs_ai:
        room.start_ai()
        room.start_clock()
        room.arm_abandon()   # 创建后一直没人连上 ws 就终止,防止 AI 空转烧模型
    return {"code": room.code, "token": room.host.token, "vs_ai": room.vs_ai}


@app.post("/api/room/{code}/rematch")
async def rematch_room(
    code: str,
    request: Request,
    room_token: str = Header(default="", alias="X-Room-Token"),
):
    room = rooms.get(code)
    if room is None:
        raise HTTPException(404, "房间不存在")
    seat = room.seat_by_token(room_token)
    if seat is None:
        raise HTTPException(403, "你不在这个房间里")
    if room.vs_ai:
        client_ip = request.client.host if request.client else "unknown"
        _consume_ai_room_quota(client_ip)
    try:
        room.rematch()
    except ValueError as e:
        raise HTTPException(400, str(e))
    await room.post_chat("系统", f"{seat.name} 开了新的一局,谜底已更换")
    await room.broadcast_state()
    return {"ok": True}


@app.post("/api/room/{code}/join")
async def join_room(code: str, body: JoinRoom):
    room = rooms.get(code)
    if room is None:
        raise HTTPException(404, "房间不存在")
    try:
        seat = room.join(body.name.strip()[:20])
    except ValueError as e:
        raise HTTPException(400, str(e))
    room.start_clock()
    await room.broadcast_state()
    return {"code": room.code, "token": seat.token}


@app.get("/api/room/{code}/debug_answer")
def debug_answer(code: str):
    if not config.DEBUG:
        raise HTTPException(404, "Not Found")
    room = rooms.get(code)
    if room is None:
        raise HTTPException(404, "房间不存在")
    return {"answer": room.answer.page}


@app.get("/api/room/{code}/transcript")
def transcript(
    code: str,
    room_token: str = Header(default="", alias="X-Room-Token"),
):
    room = rooms.get(code)
    if room is None:
        raise HTTPException(404, "房间不存在")
    if room.seat_by_token(room_token) is None:
        raise HTTPException(403, "无权查看本局 AI 回放")
    if room.status != "over":
        raise HTTPException(403, "对局还没结束,先赢了再看")
    if not room.ai:
        raise HTTPException(404, "本局没有 AI 参与")
    return {"model": config.AI_MODEL, "transcript": room.ai.transcript}


@app.websocket("/ws/room/{code}")
async def room_ws(ws: WebSocket, code: str, token: str = ""):
    room = rooms.get(code)
    seat = room.seat_by_token(token) if room else None
    if room is None or seat is None:
        await ws.close(code=4404)
        return
    await ws.accept()
    seat.ws = ws
    room.cancel_abandon()          # 断线重连回来了,取消弃局倒计时
    await room.broadcast_state()
    try:
        while True:
            msg = await ws.receive_json()
            t = msg.get("type")
            if t == "guess":
                try:
                    await room.make_guess(seat, msg.get("name", ""))
                except (ValueError, LookupError) as e:
                    await ws.send_json({"type": "error", "message": str(e)})
            elif t == "chat":
                await room.post_chat(seat.name, msg.get("text", ""))
            elif t == "leave":
                # 点「离开房间」= 明确弃局,立即终结(对手在打则判对手胜)
                await room.end_by_leave(seat)
                break
    except WebSocketDisconnect:
        pass
    finally:
        if seat.ws is ws:
            seat.ws = None
        # 所有人类都断线(刷新/关页)时,只留几秒重连窗口,然后立即终局
        if room.status == "playing" and not room.humans_connected():
            room.arm_abandon()


# ---------------------------------------------------------------- static
static_dir = ROOT / "static"
img_dir = ROOT / "data" / "img"
app.mount("/static", StaticFiles(directory=static_dir), name="static")
if img_dir.exists():
    app.mount("/img", StaticFiles(directory=img_dir), name="img")


@app.get("/")
def index():
    return FileResponse(static_dir / "index.html")
