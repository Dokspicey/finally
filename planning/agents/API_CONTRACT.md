# API Contract

**Status:** DRAFT — owned by `backend-api`. Updated as endpoints land. Frontend and integration tester read this as the source of truth.

Base URL: same origin as the frontend (`/api/*`). All responses are JSON unless noted.

**Conventions**
- Timestamps are ISO-8601 UTC strings with second precision (e.g. `"2026-05-18T13:42:11Z"`), matching the `*_at` columns in the DB schema (PLAN.md §7).
- Money/price/quantity values are JSON numbers (floats). Fractional shares are allowed; the backend does not round.
- Tickers are upper-case ASCII (the backend normalizes on input).
- A single hardcoded user (`user_id = "default"`) is used for now — the API does not require any user identifier.
- Error responses follow FastAPI's convention: HTTP 4xx/5xx with body `{"detail": "<reason>"}`.

---

## GET /api/health
Liveness probe.

**Response 200:**
```json
{ "status": "ok" }
```

---

## GET /api/stream/prices
SSE stream of live price updates. Frontend consumes with `EventSource`.

- `Content-Type: text/event-stream`
- The server emits an initial `retry: 1000` directive so the browser auto-reconnects after 1s on drop.
- Each `data:` line is a JSON object keyed by ticker. Every value matches `PriceUpdate.to_dict()`:

```json
{
  "AAPL": {
    "ticker": "AAPL",
    "price": 190.50,
    "previous_price": 190.42,
    "timestamp": 1779090804.66,
    "change": 0.08,
    "change_percent": 0.042,
    "direction": "up"
  },
  "GOOGL": { "...": "..." }
}
```

- `direction` is `"up" | "down" | "flat"`.
- `timestamp` is a UNIX epoch float (seconds). This is the only place we use epoch floats; everywhere else is ISO-8601.
- On connect the server emits a snapshot containing every tracked ticker, then pushes diffs as the cache version changes.

---

## GET /api/portfolio
Current portfolio state.

**Response 200:**
```json
{
  "cash_balance": 9821.50,
  "total_value": 10134.27,
  "unrealized_pnl": 134.27,
  "unrealized_pnl_percent": 1.34,
  "positions": [
    {
      "ticker": "AAPL",
      "quantity": 1.5,
      "avg_cost": 190.00,
      "current_price": 192.18,
      "market_value": 288.27,
      "unrealized_pnl": 3.27,
      "unrealized_pnl_percent": 1.15,
      "updated_at": "2026-05-18T13:42:11Z"
    }
  ]
}
```

Notes:
- `total_value = cash_balance + sum(positions[].market_value)`.
- `current_price` falls back to `avg_cost` when the price cache has no entry (PLAN.md §7 valuation fallback). Frontend should treat the value as authoritative; it never has to compute fallbacks itself.
- `unrealized_pnl` and `unrealized_pnl_percent` at the top level are vs. cost basis of all open positions (`sum(quantity * (current_price - avg_cost))`). Per-position fields are the same math, per row.
- `positions` is sorted by ticker ascending. Empty array when there are no holdings.

---

## POST /api/portfolio/trade
Execute a market order. Instant fill at the current price from the cache. Cash and position rows are mutated under a single asyncio lock (PLAN.md §8 concurrency).

**Request body:**
```json
{
  "ticker": "AAPL",
  "side": "buy",
  "quantity": 1.5
}
```

- `side` is `"buy" | "sell"` (case-insensitive on the wire, lower-cased before persistence).
- `quantity` must be `> 0`. Fractional shares are supported.
- `ticker` is upper-cased server-side.

**Response 200:**
```json
{
  "trade": {
    "id": "0c3f...uuid",
    "ticker": "AAPL",
    "side": "buy",
    "quantity": 1.5,
    "price": 192.18,
    "executed_at": "2026-05-18T13:42:11Z"
  },
  "cash_balance": 9533.23,
  "position": {
    "ticker": "AAPL",
    "quantity": 1.5,
    "avg_cost": 192.18,
    "updated_at": "2026-05-18T13:42:11Z"
  }
}
```

- `trade` fields mirror the `trades` table row.
- `position` reflects the post-trade state. When a `sell` zeroes the position out, `position` is `null` and the row is deleted from `positions`.
- The handler also writes a `portfolio_snapshots` row immediately after the trade commits (PLAN.md §8).

**Response 400 (validation failures):**
```json
{ "detail": "insufficient cash" }
```

Other expected `detail` values:
- `"insufficient shares"` — sell more than held
- `"quantity must be positive"`
- `"unknown side"` — anything other than buy/sell
- `"no price available"` — cache has no quote and no fallback exists (only on a buy of a never-seen ticker)

---

## GET /api/portfolio/history?from=&to=
Portfolio value snapshots used for the P&L line chart.

