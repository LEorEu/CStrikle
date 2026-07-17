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
