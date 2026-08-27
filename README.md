# CStrikle — 猜 CS 职业哥

自建版 Counter-Strikle(blast.tv 的 CS 选手 Wordle),带个人模式、
双人对战和 **LLM AI 对手**(会上网搜资料、会思考、会喷垃圾话,赛后可
回放它的完整思考过程)。选手照片 / 战队图标 / 国旗全套本地化。

> **这个仓库里有两个游戏。** 这份 README 说的是已经上线的**猜选手**。
> 另一个是在做的 **Blind Draft**(用 $15 签 5 名选手组队去打 Major),
> 两边共用同一份选手数据库。文档索引见 **[docs/](docs/)**,
> Blind Draft 从 [docs/blind-draft/](docs/blind-draft/) 进。

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
AI_TOOLS_MODE=auto
AI_REASONING_EFFORT=low
AI_DECISION_TIMEOUT_SECONDS=20
AI_ROOM_RATE_LIMIT=3
AI_ROOM_RATE_WINDOW_SECONDS=600
```

AI 有三种强度：

- 下饭：模型读取完整反馈后，凭自己的 CS 常识和直觉自由猜，不使用候选过滤或求解器；第一轮不搜索，后续每轮最多搜索一次。
- 普通：首轮从信息增益前五随机开局；之后服务器只整理符合反馈的候选，由模型自主选择。
- 作弊：全程使用确定性求解器的最优落子和小集合精确求解。

下饭每轮最多进行 `AI_MAX_STEPS` 次模型动作，多步共同受
`AI_DECISION_TIMEOUT_SECONDS` 的 20 秒总预算限制；普通和作弊每轮最多等待一次
模型响应。模型超时或没有提交有效人选时，服务器仍会使用已经确定的合法人选继续。
三档都提供 AI 聊天：下饭和普通尽量在猜测响应里同时调用 `say`，作弊由求解器
确定落子后只让模型负责说一句话；聊天失败不会改变猜测结果。
对局结束后可查看玩家语言的 AI 决策回放。

`AI_TOOLS_MODE=text` 可用于不支持 OpenAI function calling 的兼容接口；
`auto`/`native` 使用 `submit_guess` 工具。普通模式的选人请求不会调用联网搜索，
避免搜索和二次工具调用拖慢回合。

标准对战难度固定 8 次猜测、整局 2 分钟；自定义房仍可选择不限时或
1/2/3 分钟。服务端会把旧客户端提交的标准难度 60 秒设置统一纠正为 120 秒。

需要评估不支持 function calling 的兼容接口时，可使用隔离基准工具：

```bash
python scripts/benchmark_text_provider.py \
  --base-url https://provider.example/v1 \
  --model model-name \
  --key-config /secure/provider-config.json \
  --key-field auth-key \
  --samples 5 --timeout 8
