"""Evaluates hard exit conditions for an open trade."""

import time

from common.debug import debug_print as print


class ExitEngine:
    """
    Final exit decision logic.
    """

    def should_exit(self, row, stop_price, side="long"):
        start = time.time()
        side = str(side).lower()

        print("\nChecking exit conditions...")

        close_price = row["close"]
        low_price = row.get("low", close_price)
        high_price = row.get("high", close_price)

        if side == "short":
            if high_price >= stop_price:
                print("SHORT STOP TOUCHED INTRABAR -> EXIT")
                print(f"  High:  {high_price:.2f}")
                print(f"  Close: {close_price:.2f}")
                print(f"  Stop:  {stop_price:.2f}")
                print(f"Elapsed: {time.time() - start:.4f}s")
                return True

            print("No short exit signal (intrabar high below stop)")
            print(f"  High:  {high_price:.2f}")
            print(f"  Close: {close_price:.2f}")
            print(f"  Stop:  {stop_price:.2f}")
            print(f"Elapsed: {time.time() - start:.4f}s")
            return False

        if low_price <= stop_price:
            print("LONG STOP TOUCHED INTRABAR -> EXIT")
            print(f"  Low:   {low_price:.2f}")
            print(f"  Close: {close_price:.2f}")
            print(f"  Stop:  {stop_price:.2f}")
            print(f"Elapsed: {time.time() - start:.4f}s")
            return True

        print("No long exit signal (intrabar low above stop)")
        print(f"  Low:   {low_price:.2f}")
        print(f"  Close: {close_price:.2f}")
        print(f"  Stop:  {stop_price:.2f}")
        print(f"Elapsed: {time.time() - start:.4f}s")
        return False


def should_exit(row, stop_price, side="long"):
    return ExitEngine().should_exit(row, stop_price, side=side)
