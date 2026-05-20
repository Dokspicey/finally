"""Tests for the deterministic mock LLM (used when LLM_MOCK=true).

Per PLAN.md §9: tests must be able to exercise the chat endpoint without an
OpenAI key. Minimum guarantees:
- a benign hello reply (no actions) on generic input
- a trade-executing reply when the user message contains "buy 1 AAPL"
"""

from __future__ import annotations

from app.chat.mock import mock_chat_response


def test_mock_hello_returns_benign_message_no_actions():
    resp = mock_chat_response("hello")
    assert isinstance(resp.message, str) and resp.message.strip()
    assert resp.trades == []
    assert resp.watchlist_changes == []


def test_mock_buy_1_aapl_triggers_a_buy_trade():
    resp = mock_chat_response("Please buy 1 AAPL for me")
    assert len(resp.trades) == 1
    trade = resp.trades[0]
    assert trade.ticker == "AAPL"
    assert trade.side == "buy"
    assert trade.quantity == 1
    assert resp.watchlist_changes == []
    assert isinstance(resp.message, str) and resp.message.strip()


def test_mock_buy_1_aapl_case_insensitive():
    """'buy 1 aapl' (lowercase) should also trigger the buy."""
    resp = mock_chat_response("buy 1 aapl now")
    assert len(resp.trades) == 1
    assert resp.trades[0].ticker == "AAPL"


def test_mock_watch_pypl_adds_to_watchlist():
    resp = mock_chat_response("watch PYPL please")
    assert len(resp.watchlist_changes) == 1
    assert resp.watchlist_changes[0].ticker == "PYPL"
    assert resp.watchlist_changes[0].action == "add"


def test_mock_unrelated_message_falls_back_to_hello():
    """Anything that doesn't match a recognized intent gets the generic reply."""
    resp = mock_chat_response("what is your favorite color")
    assert resp.trades == []
    assert resp.watchlist_changes == []
    assert isinstance(resp.message, str) and resp.message.strip()
