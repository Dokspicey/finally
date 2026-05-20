"""End-to-end tests for /api/chat and /api/chat/history.

All tests run with LLM_MOCK=true (via the autouse `llm_mock` fixture in conftest).
This means the responses are driven by `app.chat.mock.mock_chat_response`.

What we cover here:
- generic message: assistant message persisted, no actions
- mock-triggered trade: trade executes, position appears, action_results
  surfaces success, response payload matches the API contract
- mock-triggered watchlist add / remove
- failure path: when execute_trade raises (insufficient cash), action_results
  records the failure and the assistant message is still persisted
- history endpoint: returns oldest-first, default limit 50, custom limit honored
- request validation
"""

from __future__ import annotations

import json

from app.db import get_chat_messages, get_positions, get_user_profile, get_watchlist


def _send(client, message: str):
    return client.post("/api/chat", json={"message": message})


# ---------- generic round-trip ----------


def test_chat_generic_message_persists_user_and_assistant(chat_client):
    """BUG-002: `message` in the response must be a full ChatMessage object,
    matching the shape `/api/chat/history` returns and the frontend `ChatMessage`
    TypeScript interface. Spreading a string in the frontend yields no own keys
    and the assistant bubble loses its role/id/content."""
    resp = _send(chat_client, "hello there")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert "message" in body
    message = body["message"]
    assert isinstance(message, dict), f"expected ChatMessage object, got {type(message).__name__}"
    assert message["role"] == "assistant"
    assert isinstance(message["content"], str) and message["content"].strip()
    assert isinstance(message["id"], str) and message["id"]
    assert isinstance(message["created_at"], str) and message["created_at"]

    assert body["action_results"] == []
    assert body["trades_requested"] == []
    assert body["watchlist_changes_requested"] == []

    msgs = get_chat_messages(limit=10)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"] == "hello there"
    assert msgs[1]["content"] == message["content"]
    # The id returned in the payload is the same one persisted to chat_messages.
    assert msgs[1]["id"] == message["id"]


def test_chat_response_shape_has_required_fields(chat_client):
    body = _send(chat_client, "hello").json()
    for field in ("message", "trades_requested", "watchlist_changes_requested", "action_results"):
        assert field in body, f"missing field {field}: {body}"


# ---------- request validation ----------


def test_chat_empty_message_rejected(chat_client):
    resp = _send(chat_client, "")
    assert resp.status_code in (400, 422)


def test_chat_missing_message_rejected(chat_client):
    resp = chat_client.post("/api/chat", json={})
    assert resp.status_code == 422  # FastAPI/pydantic body validation


# ---------- trade auto-execution ----------


def test_chat_buy_1_aapl_executes_trade(chat_client, fake_source):
    fake_source.seed_price("AAPL", 100.0)

    resp = _send(chat_client, "please buy 1 AAPL")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert len(body["trades_requested"]) == 1
    assert body["trades_requested"][0] == {"ticker": "AAPL", "side": "buy", "quantity": 1.0}

    assert len(body["action_results"]) == 1
    result = body["action_results"][0]
    # BUG-001: discriminator key is "kind" to match the frontend TS type.
    assert result["kind"] == "trade"
    assert result["success"] is True
    assert result["ticker"] == "AAPL"
    # Past-tense grammar in the human-readable note.
    assert "bought" in result["note"].lower()
    assert "buyed" not in result["note"].lower()
    assert "trade" in result and result["trade"]["price"] == 100.0

    positions = get_positions()
    assert len(positions) == 1 and positions[0]["ticker"] == "AAPL"

    profile = get_user_profile()
    assert profile["cash_balance"] == 9900.0


def test_chat_sell_uses_past_tense_sold_in_note(chat_client, fake_source):
    """BUG-001: sell-side note must say 'sold' (not 'selled')."""
    fake_source.seed_price("AAPL", 100.0)
    _send(chat_client, "buy 1 AAPL")

    resp = _send(chat_client, "sell 1 AAPL")
    assert resp.status_code == 200
    result = resp.json()["action_results"][0]
    assert result["kind"] == "trade"
    assert result["success"] is True
    assert "sold" in result["note"].lower()
    assert "selled" not in result["note"].lower()


def test_chat_failed_trade_records_action_result_no_llm_reinvocation(chat_client, fake_source):
    """Insufficient cash — failure flows through action_results, no LLM retry."""
    fake_source.seed_price("AAPL", 1000000.0)  # absurdly expensive

    resp = _send(chat_client, "buy 1 AAPL")
    assert resp.status_code == 200
    body = resp.json()

    assert len(body["action_results"]) == 1
    result = body["action_results"][0]
    assert result["success"] is False
    assert result["note"] == "insufficient cash"

    # Cash and positions unchanged
    assert get_user_profile()["cash_balance"] == 10000.0
    assert get_positions() == []

    # Persistence: assistant message stored with failed action embedded
    msgs = get_chat_messages(limit=10)
    assistant = msgs[-1]
    assert assistant["role"] == "assistant"
    stored = json.loads(assistant["actions"])
    assert any(r.get("success") is False for r in stored["action_results"])


# ---------- watchlist auto-execution ----------


def test_chat_watch_pypl_adds_to_watchlist(chat_client, fake_source):
    resp = _send(chat_client, "watch PYPL")
    assert resp.status_code == 200
    body = resp.json()

    assert len(body["watchlist_changes_requested"]) == 1
    assert body["watchlist_changes_requested"][0] == {"ticker": "PYPL", "action": "add"}

    assert any(
        r["kind"] == "watchlist" and r["success"] and r["ticker"] == "PYPL"
        for r in body["action_results"]
    )

    tickers = {row["ticker"] for row in get_watchlist()}
    assert "PYPL" in tickers


def test_chat_unwatch_aapl_removes_from_watchlist(chat_client, fake_source):
    # AAPL is seeded by default
    resp = _send(chat_client, "unwatch AAPL")
    assert resp.status_code == 200

    tickers = {row["ticker"] for row in get_watchlist()}
    assert "AAPL" not in tickers


# ---------- /api/chat/history ----------


def test_chat_history_returns_oldest_first(chat_client):
    _send(chat_client, "first")
    _send(chat_client, "second")
    body = chat_client.get("/api/chat/history").json()

    msgs = body["messages"]
    # Two user + two assistant
    assert len(msgs) == 4
    assert msgs[0]["content"] == "first"
    assert msgs[-1]["role"] == "assistant"


def test_chat_history_respects_limit(chat_client):
    for i in range(5):
        _send(chat_client, f"msg-{i}")
    body = chat_client.get("/api/chat/history", params={"limit": 3}).json()
    assert len(body["messages"]) == 3


def test_chat_history_returns_actions_as_parsed_dict(chat_client, fake_source):
    fake_source.seed_price("AAPL", 100.0)
    _send(chat_client, "buy 1 AAPL")

    body = chat_client.get("/api/chat/history").json()
    assistant = body["messages"][-1]
    assert assistant["role"] == "assistant"
    assert isinstance(assistant["actions"], dict)
    assert "action_results" in assistant["actions"]


def test_chat_history_empty_when_no_messages(chat_client):
    body = chat_client.get("/api/chat/history").json()
    assert body == {"messages": []}
