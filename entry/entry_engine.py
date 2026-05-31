"""Facade that routes entry conversion to legacy or weighted execution logic."""

from common.debug import debug_print as print
from config import AppConfig
from entry.legacy_entry_engine import LegacyEntryEngine
from entry.weighted_opportunity_engine import WeightedOpportunityEngine


class EntryEngine:
    """
    Thin compatibility facade for the active entry execution model.
    """

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        self.entry_threshold = self.config.require("entry", "score_threshold")
        self.fast_ema_period = self.config.require("features", "ema_periods", "fast")
        self.slow_ema_period = self.config.require("features", "ema_periods", "slow")
        self.fast_ema_column = f"ema{self.fast_ema_period}"
        self.slow_ema_column = f"ema{self.slow_ema_period}"
        self.scoring_config = self.config.require("strategy", "scoring")
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
            execution_config = getter(
                "strategy",
                "execution",
                default={},
            ) or {}
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
            try:
                execution_config = self.config.require(
                    "strategy",
                    "execution",
                )
            except Exception:
                execution_config = {}

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
        self.execution_mode = str(
            (execution_config or {}).get("mode", "legacy")
        ).lower()
        weighted_config = (execution_config or {}).get("weighted", {}) or {}
        self.weighted_score_weight = float(weighted_config.get("score_weight", 0.7))
        self.weighted_momentum_weight = float(weighted_config.get("momentum_weight", 0.3))
        self.weighted_noise_guard_min_strength = float(
            weighted_config.get("noise_guard_min_strength", 0.25)
        )
        self.weighted_max_strength_multiplier = float(
            weighted_config.get("max_strength_multiplier", 1.75)
        )
        self.weighted_min_entry_risk_multiplier = float(
            weighted_config.get(
                "min_entry_risk_multiplier",
                self.weighted_noise_guard_min_strength,
            )
        )
        self.weighted_event_bonus = float(weighted_config.get("event_bonus", 1.15))
        self.weighted_non_event_bonus = float(weighted_config.get("non_event_bonus", 1.0))
        self.weighted_structural_floor_enabled = bool(
            weighted_config.get("structural_floor_enabled", True)
        )
        self.weighted_structural_floor_anchor_column = str(
            weighted_config.get(
                "structural_floor_anchor_column",
                self.slow_ema_column,
            )
        )
        self.weighted_bias_weights = {
            "bullish": 1.15,
            "neutral": 0.95,
            "bearish": 0.70,
        }
        self.weighted_bias_weights.update(
            {
                str(label).lower(): float(value)
                for label, value in (
                    weighted_config.get("bias_weights", {}) or {}
                ).items()
            }
        )
        self.weighted_bias_weights_by_side = {
            str(side).lower(): {
                str(label).lower(): float(value)
                for label, value in (mapping or {}).items()
            }
            for side, mapping in (
                weighted_config.get("bias_weights_by_side", {}) or {}
            ).items()
        }
        self.weighted_regime_weights = {
            "weak": 0.65,
            "moderate": 1.0,
            "strong": 1.25,
        }
        self.weighted_regime_weights.update(
            {
                str(label).lower(): float(value)
                for label, value in (
                    weighted_config.get("regime_weights", {}) or {}
                ).items()
            }
        )
        self.weighted_regime_weights_by_side = {
            str(side).lower(): {
                str(label).lower(): float(value)
                for label, value in (mapping or {}).items()
            }
            for side, mapping in (
                weighted_config.get("regime_weights_by_side", {}) or {}
            ).items()
        }
        self.weighted_momentum_component_weights = {
            "price_to_fast_ema": 0.35,
            "ema_gap": 0.25,
            "vwap_distance": 0.20,
            "macd_hist": 0.10,
            "atr_rising": 0.10,
        }
        self.weighted_momentum_component_weights.update(
            {
                str(label): float(value)
                for label, value in (
                    weighted_config.get("momentum_component_weights", {}) or {}
                ).items()
            }
        )
        self.weighted_momentum_scales = {
            "price_to_fast_ema_ratio": 0.006,
            "ema_gap_ratio": 0.004,
            "vwap_distance_ratio": 0.004,
            "macd_hist_atr_ratio": 0.25,
        }
        self.weighted_momentum_scales.update(
            {
                str(label): float(value)
                for label, value in (
                    weighted_config.get("momentum_scales", {}) or {}
                ).items()
            }
        )
        self.max_score = self._compute_max_score()
        self.legacy_engine = LegacyEntryEngine(self)
        self.weighted_engine = WeightedOpportunityEngine(self)

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

    def _compute_max_score(self):
        weight_keys = [
            "bias_weight",
            "trend_weight",
            "compression_weight",
            "breakout_weight",
            "body_strength_weight",
            "close_position_weight",
            "upper_wick_weight",
            "vwap_weight",
            "atr_weight",
            "macd_weight",
            "bollinger_weight",
        ]
        score = sum(float(self.scoring_config.get(key, 0)) for key in weight_keys)
        lower_wick_weight = self.scoring_config.get("lower_wick_weight")
        if lower_wick_weight is not None:
            score = score - float(self.scoring_config.get("upper_wick_weight", 0)) + float(lower_wick_weight)
        return max(float(score), 1.0)

    @staticmethod
    def _clip(value, lower=0.0, upper=1.0):
        return max(lower, min(float(value), upper))

    def is_weighted_mode(self):
        return self.execution_mode == "weighted"

    @staticmethod
    def _aligned_value(value, side):
        value = float(value)
        return value if side == "long" else -value

    def _bias_weight_for_side(self, bias, side):
        side = str(side).lower()
        side_overrides = self.weighted_bias_weights_by_side.get(side)
        if side_overrides:
            mapping = dict(self.weighted_bias_weights)
            mapping.update(side_overrides)
            return float(mapping.get(str(bias).lower(), 1.0))

        if side == "short":
            inverted = {
                "bullish": self.weighted_bias_weights.get("bearish", 0.70),
                "neutral": self.weighted_bias_weights.get("neutral", 0.95),
                "bearish": self.weighted_bias_weights.get("bullish", 1.15),
            }
            return float(inverted.get(str(bias).lower(), 1.0))

        return float(self.weighted_bias_weights.get(str(bias).lower(), 1.0))

    def _regime_weight_for_side(self, regime_class, side):
        side = str(side).lower()
        label = str(regime_class or "weak").lower()
        side_overrides = self.weighted_regime_weights_by_side.get(side, {})
        if label in side_overrides:
            return float(side_overrides[label])
        return float(self.weighted_regime_weights.get(label, 1.0))

    def _event_bonus_for_side(self, row, side):
        event_column = "breakout" if side == "long" else "breakdown"
        return self.weighted_event_bonus if bool(row.get(event_column, False)) else self.weighted_non_event_bonus

    def _passes_weighted_structural_floor(self, row, side):
        if not self.weighted_structural_floor_enabled:
            return True

        anchor_price = float(row.get(self.weighted_structural_floor_anchor_column, row.get("close", 0.0)))
        close_price = float(row.get("close", 0.0))
        if side == "short":
            return close_price < anchor_price
        return close_price > anchor_price

    def _momentum_strength(self, row, side):
        side = str(side).lower()

        aligned_price_to_fast = self._aligned_value(
            row.get("price_to_fast_ema_ratio", 0.0),
            side,
        )
        aligned_ema_gap = self._aligned_value(
            row.get("ema_gap_ratio", 0.0),
            side,
        )
        aligned_vwap_distance = self._aligned_value(
            row.get("vwap_distance_ratio", 0.0),
            side,
        )
        atr_value = abs(float(row.get("atr", 0.0) or 0.0))
        macd_hist = float(row.get("macd_hist", 0.0) or 0.0)
        aligned_macd = self._aligned_value(
            macd_hist / (atr_value + 1e-9),
            side,
        )

        components = {
            "price_to_fast_ema": self._clip(
                aligned_price_to_fast /
                self.weighted_momentum_scales["price_to_fast_ema_ratio"]
            ),
            "ema_gap": self._clip(
                aligned_ema_gap /
                self.weighted_momentum_scales["ema_gap_ratio"]
            ),
            "vwap_distance": self._clip(
                aligned_vwap_distance /
                self.weighted_momentum_scales["vwap_distance_ratio"]
            ),
            "macd_hist": self._clip(
                aligned_macd /
                self.weighted_momentum_scales["macd_hist_atr_ratio"]
            ),
            "atr_rising": 1.0 if bool(row.get("atr_rising", False)) else 0.0,
        }

        weighted_total = 0.0
        weight_sum = 0.0
        for label, value in components.items():
            component_weight = float(
                self.weighted_momentum_component_weights.get(label, 0.0)
            )
            if component_weight <= 0:
                continue
            weighted_total += component_weight * value
            weight_sum += component_weight

        if weight_sum <= 0:
            return 0.0, components

        return weighted_total / weight_sum, components

    def evaluate_weighted_opportunity(
        self,
        row,
        score,
        bias,
        side="long",
        regime_score=None,
        regime_class=None,
        score_details=None,
    ):
        return self.weighted_engine.build_candidate(
            row,
            score,
            bias,
            side=side,
            regime_score=regime_score,
            regime_class=regime_class,
            score_details=score_details,
        )

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
        score_details=None,
    ):
        profile = self.build_candidate(
            row,
            score,
            bias,
            side=side,
            regime_score=regime_score,
            regime_class=regime_class,
            score_details=score_details,
        )
        candidate = profile.get("candidate")
        if candidate is None:
            reason = profile.get("rejection_reason")
            if self.is_weighted_mode():
                print(
                    "No entry: weighted model rejected candidate "
                    f"({reason or 'weighted_rejection'})"
                )
            return None
        return candidate["trade"]

    def build_candidate(
        self,
        row,
        score,
        bias,
        side="long",
        regime_score=None,
        regime_class=None,
        score_details=None,
    ):
        if self.is_weighted_mode():
            return self.weighted_engine.build_candidate(
                row,
                score,
                bias,
                side=side,
                regime_score=regime_score,
                regime_class=regime_class,
                score_details=score_details,
            )
        return self.legacy_engine.build_candidate(
            row,
            score,
            bias,
            side=side,
            regime_score=regime_score,
            regime_class=regime_class,
            score_details=score_details,
        )


def generate_entry(row, score, bias, side="long", config=None):
    return EntryEngine(config=config).generate_entry(row, score, bias, side=side)
