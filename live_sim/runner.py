import time

from simulation.simulator import Simulator
from data.downloader import fetch_recent
from data.resampler import build_timeframes_and_save
from core.features.feature_pipeline import compute_features
from live_sim.candle_clock import is_new_15m_candle


def run_live_sim(symbol="BTCUSDT"):

    print("\n🚀 STARTING LIVE SIMULATION\n")

    sim = Simulator(initial_equity=20000)

    last_candle_time = None

    while True:

        cycle_start = time.time()

        print("\n📡 Fetching latest 1m data...")
        df_1m = fetch_recent(symbol=symbol, interval="1m", limit=1000)

        print("📊 Building timeframes...")
        df_15m, df_1h, df_5h, df_12h = build_timeframes_and_save(
            df_1m,
            symbol=symbol
        )

        print("🧮 Computing features...")
        df_15m = compute_features(df_15m)

        # ✅ avoid lookahead
        df_15m["hh20_prev"] = df_15m["hh20"].shift(1)

        # ✅ check if new 15m candle formed
        is_new, last_candle_time = is_new_15m_candle(
            df_15m,
            last_candle_time
        )

        if is_new:

            print("\n✅ New 15m candle detected → running strategy")

            row = df_15m.iloc[-1]

            sim.step(row, df_1h, df_5h, df_12h)

        else:
            print("⏳ No new 15m candle yet")

        # ✅ cycle timing
        cycle_time = time.time() - cycle_start

        print(f"\n⏱ Cycle completed in {cycle_time:.2f}s")

        # ✅ wait before next fetch
        time.sleep(30)


# ✅ run directly
if __name__ == "__main__":
    run_live_sim()
