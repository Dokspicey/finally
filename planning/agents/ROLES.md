# FinAlly Team — Role Briefs

The authoritative spec is `planning/PLAN.md`. Section references (§) point at it. Coordination rules:

- Communicate with teammates via `SendMessage` (by name). No terminal commands to inspect other agents.
- Mark your own tasks `in_progress` when you start and `completed` when fully done (tests pass, code commits-ready). Never mark complete if anything is unfinished.
- After completing a task, call `TaskList` and claim the next unblocked task in your lane (lowest ID first).
- Always write code that satisfies the project's CLAUDE.md and PLAN.md.
- The market data layer (`backend/app/market/`) is **complete and frozen**. Do not modify its behavior. `backend/app/market/stream.py` exposes a FastAPI router that backend-api will mount; the `PriceCache` + tracked-ticker set are the shared bridge to portfolio/watchlist.

---

## db-engineer — Database Engineer
**Read first:** PLAN.md §4 (boundaries), §7 (schema), §10 (lazy init mention).

**Scope:**
- Create `backend/app/db/` (Python module). Keep `backend/db/` reserved for the runtime SQLite file (bind-mounted from host `db/`).
- Implement schema SQL for: `user_profile`, `watchlist`, `positions`, `trades`, `portfolio_snapshots`, `chat_messages` exactly per §7. All tables include `user_id` defaulting to `"default"`.
- Lazy initialization: on first access, create file at `db/finally.db` (relative to backend CWD or `FINALLY_DB_PATH` env override), apply schema if missing, seed default user (`$10,000` cash) and 10 default watchlist tickers (AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX).
- Expose a `get_db()` connection helper and small query helpers for use by other modules (do NOT scatter raw SQL across the codebase). Use `sqlite3` from stdlib with `check_same_thread=False` and a thread/async-safe wrapper. WAL mode preferred.
- Unit tests in `backend/tests/db/` using a temp-file SQLite path (do NOT touch the real DB).

**Done when:** Schema applies cleanly to an empty file, seed data matches §7, all helpers covered by pytest, `uv run pytest backend/tests/db/` is green.

---

## backend-api — Backend API Engineer
**Read first:** PLAN.md §4, §6 (tracked-ticker set), §8 (endpoints), §10 (frontend expectations).

**Scope:**
- Initialize the FastAPI app in `backend/app/main.py`. Mount the existing SSE router from `backend/app/market/stream.py`. Add `GET /api/health` (returns `{"status":"ok"}`).
- Implement non-chat REST endpoints from §8:
  - `GET /api/portfolio` — positions + cash + total value + unrealized P&L
  - `POST /api/portfolio/trade` — market order, instant fill at current price from `PriceCache`
  - `GET /api/portfolio/history?from&to` — `portfolio_snapshots` rows; defaults to last 24h
  - `GET /api/trades?limit=` — recent trades, newest first, default limit 100
  - `GET /api/watchlist`, `POST /api/watchlist`, `DELETE /api/watchlist/{ticker}`
- **Concurrency (§8):** Wrap all cash/position mutations (manual *and* LLM-initiated) in a single `asyncio.Lock`. Expose the executor as a function `execute_trade(...)` that `llm-engineer` can import — do not duplicate logic.
- **Tracked-ticker set:** On every watchlist add/remove and every trade that opens/closes a position, update the price source's tracked set (use the existing helper in `backend/app/market/`).
- **Portfolio snapshots:** Write one snapshot row on startup and one after each trade.
- **Valuation fallback (§7):** If `PriceCache` has no entry for a held ticker, use `avg_cost` for valuation.
- Draft `planning/agents/API_CONTRACT.md` early (request/response JSON shapes) — frontend and integration tester depend on it. Update it if anything changes during implementation.
- Unit tests in `backend/tests/api/` covering: buy, sell, insufficient cash, over-sell, fractional shares, watchlist CRUD, snapshot write, health, valuation fallback, lock serialization (use `asyncio.gather` to fire two trades).

**Done when:** All non-chat §8 endpoints implemented, `API_CONTRACT.md` matches reality, `uv run pytest backend/tests/api/` green.

---

## llm-engineer — LLM Engineer
**Read first:** PLAN.md §5 (env vars), §9 (LLM integration), §8 (chat endpoints).

**Scope:**
- Implement `POST /api/chat` and `GET /api/chat/history?limit=` in `backend/app/chat/`.
- Use **LiteLLM → OpenAI `gpt-4o`** with Structured Outputs matching the §9 schema (`message`, optional `trades[]`, optional `watchlist_changes[]`).
- Build prompt context per §9: portfolio snapshot (cash, positions with live P&L from `PriceCache`, watchlist), last 20 messages from `chat_messages`, system prompt as "FinAlly, an AI trading assistant" (concise, data-driven).
- Auto-execute trades and watchlist changes by **importing the executor from `backend-api`** (do not reimplement). Collect per-action `action_results` with `success: bool` and `note: str` (e.g., "insufficient cash"). The §9 rule: on failure, do NOT re-invoke the LLM — surface the failure in the response payload.
- Persist user + assistant messages to `chat_messages.actions` (JSON of executed actions including failures).
- `LLM_MOCK=true` returns deterministic fixtures (at minimum: a benign "hello" reply, and a reply that buys 1 AAPL when user says "buy 1 AAPL"). Tests must pass with `LLM_MOCK=true`.
- Unit tests in `backend/tests/chat/` covering: schema parsing, mock mode, context loading (last 20), action success path, action failure pass-through, history endpoint.

