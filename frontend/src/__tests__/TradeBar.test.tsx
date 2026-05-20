import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TradeBar } from '@/components/TradeBar';
import type { PriceMap } from '@/types/api';

const prices: PriceMap = {
  AAPL: {
    ticker: 'AAPL',
    price: 200,
    previous_price: 198,
    timestamp: 1,
    change: 2,
    change_percent: 1,
    direction: 'up',
  },
};

describe('TradeBar', () => {
  it('defaults the ticker field to the selected ticker', () => {
    render(<TradeBar selected="GOOGL" prices={prices} onTrade={vi.fn()} />);
    expect(screen.getByLabelText('Trade ticker')).toHaveValue('GOOGL');
  });

  it('updates ticker when selection changes', async () => {
    const { rerender } = render(
      <TradeBar selected="AAPL" prices={prices} onTrade={vi.fn()} />,
    );
    rerender(<TradeBar selected="MSFT" prices={prices} onTrade={vi.fn()} />);
    expect(screen.getByLabelText('Trade ticker')).toHaveValue('MSFT');
  });

  it('submits a buy with normalized ticker and parsed quantity', async () => {
    const onTrade = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<TradeBar selected="aapl" prices={prices} onTrade={onTrade} />);

    const qty = screen.getByLabelText('Trade quantity');
    await user.clear(qty);
    await user.type(qty, '2.5');
    await user.click(screen.getByRole('button', { name: 'Buy' }));

    expect(onTrade).toHaveBeenCalledWith({ ticker: 'AAPL', side: 'buy', quantity: 2.5 });
  });

  it('submits a sell via the sell button', async () => {
    const onTrade = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<TradeBar selected="AAPL" prices={prices} onTrade={onTrade} />);
    await user.click(screen.getByRole('button', { name: 'Sell' }));
    expect(onTrade).toHaveBeenCalledWith({ ticker: 'AAPL', side: 'sell', quantity: 1 });
  });

  it('shows an error for non-positive quantity and skips onTrade', async () => {
    const onTrade = vi.fn();
    const user = userEvent.setup();
    render(<TradeBar selected="AAPL" prices={prices} onTrade={onTrade} />);
    const qty = screen.getByLabelText('Trade quantity');
    await user.clear(qty);
    await user.type(qty, '0');
    await user.click(screen.getByRole('button', { name: 'Buy' }));
    expect(onTrade).not.toHaveBeenCalled();
    expect(screen.getByRole('status').textContent).toMatch(/positive/i);
  });

  it('surfaces server errors from onTrade', async () => {
    const onTrade = vi.fn().mockRejectedValue(new Error('insufficient cash'));
    const user = userEvent.setup();
    render(<TradeBar selected="AAPL" prices={prices} onTrade={onTrade} />);
    await user.click(screen.getByRole('button', { name: 'Buy' }));
    expect((await screen.findByRole('status')).textContent).toMatch(/insufficient cash/);
  });
});
