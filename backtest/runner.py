"""Orchestrates the complete historical backtest pipeline from data loading through simulation."""

import time
from pathlib import Path

from common.backtest_progress import BacktestProgressDisplay
from common.debug import configure_debug, debug_print as print, is_debug_enabled
from config import AppConfig
from simulation.simulator import Simulator
from backtest.engine import BacktestEngine
from backtest.equity_logger import EquityLogger
from backtest.logger import TradeLogger

from data.downloader import load_from_csv
from data.resampler import build_timeframes_and_save
from features.feature_pipeline import compute_features


def _fmt_minutes(seconds):
    return f"{seconds / 60:.2f} minutes"


def run_backtest(
    symbol=None,
    base_path=None,
    start_date=None,
    end_date=None,
    config=None
):
    """
    Full backtest runner:
    - Load 1m data
    - Build timeframes
    - Compute features
    - Run backtest engine
    """

    config = config or AppConfig.load()
    configure_debug(config=config)
    symbol = symbol or config.require("app", "default_symbol")
    base_path = base_path or config.require("storage", "base_path")
    start_date = start_date or config.require("history", "start_date")
    end_date = end_date or config.require("history", "end_date")
    base_tf = config.require("timeframes", "base")

    overall_start = time.time()
    original_debug_state = is_debug_enabled()
    display = BacktestProgressDisplay(enabled=True)
    completed = False
    if display.enabled:
        display.start(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_equity=config.require("account", "initial_equity"),
        )
        configure_debug(enabled=False)

    print("\nSTARTING FULL BACKTEST PIPELINE\n")

    try:
        # ------------------------------------------
        # 1. LOAD DATA
        # ------------------------------------------

        path_1m = Path(base_path) / symbol / base_tf["label"] / (
            f"{symbol}_{base_tf['label']}_{start_date}_to_{end_date}.csv"
        )

        if display.enabled:
            display.update_phase("Loading 1m history", f"Loading source CSV {path_1m}")

        print("Loading 1m data...")
        df_1m = load_from_csv(path_1m)

        if display.enabled:
            display.add_event("phase", f"Loaded {len(df_1m):,} rows of 1m history")

        # ------------------------------------------
        # 2. RESAMPLE
        # ------------------------------------------

        if display.enabled:
            display.update_phase("Resampling timeframes", "Building 15m, 1h, 5h, and 12h candles")

        df_15m, df_1h, df_5h, df_12h = build_timeframes_and_save(
            df_1m,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            base_path=base_path
        )

        if display.enabled:
            display.add_event(
                "phase",
                "Resample complete "
                f"(15m={len(df_15m):,}, 1h={len(df_1h):,}, 5h={len(df_5h):,}, 12h={len(df_12h):,})",
            )

        # ------------------------------------------
        # 3. FEATURES
        # ------------------------------------------

        if display.enabled:
            display.update_phase("Computing features", "Building all derived strategy columns")

        print("\nComputing features on all strategy timeframes...")
        df_15m = compute_features(df_15m, config=config)
        df_1h = compute_features(df_1h, config=config)
        df_5h = compute_features(df_5h, config=config)
        df_12h = compute_features(df_12h, config=config)

        if display.enabled:
            display.add_event("phase", "Feature generation complete on all timeframes")

        # ------------------------------------------
        # 4. INITIALIZE SIMULATOR
        # ------------------------------------------

        if display.enabled:
            display.update_phase("Initializing simulator", "Preparing trade, equity, and strategy modules")

        sim = Simulator(
            trade_logger=TradeLogger(config=config),
            equity_logger=EquityLogger(config=config),
            config=config
        )

        if display.enabled:
            display.add_event("phase", "Simulator initialized")

        # ------------------------------------------
        # 5. RUN BACKTEST
        # ------------------------------------------

        if display.enabled:
            display.update_phase("Preparing backtest engine", "Building historical execution engine")

        engine = BacktestEngine(
            df_15m=df_15m,
            df_1h=df_1h,
            df_5h=df_5h,
            df_12h=df_12h,
            simulator=sim,
            progress_display=display,
        )

        engine.run()

        # ------------------------------------------
        # 6. FINAL SUMMARY
        # ------------------------------------------

        total_time = time.time() - overall_start

        if display.enabled:
            display.add_event("done", f"Total runtime {_fmt_minutes(total_time)}")

        completed = True
        return sim
    finally:
        configure_debug(enabled=original_debug_state)
        if display.enabled:
            display.stop()

        total_time = time.time() - overall_start

        if completed:
            print("\nBACKTEST PIPELINE COMPLETE")
            print(f"Total runtime: {total_time/60:.2f} minutes")


# Run directly
if __name__ == "__main__":
    run_backtest()
