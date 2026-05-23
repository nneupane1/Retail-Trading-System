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
            score_threshold_by_side = getter(
                "entry",
                "score_threshold_by_side",
                default={},
            )
            self.block_compression = bool(
                getter("entry", "block_compression", default=False)
            )
            blocked_scores = getter("entry", "blocked_scores", default=[])
            blocked_scores_by_side = getter(
                "entry",
                "blocked_scores_by_side",
                default={},
            )
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
            directional_filters = getter(
                "entry",
                "directional_filters",
                default={},
            )
            risk_multipliers_by_score = getter(
                "entry",
                "risk_multipliers_by_score",
                default={},
            )
            allowed_entry_roles = getter(
                "entry",
                "allowed_entry_roles",
                default=None,
            )
            block_compression_sides = getter(
                "entry",
                "block_compression_sides",
                default=None,
            )
        else:
            try:
                score_threshold_by_side = self.config.require(
                    "entry",
                    "score_threshold_by_side",
                )
            except Exception:
                score_threshold_by_side = {}
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
                blocked_scores_by_side = self.config.require(
                    "entry",
                    "blocked_scores_by_side",
                )
            except Exception:
                blocked_scores_by_side = {}
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
                directional_filters = self.config.require(
                    "entry",
                    "directional_filters",
                )
            except Exception:
                directional_filters = {}
            try:
                risk_multipliers_by_score = self.config.require(
                    "entry",
                    "risk_multipliers_by_score",
                )
            except Exception:
                risk_multipliers_by_score = {}
            try:
                allowed_entry_roles = self.config.require(
                    "entry",
                    "allowed_entry_roles",
                )
            except Exception:
                allowed_entry_roles = None
            try:
                block_compression_sides = self.config.require(
                    "entry",
                    "block_compression_sides",
                )
            except Exception:
                block_compression_sides = None

        self.score_threshold_by_side = {
            str(side).lower(): int(value)
            for side, value in (score_threshold_by_side or {}).items()
        }
        self.blocked_scores = {int(score) for score in blocked_scores}
        self.blocked_scores_by_side = {
            str(side).lower(): {int(score) for score in (scores or [])}
            for side, scores in (blocked_scores_by_side or {}).items()
        }
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
        self.directional_filters = {
            str(side).lower(): dict(filters or {})
            for side, filters in (directional_filters or {}).items()
        }
        self.risk_multipliers_by_score = self._parse_risk_multipliers(
            risk_multipliers_by_score or {}
        )
        self.allowed_entry_roles = (
            {str(role).lower() for role in (allowed_entry_roles or [])}
            if allowed_entry_roles is not None
            else None
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
    def _parse_risk_multipliers(raw_multipliers):
        parsed = {}
        for score, value in (raw_multipliers or {}).items():
            parsed_score = int(score)
            if isinstance(value, dict):
                parsed[parsed_score] = {
                    str(side).lower(): float(multiplier)
                    for side, multiplier in value.items()
                }
            else:
                parsed[parsed_score] = float(value)
        return parsed

    @staticmethod
    def _metric_debug_label(metric_name):
        return metric_name.replace("_", " ")

    def _resolve_entry_risk_multiplier(self, score, side):
        configured = self.risk_multipliers_by_score.get(int(score))
        if configured is None:
            return 1.0
        if isinstance(configured, dict):
            return float(configured.get(side, 1.0))
        return float(configured)

    def entry_threshold_for_side(self, side):
        side = str(side).lower()
        return self.score_threshold_by_side.get(side, self.entry_threshold)

    def preview_entry_metadata(self, score, side):
        side = str(side).lower()
        entry_risk_multiplier = self._resolve_entry_risk_multiplier(score, side)
        entry_role = "support" if entry_risk_multiplier < 1.0 else "core"
        entry_priority = 0 if entry_role == "support" else 1
        return {
            "entry_threshold": self.entry_threshold_for_side(side),
            "entry_risk_multiplier": entry_risk_multiplier,
            "entry_role": entry_role,
            "entry_priority": entry_priority,
        }

    def _passes_filter_set(self, row, filters, score, side, label):
        if not filters:
            return True

        allowed_regime_classes = {
            str(value).lower()
            for value in (filters.get("allowed_regime_classes", []) or [])
        }
        if allowed_regime_classes:
            regime_class = str(row.get("regime_class", "") or "").lower()
            if regime_class not in allowed_regime_classes:
                print(
                    f"No entry: {label} filter failed for {side} score {score} "
                    f"(regime class={regime_class or 'unknown'}, "
                    f"allowed={sorted(allowed_regime_classes)})"
                )
                return False

        blocked_regime_classes = {
            str(value).lower()
            for value in (filters.get("blocked_regime_classes", []) or [])
        }
        if blocked_regime_classes:
            regime_class = str(row.get("regime_class", "") or "").lower()
            if regime_class in blocked_regime_classes:
                print(
                    f"No entry: {label} filter failed for {side} score {score} "
                    f"(regime class={regime_class}, blocked by configuration)"
                )
                return False

        comparisons = [
            ("min_body_strength", "body_strength", ">="),
            ("max_body_strength", "body_strength", "<="),
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
                    f"No entry: {label} filter failed for "
                    f"{side} score {score} "
                    f"({self._metric_debug_label(row_key)}={value:.4f}, "
                    f"required {operator} {threshold:.4f})"
                )
                return False

        for row_key, threshold in (filters.get("min_metric_values", {}) or {}).items():
            value = float(row.get(row_key, 0.0))
            threshold = float(threshold)
            if value < threshold:
                print(
                    f"No entry: {label} filter failed for {side} score {score} "
                    f"({self._metric_debug_label(row_key)}={value:.4f}, required >= {threshold:.4f})"
                )
                return False

        for row_key, threshold in (filters.get("max_metric_values", {}) or {}).items():
            value = float(row.get(row_key, 0.0))
            threshold = float(threshold)
            if value > threshold:
                print(
                    f"No entry: {label} filter failed for {side} score {score} "
                    f"({self._metric_debug_label(row_key)}={value:.4f}, required <= {threshold:.4f})"
                )
                return False

        if filters.get("require_atr_rising") and not bool(row.get("atr_rising", False)):
            print(
                f"No entry: {label} filter requires ATR expansion for {side} score {score}"
            )
            return False

        if filters.get("require_vwap_alignment"):
            price = float(row.get("close", 0.0))
            vwap = float(row.get("session_vwap", price))
            aligned = price >= vwap if side == "long" else price <= vwap
            if not aligned:
                print(
                    f"No entry: {label} filter requires VWAP alignment for {side} score {score}"
                )
                return False

        return True

    def generate_entry(
        self,
        row,
        score,
        bias,
        side="long",
        regime_score=None,
        regime_class=None,
    ):
        start = time.time()
        side = str(side).lower()

        print("\nRunning entry engine...")

        required_bias = "bullish" if side == "long" else "bearish"
        event_column = "breakout" if side == "long" else "breakdown"
        entry_metadata = self.preview_entry_metadata(score, side)
        entry_threshold = entry_metadata["entry_threshold"]
        entry_role = entry_metadata["entry_role"]

        if bias != required_bias:
            print(f"No entry: bias not {required_bias}")
            return None

        if self.allowed_entry_roles is not None and entry_role not in self.allowed_entry_roles:
            print(
                f"No entry: role {entry_role} blocked by channel configuration"
            )
            return None

        if score < entry_threshold:
            print(f"No entry: score too low ({score} < {entry_threshold})")
            return None

        side_blocked_scores = self.blocked_scores_by_side.get(side, set())
        if score in self.blocked_scores or score in side_blocked_scores:
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

        filter_context = row.to_dict()
        if regime_score is not None:
            filter_context["regime_score"] = regime_score
        if regime_class is not None:
            filter_context["regime_class"] = regime_class

        directional_filters = self.directional_filters.get(side, {})
        if not self._passes_filter_set(
            filter_context,
            directional_filters,
            score,
            side,
            label="directional",
        ):
            return None

        score_filters = self.conditional_filters_by_score.get(score, {}).get(side, {})
        if not self._passes_filter_set(
            filter_context,
            score_filters,
            score,
            side,
            label="conditional score",
        ):
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
        trade.entry_risk_multiplier = entry_metadata["entry_risk_multiplier"]
        trade.entry_role = entry_role
        trade.entry_priority = entry_metadata["entry_priority"]

        print("\nENTRY SIGNAL GENERATED")
        print(f"  Side: {side.upper()}")
        print(f"  Time: {row.name}")
        print(f"  Price: {row['close']:.2f}")
        print(f"  Score: {score}")
        print(f"  Bias: {bias}")
        print(f"  Role: {trade.entry_role.upper()}")
        print(f"  Risk multiplier: {trade.entry_risk_multiplier:.2f}x")

        elapsed = time.time() - start
        print(f"Elapsed: {elapsed:.4f}s")

        return trade


def generate_entry(row, score, bias, side="long", config=None):
    return EntryEngine(config=config).generate_entry(row, score, bias, side=side)
