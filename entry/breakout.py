"""Detects close-confirmed breakouts using configured rolling structure columns."""

import time

from config import AppConfig


class BreakoutDetector:
    """
    Close-based breakout detector.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        high_period = self.config.require("features", "structure", "high_period")
        self.previous_high_column = f"hh{high_period}_prev"

    def is_breakout(self, row):
        start = time.time()

        print("\nChecking breakout...")

        breakout = row["close"] > row[self.previous_high_column]

        if breakout:
            print("Breakout (CLOSE > previous HH)")
        else:
            print("No breakout")

        print(f"  Close: {row['close']:.2f}")
        print(f"  Prev HH: {row[self.previous_high_column]:.2f}")

        print(f"Elapsed: {time.time() - start:.4f}s")

        return breakout


def is_breakout(row, config=None):
    return BreakoutDetector(config=config).is_breakout(row)
