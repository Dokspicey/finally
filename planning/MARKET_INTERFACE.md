# Market Data Interface

Unified Python interface for live prices in FinAlly. Two implementations sit behind one abstract base class — a GBM simulator (default) and a Massive REST poller (when `MASSIVE_API_KEY` is set). Everything downstream of the interface — SSE streaming, portfolio valuation, trade execution — is source-agnostic.

## Design Goal

The application should not know or care whether a price came from a simulator or a real API. It should:

1. Ask for prices from a single, in-memory cache.
2. Trust that whatever is in the cache is the freshest value available.
3. Have one stable shape (`PriceUpdate`) to render and serialize.

Everything below serves that goal.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Producer (exactly one running at a time)           │
│                                                     │
│  SimulatorDataSource  ──┐                           │
│                         ├──→  writes  ──┐           │
│  MassiveDataSource    ──┘               ▼           │
│                                  ┌─────────────┐    │
│                                  │ PriceCache  │    │
│                                  │ (in-memory) │    │
│                                  └──────┬──────┘    │
│                                         │           │
│                            reads ◄──────┤           │
│                                         │           │
│   Consumers (many, decoupled):          ▼           │
│     • SSE /api/stream/prices                        │
│     • Portfolio valuation                           │
│     • Trade execution (current-price lookup)        │
└─────────────────────────────────────────────────────┘
```

- **Producers push, consumers pull.** The data source writes to the cache on its own schedule; nothing reads from the source directly.
- **The cache is the only shared state.** It is thread-safe and keeps a monotonic `version` counter so SSE can do cheap change detection without diffing dicts.
- **One source is active at a time** — selected at startup by a factory that reads the environment.

This is a textbook Strategy + Observer pattern, applied so the AI-coding-course audience can see both clearly.

---

## Core Data Model

`PriceUpdate` is the *only* shape that leaves the market layer. Everything else is implementation detail.

```python
from dataclasses import dataclass, field
import time

@dataclass(frozen=True, slots=True)
class PriceUpdate:
    ticker: str
    price: float
    previous_price: float
    timestamp: float = field(default_factory=time.time)  # Unix seconds

    @property
    def change(self) -> float:
        return round(self.price - self.previous_price, 4)

    @property
    def change_percent(self) -> float:
        if self.previous_price == 0:
            return 0.0
        return round((self.price - self.previous_price) / self.previous_price * 100, 4)

    @property
    def direction(self) -> str:
        if self.price > self.previous_price: return "up"
        if self.price < self.previous_price: return "down"
        return "flat"

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "price": self.price,
            "previous_price": self.previous_price,
            "timestamp": self.timestamp,
            "change": self.change,
            "change_percent": self.change_percent,
            "direction": self.direction,
        }
```

**Why frozen + slots?**
- `frozen=True` — updates are immutable. Once published, they can't be tampered with by a reader.
- `slots=True` — tighter memory layout; meaningful when we push hundreds of these per second through SSE.
- Derived fields (`change`, `direction`, `change_percent`) live as `@property` so they can't drift out of sync with `price`/`previous_price`.

`to_dict()` is the canonical JSON shape sent to the frontend over SSE. Every consumer that serializes a `PriceUpdate` uses this method.

---

## Abstract Interface

```python
from abc import ABC, abstractmethod

class MarketDataSource(ABC):
    """Contract for market data providers.

    Implementations push price updates into a shared PriceCache on their own
    schedule. Downstream code never calls the data source directly for prices —
    it reads from the cache.
    """

    @abstractmethod
    async def start(self, tickers: list[str]) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None: ...

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None: ...

    @abstractmethod
    def get_tickers(self) -> list[str]: ...
```

**Lifecycle**

```
create_market_data_source(cache)
       │
       ▼
   start(tickers)        ← seeds cache, launches background task
       │
       ├── add_ticker(t)
       ├── remove_ticker(t)
       │
       ▼
   stop()                ← cancels task, releases resources (idempotent)
```

**Contract notes**

- `start()` must be called **exactly once** per source. Calling it twice is undefined.
- `stop()` is **idempotent** — calling it twice is a no-op the second time.
- `add_ticker()` / `remove_ticker()` are no-ops if the ticker is already present / absent.
- `get_tickers()` is **sync** — it's a cheap snapshot of internal state used by health checks and the watchlist API. Everything else is async because the underlying work (sim step, API poll) is async.
- Implementations are responsible for **seeding the cache immediately** on `start()` (and on `add_ticker()`, where feasible). SSE clients connecting just after startup must see prices on first frame — they should never see an empty initial snapshot.

---

## PriceCache

A thread-safe in-memory store. One writer (the active data source), many readers. The cache is intentionally tiny — fewer than 100 lines — because it has one job.

```python
import time
from threading import Lock
from .models import PriceUpdate

