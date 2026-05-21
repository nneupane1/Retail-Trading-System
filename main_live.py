"""Command-line entry point for running the near-live simulation loop."""

import time

from config import AppConfig
from live_sim.runner import run_live_sim


def main():
    """
    Main entry point for near-live simulation.
    """

    print("\nLAUNCHING LIVE SIMULATION SYSTEM\n")

    start = time.time()
    config = AppConfig.load()

    try:
        # start continuous live simulation
        run_live_sim(config=config)

    except KeyboardInterrupt:
        print("\nSTOP: Live simulation stopped by user")

    total_time = time.time() - start

    print("\nLIVE SIMULATION ENDED")
    print(f"Total runtime: {total_time/60:.2f} minutes")


# run directly
if __name__ == "__main__":
    main()
