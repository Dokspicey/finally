"""FinAlly FastAPI application entry point.

Bootstraps the app with:
- A shared `PriceCache` and market data source (simulator or Massive API)
- The SSE streaming router from `app.market.stream`
- REST routers from `app.api` (portfolio, trades, watchlist)
- `/api/health` liveness endpoint
- Startup tracked-ticker sync (watchlist ∪ positions) and a seed portfolio snapshot
- Static mount of the built Next.js export at `FINALLY_STATIC_DIR` (default
  `/app/static` in the container) with SPA fallback to `index.html`. Mounted
  LAST so it never shadows `/api/*` routes.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import (
    portfolio_router,
    set_app_state,
    sync_tracked_tickers,
    trades_router,
    watchlist_router,
    write_portfolio_snapshot,
)
from app.chat import chat_router
from app.db import get_db, get_positions, get_watchlist
from app.market import PriceCache, create_market_data_source, create_stream_router

logger = logging.getLogger(__name__)


def _initial_tickers() -> list[str]:
    """Tickers to track at startup: union of watchlist and open positions.

    The DB layer seeds the default 10-ticker watchlist on first init, so on a
    fresh install this returns the default set.
    """
    conn = get_db()
    try:
        watch = {row["ticker"] for row in get_watchlist(conn=conn)}
        held = {row["ticker"] for row in get_positions(conn=conn)}
    finally:
        conn.close()
    return sorted(watch | held)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    price_cache = PriceCache()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        market_source = create_market_data_source(price_cache)
        tickers = _initial_tickers()
        await market_source.start(tickers)

        app.state.price_cache = price_cache
        app.state.market_source = market_source
        set_app_state(price_cache, market_source)

        # Cover the case where the active set diverges from (watchlist ∪ positions)
        # at startup (e.g. held ticker no longer on watchlist).
        await sync_tracked_tickers()

        # Seed snapshot so the P&L chart has at least one data point immediately.
        write_portfolio_snapshot()

        logger.info("FinAlly backend started with %d tracked tickers", len(tickers))
        try:
            yield
        finally:
            await market_source.stop()
            set_app_state(None, None)
            logger.info("FinAlly backend shut down")

    app = FastAPI(
        title="FinAlly",
        description="AI Trading Workstation backend",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Wire the cache eagerly so route handlers invoked without a full lifespan
    # (e.g. some unit-test setups) still see a cache. The lifespan re-wires it
    # alongside the started market source.
    app.state.price_cache = price_cache
    set_app_state(price_cache, None)

    app.include_router(create_stream_router(price_cache))
    app.include_router(portfolio_router)
    app.include_router(trades_router)
    app.include_router(watchlist_router)
    app.include_router(chat_router)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """Liveness probe used by Docker and deployment platforms."""
        return {"status": "ok"}

    _mount_frontend(app)

    return app


def _mount_frontend(app: FastAPI) -> None:
    """Mount the built Next.js static export with SPA fallback.

    Behavior:
    - `/` serves `index.html`.
    - Files under `_next/`, `static/`, plus top-level assets (favicon, etc.) are
      served from disk by `StaticFiles`.
    - Any other non-`/api/*` GET that doesn't match a file falls back to
      `index.html` so client-side routes (and direct deep links) work.
    - `/api/*` is registered earlier via routers, so this catch-all never
      shadows it (FastAPI matches routes in registration order).
    - If the static dir is missing (e.g. running the backend outside Docker
      without a frontend build), the mount is skipped — the API still works.
    """
    static_dir = Path(os.environ.get("FINALLY_STATIC_DIR", "/app/static"))
    index_file = static_dir / "index.html"

    if not index_file.is_file():
        logger.info("Static frontend not found at %s — skipping mount", static_dir)
        return

    # `html=True` makes StaticFiles serve `index.html` at "/" and for any
    # directory request. The catch-all below handles unknown paths (SPA routes).
    app.mount(
        "/_next",
        StaticFiles(directory=static_dir / "_next"),
        name="next-assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        # Defensive: `/api/*` is already routed above, so this should never
        # see an API path. Reject explicitly in case route ordering ever shifts.
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404)

        candidate = (static_dir / full_path).resolve()
        # Reject path traversal attempts (`..` segments that escape static_dir).
        try:
            candidate.relative_to(static_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=404) from None

        if candidate.is_file():
            return FileResponse(candidate)

        # SPA fallback — let the client-side router handle the path.
        return FileResponse(index_file)

    logger.info("Mounted frontend static export from %s", static_dir)


app = create_app()
