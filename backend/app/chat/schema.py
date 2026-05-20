"""Pydantic models for the LLM structured-output payload (PLAN.md §9).

The LLM is instructed to respond with JSON of the form:

    {
      "message": "Your conversational reply",
      "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10.5}],
      "watchlist_changes": [{"ticker": "PYPL", "action": "add"}]
    }

These models validate and normalize that payload (upper-cases ticker, lower-cases
side/action). Invalid payloads raise pydantic's `ValidationError`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LLMTrade(BaseModel):
    """One trade the LLM wants the backend to execute."""

    model_config = ConfigDict(str_strip_whitespace=True)

    ticker: str
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)

    @field_validator("ticker", mode="before")
    @classmethod
    def _normalize_ticker(cls, v: object) -> object:
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("side", mode="before")
    @classmethod
    def _normalize_side(cls, v: object) -> object:
        return v.strip().lower() if isinstance(v, str) else v


class LLMWatchlistChange(BaseModel):
    """One watchlist mutation requested by the LLM."""

    model_config = ConfigDict(str_strip_whitespace=True)

    ticker: str
    action: Literal["add", "remove"]

    @field_validator("ticker", mode="before")
    @classmethod
    def _normalize_ticker(cls, v: object) -> object:
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("action", mode="before")
    @classmethod
    def _normalize_action(cls, v: object) -> object:
        return v.strip().lower() if isinstance(v, str) else v


class ChatLLMResponse(BaseModel):
    """The full structured response from the LLM."""

    model_config = ConfigDict(str_strip_whitespace=True)

    message: str
    trades: list[LLMTrade] = Field(default_factory=list)
    watchlist_changes: list[LLMWatchlistChange] = Field(default_factory=list)
