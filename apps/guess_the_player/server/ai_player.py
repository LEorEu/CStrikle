# -*- coding: utf-8 -*-
"""
Three AI styles: free-form model, candidate-guided model, and deterministic solver.

The replay records player-readable decision summaries and public model output.
Provider-private chain-of-thought is not required.
"""
import asyncio
import json
import logging
import random
import re
import time

from openai import AsyncOpenAI

from . import config
from .game import feedback_text
from playerdb.players import PlayerDB
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
                    "reason": {
                        "type": "string",
                        "description": "一句简短中文理由，说明为什么想猜这个人",
                    },
                },
                "required": ["nickname", "reason"],
            },
        },
    },
]

EASY_SYSTEM_PROMPT = """你是一名很懂 CS 电竞圈、但这局只凭自己感觉玩的真人对手,正在和玩家对战 FribergCS2(猜 CS 职业选手的 Wordle 类游戏)。

## 规则
- 双方猜同一个神秘职业选手,谁先猜中谁赢。你每轮提交一个猜测。
- 每次猜测后会得到逐属性反馈:
  - 国籍:✔=同一国家;≈=同一赛区;✘=不同赛区
  - 战队:✔=当前战队相同(自由身互相判✔)
  - 年龄:✔=相同;≈=相差2岁以内;并提示答案更大还是更小
  - 位置:✔=主位置相同(IGL/AWPer/Rifler/Coach);≈=位置有重叠
  - Major次数、Major冠军数:✔=相同;≈=相差1;并提示答案更多还是更少
- 谜底范围:{pool_desc}

## 你的玩法
1. 阅读自己之前每次猜测的完整反馈,再凭你的 CS 常识、印象和直觉自由猜一个人。
2. 服务器不会给你候选名单,也不会替你计算最优解;你可以猜偏,甚至误读线索。
3. {search_rule}
4. 每轮调用一次 say 和玩家说一句简短的话,不要刷屏；信息足够时与 submit_guess 放在同一次回复里。
5. 每轮必须尽快调用 submit_guess,只提交一个真实职业选手的游戏 ID,并附上一句玩家能看懂的简短理由。
6. 回复中可以简短说出判断思路,不要写冗长的数学推导或逐步内心独白。

注意:你看不到对手猜了谁,只能看到对手已用的猜测次数和反馈颜色。"""

SYSTEM_PROMPT = """你是一名 CS 电竞圈老油条,正在和一个人类玩家对战 FribergCS2(猜 CS 职业选手的 Wordle 类游戏)。

## 规则
- 双方猜同一个神秘职业选手,谁先猜中谁赢。你每轮提交一个猜测。
- 每次猜测后会得到逐属性反馈:
  - 国籍:✔=同一国家;≈=同一赛区(欧洲/独联体/北美/南美/亚洲/大洋洲等);✘=都不沾边
  - 战队:✔=当前战队相同(无战队的人统一算"自由身",互相判✔)
  - 年龄:✔=相同;≈=相差2岁以内;并提示答案比你猜的更大还是更小
  - 位置:✔=主位置相同(IGL/AWPer/Rifler/Coach);≈=位置有重叠
  - Major次数:✔=相同;≈=相差1;并提示答案更多还是更少
  - Major冠军数:✔=相同;≈=相差1;并提示答案更多还是更少
- 谜底范围:{pool_desc}

## 你的任务
1. 服务器会给出与全部反馈相符的可选人名单。
2. 从名单里挑一个你自己最想猜的人；可以按 CS 常识、个人偏好或直觉选择，不要求数学最优。
3. 必须在同一次回复中调用 say 和 submit_guess：说一句简短中文，再提交一次猜测和玩家能看懂的理由；不要搜索。
4. 不允许提交名单之外或已经猜过的人。

注意:你看不到对手猜了谁,只能看到对手已用的猜测次数和反馈颜色。"""

