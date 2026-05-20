"""HTTP API routers and shared trade execution.

Public surface:
    portfolio_router         - GET /api/portfolio, GET /api/portfolio/history, POST /api/portfolio/trade
    trades_router            - GET /api/trades
    watchlist_router         - GET/POST/DELETE /api/watchlist[/{ticker}]
    execute_trade            - Coroutine used by both REST and LLM-initiated trades
    add_watchlist_ticker     - Coroutine used by both REST and LLM-initiated watchlist adds
    remove_watchlist_ticker  - Coroutine used by both REST and LLM-initiated watchlist removes
    TradeRequest             - Validated trade input
    TradeResult              - Successful trade output
    TradeError               - Exception raised on validation failure
    write_portfolio_snapshot - Compute and persist a portfolio snapshot
    set_app_state            - Wire the routers to the FastAPI app's PriceCache + MarketDataSource
"""

from .portfolio import router as portfolio_router
from .trade_history import router as trades_router
from .trades import (
    TradeError,
    TradeRequest,
    TradeResult,
    execute_trade,
    set_app_state,
    sync_tracked_tickers,
    write_portfolio_snapshot,
)
from .watchlist import (
    add_watchlist_ticker,
    remove_watchlist_ticker,
)
from .watchlist import (
    router as watchlist_router,
)

__all__ = [
    "portfolio_router",
    "trades_router",
    "watchlist_router",
    "execute_trade",
    "TradeRequest",
    "TradeResult",
    "TradeError",
    "write_portfolio_snapshot",
    "set_app_state",
    "sync_tracked_tickers",
    "add_watchlist_ticker",
    "remove_watchlist_ticker",
]
