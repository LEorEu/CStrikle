# Project Memory

## 2026-07-18 — 游戏性四连:外链、纠错反馈、随机匹配、年度 Top20

- Request:
  - Xyp9x 按"助教=刚转岗"口径改回 Rifler/自由身。
  - 结算弹窗给谜底选手加 HLTV / Liquipedia 外链。
  - 加"信息有误"玩家纠错反馈按钮,靠玩家众包修数据。
  - 参考 shnlfriberg.online/multi 加随机匹配。
  - 新增 HLTV 历年年度 Top20 竞猜模式(人少、新手友好)。
- Changes:
  - `player_overrides.json`:Xyp9x → Rifler + 自由身(与 Attacker/NBK- 同类)。
  - 谜底卡(所有模式共用 answerCard)加 Liquipedia 直链(page 构造)与 HLTV 链接(hltv_player_map 有 ID 用直链,否则站内搜索);`full()` 新增 `hltv_url`。
  - `POST /api/feedback`:按 IP 滑动窗口限流(默认 5 次/600 秒,FEEDBACK_RATE_* 可调),JSONL 写 `FEEDBACK_PATH`(默认 data/feedback.jsonl,已 gitignore;只读容器需指到可写卷)+ 应用日志双写;前端 fb-modal 小弹窗,记录选手 page 与场景 context。
  - 随机匹配:`/api/match/join|poll|cancel` 单等待位 + 轮询保活(15 秒 TTL)+ 结果 5 分钟过期;固定 medium + 120 秒;同名自动加"2";大厅第三面板,离开大厅自动退队。原 AI 房限流器重构为通用 `_consume_quota`。
  - Top20 难度:`data/hltv_top20.json` 快照源自 Liquipedia `HLTV/Top_20_Players` 汇总页(浏览器提取,2012 无榜单);2013–2025 共 13 年全部 20/20 匹配本地库,2010/2011 因缺 9 名 1.6 老将(trace/Gux/fRoD 等)存入 excluded_years 待补。按用户后续决定,不做年份选择:历年上榜合并去重为 99 人全明星池(NiKo 10 次上榜最多),作为标准难度档 `top20` 接入 difficulty_pool;meta 的 pool_sizes 含 top20。
  - UI 修整(用户反馈):难度按钮改短标签(简单/常规/困难/Top20/自定义)避免换行;每档难度下方动态说明文案(含候选数);难度行加「?」点击展开内嵌规则说明块(教练判定/混合位置黄色/自由身/中国国籍统一,内嵌块避开 panel clip-path 裁剪);对战大厅三处昵称输入合并为顶部一处 `lobby-name`。
- Verification:
  - 37 项测试全过(新增 7 项 API 测试:top20 池、feedback 落盘/校验、匹配配对/取消/同名)。
  - 浏览器端到端:Top20 2025 局(谜底 molodoy)结算卡外链正确、反馈弹窗提交成功且 JSONL 落盘;双标签页随机匹配互相配对进房、对手色块同步、2 分钟倒计时生效、取消/退队正常。
  - compileall、node --check、git diff --check 通过。
- Deployment (2026-07-18):
  - 提交 `8bbe76b` 并推送 origin/main;git archive 打包上传春川 `/home/ubuntu/docker/cstrikle`。
  - 部署前修复:`cstrikle.feedback` logger 显式挂 stderr handler(root logger 无 handler 时 INFO 会被静默丢弃);compose 加 `./feedback:/data/feedback` 可写卷(宿主目录 1777),服务器 `.env` 追加 `FEEDBACK_PATH=/data/feedback/feedback.jsonl`;`.dockerignore`/`.gitignore` 排除反馈文件。
  - 生产验证:容器 healthy;公网 meta `pool_sizes` 含 top20=99;前端新资源就位;真实反馈 POST 同时落宿主卷 JSONL 和 docker logs;匹配 join/poll/cancel 公网可用(注意 Windows Git Bash 里 curl 发中文 JSON 会因 GBK 编码 400,非服务端问题)。
- Follow-up (2026-07-18, `d824c1e` 已部署):
  - 修自定义档窄面板排版(tag 整词不换行、筛选行独立对齐、自定义不显示说明行)。
  - Top20 移到难度段第一位(真正的新手档);随机匹配加难度选择(Top20/简单/常规/困难),服务端改为按难度分队列,结构上杜绝跨难度配对;生产实测 top20 与 medium 各自排队、同难度即配。
  - 架构确认(用户问答):匹配永远新建房间,不会进入手动房;房间无硬上限(内存字典,6h 清理,4 位码 168 万空间);每房间独立谜底/设置/座位/计时;每个 AI 房独立 AIPlayer 实例(私有历史/缓存),仅共享上游账号池,无串台可能。
- Next steps:
  - 待选后续:随机匹配 BO3 赛制、2010/2011 老将补库、反馈后台查看工具(反馈文件在服务器 `feedback/feedback.jsonl`)。

## Current session

- Request: inspect the project’s AI/search configuration and determine how to use a model provider’s native search capability, especially when routing `grok-4.5` through CPA on the Chuncheon ARM server.
- Findings:
  - `server/ai_player.py` exposes an application function named `web_search`; when invoked, the server runs `ddgs` locally and sends five result snippets back to the model.
  - The active `.env` points to `https://cliproxy.estia.moe/v1`, model `grok-4.5`, with `AI_SEARCH_ENABLED=1` and `AI_TOOLS_MODE=auto`.
  - Chuncheon ARM CPA is CLIProxyAPI v7.2.80. Its active `config.yaml` globally appends `{"type":"web_search"}` to `grok-4.5` requests through `payload.override-raw`.
  - CPA’s upstream trace showed the project’s function `web_search` plus Grok-native `web_search` and `x_search` in the same request.
  - A live mixed-tools test returned HTTP 400: `Duplicate tool names: web_search`.
  - A control request that omitted the application `web_search` but retained `submit_guess` succeeded; Grok used native search and returned a `submit_guess` function call.
- Recommendation:
  - Immediate, configuration-only fix for the current CPA route: set `AI_SEARCH_ENABLED=0`. This removes the local DDGS function while CPA continues to inject Grok-native search.
  - Keep `AI_TOOLS_MODE=native` or `auto`; `say` and `submit_guess` still require function calling.
  - Longer-term code cleanup: replace the ambiguous boolean with `AI_SEARCH_MODE=app|provider|off`, conditionally adjust the prompt/tool list, and document that provider-native searches are not currently surfaced as the project’s detailed `search` / `search_result` transcript events.
- Changes made: created and updated this project memory only. No application code, local `.env`, or CPA/server configuration was changed.
- Verification:
  - Read the complete AI agent/config path and active non-secret settings.
  - Inspected the live CPA config, container version, upstream request traces, and recent errors.
  - Ran one expected-failure mixed-search request and one successful provider-native-search control request.
