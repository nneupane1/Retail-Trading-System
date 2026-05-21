"""Detects retest-style continuation setups against the configured breakout level."""

import time

from config import AppConfig


class RetestDetector:
    """
    Detects configured retest setups.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        high_period = self.config.require("features", "structure", "high_period")
        fast_ema_period = self.config.require("features", "ema_periods", "fast")
        self.high_column = f"hh{high_period}"
        self.previous_high_column = f"{self.high_column}_prev"
        self.fast_ema_column = f"ema{fast_ema_period}"

    def is_retest(self, row):
        start = time.time()

        print("\nChecking retest condition...")

        price = row["close"]
        prev_hh = row[self.previous_high_column]
        ema_value = row[self.fast_ema_column]

        # Step 1: pullback into zone (near previous HH)
        pullback = price <= prev_hh

        # Step 2: holds above EMA
        hold = price > ema_value

        # Step 3: continuation attempt
        continuation = price > prev_hh

        retest = pullback and hold and continuation

        # Debug prints
        print(f"  Price: {price:.2f}")
        print(f"  Prev HH: {prev_hh:.2f}")
        print(f"  {self.fast_ema_column}: {ema_value:.2f}")

        print(f"  Pullback: {'PASS' if pullback else 'FAIL'}")
        print(f"  Hold above EMA: {'PASS' if hold else 'FAIL'}")
        print(f"  Continuation: {'PASS' if continuation else 'FAIL'}")

        if retest:
            print("Retest setup confirmed")
        else:
            print("No valid retest")

        elapsed = time.time() - start
        print(f"Elapsed: {elapsed:.4f}s")

        return retest


def is_retest(row, config=None):
    return RetestDetector(config=config).is_retest(row)
