'use client';

import { useMemo } from 'react';
import type { Position } from '@/types/api';
import { formatUsd, formatPercent } from '@/lib/format';

interface Props {
  positions: Position[];
  onSelect: (ticker: string) => void;
}

interface Rect {
  ticker: string;
  position: Position;
  x: number;
  y: number;
  w: number;
  h: number;
}

// Squarified treemap layout — simplified version.
function squarify(
  positions: Position[],
  width: number,
  height: number,
): Rect[] {
  const total = positions.reduce((sum, p) => sum + p.market_value, 0);
  if (total <= 0 || positions.length === 0) return [];

  // Sort by value descending.
  const items = [...positions].sort((a, b) => b.market_value - a.market_value);
  const area = width * height;
  const scaled = items.map((p) => ({
    p,
    area: (p.market_value / total) * area,
  }));

  const rects: Rect[] = [];
  let x = 0;
  let y = 0;
  let remainingW = width;
  let remainingH = height;
  let row: { p: Position; area: number }[] = [];

  const worstRatio = (
    row: { p: Position; area: number }[],
    extra: { p: Position; area: number } | null,
    side: number,
  ): number => {
    const items = extra ? [...row, extra] : row;
    if (items.length === 0) return Infinity;
    const sum = items.reduce((s, it) => s + it.area, 0);
    const minA = Math.min(...items.map((it) => it.area));
    const maxA = Math.max(...items.map((it) => it.area));
    const s2 = side * side;
    const sum2 = sum * sum;
    return Math.max((s2 * maxA) / sum2, sum2 / (s2 * minA));
  };

  const layoutRow = (row: { p: Position; area: number }[], side: number) => {
    const sum = row.reduce((s, it) => s + it.area, 0);
    const horizontal = remainingW < remainingH;
    if (horizontal) {
      const rowHeight = sum / remainingW;
      let cx = x;
      for (const it of row) {
        const w = it.area / rowHeight;
        rects.push({ ticker: it.p.ticker, position: it.p, x: cx, y, w, h: rowHeight });
        cx += w;
      }
      y += rowHeight;
      remainingH -= rowHeight;
    } else {
      const rowWidth = sum / remainingH;
      let cy = y;
      for (const it of row) {
        const h = it.area / rowWidth;
        rects.push({ ticker: it.p.ticker, position: it.p, x, y: cy, w: rowWidth, h });
        cy += h;
      }
      x += rowWidth;
      remainingW -= rowWidth;
    }
  };

  for (const item of scaled) {
    const side = Math.min(remainingW, remainingH);
    if (side <= 0) break;
    const current = worstRatio(row, null, side);
    const next = worstRatio(row, item, side);
    if (row.length === 0 || next <= current) {
      row.push(item);
    } else {
      layoutRow(row, side);
      row = [item];
    }
  }
  if (row.length > 0) {
    layoutRow(row, Math.min(remainingW, remainingH));
  }
  return rects;
}

function pnlBg(pnl: number, pct: number): string {
  if (pnl === 0) return 'rgba(161, 161, 170, 0.18)';
  const intensity = Math.min(0.65, 0.18 + Math.abs(pct) / 30);
  return pnl > 0
    ? `rgba(34, 197, 94, ${intensity.toFixed(2)})`
    : `rgba(239, 68, 68, ${intensity.toFixed(2)})`;
}

export function PortfolioTreemap({ positions, onSelect }: Props) {
  const W = 100;
  const H = 100;
  const rects = useMemo(() => squarify(positions, W, H), [positions]);

  return (
    <div className="panel flex flex-col h-full overflow-hidden">
      <div className="panel-header">
        <span>Allocation</span>
        <span className="text-flat normal-case tracking-normal">{positions.length} pos</span>
      </div>
      <div className="flex-1 relative min-h-0">
        {rects.length === 0 ? (
          <div className="absolute inset-0 grid place-items-center text-sm text-flat">
            No positions
          </div>
        ) : (
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="absolute inset-0 w-full h-full">
            {rects.map((r) => {
              const fill = pnlBg(r.position.unrealized_pnl, r.position.unrealized_pnl_percent);
              const showLabel = r.w > 12 && r.h > 8;
              return (
                <g
                  key={r.ticker}
                  className="cursor-pointer"
                  onClick={() => onSelect(r.ticker)}
                >
                  <rect
                    x={r.x}
                    y={r.y}
                    width={Math.max(0, r.w - 0.4)}
                    height={Math.max(0, r.h - 0.4)}
                    fill={fill}
                    stroke="#0d1117"
                    strokeWidth={0.4}
                  />
                  {showLabel && (
                    <>
                      <text
                        x={r.x + 1.5}
                        y={r.y + 4}
                        fontSize={r.w > 20 ? 3 : 2.5}
                        fill="#e6edf3"
                        fontWeight={600}
                      >
                        {r.ticker}
                      </text>
                      {r.w > 20 && r.h > 14 && (
                        <text x={r.x + 1.5} y={r.y + 8} fontSize={2} fill="#cbd5e1">
                          {formatPercent(r.position.unrealized_pnl_percent)}
                        </text>
                      )}
                      {r.w > 24 && r.h > 18 && (
                        <text x={r.x + 1.5} y={r.y + 11.5} fontSize={1.8} fill="#9ba3b4">
                          {formatUsd(r.position.market_value)}
                        </text>
                      )}
                    </>
                  )}
                </g>
              );
            })}
          </svg>
        )}
      </div>
    </div>
  );
}