- Next step: if requested, implement the three-state search mode and update `.env.example` / README, or apply only the one-line local `.env` fix.

## 2026-07-17 — Chuncheon ARM deployment

- Request:
  - Verify the user’s `AI_SEARCH_ENABLED=0` change.
  - Deploy CStrikle to the Chuncheon ARM server.
  - Publish it as `https://cs2.estia.moe` through the existing Caddy stack.
  - Check whether AI requests or credentials are exposed.
- Local changes:
  - Added `.dockerignore`; it excludes `.env`, `.git`, `.venv`, caches, logs, scraper sources, memory, and root PNG files from the image context.
  - Added a multi-architecture `Dockerfile` based on `python:3.12-slim`; the app runs as a non-root user and has a `/api/meta` health check.
  - Added `compose.yaml`; the container is read-only, uses a temporary `/tmp`, has `no-new-privileges`, exposes no host port, and joins the existing external `rag-stack_rag-net`.
- Server changes:
  - Deployed source and runtime `.env` to `/home/ubuntu/docker/cstrikle`.
  - Built and started container `cstrikle`; it is healthy and reachable only as `cstrikle:8620` on the internal Docker network.
  - Created a grey-cloud Cloudflare A record `cs2.estia.moe -> 134.185.114.78`.
  - Backed up and updated `/home/ubuntu/docker/rag-stack/Caddyfile` with a `cs2.estia.moe` reverse proxy to `cstrikle:8620`.
  - Validated the Caddyfile and restarted `rag-caddy` because its admin endpoint is disabled.
  - Let’s Encrypt DNS-01 issuance succeeded for `cs2.estia.moe`.
- Verification:
  - Local Python compile check passed.
  - Remote `docker compose config -q` and ARM64 image build passed.
  - `cstrikle` and `rag-caddy` are running; `cstrikle` reports healthy.
  - Public `/`, `/static/app.js`, and `/api/meta` return HTTP 200 over HTTPS.
  - Public `/.env` and `/Dockerfile` return 404.
  - Runtime config reports `AI_MODEL=grok-4.5`, `AI_SEARCH_ENABLED=0`, `AI_TOOLS_MODE=auto`, and `CSTRIKLE_DEBUG=0`.
  - Server `.env` mode is `600`; `/app/.env` is absent from the container image; temporary archives containing `.env` were removed locally and remotely.
  - The TLS certificate subject is `cs2.estia.moe` and is issued by Let’s Encrypt.
- Security assessment:
  - Browser code calls only same-origin CStrikle REST/WebSocket endpoints. CPA requests and `AI_API_KEY` stay server-side and are not exposed to browser developer tools.
  - The public `POST /api/room` endpoint currently allows anonymous `vs_ai=true` rooms without rate limiting or authentication. Attackers can consume the CPA/Grok account pool even though they cannot see the key.
  - The post-game transcript endpoint requires only an existing four-character room code, not the seat token. It can expose AI reasoning for a finished game.
  - Public scanners began probing the new hostname shortly after DNS publication; sensitive paths correctly returned 404.
- Next steps:
  - Recommended before promoting the site broadly: add an AI-room IP rate limit or access code, and require a room seat token for transcript access.
  - No end-to-end public AI match was started during deployment to avoid consuming multiple model turns; provider-native search plus `submit_guess` had already been validated against the same CPA/model route earlier in the session.

## 2026-07-17 — Public AI safeguards and Git publication

- Request:
  - Add the previously recommended public AI safeguards.
  - Publish the project to the new private repository `https://github.com/LEorEu/CStrikle.git`.
- Security changes:
  - Added an in-memory sliding-window limiter for AI room creation only. The default is three AI rooms per real client IP per 600 seconds; normal human-vs-human rooms are unaffected.
  - Limit settings are configurable through `AI_ROOM_RATE_LIMIT` and `AI_ROOM_RATE_WINDOW_SECONDS`.
  - A rejected request returns HTTP 429 and a calculated `Retry-After` header.
  - The post-game transcript endpoint now requires a valid human seat token through the `X-Room-Token` request header.
  - The frontend automatically sends the room token in the header, avoiding token leakage through URL query strings and access logs.
- Documentation and repository hygiene:
  - Updated `.env.example` and README with rate-limit settings, native-provider search guidance, security behavior, and Docker deployment instructions.
  - Expanded `.gitignore` to exclude `.env`, bytecode, logs, root-level attached PNGs, and deployment archives while retaining game assets under `data/img`.
  - Initialized an independent Git repository at `D:\TTS\cstrikle` on branch `main` and configured `origin` to the requested private GitHub repository.
- Deployment:
  - Rebuilt and replaced the `cstrikle` container on Chuncheon ARM without changing Caddy or DNS.
  - The replacement container is healthy and remains internal-only on `rag-stack_rag-net`.
- Verification:
  - Python compile and JavaScript syntax checks passed.
  - Direct limiter tests confirmed the third request is rejected when configured for a two-request test limit, with the correct `Retry-After`, and that quota expires correctly.
  - FastAPI tests confirmed transcript requests without a token are rejected before game-state disclosure, while a valid token proceeds to the expected “game not over” response.
  - Public verification on `https://cs2.estia.moe` confirmed the updated frontend sends `X-Room-Token`.
  - The live container reports `AI_ROOM_RATE_LIMIT=3` and `AI_ROOM_RATE_WINDOW_SECONDS=600` via application defaults.
  - A public non-AI room test returned 403 without a token and the expected game-state 403 with its valid token; no model request was triggered.
- Git publication result:
  - Final pre-commit audit covered 813 files / approximately 41.5 MB; 789 files are localized game image assets.
  - Hard-coded secret scan found no matches; `.env`, logs, root attachment PNGs, and deployment archives were not tracked.
  - The remote repository was confirmed empty before publication.
  - Initial commit `afef9ee` (`Initial CStrikle release`) was pushed successfully to `origin/main`, and the local `main` branch now tracks it.
- Next steps:
  - No required deployment or publication work remains. A future hardening option is a global concurrent-AI-room cap if public traffic grows beyond what per-IP limiting handles.

## 2026-07-17 — Shorter matches, stage background, and Grok latency

- Request:
  - Replace the 3/5/10-minute versus limits with 1/2/3 minutes because a match has only eight guesses.
  - Use the supplied CS character image as the page background instead of leaving the UI visually empty.
  - Diagnose why CPA-routed `grok-4.5` feels much slower than `gpt-5.5`, then improve it.
