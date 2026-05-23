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
        self.lower_close_position_max = self.thresholds.get(
            "close_position_max",
            1.0 - self.thresholds["close_position_min"],
        )
        self.lower_wick_max = self.thresholds.get(
            "lower_wick_max",
            self.thresholds["upper_wick_max"],
        )
        self.require_short_vwap_alignment = bool(
            self.thresholds.get("require_short_vwap_alignment", True)
        )
        self.side_overrides = {
            str(side).lower(): dict(values or {})
            for side, values in (self.thresholds.get("by_side", {}) or {}).items()
        }

    def _side_value(self, side, key, default):
        return self.side_overrides.get(side, {}).get(key, default)

    def is_trend_alive(self, row, trade=None):
        start = time.time()

        print("\nSniffing trend strength...")

        side = getattr(trade, "side", "long") if trade is not None else "long"
        price = row["close"]
        body_strength = row["body_strength"]
        close_pos = row["close_position"]
        wick_metric = "upper_wick_ratio" if side == "long" else "lower_wick_ratio"
        wick_value = row[wick_metric]
        wick_threshold = (
            self._side_value(side, "upper_wick_max", self.thresholds["upper_wick_max"])
            if side == "long"
            else self._side_value(side, "lower_wick_max", self.lower_wick_max)
        )
        min_confirmations = self._side_value(
            side,
            "min_confirmations",
            self.thresholds.get("min_confirmations", 1),
        )

        open_r_multiple = None
        anchor_column = self.fast_ema_column
        relax_after_r = self._side_value(
            side,
            "relax_after_r",
            self.thresholds.get("relax_after_r"),
        )
        relaxed_min_confirmations = self._side_value(
            side,
            "relaxed_min_confirmations",
            self.thresholds.get("relaxed_min_confirmations", min_confirmations),
        )

        if trade is not None and getattr(trade, "R", 0):
            if side == "short":
                open_r_multiple = (trade.entry_price - price) / trade.R
            else:
                open_r_multiple = (price - trade.entry_price) / trade.R

            if relax_after_r is not None and open_r_multiple >= relax_after_r:
                min_confirmations = relaxed_min_confirmations

            slow_anchor_after_r = self._side_value(
                side,
                "slow_anchor_after_r",
                self.thresholds.get("slow_anchor_after_r"),
            )
            if (
                slow_anchor_after_r is not None
                and open_r_multiple >= slow_anchor_after_r
                and self.slow_ema_column in row
            ):
                anchor_column = self.slow_ema_column

        ema_value = row[anchor_column]

        if side == "short":
            anchor_aligned = price < ema_value
            short_close_position_max = self._side_value(
                side,
                "close_position_max",
                self.lower_close_position_max,
            )
            strong_close = close_pos < short_close_position_max
            vwap_value = row.get("session_vwap", price)
            require_short_vwap_alignment = self._side_value(
                side,
                "require_short_vwap_alignment",
                self.require_short_vwap_alignment,
            )
            vwap_aligned = (price < vwap_value) if require_short_vwap_alignment else True
        else:
            anchor_aligned = price > ema_value
            strong_close = close_pos > self._side_value(
                side,
                "close_position_min",
                self.thresholds["close_position_min"],
            )
            vwap_aligned = True
            vwap_value = row.get("session_vwap", price)

        strong_body = body_strength > self._side_value(
            side,
            "body_strength_min",
            self.thresholds["body_strength_min"],
        )
        clean_wick = wick_value < wick_threshold

        confirmation_count = sum([
            strong_body,
            clean_wick,
            strong_close,
        ])
        trend_alive = (
            anchor_aligned
            and vwap_aligned
            and confirmation_count >= min_confirmations
        )

        print(f"  Side: {side.upper()}")
        print(f"  Price: {price:.2f}")
        print(f"  Anchor EMA ({anchor_column}): {ema_value:.2f}")
        if side == "short":
            print(f"  Session VWAP: {vwap_value:.2f}")

        print(
            f"\n  Anchor aligned: {'PASS' if anchor_aligned else 'FAIL'}"
        )
        if side == "short" and require_short_vwap_alignment:
            print(f"  Below session VWAP: {'PASS' if vwap_aligned else 'FAIL'}")
        print(f"  Body strength: {body_strength:.2f} {'PASS' if strong_body else 'FAIL'}")
        print(f"  {wick_metric}: {wick_value:.2f} {'PASS' if clean_wick else 'FAIL'}")
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
