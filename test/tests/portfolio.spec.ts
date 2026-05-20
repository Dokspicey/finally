import { test, expect } from '@playwright/test';
import { resetState, waitForFirstPrice } from './helpers';

test.describe('portfolio renders — treemap + P&L chart', () => {
  test.beforeEach(async ({ request }) => {
    await resetState(request);
  });

  test('heatmap shows rectangle and P&L chart has >=2 points after a trade', async ({
    page,
    request,
  }) => {
    await page.goto('/');
    await waitForFirstPrice(page);

    // Buy 1 NVDA via the API so we don't depend on UI timing for this spec.
    const res = await request.post('/api/portfolio/trade', {
      data: { ticker: 'NVDA', side: 'buy', quantity: 1 },
    });
    expect(res.ok()).toBeTruthy();

    // Refresh portfolio data — the trade-bar path normally triggers refreshPortfolio
    // for us, but since we placed the order via the API we reload to pull it in.
    await page.reload();
    await waitForFirstPrice(page);

    // Treemap (Allocation panel) renders an SVG group for the held ticker.
    const allocationPanel = page.locator('div.panel', { has: page.getByText('Allocation', { exact: true }) });
    await expect(allocationPanel).toBeVisible();
    await expect(allocationPanel.locator('svg g')).toHaveCount(1, { timeout: 5_000 });

    // P&L chart header reports its point count — needs >=2 (startup snapshot + post-trade).
    const pnlPanel = page.locator('div.panel', { has: page.getByText('Portfolio Value', { exact: true }) });
    await expect(pnlPanel).toBeVisible();
    await expect
      .poll(async () => {
        const text = (await pnlPanel.locator('text=/\\d+\\s+pts/').textContent()) ?? '';
        const match = text.match(/(\d+)\s+pts/);
        return match ? Number(match[1]) : 0;
      }, { timeout: 10_000, message: 'expected >=2 P&L data points' })
      .toBeGreaterThanOrEqual(2);
  });
});
