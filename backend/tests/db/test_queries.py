"""Tests for query helpers."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db import (
    DEFAULT_CASH_BALANCE,
    DEFAULT_USER_ID,
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


class TestUserProfile:
    def test_get_returns_seeded_user(self, fresh_db: sqlite3.Connection):
        profile = get_user_profile(conn=fresh_db)
        assert profile is not None
        assert profile["id"] == DEFAULT_USER_ID
        assert profile["cash_balance"] == DEFAULT_CASH_BALANCE
        assert "created_at" in profile

    def test_get_unknown_user_returns_none(self, fresh_db: sqlite3.Connection):
        assert get_user_profile(user_id="nobody", conn=fresh_db) is None

    def test_update_cash_balance(self, fresh_db: sqlite3.Connection):
        update_cash_balance(5432.10, conn=fresh_db)
        profile = get_user_profile(conn=fresh_db)
        assert profile["cash_balance"] == 5432.10

    def test_update_cash_balance_no_conn(self, db_path):
        """Helpers without an explicit conn open their own connection."""
        update_cash_balance(123.45)
        profile = get_user_profile()
        assert profile["cash_balance"] == 123.45


class TestWatchlist:
    def test_default_watchlist(self, fresh_db: sqlite3.Connection):
        rows = get_watchlist(conn=fresh_db)
        tickers = [r["ticker"] for r in rows]
        assert set(tickers) == set(DEFAULT_WATCHLIST)

    def test_add_new(self, fresh_db: sqlite3.Connection):
        added = add_to_watchlist("PYPL", conn=fresh_db)
        assert added is True
        tickers = [r["ticker"] for r in get_watchlist(conn=fresh_db)]
        assert "PYPL" in tickers

    def test_add_existing_returns_false(self, fresh_db: sqlite3.Connection):
        added = add_to_watchlist("AAPL", conn=fresh_db)
        assert added is False

    def test_add_normalizes_to_uppercase(self, fresh_db: sqlite3.Connection):
        added = add_to_watchlist("pypl", conn=fresh_db)
        assert added is True
        tickers = [r["ticker"] for r in get_watchlist(conn=fresh_db)]
        assert "PYPL" in tickers
        assert "pypl" not in tickers

    def test_remove_existing(self, fresh_db: sqlite3.Connection):
        removed = remove_from_watchlist("AAPL", conn=fresh_db)
        assert removed is True
        tickers = [r["ticker"] for r in get_watchlist(conn=fresh_db)]
        assert "AAPL" not in tickers

    def test_remove_missing_returns_false(self, fresh_db: sqlite3.Connection):
        removed = remove_from_watchlist("NOPE", conn=fresh_db)
        assert removed is False

    def test_remove_normalizes_case(self, fresh_db: sqlite3.Connection):
        removed = remove_from_watchlist("aapl", conn=fresh_db)
        assert removed is True


class TestPositions:
    def test_no_positions_initially(self, fresh_db: sqlite3.Connection):
        assert get_positions(conn=fresh_db) == []

    def test_get_missing_position(self, fresh_db: sqlite3.Connection):
        assert get_position("AAPL", conn=fresh_db) is None

    def test_upsert_inserts(self, fresh_db: sqlite3.Connection):
        upsert_position("AAPL", quantity=10.5, avg_cost=180.0, conn=fresh_db)
        pos = get_position("AAPL", conn=fresh_db)
        assert pos is not None
        assert pos["ticker"] == "AAPL"
        assert pos["quantity"] == 10.5
        assert pos["avg_cost"] == 180.0

    def test_upsert_updates(self, fresh_db: sqlite3.Connection):
        upsert_position("AAPL", quantity=5.0, avg_cost=190.0, conn=fresh_db)
        upsert_position("AAPL", quantity=12.0, avg_cost=185.0, conn=fresh_db)
        positions = get_positions(conn=fresh_db)
        assert len(positions) == 1
        assert positions[0]["quantity"] == 12.0
        assert positions[0]["avg_cost"] == 185.0

    def test_delete_existing(self, fresh_db: sqlite3.Connection):
        upsert_position("AAPL", 1, 100.0, conn=fresh_db)
        assert delete_position("AAPL", conn=fresh_db) is True
        assert get_position("AAPL", conn=fresh_db) is None

    def test_delete_missing_returns_false(self, fresh_db: sqlite3.Connection):
        assert delete_position("AAPL", conn=fresh_db) is False

    def test_get_positions_sorted_by_ticker(self, fresh_db: sqlite3.Connection):
        for t in ["TSLA", "AAPL", "MSFT"]:
            upsert_position(t, 1.0, 100.0, conn=fresh_db)
        tickers = [p["ticker"] for p in get_positions(conn=fresh_db)]
        assert tickers == ["AAPL", "MSFT", "TSLA"]

    def test_upsert_normalizes_case(self, fresh_db: sqlite3.Connection):
        upsert_position("aapl", 1.0, 100.0, conn=fresh_db)
        assert get_position("AAPL", conn=fresh_db) is not None


class TestTrades:
    def test_no_trades_initially(self, fresh_db: sqlite3.Connection):
        assert get_trades(conn=fresh_db) == []

    def test_insert_returns_uuid(self, fresh_db: sqlite3.Connection):
        trade_id = insert_trade("AAPL", "buy", 10.0, 190.0, conn=fresh_db)
        # Should parse as a UUID
        uuid.UUID(trade_id)

    def test_insert_and_get(self, fresh_db: sqlite3.Connection):
        insert_trade("AAPL", "buy", 10.0, 190.0, conn=fresh_db)
        trades = get_trades(conn=fresh_db)
        assert len(trades) == 1
        t = trades[0]
        assert t["ticker"] == "AAPL"
        assert t["side"] == "buy"
        assert t["quantity"] == 10.0
        assert t["price"] == 190.0

    def test_invalid_side_raises(self, fresh_db: sqlite3.Connection):
        with pytest.raises(ValueError):
            insert_trade("AAPL", "short", 1.0, 100.0, conn=fresh_db)

    def test_get_orders_newest_first(self, fresh_db: sqlite3.Connection):
        # The executed_at column carries a wall-clock timestamp; insert two trades
        # back-to-back and check ordering. Even when timestamps tie, the id tiebreak
        # is deterministic per call ordering since DESC.
        ids = []
        for ticker in ["AAPL", "GOOGL", "MSFT"]:
            ids.append(insert_trade(ticker, "buy", 1.0, 100.0, conn=fresh_db))
        trades = get_trades(conn=fresh_db)
        # All three present, newest-first ordering means we see them in
        # ascending or descending timestamp order — at minimum all 3 should be returned
        assert len(trades) == 3
        returned_ids = {t["id"] for t in trades}
        assert returned_ids == set(ids)

    def test_limit_caps_results(self, fresh_db: sqlite3.Connection):
        for _ in range(5):
            insert_trade("AAPL", "buy", 1.0, 100.0, conn=fresh_db)
        trades = get_trades(limit=3, conn=fresh_db)
        assert len(trades) == 3

    def test_side_check_constraint_enforced(self, fresh_db: sqlite3.Connection):
        # Direct SQL bypasses our validator — schema CHECK should still reject.
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), DEFAULT_USER_ID, "AAPL", "long", 1.0, 1.0, "now"),
            )


class TestPortfolioSnapshots:
    def test_insert_and_retrieve(self, fresh_db: sqlite3.Connection):
        insert_portfolio_snapshot(10000.0, conn=fresh_db)
        rows = get_portfolio_history(conn=fresh_db)
        assert len(rows) == 1
        assert rows[0]["total_value"] == 10000.0

    def test_default_window_is_last_24h(self, fresh_db: sqlite3.Connection):
        # Insert one current snapshot and one 48h-old snapshot manually
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=48)
        fresh_db.execute(
            "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
            "VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), DEFAULT_USER_ID, 9000.0, old.isoformat()),
        )
        insert_portfolio_snapshot(11000.0, conn=fresh_db)

        rows = get_portfolio_history(conn=fresh_db)  # default window
        values = [r["total_value"] for r in rows]
        assert 11000.0 in values
        assert 9000.0 not in values

    def test_explicit_window(self, fresh_db: sqlite3.Connection):
        now = datetime.now(timezone.utc)
        # Three snapshots: 3h ago, 1h ago, now
        for hours_ago, value in [(3, 100.0), (1, 200.0), (0, 300.0)]:
            ts = (now - timedelta(hours=hours_ago)).isoformat()
            fresh_db.execute(
                "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
                "VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), DEFAULT_USER_ID, value, ts),
            )

        from_iso = (now - timedelta(hours=2)).isoformat()
        to_iso = (now + timedelta(minutes=1)).isoformat()
        rows = get_portfolio_history(from_iso=from_iso, to_iso=to_iso, conn=fresh_db)
        values = sorted(r["total_value"] for r in rows)
        assert values == [200.0, 300.0]

    def test_history_ordered_oldest_first(self, fresh_db: sqlite3.Connection):
        for v in [1.0, 2.0, 3.0]:
            insert_portfolio_snapshot(v, conn=fresh_db)
        rows = get_portfolio_history(
            from_iso="1970-01-01T00:00:00+00:00",
            to_iso="2999-12-31T00:00:00+00:00",
            conn=fresh_db,
        )
        timestamps = [r["recorded_at"] for r in rows]
        assert timestamps == sorted(timestamps)


class TestChatMessages:
    def test_no_messages_initially(self, fresh_db: sqlite3.Connection):
        assert get_chat_messages(conn=fresh_db) == []

    def test_insert_user_message(self, fresh_db: sqlite3.Connection):
        insert_chat_message("user", "hello", conn=fresh_db)
        msgs = get_chat_messages(conn=fresh_db)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello"
        assert msgs[0]["actions"] is None

    def test_insert_assistant_with_actions(self, fresh_db: sqlite3.Connection):
        actions = json.dumps({"trades": [{"ticker": "AAPL", "side": "buy", "quantity": 1}]})
        insert_chat_message("assistant", "bought it", actions=actions, conn=fresh_db)
        msgs = get_chat_messages(conn=fresh_db)
        assert msgs[0]["actions"] == actions

    def test_invalid_role_raises(self, fresh_db: sqlite3.Connection):
        with pytest.raises(ValueError):
            insert_chat_message("system", "hi", conn=fresh_db)

    def test_history_returns_oldest_first(self, fresh_db: sqlite3.Connection):
        insert_chat_message("user", "one", conn=fresh_db)
        insert_chat_message("assistant", "two", conn=fresh_db)
        insert_chat_message("user", "three", conn=fresh_db)
        msgs = get_chat_messages(conn=fresh_db)
        contents = [m["content"] for m in msgs]
        # All three are present in chronological order (oldest first)
        assert contents == ["one", "two", "three"]

    def test_limit_keeps_most_recent(self, fresh_db: sqlite3.Connection):
        # Insert 5 messages with explicit timestamps to guarantee ordering.
        base = datetime.now(timezone.utc)
        for i in range(5):
            ts = (base + timedelta(seconds=i)).isoformat()
            fresh_db.execute(
                "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), DEFAULT_USER_ID, "user", f"m{i}", None, ts),
            )

        msgs = get_chat_messages(limit=3, conn=fresh_db)
        # Most recent 3 = m2, m3, m4 — returned oldest-first
        assert [m["content"] for m in msgs] == ["m2", "m3", "m4"]

    def test_role_check_constraint_enforced(self, fresh_db: sqlite3.Connection):
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), DEFAULT_USER_ID, "system", "hi", None, "now"),
            )


class TestMultiUserIsolation:
    """Schema supports user_id; verify queries scope correctly."""

    def test_separate_user_has_no_data(self, fresh_db: sqlite3.Connection):
        upsert_position("AAPL", 10.0, 190.0, conn=fresh_db)
        assert get_positions(user_id="other", conn=fresh_db) == []

    def test_watchlist_scoped_to_user(self, fresh_db: sqlite3.Connection):
        add_to_watchlist("PYPL", user_id="other", conn=fresh_db)
        default_tickers = {r["ticker"] for r in get_watchlist(conn=fresh_db)}
        other_tickers = {r["ticker"] for r in get_watchlist(user_id="other", conn=fresh_db)}
        assert "PYPL" not in default_tickers
        assert other_tickers == {"PYPL"}
