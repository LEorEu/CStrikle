# -*- coding: utf-8 -*-
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

AI_BASE_URL = os.getenv("AI_BASE_URL", "")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")
AI_SEARCH_ENABLED = os.getenv("AI_SEARCH_ENABLED", "1") not in ("0", "false", "")
AI_MAX_STEPS = int(os.getenv("AI_MAX_STEPS", "2"))
AI_TIMEOUT_SECONDS = max(10, int(os.getenv("AI_TIMEOUT_SECONDS", "35")))
AI_DECISION_TIMEOUT_SECONDS = max(
    3,
    min(
        AI_TIMEOUT_SECONDS,
        int(os.getenv("AI_DECISION_TIMEOUT_SECONDS", "20")),
    ),
)
AI_EXACT_THRESHOLD = max(2, int(os.getenv("AI_EXACT_THRESHOLD", "10")))
AI_SEARCH_CACHE_TTL_SECONDS = max(
    60, int(os.getenv("AI_SEARCH_CACHE_TTL_SECONDS", "3600"))
)
# native = OpenAI function calling;text = 模型在正文里输出 JSON 指令
# (给不支持 tools 的接口用,比如 grok.com 逆向类);auto = 先试 native,
# 第一轮就发现不支持时自动降级 text
AI_TOOLS_MODE = os.getenv("AI_TOOLS_MODE", "auto").lower()
# 兼容 OpenAI 风格 reasoning_effort；留空时不发送该参数。
AI_REASONING_EFFORT = os.getenv("AI_REASONING_EFFORT", "").strip().lower()
# 可选思考模式，主要用于 DeepSeek V4；留空时保持上游模型默认行为。
AI_THINKING_MODE = os.getenv("AI_THINKING_MODE", "").strip().lower()
if AI_THINKING_MODE not in ("enabled", "disabled"):
    AI_THINKING_MODE = ""
# AI 落子后的最短间隔(原 fast/normal/slow 档已砍掉,固定按最快节奏来)
AI_GUESS_DELAY_SECONDS = 1.0
# Per-client protection for the public AI-room creation endpoint.
AI_ROOM_RATE_LIMIT = max(1, int(os.getenv("AI_ROOM_RATE_LIMIT", "3")))
AI_ROOM_RATE_WINDOW_SECONDS = max(
    60, int(os.getenv("AI_ROOM_RATE_WINDOW_SECONDS", "600"))
)

AI_ENABLED = bool(AI_BASE_URL and AI_API_KEY)

# 玩家纠错反馈:JSONL 落盘路径(生产容器只读时指向可写卷或 /tmp),
# 写入失败时仍会记入应用日志,不丢反馈。
FEEDBACK_PATH = Path(
    os.getenv("FEEDBACK_PATH",
              Path(__file__).resolve().parent.parent / "data" / "feedback.jsonl")
)
FEEDBACK_RATE_LIMIT = max(1, int(os.getenv("FEEDBACK_RATE_LIMIT", "5")))
FEEDBACK_RATE_WINDOW_SECONDS = max(
    60, int(os.getenv("FEEDBACK_RATE_WINDOW_SECONDS", "600"))
)

# 调试:开启后暴露 /api/room/{code}/debug_answer(仅本地测试用)
DEBUG = os.getenv("CSTRIKLE_DEBUG", "0") not in ("0", "false", "")
