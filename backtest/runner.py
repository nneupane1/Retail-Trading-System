"""Orchestrates the complete historical backtest pipeline from data loading through simulation."""

import time
from contextlib import nullcontext
from pathlib import Path

from backtest.checkpoint import BacktestCheckpointStore
from common.backtest_progress import BacktestProgressDisplay
from common.debug import configure_debug, debug_print as print, override_debug
from config import AppConfig
from simulation.simulator import Simulator
from backtest.engine import BacktestEngine
from backtest.equity_logger import EquityLogger
from backtest.logger import TradeLogger
from backtest.opportunity_logger import OpportunityLogger

from data.downloader import load_from_csv
from data.resampler import build_timeframes_and_save
from features.feature_pipeline import compute_features


def _fmt_minutes(seconds):
    return f"{seconds / 60:.2f} minutes"


def _build_checkpoint_store(config, symbol, start_date, end_date):
    if not config.get("backtest", "resume_enabled", default=True):
        return None

    output_dir = config.path("backtest", "output_dir")
    checkpoint_dir_value = config.get("backtest", "checkpoint_dir", default="_checkpoints")
    checkpoint_dir = Path(checkpoint_dir_value)
    if not checkpoint_dir.is_absolute():
        checkpoint_dir = output_dir / checkpoint_dir

    suffix = config.get(
        "backtest",
        "checkpoint_suffix",
        default=".checkpoint.json",
    )
    checkpoint_path = checkpoint_dir / (
        f"{symbol}_backtest_{start_date}_to_{end_date}{suffix}"
    )
    return BacktestCheckpointStore(checkpoint_path)


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
    display = BacktestProgressDisplay(enabled=True)
    completed = False
    checkpoint_store = _build_checkpoint_store(config, symbol, start_date, end_date)
    resume_payload = checkpoint_store.load() if checkpoint_store and checkpoint_store.exists() else None
    resume_index = None
    resume_active = False

    if display.enabled:
        display.start(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_equity=config.require("account", "initial_equity"),
        )

    print("\nSTARTING FULL BACKTEST PIPELINE\n")

    debug_context = override_debug(False) if display.enabled else nullcontext()

    with debug_context:
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

            if resume_payload:
                resume_metadata = resume_payload.get("metadata", {})
                expected_metadata = {
                    "symbol": symbol,
                    "start_date": start_date,
                    "end_date": end_date,
                }
                if all(
                    resume_metadata.get(key) == value
                    for key, value in expected_metadata.items()
                ):
                    resume_index = resume_payload.get("next_index")
                    if resume_index is not None:
                        resume_active = True
                        if display.enabled:
                            display.add_event(
                                "resume",
                                f"Resuming from index {resume_index:,}",
                            )
                elif display.enabled:
                    display.add_event(
                        "phase",
                        "Ignoring incompatible checkpoint metadata",
                    )

            # ------------------------------------------
            # 4. INITIALIZE SIMULATOR
            # ------------------------------------------

            if display.enabled:
                display.update_phase("Initializing simulator", "Preparing trade, equity, and strategy modules")

            sim = Simulator(
                trade_logger=TradeLogger(config=config, reset=not resume_active),
                equity_logger=EquityLogger(config=config, reset=not resume_active),
                opportunity_logger=(
                    OpportunityLogger(config=config, reset=not resume_active)
                    if config.get("backtest", "opportunity_log_enabled", default=False)
                    else None
                ),
                config=config
            )

            if resume_active:
                sim.restore_state(resume_payload.get("simulator_state"))

            if display.enabled:
                if resume_active:
                    display.add_event("phase", "Simulator restored from checkpoint")
                else:
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
                checkpoint_store=checkpoint_store,
                checkpoint_every_steps=config.get(
                    "backtest",
                    "save_every_steps",
                    default=250,
                ),
                resume_index=resume_index,
                checkpoint_metadata={
                    "symbol": symbol,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            )

            run_completed = engine.run()
            sim.backtest_completed = bool(run_completed)

            # ------------------------------------------
            # 6. FINAL SUMMARY
            # ------------------------------------------

            total_time = time.time() - overall_start

            if display.enabled:
                display.add_event("done", f"Total runtime {_fmt_minutes(total_time)}")

            completed = bool(run_completed)
            return sim
        finally:
            if display.enabled:
                display.stop()

            total_time = time.time() - overall_start

            if completed:
                print("\nBACKTEST PIPELINE COMPLETE")
                print(f"Total runtime: {total_time/60:.2f} minutes")


# Run directly
if __name__ == "__main__":
    run_backtest()
