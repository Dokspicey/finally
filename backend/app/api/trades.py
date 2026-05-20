"""Shared trade execution + locking + tracked-ticker management.

The single `_TRADE_LOCK` defined here is the only synchronization primitive that
guards cash/position mutations. Both the manual REST handler in
`app.api.portfolio` and the LLM-initiated path in `app.chat` call
`execute_trade(...)` — never reimplement the trade logic.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.db import (
    delete_position,
    get_db,
    get_position,
    get_positions,
    get_user_profile,
    get_watchlist,
    insert_portfolio_snapshot,
    insert_trade,
    update_cash_balance,
    upsert_position,
)
from app.market import MarketDataSource, PriceCache

logger = logging.getLogger(__name__)

# Serializes every cash/position mutation across the process. Manual trades,
# LLM-initiated trades, and watchlist mutations all acquire this so the
# read-validate-write sequence on `user_profile.cash_balance` + `positions`
# cannot race.
_TRADE_LOCK = asyncio.Lock()

_PRICE_CACHE: PriceCache | None = None
_MARKET_SOURCE: MarketDataSource | None = None

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_VALID_SIDES = {"buy", "sell"}


class TradeError(Exception):
    """Raised when a trade fails validation. Message is user-facing."""


@dataclass(frozen=True)
class TradeRequest:
    ticker: str
    side: str
    quantity: float


@dataclass(frozen=True)
class TradeResult:
    trade_id: str
    ticker: str
    side: str
    quantity: float
    price: float
    executed_at: str
    cash_balance: float
    position: dict[str, Any] | None  # None when a sell zeroed the position


# --------------------------------------------------------------------------- #
# wiring


def set_app_state(
    price_cache: PriceCache | None,
    market_source: MarketDataSource | None,
) -> None:
    """Wire the module to the running app's PriceCache and MarketDataSource."""
    global _PRICE_CACHE, _MARKET_SOURCE
    _PRICE_CACHE = price_cache
    _MARKET_SOURCE = market_source


def get_price_cache() -> PriceCache:
    if _PRICE_CACHE is None:
        raise RuntimeError("PriceCache not wired — call set_app_state()")
    return _PRICE_CACHE


def get_market_source() -> MarketDataSource | None:
    return _MARKET_SOURCE


def get_trade_lock() -> asyncio.Lock:
    """Expose the lock so adjacent mutations (e.g. watchlist) can share it."""
    return _TRADE_LOCK


# --------------------------------------------------------------------------- #
# helpers


