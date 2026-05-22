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

    def generate_entry(self, row, score, bias):
        start = time.time()

        print("\nRunning entry engine...")

        # Only trade in bullish direction (for now)
        if bias != "bullish":
            print("No entry: bias not bullish")
            return None

        # Score check
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

        blocked_upper_wick_ranges = self.blocked_upper_wick_ranges_by_score.get(
            score,
            [],
        )
        if blocked_upper_wick_ranges:
            upper_wick_ratio = float(row.get("upper_wick_ratio", 0.0))
            for min_upper_wick, max_upper_wick in blocked_upper_wick_ranges:
                if min_upper_wick <= upper_wick_ratio < max_upper_wick:
                    print(
                        "No entry: upper wick ratio falls inside blocked "
                        "score-specific band "
                        f"({upper_wick_ratio:.4f} in "
                        f"[{min_upper_wick:.4f}, {max_upper_wick:.4f}))"
                    )
                    return None

        # Breakout event must be present (core rule)
        if not row["breakout"]:
            print("No entry: breakout event not confirmed")
            return None

        if self.block_compression and bool(row.get("compression", False)):
            print("No entry: compressed setup blocked by configuration")
            return None

        # Optional: allow retest as alternative (if you want later)
        # if not (row["breakout"] or row["retest"]):
        #    return None

        # Create trade
        trade = Trade(row, score, config=self.config)

        print("\nENTRY SIGNAL GENERATED")
        print(f"  Time: {row.name}")
        print(f"  Price: {row['close']:.2f}")
        print(f"  Score: {score}")
        print(f"  Bias: {bias}")

        elapsed = time.time() - start
        print(f"Elapsed: {elapsed:.4f}s")

        return trade


def generate_entry(row, score, bias, config=None):
    return EntryEngine(config=config).generate_entry(row, score, bias)
