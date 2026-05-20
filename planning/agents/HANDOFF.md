# FinAlly — Handoff

Built end-to-end by the `finally-build` agent team (2026-05-18 → 2026-05-19). All eight tasks in `planning/agents/ROLES.md` are complete; both bugs filed during E2E are resolved (`planning/agents/BUGS.md`).

## Run it

```bash
bash scripts/start_mac.sh --build   # build image (first time or after code changes)
bash scripts/start_mac.sh           # subsequent starts
# → http://localhost:8000
bash scripts/stop_mac.sh            # tear down (db/ on host is preserved)
```

Windows equivalents: `scripts/start_windows.ps1` / `scripts/stop_windows.ps1`.

**Important:** the user's `.env` currently has `MASSIVE_API_KEY` set to a value that returns 404 from Massive, which makes the factory pick the live source and starves the price stream. Either clear that key in `.env` (`MASSIVE_API_KEY=`) to use the simulator (PLAN §5 default), or supply a working paid key. The E2E suite is isolated from this — its compose file pins `MASSIVE_API_KEY=""` regardless of host env.

## What's inside

| Layer | Path | Notes |
|---|---|---|
| Database | `backend/app/db/` | Stdlib sqlite3, WAL, lazy init + seed (10 default tickers + $10k cash). Helpers in `__init__.py`; never scatter SQL elsewhere. |
| Market data | `backend/app/market/` | **Frozen** — simulator + Massive client + price cache + SSE router. Built before the team was spawned. |
| REST API | `backend/app/api/` | Portfolio / trade / history / trades / watchlist. Single `asyncio.Lock` in `app.api.trades` serializes cash + position mutations; `execute_trade(...)` is the public async entry point. |
| Chat | `backend/app/chat/` | LiteLLM → `gpt-4o` with structured outputs. `LLM_MOCK=true` returns deterministic fixtures. Imports `execute_trade` and the shared watchlist coroutines — no duplicated logic. |
| Frontend | `frontend/` | Next.js 14 + TypeScript, `output: 'export'`, Tailwind dark theme (§2 palette). Lightweight Charts canvas for the main chart; native `EventSource` for SSE; sparklines accumulate from the stream since page load. |
| Docker | `Dockerfile` | Multi-stage: Node builds the static export, Python runs `uvicorn`. `_mount_frontend()` in `backend/app/main.py` serves `/app/static` with SPA fallback and a defensive `api/` rejection. |

## Verification status

| Suite | Command | Result |
|---|---|---|
| Backend unit tests | `cd backend && uv run --extra dev pytest` | 198 passed |
| Frontend unit tests | `cd frontend && npm test` | 22 passed |
| E2E (Playwright) | `cd test && npm run e2e` | 6/6 specs pass (~7s) |
| Browser smoke | `start_mac.sh` → `http://localhost:8000` | UI renders, live prices flash, trade bar buys, chat panel executes mocked trade |

## Known follow-ups (not blocking)

- `backend/app/market/factory.py` currently picks the Massive source any time `MASSIVE_API_KEY` is non-empty, even when polls return 4xx. Falling back to the simulator on repeated 4xx would make the app self-healing for users with stale/expired keys.
- `app/chat/router.py` reads back the assistant row via a local `_fetch_chat_message_by_id` helper because the role brief forbade modifying `app/db/`. If you want to consolidate, add `get_chat_message_by_id` to `backend/app/db/queries.py` and swap the call.

## Coordination artifacts (still useful)

- `planning/agents/ROLES.md` — role briefs for each engineer.
- `planning/agents/API_CONTRACT.md` — on-wire request/response shapes, with an edit log.
- `planning/agents/BUGS.md` — two resolved entries (BUG-001 field-name mismatch, BUG-002 chat message shape).
