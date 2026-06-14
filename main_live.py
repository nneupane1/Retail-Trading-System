"""Command-line entry point for running the near-live simulation loop."""

import time

from common.debug import configure_debug
from common.runtime_readiness import assert_runtime_mode_ready
from config import AppConfig
from live_sim.runner import run_live_sim


def main():
    """
    Main entry point for near-live simulation.
    """

    print("\nLAUNCHING LIVE SIMULATION SYSTEM\n")

    start = time.time()
    config = AppConfig.load()
    configure_debug(config=config)
    readiness = assert_runtime_mode_ready(
        config=config,
        mode=config.get("live_sim", "mode", default="portfolio_paper"),
    )
    if readiness.get("warnings"):
        print("Runtime readiness warnings:")
        for warning in readiness["warnings"]:
            print(f"  - {warning}")
    print(
        "Validated boundary: "
        f"{readiness.get('validated_boundary') or 'unknown'} | "
        f"classification: {readiness.get('classification')}"
    )

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
