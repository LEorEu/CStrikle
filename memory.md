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

## 2026-07-18 — 接入 FribergCS2 Favicon

- Request:
  - 用户新增网站图标并要求接入。
- Changes:
  - 保留用户提供的 `static/favicon.jpg`；图像为 360×360 JPEG、蓝橙底色的白色 CS 人物剪影。
  - 在 `static/index.html` 的 `<head>` 中增加显式 `rel="icon"`、`type="image/jpeg"` 和 `/static/favicon.jpg` 路径。
- Verification:
  - 本地首页返回 200 且包含 favicon 声明。
  - favicon 静态资源返回 200、`Content-Type: image/jpeg`、`Content-Length: 8337`。
  - `git diff --check` 通过。
- Next steps:
  - 用户随后要求部署；生产部署结果见下方记录。

## 2026-07-18 — FribergCS2 Favicon 生产部署

- Request:
  - 将已接入的 favicon 部署到春川 ARM 生产站。
- Deployment:
  - 发布范围仅为 `static/index.html` 与 `static/favicon.jpg`；没有创建 Git 提交或推送。
  - 部署前完整回滚包为 `/home/ubuntu/cstrikle-pre-favicon-20260718-184807.tar.gz`，SHA-256 为 `7634db6047c4591b56405aa68bbc552149543019263d706daf7b207296e7a375`。
  - 上传文件经 SHA-256 校验后写入 `/home/ubuntu/docker/cstrikle/static/`，随后重建并 recreate 容器。
  - 临时上传文件已清理，完整回滚包保留。
- Verification:
  - 生产容器 healthy、RestartCount=0、FailingStreak=0。
  - 公网首页与 favicon 均返回 200，HTML 声明存在；图片 MIME 为 `image/jpeg`、长度 8337 字节。
  - 公网 favicon SHA-256 为 `030d9edec1d532f03a7512998efe0ac01a368f3f494b490fb82ff5cf0119357f`，与本地及服务器源文件一致。
  - 生产 AI 配置保持 `gpt-5.5-cstrikle`、项目搜索开启、reasoning medium。
- Next steps:
  - favicon 当前已上线但尚未进入 Git；下一次从仓库做完整部署前应先提交并推送 `static/favicon.jpg`、`static/index.html` 与本次 `memory.md`。

## 2026-07-18 — 临时增加 MachineWJQ 并部署

- Request:
  - 从 Liquipedia 的 `MachineWJQ` 页面核对资料，临时加入选手数据库并部署生产。
- Source findings:
  - Liquipedia API 页面源：ID `MachineWJQ`，姓名刘亦博 / `Liu Yibo`，中国，出生于 1996-01-11，状态 Active，选手年份 2017–2020，当前角色 Caster，曾效力 Team Zero。
  - 页面主图为 `MachineWJQ at prohouse 2020.jpg`，Liquipedia Commons 原图 600×441 JPEG。
  - HLTV ID 16149，当前无战队；仅 1 张记录地图、Sniping 0/100，因此临时游戏位置定为 Rifler。
- Changes:
  - `data/players.json` 增加完整记录：MachineWJQ / Liu Yibo / China / Asia / 1996-01-11 / 自由身 / Rifler / 0 Major。
  - 保留当前 Caster 原始角色，并用 `game_role=Rifler` 区分解说身份和选手时期位置。
  - 临时设为默认身份池成员，使其进入常规与困难题库，不进入简单或 Top20。
  - `data/images.json` 与 `data/img/players/MachineWJQ.jpg` 增加 Liquipedia 主图映射；`data/hltv_player_map.json` 增加 ID 16149、6657/玩机器别名证据和 HLTV 直链。
- Verification:
  - 本地 PlayerDB/API：650 名可搜索选手、645 名可出题选手；常规 503、困难 645、简单仍 351。
  - 46 项完整 unittest 全部通过；`git diff --check` 通过。
  - 公网实际 hard 对局成功提交 MachineWJQ，反馈为中国、自由身、30 岁、Rifler、0 Major、0 冠；图片返回 200 且 SHA-256 与 Liquipedia 下载文件一致。
- Deployment:
  - 部署前完整回滚包：`/home/ubuntu/cstrikle-pre-machinewjq-20260718-185700.tar.gz`，SHA-256=`446ec21e001b286729697cd7640c0452e31dd518d8c66712d271feec7ae979ba`。
  - 数据增量包 SHA-256=`fb2e78fd3f88c528ba22cdae1a6d0c00c55c85f0f54658b5cd4545a4b1a23377`，上传后哈希与四文件清单均通过。
  - 容器重建后 healthy、RestartCount=0、FailingStreak=0；AI 配置仍为 `gpt-5.5-cstrikle`、项目搜索开启、medium。
  - 临时增量包已从本地和服务器清理，完整回滚包保留。
- Next steps:
  - 本轮按用户要求只部署，尚未提交或推送；favicon 与 MachineWJQ 数据均需在下次完整仓库部署前一起提交，否则会被 Git 版本覆盖。

## 2026-07-19 — 退役与非选手职务的战队字段诊断

- Request:
  - 核查 Kjaerbye、f0rest、Hyper、denis、DiSTURBED 等退役或转职人员为何仍显示 JiJieHao、NiP、Phantom Esports、esports player foundation、HAVU 等战队。
  - 用户确定游戏数据应以 HLTV 为最终标准；本轮只分析，不修改产品数据、不提交、不部署。
- Findings:
  - 本地数据与 Liquipedia 当前顶层字段一致，问题不是单纯的旧快照：Liquipedia 会把 streamer、caster、manager 等当前组织归属继续写入 `team`。
  - HLTV 当前个人页将 Kjaerbye 标为 `No team`，将 Hyper、denis、f0rest 标为 `Retired`，DiSTURBED 为 `No team`；因此这些组织都不应作为游戏战队。
  - Liquipedia 队史已把 Kjaerbye 标为 2024-08-20 起 inactive，但抓取器只保留顶层 infobox，丢弃了 `team_history` 的 inactive 标记。
  - 全库 657 条原始记录中有 14 名 Retired 仍带非空 team；按 Retired/Inactive 和非选手职务归一化，至少 20 条记录需要清空游戏 team。
  - `Player.is_active` 当前把 `in_blast_pool` 当作现役依据，导致部分退役选手进入“仅现役”题库；`in_blast_pool` 实际只代表原始竞猜身份池。
