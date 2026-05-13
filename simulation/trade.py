import time


class Trade:
    """
    Represents a single trade lifecycle.

    Stores:
    - entry info
    - pyramid entries
    - stop + R
    - exit info
    - PnL
    - conditions (WHY trade was taken)
    """

    def __init__(self, row, score):

        print("\n📦 Creating new Trade object...")

        start = time.time()

        # ✅ Entry info
        self.entry_time = row.name
        self.entry_price = row["close"]
        self.score = score

        # ✅ Structure
        self.stop = row["ll10"]     # stop = recent low
        self.R = abs(self.entry_price - self.stop)

        # ✅ Position tracking
        self.entries = []           # [(price, size)]
        self.pyramid_level = 0

        # ✅ Exit info
        self.exit_time = None
        self.exit_price = None

        # ✅ Results
        self.pnl = 0
        self.pnl_R = 0

        # ✅ Store WHY trade happened (very important)
        self.conditions = {
            "score": score,
            "body_strength": row.get("body_strength", None),
            "close_position": row.get("close_position", None),
            "upper_wick_ratio": row.get("upper_wick_ratio", None),
            "compression": row.get("compression", None),
            "breakout": row.get("breakout", None),
        }

        print(f"✅ Trade created at {self.entry_time}")
        print(f"   Entry price: {self.entry_price:.2f}")
        print(f"   Stop: {self.stop:.2f}")
        print(f"   R: {self.R:.2f}")

        print(f"⏱ Init time: {time.time() - start:.4f}s")

    # ✅ ------------------------------------------
    # Add position (entry or pyramiding)
    # ✅ ------------------------------------------

    def add_entry(self, price, size):

        print("\n➕ Adding position...")

        start = time.time()

        self.entries.append((price, size))

        print(f"✅ Added: price={price:.2f}, size={size:.4f}")
        print(f"   Total entries: {len(self.entries)}")

        print(f"⏱ Time taken: {time.time() - start:.4f}s")

    # ✅ ------------------------------------------
    # Close trade
    # ✅ ------------------------------------------

    def close(self, row):

        print("\n🏁 Closing trade...")

        start = time.time()

        self.exit_time = row.name
        self.exit_price = row["close"]

        print(f"✅ Exit time: {self.exit_time}")
        print(f"✅ Exit price: {self.exit_price:.2f}")

        self.compute_pnl()

        print(f"⏱ Time taken: {time.time() - start:.4f}s")

    # ✅ ------------------------------------------
    # Compute PnL
    # ✅ ------------------------------------------

    def compute_pnl(self):

        print("\n💰 Computing PnL...")

        start = time.time()

        total = 0

        for entry_price, size in self.entries:
            move = self.exit_price - entry_price
            pnl_part = move * size
            total += pnl_part

            print(f"   Entry: {entry_price:.2f} → Exit: {self.exit_price:.2f} | PnL: {pnl_part:.2f}")

        self.pnl = total

        if self.R != 0:
            self.pnl_R = total / self.R

        print(f"\n✅ Total PnL: {self.pnl:.2f}")
        print(f"✅ PnL (R multiple): {self.pnl_R:.2f}")

        print(f"⏱ Time taken: {time.time() - start:.4f}s")
