# FinAlly — Playwright E2E

End-to-end suite that drives the production Docker image of the FinAlly
trading workstation. Implements every scenario from `planning/PLAN.md` §12.

## Layout

- `docker-compose.test.yml` — spins up the `finally` image on host port `8001`
  with hermetic env (`LLM_MOCK=true`, `MASSIVE_API_KEY=""`, throwaway SQLite
  volume). Pins env values inline so the user's local `.env` cannot leak in.
- `playwright.config.ts` — Chromium only, single worker (state is shared via
  one container; specs reset via `helpers.ts`), baseURL `http://localhost:8001`.
- `tests/helpers.ts` — `resetState()` (liquidate positions + restore the 10
  default watchlist tickers) and small price/cash readers.
- `tests/*.spec.ts` — one spec per PLAN §12 scenario:
  - `smoke.spec.ts` — 10 default tickers, $10k cash, streaming prices.
  - `watchlist.spec.ts` — add then remove a ticker via the form / × button.
  - `trade.spec.ts` — buy 1 AAPL then sell 1 AAPL via the trade bar.
  - `portfolio.spec.ts` — heatmap rectangle + ≥2 P&L chart points after a trade.
  - `chat.spec.ts` — LLM_MOCK "buy 1 AAPL" → inline action confirmation +
    position appears in the table.
  - `sse-resilience.spec.ts` — one-shot route abort proves the EventSource
    auto-reconnect path restores the green status dot.
- `wait-for-health.sh` — blocks until `/api/health` is 200; used by `npm run up`.

## Running

```bash
cd test
npm install                      # one-time
npx playwright install chromium  # one-time
npm run up                       # build + start container, wait for healthy
npm test                         # run all specs
npm run down                     # stop container, remove volume
```

Or end-to-end in one command:

```bash
npm run e2e
```

## On failure

`integration-tester` appends an entry to `planning/agents/BUGS.md` (template at
the top of that file) and messages the suspected owner. The bug is closed once
the spec is green again on a re-run.
