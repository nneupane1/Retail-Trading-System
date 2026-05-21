"""Computes candle body, wick, and close-location metrics used by entry and management logic."""

import time

from config import AppConfig


class CandleMetricsCalculator:
    """
    Computes quantitative candle behavior metrics.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        self.average_body_period = self.config.require(
            "features",
            "candle_metrics",
            "average_body_period"
        )

    def compute(self, df):
        start = time.time()

        print("\nComputing candle metrics...")

        # basic components
        body = (df["close"] - df["open"]).abs()
        avg_body = body.rolling(self.average_body_period).mean()

        high = df["high"]
        low = df["low"]
        close = df["close"]

        # full candle range
        candle_range = high - low

        # wick calculations
        upper_wick = high - df[["open", "close"]].max(axis=1)
        lower_wick = df[["open", "close"]].min(axis=1) - low

        # core metrics
        df["body_strength"] = body / (avg_body + 1e-6)

        df["upper_wick_ratio"] = upper_wick / (body + 1e-6)
        df["lower_wick_ratio"] = lower_wick / (body + 1e-6)

        df["close_position"] = (close - low) / (candle_range + 1e-6)

        elapsed = time.time() - start

        print("Candle metrics computed")
        print(f"Elapsed: {elapsed:.2f}s")

        print("\nSample output:")
        print(df[[
            "body_strength",
            "upper_wick_ratio",
            "lower_wick_ratio",
            "close_position"
        ]].tail(3))

        return df


def compute_candle_metrics(df, config=None):
    return CandleMetricsCalculator(config=config).compute(df)