class PriceCache:
    def __init__(self) -> None:
        self._prices: dict[str, PriceUpdate] = {}
        self._lock = Lock()
        self._version: int = 0  # Monotonic; bumped on every update

    def update(self, ticker: str, price: float,
               timestamp: float | None = None) -> PriceUpdate:
        with self._lock:
            ts = timestamp or time.time()
            prev = self._prices.get(ticker)
            previous_price = prev.price if prev else price
            update = PriceUpdate(
                ticker=ticker,
                price=round(price, 2),
                previous_price=round(previous_price, 2),
                timestamp=ts,
            )
            self._prices[ticker] = update
            self._version += 1
            return update

    def get(self, ticker: str) -> PriceUpdate | None:
        with self._lock:
            return self._prices.get(ticker)

    def get_price(self, ticker: str) -> float | None:
        u = self.get(ticker)
        return u.price if u else None

    def get_all(self) -> dict[str, PriceUpdate]:
        with self._lock:
            return dict(self._prices)  # shallow copy

    def remove(self, ticker: str) -> None:
        with self._lock:
            self._prices.pop(ticker, None)

    @property
    def version(self) -> int:
        return self._version
```

**Design notes**

- `threading.Lock` (not `asyncio.Lock`) because the simulator's step is called from sync code paths and the Massive poll runs in a thread. A regular lock is the lowest-common-denominator that works from both.
- The `version` counter is what makes SSE efficient — the streamer remembers the version it last sent and only emits new frames when `version` advances. No deep equality check, no diff.
- `update()` writes `previous_price` from whatever the cache already held — so a ticker's first-ever update has `previous_price == price` and `direction == "flat"`. There's no special "first update" branching for consumers.
- Prices are rounded to 2 decimals before storage. This keeps wire-level diffs deterministic and stops sub-cent noise from registering as "changes" in the UI.
- `get_all()` returns a copy so iteration outside the lock is safe.

**Fallback for portfolio valuation.** If a held ticker has no cache entry (cold start, API outage), portfolio code falls back to `position.avg_cost`. That logic lives in the portfolio layer, not the cache — the cache itself just returns `None`. See PLAN.md §7.

---

## Factory

```python
import os
import logging
from .cache import PriceCache
from .interface import MarketDataSource
from .massive_client import MassiveDataSource
from .simulator import SimulatorDataSource

logger = logging.getLogger(__name__)

def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if api_key:
        logger.info("Market data source: Massive API (real data)")
        return MassiveDataSource(api_key=api_key, price_cache=price_cache)
    logger.info("Market data source: GBM Simulator")
    return SimulatorDataSource(price_cache=price_cache)
```

Returns an **unstarted** source. The caller must `await source.start(tickers)`. This keeps construction cheap and side-effect-free, which is nice for tests.

---

## Implementation: SimulatorDataSource

Wraps a `GBMSimulator` (see `MARKET_SIMULATOR.md`) in an asyncio loop that ticks every 500ms.

```python
import asyncio, logging
from .cache import PriceCache
from .interface import MarketDataSource

logger = logging.getLogger(__name__)

class SimulatorDataSource(MarketDataSource):
    def __init__(self, price_cache: PriceCache,
                 update_interval: float = 0.5,
                 event_probability: float = 0.001) -> None:
        self._cache = price_cache
        self._interval = update_interval
        self._event_prob = event_probability
        self._sim: GBMSimulator | None = None
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        self._sim = GBMSimulator(tickers=tickers, event_probability=self._event_prob)
        # Seed cache so SSE has data on first frame
        for ticker in tickers:
            price = self._sim.get_price(ticker)
            if price is not None:
                self._cache.update(ticker=ticker, price=price)
        self._task = asyncio.create_task(self._run_loop(), name="simulator-loop")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass
        self._task = None

    async def add_ticker(self, ticker: str) -> None:
        if self._sim:
            self._sim.add_ticker(ticker)
            price = self._sim.get_price(ticker)
            if price is not None:
                self._cache.update(ticker=ticker, price=price)  # seed immediately

    async def remove_ticker(self, ticker: str) -> None:
        if self._sim:
            self._sim.remove_ticker(ticker)
        self._cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return self._sim.get_tickers() if self._sim else []

    async def _run_loop(self) -> None:
        while True:
            try:
                if self._sim:
                    for ticker, price in self._sim.step().items():
                        self._cache.update(ticker=ticker, price=price)
            except Exception:
                logger.exception("Simulator step failed")
            await asyncio.sleep(self._interval)
```

Key behaviors:
- Cache is **seeded synchronously** in `start()` and on `add_ticker()` — SSE clients never see an empty snapshot.
- The loop catches `Exception` so a single bad step can't kill the source.
- Cancellation is clean via `asyncio.CancelledError`.

---

## Implementation: MassiveDataSource

Wraps the (synchronous) `massive` REST client in an asyncio polling loop. Full detail in `MASSIVE_API.md`; sketch here for symmetry.

```python
import asyncio, logging
from massive import RESTClient
from massive.rest.models import SnapshotMarketType
from .cache import PriceCache
from .interface import MarketDataSource

logger = logging.getLogger(__name__)

