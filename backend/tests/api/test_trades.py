"""Tests for /api/portfolio/trade and /api/trades."""

from __future__ import annotations

import asyncio

import pytest

from app.api import TradeError, execute_trade
from app.db import get_portfolio_history, get_positions, get_trades, get_user_profile

# --- /api/portfolio/trade — REST surface ---


def test_buy_succeeds_and_updates_cash_position(api_client, fake_source):
    fake_source.seed_price("AAPL", 100.0)
    resp = api_client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "buy", "quantity": 2},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["cash_balance"] == 10000.0 - 200.0
    assert body["position"]["ticker"] == "AAPL"
    assert body["position"]["quantity"] == 2.0
    assert body["position"]["avg_cost"] == 100.0
    assert body["trade"]["ticker"] == "AAPL"
    assert body["trade"]["side"] == "buy"
    assert body["trade"]["quantity"] == 2.0
    assert body["trade"]["price"] == 100.0
    assert "id" in body["trade"]
    assert "executed_at" in body["trade"]

    # Position persisted in DB
    positions = get_positions()
    assert len(positions) == 1
    assert positions[0]["ticker"] == "AAPL"

    # Cash persisted
    profile = get_user_profile()
    assert profile["cash_balance"] == 10000.0 - 200.0


def test_buy_normalizes_lowercase_ticker_and_side(api_client, fake_source):
    fake_source.seed_price("AAPL", 50.0)
    resp = api_client.post(
        "/api/portfolio/trade",
        json={"ticker": "aapl", "side": "BUY", "quantity": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["trade"]["ticker"] == "AAPL"
    assert body["trade"]["side"] == "buy"


def test_buy_fractional_shares_supported(api_client, fake_source):
    fake_source.seed_price("AAPL", 100.0)
    resp = api_client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "buy", "quantity": 0.5},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["position"]["quantity"] == 0.5
    assert body["cash_balance"] == 10000.0 - 50.0


def test_buy_insufficient_cash_returns_400(api_client, fake_source):
    fake_source.seed_price("AAPL", 100000.0)  # too expensive
    resp = api_client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "buy", "quantity": 1},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "insufficient cash"

    # No mutations leaked
    assert get_user_profile()["cash_balance"] == 10000.0
    assert get_positions() == []


def test_buy_unknown_ticker_with_no_quote_rejected(api_client):
    """Buying a ticker with no price in cache returns 'no price available'."""
    resp = api_client.post(
        "/api/portfolio/trade",
        json={"ticker": "NOQUOTE", "side": "buy", "quantity": 1},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "no price available"


def test_sell_existing_position_updates_cash_and_qty(api_client, fake_source):
    fake_source.seed_price("AAPL", 100.0)
    api_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 2})

    fake_source.seed_price("AAPL", 150.0)
    resp = api_client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "sell", "quantity": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cash_balance"] == 10000.0 - 200.0 + 150.0
    assert body["position"]["quantity"] == 1.0
    # avg_cost is unchanged on sells
    assert body["position"]["avg_cost"] == 100.0


def test_sell_full_quantity_deletes_position(api_client, fake_source):
    fake_source.seed_price("AAPL", 100.0)
    api_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 1})

    resp = api_client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "sell", "quantity": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["position"] is None
    assert get_positions() == []


def test_sell_more_than_owned_returns_400(api_client, fake_source):
    fake_source.seed_price("AAPL", 100.0)
    api_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 1})

    resp = api_client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "sell", "quantity": 5},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "insufficient shares"


def test_sell_with_no_position_returns_400(api_client, fake_source):
    fake_source.seed_price("AAPL", 100.0)
    resp = api_client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "sell", "quantity": 1},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "insufficient shares"


def test_unknown_side_returns_400(api_client, fake_source):
    fake_source.seed_price("AAPL", 100.0)
    resp = api_client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "swap", "quantity": 1},
    )
    # Pydantic accepts the string; our validator rejects it -> 400
    assert resp.status_code == 400
    assert resp.json()["detail"] == "unknown side"


def test_zero_quantity_rejected_by_pydantic(api_client, fake_source):
    fake_source.seed_price("AAPL", 100.0)
    resp = api_client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "buy", "quantity": 0},
    )
    assert resp.status_code == 422  # FastAPI validation


# --- /api/trades — history ---