- Latency diagnosis:
  - A real game turn in CPA logs made three sequential model requests taking 57.085, 58.835, and 26.929 seconds. The next request failed after 4.927 seconds.
  - The project then added a separate 20–30-second “normal” delay after every AI guess, so model latency and artificial pacing stacked.
  - CPA globally injects Grok-native `web_search`/`x_search`, enlarging Grok's request context. A minimal controlled request was still fast (`grok-4.5` 3.054 seconds versus `gpt-5.5` 3.712 seconds), showing the base route/model was not the main cause.
  - The real prompt could return only `say` without `submit_guess`, causing the app agent loop to call the model repeatedly.
  - The failed CPA request retried three different xAI accounts before returning `context canceled`; unhealthy account retries remain a source of tail-latency variance.
- Changes:
  - Versus time options are now unlimited or 1/2/3 minutes (60/120/180 seconds).
  - Moved the supplied image to `static/cs2-bg.png`, allowed it through `.dockerignore`, and integrated it as a fixed stage background.
  - Added central dark overlays, translucent/blurred HUD cards and panels, and a mobile-specific crop so the image adds atmosphere without reducing text readability.
  - Reduced AI pacing presets from 8/20/40 seconds to 1/3/6 seconds, initial AI wait from 3 to 1.5 seconds, and error retry wait from 10 to 3 seconds.
  - Added optional `AI_REASONING_EFFORT`; production uses `low`.
  - Reduced the default and production `AI_MAX_STEPS` from 10 to 4.
  - Tightened the system prompt: no first-round search, at most one search per round, and `say` plus `submit_guess` should be sent together.
  - If the first native-tool response does not produce a valid guess, later steps force the `submit_guess` tool, preventing repeated chat/search-only calls.
  - Added per-model-call elapsed-time logging for future diagnosis.
  - No global CPA configuration or retry policy was changed because those settings affect other CPA clients.
- Deployment and verification:
  - Python compile, JavaScript syntax, and `git diff --check` passed.
  - Rebuilt and redeployed the container at `/home/ubuntu/docker/cstrikle`; it is healthy.
  - Public `https://cs2.estia.moe` loaded the background with HTTP 200 and showed the new 1/2/3-minute options.
  - Desktop and 390px mobile screenshots were visually inspected; the CS2 HUD remains readable and responsive.
  - The live runtime reports `AI_MAX_STEPS=4`, `AI_REASONING_EFFORT=low`, and speed presets `1/3/6`.
  - One controlled real Grok game turn completed in 17.53 seconds and returned `reasoning + say + guess` in one response, successfully selecting s1mple. This removes the previous three-request runaway and the 20–30-second artificial delay, though CPA/Grok upstream latency can still vary.
- Next steps:
  - Observe the new timing logs during normal play. If occasional long tails remain, clean up failing xAI accounts or reduce `request-retry` in a route-specific CPA configuration rather than changing the global policy.
  - If consistently lower latency matters more than Grok-native search, compare or switch this app alone to `gpt-5.5`; no model switch was made in this session.

## 2026-07-17 — Live Grok latency incident diagnosis

- Request: inspect the live server while the user was playing because AI guesses were still taking far too long.
- Live evidence:
  - Room `GO4B` produced single application-level calls of 56.43 seconds and 79.76 seconds for turns 1 and 2.
  - Turn 3 took 147.27 seconds in application logs: the first CPA request failed at exactly 120 seconds, then the OpenAI SDK silently retried and the replacement CPA request succeeded after another 26.77 seconds.
  - The application’s `AsyncOpenAI` client was confirmed to use the SDK defaults `max_retries=2` and `timeout=120`.
  - CPA was confirmed to use `request-retry: 3`. Several request IDs showed two or three xAI executor attempts, so SDK retries and CPA account retries are nested.
  - CPA transforms the app’s two functions (`say`, `submit_guess`) into a Grok upstream request that additionally contains globally injected `web_search` and `x_search`, even though app-local search is disabled.
  - A new one-minute room `PILF` started an AI request that produced no action for 58 seconds. The match timer then canceled the AI task, CPA returned `context canceled`, and the transcript was empty.
  - Leaving the unlimited `GO4B` room did not stop its AI task. It continued through at least turn 6 and kept one CPA connection occupied because WebSocket disconnect only clears `seat.ws`; abandoned-room AI tasks are not canceled until the match finishes, or a later room creation triggers cleanup after the room is over six hours old.
- Conclusion:
  - Current latency is upstream Grok/native-search latency amplified by two retry layers, not the reduced 1–4.5-second game pacing delay.
  - Short 1/2/3-minute matches are incompatible with 50–80-second native-search turns unless calls are bounded and search is restricted or removed for this app.
- No changes made during diagnosis: no container restart, CPA edit, or application deployment was performed to avoid interrupting a live game.
- Recommended fix:
  - Set the app SDK to `max_retries=0` with a match-appropriate timeout.
  - Prevent or tightly gate provider-native search for short matches; force a direct `submit_guess` when fast play is required.
  - Cancel/pause AI tasks when the human disconnects, preferably with a short reconnect grace period.
  - Keep any CPA retry reduction route-specific rather than changing its global policy for other clients.

## 2026-07-17 — Local search and dedicated AI strategy assessment

- Request: assess whether disabling CPA’s globally injected Grok search and re-enabling the project’s own search would be faster, and whether the AI needs a purpose-built reasoning prompt.
- Search benchmark on the live Chuncheon CStrikle container:
  - `ZywOo CS2 age team Major`: 5.88 seconds, five results.
  - `m0NESY CS2 nationality role`: 1.29 seconds, five results.
  - `donk Counter-Strike majors`: 2.32 seconds, five results.
- Assessment:
  - Project-local DDGS is substantially faster than the observed 55–80-second Grok-native-search turns.
  - Local search still requires a model tool-call round, the DDGS request, and a follow-up model round, so it should be cached and limited to one search only when local data is insufficient.
  - Removing the CPA override globally would also remove native search from unrelated Grok clients. A dedicated no-native-search CPA model/route for CStrikle is safer if other clients depend on the current behavior.
  - Prompt improvements alone are insufficient: the model currently receives only an approximate pool description and past feedback, not the actual locally valid candidate set.
  - The strongest design is a deterministic local solver that filters the same `PlayerDB` pool using the game’s exact `compare()` semantics, ranks guesses by information gain, and supplies a shortlist to the model. The model then chooses among valid candidates, explains briefly, and handles personality/chat.
  - Web search should be a fallback for missing or uncertain metadata, not the main solver. The local game database must remain authoritative because current web facts can differ from the dataset used to score the match.
- No runtime or CPA changes were made during this assessment.

## 2026-07-17 — CPA alias, reasoning effort, and optimal solver design

- Request:
  - Verify whether CPA can expose a separate CStrikle-specific Grok model route.
  - Clarify whether `AI_REASONING_EFFORT=low` affects every model and whether it should remain low after native search is removed.
  - Derive an optimal guessing algorithm before writing the AI strategy prompt.