**Done when:** Chat endpoint round-trips with both real and mock LLM, failed actions appear in response and DB, `uv run pytest backend/tests/chat/` green.

---

## frontend-engineer — Frontend Engineer
**Read first:** PLAN.md §2 (UX + palette), §6 (SSE contract), §8 (endpoints), §10 (layout), `planning/agents/API_CONTRACT.md`.

**Scope:**
- Create `frontend/` as a Next.js 14+ TypeScript project with `output: 'export'` (static export). Use Tailwind for styling. Dark theme per §2 palette (bg `#0d1117` / `#1a1a2e`, accent `#ecad0a`, primary `#209dd7`, submit `#753991`).
- Implement the layout from §10:
  - Header: portfolio total (live), cash balance, connection-status dot (green/yellow/red).
  - Watchlist grid: ticker, price (flash green/red ~500ms CSS transition on change), daily %, sparkline (accumulated from SSE since page load).
  - Main chart area for currently selected ticker. Use **Lightweight Charts** (canvas).
  - Portfolio treemap (sized by weight, colored by P&L), P&L line chart (from `/api/portfolio/history`), positions table.
  - Trade bar: ticker (defaults to selected ticker), quantity, buy/sell buttons. Market orders, no confirmation.
  - AI chat panel: scrolling history loaded from `/api/chat/history`, message input, loading indicator, inline rendering of `action_results` (e.g., "✓ Bought 10 AAPL" / "✗ Tried to buy 50 AAPL — insufficient cash").
- SSE: native `EventSource` on `/api/stream/prices`. On disconnect, the browser auto-retries; reflect state in the connection-status dot.
- All `/api/*` calls go to the same origin — no CORS config needed.
- Unit tests (React Testing Library + Vitest) for: watchlist row flash logic, trade bar form, chat message component, the SSE reducer that maintains the price/sparkline state.

**Done when:** `npm run build` produces a static export, `npm test` is green, the app renders end-to-end against the backend (locally or in Docker), and the trade bar + chat both successfully mutate state.

---

## devops-engineer — DevOps Engineer
**Read first:** PLAN.md §4, §5, §11.

**Scope:**
- Multi-stage `Dockerfile`:
  - Stage 1: `node:20-slim` — copy `frontend/`, `npm ci`, `npm run build` → produces static export in `frontend/out/`.
  - Stage 2: `python:3.12-slim` — install `uv`, copy `backend/`, `uv sync --frozen`, copy `frontend/out/` to a backend-accessible `static/` directory. FastAPI uses `StaticFiles` with SPA fallback to serve it. Expose `8000`, `CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`.
- Scripts (idempotent):
  - `scripts/start_mac.sh` — build image if missing or on `--build`, run with `-v "$(pwd)/db:/app/db" -p 8000:8000 --env-file .env`, print URL.
  - `scripts/stop_mac.sh` — stop+rm container, leave `db/` alone.
  - `scripts/start_windows.ps1` / `scripts/stop_windows.ps1` — PowerShell equivalents.
- `.env.example` in repo root with all keys from §5 (no values).
- `db/.gitkeep` so the directory is tracked but `finally.db` is gitignored.
- Coordinate with `backend-api` on the static mount: FastAPI must serve `index.html` for any non-`/api/*` path so the SPA routes work.

**Done when:** `scripts/start_mac.sh` builds and starts the container in one command; `curl http://localhost:8000/api/health` returns 200; browser at `http://localhost:8000` shows the frontend.

---

## integration-tester — Integration Tester
**Read first:** PLAN.md §12, `planning/agents/API_CONTRACT.md`.

**Scope:**
- Set up `test/` with `package.json`, Playwright, and `test/docker-compose.test.yml` that spins up the app container + a Playwright runner container. Tests run with `LLM_MOCK=true`.
- Implement E2E specs per §12:
  - Fresh start: 10 default tickers visible, $10k cash, prices streaming (assert at least 2 distinct values for some ticker within ~5s).
  - Add ticker, remove ticker.
  - Buy 1 share: cash decreases by ~current price, position appears, portfolio updates.
  - Sell: cash increases, position decrements/removes.
  - Portfolio renders: heatmap rectangles present, P&L chart has ≥2 data points.
  - Chat (mocked): send "buy 1 AAPL", assert action confirmation appears inline and position was created.
  - SSE resilience: kill EventSource via `evaluate`, then verify reconnection (status dot returns green).
- On any failure: append a new entry to `planning/agents/BUGS.md` (use the template at the top of that file), then `SendMessage` the suspected owner with a short repro.
- Re-run after each fix; close the BUGS.md entry when green.

**Done when:** All E2E specs pass against the production container; `BUGS.md` has zero open entries.
