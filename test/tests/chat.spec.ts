import { test, expect } from '@playwright/test';
import { resetState, waitForFirstPrice } from './helpers';

test.describe('AI chat (LLM_MOCK)', () => {
  test.beforeEach(async ({ request }) => {
    await resetState(request);
  });

  test('"buy 1 AAPL" triggers an inline action confirmation and creates a position', async ({
    page,
  }) => {
    await page.goto('/');
    await waitForFirstPrice(page);

    // Type the magic phrase into the chat panel.
    await page.getByLabel('Chat message').fill('buy 1 AAPL');
    await page.getByRole('button', { name: 'Send' }).click();

    // The assistant message renders with an inline success action_result.
    await expect(page.getByTestId('chat-message-assistant').last()).toBeVisible({ timeout: 10_000 });
    const okAction = page.getByTestId('chat-action-ok').last();
    await expect(okAction).toBeVisible({ timeout: 10_000 });
    await expect(okAction).toContainText(/Bought.*AAPL/i);

    // And the position now exists in the positions table.
    await expect(page.getByRole('cell', { name: 'AAPL', exact: true }).first()).toBeVisible({
      timeout: 5_000,
    });
  });
});
