"""Runs the near-live simulation loop using recent Binance data and the shared simulator."""

import time

from config import AppConfig
from simulation.simulator import Simulator
from data.downloader import fetch_recent
from data.resampler import build_timeframes_and_save
from features.feature_pipeline import compute_features
from live_sim.candle_clock import is_new_15m_candle
from live_sim.logger import LiveTradeLogger


def run_live_sim(symbol=None, config=None):
    config = config or AppConfig.load()
    symbol = symbol or config.require("app", "default_symbol")
    interval = config.require("binance", "default_interval")
    recent_limit = config.require("binance", "recent_limit")
    poll_seconds = config.require("live_sim", "poll_seconds")

    print("\nSTARTING LIVE SIMULATION\n")

    sim = Simulator(
        trade_logger=LiveTradeLogger(config=config),
        config=config
    )

    last_candle_time = None

    while True:

        cycle_start = time.time()

        print("\nFetching latest 1m data...")
        df_1m = fetch_recent(
            symbol=symbol,
            interval=interval,
            limit=recent_limit
        )

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

        # avoid lookahead
        high_period = config.require("features", "structure", "high_period")
        high_column = f"hh{high_period}"
        df_15m[f"{high_column}_prev"] = df_15m[high_column].shift(1)

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
