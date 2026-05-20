'use client';

import { useEffect, useMemo, useState } from 'react';
import { Header } from '@/components/Header';
import { Watchlist } from '@/components/Watchlist';
import { PriceChart } from '@/components/PriceChart';
import { PnlChart } from '@/components/PnlChart';
import { PortfolioTreemap } from '@/components/PortfolioTreemap';
import { PositionsTable } from '@/components/PositionsTable';
import { TradeBar } from '@/components/TradeBar';
import { ChatPanel } from '@/components/ChatPanel';
import { usePriceStream } from '@/hooks/usePriceStream';
import { usePortfolio } from '@/hooks/usePortfolio';
import { useWatchlist } from '@/hooks/useWatchlist';
import { api } from '@/lib/api';
import type { TradeRequest } from '@/types/api';

const DEFAULT_TICKER = 'AAPL';

export default function Home() {
  const { prices, sparks, status } = usePriceStream();
  const { portfolio, snapshots, refresh: refreshPortfolio } = usePortfolio();
  const { entries: watchlist, add: addWatch, remove: removeWatch } = useWatchlist();
  const [selected, setSelected] = useState<string | null>(null);

  // Auto-select first watchlist ticker once we know what's there.
  useEffect(() => {
    if (selected) return;
    if (watchlist.length === 0) return;
    const preferred = watchlist.find((w) => w.ticker === DEFAULT_TICKER);
    setSelected(preferred?.ticker ?? watchlist[0].ticker);
  }, [watchlist, selected]);

  async function handleTrade(req: TradeRequest) {
    await api.trade(req);
    await refreshPortfolio();
  }

  const livePositions = useMemo(() => {
    if (!portfolio) return [];
    return portfolio.positions.map((p) => {
      const live = prices[p.ticker]?.price;
      if (live == null) return p;
      const marketValue = p.quantity * live;
      const pnl = (live - p.avg_cost) * p.quantity;
      const cost = p.avg_cost * p.quantity;
      const pct = cost > 0 ? (pnl / cost) * 100 : 0;
      return {
        ...p,
        current_price: live,
        market_value: marketValue,
        unrealized_pnl: pnl,
        unrealized_pnl_percent: pct,
      };
    });
  }, [portfolio, prices]);

  const liveTotals = useMemo(() => {
    if (!portfolio) {
      return { cash: null, total: null, pnl: null, pnlPct: null };
    }
    const positionsValue = livePositions.reduce((s, p) => s + p.market_value, 0);
    const cost = livePositions.reduce((s, p) => s + p.avg_cost * p.quantity, 0);
    const pnl = livePositions.reduce((s, p) => s + p.unrealized_pnl, 0);
    const pct = cost > 0 ? (pnl / cost) * 100 : 0;
    return {
      cash: portfolio.cash_balance,
      total: portfolio.cash_balance + positionsValue,
      pnl,
      pnlPct: pct,
    };
  }, [portfolio, livePositions]);

  const chartTicker = selected ?? DEFAULT_TICKER;

  return (
    <div className="flex flex-col h-screen">
      <Header
        cash={liveTotals.cash}
        totalValue={liveTotals.total}
        pnl={liveTotals.pnl}
        pnlPercent={liveTotals.pnlPct}
        status={status}
      />

      <main className="flex-1 grid gap-3 p-3 min-h-0 overflow-hidden grid-cols-1 lg:grid-cols-[260px_minmax(0,1fr)_320px]">
        {/* Left column — Watchlist */}
        <div className="min-h-0 hidden lg:block">
          <Watchlist
            entries={watchlist}
            prices={prices}
            sparks={sparks}
            selected={selected}
            onSelect={setSelected}
            onAdd={addWatch}
            onRemove={removeWatch}
          />
        </div>

        {/* Middle column — chart + portfolio viz + positions + trade bar */}
        <div className="flex flex-col gap-3 min-h-0">
          <div className="grid gap-3 grid-cols-1 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] flex-1 min-h-0">
            <PriceChart ticker={chartTicker} points={sparks[chartTicker]} />
            <div className="grid gap-3 grid-rows-2 min-h-0">
              <PortfolioTreemap positions={livePositions} onSelect={setSelected} />
              <PnlChart snapshots={snapshots} />
            </div>
          </div>
          <div className="grid gap-3 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <PositionsTable
              positions={livePositions}
              prices={prices}
              selected={selected}
              onSelect={setSelected}
            />
            <TradeBar selected={selected} prices={prices} onTrade={handleTrade} />
          </div>
          {/* Watchlist on mobile */}
          <div className="lg:hidden">
            <Watchlist
              entries={watchlist}
              prices={prices}
              sparks={sparks}
              selected={selected}
              onSelect={setSelected}
              onAdd={addWatch}
              onRemove={removeWatch}
            />
          </div>
        </div>

        {/* Right column — Chat */}
        <div className="min-h-0">
          <ChatPanel onActionsExecuted={refreshPortfolio} />
        </div>
      </main>
    </div>
  );
}
