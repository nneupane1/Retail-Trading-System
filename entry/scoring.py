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

    @staticmethod
    def _clip(value, lower=0.0, upper=1.0):
        return max(lower, min(float(value), upper))

    @staticmethod
    def _sum_component_field(components, field):
        return sum(float(component.get(field, 0.0)) for component in components.values())

    def compute_score_components(self, row, bias, side="long"):
        side = str(side).lower()
        direction = self._direction_label(side)
        required_bias = "bullish" if side == "long" else "bearish"
        event_column = "breakout" if side == "long" else "breakdown"
        components = {}

        bias_aligned = bias == required_bias
        components["bias"] = {
            "aligned": bias_aligned,
            "weight": float(self.scoring["bias_weight"]),
            "points": float(self.scoring["bias_weight"]) if bias_aligned else 0.0,
            "actual_bias": str(bias).lower(),
            "required_bias": required_bias,
            "debug_true": f"{direction} bias aligned (+{self.scoring['bias_weight']})",
            "debug_false": f"{direction} bias not aligned",
        }

        trend_aligned = (
            row["close"] > row[self.fast_ema_column]
            if side == "long"
            else row["close"] < row[self.fast_ema_column]
        )
        comparator = "above" if side == "long" else "below"
        opposite_comparator = "below" if side == "long" else "above"
        components["trend"] = {
            "aligned": trend_aligned,
            "weight": float(self.scoring["trend_weight"]),
            "points": float(self.scoring["trend_weight"]) if trend_aligned else 0.0,
            "close": float(row["close"]),
            "anchor": float(row[self.fast_ema_column]),
            "anchor_column": self.fast_ema_column,
            "debug_true": (
                f"Price {comparator} {self.fast_ema_column} "
                f"(+{self.scoring['trend_weight']})"
            ),
            "debug_false": f"Price {opposite_comparator} {self.fast_ema_column}",
        }

        vwap_weight = self.scoring.get("vwap_weight", 0)
        vwap_aligned = (
            row["close"] > row.get("session_vwap", row["close"])
            if side == "long"
            else row["close"] < row.get("session_vwap", row["close"])
        )
        components["vwap"] = {
            "aligned": bool(vwap_aligned),
            "weight": float(vwap_weight),
            "points": float(vwap_weight) if vwap_weight and vwap_aligned else 0.0,
            "close": float(row["close"]),
            "session_vwap": float(row.get("session_vwap", row["close"])),
            "debug_true": f"Price {comparator} session VWAP (+{vwap_weight})",
            "debug_false": f"Price {opposite_comparator} session VWAP",
        }

        compression_aligned = bool(row["compression"])
        components["compression"] = {
            "aligned": compression_aligned,
            "weight": float(self.scoring["compression_weight"]),
            "points": (
                float(self.scoring["compression_weight"])
                if compression_aligned
                else 0.0
            ),
            "debug_true": (
                f"Compression detected (+{self.scoring['compression_weight']})"
            ),
            "debug_false": "No compression",
        }

        event_weight_key = "breakout_weight" if side == "long" else "breakdown_weight"
        event_weight = self.scoring.get(
            event_weight_key,
            self.scoring.get("breakout_weight", 0),
        )
        event_aligned = bool(row[event_column])
        components["event"] = {
            "aligned": event_aligned,
            "weight": float(event_weight),
            "points": float(event_weight) if event_aligned else 0.0,
            "event_column": event_column,
            "debug_true": f"{event_column.title()} event confirmed (+{event_weight})",
            "debug_false": f"No {event_column} event",
        }

        body_aligned = row["body_strength"] > self.scoring["body_strength_min"]
        components["body_strength"] = {
            "aligned": body_aligned,
            "weight": float(self.scoring["body_strength_weight"]),
            "points": (
                float(self.scoring["body_strength_weight"])
                if body_aligned
                else 0.0
            ),
            "value": float(row["body_strength"]),
            "threshold": float(self.scoring["body_strength_min"]),
            "debug_true": (
                f"Strong body (+{self.scoring['body_strength_weight']})"
            ),
            "debug_false": "Weak body",
        }

        close_position_aligned = (
            row["close_position"] > self.scoring["close_position_min"]
            if side == "long"
            else row["close_position"] < self.lower_close_position_max
        )
        components["close_position"] = {
            "aligned": close_position_aligned,
            "weight": float(self.scoring["close_position_weight"]),
            "points": (
                float(self.scoring["close_position_weight"])
                if close_position_aligned
                else 0.0
            ),
            "value": float(row["close_position"]),
            "threshold": (
                float(self.scoring["close_position_min"])
                if side == "long"
                else float(self.lower_close_position_max)
            ),
            "debug_true": (
                "Directional close quality "
                f"(+{self.scoring['close_position_weight']})"
            ),
            "debug_false": "Weak directional close",
        }

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
        wick_aligned = row[wick_metric] < wick_threshold
        components["wick"] = {
            "aligned": wick_aligned,
            "weight": float(wick_weight),
            "points": float(wick_weight) if wick_aligned else 0.0,
            "metric": wick_metric,
            "value": float(row[wick_metric]),
            "threshold": float(wick_threshold),
            "debug_true": f"Directional wick quality (+{wick_weight})",
            "debug_false": "Poor directional wick quality",
        }

        atr_weight = self.scoring.get("atr_weight", 0)
        atr_aligned = bool(row.get("atr_rising", False))
        components["atr"] = {
            "aligned": atr_aligned,
            "weight": float(atr_weight),
            "points": float(atr_weight) if atr_weight and atr_aligned else 0.0,
            "debug_true": f"Volatility expansion (+{atr_weight})",
            "debug_false": "ATR not expanding",
        }

        macd_weight = self.scoring.get("macd_weight", 0)
        macd_aligned = (
            row.get("macd_line", 0.0) > row.get("macd_signal", 0.0)
            and row.get("macd_hist", 0.0) > 0
            if side == "long"
            else row.get("macd_line", 0.0) < row.get("macd_signal", 0.0)
            and row.get("macd_hist", 0.0) < 0
        )
        components["macd"] = {
            "aligned": macd_aligned,
            "weight": float(macd_weight),
            "points": float(macd_weight) if macd_weight and macd_aligned else 0.0,
            "macd_line": float(row.get("macd_line", 0.0) or 0.0),
            "macd_signal": float(row.get("macd_signal", 0.0) or 0.0),
            "macd_hist": float(row.get("macd_hist", 0.0) or 0.0),
            "debug_true": f"MACD aligned (+{macd_weight})",
            "debug_false": "MACD not aligned",
        }

        bollinger_weight = self.scoring.get("bollinger_weight", 0)
        bollinger_aligned = (
            bool(row.get("bb_breakout_up", False))
            if side == "long"
            else bool(row.get("bb_breakout_down", False))
        )
        components["bollinger"] = {
            "aligned": bollinger_aligned,
            "weight": float(bollinger_weight),
            "points": (
                float(bollinger_weight)
                if bollinger_weight and bollinger_aligned
                else 0.0
            ),
            "debug_true": (
                f"Bollinger breakout context (+{bollinger_weight})"
            ),
            "debug_false": "No Bollinger breakout context",
        }

        return components

    def compute_normalized_score(self, components):
        max_score = self._sum_component_field(components, "weight")
        if max_score <= 0:
            return 0.0
        raw_score = self._sum_component_field(components, "points")
        return self._clip(raw_score / max_score)

    def compute_score_details(self, row, bias, side="long", emit_debug=False):
        start = time.time()
        side = str(side).lower()
        direction = self._direction_label(side)
        entry_threshold = self.config.require("entry", "score_threshold")
        components = self.compute_score_components(row, bias, side=side)
        score = self._sum_component_field(components, "points")
        normalized_score = self.compute_normalized_score(components)
        max_score = self._sum_component_field(components, "weight")

        if emit_debug:
            print(f"\nComputing {direction} entry score...")
            debug_order = [
                "bias",
                "trend",
                "vwap",
                "compression",
                "event",
                "body_strength",
                "close_position",
                "wick",
                "atr",
                "macd",
                "bollinger",
            ]
            for key in debug_order:
                component = components[key]
                print(
                    component["debug_true"]
                    if component["aligned"]
                    else component["debug_false"]
                )

            elapsed = time.time() - start
            display_score = int(round(score)) if float(score).is_integer() else score

            print(f"\nFinal {direction} Score: {display_score}")
            print(f"Normalized {direction} Strength: {normalized_score:.4f}")
            print(f"Elapsed: {elapsed:.4f}s")

            if score > entry_threshold:
                print(f"High-quality {direction} setup")
            elif score == entry_threshold:
                print(f"Tradable {direction} setup")
            else:
                print(f"Weak {direction} setup")

        return {
            "components": components,
            "score": score,
            "normalized_score": normalized_score,
            "max_score": max_score,
            "entry_threshold": entry_threshold,
        }

    def compute_score(self, row, bias, side="long"):
        details = self.compute_score_details(
            row,
            bias,
            side=side,
            emit_debug=True,
        )
        score = details["score"]
        if float(score).is_integer():
            return int(round(score))
        return score


def compute_score(row, bias, side="long", config=None):
    return ScoreEngine(config=config).compute_score(row, bias, side=side)


def compute_score_components(row, bias, side="long", config=None):
    return ScoreEngine(config=config).compute_score_components(
        row,
        bias,
        side=side,
    )


def compute_normalized_score(components, config=None):
    return ScoreEngine(config=config).compute_normalized_score(components)
