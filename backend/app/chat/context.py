"""Context builder — assembles the data the LLM needs to reason about the user.

Per PLAN.md §9 we hand the model:
- cash balance + total portfolio value
- positions with live prices and unrealized P&L (cache-fallback per §7)
- watchlist with latest prices
- the last 20 chat messages (sliding-window) — older messages are dropped to
  keep prompts bounded

`build_chat_context()` is sync — it talks to the DB + cache and returns a plain
dict suitable for both prompt assembly and any downstream JSON-serializing
debug surface.
"""

from __future__ import annotations

import json
from typing import Any

from app.api.trades import current_price
from app.db import (
    get_chat_messages,
    get_db,
    get_positions,
    get_user_profile,
    get_watchlist,
)

CONTEXT_HISTORY_LIMIT = 20


def _position_view(pos: dict[str, Any]) -> dict[str, Any]:
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
    }


def _watchlist_view(row: dict[str, Any]) -> dict[str, Any]:
    ticker = row["ticker"]
    price = current_price(ticker, fallback=None)
    return {"ticker": ticker, "price": price, "added_at": row["added_at"]}


def _parse_actions(blob: str | None) -> Any:
    if blob is None:
        return None
    try:
        return json.loads(blob)
    except (TypeError, ValueError):
        return None


def build_chat_context() -> dict[str, Any]:
    """Snapshot the user's state + recent chat history for prompt assembly."""
    conn = get_db()
    try:
        profile = get_user_profile(conn=conn)
        positions = get_positions(conn=conn)
        watchlist = get_watchlist(conn=conn)
        messages = get_chat_messages(limit=CONTEXT_HISTORY_LIMIT, conn=conn)
    finally:
        conn.close()

    cash = float(profile["cash_balance"]) if profile else 0.0
    position_views = [_position_view(p) for p in positions]
    market_value = sum(p["market_value"] for p in position_views)
    total_value = cash + market_value

    history = [
        {
            "role": m["role"],
            "content": m["content"],
            "actions": _parse_actions(m.get("actions")),
            "created_at": m["created_at"],
        }
        for m in messages
    ]

    return {
        "cash_balance": cash,
        "total_value": total_value,
        "positions": position_views,
        "watchlist": [_watchlist_view(w) for w in watchlist],
        "recent_messages": history,
    }
