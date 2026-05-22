"""Runs the near-live simulation loop using recent Binance data and the shared simulator."""

import time
from pathlib import Path

import pandas as pd

from common.debug import configure_debug, debug_print as print
from config import AppConfig
from simulation.simulator import Simulator
from data.downloader import fetch_recent, load_from_csv
from data.resampler import build_timeframes_and_save
from features.feature_pipeline import compute_features
from live_sim.candle_clock import is_new_15m_candle
from live_sim.logger import LiveTradeLogger


def _extract_period_from_column(column_name, fallback):
    digits = "".join(character for character in str(column_name) if character.isdigit())
    return int(digits) if digits else fallback


def _required_live_warmup_minutes(config):
    fast_ema_period = config.require("features", "ema_periods", "fast")
    slow_ema_period = config.require("features", "ema_periods", "slow")
    high_period = config.require("features", "structure", "high_period")
    low_period = config.require("features", "structure", "low_period")
    slow_range_period = config.require("features", "compression", "slow_range_period")
    average_body_period = config.require("features", "candle_metrics", "average_body_period")
    bias_ema_period = _extract_period_from_column(
        config.require("strategy", "bias", "ema_column"),
        fallback=slow_ema_period,
    )
    regime_ema_period = _extract_period_from_column(
        config.require("strategy", "regime", "ema_column"),
        fallback=slow_ema_period,
    )
    bias_slope_lookback = config.require("strategy", "bias", "slope_lookback")
    regime_slope_lookback = config.require("strategy", "regime", "slope_lookback")
    execution_rule = config.require("timeframes", "execution", "rule")
    direction_rule = config.require("timeframes", "direction", "rule")
    trend_rule = config.require("timeframes", "trend", "rule")
    macro_rule = config.require("timeframes", "macro", "rule")

    shared_feature_bars = max(
        fast_ema_period,
        slow_ema_period,
        high_period + 1,
        low_period,
        slow_range_period,
        average_body_period,
    )
    buffer_bars = 10

    execution_bars = shared_feature_bars + buffer_bars
    direction_bars = max(shared_feature_bars, bias_ema_period) + bias_slope_lookback + buffer_bars
    trend_bars = max(shared_feature_bars, regime_ema_period) + buffer_bars
    macro_bars = max(shared_feature_bars, regime_ema_period) + regime_slope_lookback + buffer_bars

    execution_minutes = int(pd.Timedelta(execution_rule).total_seconds() // 60)
    direction_minutes = int(pd.Timedelta(direction_rule).total_seconds() // 60)
    trend_minutes = int(pd.Timedelta(trend_rule).total_seconds() // 60)
    macro_minutes = int(pd.Timedelta(macro_rule).total_seconds() // 60)

    return max(
        execution_bars * execution_minutes,
        direction_bars * direction_minutes,
        trend_bars * trend_minutes,
        macro_bars * macro_minutes,
    )


def _trim_live_window(df_1m, warmup_minutes):
    if df_1m.empty:
        return df_1m

    cutoff = df_1m.index.max() - pd.Timedelta(minutes=warmup_minutes)
    trimmed = df_1m.loc[df_1m.index >= cutoff].copy()
    trimmed = trimmed[~trimmed.index.duplicated(keep="last")].sort_index()
    return trimmed


def _merge_recent_into_state(df_existing, df_recent, warmup_minutes):
    combined = pd.concat([df_existing, df_recent])
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    return _trim_live_window(combined, warmup_minutes)


def _bootstrap_history_paths(symbol, interval, config):
    base_path = Path(config.require("storage", "base_path"))
    start_date = config.require("history", "start_date")
    end_date = config.require("history", "end_date")
    partial_suffix = config.require("downloads", "history")["partial_suffix"]
    folder = base_path / symbol / interval
    filename = f"{symbol}_{interval}_{start_date}_to_{end_date}.csv"
    final_path = folder / filename
    partial_path = folder / f"{filename}{partial_suffix}"
    return final_path, partial_path


def _load_live_bootstrap_history(symbol, interval, warmup_minutes, config):
    final_path, partial_path = _bootstrap_history_paths(symbol, interval, config)

    if final_path.exists():
        source_path = final_path
    elif partial_path.exists():
        source_path = partial_path
    else:
        raise FileNotFoundError(
            "Live simulation requires local 1m bootstrap history. "
            f"Expected either {final_path} or {partial_path}. "
            "Run `python main_download.py` first."
        )

    df_1m = load_from_csv(source_path)
    df_1m = _trim_live_window(df_1m, warmup_minutes)
    return df_1m, source_path


def run_live_sim(symbol=None, config=None):
    config = config or AppConfig.load()
    configure_debug(config=config)
    symbol = symbol or config.require("app", "default_symbol")
    interval = config.require("binance", "default_interval")
    recent_limit = config.require("binance", "recent_limit")
    poll_seconds = config.require("live_sim", "poll_seconds")
    warmup_minutes = _required_live_warmup_minutes(config)

    print("\nSTARTING LIVE SIMULATION\n")
    print(
        "Bootstrapping live state from local 1m history "
        f"with ~{warmup_minutes / (60 * 24):.1f} days of warmup"
    )

    sim = Simulator(
        trade_logger=LiveTradeLogger(config=config),
        config=config
    )

    last_candle_time = None
    df_1m_state, source_path = _load_live_bootstrap_history(
        symbol=symbol,
        interval=interval,
        warmup_minutes=warmup_minutes,
        config=config,
    )

    print(f"Loaded live bootstrap source: {source_path}")
    print(f"Bootstrap rows retained in memory: {len(df_1m_state)}")

    while True:

        cycle_start = time.time()

        print("\nFetching latest 1m data...")
        df_recent = fetch_recent(
            symbol=symbol,
            interval=interval,
            limit=recent_limit
        )
        df_1m_state = _merge_recent_into_state(
            df_existing=df_1m_state,
            df_recent=df_recent,
            warmup_minutes=warmup_minutes,
        )
        df_1m = df_1m_state

        start_date = df_1m.index.min().strftime("%Y-%m-%d")
        end_date = df_1m.index.max().strftime("%Y-%m-%d")

        print("Building timeframes...")
        df_15m, df_1h, df_5h, df_12h = build_timeframes_and_save(
            df_1m,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date
        )

        print("Computing features...")
        df_15m = compute_features(df_15m, config=config)
        df_1h = compute_features(df_1h, config=config)
        df_5h = compute_features(df_5h, config=config)
        df_12h = compute_features(df_12h, config=config)

        # check if new 15m candle formed
        is_new, last_candle_time = is_new_15m_candle(
            df_15m,
            last_candle_time
        )

        if is_new:

            print("\nNew 15m candle detected -> running strategy")

            row = df_15m.iloc[-1]

            df_1h_context = df_1h.loc[:row.name]
            df_5h_context = df_5h.loc[:row.name]
            df_12h_context = df_12h.loc[:row.name]

            if df_1h_context.empty or df_5h_context.empty or df_12h_context.empty:
                print("Waiting for higher-timeframe candles to close before strategy run")
                continue

            sim.step(row, df_1h_context, df_5h_context, df_12h_context)

        else:
            print("No new 15m candle yet")

        # cycle timing
        cycle_time = time.time() - cycle_start

        print(f"\nTime: Cycle completed in {cycle_time:.2f}s")

        # wait before next fetch
        time.sleep(poll_seconds)


# run directly
if __name__ == "__main__":
    run_live_sim()