- CPA findings:
  - Current CPA 7.2.80 has no alias configured and globally injects native search only for requested model `grok-4.5`.
  - Official CLIProxyAPI configuration supports `oauth-model-alias` for the `xai` channel, repeated aliases for one upstream model, and `fork: true` to keep both upstream and alias model IDs.
  - Payload rules can target client-visible model IDs. The clean design is to stop injecting search into canonical `grok-4.5`, expose a separate search-enabled alias, and give CStrikle a no-native-search alias; this avoids coupling unrelated clients.
- Reasoning effort:
  - `AI_REASONING_EFFORT` is application-global inside CStrikle, not CPA-global. When non-empty, current code sends it on every CStrikle model request regardless of the configured model.
  - It only has meaningful effect when the selected provider/model supports the parameter. Live Grok traces confirmed CPA translated `low` upstream; unsupported models may ignore or reject it.
  - After native search is removed, `medium` is a reasonable quality-first setting for Grok. It should be benchmarked against `low` on representative game states while keeping retries disabled and a bounded timeout.
- Optimal strategy derivation:
  - Answers are uniformly sampled from the filtered local pool, and guesses may be any player in the full database.
  - Maintain candidate set `C`: a candidate answer remains only if `compare(previous_guess, candidate)` produces exactly the observed state/direction signature for every prior row.
  - For each legal unguessed guess, partition `C` by its possible feedback signatures.
  - Primary early-game metric: minimize expected posterior size `sum(|bucket|^2) / |C|`; use entropy and smallest worst-case bucket as tie-breakers, and prefer a guess inside `C` for its immediate hit probability.
  - When `C` becomes small, use exact dynamic programming to minimize expected remaining guesses or maximize solve probability within the remaining turns rather than relying only on one-step entropy.
  - On the default medium pool of 511 answers, exhaustive scoring found `SENER1` as the best opener: expected posterior 5.75, worst-case bucket 17, entropy 6.951 bits. The best unrestricted guess was already inside the answer pool, so an out-of-pool probe is unnecessary for this default configuration.
  - The server should compute candidate filtering and ranked moves; the model should receive the derived state and strategy, then reason among the top moves, explain briefly, and provide personality. Asking the model to perform hundreds of exact partitions from prose would be unreliable.
- No application, CPA, or production settings were changed during this design discussion.

## 2026-07-17 — Player team/status/role semantic audit

- Request:
  - Investigate retired or non-playing people incorrectly carrying coach/streamer organizations as game teams.
  - Restrict game positions to IGL, AWPer, and Rifler.
  - Reconcile friberg, olofmeister, NEO, and s1mple with BLAST/Liquipedia/current sources.
- Root cause:
  - The scraper copies Liquipedia's current person infobox `team/status/roles` without distinguishing player roster, current employer, occupation, and historical playing role.
  - The runtime exposes coach/analyst as game roles, selects the first raw role after IGL, and treats BLAST identity-list membership or Liquipedia `Active` as an active player.
  - BLAST's public 390-person JSON contains only identity fields and is not an active-player list.
- Evidence and impact:
  - Among 656 local records, 90 have only non-player occupations, 52 of those still have a team, 14 retired people retain a team, and the suspicious-team union is 62 records.
  - 25 records combine AWP and rifle labels, so raw array order cannot determine the primary role.
  - BLAST's original frontend role schema is only AWPer/Rifler; coaches never belong in game role.
- Recommended canonical model:
  - Split `competitive_status`, `player_team`, `affiliation_org`, `occupation`, `weapon_role`, `is_igl`, `game_role`, and `in_blast_original_pool`.
  - `player_team` only accepts current player/substitute/stand-in roster evidence; otherwise game display is Free Agent while retirement remains a separate status.
  - Expose only IGL/AWPer/Rifler; keep coach/streamer/etc. as occupation and use a versioned manual override file for historical/ambiguous cases.
  - Strict examples: friberg Free Agent/Rifler (Johnny Speeds coach affiliation), olofmeister Free Agent/Rifler (FaZe streamer affiliation), NEO Free Agent/Rifler (Astralis coach affiliation), s1mple BC.Game/AWPer.
  - NEO→Astralis in BLAST is an affiliation/legacy compatibility behavior and conflicts with the stated rule that coach teams must not enter game team.
- Verification:
  - Read-only code/data inspection and external cross-checks were completed.
  - No runtime code, generated player data, CPA configuration, Git publication, or production deployment was changed.
- Next steps:
  - After accepting strict roster semantics, implement the schema and override layer, regenerate/validate the database, update solver/runtime consumers, then deploy.

## 2026-07-17 — Player integrity, CPA route, deterministic solver, and deployment

- Request:
  - Keep Coach as a game role, but show a coach's team only when it is in the current HLTV Top 100.
  - Diagnose blank ALEX search results and blank AdreN unlimited-mode answers.
  - Create a dedicated CPA model alias, remove native search for this app, restore DDGS, implement deterministic candidate filtering/information gain/exact small-set solving, write the prompt from that algorithm, compare low/medium on identical states, deploy, and write a standalone report.
- Data root cause and fix:
  - Seven BLAST nickname-only records (ALEX, Zeus, Lucky, ScreaM, fox, AdreN, Sonic) were unresolved Liquipedia stubs with no attributes but `in_blast_pool=true`.
  - PlayerDB now rejects empty stubs, preserves legitimate disambiguated same-nickname profiles, and separates searchable profiles from game-ready answers.
  - Production now has 649 searchable profiles, 607 game-ready answers, and easy/medium/hard pools of 341/484/607 with no incomplete answers.
  - Added the 2026-07-13 HLTV Top 100 snapshot, aliases, and player overrides. Coach/assistant coach remain Coach; non-Top-100 coach teams become Free Agent.
  - Production examples: ALEX→British ALEX, AdreN→Kazakh AdreN/Free Agent/Rifler, friberg→Free Agent/Coach, NEO→Astralis/Coach, s1mple→BC.Game Esports/AWPer.
- AI/CPA:
  - CPA exposes `grok-4.5-cstrikle` via xAI OAuth alias with `fork: true`.
  - Alias resolution still matched the canonical payload rule, initially causing duplicate `web_search` tools. CStrikle now sends `metadata.client=cstrikle`; CPA's canonical search injection has a matching `not-match`.
  - Project search tool is `ddgs_search`, limited to once per turn and cached for 3600 seconds. Production smoke was 2.21 seconds cold and 0.0003 seconds cached.
  - OpenAI SDK retries are disabled; timeout is 35 seconds; agent has at most two steps.
