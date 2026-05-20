import { describe, it, expect } from 'vitest';
import { priceReducer, initialPriceState, SPARK_LIMIT } from '@/lib/sseReducer';
import type { PriceUpdate } from '@/types/api';

function update(ticker: string, price: number, prev: number, t = 1000): PriceUpdate {
  return {
    ticker,
    price,
    previous_price: prev,
    timestamp: t,
    change: price - prev,
    change_percent: prev > 0 ? ((price - prev) / prev) * 100 : 0,
    direction: price > prev ? 'up' : price < prev ? 'down' : 'flat',
  };
}

describe('priceReducer', () => {
  it('applies initial SSE payload and seeds sparkline', () => {
    const state = priceReducer(initialPriceState, {
      type: 'sse',
      payload: { AAPL: update('AAPL', 190, 189, 1000) },
    });
    expect(state.prices.AAPL.price).toBe(190);
    expect(state.sparks.AAPL).toEqual([{ t: 1000, price: 190 }]);
    expect(state.version).toBe(1);
  });

  it('recomputes direction relative to last seen price', () => {
    let state = priceReducer(initialPriceState, {
      type: 'sse',
      payload: { AAPL: update('AAPL', 190, 189, 1000) },
    });
    // Source claims down vs an unseen previous price; but vs our last
    // observed value (190) the new 192 is an UP tick — reducer should reflect that.
    state = priceReducer(state, {
      type: 'sse',
      payload: { AAPL: { ...update('AAPL', 192, 195, 1500), direction: 'down' } },
    });
    expect(state.prices.AAPL.direction).toBe('up');
    expect(state.prices.AAPL.previous_price).toBe(190);
  });

  it('accumulates sparkline points across multiple events', () => {
    let state = initialPriceState;
    for (let i = 0; i < 5; i++) {
      state = priceReducer(state, {
        type: 'sse',
        payload: { AAPL: update('AAPL', 190 + i, 190 + i - 1, 1000 + i) },
      });
    }
    expect(state.sparks.AAPL).toHaveLength(5);
    expect(state.sparks.AAPL[4].price).toBe(194);
  });

  it('caps sparkline history at SPARK_LIMIT', () => {
    let state = initialPriceState;
    for (let i = 0; i < SPARK_LIMIT + 25; i++) {
      state = priceReducer(state, {
        type: 'sse',
        payload: { AAPL: update('AAPL', 100 + i, 99 + i, 1000 + i) },
      });
    }
    expect(state.sparks.AAPL.length).toBe(SPARK_LIMIT);
    // Oldest points were evicted — last point should be the most recent.
    expect(state.sparks.AAPL[SPARK_LIMIT - 1].price).toBe(100 + SPARK_LIMIT + 24);
  });

  it('merges multi-ticker payloads in one event', () => {
    const state = priceReducer(initialPriceState, {
      type: 'sse',
      payload: {
        AAPL: update('AAPL', 190, 189, 1000),
        GOOGL: update('GOOGL', 175, 174, 1000),
      },
    });
    expect(Object.keys(state.prices)).toContain('AAPL');
    expect(Object.keys(state.prices)).toContain('GOOGL');
    expect(state.sparks.GOOGL).toHaveLength(1);
  });

  it('reset clears state but bumps version', () => {
    let state = priceReducer(initialPriceState, {
      type: 'sse',
      payload: { AAPL: update('AAPL', 190, 189) },
    });
    state = priceReducer(state, { type: 'reset' });
    expect(state.prices).toEqual({});
    expect(state.sparks).toEqual({});
    expect(state.version).toBe(2);
  });
});
