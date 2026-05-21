import time


class ExitEngine:
    """
    Final exit decision logic.
    """

    def should_exit(self, row, stop_price):
        start = time.time()

        print("\n❌ Checking exit conditions...")

        price = row["close"]

        # ✅ STOP LOSS CHECK
        if price < stop_price:
            print("🚨 STOP LOSS HIT → EXIT")
            print(f"   Price: {price:.2f}")
            print(f"   Stop:  {stop_price:.2f}")

            elapsed = time.time() - start
            print(f"⏱ Time taken: {elapsed:.4f}s")

            return True

        # ✅ OTHERWISE HOLD
        print("✅ No exit signal (price above stop)")
        print(f"   Price: {price:.2f}")
        print(f"   Stop:  {stop_price:.2f}")

        elapsed = time.time() - start
        print(f"⏱ Time taken: {elapsed:.4f}s")

        return False


def should_exit(row, stop_price):
    return ExitEngine().should_exit(row, stop_price)