- Solver and prompt:
  - Filters candidates using exact `compare()` feedback signatures.
  - Scores large sets by expected posterior size, worst bucket, entropy, candidate membership, and fame.
  - Uses finite-horizon recursive solve probability for sets of 10 or fewer.
  - The model receives candidate/ranking details and must submit the server-selected move; other guesses are rejected.
  - Model errors/timeouts/429 now immediately return the solver fallback instead of retrying or choosing randomly.
- Benchmark:
  - Same four fixed states, zero searches in all runs.
  - low: 1/4 success, two timeouts, one xAI free-quota 429; successful sample 20.58 seconds.
  - medium: 3/4 success, one timeout; successful mean 32.00 seconds, median 33.22 seconds.
  - All successful model turns followed the solver. Production uses medium with the 35-second cap.
- Verification and deployment:
  - compileall, `git diff --check`, and 14 unit tests passed.
  - CPA alias/model listing and function calling passed.
  - Final production container is healthy and public `/api/meta` reports `grok-4.5-cstrikle`.
  - Standalone report: `REPORT_PLAYER_DATA_AND_AI_SOLVER.md`.
- Remaining risk:
  - Grok/xAI still shows long-tail timeouts and at least one exhausted free account. The deterministic fallback protects game progress, but account-pool health remains an upstream operations concern.

## 2026-07-18 — 中国大陆、香港、澳门、台湾国籍本地化

- Request:
  - 国籍文字分别显示为“中国”“中国香港”“中国澳门”“中国台湾”。
  - 四者在猜测反馈中按同一中国国籍判定为绿色，并统一使用中国国旗。
  - 只修改本地项目，不提交、不推送、不部署。
- Changes:
  - 保留 `players.json` 的上游原始国籍值，新增公开显示名称、游戏国籍判定键和旗帜来源三个派生属性。
  - 中国大陆、香港、澳门、台湾及兼容来源值 `Macao`/`Chinese Taipei` 的国籍判定键统一为 `China`。
  - 搜索列表、完整资料与猜测格显示本地化文字；四者的旗帜统一映射到 `flags/cn.png`。
  - 添加中国香港、中国台湾与中国大陆互猜为绿色且共用中国国旗的回归测试。
- Verification:
  - Python compileall 通过。
  - 全部 16 项单元测试通过。
  - 手工烟测确认 Attacker、Freeman、Marek 分别显示“中国”“中国香港”“中国台湾”，均使用 `/img/flags/cn.png`，港/台对中国大陆的国籍反馈均为绿色。
  - `git diff --check` 通过。
- Next steps:
  - 按用户要求未提交、未推送、未部署；如后续确认，再与工作区其他未提交功能一起处理。

## 2026-07-18 — 角色/战队/状态口径终稿与落地

- Request:
  - 确定角色真值口径（生涯代表角色 vs 当前职务/近期数据）、Coach 收紧标准、混合角色黄色规则，以及退役/未签约/下放状态是否合并。
- 口径终稿（用户已确认）:
  - 角色真值 = 生涯代表角色；现役用当前角色，退役/转岗用选手期角色。
  - Coach 只给"以教练身份被记住"的人：停赛 ≥3 年且持续执教保留 Coach；刚退役转教练组回退选手期角色 + 自由身（AskUserQuestion 确认）。
  - role_set 黄色白名单：{IGL} {AWPer} {Rifler} {Coach} {IGL,AWPer} {AWPer,Rifler}；IGL 剔除步枪标签，IGL vs Rifler 不再黄。
  - 无战队统一"自由身"并互相判绿（AskUserQuestion 确认）；下放在编算原队（nota=PARIVISION）；status 退出对局反馈，只留题库过滤。
- Changes:
  - `server/players.py`：role_set 白名单重写；team_label 统一"自由身"；删除 is_retired_like 与 STAFF_ROLES。
  - `server/game.py`：team_cat 二值化（原"退役"/"未签约"两类灰判改为无队互绿）。
  - `server/ai_player.py` 提示词与 `static/app.js` 文案同步。
  - `data/player_overrides.json` 新增 9 条：刚退役转岗回退 6 人（Attacker/gla1ve/NBK-/AZR/tiziaN/mou）、erkaSt 过时战队修正（2025-08 已离开 FlyQuest，接任者 AZR）、SmithZz=AWPer、Stewie2K=IGL；Maka 无需覆盖（igl 标签天然优先）。
  - 25 名"教练+上榜战队"逐人取证分类（WebSearch；Liquipedia API 并发触发临时限流后改用搜索索引），18 人保留 Coach。
  - 新增 3 项回归测试（白名单组合、自由身合并判绿、刚退役保留选手身份），总测试 30 项。
  - 生成终审文档 `REVIEW_ROLE_TEAM_FINAL.md`，边界案例标注 ⚠（Xyp9x 按规则保留 Coach 但选手记忆极强；mou 停赛 2.75 年贴线回退；erkaSt 角色低置信）。
- Verification:
  - compileall、30 项单元测试、`git diff --check` 全部通过。
  - 抽样验证 gla1ve/NBK-/Attacker/AZR/mou/tiziaN/erkaSt=选手角色+自由身，zhokiNg/NEO/Xyp9x=Coach+战队，Maka/Jame={IGL,AWPer}，SmithZz/s1mple/ZywOo={AWPer,Rifler}，Stewie2K={IGL}，nota=PARIVISION。
  - 答案池 644 人（较上次生产 607 的增量来自本周已合入的 played_role 批量覆盖，非本轮改动）。
- Next steps:
  - 用户过目 REVIEW_ROLE_TEAM_FINAL.md，尤其三个 ⚠ 条目；确认后此事封盘，转向游戏性优化。
  - 未提交、未推送、未部署；生产仍运行旧语义。

## 2026-07-18 — 本地 HLTV 角色同步与人工审核工具

- Request:
  - 增加可在本地运行的 HLTV 同步工具，把 HLTV 选手与项目数据库稳定匹配。
  - 核对 Stewie2K（用户简称 2k）、Maka 的 IGL 证据及 SmithZz 的 AWP/步枪证据。
- Changes:
  - 新增 `scripts/sync_hltv_roles.py`，使用普通可见 Chrome/Playwright 低速访问 HLTV 搜索和选手主页；生产服务与 Docker 依赖不变。
  - 新增昵称+真实姓名严格匹配、同名分差门槛、人工稳定映射、Jake/Jacky 等受控真名别名和 `2k -> Stewie2K` 显式别名。
  - 角色推断分开保存 IGL 与武器角色证据：近期地图足够时才用 Sniping 高/低阈值建议 AWPer/Rifler；退役、无近期地图、混合区和 403 一律人工复核。
  - 缓存位于 `.cache/hltv/`，默认 8 秒限速，连续两次 403 熔断；默认仅生成 `role_review.json`，只有人工填写 `decision` 并执行 `apply --write` 才会写覆盖文件，已有覆盖默认受保护。
  - 新增 `requirements-maintenance.txt`、`data/hltv_player_map.json`、9 项离线测试及 README 使用说明。
