# -*- coding: utf-8 -*-
"""
LLM opponent: a tool-using agent that plays the guessing game.

Every turn it can think out loud, run web searches, talk trash, and must end
by submitting a guess. Everything (reasoning, tool calls, search results,
trash talk) is recorded into a transcript the human can replay after the
match.
"""
import asyncio
import json
import logging
import re
import time

from openai import AsyncOpenAI

from . import config
from .game import feedback_text
from .players import PlayerDB
from .solver import PlayerSolver, SolverAnalysis

logger = logging.getLogger("uvicorn.error")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ddgs_search",
            "description": "搜索互联网获取 CS 职业选手的资料(国籍、年龄、战队、位置、Major 经历等)。返回前几条搜索结果的标题和摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "say",
            "description": "在对局聊天里对人类对手说一句话(垃圾话、嘲讽、心理战、感叹都行,中文,一两句以内)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_guess",
            "description": "提交你本轮的猜测(选手游戏ID/昵称)。这会结束你的本轮回合。",
            "parameters": {
                "type": "object",
                "properties": {
                    "nickname": {"type": "string", "description": "选手的游戏昵称,例如 s1mple"},
                },
                "required": ["nickname"],
            },
        },
    },
]

SYSTEM_PROMPT = """你是一名 CS 电竞圈老油条,正在和一个人类玩家对战 Counter-Strikle(猜 CS 职业选手的 Wordle 类游戏)。

## 规则
- 双方猜同一个神秘职业选手,谁先猜中谁赢。你每轮提交一个猜测。
- 每次猜测后会得到逐属性反馈:
  - 国籍:✔=同一国家;≈=同一赛区(欧洲/独联体/北美/南美/亚洲/大洋洲等);✘=都不沾边
  - 战队:✔=当前战队相同(无战队时"退役"和"未签约"算两种不同状态)
  - 年龄:✔=相同;≈=相差2岁以内;并提示答案比你猜的更大还是更小
  - 位置:✔=主位置相同(IGL/AWPer/Rifler/Coach);≈=位置有重叠
  - Major次数:✔=相同;≈=相差1;并提示答案更多还是更少
  - Major冠军数:✔=相同;≈=相差1;并提示答案更多还是更少
- 谜底范围:{pool_desc}

## 最优决策逻辑
服务器已经使用与游戏完全相同的本地数据库和 compare() 规则完成以下计算:
1. 只保留对所有历史反馈都能产生相同颜色/方向的严格候选。
2. 候选较多时,枚举合法猜测并按期望后验大小、最坏分支、信息熵排序。
3. 候选较少时,在剩余回合内递归计算决策树,最大化实际猜中概率。
4. 本地数据库是本局判定真值;网页上的最新资料不能推翻本地反馈。

## 你的任务
1. 阅读用户消息中的“本地确定性求解器”结果,用中文解释候选如何缩小、为什么指定落子信息量最大或能保证求解。
2. 必须调用 submit_guess 提交“本轮指定猜测”,不得擅自换成别的选手。
3. ddgs_search 只用于补充冷门选手背景或聊天素材,不能改变指定落子;第一轮不要搜索,每轮最多一次。
4. 你性格嚣张嘴臭但有真本事,可以用 say 发一两句中文心理战,但不要拖延提交。
5. 信息足够时,在同一次回复里调用 say 和 submit_guess;不要只聊天或只输出长篇推理。

注意:你看不到对手猜了谁,只能看到对手已用的猜测次数和反馈颜色。"""

# 不支持 function calling 的接口(如 grok.com 逆向)改用正文 JSON 指令
TEXT_PROTOCOL = """

## 动作指令格式(本接口不支持工具调用,改用以下方式)
把动作写在回复正文里,每个动作单独占一行,内容是一个 JSON 对象:
{"action": "search", "query": "搜索关键词"}
{"action": "say", "message": "对人类说的话"}
{"action": "guess", "nickname": "选手游戏ID"}
先写中文推理,再给动作行。需要搜索就先只发 search,等我把结果发给你;
信息够了就发 guess(每轮最终必须提交一次 guess)。"""

