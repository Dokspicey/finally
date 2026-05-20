"""GET /api/trades — trade history."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.db import get_db, get_trades

router = APIRouter(prefix="/api", tags=["trades"])

_MAX_LIMIT = 500


@router.get("/trades")
async def list_trades(
    limit: int = Query(default=100, ge=1, le=_MAX_LIMIT),
) -> dict[str, Any]:
    """Most-recent trades first."""
    if limit > _MAX_LIMIT:
        raise HTTPException(status_code=400, detail=f"limit cannot exceed {_MAX_LIMIT}")
    conn = get_db()
    try:
        rows = get_trades(limit=limit, conn=conn)
    finally:
        conn.close()
    return {
        "trades": [
            {
                "id": r["id"],
                "ticker": r["ticker"],
                "side": r["side"],
                "quantity": float(r["quantity"]),
                "price": float(r["price"]),
                "executed_at": r["executed_at"],
            }
            for r in rows
        ]
    }
