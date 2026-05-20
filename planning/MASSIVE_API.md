# Massive API Reference (formerly Polygon.io)

Reference documentation for the Massive REST API as used in FinAlly. Massive is the rebrand of Polygon.io — `polygon.io` URLs now 301-redirect to `massive.com`, and the Python SDK has moved from the `polygon-api-client` package to the `massive` package.

## At a Glance

| | 
|---|---|
| **Docs site** | `https://massive.com/docs` |
| **Base URL** | `https://api.massive.com` (legacy `https://api.polygon.io` still works) |
| **Python package** | [`massive`](https://pypi.org/project/massive/) — current version 2.x, Python 3.9+ |
| **Repo** | `github.com/massive-com/client-python` |
| **Auth** | API key via `MASSIVE_API_KEY` env var, or `RESTClient(api_key=...)` |
| **Auth header** | `Authorization: Bearer <API_KEY>` (the client sets this automatically) |
| **Sync vs async** | The `RESTClient` is **synchronous** — wrap calls in `asyncio.to_thread()` from async code |

## Rate Limits

| Tier | Limit | Poll cadence in FinAlly |
|------|-------|--------------------------|
| Free | 5 requests/minute | Every 15s (default) |
| Starter / paid | Effectively unlimited | Every 2–5s |

The free-tier limit is the hard constraint that drives the design: we use the **snapshot-all-tickers** endpoint so the union of every watched ticker is fetched in one call, no matter how many tickers there are. Polling cadence is the only knob we turn.

## Installation

```bash
uv add massive
# or
pip install -U massive
```

## Client Initialization

```python
from massive import RESTClient

# Reads MASSIVE_API_KEY from environment automatically
client = RESTClient()

# Or pass the key explicitly
client = RESTClient(api_key="your_key_here")
```

The client is a thin wrapper around `requests`. It blocks the calling thread on each call. In an asyncio app, dispatch via `asyncio.to_thread(...)` so the event loop is never blocked (see [Async Integration](#async-integration)).

---

## Endpoints Used in FinAlly

### 1. Snapshot — All Tickers *(primary endpoint)*

This is the workhorse. One call returns current prices for every ticker we ask about, which means rate-limit usage is constant in the number of tickers — only the poll cadence scales.

**REST**
```
GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,GOOGL,MSFT
```

**Python**
```python
from massive import RESTClient
from massive.rest.models import SnapshotMarketType

client = RESTClient()

snapshots = client.get_snapshot_all(
    market_type=SnapshotMarketType.STOCKS,
    tickers=["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"],
)

for snap in snapshots:
    print(f"{snap.ticker}: ${snap.last_trade.price}")
    print(f"  Day change: {snap.day.change_percent}%")
    print(f"  OHLC: O={snap.day.open} H={snap.day.high} L={snap.day.low} C={snap.day.close}")
```

**Raw response shape** (per ticker — fields used by FinAlly highlighted):

```json
{
  "ticker": "AAPL",
  "day": {
    "o": 129.61, "h": 130.15, "l": 125.07, "c": 125.07,
    "v": 111237700, "vw": 127.35
  },
  "prevDay": {
    "o": 130.50, "h": 131.20, "l": 129.10, "c": 129.61, "v": 80123000
  },
  "lastTrade": {
    "p": 125.07,                  // ← price
    "s": 100,                     // ← size
    "x": 4,                       // ← exchange code
    "t": 1605192894630916600      // ← timestamp (nanoseconds)
  },
  "lastQuote": {
    "p": 125.06, "P": 125.08,     // bid / ask
    "s": 500,   "S": 1000,
    "t": 1605192959994246100
  },
  "todaysChange": -0.124,
  "todaysChangePerc": -0.601,
  "updated": 1605192894630916600  // nanoseconds since epoch
}
```

> **Timestamp units.** The raw v2 endpoint returns **nanoseconds** since the Unix epoch. The `massive` SDK exposes attributes (`snap.last_trade.timestamp`) that **normalize this to milliseconds**, matching the older Polygon-SDK behavior — so the FinAlly client divides by 1000 to land in seconds. If you ever call the raw REST endpoint directly, divide by 1_000_000_000 instead.

**Fields FinAlly reads from each snapshot:**

| Attribute on SDK object | Raw JSON key | Used for |
|---|---|---|
| `snap.ticker` | `ticker` | Cache key |
| `snap.last_trade.price` | `lastTrade.p` | Current price (trade + UI display) |
| `snap.last_trade.timestamp` | `lastTrade.t` | Event time (divide by 1000 → seconds) |

Everything else (`day.*`, `lastQuote.*`, OHLC, todaysChange) is currently unused but worth knowing if we extend the dashboard.

### 2. Snapshot — Single Ticker

For drilling into one ticker (e.g., a detail panel that wants quote-level data).

```python
snapshot = client.get_snapshot_ticker(
    market_type=SnapshotMarketType.STOCKS,
    ticker="AAPL",
)

print(f"Price: ${snapshot.last_trade.price}")
print(f"Bid/Ask: ${snapshot.last_quote.bid_price} / ${snapshot.last_quote.ask_price}")
print(f"Day range: ${snapshot.day.low} - ${snapshot.day.high}")
```

### 3. Previous Close

Previous trading day's OHLC. Useful for seeding starting prices when bootstrapping a new instance against real data.

**REST**: `GET /v2/aggs/ticker/{ticker}/prev`

```python
prev = client.get_previous_close_agg(ticker="AAPL")
for agg in prev:
    print(f"Prev close: ${agg.close} | OHLC O={agg.open} H={agg.high} L={agg.low}")
```

### 4. Aggregates (historical bars)

Not used by the live poller, but the natural choice if we add a historical chart on the detail view.

**REST**: `GET /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}`

```python
aggs = list(client.list_aggs(
    ticker="AAPL",
    multiplier=1,
    timespan="day",
    from_="2026-01-01",
    to="2026-05-15",
    limit=50000,
))

for a in aggs:
    print(f"{a.timestamp}: O={a.open} H={a.high} L={a.low} C={a.close} V={a.volume}")
```

`timespan` accepts `minute`, `hour`, `day`, `week`, `month`, `quarter`, `year`.

### 5. Newer v3 Unified Snapshot *(not currently used)*

Massive also exposes a newer v3 endpoint that supports stocks, options, forex, and crypto in a single call, with a different (snake_case, deeper) response schema.

```
GET /v3/snapshot?ticker.any_of=AAPL,GOOGL,MSFT&type=stocks
```

Limits: up to **250 tickers per request** via `ticker.any_of`. Fields are `last_trade`, `last_quote`, `session` (rather than `day`), and `fmv` (Business-plan only).

We stick with the v2 stock endpoint because it's well-supported, returns the exact shape we already parse, and v3 buys us nothing for stocks-only polling.

---

## How FinAlly Uses the API

The `MassiveDataSource` class (`backend/app/market/massive_client.py`) wraps the SDK in an async polling loop:

1. **Start** — record the ticker set, perform an immediate first poll so the price cache is populated before SSE clients connect, then schedule a background task.
2. **Poll loop** — every `poll_interval` seconds (default 15s for free tier):
   1. Call `client.get_snapshot_all(market_type=STOCKS, tickers=...)` via `asyncio.to_thread()`.
   2. For each returned snapshot, extract `ticker`, `last_trade.price`, and `last_trade.timestamp / 1000`.
   3. Write each price into the shared `PriceCache`. The cache bumps its version counter, which is what the SSE endpoint watches for change detection.
3. **Add/remove ticker** — mutate the in-memory ticker list. Additions appear on the next poll; removals also evict the cache entry immediately.
4. **Stop** — cancel the task and drop the client.

Errors are caught at the loop level and logged but never re-raised — the loop must survive transient failures (rate-limit blips, network errors) and try again on the next interval.

### Distilled implementation

```python
import asyncio, logging
from massive import RESTClient
from massive.rest.models import SnapshotMarketType

logger = logging.getLogger(__name__)

class MassivePoller:
    def __init__(self, api_key: str, cache, interval: float = 15.0):
        self._client = RESTClient(api_key=api_key)
        self._cache = cache
        self._interval = interval
        self._tickers: list[str] = []
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        self._tickers = list(tickers)
        await self._poll_once()  # warm the cache before clients connect
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self._poll_once()

    async def _poll_once(self) -> None:
        if not self._tickers:
            return
        try:
            snapshots = await asyncio.to_thread(
                self._client.get_snapshot_all,
                market_type=SnapshotMarketType.STOCKS,
                tickers=self._tickers,
            )
            for snap in snapshots:
                self._cache.update(
                    ticker=snap.ticker,
                    price=snap.last_trade.price,
                    timestamp=snap.last_trade.timestamp / 1000.0,
                )
        except Exception:
            logger.exception("Massive poll failed")  # keep looping
```

## Async Integration

The `massive` `RESTClient` is synchronous and uses blocking I/O. **Never await it directly** — wrap in `asyncio.to_thread()`:

```python
snapshots = await asyncio.to_thread(
    client.get_snapshot_all,
    market_type=SnapshotMarketType.STOCKS,
    tickers=tickers,
)
```

`asyncio.to_thread` schedules the synchronous call on the default thread pool executor, which is fine for a small handful of concurrent requests. We only have one poller, so contention is a non-issue.

## Error Handling

Common HTTP errors raised as exceptions by the client:

| Status | Meaning | FinAlly behavior |
|---|---|---|
| 401 | Invalid API key | Log, keep looping (so a key fix is picked up on restart only) |
| 403 | Plan doesn't include endpoint | Log; treat the source as effectively dead until restart |
| 429 | Rate limit exceeded | Log; the next interval gives the budget time to refill |
| 5xx | Server error | Log; the client retries internally (up to 3 by default), and we retry on the next tick |
| Network / DNS | Connection error | Log and retry on the next interval |

The poll loop catches `Exception` broadly because we always want the loop to survive — an unrecoverable error in one tick should not take the data source down for the lifetime of the process.

## Behavior Around Market Hours

- During regular hours: `last_trade` updates on real trades; `day` aggregates fill in throughout the session.
- Pre/post market: `last_trade` may reflect after-hours trades depending on plan/permissions.
- Closed: `last_trade` is the last print of the previous session. `day` resets at market open.
- Massive resets snapshot data daily at **12:00 AM EST**; new data begins repopulating as early as **4:00 AM EST**.

For FinAlly this is fine — we display whatever the API returns. Cold-start without a successful poll falls back to position `avg_cost` (see PLAN.md §7), so the portfolio total is always finite even outside market hours.

## Unknown / Invalid Tickers

Massive accepts unknown tickers without error — it simply returns no snapshot for them. The cache therefore never gets an entry, and the frontend shows the row with no price (`—`). This is deliberate: it lets the watchlist/LLM optimistically add anything without us needing a separate validation roundtrip.

## Notes for Operators

- The snapshot endpoint counts as **one API call per poll** no matter how many tickers we request — this is what makes free-tier 5 req/min sustainable indefinitely.
- Timestamps from `snap.last_trade.timestamp` are **milliseconds** in the SDK (the raw API uses nanoseconds — the SDK normalizes).
- The `tickers` query param is **case-sensitive**; always uppercase before sending. The `MassiveDataSource` uppercases on `add_ticker`.
- Free tier covers stocks but not all asset classes — stick to `SnapshotMarketType.STOCKS`.

## Sources

- [Unified Snapshot | Stocks REST API — Massive](https://massive.com/docs/rest/stocks/snapshots/unified-snapshot)
- [Full Market Snapshot | Stocks REST API — Massive](https://massive.com/docs/rest/stocks/snapshots/full-market-snapshot)
- [`massive` on PyPI](https://pypi.org/project/massive/)
- [Polygon Python client docs (legacy)](https://polygon.readthedocs.io/en/latest/Stocks.html)