ACTION_RE = re.compile(r'^\s*\{.*"action".*\}\s*$', re.M)


class TurnResult:
    def __init__(self):
        self.guess_name = None
        self.fallback_guess = None
        self.events = []          # transcript of this turn
        self.searches_used = 0


class AIPlayer:
    def __init__(
        self,
        db: PlayerDB,
        answer_pool: list,
        pool_desc: str,
        max_guesses: int = 8,
        on_say=None,
        on_status=None,
        reasoning_effort: str | None = None,
    ):
        self.db = db
        self.solver = PlayerSolver(
            db,
            answer_pool,
            exact_threshold=config.AI_EXACT_THRESHOLD,
        )
        self.pool_desc = pool_desc
        self.max_guesses = max_guesses
        self.on_say = on_say          # async fn(message)
        self.on_status = on_status    # async fn(status, detail)
        self.reasoning_effort = (
            config.AI_REASONING_EFFORT
            if reasoning_effort is None
            else reasoning_effort.strip().lower()
        )
        self.client = AsyncOpenAI(
            base_url=config.AI_BASE_URL,
            api_key=config.AI_API_KEY,
            timeout=config.AI_TIMEOUT_SECONDS,
            max_retries=0,
        )
        self.transcript = []          # [{turn, events: [...]}]
        self._search_cache: dict[str, tuple[float, str]] = {}
        self._required_guess = None
        # native | text;auto 从 native 起步,发现接口不支持时降级
        self.tools_mode = ("text" if config.AI_TOOLS_MODE == "text" else "native")

    # ------------------------------------------------------------ tools
    async def _web_search(self, query: str) -> str:
        key = " ".join((query or "").casefold().split())
        cached = self._search_cache.get(key)
        if cached and time.monotonic() - cached[0] <= config.AI_SEARCH_CACHE_TTL_SECONDS:
            return cached[1]

        def run():
            from ddgs import DDGS
            with DDGS() as d:
                return list(d.text(query, max_results=5))
        try:
            hits = await asyncio.to_thread(run)
        except Exception as e:
            return f"搜索失败: {e}"
        if not hits:
            return "没有搜到结果"
        result = "\n\n".join(
            f"[{i+1}] {h.get('title', '')}\n{h.get('body', '')}"
            for i, h in enumerate(hits)
        )
        self._search_cache[key] = (time.monotonic(), result)
        return result

    # ------------------------------------------------------------ turn
    def _history_block(
        self,
        my_rows,
        opp_info,
        analysis: SolverAnalysis,
    ) -> str:
        lines = []
        if my_rows:
            lines.append("## 你已有的猜测和反馈")
            for i, row in enumerate(my_rows, 1):
                lines.append(f"{i}. 猜了 {row['player']['nickname']}"
                             f"({row['player']['country']},{row['player']['team'] or '无战队'})"
                             f" -> {feedback_text(row['cells'])}")
        else:
            lines.append("## 这是你的第一轮猜测,还没有任何反馈。")
        if opp_info:
            lines.append(f"\n## 对手进度\n{opp_info}")
        lines.append("\n" + analysis.prompt_block())
        lines.append("\n请解释求解器结论并立即提交指定猜测。")
        return "\n".join(lines)

    # ------------------------------------------------- shared tool actions
    async def _do_search(self, q: str, res: TurnResult) -> str:
        if res.searches_used >= 1:
            return "本轮搜索次数已用完；请按本地求解器指定落子。"
        res.searches_used += 1
        res.events.append({"type": "search", "query": q})
        if self.on_status:
            await self.on_status("searching", None)
        out = await self._web_search(q)
        res.events.append({"type": "search_result", "text": out})
        return out

    async def _do_say(self, text: str, res: TurnResult) -> str:
        text = (text or "")[:300]
        res.events.append({"type": "say", "text": text})
        if self.on_say and text:
            await self.on_say(text)
        return "(已发送)"

    def _do_guess(self, name: str, res: TurnResult, guessed_names: set) -> str:
        name = (name or "").strip()
        p = self.db.lookup(name)
        if p is None:
            out = f"「{name}」不在选手库里(可能拼写不同或不够知名),换一个猜测。"
            res.events.append({"type": "guess_rejected", "name": name, "reason": out})
        elif p.nickname.lower() in guessed_names or p.page in guessed_names:
            out = f"{p.nickname} 你已经猜过了,换一个。"
            res.events.append({"type": "guess_rejected", "name": name, "reason": out})
        elif self._required_guess and p.page != self._required_guess.page:
            out = (
                f"本轮必须提交求解器指定的 {self._required_guess.nickname}，"
                f"不能改猜 {p.nickname}。"
            )
            res.events.append({"type": "guess_rejected", "name": name, "reason": out})
        else:
            res.guess_name = p.page
            res.events.append({"type": "guess", "name": p.nickname})
            out = "OK"
        return out

    def _system_prompt(self) -> str:
        sp = SYSTEM_PROMPT.format(pool_desc=self.pool_desc)
        if self.tools_mode == "text":
            sp += TEXT_PROTOCOL
        return sp

    async def take_turn(self, my_rows: list, opp_info: str,
                        guessed_names: set) -> TurnResult:
        res = TurnResult()
        turn_no = len(my_rows) + 1
        guessed_pages = {
            row.get("player", {}).get("page", "")
            for row in my_rows
            if row.get("player", {}).get("page")
        }
        analysis = await asyncio.to_thread(
            self.solver.analyze,
            my_rows,
            max(1, self.max_guesses - len(my_rows)),
            guessed_pages,
        )
        self._required_guess = analysis.recommended
        res.fallback_guess = analysis.recommended.page
        res.events.append({
            "type": "solver",
            "mode": analysis.mode,
            "candidate_count": len(analysis.candidates),
            "recommended": analysis.recommended.nickname,
            "exact_solve_probability": analysis.exact_solve_probability,
            "moves": [
                {
                    "nickname": move.player.nickname,
                    "expected_remaining": round(move.expected_remaining, 4),
                    "worst_case": move.worst_case,
                    "entropy": round(move.entropy, 4),
                    "in_candidates": move.in_candidates,
                }
                for move in analysis.moves
            ],
        })
        messages = [
            {"role": "system", "content": self._system_prompt()},
            {
                "role": "user",
                "content": self._history_block(my_rows, opp_info, analysis),
            },
        ]
        tools = [t for t in TOOLS
                 if config.AI_SEARCH_ENABLED or t["function"]["name"] != "ddgs_search"]

        for step in range(config.AI_MAX_STEPS):
            if self.on_status:
                await self.on_status("thinking", None)
            started = time.perf_counter()
            try:
                if self.tools_mode == "native":
                    request = {
                        "model": config.AI_MODEL,
                        "messages": messages,
                        "tools": tools,
                        "metadata": {
                            "client": "cstrikle",
                            "search_provider": "ddgs",
                        },
                    }
                    if self.reasoning_effort:
                        request["reasoning_effort"] = self.reasoning_effort
                    # 第一次没有完成猜测时，后续步骤只允许提交猜测，
                    # 避免模型连续聊天/搜索导致一个回合调用三四次。
                    if step > 0:
                        request["tool_choice"] = {
                            "type": "function",
                            "function": {"name": "submit_guess"},
                        }
                    resp = await self.client.chat.completions.create(**request)
                else:
                    request = {
                        "model": config.AI_MODEL,
                        "messages": messages,
                        "metadata": {
                            "client": "cstrikle",
                            "search_provider": "ddgs",
                        },
                    }
                    if self.reasoning_effort:
                        request["reasoning_effort"] = self.reasoning_effort
                    resp = await self.client.chat.completions.create(**request)
            except Exception as e:
                elapsed = time.perf_counter() - started
                logger.warning(
                    "AI model call failed model=%s turn=%s step=%s elapsed=%.2fs: %s",
                    config.AI_MODEL, turn_no, step + 1, elapsed, e,
                )
                # auto 模式下接口报不认识 tools -> 降级文本协议重来
                if (self.tools_mode == "native" and config.AI_TOOLS_MODE == "auto"
                        and any(w in str(e).lower() for w in ("tool", "function"))):
                    self.tools_mode = "text"
                    messages[0] = {"role": "system", "content": self._system_prompt()}
                    res.events.append({"type": "forced_guess", "name": "",
                                       "reason": "接口不支持工具调用,已切换文本指令模式"})
                    continue
                res.events.append({
                    "type": "model_error",
                    "error": type(e).__name__,
                    "message": str(e)[:500],
                    "elapsed_seconds": round(elapsed, 3),
                })
                break
            elapsed = time.perf_counter() - started
            logger.info(
                "AI model call model=%s turn=%s step=%s elapsed=%.2fs",
                config.AI_MODEL, turn_no, step + 1, elapsed,
            )
            msg = resp.choices[0].message
            reasoning = getattr(msg, "reasoning_content", None)
            if reasoning:
                res.events.append({"type": "reasoning", "text": reasoning})

            # ---------- 文本协议:从正文里解析 JSON 动作行 ----------
            actions = []
            if not msg.tool_calls and msg.content:
                for line in ACTION_RE.findall(msg.content):
                    try:
                        a = json.loads(line)
                        if isinstance(a, dict) and a.get("action"):
                            actions.append(a)
                    except json.JSONDecodeError:
                        pass
            if actions and self.tools_mode == "native" and config.AI_TOOLS_MODE == "auto":
                self.tools_mode = "text"     # 模型不用 tools 却回了指令行:定型为文本模式
                messages[0] = {"role": "system", "content": self._system_prompt()}

            if msg.content:
                shown = ACTION_RE.sub("", msg.content).strip() if actions else msg.content
                if shown:
                    res.events.append({"type": "thinking", "text": shown})

            if msg.tool_calls:
                messages.append(msg.model_dump(exclude_none=True))
                for tc in msg.tool_calls:
                    fn = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    if fn == "ddgs_search":
                        out = await self._do_search(str(args.get("query", "")), res)
                    elif fn == "say":
                        out = await self._do_say(str(args.get("message", "")), res)
                    elif fn == "submit_guess":
                        out = self._do_guess(str(args.get("nickname", "")), res,
                                             guessed_names)
                    else:
                        out = "未知工具"
                    messages.append({"role": "tool", "tool_call_id": tc.id,
                                     "content": out})
            elif actions:
                messages.append({"role": "assistant", "content": msg.content})
                fb = []
                for a in actions:
                    act = a.get("action")
                    if act == "search" and config.AI_SEARCH_ENABLED:
                        out = await self._do_search(str(a.get("query", "")), res)
                        fb.append(f"[search 结果]\n{out}")
                    elif act == "say":
                        await self._do_say(str(a.get("message", "")), res)
                    elif act == "guess":
                        out = self._do_guess(str(a.get("nickname", "")), res,
                                             guessed_names)
                        if out != "OK":
                            fb.append(f"[系统] {out}")
                if res.guess_name:
                    break
                fb.append("请继续,最终必须提交一行 guess。")
                messages.append({"role": "user", "content": "\n\n".join(fb)})
                continue
            else:
                messages.append({"role": "assistant", "content": msg.content or ""})
                nag = ("请继续:需要时调用 ddgs_search,最终必须调用 submit_guess 提交猜测。"
                       if self.tools_mode == "native"
                       else "没有解析到动作行。请按格式输出 JSON 动作,最终必须提交一行 guess。")
                messages.append({"role": "user", "content": nag})
                continue

            if res.guess_name:
                break

        self.transcript.append({"turn": turn_no, "events": res.events})
        return res
