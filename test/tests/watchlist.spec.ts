import { test, expect } from '@playwright/test';
import { resetState, waitForFirstPrice } from './helpers';

test.describe('watchlist add / remove', () => {
  test.beforeEach(async ({ request }) => {
    await resetState(request);
  });

  test('add a new ticker, then remove it', async ({ page }) => {
    await page.goto('/');
    await waitForFirstPrice(page);

    const newTicker = 'PYPL';

    // The page mounts the Watchlist twice (desktop + mobile). Every selector
    // is scoped to `.first()` so strict-mode locators are satisfied.

    // Sanity: ticker is not present before we add it.
    await expect(page.getByTestId(`watchlist-row-${newTicker}`)).toHaveCount(0);

    // Add via the watchlist form (aria-label="Add ticker").
    await page.getByLabel('Add ticker').first().fill(newTicker);
    await page.getByRole('button', { name: 'Add' }).first().click();
    await expect(page.getByTestId(`watchlist-row-${newTicker}`).first()).toBeVisible();

    // Remove via the per-row "× Remove PYPL" button. The row itself has
    // role="button" whose accessible name contains "Remove PYPL" (it's the row
    // text + child button label concatenated), so we scope to the row and
    // pick the inner button by aria-label to avoid clicking the row.
    const row = page.getByTestId(`watchlist-row-${newTicker}`).first();
    await row.locator(`button[aria-label="Remove ${newTicker}"]`).click();
    await expect(page.getByTestId(`watchlist-row-${newTicker}`)).toHaveCount(0);
  });
});