- Decision:
  - HLTV 最终负责游戏面对的当前战队、active/benched/inactive/retired、最新正式比赛与当前阵容身份。
  - Liquipedia 只补真名、生日、国籍、Major 历史和职务说明；主播、解说、经理等组织归属应拆到 `affiliation`，不能写入游戏 `team`。
  - 历史主位置和 IGL/AWPer/Rifler 歧义继续由 HLTV/比赛履历提供证据，`player_overrides.json` 作为人工最终裁决。
  - `Active` 只指当前正式比赛阵容；No team、Benched/Inactive 显示自由身，明确退役才标 Retired。Top100 教练保留战队的既有例外不变。
  - HLTV 同步只在本地维护流程中使用浏览器导出、缓存和审核建议，不让生产游戏实时抓取 HLTV。
- Verification:
  - 已核对本地原始记录、运行时归一化、Liquipedia API/队史及上述 HLTV 个人页；结论在五名样例和 14 条 Retired+team 数据上相互一致。
  - 本轮没有改动业务代码或玩家数据库，因此未运行产品测试。
- Next steps:
  - 若用户授权实施，先修 `is_active` 与 team/status 归一化并补五名回归测试，再扩展本地 HLTV 同步报告，最后批量审核并写入覆盖层。

## 2026-07-19 — HLTV 异常发现与下放/转会状态机

- Request:
  - 设计一套无需逐人复核全部数据库、但能持续发现错误战队和状态的 HLTV 同步规则。
  - 重点处理 PARIVISION 的 nota 下放，以及 BELCHONOKK 下放后加入 TDK 的连续变化。
- Findings:
  - 本地仍把 nota、BELCHONOKK 都标为 PARIVISION Active；HLTV 当前将 nota 标为 `PARIVISION (benched)`，BELCHONOKK 标为 TDK。
  - HLTV PARIVISION 队伍页的 Transfers 已按日期记录两人的 bench 事件及 BELCHONOKK 转入 TDK；TDK 队伍页和个人页也相互印证新队。
  - HLTV `/transfers` 可以作为每日增量入口；Top100 队伍页可以作为每周阵容对账入口；只有差异选手才需要打开个人页。
  - 本地 657 人中 381 人带 team，284 人的 team 属于当前 Top100、分布于 70 支队伍，先扫 Top100 可覆盖大多数高频现役答案。
  - 现有 `sync_hltv_roles.py` 只逐人抓角色，未解析 benched/Retired/No team；稳定 HLTV ID 映射也只有 4 人，需要从阵容和 transfer 链接渐进补齐。
- Decision:
  - 新同步采用“每日 transfer 增量 + 每周 Top100 roster 快照 + 异常个人页复核 + 非 Top100 滚动审计”，不每轮抓 657 个个人页。
  - 拆分 `team`、`affiliation`、`roster_status`；team 只表示 active player roster。
  - bench/inactive 保存原组织到 affiliation，但游戏 team 清空、status=Inactive；若稍后加入新队，以更新的 active roster 证据覆盖旧 bench 事件。
  - 缺页、请求失败或单次未出现绝不自动判离队；自动写入至少要求稳定 HLTV ID 与明确事件/两份成功来源一致。
- Verification:
  - 已用 HLTV 个人页、PARIVISION/TDK 队伍页、transfer feed 和新闻交叉验证 nota/BELCHONOKK 的状态链。
  - 本轮只完成规则设计与审计，没有修改业务代码、数据库、Git 历史或生产环境。
- Next steps:
  - 用户若确认实施，扩展现有同步脚本生成 roster/transfer 差异报告，先以只读模式跑全库，再审核自动应用规则。

## 2026-07-19 — 游戏语义下的自由身与角色重建规则

- Request:
  - 用户澄清游戏 team 只表示当前正式选手首发战队；退役、无队、下放、替补、主教练、助教等都应显示自由身。
  - 只有当前主教练映射 Coach；Xyp9x、Attacker 等助教回退到选手时期位置，gla1ve 当前主教练应从 IGL 改为 Coach。
  - 要求解释 nota/BELCHONOKK 多条当前队史如何处理，以及干净部署/重建如何保证准确。
- Findings:
  - Liquipedia API 当前 revision 明确写出 nota=`PARIVISION|Inactive`；BELCHONOKK 同时有 `PARIVISION|Inactive` 与更新的 `TDK` 正式条目。
  - Xyp9x、Attacker 的当前队史修饰为 Assistant Coach；gla1ve 为 Coach。
  - 现有构建器忽略 team_history，只抓顶层 team/status；运行时又把 coach 与 assistant coach 混为一类。
  - 当前 Xyp9x、Attacker 的正确展示来自人工 override；gla1ve 的人工 IGL override 已过时；nota/BELCHONOKK 没有 override。
  - Dockerfile 直接复制版本化 `data/`，服务启动不会重新抓取上游；干净部署天然使用已审核快照。
- Decision:
  - “自由身”作为游戏标签定义为“没有当前正式选手首发战队”，不表达合同法律状态。
  - 构建器解析所有 Present team_history：Inactive/Benched/staff 条目不产生 team；唯一正式 player 条目产生 team；旧队 inactive + 新队 active 时取新队；未消解的多 active 冲突使构建失败。
  - 当前 Coach → 自由身 + Coach；Assistant Coach 等 staff → 自由身 + 版本化 played_role。
  - `career_status` 与 `roster_active` 分离，Top100 和 `in_blast_pool` 不再决定游戏 team/现役阵容。
  - Liquipedia 是完整重建源，HLTV 作为低频差异审计和冲突最终裁决，不成为部署或运行时依赖。
