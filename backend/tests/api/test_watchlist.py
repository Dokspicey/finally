"""Tests for /api/watchlist CRUD + tracked-ticker sync."""

from __future__ import annotations

import pytest

from app.api import add_watchlist_ticker, remove_watchlist_ticker
from app.db import DEFAULT_WATCHLIST, upsert_position


def test_watchlist_lists_seeded_tickers(api_client):
    body = api_client.get("/api/watchlist").json()
    tickers = {row["ticker"] for row in body["watchlist"]}
    assert tickers == set(DEFAULT_WATCHLIST)


def test_watchlist_row_has_price_block(api_client, fake_source):
    fake_source.seed_price("AAPL", 200.0)
    body = api_client.get("/api/watchlist").json()
    aapl = next(r for r in body["watchlist"] if r["ticker"] == "AAPL")
    assert aapl["price"] == 200.0
    assert aapl["direction"] == "flat"  # first update -> previous == current


def test_watchlist_row_with_missing_price_returns_null_block(api_client):
    """Tickers with no cache entry render with null price fields."""
    body = api_client.get("/api/watchlist").json()
    aapl = next(r for r in body["watchlist"] if r["ticker"] == "AAPL")
    assert aapl["price"] is None
    assert aapl["previous_price"] is None


def test_add_ticker_persists_and_tracks(api_client, fake_source):
    resp = api_client.post("/api/watchlist", json={"ticker": "pypl"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["ticker"] == "PYPL"
    assert "added_at" in body

    listed = {r["ticker"] for r in api_client.get("/api/watchlist").json()["watchlist"]}
    assert "PYPL" in listed
    assert "PYPL" in fake_source.tickers


def test_add_existing_ticker_is_idempotent(api_client):
    resp = api_client.post("/api/watchlist", json={"ticker": "AAPL"})
    assert resp.status_code == 201
    assert resp.json()["ticker"] == "AAPL"


def test_add_invalid_ticker_returns_400(api_client):
    resp = api_client.post("/api/watchlist", json={"ticker": "  "})
    assert resp.status_code == 400
    assert resp.json()["detail"] in {"ticker required", "invalid ticker"}


def test_remove_existing_ticker(api_client, fake_source):
    # Pre-populate so the fake source has AAPL tracked.
    fake_source.seed_price("AAPL", 100.0)
    # Bring it into the tracked set the way the lifespan would.
    import asyncio

    asyncio.get_event_loop().run_until_complete(fake_source.add_ticker("AAPL")) if False else None

    resp = api_client.delete("/api/watchlist/AAPL")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "AAPL"
    assert body["removed"] is True

    listed = {r["ticker"] for r in api_client.get("/api/watchlist").json()["watchlist"]}
    assert "AAPL" not in listed


def test_remove_missing_ticker_returns_removed_false(api_client):
    resp = api_client.delete("/api/watchlist/ZZZZ")
    assert resp.status_code == 200
    assert resp.json() == {"ticker": "ZZZZ", "removed": False}


def test_remove_normalizes_lowercase(api_client):
    resp = api_client.delete("/api/watchlist/aapl")
    assert resp.status_code == 200
    assert resp.json()["ticker"] == "AAPL"
    assert resp.json()["removed"] is True


def test_remove_keeps_ticker_tracked_when_position_held(api_client, fake_source):
    """Held positions keep the ticker tracked even after watchlist removal."""
    fake_source.seed_price("AAPL", 100.0)
    upsert_position("AAPL", 1.0, 100.0)
    # Force AAPL into the fake source's tracked set.
    fake_source.tickers.append("AAPL") if "AAPL" not in fake_source.tickers else None

    resp = api_client.delete("/api/watchlist/AAPL")
    assert resp.status_code == 200
    assert resp.json()["removed"] is True
    assert "AAPL" in fake_source.tickers  # still held -> still tracked


def test_remove_untracks_when_no_position(api_client, fake_source):
    fake_source.seed_price("AAPL", 100.0)
    fake_source.tickers.append("AAPL") if "AAPL" not in fake_source.tickers else None

    api_client.delete("/api/watchlist/AAPL")
    assert "AAPL" not in fake_source.tickers


# --- direct coroutine imports — used by llm-engineer's chat layer ---


@pytest.mark.asyncio
async def test_add_watchlist_ticker_callable_directly(api_client, fake_source):
    result = await add_watchlist_ticker("pypl")
    assert result["ticker"] == "PYPL"
    assert "added_at" in result
    assert "PYPL" in fake_source.tickers


@pytest.mark.asyncio
async def test_add_watchlist_ticker_invalid_raises_value_error(api_client):
    with pytest.raises(ValueError):
        await add_watchlist_ticker("  ")


@pytest.mark.asyncio
async def test_remove_watchlist_ticker_callable_directly(api_client, fake_source):
    fake_source.tickers.append("AAPL") if "AAPL" not in fake_source.tickers else None
    result = await remove_watchlist_ticker("aapl")
    assert result == {"ticker": "AAPL", "removed": True}
    assert "AAPL" not in fake_source.tickers


@pytest.mark.asyncio
async def test_remove_watchlist_ticker_invalid_raises_value_error(api_client):
    with pytest.raises(ValueError):
        await remove_watchlist_ticker("")
