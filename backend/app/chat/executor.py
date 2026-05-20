"""Apply the trades + watchlist changes the LLM requested.

PLAN.md §9 rules baked in here:
- Trades go through `app.api.execute_trade` — never reimplemented. On
  `TradeError` we record a failure and keep going. No LLM re-invocation.
- Watchlist mutations share the same global trade lock so the tracked-ticker
  set + cash/positions cannot diverge mid-trade.
- Every action produces an `action_result` row with `success`/`note` so the
  frontend can render inline confirmations or errors.
"""

from __future__ import annotations

import logging
from typing import Any

from app.api import (
    TradeError,
    add_watchlist_ticker,
    execute_trade,
    remove_watchlist_ticker,
)

from .schema import ChatLLMResponse, LLMTrade, LLMWatchlistChange

logger = logging.getLogger(__name__)

# Past-tense map keeps the human-readable note grammatical.
_PAST_TENSE = {"buy": "bought", "sell": "sold"}


async def execute_actions(parsed: ChatLLMResponse) -> list[dict[str, Any]]:
    """Run every trade then every watchlist change. Return action results."""
    results: list[dict[str, Any]] = []

    for trade in parsed.trades:
        results.append(await _run_trade(trade))

    for change in parsed.watchlist_changes:
        results.append(await _run_watchlist(change))

    return results


async def _run_trade(trade: LLMTrade) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": "trade",
        "ticker": trade.ticker,
        "side": trade.side,
        "quantity": trade.quantity,
    }
    try:
        result = await execute_trade(trade.ticker, trade.quantity, trade.side)
    except TradeError as exc:
        payload["success"] = False
        payload["note"] = str(exc)
        return payload

    verb = _PAST_TENSE.get(trade.side, f"{trade.side}ed")
    payload["success"] = True
    payload["note"] = f"{verb} {trade.quantity:g} {trade.ticker} @ {result.price:.2f}"
    payload["trade"] = {
        "id": result.trade_id,
        "ticker": result.ticker,
        "side": result.side,
        "quantity": result.quantity,
        "price": result.price,
        "executed_at": result.executed_at,
    }
    payload["cash_balance"] = result.cash_balance
    payload["position"] = result.position
    return payload


async def _run_watchlist(change: LLMWatchlistChange) -> dict[str, Any]:
    """Delegate to `backend-api`'s shared coroutines.

    `add_watchlist_ticker` / `remove_watchlist_ticker` both acquire the global
    `_TRADE_LOCK` and do the DB + tracked-set update. They raise `ValueError`
    on invalid input (mirrors how `execute_trade` raises `TradeError`).
    """
    payload: dict[str, Any] = {
        "kind": "watchlist",
        "ticker": change.ticker,
        "action": change.action,
    }
    try:
        if change.action == "add":
            result = await add_watchlist_ticker(change.ticker)
            payload["success"] = True
            payload["note"] = f"added {result['ticker']} to watchlist"
        else:
            result = await remove_watchlist_ticker(change.ticker)
            payload["success"] = True
            ticker = result["ticker"]
            payload["note"] = (
                f"removed {ticker} from watchlist"
                if result.get("removed")
                else f"{ticker} was not on watchlist"
            )
    except ValueError as exc:
        payload["success"] = False
        payload["note"] = str(exc)
    return payload
