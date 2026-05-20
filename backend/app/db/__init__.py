"""Database subsystem for FinAlly.

Public API:
    get_db                  - Get a sqlite3 connection (lazy-initializes schema + seed)
    get_db_path             - Resolve the active SQLite file path
    reset_db_path_cache     - Reset cached path (for testing / FINALLY_DB_PATH overrides)
    DEFAULT_USER_ID         - The hardcoded single-user id ("default")
    DEFAULT_CASH_BALANCE    - Starting cash for a new user ($10,000)
    DEFAULT_WATCHLIST       - The 10 seeded watchlist tickers

    # Query helpers
    get_user_profile, update_cash_balance
    get_watchlist, add_to_watchlist, remove_from_watchlist
    get_positions, get_position, upsert_position, delete_position
    insert_trade, get_trades
    insert_portfolio_snapshot, get_portfolio_history
    insert_chat_message, get_chat_messages
"""

from .connection import (
    DEFAULT_USER_ID,
    get_db,
    get_db_path,
    reset_db_path_cache,
)
from .queries import (
    DEFAULT_CASH_BALANCE,
    DEFAULT_WATCHLIST,
    add_to_watchlist,
    delete_position,
    get_chat_messages,
    get_portfolio_history,
    get_position,
    get_positions,
    get_trades,
    get_user_profile,
    get_watchlist,
    insert_chat_message,
    insert_portfolio_snapshot,
    insert_trade,
    remove_from_watchlist,
    update_cash_balance,
    upsert_position,
)

__all__ = [
    "DEFAULT_USER_ID",
    "DEFAULT_CASH_BALANCE",
    "DEFAULT_WATCHLIST",
    "get_db",
    "get_db_path",
    "reset_db_path_cache",
    "get_user_profile",
    "update_cash_balance",
    "get_watchlist",
    "add_to_watchlist",
    "remove_from_watchlist",
    "get_positions",
    "get_position",
    "upsert_position",
    "delete_position",
    "insert_trade",
    "get_trades",
    "insert_portfolio_snapshot",
    "get_portfolio_history",
    "insert_chat_message",
    "get_chat_messages",
]
