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

logger = logging.getLogger("uvicorn.error")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
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
  - 战队:✔=当前战队相同(退役/无战队算"无战队")
  - 年龄:✔=相同;≈=相差2岁以内;并提示答案比你猜的更大还是更小
  - 位置:✔=主位置相同(IGL/AWPer/Rifler/Coach);≈=位置有重叠
  - Major次数:✔=相同;≈=相差1;并提示答案更多还是更少
- 谜底范围:{pool_desc}

## 你的做法
1. 先在回复正文里用中文写出你的推理:根据已有反馈,排除了谁、锁定了什么范围、下一步为什么这么猜。
2. 只有反馈不足以判断、且确实需要核对冷门资料时才用 web_search;第一轮不要搜索,每轮最多搜索一次。
3. 你性格嚣张嘴臭但有真本事,可以用 say 对人类输出一句垃圾话/心理战(中文),但别刷屏。信息足够时,say 和 submit_guess 必须放在同一次回复里。
4. 每轮必须尽快调用 submit_guess 提交一个猜测,不要只聊天或只写推理。昵称必须是真实职业选手的游戏 ID;如果提示选手不在库里,换一个再试。

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
        self.events = []          # transcript of this turn


class AIPlayer:
    def __init__(self, db: PlayerDB, pool_desc: str,
                 on_say=None, on_status=None):
        self.db = db
        self.pool_desc = pool_desc
        self.on_say = on_say          # async fn(message)
        self.on_status = on_status    # async fn(status, detail)
        self.client = AsyncOpenAI(base_url=config.AI_BASE_URL,
                                  api_key=config.AI_API_KEY, timeout=120)
        self.transcript = []          # [{turn, events: [...]}]
        # native | text;auto 从 native 起步,发现接口不支持时降级
        self.tools_mode = ("text" if config.AI_TOOLS_MODE == "text" else "native")

    # ------------------------------------------------------------ tools
    async def _web_search(self, query: str) -> str:
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
        return "\n\n".join(
            f"[{i+1}] {h.get('title', '')}\n{h.get('body', '')}"
            for i, h in enumerate(hits)
        )

    # ------------------------------------------------------------ turn
    def _history_block(self, my_rows, opp_info) -> str:
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
        lines.append("\n请推理并提交你本轮的猜测。")
        return "\n".join(lines)

    # ------------------------------------------------- shared tool actions
    async def _do_search(self, q: str, res: TurnResult) -> str:
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
        messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": self._history_block(my_rows, opp_info)},
        ]
        tools = [t for t in TOOLS
                 if config.AI_SEARCH_ENABLED or t["function"]["name"] != "web_search"]

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
                    }
                    if config.AI_REASONING_EFFORT:
                        request["reasoning_effort"] = config.AI_REASONING_EFFORT
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
                    }
                    if config.AI_REASONING_EFFORT:
                        request["reasoning_effort"] = config.AI_REASONING_EFFORT
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
                raise
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
                    if fn == "web_search":
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
                nag = ("请继续:需要时调用 web_search,最终必须调用 submit_guess 提交猜测。"
                       if self.tools_mode == "native"
                       else "没有解析到动作行。请按格式输出 JSON 动作,最终必须提交一行 guess。")
                messages.append({"role": "user", "content": nag})
                continue

            if res.guess_name:
                break

        self.transcript.append({"turn": turn_no, "events": res.events})
        return res
