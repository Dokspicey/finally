"""Portfolio endpoints: state, trade execution, value history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db import (
    get_db,
    get_portfolio_history,
    get_positions,
    get_user_profile,
)

from .trades import (
    TradeError,
    current_price,
    execute_trade,
)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class TradeBody(BaseModel):
    ticker: str = Field(..., description="Ticker symbol, e.g. 'AAPL'")
    side: str = Field(..., description="'buy' or 'sell'")
    quantity: float = Field(..., gt=0, description="Number of shares, fractional allowed")


def _position_view(pos: dict[str, Any]) -> dict[str, Any]:
    """Build the per-position payload returned by /api/portfolio."""
    ticker = pos["ticker"]
    qty = float(pos["quantity"])
    avg_cost = float(pos["avg_cost"])
    price = current_price(ticker, fallback=avg_cost)
    effective_price = price if price is not None else avg_cost
    market_value = qty * effective_price
    cost_basis = qty * avg_cost
    pnl = market_value - cost_basis
    pnl_pct = (pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0
    return {
        "ticker": ticker,
        "quantity": qty,
        "avg_cost": avg_cost,
        "current_price": effective_price,
        "market_value": market_value,
        "unrealized_pnl": pnl,
        "unrealized_pnl_percent": pnl_pct,
        "updated_at": pos["updated_at"],
    }


@router.get("")
async def get_portfolio() -> dict[str, Any]:
    """Cash, positions, and aggregate P&L for the default user."""
    conn = get_db()
    try:
        profile = get_user_profile(conn=conn)
        positions = get_positions(conn=conn)
    finally:
        conn.close()

    cash = float(profile["cash_balance"]) if profile else 0.0
    position_views = [_position_view(p) for p in positions]
    market_value = sum(p["market_value"] for p in position_views)
    total_value = cash + market_value
    cost_basis = sum(float(p["quantity"]) * float(p["avg_cost"]) for p in positions)
    unrealized_pnl = market_value - cost_basis
    unrealized_pnl_pct = (unrealized_pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0

    return {
        "cash_balance": cash,
        "total_value": total_value,
        "unrealized_pnl": unrealized_pnl,
        "unrealized_pnl_percent": unrealized_pnl_pct,
        "positions": position_views,
    }


@router.post("/trade")
async def post_trade(body: TradeBody) -> dict[str, Any]:
    """Execute a market order. Mutation is serialized via the global trade lock."""
    try:
        result = await execute_trade(body.ticker, body.quantity, body.side)
    except TradeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "trade": {
            "id": result.trade_id,
            "ticker": result.ticker,
            "side": result.side,
            "quantity": result.quantity,
            "price": result.price,
            "executed_at": result.executed_at,
        },
        "cash_balance": result.cash_balance,
        "position": result.position,
    }


@router.get("/history")
async def get_history(
    from_iso: str | None = Query(default=None, alias="from"),
    to_iso: str | None = Query(default=None, alias="to"),
) -> dict[str, Any]:
    """Portfolio value snapshots in the [from, to] window. Defaults to last 24h."""
    if from_iso is None and to_iso is None:
        now = datetime.now(timezone.utc)
        from_iso = (now - timedelta(hours=24)).isoformat()
        to_iso = now.isoformat()

    conn = get_db()
    try:
        rows = get_portfolio_history(from_iso=from_iso, to_iso=to_iso, conn=conn)
    finally:
        conn.close()

    return {
        "snapshots": [
            {
                "id": r["id"],
                "total_value": float(r["total_value"]),
                "recorded_at": r["recorded_at"],
            }
            for r in rows
        ]
    }