- Sample findings:
  - Stewie2K：HLTV 生涯专题有明确 IGL 语境；建议 IGL/high。
  - Maka：HLTV 明确称其兼任 IGL/AWP；真实采集为近三个月 23 maps、Sniping 79/100，主角色建议 IGL，同时记录 AWPer 武器信号。
  - SmithZz：HLTV 历史个人统计为步枪 9464、狙击 5434，属于混合证据；主页采集 403，因此保持人工复核，不自动定性。
  - ZywOo 未预置映射样例通过站内搜索以 0.95 分正确匹配 HLTV ID 11893，验证自动匹配路径；主页 403 后安全降级。
- Verification:
  - Python compileall 通过。
  - 全项目 27 项单元测试通过。
  - `git diff --check` 和两个 CLI 子命令帮助检查通过。
  - `apply` 预览为 0 项更新，`data/player_overrides.json` 未修改。
- Next steps:
  - 后续可按队伍或争议名单分批采集，在 `.cache/hltv/role_review.json` 人工确认 `decision` 后预览并显式写入。
  - 本轮未提交、未推送、未部署；用户侧并行图片/国旗改动保持原样。

## 2026-07-18 — 角色终稿、HLTV 工具发布与春川部署

- Request:
  - 审查用户补充的角色/战队语义改动，将当前代码推送到私有 GitHub，并部署到春川 ARM 的 `cs2.estia.moe`。
  - 盘点项目名/网站标题入口；用户考虑另取中文社区梗名，但尚未拍板。
- Changes and release:
  - 审核并发布无战队统一“自由身”、角色黄色白名单、9 条人工覆盖、HLTV 本地审核工具、终审报告和回归测试。
  - `.gitignore` 排除 `.claude/settings.local.json`、HLTV 缓存及本地规划文件，避免发布本机权限和会话状态。
  - 发布提交 `9e5305e` 已推送到 `origin/main`。
  - 从该提交生成精确 Git 归档，SHA-256 为 `c56faba66dc39cab5862217b69a153070c75d5aecb12950a31d4614633000c81`；春川覆盖前备份旧源码并保留 `.env`。
  - 在 `/home/ubuntu/docker/cstrikle` 重新构建并启动容器；Caddy 已有 `cs2.estia.moe -> cstrikle:8620`，无需修改 DNS/Caddy。
  - 网站展示名暂时保持 `CStrikle — 猜 CS 职业哥`；未来只替换 title/H1/分享文本，不改 localStorage 键、每日题哈希 seed 或 CPA metadata。
- Verification:
  - 本地 30 项 unittest、Python compileall、JavaScript 语法、diff check 和秘密模式扫描通过。
  - 生产容器 healthy、FailingStreak=0，公开首页 GET 200，`/api/meta` 返回 649/644 与 easy/medium/hard=351/502/644。
  - 生产关键映射通过：SmithZz=AWPer+Rifler、Stewie2K=IGL、Maka=IGL+AWPer、gla1ve/Attacker 为选手角色+自由身。
  - 生产 AI 保持 `grok-4.5-cstrikle`、DDGS 开启、2 steps、35 秒、medium。
- Next steps:
  - 后续单独确定中文品牌名和副标题；可考虑保留 CStrikle 作为技术名，使用“弗一把”作为中文展示品牌，避免迁移内部兼容键。

## 2026-07-18 — 队伍别名、双方重赛与 2026 科隆 Major

- Request:
  - 修复 s1mple=`BC.Game Esports`、Senzu=`BC.Game` 导致同队不绿和界面上像两个队伍的问题。
  - 真人对战结束后，“再来一局”必须双方都确认，不能单方点击立即开局。
  - 核对 2026 科隆 Major 数据；Falcons 已夺冠，但 NiKo 仍显示 0 冠。
- Root causes:
  - 战队反馈直接比较原始字符串；全库另有 5 组类似的大小写/泛化后缀别名。
  - `Room.rematch()` 没有准备状态，一次请求就直接清空双方并重置为 playing。
  - 本地已有 IEM Cologne 2026 参赛记录；Liquipedia 当前 Major Player Database 也已列出该届选手，但整届 placement 尚未回填，因此 `majors_won` 无法计入。
- Changes:
  - 队伍反馈复用 `normalize_team_name()`；当前 Top100 队伍统一使用快照规范名，队标查找增加归一化回退。s1mple/Senzu 现在都显示 `BC.Game` 并共用同一队标。
  - `Seat` 新增 `rematch_ready`；真人首人点击只进入等待，第二人确认后才换谜底并开局。AI 对局仍由真人单击立即重赛。
  - websocket 状态公开双方 ready；页面内和结算弹窗两处按钮同步显示“已准备，等待对手”，新局开始时自动关闭结算层。
  - 新增 `data/major_results.json` 与共享覆盖模块；以 HLTV 决赛结果为来源，把 IEM Cologne 2026 的 Falcons 五人（m0NESY、kyousuke、karrigan、TeSeS、NiKo）placement 设为 1。运行时和 `scraper/build_db.py` 都会应用，重建数据库不会丢失。
- Verification:
  - 全部 44 项 unittest 通过；Python compileall、`node --check static/app.js`、`git diff --check` 通过。
  - 烟测确认 BC.Game 同队反馈为 green；NiKo 为 17 次 Major、1 冠；Falcons 五名冠军选手的 2026 科隆 placement 均为 1。
  - 保留用户未跟踪文件 `新建 文本文档.txt`，未触碰。
- Release and deployment:
  - 用户随后明确授权发布；提交 `afeff31`（Fix team aliases, rematch consent, and Cologne result）已推送到 `origin/main`。
  - 从已推送提交生成精确归档，SHA-256=`F864A901042F81CA4B9F0A317E627A4B23F69EE25C95BC166496BC0403F82ABA`；远端哈希一致。
  - 春川覆盖前备份为 `/home/ubuntu/cstrikle-pre-afeff31-20260718-160709.tar.gz`；精确替换源码时保留 `.env`、`feedback/` 和 `deploy.log`。
  - 新镜像构建并 recreate 成功；最终容器 healthy、FailingStreak=0、RestartCount=0，公开首页和 `/api/meta` 均为 200。
  - 生产验收：s1mple/Senzu 均为 `BC.Game`、共用队标且 team=green；NiKo=17 次 Major/1 冠；重赛首人只 ready、第二人确认后才 playing；公网前端已有等待文案。
  - AI 配置保持 `grok-4.5-cstrikle`、项目搜索开启、2 steps、35 秒、medium。
  - 已清理本地/远端上传临时包与远端旧展开目录，保留正式回滚 tar.gz；用户未跟踪文件 `新建 文本文档.txt` 始终未触碰。