- Verification:
  - 已核对五名样例的本地原始数据、runtime 输出、override 与 2026-07-19 Liquipedia API revision。
  - 已核对 Dockerfile/compose，确认部署只复制数据快照。
  - 本轮仅规则审计与设计，未改业务代码和玩家数据，未提交或部署。
- Next steps:
  - 若用户确认实施，修改 build_db 的 team_history 解析、runtime coach/active 规则与构建校验，迁移 gla1ve override，并用五个样例做回归测试。

## 2026-07-19 — 实现自由身重建、角色分离与队伍别名回归

- Request:
  - 用户确认规则并要求修改、推送 GitHub、部署春川 ARM。
  - 补充要求排查类似 s1mple/Senzu 的同队不同显示名问题。
- Changes:
  - `scraper/build_db.py` 增加平衡模板提取和 `{{TH}}` 队史解析；Inactive/Benched/Substitute/staff 不产生游戏 team，存在另一条正式队伍时选正式队伍，多个同队记录先去重，无法消解的不同队伍使构建失败。
  - 增加 `--refresh-existing`，只刷新现有记录的 team/status/roles/当前队史证据，保留 Major、MachineWJQ 与其他人工数据。
  - `server/players.py` 将主教练与助教拆开；所有 staff 都显示自由身，只有主教练映射 Coach，助教回退版本化 played_role；`is_active` 改为当前正式选手阵容语义。
  - gla1ve 更新为自由身 + Coach；KrizzeN 根据 HLTV 生涯数据补 `played_role=Rifler`。
  - 650/657 个 Liquipedia 页面成功刷新；7 个不可用裸标题是既有同名空 stub，保留旧数据并继续从 searchable 集合排除。
  - 全库产生 116 条 team 更新，roles/status 无批量变化；runtime 队伍规范键冲突为 0，s1mple/Senzu 均为同一个 `BC.Game` 和同一 Logo。
- Verification:
  - 完整 unittest 54/54 通过；Python compileall、前端 JavaScript 语法、JSON 解析、`git diff --check` 全部通过。
  - 关键结果：nota=自由身/Rifler，BELCHONOKK=TDK/Rifler，Xyp9x/Attacker=自由身/Rifler，gla1ve=自由身/Coach。
  - 可搜索 650、可出题 645、当前正式阵容 276、排除 stub 7；没有 retired/staff 仍带 team。
  - 提交前差异秘密模式扫描为 0。
- Next steps:
  - 提交推送并按完整备份、精确 Git 归档、生产健康与公网关键样例验收流程部署。

## 2026-07-19 — 自由身与队伍归一化生产发布

- Request:
  - 将新的正式阵容/自由身规则、教练角色分离和队伍别名防回归改动推送并部署到春川 ARM。
- Deployment:
  - 功能提交 `8866c951059f365ca8b450e1a479ae1826cfaf5e` 已推送 `origin/main`。
  - 精确 Git 归档 SHA-256=`efa244f8d83e23146adf9914ca88fd0e3468680aa02cbe522def4f1f9225ed24`，服务器接收哈希一致。
  - 部署前完整回滚包为 `/home/ubuntu/cstrikle-pre-8866c95-20260719-192239.tar.gz`，SHA-256=`6fa9cc813a129e8c906e08032d81f86b60de9e804e1606682215c3b493d3d231`。
  - staging 目录原子切换后重建容器；新镜像 `sha256:efbeac0f6629ce100dd193f109d882f4be0089a98b35d69e9216012874874fff`。
  - `.env`、`feedback/` 与 `deploy.log` 均保留；上传归档和旧 staging 目录已清理。
- Verification:
  - 生产容器 `running/healthy`、RestartCount=0，近 10 分钟日志中 traceback/exception/error 计数为 0。
  - 容器内共 650 名可搜索、645 名可出题、276 名当前正式阵容选手。
  - nota=自由身/Rifler，BELCHONOKK=TDK/Rifler，gla1ve=自由身/Coach，Xyp9x/Attacker=自由身/Rifler。
  - s1mple 与 Senzu 均规范为 `BC.Game`，共用 `/img/teams/BC_Game_am.png`，不存在同队双身份。
  - 公网首页返回 200，标题为 `FribergCS2 — 猜 CS 职业哥`；`/api/meta` 返回新数据库时间 `2026-07-19T19:11:20+08:00`、650/645/7 的搜索/答案/stub 统计。
  - 本轮未改 AI 配置；部署前备份、部署后 `.env` 和容器三处 `AI_MODEL` 均为 `grok-4.5`。
- Next steps:
  - 无；若后续接入 HLTV 阵容同步，继续让 Liquipedia 负责完整重建、HLTV 负责低频差异审核与人工覆盖建议。

## 2026-07-19 — 纠正主教练与其他 staff 的战队边界

- Request:
  - 用户指出 NEO、gla1ve、zhokiNg 等现任主教练被错误显示为自由身，并明确只有助教和其他 staff 应清空战队。
- Changes:
  - 构建器将当前队史拆为 Head Coach、Assistant Coach、Inactive/Benched 和其他 staff；明确 Coach/Head Coach 保留当前战队，其他非选手职务不产生游戏 team。
  - 运行时读取版本化 `team_resolution` 判断主教练，不再只依赖可能失真的顶层 roles；主教练保留战队和 Coach，但 `is_active` 仍为 false。
  - 修复 gla1ve、mou、AZR 的旧空 team/历史位置覆盖；当前分别为 100 Thieves/Coach、HOTU/Coach、FlyQuest/Coach。
  - 补齐 broadcast analyst staff 枚举，避免 natu 等组织职务污染原始游戏 team。
  - S0tF1k 当前是助教且顶层只剩 coach；根据 HLTV 1470 张地图、Sniping 7/100 的生涯统计补 `played_role=Rifler`。
  - 重新从 Liquipedia 刷新 650/657 个页面；7 个既有不可用裸标题保持不变。
