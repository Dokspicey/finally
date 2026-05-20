# Bug Log

Append-only. `integration-tester` writes entries when an E2E run fails. Owner fixes, marks bug `RESOLVED`, then `integration-tester` re-runs.

## Entry template
```
### BUG-XXX — short title
- **Owner:** db-engineer | backend-api | llm-engineer | frontend-engineer | devops-engineer
- **Status:** OPEN | RESOLVED
- **Spec ref:** PLAN.md §N
- **Repro:** what action / test name
- **Expected:** ...
- **Actual:** ...
- **Notes:** logs, screenshots paths, etc.
```

---

### BUG-001 — chat `action_results` field-name mismatch (`type` vs `kind`)
- **Owner:** llm-engineer
- **Status:** RESOLVED (2026-05-19)
- **Spec ref:** PLAN.md §9 (action_results); API_CONTRACT.md (chat endpoints)
- **Repro:** `test/tests/chat.spec.ts` — send "buy 1 AAPL" via the chat panel and read `data-testid="chat-action-ok"`.
- **Expected:** inline confirmation reads e.g. `"✓ Bought 1 AAPL"` (frontend `ChatMessage.describeResult` branch for trade actions).
- **Actual:** inline confirmation reads `"✓ buyed 1 AAPL @ 190.00"` — the raw `note` from the backend.
- **Notes:** `backend/app/chat/executor.py` emits `{"type": "trade", ...}` in each `action_result` payload, but `frontend/src/types/api.ts` declares `ActionResult.kind: 'trade' | 'watchlist'` and `ChatMessage.tsx` switches on `r.kind`. With `kind` undefined the formatter falls through to `return r.note;` and the backend's raw `"buyed/selled <qty> <ticker> @ <px>"` string surfaces in the UI. Fix: change the backend payload key from `type` → `kind` in `executor.py` (`_run_trade` and `_run_watchlist`). Same key should also appear in any persisted `chat_messages.actions` rows; if history rows already used `type`, also update `mock.py`/`router.py` if they construct results elsewhere.
- **Resolution (2026-05-19, llm-engineer):** Renamed `"type"` → `"kind"` in `_run_trade` and `_run_watchlist` (only call sites — `mock.py` and `router.py` don't construct action_results directly). Added a `_PAST_TENSE = {"buy": "bought", "sell": "sold"}` map so the human-readable note uses correct English. Updated `tests/chat/test_router.py` to assert on `result["kind"]` plus added a new `test_chat_sell_uses_past_tense_sold_in_note` to lock in `"sold"` (the existing suite had no sell-via-chat coverage). Updated `planning/agents/API_CONTRACT.md` samples + added an edit-log entry. No DB migration needed — the E2E suite uses a fresh volume, and the older `"type"` rows in any leftover dev DB only affect frontend rendering of `/api/chat/history`, which now sees the new `"kind"` discriminator on every fresh row. Verified: `uv run --extra dev pytest backend/tests/chat/` → 34 passed (was 33 + 1 new sell test); full backend regression 198 passed; ruff clean.
- **Verification (2026-05-19, integration-tester):** Re-ran the e2e suite — the inline action confirmation now reads `"✓ Bought 1 AAPL"` as expected. Closing.

### BUG-002 — `POST /api/chat` response wraps `message` as a bare string, frontend expects an object
- **Owner:** llm-engineer
- **Status:** RESOLVED (2026-05-19)
- **Spec ref:** PLAN.md §9; API_CONTRACT.md (chat endpoints)
- **Repro:** `test/tests/chat.spec.ts` — send "buy 1 AAPL" via the chat panel, then look for `data-testid="chat-message-assistant"`.
- **Expected:** the assistant bubble renders with `data-testid="chat-message-assistant"` and shows the assistant's text + the inline `action_results` list.
- **Actual:** the bubble renders with `data-testid="chat-message-undefined"`, because `message.role` is `undefined` on the client. The inline `action_results` list (`✓ Bought 1 AAPL`) IS rendered, so the round-trip works — only the message bubble's metadata (role, id, content) is lost.
- **Notes:** A live `curl -X POST /api/chat -d '{"message":"buy 1 AAPL"}'` returns:
  ```json
  { "message": "On it — buying 1 AAPL.", "trades_requested": [...], "watchlist_changes_requested": [...], "action_results": [...] }
  ```
  But `frontend/src/types/api.ts` declares `ChatResponse { message: ChatMessage; action_results: ActionResult[] }` where `ChatMessage` is a full `{id, role, content, created_at}` object — matching what `GET /api/chat/history` returns. `ChatPanel.tsx` does `const assistant = { ...res.message, action_results: res.action_results }`. Spreading a string yields no own keys → `role`, `content`, `id` are all undefined, hence `chat-message-undefined` in the DOM.
  Two possible fixes:
  1. (Preferred) Backend wraps `message` as a `ChatMessage` object on the way out — `{ "message": { "id": "...", "role": "assistant", "content": "On it — buying 1 AAPL.", "created_at": "..." }, "action_results": [...] }`. Matches the frontend's existing types and parallels what `/api/chat/history` already returns. Update `API_CONTRACT.md` to make this explicit.
  2. Frontend wraps the string into a `ChatMessage` shape in `ChatPanel.tsx`. Cheaper, but leaves the on-wire contract ambiguous and re-invites the same drift.
- **Resolution (2026-05-19, llm-engineer):** Took fix #1 (backend wrap). `app/chat/router.py` now persists the assistant turn first via `insert_chat_message`, reads the row back through `get_chat_messages` (small added helper `_fetch_chat_message_by_id` lives in `router.py` since the role brief forbids modifying `app/db/`), and returns a `ChatMessage`-shaped dict at `response["message"]`: `{id, role: "assistant", content, actions (parsed dict), action_results, created_at}`. `actions` and `action_results` are also included so the frontend can render the bubble's inline confirmations without a second fetch. `action_results` is duplicated at the top level (same array reference) — kept for backward compatibility with the existing top-level access pattern. Updated `tests/chat/test_router.py::test_chat_generic_message_persists_user_and_assistant` to assert the new shape (`isinstance(message, dict)`, `role == "assistant"`, non-empty `id` + `content` + `created_at`, and `id` equality between payload and persisted row). Live-curl smoke check via `TestClient` confirms the wire shape matches the frontend's `ChatMessage` TS interface. Updated `API_CONTRACT.md` with the new sample + explanatory note + edit-log entry. Verified: backend/tests/chat/ → 34 passed, full backend regression → 198 passed, ruff clean.
- **Verification (2026-05-19, integration-tester):** Re-ran the full Playwright suite from a cold container start — **6/6 specs pass in ~7s** (chat, portfolio, smoke, sse-resilience, trade, watchlist). The chat assistant bubble now renders with `data-testid="chat-message-assistant"` and the round-trip "buy 1 AAPL" → inline `✓ Bought 1 AAPL` → AAPL position appearing in the table all succeed. Closing.
