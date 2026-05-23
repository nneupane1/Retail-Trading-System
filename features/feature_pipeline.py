"""Creates all configured technical features required by the strategy modules."""

import time

from common.debug import debug_print as print
from config import AppConfig
from .indicators import (
    atr,
    bollinger_bands,
    ema,
    macd,
    rolling_high,
    rolling_low,
    session_vwap,
)
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
        indicator_config = self.config.get("features", "indicators", default={}) or {}
        self.atr_period = int(indicator_config.get("atr_period", 14))
        self.macd_fast_period = int(indicator_config.get("macd_fast_period", 12))
        self.macd_slow_period = int(indicator_config.get("macd_slow_period", 26))
        self.macd_signal_period = int(indicator_config.get("macd_signal_period", 9))
        self.bollinger_period = int(indicator_config.get("bollinger_period", 20))
        self.bollinger_std_dev = float(indicator_config.get("bollinger_std_dev", 2.0))
        self.candle_metrics = CandleMetricsCalculator(config=self.config)

    @staticmethod
    def _drop_incomplete_feature_rows(df, required_columns):
        before = len(df)
        df = df.dropna(subset=required_columns).copy()
        removed = before - len(df)

        if removed:
            print(f"Dropped {removed} incomplete feature row(s)")
        else:
            print("No incomplete feature rows detected")

        return df

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
        # 4. BREAKOUT EVENT (CLOSE-based)
        # ------------------------------

        t0 = time.time()

        previous_high_column = f"{high_column}_prev"
        previous_low_column = f"{low_column}_prev"
        df["prev_close"] = df["close"].shift(1)
        df[previous_high_column] = df[high_column].shift(1)
        df[previous_low_column] = df[low_column].shift(1)
        df["above_breakout_level"] = df["close"] > df[previous_high_column]
        df["breakout"] = (
            df["above_breakout_level"] &
            (df["prev_close"] <= df[previous_high_column])
        )
        df["below_breakdown_level"] = df["close"] < df[previous_low_column]
        df["breakdown"] = (
            df["below_breakdown_level"] &
            (df["prev_close"] >= df[previous_low_column])
        )

        print(f"Breakout event logic applied | Time: {time.time() - t0:.2f}s\n")

        # ------------------------------
        # 5. DIRECTIONAL INDICATORS
        # ------------------------------

        t0 = time.time()

        df["session_vwap"] = session_vwap(df)
        df["vwap_distance_ratio"] = (
            (df["close"] - df["session_vwap"]) / (df["session_vwap"] + 1e-9)
        )
        df["atr"] = atr(df, self.atr_period)
        df["atr_rising"] = df["atr"] > df["atr"].shift(1)

        macd_line, macd_signal, macd_hist = macd(
            df["close"],
            fast_period=self.macd_fast_period,
            slow_period=self.macd_slow_period,
            signal_period=self.macd_signal_period,
        )
        df["macd_line"] = macd_line
        df["macd_signal"] = macd_signal
        df["macd_hist"] = macd_hist

        bb_mid, bb_upper, bb_lower = bollinger_bands(
            df["close"],
            period=self.bollinger_period,
            std_dev=self.bollinger_std_dev,
        )
        df["bb_mid"] = bb_mid
        df["bb_upper"] = bb_upper
        df["bb_lower"] = bb_lower
        df["bb_breakout_up"] = df["close"] > df["bb_upper"]
        df["bb_breakout_down"] = df["close"] < df["bb_lower"]

        df["ema_gap_ratio"] = (
            (df[fast_ema_column] - df[slow_ema_column]) / (df[slow_ema_column] + 1e-9)
        )
        df["price_to_fast_ema_ratio"] = (
            (df["close"] - df[fast_ema_column]) / (df[fast_ema_column] + 1e-9)
        )
        df["fast_ema_slope_ratio"] = (
            df[fast_ema_column].pct_change().fillna(0.0)
        )

        print(f"Directional indicators computed | Time: {time.time() - t0:.2f}s\n")

        # ------------------------------
        # 6. CANDLE METRICS
        # ------------------------------

        df = self.candle_metrics.compute(df)

        # ------------------------------
        # 7. CLEAN INCOMPLETE ROWS
        # ------------------------------

        required_columns = [
            fast_ema_column,
            slow_ema_column,
            high_column,
            low_column,
            fast_range_column,
            slow_range_column,
            "prev_close",
            previous_high_column,
            previous_low_column,
            "session_vwap",
            "atr",
            "macd_line",
            "macd_signal",
            "macd_hist",
            "bb_mid",
            "bb_upper",
            "bb_lower",
            "ema_gap_ratio",
            "price_to_fast_ema_ratio",
            "fast_ema_slope_ratio",
            "body_strength",
            "upper_wick_ratio",
            "lower_wick_ratio",
            "close_position",
        ]
        df = self._drop_incomplete_feature_rows(df, required_columns)

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
