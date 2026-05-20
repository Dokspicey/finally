import { test, expect } from '@playwright/test';
import { readHeaderCash, readWatchlistPrice, resetState, waitForFirstPrice } from './helpers';

test.describe('trade buy / sell', () => {
  test.beforeEach(async ({ request }) => {
    await resetState(request);
  });

  test('buy 1 AAPL, sell 1 AAPL — cash and position update', async ({ page }) => {
    await page.goto('/');
    await waitForFirstPrice(page);

    // Click AAPL so the trade bar defaults to AAPL.
    // The desktop+mobile Watchlist duplication forces a `.first()`.
    await page.getByTestId('watchlist-row-AAPL').first().click();

    const beforeCash = await readHeaderCash(page);
    const livePrice = await readWatchlistPrice(page, 'AAPL');
    expect(beforeCash).not.toBeNull();
    expect(livePrice).not.toBeNull();

    // Quantity input is pre-filled with "1" — leave it.
    await page.getByLabel('Trade quantity').fill('1');
    await page.getByRole('button', { name: 'Buy' }).click();

    // Trade-bar status message confirms the buy.
    await expect(page.getByRole('status')).toContainText(/Bought 1 AAPL/i);

    // Position row appears in the Positions table.
    const aaplCell = page.getByRole('cell', { name: 'AAPL', exact: true });
    await expect(aaplCell.first()).toBeVisible({ timeout: 5_000 });

    // Cash decreased by ~AAPL price (simulator drifts so allow a $5 window).
    await expect
      .poll(async () => await readHeaderCash(page), {
        timeout: 5_000,
        message: 'expected cash to decrease after buy',
      })
      .toBeLessThan(beforeCash! - 1);
    const afterBuyCash = await readHeaderCash(page);
    expect(afterBuyCash!).toBeGreaterThan(beforeCash! - livePrice! - 50);

    // Sell back the 1 share.
    await page.getByLabel('Trade quantity').fill('1');
    await page.getByRole('button', { name: 'Sell' }).click();
    await expect(page.getByRole('status')).toContainText(/Sold 1 AAPL/i);

    // Position row disappears (sell zeroes the position out per API contract).
    await expect(aaplCell).toHaveCount(0, { timeout: 5_000 });

    // Cash recovers — should be within $5 of the original (simulator drift).
    await expect
      .poll(async () => await readHeaderCash(page), {
        timeout: 5_000,
        message: 'cash should rebound after sell',
      })
      .toBeGreaterThan(afterBuyCash! + 1);
  });
});
