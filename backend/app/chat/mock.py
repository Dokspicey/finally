"""Deterministic mock LLM used when LLM_MOCK=true.

Recognized intents (case-insensitive substring match against the user message):
- "buy <n> <ticker>"  -> emits a buy trade for that ticker/quantity
- "sell <n> <ticker>" -> emits a sell trade for that ticker/quantity
- "watch <ticker>"    -> emits a watchlist add
- "unwatch <ticker>"  -> emits a watchlist remove
- anything else       -> a benign hello reply with no actions

The matchers are intentionally simple — they only need to cover the scenarios
required by PLAN.md §9 + the E2E suite. Real LLM behavior lives in `llm.py`.
"""

from __future__ import annotations

import re

from .schema import ChatLLMResponse, LLMTrade, LLMWatchlistChange

_TRADE_RE = re.compile(r"\b(buy|sell)\s+(\d+(?:\.\d+)?)\s+([a-zA-Z][a-zA-Z0-9.\-]{0,9})\b")
_WATCH_RE = re.compile(r"\b(watch|unwatch)\s+([a-zA-Z][a-zA-Z0-9.\-]{0,9})\b")

_HELLO_REPLY = (
    "Hi! I'm FinAlly, your trading copilot. I can analyze your portfolio, "
    "manage your watchlist, and execute trades. Ask me anything."
)


def mock_chat_response(user_message: str) -> ChatLLMResponse:
    """Return a deterministic ChatLLMResponse based on the user's message."""
    text = user_message.lower()
    trades: list[LLMTrade] = []
    watchlist_changes: list[LLMWatchlistChange] = []

    for match in _TRADE_RE.finditer(text):
        side, qty_str, ticker = match.group(1), match.group(2), match.group(3)
        trades.append(LLMTrade(ticker=ticker, side=side, quantity=float(qty_str)))

    for match in _WATCH_RE.finditer(text):
        verb, ticker = match.group(1), match.group(2)
        action = "add" if verb == "watch" else "remove"
        watchlist_changes.append(LLMWatchlistChange(ticker=ticker, action=action))

    if trades:
        first = trades[0]
        message = (
            f"On it — {first.side}ing {first.quantity:g} {first.ticker}"
            + ("." if len(trades) == 1 else f" (plus {len(trades) - 1} more).")
        )
    elif watchlist_changes:
        first = watchlist_changes[0]
        verb = "Adding" if first.action == "add" else "Removing"
        preposition = "to" if first.action == "add" else "from"
        message = f"{verb} {first.ticker} {preposition} your watchlist."
    else:
        message = _HELLO_REPLY

    return ChatLLMResponse(message=message, trades=trades, watchlist_changes=watchlist_changes)