- `from`, `to`: ISO-8601 timestamps. Both optional. Default window is last 24h (`to = now`, `from = now - 24h`).
- Inclusive on both ends.

**Response 200:**
```json
{
  "snapshots": [
    { "id": "uuid", "total_value": 10000.00, "recorded_at": "2026-05-17T13:42:11Z" },
    { "id": "uuid", "total_value": 10134.27, "recorded_at": "2026-05-18T13:42:11Z" }
  ]
}
```

- Ordered by `recorded_at` ascending so the frontend can plot directly.
- Empty array when no snapshots fall in the window.

---

## GET /api/trades?limit=
Trade history.

- `limit`: positive integer, optional, default `100`, max `500`.

**Response 200:**
```json
{
  "trades": [
    {
      "id": "uuid",
      "ticker": "AAPL",
      "side": "buy",
      "quantity": 1.5,
      "price": 192.18,
      "executed_at": "2026-05-18T13:42:11Z"
    }
  ]
}
```

- Ordered by `executed_at` descending (most recent first).

---

## GET /api/watchlist
Current watchlist with live prices.

**Response 200:**
```json
{
  "watchlist": [
    {
      "ticker": "AAPL",
      "added_at": "2026-05-18T13:00:00Z",
      "price": 192.18,
      "previous_price": 190.42,
      "change": 1.76,
      "change_percent": 0.92,
      "direction": "up"
    }
  ]
}
```

- Ordered by `added_at` ascending (the order tickers were added).
- When the price cache has no entry yet for a watched ticker (e.g. cold start or invalid Massive ticker), `price` and friends are `null`. The frontend should render `—` in that case.

---

## POST /api/watchlist
Add a ticker to the watchlist. Idempotent — re-adding an existing ticker is a no-op success.

**Request body:**
```json
{ "ticker": "PYPL" }
```

**Response 201:**
```json
{
  "ticker": "PYPL",
  "added_at": "2026-05-18T13:42:11Z"
}
```

Side effects:
- The ticker is added to the market data source's tracked set so prices start streaming.

**Response 400:**
- `{"detail": "ticker required"}` — missing/empty
- `{"detail": "invalid ticker"}` — fails the simple `[A-Z.\-]{1,10}` shape check

---

## DELETE /api/watchlist/{ticker}
Remove a ticker from the watchlist. Idempotent — removing a ticker that isn't there returns 200.

**Response 200:**
```json
{ "ticker": "PYPL", "removed": true }
```

- `removed` is `false` when the ticker wasn't on the watchlist.

Side effects:
- The ticker is removed from the market data source's tracked set **only if no open position references it** (PLAN.md §6 tracked-ticker rule).

---

## POST /api/chat
Send a user message to the LLM. The LLM may auto-execute trades + watchlist changes via the same code paths as the REST endpoints (single global `asyncio.Lock` — PLAN.md §8/§9). Failed actions are reported in the response and persisted; the LLM is **not** re-invoked on failure.

**Request body:**
```json
{ "message": "buy 1 AAPL" }
```

- `message` must be non-empty after `.strip()`. Empty/missing → 422.

**Response 200:**
```json
{
  "message": {
    "id": "uuid",
    "role": "assistant",
    "content": "On it — buying 1 AAPL.",
    "actions": {
      "trades": [{ "ticker": "AAPL", "side": "buy", "quantity": 1.0 }],
      "watchlist_changes": [{ "ticker": "PYPL", "action": "add" }],
      "action_results": [
        {"kind": "trade", "ticker": "AAPL", "success": true, "note": "bought 1 AAPL @ 192.18"}
      ]
    },
    "action_results": [
      {"kind": "trade", "ticker": "AAPL", "success": true, "note": "bought 1 AAPL @ 192.18"}
    ],
    "created_at": "2026-05-18T13:42:12Z"
  },
  "trades_requested": [
    { "ticker": "AAPL", "side": "buy", "quantity": 1.0 }
  ],
  "watchlist_changes_requested": [
    { "ticker": "PYPL", "action": "add" }
  ],
  "action_results": [
    {
      "kind": "trade",
      "ticker": "AAPL",
      "side": "buy",
      "quantity": 1.0,
      "success": true,
      "note": "bought 1 AAPL @ 192.18",
      "trade": {
        "id": "uuid",
        "ticker": "AAPL",
        "side": "buy",
        "quantity": 1.0,
        "price": 192.18,
        "executed_at": "2026-05-18T13:42:11Z"
      },
      "cash_balance": 9807.82,
      "position": {
        "ticker": "AAPL",
        "quantity": 1.0,
        "avg_cost": 192.18,
        "updated_at": "2026-05-18T13:42:11Z"
      }
    },
    {
      "kind": "watchlist",
      "ticker": "PYPL",
      "action": "add",
      "success": true,
      "note": "added PYPL to watchlist"
    }
  ]
}
```