```

工具不会读取项目 `.env` 或打印密钥，会用真实反馈生成歧义候选，并检查正文
JSON 是否选择了合法选手。

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
  `data/manual/player_overrides.json` 保存人工确认的历史/争议结论；IGL 与
  AWPer/Rifler 的武器角色会分开取证，不能仅凭标签或一个统计值硬覆盖
- 难度分层:简单=Major≥4 次或现役常客;常规=Major≥2 或 blast 现役名单;
  困难=全部

更新数据(遵守 Liquipedia API 速率限制,约 3 分钟):

```powershell
.\.venv\Scripts\python -X utf8 scraper\build_db.py       # 选手数据 -> data/players.json
.\.venv\Scripts\python -X utf8 scraper\fetch_images.py   # 照片(600px)/队标/国旗 -> data/img/
```

直接跑会立即覆盖正式库;更稳的方式是走 staging(管理页「数据更新」
就是这么做的,也可手动 `--out data/players.staging.json` 后在管理页
过目 diff 再发布)。

重启服务生效。选手照片约 24MB;战队图标会自动从 Liquipedia commons
挑适合深色底的 icon/darkmode 变体。数据与图片署名:Liquipedia
(CC-BY-SA 3.0),国旗来自 flagcdn。

### 图片投递

- **尺寸不缩**:结算揭晓卡按 240px 渲染,高分屏要 480px,所以照片保持
  600px 源尺寸
- **PNG 照片自动转同尺寸 WebP**:Liquipedia 常给抠图 PNG,照片内容用
  无损格式存等于白扔几百 KB(最大一张 935KB → 56KB);四分之三真的带
  透明背景,所以只能转 WebP 不能转 JPEG。`fetch_images.py` 下载后就转,
  老库补转一次用 `scraper/convert_photos_webp.py`(需要 Pillow,见
  `requirements-maintenance.txt`;`scraper/` 不进运行时镜像)
- **URL 带内容哈希**:`server/players.py` 的 `_img()` 给每个图片地址加
  `?v=<内容哈希>`,配 `Cache-Control: immutable` 永久缓存。哈希按
  (大小, mtime) 缓存但取自内容,所以重新部署把时间戳刷了也不会让全站
  图片缓存失效——只有图真的换了 URL 才变。裸地址(不带 `?v=`)只给一天,
  免得换了同名图片的人被钉死在旧版本
- `.webp` 必须在 `server/main.py` 显式 `mimetypes.add_type`:slim 镜像
  没有 `/etc/mime.types`,Python 自带映射到 3.12 都还不认它

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
# (也可以不手编 JSON,直接在管理页「HLTV 审核」标签里表单填写)

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

### 管理页面(/admin)

在 `.env` 设置 `ADMIN_TOKEN` 后才存在(未配置时 `/admin` 与
`/api/admin/*` 一律 404,线上默认关闭);页面首次进入输入口令,
之后所有管理接口靠 `X-Admin-Token` 头校验:

```ini
ADMIN_TOKEN=换成随机长口令
```

浏览器打开 `http://127.0.0.1:8620/admin`,五个标签页:

- **反馈收件箱**:玩家纠错(`feedback.jsonl`)按选手分组展示,一键跳到
  对应选手编辑;可标记已处理/重开并留备注。处理状态存在同目录的
  `*.state.json`(按行内容哈希定位),原始 JSONL 永远只追加、不改写
- **选手编辑**:搜索定位(ID/真实姓名,变音符号折叠)后,对照
  「爬取值 / 生效值」编辑 override:战队、状态、位置、选手期位置、
  生日,`reason` 必填。只写 `data/manual/player_overrides.json`(人工修正层),
  从不改动生成物 `players.json`,scraper 重跑不丢;保存后自动热重载,
  进行中的对局不受影响,也不用重启进程
- **新增选手**(选手编辑页的「＋ 新增选手」):手工加人,用于彩蛋选手或
  上游查不到的人。写 `data/manual/players_manual.json`,加载时并入选手库
  ——**不能直接写 `players.json`**,那是生成物,下一次整库重建会把人冲掉
  (MachineWJQ 就这么丢过一次,见 `52f0b5f`)。进谜底池需要 ID + 国籍 +
  生日 + 位置四项齐全,缺任意一项只能被搜到、不会被抽中
- **头像上传**(编辑器底部):≤2MB 的 JPEG/PNG/WebP,存进
  `data/manual/img/` 并记在 `images_manual.json`,优先级高于爬取的图,
  对人工新增和爬取来的选手都生效。服务端只校验魔数和体积(运行时镜像
  没有 Pillow),不缩放,建议仍上传 600px 源图
- **数据体检**:缺生日/缺位置/缺照片/缺国籍/年龄异常/非谜底池/
  同队多指挥(现役阵容 ≥2 个 IGL,交接指挥后上游残留旧标签的典型症状)/
  现役阵容无指挥(≥4 人首发一个 IGL 都没有,上游漏标指挥的典型症状)/
  失效的 override(条目以 Liquipedia page 名为键,上游改页名后会静默失效,
  人工结论悄悄回退,没有任何报错)九类清单,主动发现问题而不是等玩家反馈,
  点选手直达编辑器。
  两项指挥检查按队分组展示整套阵容——指挥是谁只能人工判断,
  列全员才好挑;不做「无主教练」检查,上游教练覆盖率太低(约 2/3
  的现役队都查不到主教练),报出来只是噪音
- **数据更新**:一键触发「完整重建」(全量,约 3 分钟)或「快速刷新」
  (只更新战队/状态/位置,约 1 分钟),子进程写入
  `data/players.staging.json` 并实时看日志,不碰正式库;跑完展示与
  现库的逐字段 diff(新增/移除/转会等变动),人工过目后「发布」——
  自动备份 `players.json.bak`、替换正式库并热重载。staging 人数比现库
  骤降 20% 以上时(上游页面异常的典型症状)拒绝发布,需二次确认。
  「补齐图片」按钮增量抓新选手照片/队标,完成后自动重载
- **HLTV 审核**:把 `role_review.json` 表单化——逐条查看证据
  (HLTV 主页链接、近三月地图数、Sniping 百分比、IGL 新闻)后填
  decision,再「预览 apply / 写入 overrides」,复用脚本的保护逻辑
  (已有人工角色默认跳过,替换需显式勾选),写入后自动热重载;
  `collect` 采集本身仍需本机 Chrome 在命令行跑

### 两个权威源:人工层 vs 生成物

容器根文件系统只读,只有两个可写卷。`data/manual/` 是管理页唯一写盘的
地方,也是唯一**以线上为准**的数据:

| | 文件 | 权威方 | 流向 |
|---|---|---|---|
| 人工层 | `data/manual/`(override、人工新增选手、上传的照片) | **线上** | 改完从服务器拉回仓库 |
| 生成物 | `players.json`、`images.json`、`img/` | **本地**(爬虫产物) | 推送 + 重建镜像 |

两边各有唯一权威源,所以正常流程不会互相覆盖。线上改完后拉回:

```bash
rsync -av oracle-arm:/home/ubuntu/docker/cstrikle/data/manual/ data/manual/
git add data/manual && git commit -m "Pull manual layer from prod"
```

`compose.yaml` 里对应两处:`./data/manual:/app/data/manual` 可写卷,
以及 `user: "${APP_UID:-1000}:${APP_GID:-1000}"`——镜像里的进程是
uid 999(app),而卷目录是宿主用户建的,不覆盖运行身份就写不进去。
**宿主 uid 各机不同**(春川那台 `ubuntu` 是 1001,不是常见的 1000),
部署前先看一眼再写进 `.env`:

```bash
stat -c "%u:%g" data/manual        # -> 1001:1001
echo "APP_UID=1001
APP_GID=1001" >> .env
```

对不上时的表现是写入报 `Permission denied`(而不是只读卷的
`Read-only file system`),管理页会把这个错误原样显示出来。

**「数据更新」标签在生产环境不可用**:Dockerfile 不 COPY `scraper/`
(镜像不带爬虫和它的依赖),三个抓取任务会直接报「启动失败」。全库刷新
始终在本地跑,过 staging 发布后连同镜像一起部署。

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
data/manual/              人工层(可写卷,线上为准):player_overrides.json
                          人工修正 / players_manual.json 人工新增选手 /
                          images_manual.json + img/ 后台上传的照片
server/players.py         选手库加载/筛选/名字解析
server/game.py            反馈比对 + 单人对局
server/rooms.py           对战房间 + WebSocket + 整局限时 + AI 调度
server/ai_player.py       LLM agent(native/text 双协议 + 全程转录)
server/main.py            FastAPI 入口
server/admin.py           管理页接口(反馈收件箱/override 编辑/新增选手/
                          头像上传/体检/热重载)
server/regions.py         国籍 -> 赛区(server 与 scraper 共用)
static/                   前端(原生 JS 单页,无构建;admin.* 为管理页;
                          style2.css 为「新版 UI」转播风皮肤,页头按钮切换,
                          偏好存 localStorage,旧版样式不受影响)
```
