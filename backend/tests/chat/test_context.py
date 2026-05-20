"""Tests for the chat context builder.

The context builder snapshots the user's current state (cash, positions w/ live
prices, watchlist, total portfolio value) and pulls the most recent 20 chat
messages from the DB (per PLAN.md §9 sliding-window rule). It's used to assemble
the prompt sent to the LLM.
"""

from __future__ import annotations

import json

from app.chat.context import build_chat_context
from app.db import (
    add_to_watchlist,
    insert_chat_message,
    update_cash_balance,
    upsert_position,
)


def test_context_includes_cash_and_total_value(db_path, fake_source):
    fake_source.seed_price("AAPL", 150.0)
    upsert_position("AAPL", 2.0, 100.0)
    update_cash_balance(5000.0)

    ctx = build_chat_context()
    assert ctx["cash_balance"] == 5000.0
    # 2 shares * $150 + $5000 = $5300
    assert ctx["total_value"] == 5300.0


def test_context_position_has_live_pnl_from_price_cache(db_path, fake_source):
    fake_source.seed_price("AAPL", 150.0)
    upsert_position("AAPL", 2.0, 100.0)

    ctx = build_chat_context()
    positions = ctx["positions"]
    assert len(positions) == 1
    aapl = positions[0]
    assert aapl["ticker"] == "AAPL"
    assert aapl["quantity"] == 2.0
    assert aapl["avg_cost"] == 100.0
    assert aapl["current_price"] == 150.0
    # unrealized P&L = 2 * (150 - 100) = 100
    assert aapl["unrealized_pnl"] == 100.0


def test_context_position_falls_back_to_avg_cost_when_no_price(db_path, fake_source):
    """PLAN §7 valuation fallback."""
    upsert_position("OBSCURE", 1.0, 75.0)  # no price seeded

    ctx = build_chat_context()
    positions = ctx["positions"]
    assert positions[0]["current_price"] == 75.0
    assert positions[0]["unrealized_pnl"] == 0.0


def test_context_includes_watchlist_with_live_prices(db_path, fake_source):
    add_to_watchlist("MSFT")
    fake_source.seed_price("MSFT", 400.0)

    ctx = build_chat_context()
    watch = ctx["watchlist"]
    msft_rows = [w for w in watch if w["ticker"] == "MSFT"]
    assert len(msft_rows) == 1
    assert msft_rows[0]["price"] == 400.0


def test_context_loads_last_20_chat_messages_oldest_first(db_path):
    """Sliding window of 20 — older messages excluded, order oldest-first."""
    for i in range(25):
        insert_chat_message("user", f"msg-{i}")

    ctx = build_chat_context()
    history = ctx["recent_messages"]
    assert len(history) == 20
    # oldest of the 20 most recent = msg-5
    assert history[0]["content"] == "msg-5"
    assert history[-1]["content"] == "msg-24"


def test_context_parses_actions_json_in_history(db_path):
    """If a stored message has an actions JSON blob, it's parsed for the LLM."""
    actions = {"trades": [{"ticker": "AAPL", "side": "buy", "quantity": 1}]}
    insert_chat_message("user", "buy 1 AAPL")
    insert_chat_message("assistant", "Bought.", actions=json.dumps(actions))

    ctx = build_chat_context()
    history = ctx["recent_messages"]
    last = history[-1]
    assert last["role"] == "assistant"
    assert last["actions"] == actions


def test_context_handles_empty_history(db_path):
    ctx = build_chat_context()
    assert ctx["recent_messages"] == []
