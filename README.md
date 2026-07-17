# CStrikle — 猜 CS 职业哥

自建版 Counter-Strikle(blast.tv 的 CS 选手 Wordle),带个人模式、
双人对战和 **LLM AI 对手**(会上网搜资料、会思考、会喷垃圾话,赛后可
回放它的完整思考过程)。选手照片 / 战队图标 / 国旗全套本地化。

## 玩法

- 猜一名神秘 CS 职业选手,每次猜测按 5 个属性给反馈:
  **国籍**(绿=同国,黄=同赛区)/ **战队**(绿=同队)/
  **年龄**(黄=±2 岁,▲▼指方向)/ **位置**(IGL/AWPer/Rifler,黄=有重叠)/
  **Major 次数**(黄=±1,▲▼指方向)
- 搜索框支持游戏 ID 和真实姓名(不用管变音符号,`Nikola Kovac` 能搜到 NiKo)
- **每日挑战**:全球同一谜底(按日期确定),常规难度,可复制战绩嘲讽朋友
- **无限模式**:赛前自定难度、赛区、现役、Major 年代、猜测次数
- **对战模式**:房间码邀请朋友,或勾选"和 AI 打";双方猜同一谜底,
  先猜中者胜;只能看到对方的反馈色块,看不到具体猜了谁
  - **整局限时**(可选 1/2/3 分钟):时间到还没人猜中就算平局
  - 先出局的一方可以立刻"偷看谜底",不用干等对手打完
  - 结束弹出胜负结算 + 选手大图揭晓卡

## 运行

```powershell
cd D:\TTS\cstrikle
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\uvicorn server.main:app --host 127.0.0.1 --port 8620
# 浏览器打开 http://127.0.0.1:8620
```

## AI 对手

编辑 `.env`,填任意 OpenAI 兼容接口:

```ini
AI_BASE_URL=https://your-proxy/v1
AI_API_KEY=sk-xxx
AI_MODEL=gpt-5.5
AI_SEARCH_ENABLED=1   # 允许 AI 用 DuckDuckGo 搜索
AI_TOOLS_MODE=auto    # native | text | auto(见下)
AI_MAX_STEPS=4        # 单回合最多调用模型 4 次
AI_REASONING_EFFORT=low # 支持该参数的推理模型可降低延迟
AI_ROOM_RATE_LIMIT=3
AI_ROOM_RATE_WINDOW_SECONDS=600
```

AI 是一个带工具的 agent:每轮先写出推理,可调用 `web_search`
查资料、用 `say` 发垃圾话,最后 `submit_guess` 提交猜测。
对局结束后点 **"🧠 看 AI 的思考回放"** 可以看它每一轮想了什么、
搜了什么关键词、搜到了什么、为什么这么猜。

`AI_TOOLS_MODE`:接口不支持 OpenAI function calling 时
(常见于各类逆向代理),把工具改成"正文输出 JSON 指令行"的文本协议,
推理 / 搜索 / 垃圾话 / 回放全套保留。`auto` 会先走 native,
发现接口不认 tools 时自动降级,一般不用动。

`AI_SEARCH_ENABLED=1` 时,搜索由 CStrikle 服务端本地执行
(DuckDuckGo),模型只负责想关键词。如果上游代理已经为模型全局注入
原生 `web_search`(例如 CPA 的 Grok 配置),应设为 `0`,避免同一请求里
出现两个同名 `web_search` 而被上游拒绝。此时搜索完全由模型提供商执行。

公网部署默认按客户端 IP 限制 AI 房间创建频率(10 分钟 3 个),可通过
`AI_ROOM_RATE_LIMIT` 和 `AI_ROOM_RATE_WINDOW_SECONDS` 调整。普通双人房
不受影响。赛后 AI 回放要求房间座位 token,前端会自动携带。

## Docker 部署

项目自带生产用容器配置:

```bash
docker compose up -d --build
docker compose ps
```

`compose.yaml` 默认加入已有的 `rag-stack_rag-net` 外部网络,且不映射
宿主机端口,供同一网络中的 Caddy 反代 `cstrikle:8620`。其他环境请按需
修改网络配置。`.env` 只作为运行时环境文件读取,不会进入镜像。

## 选手数据库

- 数据源:Liquipedia `Majors/Player Database`(所有打过 Major 的选手
  + 每届参赛记录)+ 各选手 infobox(生日/国籍/战队/位置/状态)
  + blast.tv 官方 Counter-Strikle 的 390 现役选手名单
- 位置(Rifler/AWPer/IGL)照搬 Liquipedia infobox 当前标注,
  和你的印象可能有出入(比如 s1mple 去 BC.Game 后官方标的是 Rifler)
- 难度分层:简单=Major≥4 次或现役常客;常规=Major≥2 或 blast 现役名单;
  困难=全部

更新数据(遵守 Liquipedia API 速率限制,约 3 分钟):

```powershell
.\.venv\Scripts\python -X utf8 scraper\build_db.py       # 选手数据 -> data/players.json
.\.venv\Scripts\python -X utf8 scraper\fetch_images.py   # 照片(600px)/队标/国旗 -> data/img/
```

重启服务生效。选手照片约 40MB;战队图标会自动从 Liquipedia commons
挑适合深色底的 icon/darkmode 变体。数据与图片署名:Liquipedia
(CC-BY-SA 3.0),国旗来自 flagcdn。

## 结构

```
scraper/build_db.py       选手数据爬虫(可重跑)
scraper/fetch_images.py   照片/队标/国旗爬虫(可重跑)
scraper/iso.py            国名 -> ISO 代码(国旗用)
data/players.json         选手库(生成物,约 650+ 人)
data/images.json          图片索引(生成物)
data/img/                 照片/队标/国旗(生成物)
server/players.py         选手库加载/筛选/名字解析
server/game.py            反馈比对 + 单人对局
server/rooms.py           对战房间 + WebSocket + 整局限时 + AI 调度
server/ai_player.py       LLM agent(native/text 双协议 + 全程转录)
server/main.py            FastAPI 入口
static/                   前端(原生 JS 单页,无构建)
```
