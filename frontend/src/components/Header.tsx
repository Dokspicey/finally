'use client';

import type { ConnectionStatus } from '@/hooks/usePriceStream';
import { formatPercent, formatUsd, pnlClass } from '@/lib/format';

interface Props {
  cash: number | null;
  totalValue: number | null;
  pnl: number | null;
  pnlPercent: number | null;
  status: ConnectionStatus;
}

const statusColor: Record<ConnectionStatus, string> = {
  open: 'bg-up shadow-[0_0_8px_rgba(34,197,94,0.6)]',
  connecting: 'bg-accent shadow-[0_0_8px_rgba(236,173,10,0.6)]',
  closed: 'bg-down shadow-[0_0_8px_rgba(239,68,68,0.6)]',
};

const statusLabel: Record<ConnectionStatus, string> = {
  open: 'Live',
  connecting: 'Reconnecting',
  closed: 'Disconnected',
};

export function Header({ cash, totalValue, pnl, pnlPercent, status }: Props) {
  return (
    <header className="flex items-center justify-between gap-4 px-4 py-2 border-b border-border-subtle bg-bg-panel">
      <div className="flex items-center gap-3">
        <div className="font-mono font-bold tracking-tight text-lg">
          <span className="text-accent">Fin</span>
          <span className="text-primary">Ally</span>
        </div>
        <span className="text-flat text-xs uppercase tracking-wider hidden md:inline">
          AI Trading Workstation
        </span>
      </div>

      <div className="flex items-center gap-6 text-sm font-mono">
        <Stat label="Total" value={formatUsd(totalValue)} accent="text-accent" />
        <Stat label="Cash" value={formatUsd(cash)} accent="text-primary" />
        <Stat
          label="P&L"
          value={`${formatUsd(pnl)} (${formatPercent(pnlPercent)})`}
          accent={pnlClass(pnl)}
        />
        <div className="flex items-center gap-2">
          <span
            className={`inline-block w-2.5 h-2.5 rounded-full ${statusColor[status]}`}
            aria-label={statusLabel[status]}
            title={statusLabel[status]}
            data-testid="connection-dot"
            data-status={status}
          />
          <span className="text-xs text-flat hidden md:inline">{statusLabel[status]}</span>
        </div>
      </div>
    </header>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div className="flex flex-col items-end leading-tight">
      <span className="text-[0.6rem] uppercase tracking-wider text-flat">{label}</span>
      <span className={`tabular-nums ${accent}`}>{value}</span>
    </div>
  );
}
