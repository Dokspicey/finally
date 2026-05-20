'use client';

import { useEffect, useRef, useState } from 'react';
import type { PriceUpdate } from '@/types/api';
import type { SparkPoint } from '@/lib/sseReducer';
import { formatUsd, formatPercent } from '@/lib/format';
import { Sparkline } from './Sparkline';

interface Props {
  ticker: string;
  price: PriceUpdate | undefined;
  spark: SparkPoint[] | undefined;
  selected: boolean;
  onSelect: (ticker: string) => void;
  onRemove?: (ticker: string) => void;
}

type FlashState = 'idle' | 'up' | 'down';

export function WatchlistRow({ ticker, price, spark, selected, onSelect, onRemove }: Props) {
  const [flash, setFlash] = useState<FlashState>('idle');
  const lastPriceRef = useRef<number | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!price) return;
    const previous = lastPriceRef.current;
    if (previous != null && price.price !== previous) {
      setFlash(price.price > previous ? 'up' : 'down');
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => setFlash('idle'), 500);
    }
    lastPriceRef.current = price.price;
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [price]);

  const flashClass = flash === 'up' ? 'flash-up' : flash === 'down' ? 'flash-down' : '';
  const changeClass =
    price == null
      ? 'text-flat'
      : price.change > 0
      ? 'text-up'
      : price.change < 0
      ? 'text-down'
      : 'text-flat';

  return (
    <div
      data-testid={`watchlist-row-${ticker}`}
      className={`grid grid-cols-[1fr_auto_auto_auto] items-center gap-2 px-3 py-1.5 text-sm cursor-pointer transition-colors ${
        selected ? 'bg-bg-elevated' : 'hover:bg-bg-elevated/60'
      } ${flashClass}`}
      onClick={() => onSelect(ticker)}
      role="button"
      aria-pressed={selected}
    >
      <div className="font-mono font-semibold tracking-wide text-zinc-100">{ticker}</div>
      <div className="font-mono tabular-nums text-zinc-100">
        {price ? formatUsd(price.price) : <span className="text-flat">—</span>}
      </div>
      <div className={`font-mono tabular-nums text-xs ${changeClass}`}>
        {price ? formatPercent(price.change_percent) : '—'}
      </div>
      <div className="flex items-center gap-1.5">
        <Sparkline points={spark} />
        {onRemove && (
          <button
            type="button"
            aria-label={`Remove ${ticker}`}
            onClick={(e) => {
              e.stopPropagation();
              onRemove(ticker);
            }}
            className="text-flat hover:text-down text-xs px-1"
          >
            ×
          </button>
        )}
      </div>
    </div>
  );
}
