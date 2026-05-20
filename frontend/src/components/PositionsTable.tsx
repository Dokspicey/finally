'use client';

import type { Position, PriceMap } from '@/types/api';
import { formatPercent, formatQty, formatUsd, pnlClass } from '@/lib/format';

interface Props {
  positions: Position[];
  prices: PriceMap;
  selected: string | null;
  onSelect: (ticker: string) => void;
}

export function PositionsTable({ positions, prices, selected, onSelect }: Props) {
  return (
    <div className="panel flex flex-col h-full overflow-hidden">
      <div className="panel-header">
        <span>Positions</span>
        <span className="text-flat normal-case tracking-normal">{positions.length}</span>
      </div>
      <div className="overflow-auto flex-1 min-h-0">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-bg-elevated text-[0.65rem] uppercase tracking-wider text-flat">
            <tr>
              <th className="text-left px-3 py-1.5 font-medium">Ticker</th>
              <th className="text-right px-3 py-1.5 font-medium">Qty</th>
              <th className="text-right px-3 py-1.5 font-medium">Avg Cost</th>
              <th className="text-right px-3 py-1.5 font-medium">Last</th>
              <th className="text-right px-3 py-1.5 font-medium">P&amp;L</th>
              <th className="text-right px-3 py-1.5 font-medium">%</th>
            </tr>
          </thead>
          <tbody>
            {positions.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-flat">
                  No open positions yet — use the trade bar or chat to place an order.
                </td>
              </tr>
            )}
            {positions.map((p) => {
              const live = prices[p.ticker]?.price ?? p.current_price;
              return (
                <tr
                  key={p.ticker}
                  onClick={() => onSelect(p.ticker)}
                  className={`cursor-pointer border-t border-border-subtle hover:bg-bg-elevated/60 ${
                    selected === p.ticker ? 'bg-bg-elevated' : ''
                  }`}
                >
                  <td className="px-3 py-1.5 font-mono font-semibold">{p.ticker}</td>
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                    {formatQty(p.quantity)}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                    {formatUsd(p.avg_cost)}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                    {formatUsd(live)}
                  </td>
                  <td className={`px-3 py-1.5 text-right font-mono tabular-nums ${pnlClass(p.unrealized_pnl)}`}>
                    {formatUsd(p.unrealized_pnl)}
                  </td>
                  <td className={`px-3 py-1.5 text-right font-mono tabular-nums ${pnlClass(p.unrealized_pnl)}`}>
                    {formatPercent(p.unrealized_pnl_percent)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
