"""Scores the higher-timeframe market environment before entries are considered."""

import time

from common.debug import debug_print as print
from config import AppConfig


def _compute_slope(series, lookback):
    """
    Relative slope calculation over last N points.
    """

    if len(series) < lookback + 1:
        return 0.0

    current_value = series.iloc[-1]
    past_value = series.iloc[-(lookback + 1)]

    if past_value == 0:
        return 0.0

    return (current_value - past_value) / past_value


class RegimeDetector:
    """
    Multi-timeframe regime detector.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        self.ema_column = self.config.require("strategy", "regime", "ema_column")
        self.macro_weight = self.config.require("strategy", "regime", "macro_weight")
        self.macro_slope_weight = self.config.require(
            "strategy",
            "regime",
            "macro_slope_weight"
        )
        self.trend_weight = self.config.require("strategy", "regime", "trend_weight")
        self.slope_lookback = self.config.require("strategy", "regime", "slope_lookback")
        self.strong_score = self.config.require("strategy", "regime", "strong_score")
        self.moderate_score = self.config.require("strategy", "regime", "moderate_score")
        self.slope_threshold = self.config.get(
            "strategy",
            "regime",
            "slope_threshold",
            default=0.0
        )

    def classify(self, score):
        if score >= self.strong_score:
            return "strong"
        if score >= self.moderate_score:
            return "moderate"
        return "weak"

    def allows_entries(self, score):
        return score >= self.moderate_score

    def compute_regime(self, df_5h, df_12h):
        start = time.time()

        print("\nComputing market regime...")

        score = 0

        # ------------------------------
        # Macro timeframe
        # ------------------------------

        close_12h = df_12h["close"].iloc[-1]
        ema_12h = df_12h[self.ema_column].iloc[-1]

        if close_12h > ema_12h:
            score += self.macro_weight
            print(f"Macro bullish (price > {self.ema_column})")

        else:
            print("Macro not bullish")

        # slope (trend strength)
        slope_12h = _compute_slope(
            df_12h[self.ema_column],
            lookback=self.slope_lookback
        )

        if slope_12h > self.slope_threshold:
            score += self.macro_slope_weight
            print(
                "Macro EMA slope positive "
                f"(+{slope_12h:.4f} > {self.slope_threshold:.6f})"
            )
        else:
            print("Macro EMA slope not strong enough")

        # ------------------------------
        # Trend confirmation timeframe
        # ------------------------------

        close_5h = df_5h["close"].iloc[-1]
        ema_5h = df_5h[self.ema_column].iloc[-1]

        if close_5h > ema_5h:
            score += self.trend_weight
            print(f"Trend confirms uptrend (price > {self.ema_column})")
        else:
            print("Trend not confirming")

        # ------------------------------
        # FINAL OUTPUT
        # ------------------------------

        elapsed = time.time() - start

        max_score = self.macro_weight + self.macro_slope_weight + self.trend_weight

        print(f"\nRegime Score: {score}/{max_score}")
        print(f"Elapsed: {elapsed:.2f}s")
        print(f"  Macro EMA slope: {slope_12h:.4f}")
        print(f"  Slope threshold: {self.slope_threshold:.6f}")

        regime_classification = self.classify(score)

        if regime_classification == "strong":
            print("Strong trending environment")
        elif regime_classification == "moderate":
            print("WARNING: Moderate trend")
        else:
            print("Weak / choppy market")

        return score


def compute_regime(df_5h, df_12h, config=None):
    return RegimeDetector(config=config).compute_regime(df_5h, df_12h)
