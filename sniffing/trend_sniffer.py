"""Checks whether an open trend remains healthy enough to keep holding the trade."""

import time

from common.debug import debug_print as print
from config import AppConfig


class TrendSniffer:
    """
    Determines if the active trend remains healthy enough to hold.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        self.thresholds = self.config.require("strategy", "sniffing")
        fast_ema_period = self.config.require("features", "ema_periods", "fast")
        slow_ema_period = self.config.require("features", "ema_periods", "slow")
        self.fast_ema_column = f"ema{fast_ema_period}"
        self.slow_ema_column = f"ema{slow_ema_period}"

    def is_trend_alive(self, row, trade=None):
        start = time.time()

        print("\nSniffing trend strength...")

        price = row["close"]
        body_strength = row["body_strength"]
        upper_wick = row["upper_wick_ratio"]
        close_pos = row["close_position"]
        min_confirmations = self.thresholds.get("min_confirmations", 1)

        open_r_multiple = None
        anchor_column = self.fast_ema_column
        relax_after_r = self.thresholds.get("relax_after_r")
        relaxed_min_confirmations = self.thresholds.get(
            "relaxed_min_confirmations",
            min_confirmations,
        )

        if trade is not None and getattr(trade, "R", 0):
            open_r_multiple = (price - trade.entry_price) / trade.R
            if relax_after_r is not None and open_r_multiple >= relax_after_r:
                min_confirmations = relaxed_min_confirmations
            slow_anchor_after_r = self.thresholds.get("slow_anchor_after_r")
            if (
                slow_anchor_after_r is not None
                and open_r_multiple >= slow_anchor_after_r
                and self.slow_ema_column in row
            ):
                anchor_column = self.slow_ema_column

        ema_value = row[anchor_column]

        # Conditions
        above_ema = price > ema_value
        strong_body = body_strength > self.thresholds["body_strength_min"]
        low_rejection = upper_wick < self.thresholds["upper_wick_max"]
        strong_close = close_pos > self.thresholds["close_position_min"]

        confirmation_count = sum([
            strong_body,
            low_rejection,
            strong_close,
        ])
        trend_alive = above_ema and confirmation_count >= min_confirmations

        # Debug prints
        print(f"  Price: {price:.2f}")
        print(f"  Anchor EMA ({anchor_column}): {ema_value:.2f}")

        print(f"\n  Above {anchor_column}: {'PASS' if above_ema else 'FAIL'}")
        print(f"  Body strength: {body_strength:.2f} {'PASS' if strong_body else 'FAIL'}")
        print(f"  Upper wick: {upper_wick:.2f} {'PASS' if low_rejection else 'FAIL'}")
        print(f"  Close position: {close_pos:.2f} {'PASS' if strong_close else 'FAIL'}")
        if open_r_multiple is not None:
            print(f"  Open R multiple: {open_r_multiple:.2f}")
        print(
            "  Confirmation count: "
            f"{confirmation_count}/3 "
            f"(need {min_confirmations})"
        )

        if trend_alive:
            print("\nTrend is alive -> HOLD")
        else:
            print("\nTrend weakening -> consider EXIT")

        elapsed = time.time() - start
        print(f"Elapsed: {elapsed:.4f}s")

        return trend_alive


def is_trend_alive(row, config=None):
    return TrendSniffer(config=config).is_trend_alive(row)