class MassiveDataSource(MarketDataSource):
    def __init__(self, api_key: str, price_cache: PriceCache,
                 poll_interval: float = 15.0) -> None:
        self._api_key = api_key
        self._cache = price_cache
        self._interval = poll_interval
        self._tickers: list[str] = []
        self._task: asyncio.Task | None = None
        self._client: RESTClient | None = None

    async def start(self, tickers: list[str]) -> None:
        self._client = RESTClient(api_key=self._api_key)
        self._tickers = list(tickers)
        await self._poll_once()  # warm cache before SSE clients connect
        self._task = asyncio.create_task(self._poll_loop(), name="massive-poller")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass
        self._task = None
        self._client = None

    async def add_ticker(self, ticker: str) -> None:
        ticker = ticker.upper().strip()
        if ticker not in self._tickers:
            self._tickers.append(ticker)
        # Picked up on next poll; no immediate API call to avoid rate budget hit

    async def remove_ticker(self, ticker: str) -> None:
        ticker = ticker.upper().strip()
        self._tickers = [t for t in self._tickers if t != ticker]
        self._cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            await self._poll_once()

    async def _poll_once(self) -> None:
        if not self._tickers or not self._client:
            return
        try:
            snapshots = await asyncio.to_thread(
                self._client.get_snapshot_all,
                market_type=SnapshotMarketType.STOCKS,
                tickers=self._tickers,
            )
            for snap in snapshots:
                try:
                    self._cache.update(
                        ticker=snap.ticker,
                        price=snap.last_trade.price,
                        timestamp=snap.last_trade.timestamp / 1000.0,  # ms→s
                    )
                except (AttributeError, TypeError) as e:
                    logger.warning("Bad snapshot for %s: %s",
                                   getattr(snap, "ticker", "???"), e)
        except Exception as e:
            logger.error("Massive poll failed: %s", e)  # keep looping
```

Notable differences from the simulator:
- **Synchronous client** dispatched via `asyncio.to_thread()` so the event loop is never blocked.
- **Add doesn't trigger an immediate poll** — that would punch a hole in the rate budget every time the LLM adds a ticker. The ticker shows up on the next regular tick (≤15s on free tier).
- **Per-snapshot try/except** so one malformed entry doesn't drop the rest of the batch.

---

## SSE Integration

The SSE endpoint reads from `PriceCache`. The cache's `version` counter drives change detection — the streamer remembers the version it last sent and only emits when it advances. The endpoint factory is exposed as `create_stream_router(cache)`.

```python
async def _generate_events(cache: PriceCache) -> AsyncGenerator[str, None]:
    # Initial snapshot: every ticker, immediately, so the UI populates
    for u in cache.get_all().values():
        yield f"data: {json.dumps(u.to_dict())}\n\n"

    last_version = cache.version
    while True:
        if cache.version != last_version:
            # Diff: emit only changed tickers since last_version
            ...
            last_version = cache.version
        await asyncio.sleep(0.05)  # 20Hz polling against cache (cheap)
```

The full implementation handles per-ticker version tracking so we only emit the tickers that actually changed since the last frame, not the whole snapshot.

---

## File Layout

```
backend/app/market/
  __init__.py
  models.py          # PriceUpdate
  interface.py       # MarketDataSource ABC
  cache.py           # PriceCache
  factory.py         # create_market_data_source()
  simulator.py       # GBMSimulator + SimulatorDataSource
  massive_client.py  # MassiveDataSource
  seed_prices.py     # Seed prices, per-ticker params, correlation groups
  stream.py          # SSE router factory
```

## Public Imports

Downstream code only ever imports from the package root:

```python
from app.market import (
    PriceCache,
    PriceUpdate,
    MarketDataSource,
    create_market_data_source,
    create_stream_router,
)
```

Anything else is internal.

## End-to-End Usage

```python
# App startup
cache = PriceCache()
source = create_market_data_source(cache)
await source.start(["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
                    "NVDA", "META", "JPM", "V", "NFLX"])

# Reads (from anywhere)
update = cache.get("AAPL")          # PriceUpdate | None
price  = cache.get_price("AAPL")    # float | None
snap   = cache.get_all()            # dict[str, PriceUpdate]

# Watchlist mutations
await source.add_ticker("TSLA")
await source.remove_ticker("GOOGL")

# Mount the SSE router
app.include_router(create_stream_router(cache), prefix="/api")

# Shutdown
await source.stop()
```

## Testing Strategy

| Test target | What to verify |
|---|---|
| `PriceUpdate` | Properties compute correctly, edge case `previous_price == 0`, `to_dict()` shape |
| `PriceCache` | Concurrent updates from threads, version monotonicity, `remove()`, snapshot isolation |
| `SimulatorDataSource` | Start/stop lifecycle, ticker add/remove triggers cache writes, loop survives exceptions |
| `MassiveDataSource` | Same as above, with the SDK call mocked — verify `asyncio.to_thread` dispatch and error swallowing |
| `factory` | Env var present ↔ Massive, absent/blank ↔ simulator |

Both implementations should be exercised through the same abstract contract — write the cache, expose the same lifecycle — so a single conformance test suite can run against either.
