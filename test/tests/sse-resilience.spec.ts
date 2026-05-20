import { test, expect } from '@playwright/test';
import { resetState, waitForFirstPrice } from './helpers';

test.describe('SSE resilience', () => {
  test.beforeEach(async ({ request }) => {
    await resetState(request);
  });

  test('dropping and restoring the SSE stream → status dot recovers', async ({
    page,
    context,
  }) => {
    // Strategy: install a one-shot route handler that aborts the first SSE
    // request the page makes (causing EventSource.onerror and the connection
    // status dot to leave 'open'), then steps out of the way so the browser's
    // built-in EventSource auto-retry — driven by the server's `retry: 1000`
    // directive — succeeds on the next attempt.
    //
    // Per the HTML spec, EventSource only auto-reconnects on connection-level
    // failures (not HTTP 4xx/5xx, which set readyState=CLOSED permanently).
    // `route.abort('failed')` returns a generic network failure, which the
    // browser treats as a transient error and retries.
    let aborted = false;
    await context.route('**/api/stream/prices', async (route) => {
      if (!aborted) {
        aborted = true;
        await route.abort('failed');
        return;
      }
      await route.continue();
    });

    await page.goto('/');

    const dot = page.getByTestId('connection-dot');

    // First SSE attempt is aborted; EventSource fires onerror and the hook
    // reports either 'connecting' or 'closed'.
    await expect
      .poll(async () => await dot.getAttribute('data-status'), {
        timeout: 10_000,
        message: 'dot should show a non-open state after the first SSE attempt is aborted',
      })
      .not.toBe('open');

    // Browser auto-retry kicks in and the second attempt is allowed through.
    await expect(dot).toHaveAttribute('data-status', 'open', { timeout: 20_000 });

    // And the snapshot streams normally after recovery.
    await waitForFirstPrice(page);
  });
});
