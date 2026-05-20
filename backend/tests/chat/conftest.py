"""Shared fixtures for /api/chat tests.

Mirrors `tests/api/conftest.py`:
- temp-file SQLite DB
- fake market source
- TestClient bound to a route-only FastAPI app

Adds the chat router on top so the chat endpoints are exercised end-to-end.
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


@pytest.fixture(autouse=True)
def _wire_state(price_cache, fake_source):
    """Every test gets the trade module wired with our cache + fake source."""
    _swap_trade_lock()
    set_app_state(price_cache, fake_source)
    yield
    set_app_state(None, None)


def _swap_trade_lock() -> asyncio.Lock:
    new_lock = asyncio.Lock()
    trades_module._TRADE_LOCK = new_lock
    return new_lock


@pytest.fixture
def llm_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default: tests run with LLM_MOCK=true. Individual tests can override."""
    monkeypatch.setenv("LLM_MOCK", "true")


@pytest.fixture
def chat_client(db_path, price_cache, fake_source, llm_mock):
    """TestClient with the full backend wired and chat router mounted."""
    from app.chat import chat_router  # imported here so test failures surface clearly

    _swap_trade_lock()
    set_app_state(price_cache, fake_source)

    app = FastAPI()
    app.state.price_cache = price_cache
    app.include_router(create_stream_router(price_cache))
    app.include_router(portfolio_router)
    app.include_router(trades_router)
    app.include_router(watchlist_router)
    app.include_router(chat_router)

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    from app.db import get_db

    conn = get_db()
    conn.close()

    with TestClient(app) as tc:
        yield tc

    set_app_state(None, None)
