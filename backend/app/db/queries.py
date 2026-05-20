"""Small query helpers for the FinAlly database.

All helpers accept an optional `conn` parameter. Callers that already hold a
connection should pass it in to avoid opening extras. When `conn` is omitted, a
fresh connection is opened (and closed) per call.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from .connection import DEFAULT_USER_ID, get_db, now_iso

DEFAULT_CASH_BALANCE = 10000.0
DEFAULT_WATCHLIST: tuple[str, ...] = (
    "AAPL",
    "GOOGL",
    "MSFT",
    "AMZN",
    "TSLA",
    "NVDA",
    "META",
    "JPM",
    "V",
    "NFLX",
)


@contextmanager
def _resolve(conn: sqlite3.Connection | None) -> Iterator[sqlite3.Connection]:
    """Yield a connection, opening a fresh one if `conn` is None."""
    if conn is not None:
        yield conn
        return
    owned = get_db()
    try:
        yield owned
    finally:
        owned.close()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


# ----------------------------- user_profile -----------------------------

def get_user_profile(
    user_id: str = DEFAULT_USER_ID,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    with _resolve(conn) as c:
        row = c.execute(
            "SELECT id, cash_balance, created_at FROM user_profile WHERE id = ?",
            (user_id,),
        ).fetchone()
    return _row_to_dict(row)


def update_cash_balance(
    new_balance: float,
    user_id: str = DEFAULT_USER_ID,
    *,
    conn: sqlite3.Connection | None = None,
) -> None:
    with _resolve(conn) as c:
        c.execute(
            "UPDATE user_profile SET cash_balance = ? WHERE id = ?",
            (new_balance, user_id),
        )


# ------------------------------ watchlist ------------------------------

def get_watchlist(
    user_id: str = DEFAULT_USER_ID,
    *,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    with _resolve(conn) as c:
        rows = c.execute(
            "SELECT ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_to_watchlist(
    ticker: str,
    user_id: str = DEFAULT_USER_ID,
    *,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """Insert a ticker into the watchlist. Returns True if newly added, False if it already existed."""
    ticker = ticker.upper()
    now = now_iso()
    with _resolve(conn) as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO watchlist (user_id, ticker, added_at) VALUES (?, ?, ?)",
            (user_id, ticker, now),
        )
        return cur.rowcount > 0


def remove_from_watchlist(
    ticker: str,
    user_id: str = DEFAULT_USER_ID,
    *,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """Remove a ticker from the watchlist. Returns True if a row was deleted."""
    ticker = ticker.upper()
    with _resolve(conn) as c:
        cur = c.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
            (user_id, ticker),
        )
        return cur.rowcount > 0


# ------------------------------ positions ------------------------------

def get_positions(
    user_id: str = DEFAULT_USER_ID,
    *,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    with _resolve(conn) as c:
        rows = c.execute(
            "SELECT ticker, quantity, avg_cost, updated_at FROM positions "
            "WHERE user_id = ? ORDER BY ticker",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_position(
    ticker: str,
    user_id: str = DEFAULT_USER_ID,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    ticker = ticker.upper()
    with _resolve(conn) as c:
        row = c.execute(
            "SELECT ticker, quantity, avg_cost, updated_at FROM positions "
            "WHERE user_id = ? AND ticker = ?",
            (user_id, ticker),
        ).fetchone()
    return _row_to_dict(row)


def upsert_position(
    ticker: str,
    quantity: float,
    avg_cost: float,
    user_id: str = DEFAULT_USER_ID,
    *,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Insert-or-update a position row. `avg_cost` and `quantity` overwrite existing values."""
    ticker = ticker.upper()
    now = now_iso()
    with _resolve(conn) as c:
        c.execute(
            """
            INSERT INTO positions (user_id, ticker, quantity, avg_cost, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (user_id, ticker) DO UPDATE SET
                quantity = excluded.quantity,
                avg_cost = excluded.avg_cost,
                updated_at = excluded.updated_at
            """,
            (user_id, ticker, quantity, avg_cost, now),
        )