def normalize_ticker(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        raise ValueError("ticker required")
    t = raw.strip().upper()
    if not _TICKER_RE.match(t):
        raise ValueError("invalid ticker")
    return t


def normalize_side(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        raise ValueError("unknown side")
    s = raw.strip().lower()
    if s not in _VALID_SIDES:
        raise ValueError("unknown side")
    return s


def current_price(ticker: str, fallback: float | None = None) -> float | None:
    cache = get_price_cache()
    price = cache.get_price(ticker)
    return price if price is not None else fallback


def compute_total_value(
    cash_balance: float,
    positions: list[dict[str, Any]],
) -> float:
    """Total portfolio value = cash + sum(qty * current_price-or-avg_cost)."""
    total = cash_balance
    for pos in positions:
        ticker = pos["ticker"]
        qty = float(pos["quantity"])
        avg_cost = float(pos["avg_cost"])
        price = current_price(ticker, fallback=avg_cost)
        total += qty * (price if price is not None else avg_cost)
    return total


def write_portfolio_snapshot(conn=None) -> str:
    """Compute the current total value and append a `portfolio_snapshots` row."""
    if conn is None:
        own = get_db()
        try:
            return _write_snapshot(own)
        finally:
            own.close()
    return _write_snapshot(conn)


def _write_snapshot(conn) -> str:
    profile = get_user_profile(conn=conn)
    positions = get_positions(conn=conn)
    cash = float(profile["cash_balance"]) if profile else 0.0
    total = compute_total_value(cash, positions)
    return insert_portfolio_snapshot(total, conn=conn)


async def sync_tracked_tickers() -> None:
    """Sync the market source's tracked set to (watchlist ∪ open positions)."""
    source = _MARKET_SOURCE
    if source is None:
        return

    conn = get_db()
    try:
        watch = {row["ticker"] for row in get_watchlist(conn=conn)}
        held = {row["ticker"] for row in get_positions(conn=conn)}
    finally:
        conn.close()
    desired = watch | held
    active = set(source.get_tickers())

    for ticker in desired - active:
        await source.add_ticker(ticker)
    for ticker in active - desired:
        await source.remove_ticker(ticker)


# --------------------------------------------------------------------------- #
# execute_trade — the single mutation entry point


async def execute_trade(
    ticker: str,
    quantity: float,
    side: str,
) -> TradeResult:
    """Execute a market order under the global trade lock.

    Raises TradeError on any validation failure.
    """
    # Pre-validate before grabbing the lock so bad inputs don't block writers.
    try:
        norm_ticker = normalize_ticker(ticker)
        norm_side = normalize_side(side)
    except ValueError as exc:
        raise TradeError(str(exc)) from exc

    if not isinstance(quantity, (int, float)) or quantity != quantity:
        raise TradeError("quantity must be positive")
    qty = float(quantity)
    if qty <= 0:
        raise TradeError("quantity must be positive")

    async with _TRADE_LOCK:
        result, tracker_dirty = _run_trade(norm_ticker, qty, norm_side)
        if tracker_dirty:
            await sync_tracked_tickers()
        return result


def _run_trade(ticker: str, qty: float, side: str) -> tuple[TradeResult, bool]:
    """Synchronous trade body. Caller must hold `_TRADE_LOCK`.

    Returns the trade result and a flag indicating whether the tracked-ticker
    set may have changed (i.e. a position opened or closed).
    """
    cache = get_price_cache()
    price = cache.get_price(ticker)

    conn = get_db()
    try:
        profile = get_user_profile(conn=conn)
        if profile is None:
            raise TradeError("user profile missing")
        cash = float(profile["cash_balance"])

        existing = get_position(ticker, conn=conn)

        if price is None:
            # Buy with no quote = refuse. Sell of a held ticker can use avg_cost.
            if side == "buy" or existing is None:
                raise TradeError("no price available")
            price = float(existing["avg_cost"])

        fill_price = float(price)
        cost = fill_price * qty

        position_existed_before = existing is not None

        if side == "buy":
            if cost > cash + 1e-9:
                raise TradeError("insufficient cash")
            new_cash = cash - cost
            if existing is None:
                new_qty = qty
                new_avg = fill_price
            else:
                prev_qty = float(existing["quantity"])
                prev_avg = float(existing["avg_cost"])
                new_qty = prev_qty + qty
                new_avg = ((prev_qty * prev_avg) + (qty * fill_price)) / new_qty
        else:  # sell
            if existing is None:
                raise TradeError("insufficient shares")
            prev_qty = float(existing["quantity"])
            if qty > prev_qty + 1e-9:
                raise TradeError("insufficient shares")
            new_cash = cash + cost
            new_qty = prev_qty - qty
            new_avg = float(existing["avg_cost"])  # unchanged on sells

        update_cash_balance(new_cash, conn=conn)

        position_closed = new_qty <= 1e-9
        if position_closed:
            delete_position(ticker, conn=conn)
            position_payload: dict[str, Any] | None = None
        else:
            upsert_position(ticker, new_qty, new_avg, conn=conn)
            position_payload = get_position(ticker, conn=conn)

        trade_id = insert_trade(ticker, side, qty, fill_price, conn=conn)
        trade_row = conn.execute(
            "SELECT executed_at FROM trades WHERE id = ?",
            (trade_id,),
        ).fetchone()

        _write_snapshot(conn)
    finally:
        conn.close()

    result = TradeResult(
        trade_id=trade_id,
        ticker=ticker,
        side=side,
        quantity=qty,
        price=fill_price,
        executed_at=trade_row["executed_at"],
        cash_balance=new_cash,
        position=dict(position_payload) if position_payload else None,
    )

    # Only need to update the market source's tracked set when a position
    # opened (position_existed_before=False) or closed (position_closed=True).
    tracker_dirty = (not position_existed_before) or position_closed
    return result, tracker_dirty
