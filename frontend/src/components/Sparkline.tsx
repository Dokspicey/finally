'use client';

import { useMemo } from 'react';
import type { SparkPoint } from '@/lib/sseReducer';

interface Props {
  points: SparkPoint[] | undefined;
  width?: number;
  height?: number;
  color?: string;
}

export function Sparkline({ points, width = 80, height = 24, color }: Props) {
  const path = useMemo(() => {
    if (!points || points.length < 2) return null;
    const ys = points.map((p) => p.price);
    const min = Math.min(...ys);
    const max = Math.max(...ys);
    const range = max - min || 1;
    const stepX = width / (points.length - 1);
    const coords = points.map((p, i) => {
      const x = i * stepX;
      const y = height - ((p.price - min) / range) * height;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    });
    return `M${coords.join(' L')}`;
  }, [points, width, height]);

  const stroke =
    color ??
    (points && points.length >= 2 && points[points.length - 1].price >= points[0].price
      ? '#22c55e'
      : '#ef4444');

  return (
    <svg width={width} height={height} className="block">
      {path ? (
        <path d={path} fill="none" stroke={stroke} strokeWidth="1.25" strokeLinejoin="round" />
      ) : (
        <line
          x1="0"
          x2={width}
          y1={height / 2}
          y2={height / 2}
          stroke="#3a3f4a"
          strokeDasharray="2,3"
        />
      )}
    </svg>
  );
}