## 2026-07-18 — DeepSeek V4 Flash 试跑、FribergCS2 与主播模式

- Request:
  - 用用户临时提供的官方 DeepSeek Key 评估 `deepseek-v4-flash`，估算 5000 局/天、10 天费用，并解释 AI 强度/求解逻辑。
  - 展示品牌改为 `FribergCS2`，副标题保留“猜 CS 职业哥”；猜测输入改为底部浮动长条。
  - 对战设置增加主播模式，遮蔽对手 ID 和聊天内容，并由聊天标题眼睛按钮临时显示。
- AI findings and changes:
  - 临时 Key 只用于单次进程环境，未写入 `.env`、源码、日志或 Git；官方 `/models`、V4 Flash 非思考工具调用均成功。
  - 新增可选 `AI_THINKING_MODE=enabled|disabled`；空值保持现有 Grok 行为，切换 V4 Flash 时建议显式 `disabled`，因为官方默认开启思考且 low/medium 会映射为 high。
  - AI transcript 新增 token usage 事件；`scripts/benchmark_reasoning.py` 支持 thinking、high/max、usage 汇总和 AI 强度，默认 hard 以保证 A/B 落子一致。
  - 非思考四个固定局面为 4.339–9.114 秒、4999 输入/1309 输出；思考模式为 6.363–19.042 秒、4997 输入/2597 输出。两组都一次请求、零搜索并服从本地 solver，思考没有增加胜率。
  - 按官方价格和实测提示规模，非思考 50,000 局在平均 4/6/8 次模型调用时约 ¥299–381 / ¥449–571 / ¥599–762（区间为实测缓存到全未缓存）。
  - AI 强度与模型推理档分离：easy 在严格候选中随机；normal 在信息增益前五随机；hard 使用最佳信息增益，并在小候选集合精确求解。模型只能解释/聊天/调用工具，不能覆盖 solver 指定落子。
- UI changes:
  - title、H1、每日分享文本改为 `FribergCS2`；内部 `cstrikle` localStorage 键和 CPA metadata 保留兼容。
  - 单人和对战输入都移到网格后，改为视口底部的 CS HUD 控制条；候选列表向上展开，桌面与移动端均保留正常滚动。
  - 对战大厅新增持久化主播模式；前端缓存最近聊天以支持重新渲染，默认遮蔽对手 ID、聊天发送者/正文和系统消息中的对手昵称，眼睛按钮只在本机临时还原。
  - AI API Key 与请求仍只在 FastAPI 服务端；浏览器不接触密钥。终局回放需要有效房间 token，且只包含游戏提示/模型事件，不含请求头。
- Verification:
  - 全部 44 项 unittest 通过；Python compileall、`node --check static/app.js`、`git diff --check` 通过。
  - Playwright 桌面、390×844 移动端视觉检查通过；自动断言候选向上、底栏贴近下沿、主播遮蔽和眼睛还原均为 true。
  - 唯一浏览器控制台 404 是未提供 favicon 的默认请求，不影响功能。
- Next steps:
  - 本轮未修改生产 `.env`，未切换线上 Grok、未提交、未推送、未部署。
  - 若用户确认上线，生产建议使用 `AI_BASE_URL=https://api.deepseek.com`、`AI_MODEL=deepseek-v4-flash`、`AI_THINKING_MODE=disabled`；DDGS 是否保留取决于是否需要背景素材，和 AI 胜率无关。

## 2026-07-18 — Muyuan gpt-5.5 兼容性与 localhost UI Mock

- Request:
  - 临时测试 `https://muyuan.do/v1` 的 `gpt-5.5` 速度。
  - 启动本地服务并 mock 对局数据，让用户查看本轮 UI 修改。
- Muyuan result:
  - Key 只进入临时进程环境，未写入 `.env`、源码、日志或 Git；diff 秘密扫描为 0。
  - `/models` 可访问，但 chat completion 在进入模型前返回 403 `channel:client_restricted`。
  - OpenAI Python SDK 被识别为 `AsyncOpenAI/Python 2.45.0`；标准 httpx + `Mozilla/5.0` 同样在约 0.868 秒被拒。
  - 公开站点讨论转述站方策略：当前渠道只允许官方 Codex/Claude Code，Python、curl 与第三方客户端会被拒。CStrikle 是 FastAPI 服务端，不能合规使用该渠道；未伪造官方客户端标识，也无法获得真实模型速度。
- UI mock:
  - `static/app.js` 新增仅 localhost/127.0.0.1/::1 且显式 `?mock=streamer` 才触发的预览。
  - mock 使用 ZywOo/s1mple 两行反馈、对手三行进度、90 秒计时和三条聊天；默认开启主播遮蔽，眼睛按钮可还原。
  - 普通 `/` 首页不受影响；生产域名不会触发 mock。
- Verification:
  - Playwright 断言两行数据、底栏位置、默认遮蔽、眼睛还原和普通首页隔离均通过；视觉截图确认年龄/角色/颜色正常。
  - 45 项 unittest、compileall、JS 语法和 diff check 全部通过。
- Local service:
  - 无窗口 Uvicorn 已持续运行在 `http://127.0.0.1:8765`，PID 32760。
  - `netstat -ano`、普通首页 GET、mock URL GET 和 `/api/meta` 独立复核通过；meta 返回 649 名选手。
  - 非提升权限下 `Get-NetTCPConnection` 一度未显示监听，属于权限假阴性，不是服务被回收。
- Scope:
  - 未修改生产 `.env`，未切线上模型，未提交、未推送、未部署。

## 2026-07-18 — CPA 新 Codex Plus 路由、本地真实 AI 与搜索候选修复

- Request:
  - 让 FribergCS2 后续使用春川 CPA 新增的 Codex Plus 账号，并在本地以真实数据库/真实 AI 正常启动。
  - 用户现场发现底部输入 ID 后候选列表不可见，要求恢复为可用的上拉候选框。
- CPA routing:
  - 新旧 Codex OAuth auth 都启用且无 priority；仅添加账号时 CPA 会在匹配账号间调度，不能保证项目固定使用新账号。
  - 按 CLIProxyAPI 的 per-auth OAuth `model-aliases` 机制，只在新 Codex Plus auth 上增加唯一别名 `gpt-5.5-cstrikle -> gpt-5.5`，旧账号和全局路由未改。
  - 修改前已在 CPA auth 目录生成带日期的备份；CPA 热加载成功，`/v1/models` 可见新别名。
