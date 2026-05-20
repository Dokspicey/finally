import { expect, type Page, type APIRequestContext } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:8001';

export const DEFAULT_TICKERS = [
  'AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA',
  'NVDA', 'META', 'JPM', 'V', 'NFLX',
];

/**
 * Reset the backend to a fresh seeded state between specs.
 *
 * The DB layer lazy-inits on first request, so we wipe state by:
 *   1) reading current positions and selling them all back to the simulator
 *   2) removing any non-default watchlist tickers, restoring missing defaults
 *   3) (cash drifts on round-trip trades but the suite tolerates +/- a few $)
 *
 * This avoids needing a backend reset endpoint (the API contract has none)
 * while keeping every spec independent.
 */
export async function resetState(request: APIRequestContext): Promise<void> {
  // 1. Liquidate any positions.
  const port = await request.get(`${BASE_URL}/api/portfolio`);
  if (port.ok()) {
    const body = await port.json();
    for (const pos of body.positions ?? []) {
      if (pos.quantity > 0) {
        await request.post(`${BASE_URL}/api/portfolio/trade`, {
          data: { ticker: pos.ticker, side: 'sell', quantity: pos.quantity },
        });
      }
    }
  }

  // 2. Restore the watchlist to the default 10 tickers.
  const wl = await request.get(`${BASE_URL}/api/watchlist`);
  if (wl.ok()) {
    const body = await wl.json();
    const current = new Set<string>((body.watchlist ?? []).map((w: { ticker: string }) => w.ticker));
    for (const ticker of current) {
      if (!DEFAULT_TICKERS.includes(ticker)) {
        await request.delete(`${BASE_URL}/api/watchlist/${ticker}`);
      }
    }
    for (const ticker of DEFAULT_TICKERS) {
      if (!current.has(ticker)) {
        await request.post(`${BASE_URL}/api/watchlist`, { data: { ticker } });
      }
    }
  }
}

/**
 * Wait until at least one watchlist row reports a non-"—" price.
 * The simulator streams every ~500ms; the cache is populated at startup
 * but the SSE snapshot arrives a beat after page load.
 *
 * Note: the page renders both a desktop and a mobile Watchlist component, so
 * every `data-testid="watchlist-row-*"` resolves to two DOM nodes. We always
 * read from `.first()` to avoid strict-mode violations.
 */
export async function waitForFirstPrice(page: Page): Promise<void> {
  await expect
    .poll(async () => {
      const cells = page.locator('[data-testid^="watchlist-row-"] > div').nth(1);
      const text = await cells.first().textContent();
      return text?.trim() ?? '';
    }, { timeout: 15_000, message: 'no streaming price observed' })
    .not.toBe('—');
}

/**
 * Read the live price for a ticker from the watchlist row text.
 * Returns null if the cell is still '—'. Scoped to `.first()` to dodge the
 * desktop+mobile DOM duplication described above.
 */
export async function readWatchlistPrice(page: Page, ticker: string): Promise<number | null> {
  const row = page.getByTestId(`watchlist-row-${ticker}`).first();
  const priceCell = row.locator('> div').nth(1);
  const text = (await priceCell.textContent())?.trim() ?? '';
  if (!text || text === '—') return null;
  const cleaned = text.replace(/[$,]/g, '');
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

/**
 * Read the cash balance from the header.
 * The header renders a "Cash" Stat with formatted USD.
 */
export async function readHeaderCash(page: Page): Promise<number | null> {
  const cashLabel = page.locator('header').getByText('Cash', { exact: true });
  const value = cashLabel.locator('xpath=following-sibling::span[1]');
  const text = (await value.textContent())?.trim() ?? '';
  const cleaned = text.replace(/[$,]/g, '');
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

export { BASE_URL };
