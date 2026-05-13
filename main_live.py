import time

from live_sim.runner import run_live_sim


def main():
    """
    Main entry point for near-live simulation.
    """

    print("\n🚀 LAUNCHING LIVE SIMULATION SYSTEM\n")

    start = time.time()

    try:
        # ✅ start continuous live simulation
        run_live_sim(symbol="BTCUSDT")

    except KeyboardInterrupt:
        print("\n⛔ Live simulation stopped by user")

    total_time = time.time() - start

    print("\n🏁 LIVE SIMULATION ENDED")
    print(f"⏱ Total runtime: {total_time/60:.2f} minutes")


# ✅ run directly
if __name__ == "__main__":
    main()
``
