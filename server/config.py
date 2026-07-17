# -*- coding: utf-8 -*-
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

AI_BASE_URL = os.getenv("AI_BASE_URL", "")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")
AI_SEARCH_ENABLED = os.getenv("AI_SEARCH_ENABLED", "1") not in ("0", "false", "")
AI_MAX_STEPS = int(os.getenv("AI_MAX_STEPS", "4"))
# native = OpenAI function calling;text = 模型在正文里输出 JSON 指令
# (给不支持 tools 的接口用,比如 grok.com 逆向类);auto = 先试 native,
# 第一轮就发现不支持时自动降级 text
AI_TOOLS_MODE = os.getenv("AI_TOOLS_MODE", "auto").lower()
# 兼容 OpenAI 风格 reasoning_effort；留空时不发送该参数。
AI_REASONING_EFFORT = os.getenv("AI_REASONING_EFFORT", "").strip().lower()
# seconds between AI guesses: fast / normal / slow presets picked per room
AI_SPEED_PRESETS = {"fast": 1, "normal": 3, "slow": 6}
# Per-client protection for the public AI-room creation endpoint.
AI_ROOM_RATE_LIMIT = max(1, int(os.getenv("AI_ROOM_RATE_LIMIT", "3")))
AI_ROOM_RATE_WINDOW_SECONDS = max(
    60, int(os.getenv("AI_ROOM_RATE_WINDOW_SECONDS", "600"))
)

AI_ENABLED = bool(AI_BASE_URL and AI_API_KEY)

# 调试:开启后暴露 /api/room/{code}/debug_answer(仅本地测试用)
DEBUG = os.getenv("CSTRIKLE_DEBUG", "0") not in ("0", "false", "")