- Verification:
  - NEO=Astralis/Coach、gla1ve=100 Thieves/Coach、zhokiNg=TYLOO/Coach、mou=HOTU/Coach、AZR=FlyQuest/Coach、jR=Inner Circle/Coach，全部不算正式现役选手。
  - friberg=自由身/Rifler，Xyp9x/Attacker/S0tF1k=自由身/Rifler，kaze=自由身/AWPer，natu=自由身/IGL。
  - 全库 30 名明确当前主教练保留战队；非主教练 staff 带 team 为 0；650 名可搜索、645 名可出题、276 名正式阵容选手，位置未知数为 0。
  - 完整 unittest 55/55、Python compileall、JavaScript 语法、JSON 解析和 `git diff --check` 全部通过。
- Next steps:
  - 无；该修正已推送并部署。
- Deployment:
  - 功能提交 `d07a876c252c277fc31795fbb269242183c29c14` 已推送 `origin/main`。
  - 精确 Git 归档大小 44,632,805 字节，SHA-256=`5ad297c6b0fc4cc01a3ab5ea05fe8dbb3e14fb894ccb379537c50dfa8cc4fde9`。
  - 部署前完整回滚包为 `/home/ubuntu/cstrikle-pre-d07a876-20260719-195303.tar.gz`，SHA-256=`a3f9ad7558d8b277277b63f3a792b51ada7f65b570e5ba25e028a0844cda4c04`。
  - 新镜像 `sha256:0f5eb3fcb5e6e7e1f3b828c7239f6e1eb6c1544e5e031b4db5a0752314a7f302`；容器 running/healthy、RestartCount=0，近 10 分钟错误日志为 0。
  - 公网首页 200，`/api/meta` 为 650 名可搜索、645 名可出题、7 个排除 stub，数据时间 `2026-07-19T19:45:48+08:00`。
  - 生产容器核验 30 名明确主教练带队、276 名正式阵容选手，非主教练 staff 带 team 为 0；关键十二名结果与本地一致。
  - `.env`、feedback 和 deploy.log 保留；AI 模型部署前后均为 `grok-4.5`；上传归档和旧展开目录已清理。

## 2026-07-19 — S0tF1k / hally 当前职务复核

- Request:
  - 用户怀疑 S0tF1k 已取代 hally 成为 Team Spirit 主教练，要求按 HLTV 复核。
- Findings:
  - 2026-04-02 起 hally 因健康问题暂时离岗，S0tF1k 以 temporary coach 身份带队参加 IEM Rio 和 PGL Astana，因此曾实际代理主教练。
  - 2026-06-04 Spirit 重组教练组后，HLTV 明确 hally 回归 head coach；S0tF1k 与其协作，负责细节、战术、机制和道具。
  - 2026-06-15 hally 再次因健康问题缺席 Cologne Major，但 HLTV 仍称其为 head coach；两人远程共同工作。
  - 2026-07-19 当日抓取的 HLTV Spirit 队伍页仍列 hally 为 Coach，当前没有更晚的 HLTV 证据表明 S0tF1k 已正式取代。
- Decision:
  - 保持当前游戏映射：hally=Spirit/Coach；S0tF1k=非主教练 staff，因此自由身并回退历史 Rifler。
  - 本轮不修改业务代码、数据快照、Git 历史或生产环境。

## 2026-07-19 — 主页、头像与规则说明优化

- Request:
  - 用户希望主页减少单调和空旷感，放大候选下拉及选择/猜测后的选手头像，并补全问号规则中的选手、战队、国籍和赛区判定。
- Changes:
  - 首页重构为“赛事战术简报”结构：新增线索 Hero、反馈颜色图例、实时数据库状态板，以及有编号和行动提示的三种模式入口；保留原背景图和蓝橙 CS/HUD 视觉体系。
  - 下拉候选头像由 30px 提升至桌面 52px/移动端 48px，并分层展示昵称、真名和队伍；猜测记录头像由 38px 提升至桌面 48px/移动端 44px，行高提升至 68px/64px；答案卡头像提升至 116px/100px。
  - 问号改为可访问按钮，规则说明拆成位置、混合位置、战队/自由身、国籍比较、八赛区与数据来源；明确主教练保留战队，助教/其他 staff、Inactive、Benched、替补等显示自由身，新队优先于旧 inactive 队。
  - 明确欧洲含土耳其、独联体含哈萨克斯坦、中东非洲含以色列，并列出北美、南美、亚洲、大洋洲和其他；中国、中国香港、中国澳门、中国台湾统一中国国旗且互判绿色。
  - 自定义计时移除遗留 5 分钟，只保留 1/2/3 分钟。
- Reasons:
  - 首页问题来自缺少前景信息层级而非背景素材；强化战术简报和状态信息能填补视觉空洞，同时不破坏既有品牌气质。
  - 头像需要按使用场景形成清晰层级，候选与猜测记录是辨识瓶颈，终局头像原本已足够大。
- Verification:
  - 1440×900 真实数据浏览器回归：首页、规则、候选和猜测记录均无重叠；猜测行实测 68px，头像 48×48px。
  - 390×844 回归：首页标题稳定为两行、候选头像 48px、横向溢出为 0；完整规则口径显示八类赛区。
  - 完整 unittest 55/55、Python compileall、`node --check static/app.js` 和 `git diff --check` 全部通过。
- Next steps:
  - 本轮按用户当前请求仅完成本地修改，没有提交、推送或部署；待用户确认后再发布。
  - 已为桌面端实机预览启动本地真实数据服务：`http://127.0.0.1:8766`，Uvicorn PID 31472；`/api/meta` 返回 200。服务仅用于本机查看，尚未提交或部署。

