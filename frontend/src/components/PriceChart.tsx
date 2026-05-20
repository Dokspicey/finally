'use client';

import { useEffect, useRef } from 'react';
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
  ColorType,
  LineStyle,
} from 'lightweight-charts';
import type { SparkPoint } from '@/lib/sseReducer';

interface Props {
  ticker: string;
  points: SparkPoint[] | undefined;
}

export function PriceChart({ ticker, points }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: '#11161f' },
        textColor: '#9ba3b4',
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
      },
      grid: {
        vertLines: { color: '#1f2530', style: LineStyle.Dotted },
        horzLines: { color: '#1f2530', style: LineStyle.Dotted },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: true,
        borderColor: '#2a2f3a',
      },
      rightPriceScale: {
        borderColor: '#2a2f3a',
      },
      crosshair: {
        vertLine: { color: '#3a3f4a', width: 1, style: LineStyle.Solid, labelBackgroundColor: '#1a1a2e' },
        horzLine: { color: '#3a3f4a', width: 1, style: LineStyle.Solid, labelBackgroundColor: '#1a1a2e' },
      },
      width: container.clientWidth,
      height: container.clientHeight,
    });
    const series = chart.addLineSeries({
      color: '#209dd7',
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
    const series = seriesRef.current;
    if (!series) return;
    if (!points || points.length === 0) {
      series.setData([]);
      return;
    }
    // Dedupe and sort by timestamp — Lightweight Charts requires strictly increasing time.
    const seen = new Map<number, number>();
    for (const p of points) {
      seen.set(Math.floor(p.t), p.price);
    }
    const data: LineData[] = [...seen.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([t, price]) => ({ time: t as Time, value: price }));
    series.setData(data);
  }, [points, ticker]);

  return (
    <div className="panel flex flex-col h-full overflow-hidden">
      <div className="panel-header">
        <span>{ticker} · Price</span>
        <span className="text-flat normal-case tracking-normal">
          {points?.length ?? 0} ticks
        </span>
      </div>
      <div ref={containerRef} className="flex-1 min-h-0" />
    </div>
  );
}
