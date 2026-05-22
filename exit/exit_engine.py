"""Evaluates hard exit conditions for an open trade."""

import time

from common.debug import debug_print as print


class ExitEngine:
    """
    Final exit decision logic.
    """

    def should_exit(self, row, stop_price):
        start = time.time()

        print("\nChecking exit conditions...")

        close_price = row["close"]
        low_price = row.get("low", close_price)

        # Stop exits are intrabar-aware: if price touched the stop anywhere
        # inside the candle, the trade is treated as stopped out at the stop.
        if low_price <= stop_price:
            print("STOP TOUCHED INTRABAR -> EXIT")
            print(f"  Low:   {low_price:.2f}")
            print(f"  Close: {close_price:.2f}")
            print(f"  Stop:  {stop_price:.2f}")

            elapsed = time.time() - start
            print(f"Elapsed: {elapsed:.4f}s")

            return True

        print("No exit signal (intrabar low above stop)")
        print(f"  Low:   {low_price:.2f}")
        print(f"  Close: {close_price:.2f}")
        print(f"  Stop:  {stop_price:.2f}")

        elapsed = time.time() - start
        print(f"Elapsed: {elapsed:.4f}s")

        return False


def should_exit(row, stop_price):
    return ExitEngine().should_exit(row, stop_price)
