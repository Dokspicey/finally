import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { WatchlistRow } from '@/components/WatchlistRow';
import type { PriceUpdate } from '@/types/api';

function makePrice(price: number, prev: number): PriceUpdate {
  return {
    ticker: 'AAPL',
    price,
    previous_price: prev,
    timestamp: Date.now() / 1000,
    change: price - prev,
    change_percent: prev > 0 ? ((price - prev) / prev) * 100 : 0,
    direction: price > prev ? 'up' : price < prev ? 'down' : 'flat',
  };
}

describe('WatchlistRow', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders ticker and dash when no price', () => {
    render(
      <WatchlistRow
        ticker="AAPL"
        price={undefined}
        spark={undefined}
        selected={false}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByText('AAPL')).toBeInTheDocument();
  });

  it('applies flash-up class on upward price change and clears after 500ms', () => {
    const { rerender } = render(
      <WatchlistRow
        ticker="AAPL"
        price={makePrice(190, 189)}
        spark={undefined}
        selected={false}
        onSelect={() => {}}
      />,
    );

    const row = screen.getByTestId('watchlist-row-AAPL');
    // First render seeds the ref but doesn't flash (no prior price).
    expect(row.className).not.toMatch(/flash-up|flash-down/);

    rerender(
      <WatchlistRow
        ticker="AAPL"
        price={makePrice(191, 190)}
        spark={undefined}
        selected={false}
        onSelect={() => {}}
      />,
    );
    expect(row.className).toMatch(/flash-up/);

    act(() => {
      vi.advanceTimersByTime(600);
    });
    expect(row.className).not.toMatch(/flash-up|flash-down/);
  });

  it('applies flash-down on downward price change', () => {
    const { rerender } = render(
      <WatchlistRow
        ticker="AAPL"
        price={makePrice(190, 189)}
        spark={undefined}
        selected={false}
        onSelect={() => {}}
      />,
    );
    rerender(
      <WatchlistRow
        ticker="AAPL"
        price={makePrice(188, 190)}
        spark={undefined}
        selected={false}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByTestId('watchlist-row-AAPL').className).toMatch(/flash-down/);
  });

  it('does not flash when price is unchanged', () => {
    const { rerender } = render(
      <WatchlistRow
        ticker="AAPL"
        price={makePrice(190, 189)}
        spark={undefined}
        selected={false}
        onSelect={() => {}}
      />,
    );
    rerender(
      <WatchlistRow
        ticker="AAPL"
        price={makePrice(190, 190)}
        spark={undefined}
        selected={false}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByTestId('watchlist-row-AAPL').className).not.toMatch(/flash-/);
  });
});
