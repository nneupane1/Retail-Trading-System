"""Scores trade setup quality from bias, trend, compression, breakout, and candle behavior."""

import time

from common.debug import debug_print as print
from config import AppConfig


class ScoreEngine:
    """
    Computes a transparent setup-quality score from configured weights.

    Each scoring component corresponds to a market condition the strategy cares
    about: directional alignment, trend, compression, breakout confirmation,
    and candle quality. The resulting score is passed to the entry engine.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        self.scoring = self.config.require("strategy", "scoring")
        fast_ema_period = self.config.require("features", "ema_periods", "fast")
        self.fast_ema_column = f"ema{fast_ema_period}"

    def compute_score(self, row, bias):
        start = time.time()

        print("\nComputing entry score...")

        score = 0

        # ----------------------------------
        # 1. BIAS (direction alignment)
        # ----------------------------------

        if bias == "bullish":
            score += self.scoring["bias_weight"]
            print(f"Bias bullish (+{self.scoring['bias_weight']})")

        elif bias == "bearish":
            print("WARNING: Bearish bias (no score for long)")

        else:
            print("Neutral bias")

        # ----------------------------------
        # 2. TREND CONFIRMATION
        # ----------------------------------

        if row["close"] > row[self.fast_ema_column]:
            score += self.scoring["trend_weight"]
            print(f"Price above {self.fast_ema_column} (+{self.scoring['trend_weight']})")
        else:
            print(f"Price below {self.fast_ema_column}")

        # ----------------------------------
        # 3. COMPRESSION (setup quality)
        # ----------------------------------

        if row["compression"]:
            score += self.scoring["compression_weight"]
            print(f"Compression detected (+{self.scoring['compression_weight']})")
        else:
            print("No compression")

        # ----------------------------------
        # 4. BREAKOUT EVENT (core trigger)
        # ----------------------------------

        if row["breakout"]:
            score += self.scoring["breakout_weight"]
            print(f"Breakout event confirmed (+{self.scoring['breakout_weight']})")
        else:
            print("No breakout event")

        # ----------------------------------
        # 5. MOMENTUM (candle quality)
        # ----------------------------------

        if row["body_strength"] > self.scoring["body_strength_min"]:
            score += self.scoring["body_strength_weight"]
            print(f"Strong body (+{self.scoring['body_strength_weight']})")
        else:
            print("Weak body")

        if row["close_position"] > self.scoring["close_position_min"]:
            score += self.scoring["close_position_weight"]
            print(f"Strong close position (+{self.scoring['close_position_weight']})")
        else:
            print("Weak close")

        if row["upper_wick_ratio"] < self.scoring["upper_wick_max"]:
            score += self.scoring["upper_wick_weight"]
            print(f"Low rejection (+{self.scoring['upper_wick_weight']})")
        else:
            print("High rejection wick")

        # ----------------------------------
        # FINAL OUTPUT
        # ----------------------------------

        elapsed = time.time() - start

        print(f"\nFinal Score: {score}")
        print(f"Elapsed: {elapsed:.4f}s")

        entry_threshold = self.config.require("entry", "score_threshold")

        # quality interpretation
        if score > entry_threshold:
            print("High-quality setup")
        elif score == entry_threshold:
            print("Tradable setup")
        else:
            print("Weak setup")

        return score


def compute_score(row, bias, config=None):
    return ScoreEngine(config=config).compute_score(row, bias)
