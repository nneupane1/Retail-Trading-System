import time

from simulation.simulator import Simulator
from backtest.engine import BacktestEngine

from data.downloader import load_from_csv
from data.resampler import build_timeframes_and_save
from core.features.feature_pipeline import compute_features


def run_backtest(symbol="BTCUSDT", base_path="data_storage"):
    """
    Full backtest runner:
    - Load 1m data
    - Build timeframes
    - Compute features
    - Run backtest engine
    """

    overall_start = time.time()

    print("\n🚀 STARTING FULL BACKTEST PIPELINE\n")

    # ✅ ------------------------------------------
    # 1. LOAD DATA
    # ✅ ------------------------------------------

    path_1m = f"{base_path}/{symbol}/1m/{symbol}_1m_2017-01-01_to_2026-05-12.csv"

    print("📂 Loading 1m data...")
    df_1m = load_from_csv(path_1m)

    # ✅ ------------------------------------------
    # 2. RESAMPLE
    # ✅ ------------------------------------------

    df_15m, df_1h, df_5h, df_12h = build_timeframes_and_save(
        df_1m,
        symbol=symbol
    )

    # ✅ ------------------------------------------
    # 3. FEATURES (ONLY 15m NEEDED FOR ENTRY)
    # ✅ ------------------------------------------

    print("\n🧮 Computing features on 15m data...")
    df_15m = compute_features(df_15m)

    # ✅ IMPORTANT: prevent lookahead bias
    df_15m["hh20_prev"] = df_15m["hh20"].shift(1)

    # ✅ ------------------------------------------
    # 4. INITIALIZE SIMULATOR
    # ✅ ------------------------------------------

    sim = Simulator(initial_equity=20000)

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
