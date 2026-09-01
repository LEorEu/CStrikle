# -*- coding: utf-8 -*-
"""Versus rooms: human vs human (two websockets) or human vs AI."""
import asyncio
import random
import secrets
import string
import time

from . import config
from .ai_player import AIPlayer
from .game import compare, normalize_settings
from playerdb.players import PlayerDB

AI_NAME = "AI·bot"
STANDARD_GAME_SECONDS = 120


def _code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=4))


class Seat:
    def __init__(self, name: str, token: str, is_ai=False):
        self.name = name
        self.token = token
        self.is_ai = is_ai
        self.ws = None
        self.left = False        # 明确离开(或终局后关页),不再回来
        self.rows = []           # full guess rows (own view)
        self.status = "playing"  # playing | won | lost
        self.rematch_ready = False

    def colors(self) -> list:
        """Opponent-visible view: colors only."""
        return [[{"key": c["key"], "state": c["state"], "dir": c.get("dir")}
                 for c in r["cells"]] for r in self.rows]


class Room:
    def __init__(self, db: PlayerDB, raw_settings: dict, host_name: str,
                 vs_ai: bool, ai_level: str = "normal"):
        self.db = db
        self.settings = normalize_settings(raw_settings)
        if self.settings["difficulty"] != "custom":
            # 标准难度的房间规则由服务端固定，旧客户端也不能退回 1 分钟。
            self.settings["game_seconds"] = STANDARD_GAME_SECONDS
        if vs_ai:
            # AI 对局必须有界：禁用可能不限时的自定义难度。
            if self.settings["difficulty"] == "custom":
                raise ValueError("自定义难度不支持 AI 对手,请选标准难度")
        pool = db.filter_pool(self.settings)
        if len(pool) < 2:
            raise ValueError("筛选条件下候选选手不足(<2),请放宽范围")
        self.pool_size = len(pool)
        self.answer_pool = list(pool)
        self.answer = random.choice(pool)
        self.code = _code()
        self.vs_ai = vs_ai
        self.ai_level = ai_level if ai_level in ("easy", "normal", "hard") else "normal"
        self.host = Seat(host_name or "玩家1", secrets.token_urlsafe(12))
        self.guest = (Seat(AI_NAME, secrets.token_urlsafe(12), is_ai=True)
                      if vs_ai else None)
        self.status = "waiting" if not vs_ai else "playing"
        self.winner = None       # seat name or "draw"
        self.chat = []           # [{from, text, ts}]
        self.created = time.time()
        self.ai = None
        self.ai_task = None
        self.timer_task = None
        self.abandon_task = None  # 玩家全员离线后的弃局倒计时
        self.deadline = None     # 整局限时的截止时间戳
        self.lock = asyncio.Lock()

    # ------------------------------------------------------------ helpers
    def seats(self):
        return [s for s in (self.host, self.guest) if s]

    def seat_by_token(self, token):
        for s in self.seats():
            if s.token == token and not s.is_ai:
                return s
        return None

    def opponent(self, seat):
        return self.guest if seat is self.host else self.host

    def pool_desc(self) -> str:
        s = self.settings
        diff = {"easy": "热门选手(Major常客或现役强队)",
                "medium": "常规(打过至少2次Major或现役职业哥)",
                "hard": "全部打过Major的选手(含冷门老哥)",
                "custom": "自定义(全部选手起筛)",
                "top20": "历年 HLTV 年度 Top20 上榜选手(全明星池)",
                }[s["difficulty"]]
        parts = [diff]
        if s["regions"]:
            parts.append("赛区限定: " + "/".join(s["regions"]))
        if s["active_only"]:
            parts.append("仅现役")
        if s["year_from"] or s["year_to"]:
            parts.append(f"Major年代 {s['year_from'] or 2013}–{s['year_to'] or '至今'}")
        return ";".join(parts) + f"(候选约{self.pool_size}人)"

    def join(self, name: str) -> Seat:
        if self.vs_ai or self.guest is not None:
            raise ValueError("房间已满")
        if self.status != "waiting":
            raise ValueError("对局已开始")
        self.guest = Seat(name or "玩家2", secrets.token_urlsafe(12))
        self.status = "playing"
        return self.guest

    # ---------------------------------------------------------- abandon
    def humans_connected(self) -> bool:
        return any(not s.is_ai and s.ws is not None for s in self.seats())

    async def finish(self, sys_msg: str, winner_seat: Seat | None = None):
        """立即终局:定胜负、停 AI/计时任务并广播。"""
        if self.status == "over":
            return
        self.status = "over"
        self.winner = winner_seat.name if winner_seat else "draw"
        for s in self.seats():
            if s.status == "playing":
                s.status = "won" if s is winner_seat else "lost"
        if self.ai_task:
            self.ai_task.cancel()
        if self.timer_task:
            self.timer_task.cancel()
        self.cancel_abandon()
        await self.post_chat("系统", sys_msg)
        await self.broadcast_state()

    async def end_by_leave(self, seat: Seat):
        """玩家点「离开房间」:对局中判对手获胜;已终局则只通知留守方。"""
        seat.left = True
        other = self.opponent(seat)
        if self.status == "over":
            # 胜负已定,不改结果,但要让还留在结算页的对手知道人跑了
            if other and not other.is_ai and other.ws is not None:
                await self.post_chat("系统", f"{seat.name} 离开了房间")
                await self.broadcast_state()
            return
        if (self.status == "playing" and other and not other.is_ai
                and other.status == "playing" and other.ws is not None):
            await self.finish(f"{seat.name} 离开了房间,{other.name} 获胜", other)
        else:
            await self.finish(f"{seat.name} 离开了房间,对局终止")

    def arm_abandon(self, delay: int = 15):
        """所有人类都断线时短暂等待重连(网络抖动),否则直接终局。"""
        if self.status != "playing" or self.abandon_task is not None:
            return
        self.abandon_task = asyncio.create_task(self._abandon_after(delay))

    def cancel_abandon(self):
        if self.abandon_task is not None:
            self.abandon_task.cancel()
            self.abandon_task = None

    async def _abandon_after(self, delay: int):
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        self.abandon_task = None
        if self.status == "playing" and not self.humans_connected():
            await self.finish("玩家已离线,对局终止")

    # ------------------------------------------------------------ clock
    def start_clock(self):
        """对局开始(双座位就绪)后启动整局限时。"""
        gs = self.settings.get("game_seconds")
        if not gs or self.status != "playing" or self.timer_task is not None:
            return
        self.deadline = time.time() + gs
        self.timer_task = asyncio.create_task(self._clock_loop())

    async def _clock_loop(self):
        try:
            while self.status == "playing":
                await asyncio.sleep(1)
                if self.deadline and time.time() > self.deadline:
                    for s in self.seats():
                        if s.status == "playing":
                            s.status = "lost"
                    self.status = "over"
                    self.winner = "draw"
                    await self.post_chat("系统", "⏱ 时间到 — 谁都没猜出来,平局")
                    if self.ai_task:
                        self.ai_task.cancel()
                    await self.broadcast_state()
        except asyncio.CancelledError:
            pass

    # ------------------------------------------------------------ state
    def state_for(self, seat: Seat) -> dict:
        opp = self.opponent(seat)
        d = {
            "type": "state",
            "code": self.code,
            "status": self.status,
            "settings": self.settings,
            "pool_size": self.pool_size,
            "vs_ai": self.vs_ai,
            "you": {"name": seat.name, "status": seat.status,
                    "rows": seat.rows,
                    "rematch_ready": seat.rematch_ready,
                    "remaining": self.settings["max_guesses"] - len(seat.rows)},
            "deadline": self.deadline,
            "opponent": None,
            "chat": self.chat[-50:],
            "winner": self.winner,
            "now": time.time(),
        }
        if opp:
            d["opponent"] = {"name": opp.name, "status": opp.status,
                             "is_ai": opp.is_ai, "colors": opp.colors(),
                             "rematch_ready": opp.rematch_ready,
                             "present": opp.is_ai or (not opp.left
                                                      and opp.ws is not None),
                             "remaining": self.settings["max_guesses"] - len(opp.rows)}
        if self.status == "over":
            d["answer"] = self.answer.full()
            d["opponent_rows"] = opp.rows if opp else []
        elif seat.status != "playing":
            # 已出局的一方立刻可以偷看谜底,不用干等对手打完
            d["answer_spoiler"] = self.answer.full()
        return d

    async def _send(self, seat: Seat, payload: dict):
        if seat and not seat.is_ai and seat.ws is not None:
            try:
                await seat.ws.send_json(payload)
            except Exception:
                pass

    async def broadcast_state(self):
        for s in self.seats():
            await self._send(s, self.state_for(s))

    async def post_chat(self, sender: str, text: str):
        text = (text or "").strip()[:300]
        if not text:
            return
        msg = {"from": sender, "text": text, "ts": time.time()}
        self.chat.append(msg)
        for s in self.seats():
            await self._send(s, {"type": "chat", **msg})

    # ---------------------------------------------------------- rematch
    def request_rematch(self, seat: Seat) -> bool:
        """登记重赛准备；真人双方都确认后才开局，AI 对局立即开局。"""
        if self.status != "over":
            raise ValueError("对局还没结束,不能重开")
        if seat not in self.seats() or seat.is_ai:
            raise ValueError("无效的重赛请求")
        seat.rematch_ready = True
        if self.vs_ai or all(s.is_ai or s.rematch_ready for s in self.seats()):
            self._start_rematch()
            return True
        return False

    def _start_rematch(self):
        """同一房间、同一规则开始新一局(换谜底并清空双方状态)。"""
        self.answer = random.choice(self.answer_pool)
        for s in self.seats():
            s.rows = []
            s.status = "playing"
            s.rematch_ready = False
        self.status = "playing"
        self.winner = None
        self.deadline = None
        self.timer_task = None
        self.ai_task = None
        self.created = time.time()   # 连着打就续命,别被超龄清理
        if self.vs_ai:
            self.start_ai()
        self.start_clock()
        if not self.humans_connected():
            self.arm_abandon()

    # ------------------------------------------------------------ game
    async def make_guess(self, seat: Seat, name: str):
        async with self.lock:
            if self.status != "playing":
                raise ValueError("对局不在进行中")
            if seat.status != "playing":
                raise ValueError("你的猜测次数已用完")
            p = self.db.lookup(name)
            if p is None:
                raise LookupError(f"选手库里没有「{name}」")
            if any(r["player"]["page"] == p.page for r in seat.rows):
                raise ValueError(f"已经猜过 {p.nickname} 了")
            cells = compare(p, self.answer)
            row = {"player": p.brief(), "cells": cells,
                   "correct": p.page == self.answer.page}
            seat.rows.append(row)
            if row["correct"]:
                seat.status = "won"
                self.winner = seat.name
                self.status = "over"
                for s in self.seats():
                    if s is not seat and s.status == "playing":
                        s.status = "lost"
            elif len(seat.rows) >= self.settings["max_guesses"]:
                seat.status = "lost"
                if all(s.status == "lost" for s in self.seats()):
                    self.status = "over"
                    self.winner = "draw"
        await self.broadcast_state()
        if self.status == "over":
            if self.ai_task:
                self.ai_task.cancel()
            if self.timer_task:
                self.timer_task.cancel()
        return row

    # ------------------------------------------------------------ AI
    def start_ai(self):
        if not self.vs_ai:
            return
        if not config.AI_ENABLED:
            raise ValueError("服务端未配置 AI(.env 里设置 AI_BASE_URL / AI_API_KEY / AI_MODEL)")

        async def say(text):
            await self.post_chat(AI_NAME, text)

        async def status(state, detail):
            for s in self.seats():
                await self._send(s, {"type": "ai_status", "state": state,
                                     "detail": detail})

        self.ai = AIPlayer(
            self.db,
            self.answer_pool,
            self.pool_desc(),
            max_guesses=self.settings["max_guesses"],
            on_say=say,
            on_status=status,
            ai_level=self.ai_level,
        )
        self.ai_task = asyncio.create_task(self._ai_loop())

    async def _ai_loop(self):
        seat = self.guest
        delay = config.AI_GUESS_DELAY_SECONDS
        try:
            await asyncio.sleep(0.8)   # 给玩家一点起手时间，同时保持短局节奏
            while self.status == "playing" and seat.status == "playing":
                opp = self.host
                opp_info = (f"对手已猜 {len(opp.rows)}/{self.settings['max_guesses']} 次,"
                            f"状态: {opp.status}")
                guessed = {r["player"]["page"] for r in seat.rows}
                guessed |= {r["player"]["nickname"].lower() for r in seat.rows}
                try:
                    turn = await self.ai.take_turn(seat.rows, opp_info, guessed)
                except Exception as e:
                    await self.post_chat("系统", f"AI 接口出错了: {type(e).__name__}: {e}")
                    await asyncio.sleep(3)
                    continue
                for s in self.seats():
                    await self._send(s, {"type": "ai_status", "state": "idle",
                                         "detail": None})
                if turn.guess_name is None:
                    # 普通难度的模型超时/无效选择使用本轮备用候选，避免卡局。
                    if not turn.fallback_guess:
                        break
                    pick = self.db.by_page.get(turn.fallback_guess)
                    if pick is None:
                        break
                    self.ai.transcript[-1]["events"].append(
                        {"type": "forced_guess", "name": pick.nickname,
                         "reason": "AI 没有及时完成选择，改用备用人选"})
                    turn.guess_name = pick.page
                if self.status != "playing":
                    break
                try:
                    await self.make_guess(seat, turn.guess_name)
                except (ValueError, LookupError):
                    pass
                await asyncio.sleep(delay + random.uniform(0, delay * 0.5))
        except asyncio.CancelledError:
            pass


class RoomStore:
    def __init__(self, db: PlayerDB):
        self.db = db
        self.rooms = {}

    def create(self, raw_settings, host_name, vs_ai, ai_level="normal") -> Room:
        self._cleanup()
        room = Room(self.db, raw_settings, host_name, vs_ai, ai_level)
        while room.code in self.rooms:
            room.code = _code()
        self.rooms[room.code] = room
        return room

    def get(self, code: str) -> Room | None:
        return self.rooms.get((code or "").upper())

    def _cleanup(self, max_age=6 * 3600):
        now = time.time()
        for code in [c for c, r in self.rooms.items()
                     if now - r.created > max_age]:
            r = self.rooms.pop(code)
            for task in (r.ai_task, r.timer_task, r.abandon_task):
                if task:
                    task.cancel()