## 2026-07-19 — 玩家文案清理与已猜选手资料卡

- Request:
  - 用户要求删除面向维护者的规则说明、隐性地区比较规则、“其他”赛区、后台术语与模型名，清理装饰性 emoji，并让已选/已猜选手可点击查看资料。
- Changes:
  - 规则统一为“游戏规则 / 属性判定 / 赛区划分”，只保留位置、混合位置、战队/自由身三类玩家判定，以及欧洲、独联体、北美、南美、亚洲、大洋洲、中东非洲七个赛区。
  - 删除 `player_overrides.json`、人工订正、数据来源、队伍别名归一化和中国地区内部比较等维护实现说明；这些规则仍保留在代码与项目文档中，不再对玩家展示。
  - 首页赛区数量改为读取当前七项 meta；状态板的维护基准改成玩家提示。
  - 顶栏右侧只显示“选手库 650 人 / 更新于 2026-07-19”，删除 AI 模型别名；桌面横排、移动端右侧两行。
  - 清理随机匹配、每日/无限模式、重赛、AI 回放、纠错、搜索事件、偷看谜底、每日分享等位置的 Unicode emoji/pictogram。
  - 已猜记录的头像和姓名改成可访问按钮；点击后打开独立选手资料卡，显示头像、昵称、真名、位置、国籍/赛区、当前战队、年龄、Major 参赛和冠军数，并提供 Liquipedia/HLTV 外链。
  - 资料卡支持遮罩、关闭按钮和 Escape 关闭；关闭后键盘焦点返回原选手。候选下拉仍保持点击即猜，避免交互冲突。
- Verification:
  - 1440×900 首页/规则/资料卡和 390×844 移动资料卡真实数据视觉回归通过；全页横向溢出为 0。
  - 自动化确认顶栏 meta 位于桌面最右侧、赛区为 7、禁用维护文案未显示，资料卡 Escape 关闭及焦点恢复有效。
  - `static/index.html` 与 `static/app.js` Extended Pictographic 扫描为 0；“口径/协议/人工覆盖/模型名”等残留扫描为 0。
  - 完整 unittest 55/55、Python compileall、`node --check static/app.js` 和 `git diff --check` 全部通过。
- Next steps:
  - 本地真实数据预览仍运行于 `http://127.0.0.1:8766`；本轮未提交、推送或部署，等待用户实机确认。

## 2026-07-19 — 首页 Hero 回退与 AI 三档职责重构

- Request:
  - 删除首页 `home-hero` 展示框，直接保留模式入口和背景。
  - 解释并修复 Top20 AI 固定首猜 k0nfig、第二手频繁命中的机械体验。
  - AI 强度重新定义为：下饭完全随机；普通首轮信息增益前五随机、之后由模型自主选择；作弊使用最优求解。
  - 三档下拉只显示“下饭 / 普通 / 作弊”，提高一分钟局内行动速度，并把 AI 回放改成玩家能读懂的语言。
- Findings:
  - 房间只把 99 人 Top20 候选池和公开反馈交给 solver，没有传入实际谜底，不存在答案泄漏。
  - 原首轮数学最优是 k0nfig：99 人形成 85 种反馈，77 个谜底一次反馈即成为唯一候选；遍历非 k0nfig 谜底，原作弊策略第二手 84/98 局命中，其中 76 局已是唯一候选。
  - 本地旧 `gpt-5.5-cstrikle` 路由已从 CPA 模型表消失，最近本地对局全部 502 后使用 solver fallback，进一步造成纯脚本体验。
  - `grok-4.5-cstrikle` 最小工具调用可用，但真实候选决策在 low/medium 下 6–8 秒均超时；同局面 `gpt-5.6-terra` 的 low/medium 分别为 4.27/4.42 秒，并成功返回自主选择和中文理由。
- Changes:
  - 整体删除 `home-hero` HTML、专属 CSS、状态节点写入逻辑；模式标题首屏上移。为减少动态偏好增加卡片无动画降级。
  - 下饭档不读取反馈、不运行 solver、不请求模型，只从当前题库随机选择未猜过的人。
  - 普通档首轮从信息增益前五随机且不请求模型；后续服务器只提供与全部反馈相符的候选及公开属性，由模型自行选择。候选唯一时直接提交，不再请求。
  - 普通档每轮只暴露 `submit_guess`，要求附一句中文理由；只调用一次，8 秒超时后从合法候选使用备用人选，不再搜索、聊天或二次请求。
  - 作弊档全程使用原确定性 solver，保持全局最优和小集合精确求解，不等待模型生成解说。
  - 回放事件改为“范围如何缩小 / 该档如何选人 / 最终选择 / AI 的一句理由”，前端移除期望剩余、最坏分支、信息熵和排名；回放标题只显示难度，不显示内部模型名。
  - 本地 `.env` 切换为 `gpt-5.6-terra`，保留 `AI_REASONING_EFFORT=medium`，新增 `AI_DECISION_TIMEOUT_SECONDS=8`；同步更新 `.env.example`、README 和专项报告。
- Verification:
  - 完整 unittest 58/58；新增下饭不调用模型、普通开局前五随机、普通候选内自主选择/超时备用、作弊不等待模型、状态文案不泄露人名等覆盖。
  - Python compileall、`node --check static/app.js`、四份关键 JSON、`git diff --check` 全部通过。
  - 真实 CPA 普通档 smoke：`gpt-5.6-terra` medium 4.42 秒选择 friberg，并返回自然语言理由。
  - 本地 `http://127.0.0.1:8766` 返回 200，meta 为 650 人、AI=`gpt-5.6-terra`；首页不含 `home-hero`，三档短标签和无数学回放文案均已加载。
  - 1440×900 与 390×844 无动画视觉回归通过，三张模式卡完整显示。
- Next steps:
  - 本轮按当前请求只在本地修改并保持预览运行，没有提交、推送或部署；待用户实机体验普通档速度和选择风格后再发布。

