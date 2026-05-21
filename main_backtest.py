import time

from config import AppConfig
from backtest.runner import run_backtest


def main():
    """
    Main entry point for full backtest.
    """

    print("\n🚀 LAUNCHING BACKTEST SYSTEM\n")

    start = time.time()
    config = AppConfig.load()

    # ✅ Run full pipeline
    sim = run_backtest(config=config)

    # ✅ Final summary already printed inside runner
    # But you can optionally print again:
    print("\n📊 FINAL SUMMARY (from main)")
    sim.summary()

    total_time = time.time() - start

    print("\n🏁 BACKTEST FINISHED")
    print(f"⏱ Total runtime: {total_time/60:.2f} minutes")


# ✅ run directly
if __name__ == "__main__":
    main()
