'use client';

import { useState } from 'react';
import type { WatchlistEntry, PriceMap } from '@/types/api';
import type { SparkPoint } from '@/lib/sseReducer';
import { WatchlistRow } from './WatchlistRow';

interface Props {
  entries: WatchlistEntry[];
  prices: PriceMap;
  sparks: Record<string, SparkPoint[]>;
  selected: string | null;
  onSelect: (ticker: string) => void;
  onAdd: (ticker: string) => Promise<void>;
  onRemove: (ticker: string) => Promise<void>;
}

export function Watchlist({ entries, prices, sparks, selected, onSelect, onAdd, onRemove }: Props) {
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const ticker = input.trim().toUpperCase();
    if (!ticker) return;
    setBusy(true);
    setError(null);
    try {
      await onAdd(ticker);
      setInput('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel flex flex-col h-full overflow-hidden">
      <div className="panel-header">
        <span>Watchlist</span>
        <span className="text-flat normal-case tracking-normal">{entries.length} tickers</span>
      </div>

      <form onSubmit={handleSubmit} className="flex gap-1 px-3 py-2 border-b border-border-subtle">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value.toUpperCase())}
          placeholder="Add ticker"
          maxLength={10}
          className="flex-1 bg-bg-base border border-border-subtle rounded px-2 py-1 text-sm font-mono uppercase focus:outline-none focus:border-primary"
          aria-label="Add ticker"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="bg-primary/90 hover:bg-primary text-bg-base font-semibold text-sm px-3 py-1 rounded disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Add
        </button>
      </form>
      {error && (
        <div className="px-3 py-1 text-xs text-down border-b border-border-subtle">{error}</div>
      )}

      <div className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-2 px-3 py-1 text-[0.65rem] uppercase tracking-wider text-flat border-b border-border-subtle">
        <span>Ticker</span>
        <span>Price</span>
        <span>Chg %</span>
        <span>Spark</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {entries.length === 0 && (
          <div className="px-3 py-6 text-sm text-flat text-center">No tickers — add one above.</div>
        )}
        {entries.map((entry) => (
          <WatchlistRow
            key={entry.ticker}
            ticker={entry.ticker}
            price={prices[entry.ticker]}
            spark={sparks[entry.ticker]}
            selected={selected === entry.ticker}
            onSelect={onSelect}
            onRemove={(t) => {
              void onRemove(t);
            }}
          />
        ))}
      </div>
    </div>
  );
}
