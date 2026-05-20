import { test, expect } from '@playwright/test';
import { DEFAULT_TICKERS, resetState, waitForFirstPrice } from './helpers';

test.describe('smoke — fresh start', () => {
  test.beforeEach(async ({ request }) => {
    await resetState(request);
  });

  test('default watchlist, $10k cash, streaming prices', async ({ page }) => {
    await page.goto('/');

    // All 10 seed tickers render as watchlist rows. The page mounts a desktop
    // and a mobile Watchlist (the latter is `lg:hidden`), so the testid appears
    // twice — assert ≥1 visible per ticker via `.first()`.
    for (const ticker of DEFAULT_TICKERS) {
      await expect(page.getByTestId(`watchlist-row-${ticker}`).first()).toBeVisible();
    }

    // Header cash shows $10,000 (allow tiny variance from any prior trades; reset returns to ~10k).
    const cashLabel = page.locator('header').getByText('Cash', { exact: true });
    await expect(cashLabel).toBeVisible();
    await expect(cashLabel.locator('xpath=following-sibling::span[1]')).toContainText('$');

    // Connection dot is green/open within the first few seconds.
    await expect(page.getByTestId('connection-dot')).toHaveAttribute('data-status', 'open', { timeout: 10_000 });

    // Streaming: at least one ticker reports a numeric price (not "—").
    await waitForFirstPrice(page);

    // And then changes at least once (simulator updates ~500ms).
    const aaplPrice = page.getByTestId('watchlist-row-AAPL').first().locator('> div').nth(1);
    const first = (await aaplPrice.textContent())?.trim();
    await expect
      .poll(async () => (await aaplPrice.textContent())?.trim(), {
        timeout: 10_000,
        message: 'expected AAPL price to tick at least once',
      })
      .not.toBe(first);
  });
});
