"""Detects close-confirmed breakout events using configured rolling structure columns."""

import time

from common.debug import debug_print as print
from config import AppConfig


class BreakoutDetector:
    """
    Close-based breakout-event detector.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        high_period = self.config.require("features", "structure", "high_period")
        self.previous_high_column = f"hh{high_period}_prev"
        self.previous_close_column = "prev_close"

    def is_breakout(self, row):
        start = time.time()

        print("\nChecking breakout event...")

        required_columns = [self.previous_high_column, self.previous_close_column]
        missing_columns = [column for column in required_columns if column not in row.index]

        if missing_columns:
            joined = ", ".join(missing_columns)
            raise KeyError(
                "BreakoutDetector requires event-based inputs: "
                f"{joined}"
            )

        previous_high = row[self.previous_high_column]
        previous_close = row[self.previous_close_column]

        above_level = row["close"] > previous_high
        crossed_level = previous_close <= previous_high
        breakout = above_level and crossed_level

        if breakout:
            print("Breakout event detected")
        else:
            print("No breakout event")

        print(f"  Close: {row['close']:.2f}")
        print(f"  Prev close: {previous_close:.2f}")
        print(f"  Prev HH: {previous_high:.2f}")
        print(f"  Above breakout level: {'YES' if above_level else 'NO'}")
        print(f"  Crossed from below: {'YES' if crossed_level else 'NO'}")

        print(f"Elapsed: {time.time() - start:.4f}s")

        return breakout


def is_breakout(row, config=None):
    return BreakoutDetector(config=config).is_breakout(row)
