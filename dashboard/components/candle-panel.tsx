"use client";

import { useEffect, useMemo, useRef } from "react";
import useSWR from "swr";
import {
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp
} from "lightweight-charts";

type CandlePayload = {
  symbol: string;
  timeframe: string;
  candles: {
    time: number;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  }[];
  markers: {
    time: number;
    position: "aboveBar" | "belowBar";
    color: string;
    shape: "arrowUp" | "arrowDown" | "circle";
    text: string;
  }[];
};

const fetcher = async <T,>(url: string): Promise<T> => {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
};

export function CandlePanel({
  symbol,
  timeframe,
  apiUrl,
  untilTime,
  runId,
}: {
  symbol: string;
  timeframe: string;
  apiUrl: string;
  untilTime?: number | null;
  runId?: string | null;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const viewKeyRef = useRef<string>("");

  const url = `${apiUrl}/api/candles?symbol=${symbol}&timeframe=${timeframe}&limit=700${runId ? `&run_id=${encodeURIComponent(runId)}` : ""}`;
  const { data } = useSWR<CandlePayload>(
    url,
    fetcher,
    {
      refreshInterval: 15000,
      revalidateOnFocus: false,
    }
  );

  const untilCutoff = useMemo(() => {
    if (typeof untilTime !== "number" || Number.isNaN(untilTime)) {
      return null;
    }
    return untilTime;
  }, [untilTime]);

  const filteredCandles = useMemo(() => {
    if (!data?.candles) {
      return [];
    }
    return data.candles
      .map((candle) => ({
        ...candle,
        time: Number(candle.time),
      }))
      .filter((candle) => (untilCutoff ? candle.time <= untilCutoff : true));
  }, [data?.candles, untilCutoff]);

  const markers = useMemo(
    () =>
      (data?.markers ?? [])
        .map((marker) => ({
          ...marker,
          time: Number(marker.time) as UTCTimestamp,
        }))
        .filter((marker) => (untilCutoff ? marker.time <= untilCutoff : true)),
    [data?.markers, untilCutoff]
  );

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#050816" },
        textColor: "#cbd5e1"
      },
      grid: {
        vertLines: { color: "rgba(148, 163, 184, 0.08)" },
        horzLines: { color: "rgba(148, 163, 184, 0.08)" }
      },
      width: containerRef.current.clientWidth,
      height: 520,
      rightPriceScale: {
        borderColor: "rgba(148, 163, 184, 0.18)"
      },
      timeScale: {
        borderColor: "rgba(148, 163, 184, 0.18)",
        timeVisible: true,
        secondsVisible: false
      },
      crosshair: {
        vertLine: { color: "rgba(83, 242, 255, 0.35)" },
        horzLine: { color: "rgba(83, 242, 255, 0.2)" }
      }
    });

    const series = chart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#86efac",
      wickDownColor: "#fb7185",
      priceLineVisible: true
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const resizeObserver = new ResizeObserver(() => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current || !data) {
      return;
    }

    seriesRef.current.setData(
      filteredCandles.map((candle) => ({
        time: candle.time as UTCTimestamp,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
      }))
    );
    seriesRef.current.setMarkers(markers);
    const nextViewKey = `${symbol}:${timeframe}:${runId ?? ""}`;
    if (viewKeyRef.current !== nextViewKey) {
      chartRef.current?.timeScale().fitContent();
      viewKeyRef.current = nextViewKey;
    }
  }, [filteredCandles, markers, symbol, timeframe, runId]);

  return (
    <div className="overflow-hidden rounded-[28px] border border-white/10 bg-[#040914]">
      <div className="flex items-center justify-between border-b border-white/8 px-4 py-3 text-xs uppercase tracking-[0.22em] text-white/45">
        <span>
          {symbol} · {timeframe}
        </span>
        <span>{filteredCandles.length} candles</span>
      </div>
      <div ref={containerRef} className="h-[520px] w-full" />
    </div>
  );
}