## 2026-07-19 — AI 生产路由与两分钟局可行性调查

- Request:
  - 评估 grok 4.5 是否仍值得作为普通难度模型、function calling 是否为硬要求、个人 Codex/ChatGPT 账号是否适合公开站点，以及春川 `chatgpt2api` 免费号池能否替代。
  - 判断标准对局统一改为两分钟能否缓解 AI 行动过慢。
- Findings:
  - grok 4.5 的最小工具调用约 4.33 秒，但携带真实候选资料的普通档决策在 6–8 秒内仍会超时；问题主要在上游模型链路，延长整局只能容纳等待，不能改善单次响应。
  - 项目已实现 `AI_TOOLS_MODE=text`，普通档不强制要求 function calling；模型可返回严格 JSON，服务端仍会校验选手是否位于合法候选集。
  - 春川 CPA 当前启用 1 个 Codex 账号和 35 个 xAI 账号；`_orig_codexcli` 下 10 份文件是留档，不参与当前路由。
  - 春川 `chatgpt2api` 与 CPA 是独立服务，当前镜像为 1.4.1；其十几个免费 ChatGPT 网页账号不是 Codex API 账号。该项目文本接口并非完整通用代理，文档仅明确支持网页搜索类工具，不保证任意自定义 function tool。
  - `chatgpt2api` 属于官网逆向链路，项目自身明确警告不要用于商业、批量或规模化自动调用，并提示账号可能受限或封禁；不适合作为公开游戏的唯一生产后端。
  - 当前 AI 循环首轮等待 0.8 秒、每手间隔约 1–1.5 秒；普通档最坏还包含每手最多 8 秒的模型等待。8 次猜测在极端情况下可能超过 60 秒，因此标准局改成 120 秒有实际价值，但不应被视作供应商延迟修复。
- Changes:
  - 本轮仅完成本地代码、春川容器与上游项目文档的只读调查；未修改业务代码、服务器配置或账号池。
- Verification:
  - 核对本地普通档同时具备 native tools 与正文 JSON 两条协议；候选合法性由服务端 `_allowed_guess_pages` 检查。
  - 核对春川 `chatgpt2api`、`cli-proxy-api`、CPA 管理面板和 Caddy 容器均在运行；确认已加载账号类型和镜像版本。
- Next steps:
  - 推荐将标准对局改为 120 秒，并保留 8 秒单轮超时和备用候选。
  - 生产环境优先使用独立、可限额的正式 API/专用账号；`chatgpt2api` 只适合低流量实验或故障备用，不承载公开主流量。

## 2026-07-20 — 两分钟标准局与 chatgpt2api 门槛实测

- Request:
  - 用户接受前述方案，要求实际尝试两分钟标准局、正文 JSON 协议和春川 `chatgpt2api` 免费号池。
- Changes:
  - 标准房间由服务端固定为 120 秒；旧客户端即使提交 60 秒也会被纠正。前端标准难度说明和提交值同步改为 2 分钟；自定义房仍保留不限时与 1/2/3 分钟。
  - 新增 `scripts/benchmark_text_provider.py`：不读取项目 `.env`，从指定 JSON 配置读取密钥且不打印；用真实 `compare()` 反馈自动构造歧义候选，要求正文 JSON，并校验提交是否位于白名单。
  - README 增加两分钟规则和隔离基准用法；专项 AI 报告记录实测数据和停止条件。
- Benchmark:
  - 春川 `chatgpt2api` 当前有 14 个网页账号，实例暴露 `gpt-5-mini`、`gpt-5-3-mini`、`gpt-5-5-mini` 等文本别名。
  - `gpt-5-mini` 1/1 在 8 秒超时。
  - `gpt-5-5-mini` 6 局中 4 局成功、2 局超时；成功响应均为合法候选 JSON，耗时约 5.82–8.04 秒。
  - `gpt-5-3-mini` 3 局中 2 局成功、1 局超时；把输入压到 8 人短名单后又连续 3/3 超时。
  - 正文 JSON 协议可行，但 8 秒内稳定率不够；瓶颈主要在上游首包/账号调度，不是 function calling 或候选文本长度，因此没有扩到 100 局，也没有接入生产路由。
- Production safety:
  - 生产 CStrikle 仍为 `grok-4.5 / https://cliproxy.estia.moe/v1 / auto / low`，没有使用本地个人 `gpt-5.6-terra`。
  - 春川临时基准脚本已删除；没有修改 `chatgpt2api` 账号池、CPA 或生产 CStrikle 配置。
- Verification:
  - 完整 unittest 60/60；Python compileall、`node --check static/app.js`、`git diff --check` 和旧 1 分钟标准设置扫描通过。
  - 本地真实服务持续运行于 `http://127.0.0.1:8766`；前端静态资源确认标准难度提交 120 秒。
- Next steps:
  - 本轮没有提交、推送或部署。若发布当前改动，生产仍会保留服务器 `.env` 中的 grok 路由；`chatgpt2api` 不建议作为主后端。

## 2026-07-20 — 下饭难度恢复自由 AI

- Request:
  - 用户明确“下饭随便猜”不是服务端随机抽人，而是恢复项目求解器接入前的玩法：模型读取反馈后，凭自己的 CS 常识自由选择。
- Historical basis:
  - `afef9ee` 初版是完整自由 Agent；`36b7443` 保留自由选择，同时增加首轮不搜索、单轮一次搜索和后续步骤强制提交；`65dc558` 才引入求解器指定落子。
- Changes:
  - 下饭使用独立提示词与完整历史输入，不调用候选过滤、信息增益或精确求解，也不设置 `_allowed_guess_pages` / `_required_guess`。
  - 第一轮仅提供聊天和提交工具；获得反馈后可使用一次 DDGS。每轮最多执行 `AI_MAX_STEPS` 次模型动作，第二步强制提交。
  - 模型可提交任意选手库内且未猜过的人，不要求位于题库或严格反馈候选中；保留正文 JSON 兼容。
  - 每次模型请求仍受 8 秒上限约束；失败时返回随机题库备用人选，由 Room 保证对局继续。
  - 普通和作弊难度的现有行为未修改；README 与专项报告已同步。
