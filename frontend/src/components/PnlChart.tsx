'use client';

import { useEffect, useMemo, useRef } from 'react';
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
  ColorType,
  LineStyle,
} from 'lightweight-charts';
import type { PortfolioSnapshot } from '@/types/api';

interface Props {
  snapshots: PortfolioSnapshot[];
}

export function PnlChart({ snapshots }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Area'> | null>(null);

  const data = useMemo<LineData[]>(() => {
    const seen = new Map<number, number>();
    for (const s of snapshots) {
      const t = Math.floor(new Date(s.recorded_at).getTime() / 1000);
      seen.set(t, s.total_value);
    }
    return [...seen.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([t, value]) => ({ time: t as Time, value }));
  }, [snapshots]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: '#11161f' },
        textColor: '#9ba3b4',
        fontFamily: 'ui-monospace, monospace',
      },
      grid: {
        vertLines: { color: '#1f2530', style: LineStyle.Dotted },
        horzLines: { color: '#1f2530', style: LineStyle.Dotted },
      },
      timeScale: { timeVisible: true, borderColor: '#2a2f3a' },
      rightPriceScale: { borderColor: '#2a2f3a' },
      width: container.clientWidth,
      height: container.clientHeight,
    });
    const series = chart.addAreaSeries({
      lineColor: '#ecad0a',
      topColor: 'rgba(236, 173, 10, 0.45)',
      bottomColor: 'rgba(236, 173, 10, 0.02)',
      lineWidth: 2,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    });
    chartRef.current = chart;
    seriesRef.current = series;

    const resize = () => {
      if (!containerRef.current) return;
      chart.applyOptions({
        width: containerRef.current.clientWidth,
        height: containerRef.current.clientHeight,
      });
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    seriesRef.current?.setData(data);
    if (data.length > 0) chartRef.current?.timeScale().fitContent();
  }, [data]);

  return (
    <div className="panel flex flex-col h-full overflow-hidden">
      <div className="panel-header">
        <span>Portfolio Value</span>
        <span className="text-flat normal-case tracking-normal">{data.length} pts</span>
      </div>
      <div ref={containerRef} className="flex-1 min-h-0" />
    </div>
  );
}
