"""Represents the full lifecycle of one trade, including entries, exits, and PnL."""

import time

from common.debug import debug_print as print
from config import AppConfig


class Trade:
    """
    Represents a single trade lifecycle.

    A Trade stores the original setup context, all entry layers, the structural
    stop, the risk unit, exit state, and final PnL. It is the object passed
    between the simulator, account, and loggers so the reason and result of a
    trade remain connected.
    """

    def __init__(self, row, score, config=None):

        print("\nCreating new Trade object...")

        start = time.time()
        self.config = config or AppConfig.load()
        low_period = self.config.require("features", "structure", "low_period")
        self.stop_column = f"ll{low_period}"

        # Entry info
        self.entry_time = row.name
        self.entry_price = row["close"]
        self.score = score

        # Structure
        self.stop = row[self.stop_column]     # stop = recent low
        self.R = abs(self.entry_price - self.stop)

        # Position tracking
        self.entries = []           # [(price, size)]
        self.pyramid_level = 0

        # Exit info
        self.exit_time = None
        self.exit_price = None

        # Results
        self.pnl = 0
        self.pnl_R = 0
        self.pnl_R_total = 0
        self.pnl_R_initial = 0
        self.initial_risk_amount = 0
        self.total_risk_amount = 0

        # Store WHY trade happened (very important)
        self.conditions = {
            "score": score,
            "body_strength": row.get("body_strength", None),
            "close_position": row.get("close_position", None),
            "upper_wick_ratio": row.get("upper_wick_ratio", None),
            "compression": row.get("compression", None),
            "breakout": row.get("breakout", None),
        }

        print(f"Trade created at {self.entry_time}")
        print(f"  Entry price: {self.entry_price:.2f}")
        print(f"  Stop: {self.stop:.2f}")
        print(f"  R: {self.R:.2f}")

        print(f"Init elapsed: {time.time() - start:.4f}s")

    # ------------------------------------------
    # Add position (entry or pyramiding)
    # ------------------------------------------

    def add_entry(self, price, size):

        print("\nAdding position...")

        start = time.time()

        if not self.entries:
            self.initial_risk_amount = abs(price - self.stop) * size

        self.entries.append((price, size))

        print(f"Added: price={price:.2f}, size={size:.4f}")
        print(f"  Total entries: {len(self.entries)}")

        print(f"Elapsed: {time.time() - start:.4f}s")

    # ------------------------------------------
    # Close trade
    # ------------------------------------------

    def close(self, row):

        print("\nClosing trade...")

        start = time.time()

        self.exit_time = row.name
        self.exit_price = row["close"]

        print(f"Exit time: {self.exit_time}")
        print(f"Exit price: {self.exit_price:.2f}")

        self.compute_pnl()

        print(f"Elapsed: {time.time() - start:.4f}s")

    # ------------------------------------------
    # Compute PnL
    # ------------------------------------------

    def total_risk_to_stop(self):
        """
        Compute current total stop-risk in quote currency terms.

        For each entry layer, the risk contribution is the distance from entry
        to the structural stop multiplied by the layer size. Summing across
        layers yields the total worst-case loss if price hits the stop.
        """

        if self.stop is None:
            return 0

        total = 0
        for entry_price, size in self.entries:
            total += abs(entry_price - self.stop) * size

        return total

    def compute_pnl(self):

        print("\nComputing PnL...")

        start = time.time()

        total = 0

        for entry_price, size in self.entries:
            move = self.exit_price - entry_price
            pnl_part = move * size
            total += pnl_part

            print(f"  Entry: {entry_price:.2f} -> Exit: {self.exit_price:.2f} | PnL: {pnl_part:.2f}")

        self.pnl = total

        total_risk = self.total_risk_to_stop()
        self.total_risk_amount = total_risk

        if total_risk:
            self.pnl_R = total / total_risk
            self.pnl_R_total = self.pnl_R

        if self.initial_risk_amount:
            self.pnl_R_initial = total / self.initial_risk_amount

        print(f"\nTotal PnL: {self.pnl:.2f}")
        print(f"PnL (R multiple, total risk): {self.pnl_R_total:.2f}")
        print(f"PnL (R multiple, initial risk): {self.pnl_R_initial:.2f}")

        print(f"Elapsed: {time.time() - start:.4f}s")