- Verification:
  - 新增下饭反馈输入、候选外自由选择、首轮禁搜、失败兜底测试；完整 unittest 62/62 通过。
  - Python compileall 与 `git diff --check` 通过。
  - 真实模型烟测成功：本地 `gpt-5.6-terra` 在 4.38 秒提交 ZywOo，事件包含 usage、reasoning、公开思路和 guess。
  - 本地真实服务已重启，PID 7792 监听 `http://127.0.0.1:8766`，`/api/meta` 返回 200。
- Next steps:
  - 本轮未提交、推送或部署；待用户体验确认后再发布。

## 2026-07-20 — 本地 AI 切回 Grok 4.5

- Request:
  - 用户要求本地预览停止使用个人 `gpt-5.6-terra`，改走 CPA 的 Grok 4.5；同时明确该路由的上游原生搜索是全局启用且无法关闭的。
- Changes:
  - 本地 `.env` 改为 `AI_MODEL=grok-4.5`、`AI_REASONING_EFFORT=low`。
  - 本地 `AI_SEARCH_ENABLED=0`，只关闭项目额外提供的 DDGS，不能也不会关闭 CPA/Grok 上游原生搜索，避免同一回合叠加两套搜索。
  - 下饭提示词按项目搜索开关生成；DDGS 关闭时不再要求模型调用不存在的搜索工具，而是使用自身知识及接口自动提供的信息。
  - 新增关闭项目搜索后不暴露 `ddgs_search` 的回归测试。
- Verification:
  - `tests.test_ai_player` 9/9、Python compileall、`git diff --check` 通过。
  - Grok 4.5 真实下饭烟测成功：7.72 秒提交 s1mple，包含 reasoning、聊天、公开理由和 guess；项目 DDGS 确认为 false。
  - 本地服务已重启，PID 6640 监听 `http://127.0.0.1:8766`，meta 返回 `ai_model=grok-4.5`。
- Next steps:
  - 7.72 秒已非常接近当前 8 秒单请求上限；若实际局内仍频繁触发备用人选，应优先把 Grok 单次上限小幅提高，而不是重新开启 DDGS。
  - 本轮未提交、推送或部署。

## 2026-07-20 — Grok 4.5 连续超时的 CPA 日志诊断

- Request:
  - 用户实玩发现 Grok 4.5 每手都超过 8 秒，要求检查本地与 CPA 日志定位原因；本轮只诊断，不修改配置。
- Findings:
  - 本地房间 `DDR4` 的 8 手 AI 请求全部失败，记录耗时约 8.66、7.98、8.00、8.02、7.98、8.01、8.02、8.00 秒，没有一手收到模型提交。
  - CPA 对应 8 个请求分别返回 HTTP 500，代理侧耗时约 7.38–7.70 秒；错误文件的最终上游响应均为 `context canceled`。
  - 这些请求分别选用了 8 个不同 xAI OAuth 账号，因此不是单一坏账号或账号粘连。
  - CPA 当前配置对 canonical `grok-4.5` 全局执行 `tools.-1: {type: web_search}`；转发到 Grok Workspace 时，实际工具列表同时包含项目的 `say`、`submit_guess` 和 CPA 注入的 `web_search`、`x_search`。
  - 每个错误文件都只有 `API REQUEST 1`；虽然 CPA 配置 `request-retry: 3`、最多 6 个凭据，但客户端主动取消会终止整个 context，不会触发换号重试。
  - 额外用相同七手历史、仅在诊断进程内临时放宽到 30 秒，仍在 30.56 秒超时；CPA 侧单次上游调用持续 29.28 秒后同样记录 `context canceled`。
- Conclusion:
  - 根因是 Grok 4.5 强制原生搜索链路的长尾延迟，加上应用端硬截止主动取消；CPA 的 500 是取消后的结果，不是先发生的上游故障。
  - 8 秒不是稍微偏紧，而是与该路由不兼容；简单提高到 12 秒也无法覆盖已实测超过 30 秒的长尾。
  - 问题与 solver、项目 DDGS、提示词长度或单个账号无直接关系；第一轮短历史同样出现超时。
- Changes:
  - 无业务代码、`.env`、CPA、账号池、生产或本地服务变更。
- Next steps:
  - 若坚持 Grok 4.5 全局搜索，只能接受更长且不稳定的 AI 回合，或把 AI 决策改成不阻塞游戏时钟的异步流程。
  - 面向两分钟对局，更现实的方案是为游戏使用不强制原生搜索的独立路由/模型；不能只把 8 秒机械改成 12 秒。

## 2026-07-20 — CPA Grok 4.5 搜索路由隔离

- Request:
  - 用户希望普通 Grok 4.5 调用继续使用 CPA 全局 `web_search`，但为 CStrikle 提供一个不注入原生搜索的独立 Grok 4.5 路由。
- Findings:
  - CPA v7.2.80 已有 `grok-4.5-cstrikle → grok-4.5` 的 fork alias，但 alias 会先解析为 canonical 模型，原全局 payload 规则仍会命中，因此只建别名不能隔离搜索。
  - CStrikle 的 AI 请求已经稳定携带 `metadata.client=cstrikle`；CPA 示例配置明确支持 payload `match` / `not-match` 按 JSON 路径筛选。
- Changes:
  - 在春川 `/home/ubuntu/docker/cliproxy/config.yaml` 的 Grok 全局搜索注入规则增加 `not-match: metadata.client=cstrikle`。
  - 修改前备份为 `config.yaml.bak-before-cstrikle-search-split-20260720_005019`，随后重启 `cli-proxy-api`。
  - 本地 `.env` 模型改为 `grok-4.5-cstrikle`；项目 DDGS 仍关闭，推理强度仍为 low。
