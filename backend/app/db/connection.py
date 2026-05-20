"""SQLite connection management and lazy schema initialization."""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_USER_ID = "default"
DEFAULT_DB_RELATIVE_PATH = Path("db") / "finally.db"

_PATH_LOCK = threading.Lock()
_CACHED_PATH: Path | None = None
_INITIALIZED_PATHS: set[Path] = set()


def _schema_sql() -> str:
    """Read the bundled schema.sql file."""
    return (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")


def get_db_path() -> Path:
    """Resolve the active SQLite path.

    Honors `FINALLY_DB_PATH` env override; otherwise uses `db/finally.db` relative
    to the current working directory. Parent directories are created as needed.
    The resolved path is cached for the process; call `reset_db_path_cache()` to
    force re-evaluation (used by tests).
    """
    global _CACHED_PATH
    with _PATH_LOCK:
        if _CACHED_PATH is not None:
            return _CACHED_PATH

        override = os.environ.get("FINALLY_DB_PATH")
        path = Path(override) if override else DEFAULT_DB_RELATIVE_PATH
        path = path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        _CACHED_PATH = path
        return path


def reset_db_path_cache() -> None:
    """Drop cached path + initialization markers. Intended for tests."""
    global _CACHED_PATH
    with _PATH_LOCK:
        _CACHED_PATH = None
        _INITIALIZED_PATHS.clear()


def now_iso() -> str:
    """UTC timestamp in ISO 8601 format, used for all `*_at` columns."""
    return datetime.now(timezone.utc).isoformat()


def _initialize(conn: sqlite3.Connection) -> None:
    """Create schema and seed defaults if the database is empty."""
    from .queries import DEFAULT_CASH_BALANCE, DEFAULT_WATCHLIST

    conn.executescript(_schema_sql())

    cur = conn.execute(
        "SELECT 1 FROM user_profile WHERE id = ?",
        (DEFAULT_USER_ID,),
    )
    if cur.fetchone() is None:
        now = now_iso()
        conn.execute(
            "INSERT INTO user_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
            (DEFAULT_USER_ID, DEFAULT_CASH_BALANCE, now),
        )
        conn.executemany(
            "INSERT OR IGNORE INTO watchlist (user_id, ticker, added_at) VALUES (?, ?, ?)",
            [(DEFAULT_USER_ID, ticker, now) for ticker in DEFAULT_WATCHLIST],
        )
        conn.commit()


def get_db() -> sqlite3.Connection:
    """Return a sqlite3 connection to the FinAlly database.

    On first call (per resolved path), this lazily creates the schema and seeds
    the default user + watchlist. The connection uses `check_same_thread=False`
    so it can be passed between threads; WAL mode is enabled for concurrent reads
    while writes are happening. Callers should not share the same connection
    between threads without external locking — open a fresh connection per worker.
    Rows are returned as `sqlite3.Row` for dict-like access.
    """
    path = get_db_path()
    conn = sqlite3.connect(
        path,
        check_same_thread=False,
        isolation_level=None,  # autocommit; explicit transactions via BEGIN
        timeout=30.0,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")

    with _PATH_LOCK:
        already_initialized = path in _INITIALIZED_PATHS

    if not already_initialized:
        _initialize(conn)
        with _PATH_LOCK:
            _INITIALIZED_PATHS.add(path)

    return conn
