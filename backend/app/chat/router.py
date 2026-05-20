"""FastAPI router for /api/chat and /api/chat/history."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db import get_chat_messages, insert_chat_message

from .executor import execute_actions
from .llm import generate_chat_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

DEFAULT_HISTORY_LIMIT = 50
MAX_HISTORY_LIMIT = 500


class ChatBody(BaseModel):
    message: str = Field(..., min_length=1, description="User's chat message")


@router.post("")
async def post_chat(body: ChatBody) -> dict[str, Any]:
    """Send a message, get a structured response with any auto-executed actions."""
    user_text = body.message.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="message required")

    # Persist the user turn first so the LLM history-loader sees it on retries.
    insert_chat_message("user", user_text)

    try:
        parsed = await generate_chat_response(user_text)
    except Exception as exc:  # pragma: no cover - defensive: surfaces LLM errors as 502
        logger.exception("LLM call failed")
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}") from exc

    action_results = await execute_actions(parsed)

    trades_requested = [t.model_dump() for t in parsed.trades]
    watchlist_changes_requested = [w.model_dump() for w in parsed.watchlist_changes]

    # Persist the assistant turn first so the response can echo the canonical
    # row (id + created_at exactly as stored). Includes the full action record
    # (with any failures) so subsequent LLM turns see accurate history.
    actions_blob = json.dumps(
        {
            "trades": trades_requested,
            "watchlist_changes": watchlist_changes_requested,
            "action_results": action_results,
        },
        default=str,
    )
    assistant_id = insert_chat_message("assistant", parsed.message, actions=actions_blob)
    assistant_row = _fetch_chat_message_by_id(assistant_id)

    assistant_message: dict[str, Any] = {
        "id": assistant_row["id"],
        "role": assistant_row["role"],
        "content": assistant_row["content"],
        "actions": json.loads(assistant_row["actions"]) if assistant_row.get("actions") else None,
        "action_results": action_results,
        "created_at": assistant_row["created_at"],
    }

    return {
        "message": assistant_message,
        "trades_requested": trades_requested,
        "watchlist_changes_requested": watchlist_changes_requested,
        "action_results": action_results,
    }


def _fetch_chat_message_by_id(message_id: str) -> dict[str, Any]:
    """Read back a just-inserted chat row.

    We don't have a by-id helper in `app.db` (and that module is owned by
    `db-engineer` — we don't scatter SQL across the codebase). The newest few
    rows are cheap to scan; in our single-user model the row we just wrote is
    the most recent one anyway.
    """
    rows = get_chat_messages(limit=5)
    for row in reversed(rows):
        if row["id"] == message_id:
            return row
    raise RuntimeError(f"just-inserted chat message {message_id!r} not found")


@router.get("/history")
async def get_history(
    limit: int = Query(default=DEFAULT_HISTORY_LIMIT, ge=1, le=MAX_HISTORY_LIMIT),
) -> dict[str, Any]:
    """Return recent chat messages oldest-first (suitable for chat-panel replay)."""
    rows = get_chat_messages(limit=limit)
    messages: list[dict[str, Any]] = []
    for row in rows:
        actions_raw = row.get("actions")
        parsed: Any = None
        if actions_raw:
            try:
                parsed = json.loads(actions_raw)
            except (TypeError, ValueError):
                parsed = None
        messages.append(
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "actions": parsed,
                "created_at": row["created_at"],
            }
        )
    return {"messages": messages}
