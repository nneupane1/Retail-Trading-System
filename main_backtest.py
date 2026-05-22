"""Command-line entry point for running the historical backtest pipeline."""

import time

from common.debug import configure_debug
from config import AppConfig
from backtest.runner import run_backtest


def main():
    """
    Main entry point for full backtest.
    """

    print("\nLAUNCHING BACKTEST SYSTEM\n")

    start = time.time()
    config = AppConfig.load()
    configure_debug(config=config)

    # Run full pipeline
    sim = run_backtest(config=config)
    completed = getattr(sim, "backtest_completed", True)

    # Final summary already printed inside runner
    # But you can optionally print again:
    print("\nFINAL SUMMARY (from main)")
    sim.summary()

    total_time = time.time() - start

    if completed:
        print("\nBACKTEST FINISHED")
    else:
        print("\nBACKTEST PAUSED")
        print("Checkpoint saved. Re-run the same command to resume.")
    print(f"Total runtime: {total_time/60:.2f} minutes")


# run directly
if __name__ == "__main__":
    main()
