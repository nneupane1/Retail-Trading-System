import time

from config import AppConfig
from .indicators import ema, atr, rolling_high, rolling_low
from .candle_metrics import CandleMetricsCalculator


class FeaturePipeline:
    """
    Full configured feature pipeline.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        self.fast_ema_period = self.config.require("features", "ema_periods", "fast")
        self.slow_ema_period = self.config.require("features", "ema_periods", "slow")
        self.atr_period = self.config.require("features", "atr_period")
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

        print("\n🚀 Starting feature pipeline...\n")

        # ✅ ------------------------------
        # 1. TREND (EMA)
        # ✅ ------------------------------

        t0 = time.time()

        fast_ema_column = f"ema{self.fast_ema_period}"
        slow_ema_column = f"ema{self.slow_ema_period}"

        df[fast_ema_column] = ema(df["close"], self.fast_ema_period)
        df[slow_ema_column] = ema(df["close"], self.slow_ema_period)

        print(f"✅ Trend features done | ⏱ {time.time() - t0:.2f}s\n")

        # ✅ ------------------------------
        # 2. VOLATILITY (ATR)
        # ✅ ------------------------------

        t0 = time.time()

        df["atr"] = atr(df, self.atr_period)

        print(f"✅ Volatility (ATR) done | ⏱ {time.time() - t0:.2f}s\n")

        # ✅ ------------------------------
        # 3. STRUCTURE (HH / LL)
        # ✅ ------------------------------

        t0 = time.time()

        high_column = f"hh{self.high_period}"
        low_column = f"ll{self.low_period}"

        df[high_column] = rolling_high(df["high"], self.high_period)
        df[low_column] = rolling_low(df["low"], self.low_period)

        print(f"✅ Structure (HH/LL) done | ⏱ {time.time() - t0:.2f}s\n")

        # ✅ ------------------------------
        # 4. COMPRESSION
        # ✅ ------------------------------

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

        print(f"✅ Compression computed | ⏱ {time.time() - t0:.2f}s\n")

        # ✅ ------------------------------
        # 5. BREAKOUT (CLOSE-based)
        # ✅ ------------------------------

        t0 = time.time()

        previous_high_column = f"{high_column}_prev"
        df[previous_high_column] = df[high_column].shift(1)
        df["breakout"] = df["close"] > df[previous_high_column]

        print(f"✅ Breakout logic applied | ⏱ {time.time() - t0:.2f}s\n")

        # ✅ ------------------------------
        # 6. CANDLE METRICS (IMPORTANT)
        # ✅ ------------------------------

        df = self.candle_metrics.compute(df)

        # ✅ ------------------------------
        # FINAL SUMMARY
        # ✅ ------------------------------

        total_time = time.time() - overall_start

        print("\n🎯 Feature pipeline completed")
        print(f"⏱ Total time: {total_time:.2f}s")

        print("\n📊 Final columns:")
        print(df.columns.tolist())

        return df


def compute_features(df, config=None):
    return FeaturePipeline(config=config).compute(df)