def test_trades_list_returns_newest_first(api_client, fake_source):
    fake_source.seed_price("AAPL", 100.0)
    fake_source.seed_price("MSFT", 200.0)
    api_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 1})
    api_client.post("/api/portfolio/trade", json={"ticker": "MSFT", "side": "buy", "quantity": 1})

    body = api_client.get("/api/trades").json()
    tickers = [t["ticker"] for t in body["trades"]]
    assert tickers[0] == "MSFT"
    assert tickers[1] == "AAPL"


def test_trades_limit_param(api_client, fake_source):
    fake_source.seed_price("AAPL", 100.0)
    for _ in range(3):
        api_client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "side": "buy", "quantity": 0.1},
        )
    body = api_client.get("/api/trades", params={"limit": 2}).json()
    assert len(body["trades"]) == 2


# --- snapshot side effect ---


def test_each_trade_writes_portfolio_snapshot(api_client, fake_source):
    fake_source.seed_price("AAPL", 100.0)
    before = len(get_portfolio_history(from_iso="1970-01-01", to_iso="2999-01-01"))

    api_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 1})
    api_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "sell", "quantity": 1})

    after = len(get_portfolio_history(from_iso="1970-01-01", to_iso="2999-01-01"))
    assert after - before == 2


# --- tracked-ticker set ---


def test_buy_adds_ticker_to_market_source(api_client, fake_source):
    fake_source.seed_price("NEWBIE", 25.0)
    assert "NEWBIE" not in fake_source.tickers

    api_client.post(
        "/api/portfolio/trade",
        json={"ticker": "NEWBIE", "side": "buy", "quantity": 1},
    )
    assert "NEWBIE" in fake_source.tickers


def test_sell_full_position_removes_ticker_unless_on_watchlist(api_client, fake_source):
    """Closing a position removes the ticker from tracking when it's not also watched."""
    fake_source.seed_price("LONER", 25.0)
    api_client.post("/api/portfolio/trade", json={"ticker": "LONER", "side": "buy", "quantity": 1})
    assert "LONER" in fake_source.tickers

    api_client.post("/api/portfolio/trade", json={"ticker": "LONER", "side": "sell", "quantity": 1})
    assert "LONER" not in fake_source.tickers


def test_sell_full_position_keeps_ticker_if_on_watchlist(api_client, fake_source):
    """If the closed-out ticker is on the watchlist, it stays tracked."""
    fake_source.seed_price("AAPL", 100.0)  # AAPL is on the seeded watchlist
    api_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 1})
    api_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "sell", "quantity": 1})
    assert "AAPL" in fake_source.tickers


# --- execute_trade(): import path for llm-engineer ---


@pytest.mark.asyncio
async def test_execute_trade_callable_directly_from_python(api_client, fake_source):
    """llm-engineer imports `execute_trade` directly; verify the contract works."""
    fake_source.seed_price("AAPL", 100.0)
    result = await execute_trade("aapl", 1.0, "buy")
    assert result.ticker == "AAPL"
    assert result.side == "buy"
    assert result.quantity == 1.0
    assert result.price == 100.0
    assert result.cash_balance == 9900.0
    assert result.position["quantity"] == 1.0


@pytest.mark.asyncio
async def test_execute_trade_raises_trade_error_on_failure(api_client, fake_source):
    fake_source.seed_price("AAPL", 100.0)
    with pytest.raises(TradeError) as exc:
        await execute_trade("AAPL", 1.0, "sell")
    assert str(exc.value) == "insufficient shares"


# --- lock serialization ---


@pytest.mark.asyncio
async def test_concurrent_trades_do_not_race(api_client, fake_source):
    """Two concurrent buys that together exceed available cash: exactly one wins.

    The lock must serialize the read-validate-write sequence so the cash balance
    cannot drift negative.
    """
    fake_source.seed_price("AAPL", 6000.0)  # $6000 each; only one fits in $10k cash

    async def attempt():
        try:
            return await execute_trade("AAPL", 1.0, "buy")
        except TradeError as exc:
            return exc

    a, b = await asyncio.gather(attempt(), attempt())

    successes = [r for r in (a, b) if not isinstance(r, TradeError)]
    failures = [r for r in (a, b) if isinstance(r, TradeError)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert str(failures[0]) == "insufficient cash"

    profile = get_user_profile()
    assert profile["cash_balance"] == 10000.0 - 6000.0
    assert len(get_trades()) == 1
