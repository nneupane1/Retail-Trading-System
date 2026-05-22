"""Determines directional market bias from the configured higher timeframe trend filter."""

import time

from common.debug import debug_print as print
from config import AppConfig


def _compute_slope(series, lookback):
    """
    Relative slope calculation for EMA direction.
    """

    if len(series) < lookback + 1:
        return 0.0

    current_value = series.iloc[-1]
    past_value = series.iloc[-(lookback + 1)]

    if past_value == 0:
        return 0.0

    return (current_value - past_value) / past_value


class BiasDetector:
    """
    Determines market bias using the configured direction timeframe.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        self.ema_column = self.config.require("strategy", "bias", "ema_column")
        self.slope_lookback = self.config.require("strategy", "bias", "slope_lookback")
        self.slope_threshold = self.config.get(
            "strategy",
            "bias",
            "slope_threshold",
            default=0.0
        )

    def get_bias(self, df_1h):
        start = time.time()

        print("\nDetermining market bias...")

        close = df_1h["close"].iloc[-1]
        ema_value = df_1h[self.ema_column].iloc[-1]

        slope = _compute_slope(df_1h[self.ema_column], lookback=self.slope_lookback)

        # ------------------------------
        # BIAS LOGIC
        # ------------------------------

        if close > ema_value and slope > self.slope_threshold:
            bias = "bullish"
            print(
                f"Bullish bias: price > {self.ema_column} and "
                f"slope > {self.slope_threshold:.6f}"
            )

        elif close < ema_value and slope < -self.slope_threshold:
            bias = "bearish"
            print(
                f"Bearish bias: price < {self.ema_column} and "
                f"slope < -{self.slope_threshold:.6f}"
            )

        else:
            bias = "neutral"
            print("WARNING: Neutral bias: no clear direction")

        # ------------------------------
        # DEBUG INFO
        # ------------------------------

        print(f"  Close: {close:.2f}")
        print(f"  {self.ema_column}: {ema_value:.2f}")
        print(f"  EMA slope: {slope:.4f}")
        print(f"  Slope threshold: {self.slope_threshold:.6f}")

        elapsed = time.time() - start

        print(f"Elapsed: {elapsed:.2f}s")

        return bias


def get_bias(df_1h, config=None):
    return BiasDetector(config=config).get_bias(df_1h)