# 不支持 function calling 的接口(如 grok.com 逆向)改用正文 JSON 指令
TEXT_PROTOCOL = """

## 动作指令格式(本接口不支持工具调用,改用以下方式)
把聊天和猜测写在回复正文里,每个动作单独占一行:
{"action": "say", "message": "对玩家说的一句简短中文"}
{"action": "guess", "nickname": "选手游戏ID", "reason": "一句简短中文理由"}
不要搜索；同一次回复必须同时包含 say 和 guess。"""

EASY_TEXT_PROTOCOL = """

## 动作指令格式(本接口不支持工具调用,改用以下方式)
把动作写在回复正文里,每个动作单独占一行,内容是一个 JSON 对象:
{"action": "search", "query": "搜索关键词"}
{"action": "say", "message": "对玩家说的话"}
{"action": "guess", "nickname": "选手游戏ID", "reason": "一句简短中文理由"}
可以先写一两句判断思路。需要搜索就先发 search,等系统返回结果;
信息够了就发 guess,每轮最终必须提交一次 guess。"""

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
        thinking_mode: str | None = None,
        ai_level: str = "normal",
    ):
        self.db = db
        self.answer_pool = tuple(answer_pool)
        self.solver = PlayerSolver(
            db,
            answer_pool,
            exact_threshold=config.AI_EXACT_THRESHOLD,
        )
        self.pool_desc = pool_desc
        self.max_guesses = max_guesses
        self.ai_level = ai_level if ai_level in ("easy", "normal", "hard") else "normal"
        self.on_say = on_say          # async fn(message)
        self.on_status = on_status    # async fn(status, detail)
        self.reasoning_effort = (
            config.AI_REASONING_EFFORT
            if reasoning_effort is None
            else reasoning_effort.strip().lower()
        )
        requested_thinking = (
            config.AI_THINKING_MODE
            if thinking_mode is None
            else thinking_mode.strip().lower()
        )
        self.thinking_mode = (
            requested_thinking
            if requested_thinking in ("enabled", "disabled")
            else ""
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
        self._allowed_guess_pages: set[str] | None = None
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
                             f"({row['player']['country']},{row['player']['team'] or '自由身'})"
                             f" -> {feedback_text(row['cells'])}")
        else:
            lines.append("## 这是你的第一轮猜测,还没有任何反馈。")
        if opp_info:
            lines.append(f"\n## 对手进度\n{opp_info}")
        lines.append(
            f"\n## 与全部反馈相符的可选人（{len(analysis.candidates)} 人）"
        )
        for player in analysis.candidates[:30]:
            age = player.age()
            lines.append(
                f"- {player.nickname}: {player.country} / {player.team_label} / "
                f"{player.primary_role} / {age if age is not None else '?'} 岁 / "
                f"Major {player.majors_count or 0} 次 / 冠军 {player.majors_won}"
            )
        if len(analysis.candidates) > 30:
            lines.append(f"- 另有 {len(analysis.candidates) - 30} 人未展开")
        lines.append("\n请从上面的可选人中挑一个你自己最想猜的，立即提交。")
        return "\n".join(lines)

    def _freeform_history_block(self, my_rows, opp_info) -> str:
        lines = []
        if my_rows:
            lines.append("## 你已有的猜测和反馈")
            for i, row in enumerate(my_rows, 1):
                player = row["player"]
                lines.append(
                    f"{i}. 猜了 {player['nickname']}"
                    f"({player['country']},{player['team'] or '自由身'})"
                    f" -> {feedback_text(row['cells'])}"
                )
        else:
            lines.append("## 这是你的第一轮猜测,还没有任何反馈。")
        if opp_info:
            lines.append(f"\n## 对手进度\n{opp_info}")
        lines.append(
            "\n请自己理解这些线索,凭 CS 常识和直觉自由选择本轮人选。"
            "不要等待候选名单或求解结果。"
        )
        return "\n".join(lines)

    @staticmethod
    def _decision_event(
        strategy: str,
        chosen,
        summary: str,
        explanation: list[str],
        candidate_count: int | None = None,
        shortlist=(),
    ) -> dict:
        return {
            "type": "decision",
            "strategy": strategy,
            "chosen": chosen.nickname,
            "summary": summary,
            "explanation": explanation,
            "candidate_count": candidate_count,
            "shortlist": [player.nickname for player in shortlist],
        }

    # ------------------------------------------------- shared tool actions
    async def _do_search(self, q: str, res: TurnResult) -> str:
        if res.searches_used >= 1:
            return "本轮搜索次数已用完；请直接提交你的猜测。"
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
        elif (
            self._allowed_guess_pages is not None
            and p.page not in self._allowed_guess_pages
        ):
            out = f"{p.nickname} 与已有反馈不符，请从本轮可选人名单中选择。"
            res.events.append({"type": "guess_rejected", "name": name, "reason": out})
        else:
            res.guess_name = p.page
            res.events.append({"type": "guess", "name": p.nickname})
            out = "OK"
        return out

    def _system_prompt(self, freeform: bool = False) -> str:
        prompt = EASY_SYSTEM_PROMPT if freeform else SYSTEM_PROMPT
        search_rule = (
            "第一轮不要搜索。后续只有确实想核对冷门资料时才调用 "
            "ddgs_search,每轮最多一次。"
            if config.AI_SEARCH_ENABLED
            else
            "项目不提供额外搜索工具；直接根据反馈、你的 CS 常识以及"
            "接口自动提供的信息尽快猜测。"
        )
        sp = prompt.format(
            pool_desc=self.pool_desc,
            search_rule=search_rule,
        )
        if self.tools_mode == "text":
            sp += EASY_TEXT_PROTOCOL if freeform else TEXT_PROTOCOL
        return sp

    async def _say_for_fixed_guess(
        self,
        chosen,
        my_rows: list,
        opp_info: str,
        strategy: str,
        res: TurnResult,
        turn_no: int,
    ) -> bool:
        """Let the model chat without allowing it to change a server-picked move."""
        if self.on_status:
            await self.on_status(
                "thinking",
                f"{strategy}模式正在准备说一句话…",
            )
        system = (
            "你正在玩 FribergCS2。服务器已经决定本轮猜 "
            f"{chosen.nickname}，你不能更换人选，也不能声称自己知道谜底。"
            "请根据已有反馈，用中文对玩家说一句简短、有 CS 玩家味道的话。"
            "不要搜索，不要解释数学过程，必须立即调用 say，且只调用一次。"
        )
        if self.tools_mode == "text":
            system += (
                '\n接口不支持工具调用，请只输出一行动作：'
                '{"action":"say","message":"一句简短中文"}'
            )
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": self._freeform_history_block(my_rows, opp_info),
            },
        ]
        say_tool = next(
            tool for tool in TOOLS
            if tool["function"]["name"] == "say"
        )
        request = {
            "model": config.AI_MODEL,
            "messages": messages,
            "metadata": {
                "client": "cstrikle",
                "search_provider": "disabled",
            },
        }
        if self.tools_mode == "native":
            request["tools"] = [say_tool]
            request["tool_choice"] = {
                "type": "function",
                "function": {"name": "say"},
            }
        if self.reasoning_effort:
            request["reasoning_effort"] = self.reasoning_effort
        if self.thinking_mode:
            request["extra_body"] = {
                "thinking": {"type": self.thinking_mode},
            }

        started = time.perf_counter()
        try:
            resp = await asyncio.wait_for(
                self.client.chat.completions.create(**request),
                timeout=config.AI_DECISION_TIMEOUT_SECONDS,
            )
        except Exception as e:
            elapsed = time.perf_counter() - started
            logger.warning(
                "AI chat failed model=%s level=%s turn=%s elapsed=%.2fs: %s",
                config.AI_MODEL, self.ai_level, turn_no, elapsed, e,
            )
            res.events.append({
                "type": "chat_error",
                "error": type(e).__name__,
                "message": str(e)[:500],
                "elapsed_seconds": round(elapsed, 3),
            })
            return False

        elapsed = time.perf_counter() - started
        logger.info(
            "AI chat model=%s level=%s turn=%s elapsed=%.2fs",
            config.AI_MODEL, self.ai_level, turn_no, elapsed,
        )
        msg = resp.choices[0].message
        actions = []
        if not getattr(msg, "tool_calls", None) and msg.content:
            for line in ACTION_RE.findall(msg.content):
                try:
                    action = json.loads(line)
                    if isinstance(action, dict) and action.get("action"):
                        actions.append(action)
                except json.JSONDecodeError:
                    pass
        if (
            actions
            and self.tools_mode == "native"
            and config.AI_TOOLS_MODE == "auto"
        ):
            self.tools_mode = "text"

        if getattr(msg, "tool_calls", None):
            for tool_call in msg.tool_calls:
                if tool_call.function.name != "say":
                    continue
                try:
                    args = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                text = str(args.get("message", "")).strip()
                if text:
                    await self._do_say(text, res)
                    return True
        for action in actions:
            if action.get("action") != "say":
                continue
            text = str(action.get("message", "")).strip()
            if text:
                await self._do_say(text, res)
                return True

        shown = ACTION_RE.sub("", msg.content or "").strip()
        if shown:
            await self._do_say(shown, res)
            return True
        res.events.append({
            "type": "chat_error",
            "error": "MissingSay",
            "message": "模型没有返回聊天内容",
            "elapsed_seconds": round(elapsed, 3),
        })
        return False

    async def _take_easy_turn(
        self,
        my_rows: list,
        opp_info: str,
        guessed_names: set,
        guessed_pages: set[str],
        turn_no: int,
    ) -> TurnResult:
        """Run the original free-form model agent without solver restrictions."""
        res = TurnResult()
        fallback_pool = [
            player for player in self.answer_pool
            if player.page not in guessed_pages
        ]
        if not fallback_pool:
            fallback_pool = [
                player for player in self.db.answer_players
                if player.page not in guessed_pages
            ]
        fallback = random.choice(fallback_pool)
        res.fallback_guess = fallback.page

        # 下饭模式刻意不接收求解器候选，也不限制模型必须猜某个人。
        self._required_guess = None
        self._allowed_guess_pages = None
        messages = [
            {"role": "system", "content": self._system_prompt(freeform=True)},
            {
                "role": "user",
                "content": self._freeform_history_block(my_rows, opp_info),
            },
        ]
        can_search = bool(config.AI_SEARCH_ENABLED and my_rows)
        tool_names = {"say", "submit_guess"}
        if can_search:
            tool_names.add("ddgs_search")
        tools = [
            tool for tool in TOOLS
            if tool["function"]["name"] in tool_names
        ]
        decision_deadline = (
            time.perf_counter() + config.AI_DECISION_TIMEOUT_SECONDS
        )

        for step in range(max(1, config.AI_MAX_STEPS)):
            if self.on_status:
                await self.on_status(
                    "thinking",
                    (
                        "下饭模式正在看线索，凭感觉选一个人…"
                        if step == 0
                        else "下饭模式正在确定最后的猜测…"
                    ),
                )
            started = time.perf_counter()
            try:
                remaining_timeout = decision_deadline - time.perf_counter()
                if remaining_timeout <= 0:
                    raise asyncio.TimeoutError
                request = {
                    "model": config.AI_MODEL,
                    "messages": messages,
                    "metadata": {
                        "client": "cstrikle",
                        "search_provider": "ddgs",
                    },
                }
                if self.tools_mode == "native":
                    request["tools"] = tools
                    if step > 0:
                        request["tool_choice"] = {
                            "type": "function",
                            "function": {"name": "submit_guess"},
                        }
                if self.reasoning_effort:
                    request["reasoning_effort"] = self.reasoning_effort
                if self.thinking_mode:
                    request["extra_body"] = {
                        "thinking": {"type": self.thinking_mode},
                    }
                resp = await asyncio.wait_for(
                    self.client.chat.completions.create(**request),
                    timeout=remaining_timeout,
                )
            except Exception as e:
                elapsed = time.perf_counter() - started
                logger.warning(
                    "AI free-form call failed model=%s turn=%s step=%s "
                    "elapsed=%.2fs: %s",
                    config.AI_MODEL, turn_no, step + 1, elapsed, e,
                )
                if (
                    self.tools_mode == "native"
                    and config.AI_TOOLS_MODE == "auto"
                    and any(
                        word in str(e).lower()
                        for word in ("tool", "function")
                    )
                ):
                    self.tools_mode = "text"
                    messages[0] = {
                        "role": "system",
                        "content": self._system_prompt(freeform=True),
                    }
                    res.events.append({
                        "type": "forced_guess",
                        "name": "",
                        "reason": "接口不支持工具调用，已切换文本指令模式",
                    })
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
                "AI free-form call model=%s turn=%s step=%s elapsed=%.2fs",
                config.AI_MODEL, turn_no, step + 1, elapsed,
            )
            msg = resp.choices[0].message
            usage = getattr(resp, "usage", None)
            if usage:
                prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                completion_tokens = int(
                    getattr(usage, "completion_tokens", 0) or 0
                )
                details = getattr(usage, "prompt_tokens_details", None)
                cached_tokens = int(
                    getattr(details, "cached_tokens", 0)
                    or getattr(usage, "prompt_cache_hit_tokens", 0)
                    or 0
                )
                res.events.append({
                    "type": "usage",
                    "prompt_tokens": prompt_tokens,
                    "cached_tokens": cached_tokens,
                    "cache_miss_tokens": max(
                        0, prompt_tokens - cached_tokens
                    ),
                    "completion_tokens": completion_tokens,
                    "total_tokens": int(
                        getattr(usage, "total_tokens", 0)
                        or prompt_tokens + completion_tokens
                    ),
                })
            reasoning = getattr(msg, "reasoning_content", None)
            if reasoning:
                res.events.append({"type": "reasoning", "text": reasoning})

            actions = []
            if not getattr(msg, "tool_calls", None) and msg.content:
                for line in ACTION_RE.findall(msg.content):
                    try:
                        action = json.loads(line)
                        if isinstance(action, dict) and action.get("action"):
                            actions.append(action)
                    except json.JSONDecodeError:
                        pass
            if (
                actions
                and self.tools_mode == "native"
                and config.AI_TOOLS_MODE == "auto"
            ):
                self.tools_mode = "text"
                messages[0] = {
                    "role": "system",
                    "content": self._system_prompt(freeform=True),
                }

            if msg.content:
                shown = (
                    ACTION_RE.sub("", msg.content).strip()
                    if actions else msg.content
                )
                if shown:
                    res.events.append({"type": "thinking", "text": shown})

            if getattr(msg, "tool_calls", None):
                if hasattr(msg, "model_dump"):
                    messages.append(msg.model_dump(exclude_none=True))
                else:
                    messages.append({
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    })
                for tc in msg.tool_calls:
                    fn = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    if fn == "ddgs_search" and can_search:
                        out = await self._do_search(
                            str(args.get("query", "")), res
                        )
                    elif fn == "say":
                        out = await self._do_say(
                            str(args.get("message", "")), res
                        )
                    elif fn == "submit_guess":
                        reason = str(args.get("reason", "")).strip()[:300]
                        if reason:
                            res.events.append({
                                "type": "thinking",
                                "text": reason,
                            })
                        out = self._do_guess(
                            str(args.get("nickname", "")),
                            res,
                            guessed_names,
                        )
                    else:
                        out = "本轮不能使用这个动作，请直接提交猜测。"
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": out,
                    })
            elif actions:
                messages.append({
                    "role": "assistant",
                    "content": msg.content,
                })
                feedback = []
                for action in actions:
                    act = action.get("action")
                    if act == "search" and can_search:
                        out = await self._do_search(
                            str(action.get("query", "")), res
                        )
                        feedback.append(f"[search 结果]\n{out}")
                    elif act == "say":
                        await self._do_say(
                            str(action.get("message", "")), res
                        )
                    elif act == "guess":
                        reason = str(
                            action.get("reason", "")
                        ).strip()[:300]
                        if reason:
                            res.events.append({
                                "type": "thinking",
                                "text": reason,
                            })
                        out = self._do_guess(
                            str(action.get("nickname", "")),
                            res,
                            guessed_names,
                        )
                        if out != "OK":
                            feedback.append(f"[系统] {out}")
                    elif act == "search":
                        feedback.append("[系统] 第一轮不能搜索，请直接猜。")
                if not res.guess_name:
                    feedback.append("请现在提交一行 guess。")
                    messages.append({
                        "role": "user",
                        "content": "\n\n".join(feedback),
                    })
            else:
                messages.extend([
                    {
                        "role": "assistant",
                        "content": msg.content or "",
                    },
                    {
                        "role": "user",
                        "content": (
                            "请直接调用 submit_guess 提交一个真实选手。"
                            if self.tools_mode == "native"
                            else "没有解析到动作，请按格式提交一行 guess。"
                        ),
                    },
                ])

            if res.guess_name:
                break

        chosen = (
            self.db.by_page.get(res.guess_name)
            if res.guess_name else fallback
        )
        if res.guess_name:
            summary = (
                f"AI 看过已有反馈后，凭自己的 CS 印象猜了 "
                f"{chosen.nickname}。"
            )
            explanation = [
                "下饭难度不会使用候选过滤或最优求解。",
                "它会参考线索，但也可能凭印象猜偏。",
            ]
        else:
            summary = (
                f"AI 没在限定时间内完成选择，"
                f"本轮将改用备用人选 {fallback.nickname}。"
            )
            explanation = [
                "下饭难度原本会自己阅读反馈并自由选择。",
                "为了不让整局卡住，请求失败时会自动换一个人继续。",
            ]
        res.events.insert(
            0,
            self._decision_event(
                "下饭",
                chosen,
                summary,
                explanation,
            ),
        )
        self.transcript.append({"turn": turn_no, "events": res.events})
        return res

    async def take_turn(self, my_rows: list, opp_info: str,
                        guessed_names: set) -> TurnResult:
        res = TurnResult()
        turn_no = len(my_rows) + 1
        remaining_turns = max(1, self.max_guesses - len(my_rows))
        guessed_pages = {
            row.get("player", {}).get("page", "")
            for row in my_rows
            if row.get("player", {}).get("page")
        }
        self._required_guess = None
        self._allowed_guess_pages = None

        if self.ai_level == "easy":
            return await self._take_easy_turn(
                my_rows,
                opp_info,
                guessed_names,
                guessed_pages,
                turn_no,
            )

        if self.on_status:
            await self.on_status(
                "thinking",
                (
                    "作弊模式正在计算最合适的下一手…"
                    if self.ai_level == "hard"
                    else "普通模式正在整理上一手线索…"
                ),
            )
        analysis = await asyncio.to_thread(
            self.solver.analyze,
            my_rows,
            remaining_turns,
            guessed_pages,
        )
        previous_candidates = self.solver.filter_candidates(my_rows[:-1])
        previous_candidate_count = (
            len(previous_candidates)
            if previous_candidates
            else len(self.solver.initial_candidates)
        )

        if self.ai_level == "hard":
            chosen = analysis.recommended
            res.guess_name = chosen.page
            res.fallback_guess = chosen.page
            if my_rows:
                summary = (
                    f"上一手线索把可能人选从 {previous_candidate_count} 人"
                    f"缩小到 {len(analysis.candidates)} 人，最后选择 {chosen.nickname}。"
                )
            else:
                summary = (
                    f"从 {len(analysis.candidates)} 名可能谜底中，"
                    f"直接选择最容易继续排除的 {chosen.nickname}。"
                )
            explanation = [
                "作弊难度会读取每一格反馈，并比较所有可用猜法。",
                (
                    "现在只剩一个符合线索的人，直接提交答案。"
                    if len(analysis.candidates) == 1
                    else "这一手优先让下一轮剩下的人尽可能少。"
                ),
            ]
            await self._say_for_fixed_guess(
                chosen,
                my_rows,
                opp_info,
                "作弊",
                res,
                turn_no,
            )
            res.events.insert(
                0,
                self._decision_event(
                    "作弊",
                    chosen,
                    summary,
                    explanation,
                    candidate_count=len(analysis.candidates),
                    shortlist=analysis.candidates[:12],
                ),
            )
            res.events.append({"type": "guess", "name": chosen.nickname})
            self.transcript.append({"turn": turn_no, "events": res.events})
            return res

        if not my_rows:
            opening_moves = self.solver.rank_moves(
                analysis.candidates,
                guessed_pages=guessed_pages,
                limit=5,
            )
            chosen = random.choice(list(opening_moves)).player
            res.guess_name = chosen.page
            res.fallback_guess = chosen.page
            await self._say_for_fixed_guess(
                chosen,
                my_rows,
                opp_info,
                "普通",
                res,
                turn_no,
            )
            res.events.insert(
                0,
                self._decision_event(
                    "普通",
                    chosen,
                    f"从五个适合开局的人选里随机挑了 {chosen.nickname}。",
                    [
                        "这五个人都能让第一轮反馈比较有区分度。",
                        "开局只在五人中随机，不会每局都固定猜同一个人。",
                    ],
                    candidate_count=len(analysis.candidates),
                    shortlist=[move.player for move in opening_moves],
                ),
            )
            res.events.append({"type": "guess", "name": chosen.nickname})
            self.transcript.append({"turn": turn_no, "events": res.events})
            return res

        candidate_pool = [
            player for player in analysis.candidates
            if player.page not in guessed_pages
        ]
        if not candidate_pool:
            candidate_pool = [
                player for player in self.answer_pool
                if player.page not in guessed_pages
            ]
        fallback = random.choice(candidate_pool)
        res.fallback_guess = fallback.page

        if len(candidate_pool) == 1:
            chosen = candidate_pool[0]
            res.guess_name = chosen.page
            await self._say_for_fixed_guess(
                chosen,
                my_rows,
                opp_info,
                "普通",
                res,
                turn_no,
            )
            res.events.insert(
                0,
                self._decision_event(
                    "普通",
                    chosen,
                    f"上一手线索只剩 {chosen.nickname} 一个人符合，直接提交。",
                    [
                        f"可能人选从 {previous_candidate_count} 人缩小到 1 人。",
                        "已经没有需要二选一的地方，所以不用再等待 AI 请求。",
                    ],
                    candidate_count=1,
                    shortlist=(chosen,),
                ),
            )
            res.events.append({"type": "guess", "name": chosen.nickname})
            self.transcript.append({"turn": turn_no, "events": res.events})
            return res

        self._allowed_guess_pages = {player.page for player in candidate_pool}
        if self.on_status:
            await self.on_status(
                "thinking",
                f"普通模式正在从 {len(candidate_pool)} 名可能人选中做决定…",
            )
        messages = [
            {"role": "system", "content": self._system_prompt()},
            {
                "role": "user",
                "content": self._history_block(my_rows, opp_info, analysis),
            },
        ]
        decision_tools = [
            tool for tool in TOOLS
            if tool["function"]["name"] in {"say", "submit_guess"}
        ]
        started = time.perf_counter()
        try:
            request = {
                "model": config.AI_MODEL,
                "messages": messages,
                "metadata": {
                    "client": "cstrikle",
                    "search_provider": "ddgs",
                },
            }
            if self.tools_mode == "native":
                request["tools"] = decision_tools
                request["tool_choice"] = "required"
            if self.reasoning_effort:
                request["reasoning_effort"] = self.reasoning_effort
            if self.thinking_mode:
                request["extra_body"] = {
                    "thinking": {"type": self.thinking_mode},
                }
            resp = await asyncio.wait_for(
                self.client.chat.completions.create(**request),
                timeout=config.AI_DECISION_TIMEOUT_SECONDS,
            )
        except Exception as e:
            elapsed = time.perf_counter() - started
            logger.warning(
                "AI decision failed model=%s turn=%s elapsed=%.2fs: %s",
                config.AI_MODEL, turn_no, elapsed, e,
            )
            res.events.append({
                "type": "model_error",
                "error": type(e).__name__,
                "message": str(e)[:500],
                "elapsed_seconds": round(elapsed, 3),
            })
        else:
            elapsed = time.perf_counter() - started
            logger.info(
                "AI decision model=%s turn=%s elapsed=%.2fs",
                config.AI_MODEL, turn_no, elapsed,
            )
            msg = resp.choices[0].message
            usage = getattr(resp, "usage", None)
            if usage:
                prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
                details = getattr(usage, "prompt_tokens_details", None)
                cached_tokens = int(
                    getattr(details, "cached_tokens", 0)
                    or getattr(usage, "prompt_cache_hit_tokens", 0)
                    or 0
                )
                res.events.append({
                    "type": "usage",
                    "prompt_tokens": prompt_tokens,
                    "cached_tokens": cached_tokens,
                    "cache_miss_tokens": max(0, prompt_tokens - cached_tokens),
                    "completion_tokens": completion_tokens,
                    "total_tokens": int(
                        getattr(usage, "total_tokens", 0)
                        or prompt_tokens + completion_tokens
                    ),
                })
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
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    if tc.function.name == "say":
                        await self._do_say(
                            str(args.get("message", "")),
                            res,
                        )
                    elif (
                        tc.function.name == "submit_guess"
                        and not res.guess_name
                    ):
                        reason = str(args.get("reason", "")).strip()[:300]
                        if reason:
                            res.events.append({
                                "type": "thinking",
                                "text": reason,
                            })
                        self._do_guess(
                            str(args.get("nickname", "")),
                            res,
                            guessed_names,
                        )
            elif actions:
                for a in actions:
                    if a.get("action") == "say":
                        await self._do_say(
                            str(a.get("message", "")),
                            res,
                        )
                    elif a.get("action") == "guess" and not res.guess_name:
                        reason = str(a.get("reason", "")).strip()[:300]
                        if reason:
                            res.events.append({"type": "thinking", "text": reason})
                        self._do_guess(
                            str(a.get("nickname", "")),
                            res,
                            guessed_names,
                        )

        chosen = (
            self.db.by_page.get(res.guess_name)
            if res.guess_name
            else fallback
        )
        if res.guess_name:
            summary = (
                f"上一手线索把可能人选从 {previous_candidate_count} 人"
                f"缩小到 {len(candidate_pool)} 人，AI 自己选择了 {chosen.nickname}。"
            )
            explanation = [
                "服务器只整理与全部反馈相符的人，没有指定唯一答案。",
                "最终人选由 AI 按自己的 CS 常识和偏好决定。",
            ]
        else:
            summary = (
                f"AI 没在 {config.AI_DECISION_TIMEOUT_SECONDS} 秒内完成选择，"
                f"改用备用人选 {fallback.nickname}。"
            )
            explanation = [
                f"上一手反馈把范围从 {previous_candidate_count} 人缩小到 "
                f"{len(candidate_pool)} 人。",
                "为了不让整局卡住，本轮直接从这些人里挑一个继续。",
            ]
        res.events.insert(
            0,
            self._decision_event(
                "普通",
                chosen,
                summary,
                explanation,
                candidate_count=len(candidate_pool),
                shortlist=candidate_pool[:12],
            ),
        )
        self.transcript.append({"turn": turn_no, "events": res.events})
        return res