- `message` is a full `ChatMessage` object (same shape as items in `/api/chat/history` — `{id, role, content, actions, action_results, created_at}`). `role` is always `"assistant"` for this response. The `id` and `created_at` match the row just written to `chat_messages`; the frontend can therefore add it directly to its message list without remapping. `action_results` is duplicated on both the top-level payload and inside `message` for convenience — they are the same array.
- `trades_requested` / `watchlist_changes_requested` (at the top level) mirror what the LLM asked for (normalized: tickers upper-case, sides/actions lower-case).
- `action_results` is one row per requested action, ordered trades-first then watchlist-changes. Every row has `kind` ∈ `{"trade","watchlist"}` (the discriminator the frontend `ActionResult` type switches on), `success: bool`, and `note: str`. Trade-side notes use past-tense English (`"bought"` / `"sold"`).
- Successful trade rows also carry `trade` (mirror of the `/api/portfolio/trade` body's `trade` field), `cash_balance`, and `position` (the post-trade snapshot from `execute_trade`; `position` is `null` when a sell zeroed the holding).
- Failed trade rows: `success: false`, `note` is the `TradeError` message (`"insufficient cash"`, `"insufficient shares"`, `"no price available"`, `"unknown side"`, `"quantity must be positive"`, `"invalid ticker"`). No mutation occurred.
- Watchlist add: `note` is `"added <TICKER> to watchlist"` or `"<TICKER> already on watchlist"` (both `success: true` — idempotent).
- Watchlist remove: `note` is `"removed <TICKER> from watchlist"` or `"<TICKER> was not on watchlist"` (both `success: true`).
- The full record (including failed actions) is persisted into `chat_messages.actions` on the assistant turn so future LLM calls see accurate history.

**Mock mode (`LLM_MOCK=true`):**
- Generic messages → benign hello reply (no actions).
- `buy <n> <ticker>` / `sell <n> <ticker>` → emits a matching trade for auto-execution.
- `watch <ticker>` → watchlist add.
- `unwatch <ticker>` → watchlist remove.
- Matching is case-insensitive substring (regex). Used by Playwright E2E tests.

**Response 422:** Pydantic validation failure (missing/empty `message`).
**Response 502:** Upstream LLM error (non-mock mode only).

---

## GET /api/chat/history?limit=
Replay recent chat messages — used by the frontend to repopulate the chat panel on page load.

- `limit`: positive integer, optional, default `50`, max `500`.

**Response 200:**
```json
{
  "messages": [
    {
      "id": "uuid",
      "role": "user",
      "content": "buy 1 AAPL",
      "actions": null,
      "created_at": "2026-05-18T13:42:11Z"
    },
    {
      "id": "uuid",
      "role": "assistant",
      "content": "On it — buying 1 AAPL.",
      "actions": {
        "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 1.0}],
        "watchlist_changes": [],
        "action_results": [
          {"kind": "trade", "ticker": "AAPL", "success": true, "note": "bought 1 AAPL @ 192.18"}
        ]
      },
      "created_at": "2026-05-18T13:42:12Z"
    }
  ]
}
```

- Ordered oldest-first.
- `role` is `"user" | "assistant"`.
- `actions` is `null` on user rows (and on assistant rows where the stored JSON failed to parse). On a normal assistant row it's a dict with `trades`, `watchlist_changes`, and `action_results` — the same `action_results` shape as `/api/chat`.

---

**Edit log** — one line per contract change.

- `2026-05-18` — initial scaffold.
- `2026-05-18` — backend-api: filled concrete request/response shapes for `/api/health`, `/api/portfolio*`, `/api/trades`, `/api/watchlist*`, and documented the SSE event payload.
- `2026-05-19` — backend-api: task #4 shipped. Implementation matches the drafted contract exactly (no shape changes). `execute_trade(ticker, quantity, side)` is importable from `app.api` for the chat layer.
- `2026-05-19` — llm-engineer: filled concrete shapes for `/api/chat` and `/api/chat/history` (request, response, `action_results` rows, mock-mode behavior, history `actions` parsing).
- `2026-05-19` — llm-engineer: BUG-001 fix — action_results discriminator key is `kind` (was `type` — frontend `ActionResult.kind` is the source of truth). Trade notes use past-tense English (`bought` / `sold`, not `buyed` / `selled`).
- `2026-05-19` — llm-engineer: BUG-002 fix — `POST /api/chat` now returns `message` as a full `ChatMessage` object (`id`, `role`, `content`, `actions`, `action_results`, `created_at`), matching the items in `/api/chat/history` and the frontend `ChatMessage` interface. `action_results` is duplicated at the top level for convenience and is the same array as `message.action_results`.
