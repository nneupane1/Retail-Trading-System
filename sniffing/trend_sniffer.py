"""Checks whether an open trend remains healthy enough to keep holding the trade."""

import time

from config import AppConfig


class TrendSniffer:
    """
    Determines if the active trend remains healthy enough to hold.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        self.thresholds = self.config.require("strategy", "sniffing")
        fast_ema_period = self.config.require("features", "ema_periods", "fast")
        self.fast_ema_column = f"ema{fast_ema_period}"

    def is_trend_alive(self, row):
        start = time.time()

        print("\nSniffing trend strength...")

        price = row["close"]
        ema_value = row[self.fast_ema_column]
        body_strength = row["body_strength"]
        upper_wick = row["upper_wick_ratio"]
        close_pos = row["close_position"]

        # Conditions
        above_ema = price > ema_value
        strong_body = body_strength > self.thresholds["body_strength_min"]
        low_rejection = upper_wick < self.thresholds["upper_wick_max"]
        strong_close = close_pos > self.thresholds["close_position_min"]

        trend_alive = above_ema and strong_body and low_rejection and strong_close

        # Debug prints
        print(f"  Price: {price:.2f}")
        print(f"  {self.fast_ema_column}: {ema_value:.2f}")

        print(f"\n  Above {self.fast_ema_column}: {'PASS' if above_ema else 'FAIL'}")
        print(f"  Body strength: {body_strength:.2f} {'PASS' if strong_body else 'FAIL'}")
        print(f"  Upper wick: {upper_wick:.2f} {'PASS' if low_rejection else 'FAIL'}")
        print(f"  Close position: {close_pos:.2f} {'PASS' if strong_close else 'FAIL'}")

        if trend_alive:
            print("\nTrend is alive -> HOLD")
        else:
            print("\nTrend weakening -> consider EXIT")

        elapsed = time.time() - start
        print(f"Elapsed: {elapsed:.4f}s")

        return trend_alive


def is_trend_alive(row, config=None):
    return TrendSniffer(config=config).is_trend_alive(row)
