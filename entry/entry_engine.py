"""Converts a scored setup into a Trade object when configured entry rules are satisfied."""

import time

from common.debug import debug_print as print
from config import AppConfig
from simulation.trade import Trade


class EntryEngine:
    """
    Converts score and bias into an executable Trade object.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        self.entry_threshold = self.config.require("entry", "score_threshold")
        getter = getattr(self.config, "get", None)
        if callable(getter):
            self.block_compression = bool(
                getter("entry", "block_compression", default=False)
            )
            blocked_scores = getter("entry", "blocked_scores", default=[])
            min_body_strength_by_score = getter(
                "entry",
                "min_body_strength_by_score",
                default={},
            )
            blocked_upper_wick_ranges_by_score = getter(
                "entry",
                "blocked_upper_wick_ranges_by_score",
                default={},
            )
            blocked_lower_wick_ranges_by_score = getter(
                "entry",
                "blocked_lower_wick_ranges_by_score",
                default={},
            )
            conditional_filters_by_score = getter(
                "entry",
                "conditional_filters_by_score",
                default={},
            )
            block_compression_sides = getter(
                "entry",
                "block_compression_sides",
                default=None,
            )
        else:
            try:
                self.block_compression = bool(
                    self.config.require("entry", "block_compression")
                )
            except Exception:
                self.block_compression = False
            try:
                blocked_scores = self.config.require("entry", "blocked_scores")
            except Exception:
                blocked_scores = []
            try:
                min_body_strength_by_score = self.config.require(
                    "entry",
                    "min_body_strength_by_score",
                )
            except Exception:
                min_body_strength_by_score = {}
            try:
                blocked_upper_wick_ranges_by_score = self.config.require(
                    "entry",
                    "blocked_upper_wick_ranges_by_score",
                )
            except Exception:
                blocked_upper_wick_ranges_by_score = {}
            try:
                blocked_lower_wick_ranges_by_score = self.config.require(
                    "entry",
                    "blocked_lower_wick_ranges_by_score",
                )
            except Exception:
                blocked_lower_wick_ranges_by_score = {}
            try:
                conditional_filters_by_score = self.config.require(
                    "entry",
                    "conditional_filters_by_score",
                )
            except Exception:
                conditional_filters_by_score = {}
            try:
                block_compression_sides = self.config.require(
                    "entry",
                    "block_compression_sides",
                )
            except Exception:
                block_compression_sides = None

        self.blocked_scores = {int(score) for score in blocked_scores}
        self.min_body_strength_by_score = {
            int(score): float(value)
            for score, value in (min_body_strength_by_score or {}).items()
        }
        self.blocked_upper_wick_ranges_by_score = {
            int(score): [
                (
                    float(range_config["min"]),
                    float(range_config["max"]),
                )
                for range_config in (ranges or [])
            ]
            for score, ranges in (
                blocked_upper_wick_ranges_by_score or {}
            ).items()
        }
        self.blocked_lower_wick_ranges_by_score = {
            int(score): [
                (
                    float(range_config["min"]),
                    float(range_config["max"]),
                )
                for range_config in (ranges or [])
            ]
            for score, ranges in (
                blocked_lower_wick_ranges_by_score or {}
            ).items()
        }
        if block_compression_sides is None:
            self.block_compression_sides = {"long"} if self.block_compression else set()
        else:
            self.block_compression_sides = {
                str(side).lower() for side in (block_compression_sides or [])
            }
        self.conditional_filters_by_score = self._parse_conditional_filters(
            conditional_filters_by_score or {}
        )

    @staticmethod
    def _parse_conditional_filters(raw_filters):
        parsed = {}
        for score, side_mapping in raw_filters.items():
            parsed_score = int(score)
            parsed[parsed_score] = {}
            for side, filters in (side_mapping or {}).items():
                parsed[parsed_score][str(side).lower()] = dict(filters or {})
        return parsed

    @staticmethod
    def _metric_debug_label(metric_name):
        return metric_name.replace("_", " ")

    def _passes_conditional_filters(self, row, score, side):
        filters = self.conditional_filters_by_score.get(score, {}).get(side, {})
        if not filters:
            return True

        comparisons = [
            ("min_body_strength", "body_strength", ">="),
            ("max_upper_wick_ratio", "upper_wick_ratio", "<="),
            ("max_lower_wick_ratio", "lower_wick_ratio", "<="),
            ("min_close_position", "close_position", ">="),
            ("max_close_position", "close_position", "<="),
            ("min_abs_vwap_distance_ratio", "vwap_distance_ratio", "abs>="),
            ("min_abs_ema_gap_ratio", "ema_gap_ratio", "abs>="),
            ("min_abs_price_to_fast_ema_ratio", "price_to_fast_ema_ratio", "abs>="),
            ("min_abs_fast_ema_slope_ratio", "fast_ema_slope_ratio", "abs>="),
        ]

        for filter_key, row_key, operator in comparisons:
            if filter_key not in filters:
                continue

            threshold = float(filters[filter_key])
            value = float(row.get(row_key, 0.0))
            passes = False
            if operator == ">=":
                passes = value >= threshold
            elif operator == "<=":
                passes = value <= threshold
            elif operator == "abs>=":
                passes = abs(value) >= threshold

            if not passes:
                print(
                    "No entry: conditional score filter failed for "
                    f"{side} score {score} "
                    f"({self._metric_debug_label(row_key)}={value:.4f}, "
                    f"required {operator} {threshold:.4f})"
                )
                return False

        if filters.get("require_atr_rising") and not bool(row.get("atr_rising", False)):
            print(
                f"No entry: conditional score filter requires ATR expansion for {side} score {score}"
            )
            return False

        if filters.get("require_vwap_alignment"):
            price = float(row.get("close", 0.0))
            vwap = float(row.get("session_vwap", price))
            aligned = price >= vwap if side == "long" else price <= vwap
            if not aligned:
                print(
                    f"No entry: conditional score filter requires VWAP alignment for {side} score {score}"
                )
                return False

        return True

    def generate_entry(self, row, score, bias, side="long"):
        start = time.time()
        side = str(side).lower()

        print("\nRunning entry engine...")

        required_bias = "bullish" if side == "long" else "bearish"
        event_column = "breakout" if side == "long" else "breakdown"

        if bias != required_bias:
            print(f"No entry: bias not {required_bias}")
            return None

        if score < self.entry_threshold:
            print(f"No entry: score too low ({score} < {self.entry_threshold})")
            return None

        if score in self.blocked_scores:
            print(f"No entry: score {score} blocked by configuration")
            return None

        min_body_strength = self.min_body_strength_by_score.get(score)
        if min_body_strength is not None:
            body_strength = float(row.get("body_strength", 0.0))
            if body_strength < min_body_strength:
                print(
                    "No entry: body strength below score-specific minimum "
                    f"({body_strength:.4f} < {min_body_strength:.4f})"
                )
                return None

        wick_ranges_by_score = (
            self.blocked_upper_wick_ranges_by_score
            if side == "long"
            else self.blocked_lower_wick_ranges_by_score
        )
        wick_metric = "upper_wick_ratio" if side == "long" else "lower_wick_ratio"
        blocked_wick_ranges = wick_ranges_by_score.get(score, [])
        if blocked_wick_ranges:
            wick_ratio = float(row.get(wick_metric, 0.0))
            for min_wick, max_wick in blocked_wick_ranges:
                if min_wick <= wick_ratio < max_wick:
                    print(
                        "No entry: wick ratio falls inside blocked score-specific band "
                        f"({wick_metric}={wick_ratio:.4f} in "
                        f"[{min_wick:.4f}, {max_wick:.4f}))"
                    )
                    return None

        if not self._passes_conditional_filters(row, score, side):
            return None

        if not row[event_column]:
            print(f"No entry: {event_column} event not confirmed")
            return None

        if (
            self.block_compression
            and side in self.block_compression_sides
            and bool(row.get("compression", False))
        ):
            print("No entry: compressed setup blocked by configuration")
            return None

        # Optional: allow retest as alternative (if you want later)
        # if not (row["breakout"] or row["retest"]):
        #    return None

        # Create trade
        trade = Trade(row, score, side=side, config=self.config)

        print("\nENTRY SIGNAL GENERATED")
        print(f"  Side: {side.upper()}")
        print(f"  Time: {row.name}")
        print(f"  Price: {row['close']:.2f}")
        print(f"  Score: {score}")
        print(f"  Bias: {bias}")

        elapsed = time.time() - start
        print(f"Elapsed: {elapsed:.4f}s")

        return trade


def generate_entry(row, score, bias, side="long", config=None):
    return EntryEngine(config=config).generate_entry(row, score, bias, side=side)