- Real AI verification:
  - 最小强制工具调用约 3.52 秒，正确调用 `submit_guess`，上游响应模型为 `gpt-5.5`。
  - 项目 hard/one_feedback 固定局面约 11.063 秒，0 次 DDGS 搜索、1585 total tokens，严格提交 solver 指定的 s1mple。
  - 本地真实房间日志中连续四次 AI 调用约 5.93/3.87/3.94/3.88 秒；额外测试客户端超时是错误读取 websocket state 结构，并非 AI 请求超时。
- Local service:
  - 本地忽略文件 `.env` 的模型改为 `gpt-5.5-cstrikle`，CPA 地址、DDGS=1、reasoning=medium、tools=auto 保持不变；密钥未输出或写入跟踪文件。
  - 旧 Uvicorn PID 32760 经命令行确认后停止；真实服务以 PID 23480 运行在 `http://127.0.0.1:8765/`。
  - `/api/meta` 为 649 名选手、644 名可出题选手，AI enabled 且模型为新别名；已打开新的可见 Chrome 窗口，不带 mock 参数。
- Search suggestion fix:
  - 根因是 `.guess-dock` 上的 `clip-path` 会裁剪绝对定位到容器上方的 `.suggest`，所以 JS 有数据但视觉上完全不可见。
  - 移除 dock 容器级 `clip-path`，保留原边框、阴影、模糊和阵营色；候选继续使用 `bottom: calc(100% + 5px)` 向上展开。
  - Playwright 使用真实 649 人数据库验证：1449×656 桌面与 390×844 手机视口输入 `s1` 均显示 5 条建议，候选列表完整位于搜索框上方。
- Scope:
  - 本轮没有提交、推送或部署 FribergCS2 项目代码；生产 `cs2.estia.moe` 仍使用之前的线上配置。

## 2026-07-18 — 恢复原版输入框与 AI 决策回放

- Request:
  - 用户否定底部浮动长输入框，要求恢复原版位置与外观。
  - 用户发现 GPT-5.5 回放几乎没有“思考过程”，希望解释 solver 的影响并优化。
- Input layout:
  - 单人和对战输入框都恢复到反馈网格之前，宽度恢复原版上限 460px。
  - 删除 `guess-dock`、sticky、满宽 HUD 标签、上拉候选和满屏 flex；候选重新从输入框下方向下展开。
  - Playwright 真实数据验证：桌面输入框 460×46，移动端 366×46；两端输入 `s1` 均显示 5 条同宽下拉建议。
- AI reasoning diagnosis:
  - `PlayerSolver` 会先完成严格候选过滤、信息增益评分或小集合有限步精确求解，并指定本轮唯一允许提交的落子。
  - GPT-5.5 在该流程中通常直接返回 `say`/`submit_guess` 工具调用，`content` 和 `reasoning_content` 可以为空；没有文本不代表没有执行模型调用。
  - 模型私有思维链既不稳定也不应成为产品功能依赖；游戏强度来自可复现的服务器 solver。
- Explainability changes:
  - solver transcript 新增上一轮/当前候选数、剩余回合、逐步中文解释、选中落子的期望剩余人数/最坏分支/信息熵，以及精确解出率。
  - 实时 `ai_status.detail` 现在分阶段显示“按反馈筛选”“计算信息增益/决策树”“整理公开解说并提交”等安全状态，只给候选数与算法阶段，不泄露候选名或指定落子。
  - UI 将“AI 思考回放”改为“AI 决策回放”，增加决策卡、三项指标、排名折叠和说明文字；模型主动公开的解说、搜索和工具动作继续保留。
  - 桌面和 390×844 移动端视觉通过；移动端三项指标自动单列，弹层内部滚动正常。
- Verification:
  - 真实 `gpt-5.5-cstrikle` 首回合 9.11 秒完成，502 名候选、3 条解释、完整 selected metrics；事件为 solver/usage/say/guess，安全状态未泄露最终落子 Refrezh。
  - 46 项 unittest、compileall、`node --check static/app.js`、`git diff --check` 全部通过；秘密模式扫描 0 命中。
  - 本地服务已重启为 PID 35064，继续运行在 `http://127.0.0.1:8765/`，meta 为 649 名选手和 `gpt-5.5-cstrikle`。
- Scope:
  - 本轮未提交、未推送、未部署；生产站仍未包含这些本地 UI/回放修改。

## 2026-07-18 — FribergCS2 UI、主播模式与 GPT-5.5 决策回放上线

- Request:
  - 用户确认恢复后的输入布局和 AI 决策回放效果，要求推送当前代码并部署到春川 ARM。
- Git release:
  - 发布范围为 `.env.example`、AI 配置/基准/回放后端、品牌与主播模式前端及 AI 单测共 9 个跟踪文件。
  - 暂存前后秘密模式扫描均为 0；本地 `.env` 被 `.gitignore` 排除，API Key 未进入提交或部署归档。
  - 功能提交 `7796a56`（Improve AI decisions, privacy, and UI branding）已推送到 `origin/main`。
  - 从该提交生成精确 Git 归档，SHA-256 为 `cb81f13ecac96e5f3e1360158fedb8b767e879004cd6b182f878579f604c52ec`；服务器上传包哈希一致。
- Production deployment:
  - 部署目录仍为 `/home/ubuntu/docker/cstrikle`，Caddy 与域名无需修改。
  - 部署前完整回滚包为 `/home/ubuntu/cstrikle-pre-7796a56-20260718-183640.tar.gz`，SHA-256 为 `5e639f8e2099f33236c547a0a43fc0558fad4e14736173924e46e489a46d1347`。
  - 使用 staging 解包后保留 `.env`、`feedback/` 和 `deploy.log`，反馈目录与旧版本 `diff -qr` 一致。
  - 仅将生产 `AI_MODEL` 从 `grok-4.5-cstrikle` 切到新账号专属别名 `gpt-5.5-cstrikle`；CPA 地址、项目 DDGS、medium、auto、2 steps 和 35 秒上限保持不变。
  - 新镜像构建并 recreate 成功；临时上传包和旧展开目录已清理，正式回滚 tar 保留。
- Verification:
  - 发布前完整 46 项 unittest、Python compileall、JavaScript 语法、`git diff --check` 和秘密扫描均通过。
  - 生产容器 `healthy`、RestartCount=0、FailingStreak=0；公网 `/api/meta` 返回 649/644 人、AI enabled、模型 `gpt-5.5-cstrikle`。
  - 公网首页命中 `FribergCS2`、主播模式和“AI 决策回放”，本机与服务器两条公网链路均验证成功。
  - 生产真实 AI 烟测房间创建成功，`gpt-5.5-cstrikle` 首次模型调用 4.17 秒完成，无模型错误或 solver 回退。
- Next steps:
  - 观察实际玩家局面的 GPT-5.5 延迟和 token usage；若出现持续慢调用，可按回放中的 usage/solver 事件与 CPA 日志定位，不需要恢复原生搜索。
