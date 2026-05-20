"""Tests for connection management and lazy schema initialization."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.db import (
    DEFAULT_CASH_BALANCE,
    DEFAULT_USER_ID,
    DEFAULT_WATCHLIST,
    get_db,
    get_db_path,
    reset_db_path_cache,
)


class TestGetDbPath:
    def test_honors_env_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        target = tmp_path / "custom" / "mydb.sqlite"
        monkeypatch.setenv("FINALLY_DB_PATH", str(target))
        reset_db_path_cache()
        try:
            assert get_db_path() == target.resolve()
            # Parent directory was created
            assert target.parent.is_dir()
        finally:
            reset_db_path_cache()

    def test_caches_resolved_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        target = tmp_path / "a.db"
        monkeypatch.setenv("FINALLY_DB_PATH", str(target))
        reset_db_path_cache()
        try:
            first = get_db_path()
            # Change env underneath — cache should ignore it
            monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "b.db"))
            second = get_db_path()
            assert first == second
        finally:
            reset_db_path_cache()

    def test_reset_cache_re_reads_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "a.db"))
        reset_db_path_cache()
        first = get_db_path()
        monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "b.db"))
        reset_db_path_cache()
        second = get_db_path()
        assert first != second


class TestLazyInit:
    def test_creates_file_on_first_get(self, db_path: Path):
        assert not db_path.exists()
        conn = get_db()
        try:
            assert db_path.exists()
        finally:
            conn.close()

    def test_schema_tables_present(self, fresh_db: sqlite3.Connection):
        tables = {
            r["name"]
            for r in fresh_db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = {
            "user_profile",
            "watchlist",
            "positions",
            "trades",
            "portfolio_snapshots",
            "chat_messages",
        }
        assert expected.issubset(tables)

    def test_seeds_default_user(self, fresh_db: sqlite3.Connection):
        row = fresh_db.execute(
            "SELECT id, cash_balance FROM user_profile WHERE id = ?",
            (DEFAULT_USER_ID,),
        ).fetchone()
        assert row is not None
        assert row["id"] == DEFAULT_USER_ID
        assert row["cash_balance"] == DEFAULT_CASH_BALANCE

    def test_seeds_default_watchlist(self, fresh_db: sqlite3.Connection):
        rows = fresh_db.execute(
            "SELECT ticker FROM watchlist WHERE user_id = ?",
            (DEFAULT_USER_ID,),
        ).fetchall()
        tickers = {r["ticker"] for r in rows}
        assert tickers == set(DEFAULT_WATCHLIST)
        assert len(tickers) == 10

    def test_idempotent_init(self, db_path: Path):
        """Opening the DB twice should not duplicate seed data."""
        c1 = get_db()
        c1.close()
        # Force re-init code path by wiping the in-memory marker
        reset_db_path_cache()
        # Re-set env since reset_db_path_cache cleared cache (env still set by fixture)
        c2 = get_db()
        try:
            count = c2.execute(
                "SELECT COUNT(*) AS n FROM user_profile WHERE id = ?",
                (DEFAULT_USER_ID,),
            ).fetchone()["n"]
            assert count == 1
            wl_count = c2.execute(
                "SELECT COUNT(*) AS n FROM watchlist WHERE user_id = ?",
                (DEFAULT_USER_ID,),
            ).fetchone()["n"]
            assert wl_count == 10
        finally:
            c2.close()

    def test_wal_mode_enabled(self, fresh_db: sqlite3.Connection):
        mode = fresh_db.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"

    def test_row_factory_returns_rows(self, fresh_db: sqlite3.Connection):
        row = fresh_db.execute(
            "SELECT id FROM user_profile LIMIT 1"
        ).fetchone()
        # sqlite3.Row supports both index and key access
        assert row["id"] == DEFAULT_USER_ID

    def test_check_same_thread_false(self, fresh_db: sqlite3.Connection):
        """Connection should be usable from another thread."""
        import threading

        result: list[str] = []

        def worker():
            row = fresh_db.execute("SELECT id FROM user_profile LIMIT 1").fetchone()
            result.append(row["id"])

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        assert result == [DEFAULT_USER_ID]