def delete_position(
    ticker: str,
    user_id: str = DEFAULT_USER_ID,
    *,
    conn: sqlite3.Connection | None = None,
) -> bool:
    ticker = ticker.upper()
    with _resolve(conn) as c:
        cur = c.execute(
            "DELETE FROM positions WHERE user_id = ? AND ticker = ?",
            (user_id, ticker),
        )
        return cur.rowcount > 0


# ------------------------------- trades --------------------------------

def insert_trade(
    ticker: str,
    side: str,
    quantity: float,
    price: float,
    user_id: str = DEFAULT_USER_ID,
    *,
    conn: sqlite3.Connection | None = None,
) -> str:
    """Append a trade to the immutable trade log. Returns the new trade id."""
    if side not in ("buy", "sell"):
        raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
    trade_id = str(uuid.uuid4())
    ticker = ticker.upper()
    now = now_iso()
    with _resolve(conn) as c:
        c.execute(
            """
            INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (trade_id, user_id, ticker, side, quantity, price, now),
        )
    return trade_id


def get_trades(
    user_id: str = DEFAULT_USER_ID,
    limit: int = 100,
    *,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Most-recent-first trade history."""
    with _resolve(conn) as c:
        rows = c.execute(
            """
            SELECT id, ticker, side, quantity, price, executed_at
            FROM trades
            WHERE user_id = ?
            ORDER BY executed_at DESC, id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ------------------------- portfolio_snapshots -------------------------

def insert_portfolio_snapshot(
    total_value: float,
    user_id: str = DEFAULT_USER_ID,
    *,
    conn: sqlite3.Connection | None = None,
) -> str:
    snapshot_id = str(uuid.uuid4())
    now = now_iso()
    with _resolve(conn) as c:
        c.execute(
            """
            INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)
            VALUES (?, ?, ?, ?)
            """,
            (snapshot_id, user_id, total_value, now),
        )
    return snapshot_id


def get_portfolio_history(
    user_id: str = DEFAULT_USER_ID,
    from_iso: str | None = None,
    to_iso: str | None = None,
    *,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Return snapshots in the [from, to] window (inclusive), oldest first.

    Defaults to the last 24h when neither bound is given.
    """
    if from_iso is None and to_iso is None:
        to_dt = datetime.now(timezone.utc)
        from_dt = to_dt - timedelta(hours=24)
        from_iso = from_dt.isoformat()
        to_iso = to_dt.isoformat()

    sql = "SELECT id, total_value, recorded_at FROM portfolio_snapshots WHERE user_id = ?"
    params: list[Any] = [user_id]
    if from_iso is not None:
        sql += " AND recorded_at >= ?"
        params.append(from_iso)
    if to_iso is not None:
        sql += " AND recorded_at <= ?"
        params.append(to_iso)
    sql += " ORDER BY recorded_at"

    with _resolve(conn) as c:
        rows = c.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# --------------------------- chat_messages -----------------------------

def insert_chat_message(
    role: str,
    content: str,
    actions: str | None = None,
    user_id: str = DEFAULT_USER_ID,
    *,
    conn: sqlite3.Connection | None = None,
) -> str:
    """Append a chat message. `actions` is an opaque JSON string (or None)."""
    if role not in ("user", "assistant"):
        raise ValueError(f"role must be 'user' or 'assistant', got {role!r}")
    message_id = str(uuid.uuid4())
    now = now_iso()
    with _resolve(conn) as c:
        c.execute(
            """
            INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (message_id, user_id, role, content, actions, now),
        )
    return message_id


def get_chat_messages(
    user_id: str = DEFAULT_USER_ID,
    limit: int = 50,
    *,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Return the most recent `limit` messages, oldest first (suitable for chat UI replay)."""
    with _resolve(conn) as c:
        rows = c.execute(
            """
            SELECT id, role, content, actions, created_at
            FROM (
                SELECT id, role, content, actions, created_at
                FROM chat_messages
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
            )
            ORDER BY created_at, id
            """,
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]
