import time
from pathlib import Path

from config import AppConfig
from simulation.simulator import Simulator
from backtest.engine import BacktestEngine
from backtest.equity_logger import EquityLogger
from backtest.logger import TradeLogger

from data.downloader import load_from_csv
from data.resampler import build_timeframes_and_save
from features.feature_pipeline import compute_features


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
    symbol = symbol or config.require("app", "default_symbol")
    base_path = base_path or config.require("storage", "base_path")
    start_date = start_date or config.require("history", "start_date")
    end_date = end_date or config.require("history", "end_date")
    base_tf = config.require("timeframes", "base")

    overall_start = time.time()

    print("\n🚀 STARTING FULL BACKTEST PIPELINE\n")

    # ✅ ------------------------------------------
    # 1. LOAD DATA
    # ✅ ------------------------------------------

    path_1m = Path(base_path) / symbol / base_tf["label"] / (
        f"{symbol}_{base_tf['label']}_{start_date}_to_{end_date}.csv"
    )

    print("📂 Loading 1m data...")
    df_1m = load_from_csv(path_1m)

    # ✅ ------------------------------------------
    # 2. RESAMPLE
    # ✅ ------------------------------------------

    df_15m, df_1h, df_5h, df_12h = build_timeframes_and_save(
        df_1m,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        base_path=base_path
    )

    # ✅ ------------------------------------------
    # 3. FEATURES
    # ✅ ------------------------------------------

    print("\n🧮 Computing features on all strategy timeframes...")
    df_15m = compute_features(df_15m, config=config)
    df_1h = compute_features(df_1h, config=config)
    df_5h = compute_features(df_5h, config=config)
    df_12h = compute_features(df_12h, config=config)

    # ✅ IMPORTANT: prevent lookahead bias
    high_period = config.require("features", "structure", "high_period")
    high_column = f"hh{high_period}"
    df_15m[f"{high_column}_prev"] = df_15m[high_column].shift(1)

    # ✅ ------------------------------------------
    # 4. INITIALIZE SIMULATOR
    # ✅ ------------------------------------------

    sim = Simulator(
        trade_logger=TradeLogger(config=config),
        equity_logger=EquityLogger(config=config),
        config=config
    )

    # ✅ ------------------------------------------
    # 5. RUN BACKTEST
    # ✅ ------------------------------------------

    engine = BacktestEngine(
        df_15m=df_15m,
        df_1h=df_1h,
        df_5h=df_5h,
        df_12h=df_12h,
        simulator=sim
    )

    engine.run()

    # ✅ ------------------------------------------
    # 6. FINAL SUMMARY
    # ✅ ------------------------------------------

    total_time = time.time() - overall_start

    print("\n🏁 BACKTEST PIPELINE COMPLETE")
    print(f"⏱ Total runtime: {total_time/60:.2f} minutes")

    return sim


# ✅ Run directly
if __name__ == "__main__":
    run_backtest()
