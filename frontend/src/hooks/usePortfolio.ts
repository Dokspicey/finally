'use client';

import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { Portfolio, PortfolioSnapshot, Trade } from '@/types/api';

export function usePortfolio() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [p, h, t] = await Promise.all([
        api.portfolio(),
        api.portfolioHistory(),
        api.trades(50),
      ]);
      setPortfolio(p);
      setSnapshots(h.snapshots);
      setTrades(t.trades);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed to load');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { portfolio, snapshots, trades, error, refresh };
}
