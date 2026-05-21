"""Creates all configured technical features required by the strategy modules."""

import time

from config import AppConfig
from .indicators import ema, rolling_high, rolling_low
from .candle_metrics import CandleMetricsCalculator


class FeaturePipeline:
    """
    Builds the configured feature set for one OHLCV timeframe.

    This class owns the column contract used by downstream strategy modules:
    trend filters, structure, compression, breakout flags, and candle-behavior
    metrics are all created here from JSON-backed settings.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        self.fast_ema_period = self.config.require("features", "ema_periods", "fast")
        self.slow_ema_period = self.config.require("features", "ema_periods", "slow")
        self.high_period = self.config.require("features", "structure", "high_period")
        self.low_period = self.config.require("features", "structure", "low_period")
        self.fast_range_period = self.config.require(
            "features",
            "compression",
            "fast_range_period"
        )
        self.slow_range_period = self.config.require(
            "features",
            "compression",
            "slow_range_period"
        )
        self.compression_ratio = self.config.require("features", "compression", "ratio")
        self.candle_metrics = CandleMetricsCalculator(config=self.config)

    def compute(self, df):
        overall_start = time.time()

        print("\nStarting feature pipeline...\n")

        # ------------------------------
        # 1. TREND (EMA)
        # ------------------------------

        t0 = time.time()

        fast_ema_column = f"ema{self.fast_ema_period}"
        slow_ema_column = f"ema{self.slow_ema_period}"

        df[fast_ema_column] = ema(df["close"], self.fast_ema_period)
        df[slow_ema_column] = ema(df["close"], self.slow_ema_period)

        print(f"Trend features done | Time: {time.time() - t0:.2f}s\n")

        # ------------------------------
        # 2. STRUCTURE (HH / LL)
        # ------------------------------

        t0 = time.time()

        high_column = f"hh{self.high_period}"
        low_column = f"ll{self.low_period}"

        df[high_column] = rolling_high(df["high"], self.high_period)
        df[low_column] = rolling_low(df["low"], self.low_period)

        print(f"Structure (HH/LL) done | Time: {time.time() - t0:.2f}s\n")

        # ------------------------------
        # 3. COMPRESSION
        # ------------------------------

        t0 = time.time()

        fast_range_column = f"range_{self.fast_range_period}"
        slow_range_column = f"range_{self.slow_range_period}"

        df[fast_range_column] = (
            df["high"].rolling(self.fast_range_period).max() -
            df["low"].rolling(self.fast_range_period).min()
        )

        df[slow_range_column] = (
            df["high"].rolling(self.slow_range_period).max() -
            df["low"].rolling(self.slow_range_period).min()
        )

        df["compression"] = (
            df[fast_range_column] < (self.compression_ratio * df[slow_range_column])
        )

        print(f"Compression computed | Time: {time.time() - t0:.2f}s\n")

        # ------------------------------
        # 4. BREAKOUT (CLOSE-based)
        # ------------------------------

        t0 = time.time()

        previous_high_column = f"{high_column}_prev"
        df[previous_high_column] = df[high_column].shift(1)
        df["breakout"] = df["close"] > df[previous_high_column]

        print(f"Breakout logic applied | Time: {time.time() - t0:.2f}s\n")

        # ------------------------------
        # 5. CANDLE METRICS
        # ------------------------------

        df = self.candle_metrics.compute(df)

        # ------------------------------
        # FINAL SUMMARY
        # ------------------------------

        total_time = time.time() - overall_start

        print("\nFeature pipeline completed")
        print(f"Total time: {total_time:.2f}s")

        print("\nFinal columns:")
        print(df.columns.tolist())

        return df


def compute_features(df, config=None):
    return FeaturePipeline(config=config).compute(df)
