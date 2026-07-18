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
- **随机匹配**:对战大厅一键排队,自动配对一位路人对手
  (固定常规难度 + 2 分钟整局限时);等待方轮询保活,关页自动出队
- **Top20 难度**:谜底限定"进过 HLTV 年度 Top20"的选手——2013–2025
  历年上榜合并去重的全明星池(约 99 人;快照在 `data/hltv_top20.json`,
  源自 Liquipedia 汇总页),全是明星,新手友好。单人、对战、AI 对手都可选;
  难度旁的「?」可展开教练 / 混合位置 / 自由身等属性判定规则说明
- **揭晓卡外链与纠错**:谜底卡片带 Liquipedia / HLTV 链接帮助玩家了解
  选手;"信息有误?"按钮让玩家提交纠错(`POST /api/feedback`,按 IP 限流,
  JSONL 记录到 `FEEDBACK_PATH`,默认 `data/feedback.jsonl`,同时写应用日志;
  只读容器部署时把 `FEEDBACK_PATH` 指到可写卷或 `/tmp`)

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
- 位置先按 Liquipedia infobox 的角色顺序归一化，再由
  `data/player_overrides.json` 保存人工确认的历史/争议结论；IGL 与
  AWPer/Rifler 的武器角色会分开取证，不能仅凭标签或一个统计值硬覆盖
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

### HLTV 角色审核（本地维护）

HLTV 没有供本项目使用的稳定公开 API，普通 HTTP 访问也可能被
Cloudflare 拒绝。维护工具使用本机普通 Chrome 低速访问公开选手页，
只生成缓存和审核文件，不参与线上请求，也不会默认修改正式数据。

```powershell
.\.venv\Scripts\pip install -r requirements-maintenance.txt

# “2k” 通过人工映射明确指 Stewie2K，不会误配 Woro2k
.\.venv\Scripts\python -X utf8 scripts\sync_hltv_roles.py collect `
  --players 2k Maka SmithZz --with-igl-news

# 查看并编辑 .cache/hltv/role_review.json：
# 只有人工确认后才给对应条目填写 decision，例如 "IGL" 或 "Rifler"

# 第一次仅预览；确认无误后才实际写入 player_overrides.json
.\.venv\Scripts\python -X utf8 scripts\sync_hltv_roles.py apply
.\.venv\Scripts\python -X utf8 scripts\sync_hltv_roles.py apply --write
```

默认打开可见 Chrome、页面间隔至少 8 秒并缓存 7 天。`--all` 必须显式
指定，以防误扫全库；同名、低置信度、无近期地图、退役选手和 Sniping
混合区都会进入人工复核。已有 `game_role` 覆盖默认受保护，只有显式使用
`--replace-existing` 才能替换。连续两页收到 403 时工具会主动熔断；
建议先按队伍或争议名单分批传给 `--players`，稍后重跑会复用成功缓存。
若本机没有 Chrome，可执行 `python -m playwright install chromium`，并
传入 `--browser-channel bundled`。

## 结构

```
scraper/build_db.py       选手数据爬虫(可重跑)
scraper/fetch_images.py   照片/队标/国旗爬虫(可重跑)
scraper/iso.py            国名 -> ISO 代码(国旗用)
scripts/sync_hltv_roles.py 本地 HLTV 匹配/角色证据/人工审核
data/players.json         选手库(生成物,约 650+ 人)
data/hltv_player_map.json 已人工确认的本地 page -> HLTV ID 映射
data/images.json          图片索引(生成物)
data/img/                 照片/队标/国旗(生成物)
server/players.py         选手库加载/筛选/名字解析
server/game.py            反馈比对 + 单人对局
server/rooms.py           对战房间 + WebSocket + 整局限时 + AI 调度
server/ai_player.py       LLM agent(native/text 双协议 + 全程转录)
server/main.py            FastAPI 入口
static/                   前端(原生 JS 单页,无构建)
```
