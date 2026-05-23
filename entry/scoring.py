"""Scores long and short setup quality from aligned trend, structure, and candle behavior."""

import time

from common.debug import debug_print as print
from config import AppConfig


class ScoreEngine:
    """
    Computes transparent setup-quality scores from configured weights.

    The same engine evaluates both long and short candidates so the simulator
    can compare competing directional opportunities on the same closed candle.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        self.scoring = self.config.require("strategy", "scoring")
        fast_ema_period = self.config.require("features", "ema_periods", "fast")
        self.fast_ema_column = f"ema{fast_ema_period}"
        self.lower_close_position_max = self.scoring.get(
            "close_position_max",
            1.0 - self.scoring["close_position_min"],
        )
        self.lower_wick_max = self.scoring.get(
            "lower_wick_max",
            self.scoring["upper_wick_max"],
        )

    @staticmethod
    def _direction_label(side):
        return "LONG" if side == "long" else "SHORT"

    def compute_score(self, row, bias, side="long"):
        start = time.time()
        side = str(side).lower()
        direction = self._direction_label(side)
        required_bias = "bullish" if side == "long" else "bearish"
        event_column = "breakout" if side == "long" else "breakdown"

        print(f"\nComputing {direction} entry score...")

        score = 0

        if bias == required_bias:
            score += self.scoring["bias_weight"]
            print(f"{direction} bias aligned (+{self.scoring['bias_weight']})")
        else:
            print(f"{direction} bias not aligned")

        trend_aligned = (
            row["close"] > row[self.fast_ema_column]
            if side == "long"
            else row["close"] < row[self.fast_ema_column]
        )
        if trend_aligned:
            score += self.scoring["trend_weight"]
            comparator = "above" if side == "long" else "below"
            print(
                f"Price {comparator} {self.fast_ema_column} "
                f"(+{self.scoring['trend_weight']})"
            )
        else:
            comparator = "below" if side == "long" else "above"
            print(f"Price {comparator} {self.fast_ema_column}")

        vwap_weight = self.scoring.get("vwap_weight", 0)
        if vwap_weight:
            vwap_aligned = (
                row["close"] > row.get("session_vwap", row["close"])
                if side == "long"
                else row["close"] < row.get("session_vwap", row["close"])
            )
            if vwap_aligned:
                score += vwap_weight
                comparator = "above" if side == "long" else "below"
                print(f"Price {comparator} session VWAP (+{vwap_weight})")
            else:
                comparator = "below" if side == "long" else "above"
                print(f"Price {comparator} session VWAP")

        if row["compression"]:
            score += self.scoring["compression_weight"]
            print(f"Compression detected (+{self.scoring['compression_weight']})")
        else:
            print("No compression")

        event_weight_key = "breakout_weight" if side == "long" else "breakdown_weight"
        event_weight = self.scoring.get(
            event_weight_key,
            self.scoring.get("breakout_weight", 0),
        )
        if row[event_column]:
            score += event_weight
            print(f"{event_column.title()} event confirmed (+{event_weight})")
        else:
            print(f"No {event_column} event")

        if row["body_strength"] > self.scoring["body_strength_min"]:
            score += self.scoring["body_strength_weight"]
            print(f"Strong body (+{self.scoring['body_strength_weight']})")
        else:
            print("Weak body")

        close_position_aligned = (
            row["close_position"] > self.scoring["close_position_min"]
            if side == "long"
            else row["close_position"] < self.lower_close_position_max
        )
        if close_position_aligned:
            score += self.scoring["close_position_weight"]
            print(
                "Directional close quality "
                f"(+{self.scoring['close_position_weight']})"
            )
        else:
            print("Weak directional close")

        wick_metric = "upper_wick_ratio" if side == "long" else "lower_wick_ratio"
        wick_threshold = (
            self.scoring["upper_wick_max"]
            if side == "long"
            else self.lower_wick_max
        )
        wick_weight = (
            self.scoring["upper_wick_weight"]
            if side == "long"
            else self.scoring.get(
                "lower_wick_weight",
                self.scoring["upper_wick_weight"],
            )
        )
        if row[wick_metric] < wick_threshold:
            score += wick_weight
            print(f"Directional wick quality (+{wick_weight})")
        else:
            print("Poor directional wick quality")

        atr_weight = self.scoring.get("atr_weight", 0)
        if atr_weight:
            if bool(row.get("atr_rising", False)):
                score += atr_weight
                print(f"Volatility expansion (+{atr_weight})")
            else:
                print("ATR not expanding")

        macd_weight = self.scoring.get("macd_weight", 0)
        if macd_weight:
            macd_aligned = (
                row.get("macd_line", 0.0) > row.get("macd_signal", 0.0)
                and row.get("macd_hist", 0.0) > 0
                if side == "long"
                else row.get("macd_line", 0.0) < row.get("macd_signal", 0.0)
                and row.get("macd_hist", 0.0) < 0
            )
            if macd_aligned:
                score += macd_weight
                print(f"MACD aligned (+{macd_weight})")
            else:
                print("MACD not aligned")

        bollinger_weight = self.scoring.get("bollinger_weight", 0)
        if bollinger_weight:
            bollinger_aligned = (
                bool(row.get("bb_breakout_up", False))
                if side == "long"
                else bool(row.get("bb_breakout_down", False))
            )
            if bollinger_aligned:
                score += bollinger_weight
                print(f"Bollinger breakout context (+{bollinger_weight})")
            else:
                print("No Bollinger breakout context")

        elapsed = time.time() - start

        print(f"\nFinal {direction} Score: {score}")
        print(f"Elapsed: {elapsed:.4f}s")

        entry_threshold = self.config.require("entry", "score_threshold")
        if score > entry_threshold:
            print(f"High-quality {direction} setup")
        elif score == entry_threshold:
            print(f"Tradable {direction} setup")
        else:
            print(f"Weak {direction} setup")

        return score


def compute_score(row, bias, side="long", config=None):
    return ScoreEngine(config=config).compute_score(row, bias, side=side)
