"""Shared fixtures for API route tests.

Each test gets:
- A fresh temp-file SQLite DB (`FINALLY_DB_PATH` + path-cache reset)
- A fake `MarketDataSource` so we can assert tracked-ticker mutations and seed prices
- A FastAPI `TestClient` bound to a route-only app (no real simulator)

The fake market source matches the `MarketDataSource` contract but never spawns
background tasks. Tests can inspect `fake_source.tickers` and call
`fake_source.seed_price(...)` to drive deterministic fills.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import (
    portfolio_router,
    set_app_state,
    trades_router,
    watchlist_router,
)
from app.api import trades as trades_module
from app.db.connection import reset_db_path_cache
from app.market import PriceCache, create_stream_router


class FakeMarketSource:
    """In-memory MarketDataSource stand-in for tests."""

    def __init__(self, cache: PriceCache) -> None:
        self._cache = cache
        self.tickers: list[str] = []
        self._seed_prices: dict[str, float] = {}

    async def start(self, tickers: list[str]) -> None:
        for t in tickers:
            await self.add_ticker(t)

    async def stop(self) -> None:
        return None

    async def add_ticker(self, ticker: str) -> None:
        if ticker not in self.tickers:
            self.tickers.append(ticker)
        seed = self._seed_prices.get(ticker)
        if seed is not None:
            self._cache.update(ticker, seed)

    async def remove_ticker(self, ticker: str) -> None:
        if ticker in self.tickers:
            self.tickers.remove(ticker)
        self._cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return list(self.tickers)

    # Test-only helpers
    def seed_price(self, ticker: str, price: float) -> None:
        self._seed_prices[ticker] = price
        self._cache.update(ticker, price)


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "test_finally.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(path))
    reset_db_path_cache()
    yield path
    reset_db_path_cache()


@pytest.fixture
def price_cache() -> PriceCache:
    return PriceCache()


@pytest.fixture
def fake_source(price_cache: PriceCache) -> FakeMarketSource:
    return FakeMarketSource(price_cache)


def _swap_trade_lock() -> asyncio.Lock:
    """Replace the module-level trade lock with a fresh one.

    asyncio.Lock binds to the event loop on first await. TestClient spins up a
    new loop per test, so we reset the lock between tests to avoid the
    'bound to a different loop' RuntimeError.
    """
    new_lock = asyncio.Lock()
    trades_module._TRADE_LOCK = new_lock
    return new_lock


@pytest.fixture
def api_client(db_path, price_cache, fake_source):
    """TestClient bound to a route-only app. No real simulator runs."""
    _swap_trade_lock()
    set_app_state(price_cache, fake_source)

    app = FastAPI()
    app.state.price_cache = price_cache
    app.include_router(create_stream_router(price_cache))
    app.include_router(portfolio_router)
    app.include_router(trades_router)
    app.include_router(watchlist_router)

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    # Trigger lazy DB init (seeds default user + watchlist).
    from app.db import get_db

    conn = get_db()
    conn.close()

    with TestClient(app) as tc:
        yield tc

    set_app_state(None, None)
