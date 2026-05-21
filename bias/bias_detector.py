import time

from config import AppConfig


def _compute_slope(series, lookback):
    """
    Simple slope calculation for EMA direction.
    """

    if len(series) < lookback + 1:
        return 0

    return series.iloc[-1] - series.iloc[-lookback]


class BiasDetector:
    """
    Determines market bias using the configured direction timeframe.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        self.ema_column = self.config.require("strategy", "bias", "ema_column")
        self.slope_lookback = self.config.require("strategy", "bias", "slope_lookback")

    def get_bias(self, df_1h):
        start = time.time()

        print("\n🧭 Determining market bias...")

        close = df_1h["close"].iloc[-1]
        ema_value = df_1h[self.ema_column].iloc[-1]

        slope = _compute_slope(df_1h[self.ema_column], lookback=self.slope_lookback)

        # ✅ ------------------------------
        # BIAS LOGIC
        # ✅ ------------------------------

        if close > ema_value and slope > 0:
            bias = "bullish"
            print(f"✅ Bullish bias: price > {self.ema_column} and slope > 0")

        elif close < ema_value and slope < 0:
            bias = "bearish"
            print(f"✅ Bearish bias: price < {self.ema_column} and slope < 0")

        else:
            bias = "neutral"
            print("⚠️ Neutral bias: no clear direction")

        # ✅ ------------------------------
        # DEBUG INFO
        # ✅ ------------------------------

        print(f"   Close: {close:.2f}")
        print(f"   {self.ema_column}: {ema_value:.2f}")
        print(f"   EMA slope: {slope:.4f}")

        elapsed = time.time() - start

        print(f"⏱ Time taken: {elapsed:.2f}s")

        return bias


def get_bias(df_1h, config=None):
    return BiasDetector(config=config).get_bias(df_1h)
