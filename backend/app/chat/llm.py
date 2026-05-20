"""LiteLLM caller — talks to OpenAI gpt-4o with Structured Outputs.

Behavior:
- When `LLM_MOCK=true`, returns deterministic fixtures from `mock.py` and never
  contacts OpenAI. This is what test runs + CI use.
- Otherwise, calls `litellm.acompletion(model='gpt-4o', response_format=...)`
  with a JSON schema derived from `ChatLLMResponse`, parses the result into the
  Pydantic model, and returns it.

The schema and system prompt live here. `router.py` is purely orchestration.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from .context import build_chat_context
from .mock import mock_chat_response
from .schema import ChatLLMResponse

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are FinAlly, an AI trading assistant. The user runs a simulated "
    "portfolio with virtual cash; trades you request will execute automatically. "
    "Be concise and data-driven. Analyze portfolio concentration and P&L when "
    "asked. Manage the watchlist proactively. Respond with valid structured "
    "JSON only. If the user asks you to trade, include the trade in the trades "
    "array. Use the watchlist_changes array to add or remove tickers."
)


def _is_mock_mode() -> bool:
    return os.environ.get("LLM_MOCK", "").strip().lower() == "true"


def _serialize_context(ctx: dict[str, Any]) -> str:
    """Compact JSON-encoded snapshot for the prompt — keeps tokens predictable."""
    return json.dumps(ctx, default=str, separators=(",", ":"))


def _build_messages(context: dict[str, Any], user_message: str) -> list[dict[str, str]]:
    """Assemble the chat messages for the LLM call.

    Order: system prompt, current portfolio context, last 20 turns, new user msg.
    """
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    portfolio_blob = {
        "cash_balance": context["cash_balance"],
        "total_value": context["total_value"],
        "positions": context["positions"],
        "watchlist": context["watchlist"],
    }
    messages.append(
        {
            "role": "system",
            "content": "Current portfolio snapshot: " + _serialize_context(portfolio_blob),
        }
    )
    for m in context.get("recent_messages", []):
        if m["role"] in ("user", "assistant"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_message})
    return messages


async def generate_chat_response(user_message: str) -> ChatLLMResponse:
    """Call the LLM (or mock) and return a parsed `ChatLLMResponse`."""
    if _is_mock_mode():
        return mock_chat_response(user_message)

    # Real LLM path — imported lazily so the test suite never needs litellm
    # to be importable for mock-mode test runs.
    import litellm  # type: ignore[import-untyped]

    context = build_chat_context()
    messages = _build_messages(context, user_message)

    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "chat_response",
            "schema": ChatLLMResponse.model_json_schema(),
            "strict": False,
        },
    }

    completion = await litellm.acompletion(
        model="gpt-4o",
        messages=messages,
        response_format=response_format,
    )
    raw = completion.choices[0].message.content
    if not raw:
        raise RuntimeError("LLM returned empty response")
    payload = json.loads(raw)
    return ChatLLMResponse.model_validate(payload)
