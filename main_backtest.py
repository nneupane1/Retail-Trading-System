"""Command-line entry point for running the historical backtest pipeline."""

import time

from config import AppConfig
from backtest.runner import run_backtest


def main():
    """
    Main entry point for full backtest.
    """

    print("\nLAUNCHING BACKTEST SYSTEM\n")

    start = time.time()
    config = AppConfig.load()

    # Run full pipeline
    sim = run_backtest(config=config)

    # Final summary already printed inside runner
    # But you can optionally print again:
    print("\nFINAL SUMMARY (from main)")
    sim.summary()

    total_time = time.time() - start

    print("\nBACKTEST FINISHED")
    print(f"Total runtime: {total_time/60:.2f} minutes")


# run directly
if __name__ == "__main__":
    main()
