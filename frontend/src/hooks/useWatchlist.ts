'use client';

import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { WatchlistEntry } from '@/types/api';

export function useWatchlist() {
  const [entries, setEntries] = useState<WatchlistEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await api.watchlist();
      setEntries(res.watchlist);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed to load watchlist');
    }
  }, []);

  const add = useCallback(
    async (ticker: string) => {
      await api.addWatch(ticker);
      await refresh();
    },
    [refresh],
  );

  const remove = useCallback(
    async (ticker: string) => {
      await api.removeWatch(ticker);
      await refresh();
    },
    [refresh],
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { entries, error, refresh, add, remove };
}
