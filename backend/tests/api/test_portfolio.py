"""Tests for /api/portfolio and /api/portfolio/history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db import insert_portfolio_snapshot, upsert_position


def test_portfolio_empty_state_returns_seeded_cash(api_client):
    resp = api_client.get("/api/portfolio")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cash_balance"] == 10000.0
    assert body["total_value"] == 10000.0
    assert body["positions"] == []
    assert body["unrealized_pnl"] == 0.0


def test_portfolio_includes_positions_with_live_price(api_client, fake_source):
    fake_source.seed_price("AAPL", 200.00)
    upsert_position("AAPL", 2.0, 190.00)  # bought below current price

    body = api_client.get("/api/portfolio").json()
    positions = {p["ticker"]: p for p in body["positions"]}

    aapl = positions["AAPL"]
    assert aapl["quantity"] == 2.0
    assert aapl["avg_cost"] == 190.00
    assert aapl["current_price"] == 200.00
    assert aapl["market_value"] == 400.00
    assert aapl["unrealized_pnl"] == 20.00  # 2 * (200 - 190)
    assert aapl["unrealized_pnl_percent"] == pytest_approx(20.0 / 380.0 * 100.0)
    assert body["total_value"] == 10000.0 + 400.00
    assert body["unrealized_pnl"] == 20.00


def test_portfolio_uses_avg_cost_fallback_when_price_missing(api_client):
    """Valuation fallback: held ticker with no cache entry uses avg_cost."""
    upsert_position("MYSTERY", 1.0, 50.00)

    body = api_client.get("/api/portfolio").json()
    pos = next(p for p in body["positions"] if p["ticker"] == "MYSTERY")
    assert pos["current_price"] == 50.00
    assert pos["market_value"] == 50.00
    assert pos["unrealized_pnl"] == 0.0
    # Total value reflects the fallback, no fake P&L spike.
    assert body["total_value"] == 10050.00


def test_history_default_window_returns_last_24h(api_client):
    """The default window is the last 24h."""
    insert_portfolio_snapshot(9000.0)  # falls in window (created just now)

    body = api_client.get("/api/portfolio/history").json()
    assert len(body["snapshots"]) == 1
    snap = body["snapshots"][0]
    assert snap["total_value"] == 9000.0
    assert "id" in snap
    assert "recorded_at" in snap


def test_history_respects_from_and_to_params(api_client):
    insert_portfolio_snapshot(1234.0)

    far_future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    body = api_client.get(
        "/api/portfolio/history",
        params={"from": far_future, "to": far_future},
    ).json()
    assert body["snapshots"] == []


# --- tiny local approx helper (avoid pulling in pytest.approx import cycles) ---

def pytest_approx(value: float, tol: float = 1e-6):
    class _Approx:
        def __eq__(self, other: float) -> bool:
            return abs(other - value) < tol

        def __repr__(self) -> str:
            return f"~{value}"

    return _Approx()
