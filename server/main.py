# -*- coding: utf-8 -*-
"""cstrikle server: REST + WebSocket + static frontend."""
import time
from collections import deque
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .game import Game
from .players import REGIONS, PlayerDB
from .rooms import RoomStore

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="cstrikle")

db = PlayerDB()
rooms = RoomStore(db)
games: dict[str, tuple[float, Game]] = {}
_ai_room_attempts: dict[str, deque[float]] = {}


def _cleanup_games(max_age=12 * 3600):
    now = time.time()
    for gid in [g for g, (ts, _) in games.items() if now - ts > max_age]:
        games.pop(gid, None)


def _consume_ai_room_quota(client_ip: str, now: float | None = None):
    """Apply a small in-memory sliding-window limit to AI room creation."""
    now = time.time() if now is None else now
    cutoff = now - config.AI_ROOM_RATE_WINDOW_SECONDS

    for ip, attempts in list(_ai_room_attempts.items()):
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if not attempts:
            _ai_room_attempts.pop(ip, None)

    attempts = _ai_room_attempts.setdefault(client_ip, deque())
    if len(attempts) >= config.AI_ROOM_RATE_LIMIT:
        retry_after = max(
            1, int(attempts[0] + config.AI_ROOM_RATE_WINDOW_SECONDS - now) + 1
        )
        raise HTTPException(
            429,
            f"AI 房间创建太频繁,请 {retry_after} 秒后再试",
            headers={"Retry-After": str(retry_after)},
        )
    attempts.append(now)


# ------------------------------------------------------------------ meta
@app.get("/api/meta")
def meta():
    return {
        "db_generated_at": db.generated_at,
        "player_count": len(db.players),
        "regions": REGIONS[:-1],
        "pool_sizes": {d: len(db.difficulty_pool(d))
                       for d in ("easy", "medium", "hard")},
        "ai_enabled": config.AI_ENABLED,
        "ai_model": config.AI_MODEL if config.AI_ENABLED else None,
    }


@app.get("/api/players")
def players():
    return [p.brief() for p in db.players]


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


# ----------------------------------------------------------------- rooms
class NewRoom(BaseModel):
    name: str = "玩家1"
    settings: dict | None = None
    vs_ai: bool = False
    ai_speed: str = "normal"


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
                            body.ai_speed)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if body.vs_ai:
        room.start_ai()
        room.start_clock()
    return {"code": room.code, "token": room.host.token, "vs_ai": room.vs_ai}


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
    except WebSocketDisconnect:
        pass
    finally:
        if seat.ws is ws:
            seat.ws = None


# ---------------------------------------------------------------- static
static_dir = ROOT / "static"
img_dir = ROOT / "data" / "img"
app.mount("/static", StaticFiles(directory=static_dir), name="static")
if img_dir.exists():
    app.mount("/img", StaticFiles(directory=img_dir), name="img")


@app.get("/")
def index():
    return FileResponse(static_dir / "index.html")