- Verification:
  - CS 别名请求的 CPA 上游 body 只包含项目 `say` / `submit_guess`，`web_search` 与 `x_search` 均未出现。
  - 使用普通 `grok-4.5` 且 `metadata.client=route-verification-other` 的对照请求，上游 body 仍包含 `web_search` 和 `x_search`。
  - `cli-proxy-api` 重启后正常运行；本地服务 PID 2612 监听 `http://127.0.0.1:8766`，meta 返回 `grok-4.5-cstrikle`。
- Remaining issue:
  - 搜索隔离解决了超过 30 秒的搜索长尾，但 Grok 4.5 本身对七手完整反馈仍然很慢：8 秒测试失败，临时 20 秒诊断也未完成。
  - 因此路由拆分已经成功，但不能单独保证当前 8 秒截止下的可用性；下一步需单独优化提示输入/调用方式或更换低延迟模型。
- Next steps:
  - 本轮没有推送或部署 CStrikle 代码；CPA 路由和本地预览配置已经生效。

## 2026-07-20 — 三档 AI 聊天与 20 秒回合预算

- Request:
  - 用户决定 CStrikle Grok 路由保持无搜索，把每轮 AI 等待放宽到 20 秒，并要求下饭、普通、作弊三档都能使用 `say` 在聊天框说话。
- Changes:
  - `.env`、`.env.example`、`server/config.py` 默认和当前说明统一为 20 秒。
  - 下饭最多执行两步模型动作，但两步共享同一个 20 秒 deadline，不会变成最坏 40 秒等待；继续在同一响应中要求 `say + submit_guess`。
  - 普通反馈局的模型请求由只提供 `submit_guess` 改为同时提供 `say + submit_guess`，要求同一响应完成聊天和候选内选择。
  - 普通开局与候选唯一路径仍由服务器确定落子，新增一次只暴露 `say` 的聊天调用；聊天失败不改变人选。
  - 作弊仍完全由 solver 决定猜谁，模型只收到已确定的人选并被强制调用一次 `say`；超时或失败仍提交 solver 结果。
  - 回放中的“垃圾话”标签改为“AI 聊天”。
- Reasons:
  - 之前聊天框没有 AI 消息，是因为下饭请求在模型返回工具调用前全部被 8 秒截止取消；前端聊天框和 `on_say` 广播链路没有损坏。
  - 将固定落子与聊天解耦，能让普通/作弊参与聊天，同时防止模型改写求解结果。
- Verification:
  - 完整 unittest 64/64、Python compileall、`node --check static/app.js`、`git diff --check` 通过。
  - 无搜索 `grok-4.5-cstrikle` 三档并行真实首轮烟测全部成功：
    - 下饭 11.78 秒，猜 s1mple，聊天 1 条；
    - 普通 14.12 秒，猜 k0nfig，聊天 1 条；
    - 作弊 7.13 秒，猜 k0nfig，聊天 1 条。
  - 三档均无 model/chat error；普通与作弊的猜测仍来自原有服务器/solver 路径。
- Next steps:
  - 本轮未提交、推送或部署；本地预览重启后可直接体验。

## 2026-07-20 — 当前版本发布

- Request:
  - 用户接受暂时继续使用无搜索 Grok 路由，要求将当前累计改动推送到私有 GitHub 仓库并部署到春川 ARM。
- Release scope:
  - 包含此前已完成的选手数据规则与修正、标准局两分钟、AI 三档策略、玩家化回放、20 秒共享决策预算、三档聊天、UI 与规则说明更新，以及隔离的文本模型基准脚本。
  - 本地 `.env` 已确认由 `.gitignore` 排除；生产密钥、反馈数据和日志不进入 Git，也不会被部署归档覆盖。
- Pre-deploy verification:
  - 秘密信息扫描没有发现实际 API Key、Bearer Token 或私钥。
  - 完整 unittest 64/64 通过。
  - Python compileall、`node --check static/app.js` 和 `git diff --check` 通过。
  - 审阅新增基准脚本时修正异常分支引用未定义变量的问题。
- Deployment plan:
  - 提交并推送 `main` 后从精确提交生成归档；部署前备份生产源码和 `.env`，保留运行数据。
  - 生产非秘密 AI 配置设为 `grok-4.5-cstrikle`、项目 DDGS 关闭、low、auto、20 秒。
- Deployment result:
  - 发布提交 `3fa4ffa`（`Improve AI modes and game experience`）已推送到 `origin/main`，并从该精确提交生成归档部署。
  - 旧生产目录完整保留在 `/home/ubuntu/docker/backups/cstrikle-before-3fa4ffa-20260720-013239`，其中包含原 `.env`、compose、源码、反馈与日志。
  - 新目录复制原生产 `.env` 和反馈数据，只更新非秘密项：`AI_MODEL=grok-4.5-cstrikle`、`AI_SEARCH_ENABLED=0`、`AI_REASONING_EFFORT=low`、`AI_TOOLS_MODE=auto`、`AI_DECISION_TIMEOUT_SECONDS=20`。
- Production verification:
  - `cstrikle` 容器重建后为 healthy；启动日志无错误。
  - 容器内与公开 `https://cs2.estia.moe/api/meta` 均返回 200、650 名选手、AI 模型 `grok-4.5-cstrikle`。
  - 公开首页与静态脚本返回 200；确认 `FribergCS2`、标准局 120 秒和“AI 聊天”新文案已上线。
  - 旧目录与新目录的反馈文件数一致，生产反馈挂载保留。
  - 生产容器真实 AI 烟测 11.07 秒完成，事件为 decision/say/guess，证明无搜索 Grok 路由、聊天工具和猜测链路可用。
- Next steps:
  - 继续观察 Grok 的真实长尾延迟；当前 20 秒超时和合法猜测兜底可保证对局继续，但长期仍应寻找更稳定、低延迟且成本可控的专用渠道。
