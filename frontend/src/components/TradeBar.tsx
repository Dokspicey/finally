'use client';

import { useEffect, useState } from 'react';
import type { PriceMap, TradeRequest } from '@/types/api';
import { formatUsd } from '@/lib/format';

interface Props {
  selected: string | null;
  prices: PriceMap;
  onTrade: (req: TradeRequest) => Promise<void>;
}

export function TradeBar({ selected, prices, onTrade }: Props) {
  const [ticker, setTicker] = useState(selected ?? '');
  const [quantity, setQuantity] = useState('1');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  useEffect(() => {
    if (selected) setTicker(selected);
  }, [selected]);

  const tickerUpper = ticker.trim().toUpperCase();
  const price = tickerUpper ? prices[tickerUpper]?.price : undefined;
  const qty = parseFloat(quantity);
  const estimated = price != null && Number.isFinite(qty) && qty > 0 ? price * qty : null;

  async function submit(side: 'buy' | 'sell') {
    if (!tickerUpper || !Number.isFinite(qty) || qty <= 0) {
      setMessage({ kind: 'err', text: 'enter ticker and positive quantity' });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      await onTrade({ ticker: tickerUpper, side, quantity: qty });
      setMessage({ kind: 'ok', text: `${side === 'buy' ? 'Bought' : 'Sold'} ${qty} ${tickerUpper}` });
    } catch (err) {
      setMessage({ kind: 'err', text: err instanceof Error ? err.message : 'trade failed' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel flex flex-col">
      <div className="panel-header">
        <span>Trade</span>
        {estimated != null && (
          <span className="text-flat normal-case tracking-normal">
            est. {formatUsd(estimated)}
          </span>
        )}
      </div>
      <form
        className="flex flex-wrap items-end gap-2 px-3 py-3"
        onSubmit={(e) => {
          e.preventDefault();
          void submit('buy');
        }}
      >
        <label className="flex flex-col gap-1 min-w-[120px] flex-1">
          <span className="text-[0.65rem] uppercase tracking-wider text-flat">Ticker</span>
          <input
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            aria-label="Trade ticker"
            placeholder="AAPL"
            maxLength={10}
            className="bg-bg-base border border-border-subtle rounded px-2 py-1.5 font-mono uppercase focus:outline-none focus:border-primary"
          />
        </label>
        <label className="flex flex-col gap-1 min-w-[100px] flex-1">
          <span className="text-[0.65rem] uppercase tracking-wider text-flat">Quantity</span>
          <input
            type="number"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            aria-label="Trade quantity"
            min="0"
            step="0.0001"
            className="bg-bg-base border border-border-subtle rounded px-2 py-1.5 font-mono tabular-nums focus:outline-none focus:border-primary"
          />
        </label>
        <div className="flex flex-col gap-1">
          <span className="text-[0.65rem] uppercase tracking-wider text-flat">Last</span>
          <div className="font-mono tabular-nums px-2 py-1.5 border border-transparent">
            {price != null ? formatUsd(price) : <span className="text-flat">—</span>}
          </div>
        </div>
        <div className="flex gap-2 ml-auto">
          <button
            type="submit"
            disabled={busy}
            className="bg-up/85 hover:bg-up text-bg-base font-semibold px-4 py-1.5 rounded disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Buy
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void submit('sell')}
            className="bg-down/85 hover:bg-down text-bg-base font-semibold px-4 py-1.5 rounded disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Sell
          </button>
        </div>
      </form>
      {message && (
        <div
          className={`px-3 pb-2 text-xs font-mono ${
            message.kind === 'ok' ? 'text-up' : 'text-down'
          }`}
          role="status"
        >
          {message.text}
        </div>
      )}
    </div>
  );
}
