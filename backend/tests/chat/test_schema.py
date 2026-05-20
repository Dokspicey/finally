"""Tests for the LLM response schema parser (Pydantic models).

These are unit tests on the data layer: parsing raw JSON dicts into typed
`ChatLLMResponse` objects, normalizing ticker case + side, defaulting empty
lists, rejecting malformed payloads.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.chat.schema import ChatLLMResponse, LLMTrade, LLMWatchlistChange


def test_parse_minimal_response_just_a_message():
    parsed = ChatLLMResponse.model_validate({"message": "Hello there!"})
    assert parsed.message == "Hello there!"
    assert parsed.trades == []
    assert parsed.watchlist_changes == []


def test_parse_response_with_trades():
    parsed = ChatLLMResponse.model_validate(
        {
            "message": "Bought.",
            "trades": [{"ticker": "aapl", "side": "BUY", "quantity": 1.5}],
        }
    )
    assert len(parsed.trades) == 1
    assert parsed.trades[0].ticker == "AAPL"  # upper-cased
    assert parsed.trades[0].side == "buy"  # lower-cased
    assert parsed.trades[0].quantity == 1.5


def test_parse_response_with_watchlist_changes():
    parsed = ChatLLMResponse.model_validate(
        {
            "message": "Watchlist updated.",
            "watchlist_changes": [
                {"ticker": "pypl", "action": "ADD"},
                {"ticker": "tsla", "action": "remove"},
            ],
        }
    )
    assert len(parsed.watchlist_changes) == 2
    assert parsed.watchlist_changes[0].ticker == "PYPL"
    assert parsed.watchlist_changes[0].action == "add"
    assert parsed.watchlist_changes[1].action == "remove"


def test_missing_message_rejected():
    with pytest.raises(ValidationError):
        ChatLLMResponse.model_validate({"trades": []})


def test_unknown_side_rejected():
    with pytest.raises(ValidationError):
        ChatLLMResponse.model_validate(
            {"message": "x", "trades": [{"ticker": "AAPL", "side": "swap", "quantity": 1}]}
        )


def test_unknown_watchlist_action_rejected():
    with pytest.raises(ValidationError):
        ChatLLMResponse.model_validate(
            {
                "message": "x",
                "watchlist_changes": [{"ticker": "AAPL", "action": "ignore"}],
            }
        )


def test_zero_or_negative_quantity_rejected():
    with pytest.raises(ValidationError):
        ChatLLMResponse.model_validate(
            {"message": "x", "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 0}]}
        )


def test_individual_trade_model_normalizes():
    """Sanity: LLMTrade can be constructed directly (used by the mock)."""
    trade = LLMTrade(ticker="msft", side="Buy", quantity=2)
    assert trade.ticker == "MSFT"
    assert trade.side == "buy"


def test_individual_watchlist_change_model_normalizes():
    wc = LLMWatchlistChange(ticker="pypl", action="Add")
    assert wc.ticker == "PYPL"
    assert wc.action == "add"
