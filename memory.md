# Project Memory

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
