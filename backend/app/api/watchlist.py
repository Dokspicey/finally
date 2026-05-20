"""Watchlist endpoints: GET / POST / DELETE.

The locked mutation coroutines (`add_watchlist_ticker`, `remove_watchlist_ticker`)
are the canonical entry points used by both the REST handlers and the LLM chat
layer. Do not duplicate the DB+tracked-set logic — import these instead.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import (
    add_to_watchlist,
    get_db,
    get_position,
    get_watchlist,
    remove_from_watchlist,
)

from .trades import (
    get_market_source,
    get_trade_lock,
    normalize_ticker,
)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class AddBody(BaseModel):
    ticker: str = Field(..., description="Ticker symbol to add")


def _ticker_view(row: dict[str, Any]) -> dict[str, Any]:
    """Hydrate a watchlist row with the latest price snapshot (if any)."""
    from .trades import get_price_cache

    update = get_price_cache().get(row["ticker"])
    if update is None:
        price_block: dict[str, Any] = {
            "price": None,
            "previous_price": None,
            "change": None,
            "change_percent": None,
            "direction": None,
        }
    else:
        price_block = {
            "price": update.price,
            "previous_price": update.previous_price,
            "change": update.change,
            "change_percent": update.change_percent,
            "direction": update.direction,
        }
    return {
        "ticker": row["ticker"],
        "added_at": row["added_at"],
        **price_block,
    }


# --------------------------------------------------------------------------- #
# Public coroutines — used by REST handlers AND the LLM chat layer.
# Validation raises ValueError; callers map to whatever surface error they need
# (HTTPException for REST, action_results entry for chat).


async def add_watchlist_ticker(ticker: str) -> dict[str, Any]:
    """Add `ticker` to the watchlist and start streaming its price.

    Idempotent — re-adding an existing ticker returns the original `added_at`.
    Validation: `ticker` is normalized + shape-checked; ValueError on bad input.
    Returns `{"ticker": <UPPER>, "added_at": <iso>}`.
    """
    norm = normalize_ticker(ticker)

    async with get_trade_lock():
        conn = get_db()
        try:
            row = next(
                (r for r in get_watchlist(conn=conn) if r["ticker"] == norm),
                None,
            )
            if row is None:
                add_to_watchlist(norm, conn=conn)
                row = next(
                    (r for r in get_watchlist(conn=conn) if r["ticker"] == norm),
                    None,
                )
        finally:
            conn.close()

        source = get_market_source()
        if source is not None and norm not in source.get_tickers():
            await source.add_ticker(norm)

    return {"ticker": norm, "added_at": row["added_at"] if row else None}


async def remove_watchlist_ticker(ticker: str) -> dict[str, Any]:
    """Remove `ticker` from the watchlist. Idempotent.

    The ticker stays in the market source's tracked set if a position still
    references it (PLAN.md §6 tracked-ticker rule).
    Returns `{"ticker": <UPPER>, "removed": <bool>}`.
    """
    norm = normalize_ticker(ticker)

    async with get_trade_lock():
        conn = get_db()
        try:
            removed = remove_from_watchlist(norm, conn=conn)
            held = get_position(norm, conn=conn) is not None
        finally:
            conn.close()

        source = get_market_source()
        if removed and not held and source is not None and norm in source.get_tickers():
            await source.remove_ticker(norm)

    return {"ticker": norm, "removed": removed}


# --------------------------------------------------------------------------- #
# REST handlers — thin wrappers that translate ValueError → HTTP 400.


@router.get("")
async def list_watchlist() -> dict[str, Any]:
    conn = get_db()
    try:
        rows = get_watchlist(conn=conn)
    finally:
        conn.close()
    return {"watchlist": [_ticker_view(r) for r in rows]}


@router.post("", status_code=201)
async def add_ticker(body: AddBody) -> dict[str, Any]:
    try:
        return await add_watchlist_ticker(body.ticker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{ticker}")
async def remove_ticker(ticker: str) -> dict[str, Any]:
    try:
        return await remove_watchlist_ticker(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
