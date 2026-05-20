"""Chat subsystem: LLM-powered conversational interface with auto-execution.

Public surface:
    chat_router         - FastAPI router mounted at /api/chat + /api/chat/history
    ChatLLMResponse     - Parsed structured-output payload from the LLM
"""

from .router import router as chat_router
from .schema import ChatLLMResponse, LLMTrade, LLMWatchlistChange

__all__ = [
    "chat_router",
    "ChatLLMResponse",
    "LLMTrade",
    "LLMWatchlistChange",
]
