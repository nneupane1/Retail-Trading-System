"""Determines directional market bias from the configured higher timeframe trend filter."""

import math
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

    @staticmethod
    def _squash_signed(value, scale):
        scale = abs(float(scale)) or 1e-9
        return math.tanh(float(value) / scale)

    def get_bias_snapshot(self, df_1h):
        start = time.time()

        print("\nDetermining market bias...")

        close = float(df_1h["close"].iloc[-1])
        ema_value = float(df_1h[self.ema_column].iloc[-1])
        slope = float(
            _compute_slope(df_1h[self.ema_column], lookback=self.slope_lookback)
        )
        price_vs_ema_ratio = (
            (close - ema_value) / ema_value
            if ema_value
            else 0.0
        )

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

        distance_strength = self._squash_signed(
            price_vs_ema_ratio,
            max(abs(self.slope_threshold), 0.001),
        )
        slope_strength = self._squash_signed(
            slope,
            max(abs(self.slope_threshold), 0.0005),
        )
        directional_strength = 0.5 * (distance_strength + slope_strength)

        print(f"  Close: {close:.2f}")
        print(f"  {self.ema_column}: {ema_value:.2f}")
        print(f"  EMA slope: {slope:.4f}")
        print(f"  Slope threshold: {self.slope_threshold:.6f}")

        elapsed = time.time() - start
        print(f"Elapsed: {elapsed:.2f}s")

        return {
            "label": bias,
            "close": close,
            "ema_value": ema_value,
            "ema_column": self.ema_column,
            "price_vs_ema_ratio": price_vs_ema_ratio,
            "ema_slope": slope,
            "slope_threshold": float(self.slope_threshold),
            "distance_strength": distance_strength,
            "slope_strength": slope_strength,
            "directional_strength": directional_strength,
        }

    def get_bias(self, df_1h):
        return self.get_bias_snapshot(df_1h)["label"]


def get_bias(df_1h, config=None):
    return BiasDetector(config=config).get_bias(df_1h)


def get_bias_snapshot(df_1h, config=None):
    return BiasDetector(config=config).get_bias_snapshot(df_1h)
