"""Weighted opportunity logic extracted from the mixed entry engine."""

from simulation.trade import Trade


class WeightedOpportunityEngine:
    """Builds continuous weighted candidates instead of pass/fail entries."""

    def __init__(self, owner):
        self.owner = owner

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
        side = str(side).lower()
        score_components = None
        score_max = float(self.owner.max_score)
        if isinstance(score_details, dict):
            score_norm = float(
                score_details.get(
                    "normalized_score",
                    self.owner._clip(float(score) / self.owner.max_score),
                )
            )
            score_components = score_details.get("components")
            score_max = float(score_details.get("max_score", score_max) or score_max)
        else:
            score_norm = self.owner._clip(float(score) / self.owner.max_score)
        momentum_strength, momentum_components = self.owner._momentum_strength(
            row,
            side,
        )
        signal_strength = (
            (self.owner.weighted_score_weight * score_norm) +
            (self.owner.weighted_momentum_weight * momentum_strength)
        )
        bias_weight = self.owner._bias_weight_for_side(bias, side)
        regime_weight = self.owner._regime_weight_for_side(regime_class, side)
        event_bonus = self.owner._event_bonus_for_side(row, side)
        final_strength = signal_strength * bias_weight * regime_weight * event_bonus
        final_strength = min(
            final_strength,
            self.owner.weighted_max_strength_multiplier,
        )
        bucket_profile = self.owner.edge_selector.evaluate(
            row,
            bias=bias,
            side=side,
        )

        structural_floor_passed = self.owner._passes_weighted_structural_floor(
            row,
            side,
        )
        rejection_reason = None
        if not structural_floor_passed:
            rejection_reason = "structural_floor"
        elif (
            bucket_profile.get("edge_selector_enabled")
            and bucket_profile.get("edge_selector_active")
            and not bucket_profile.get("bucket_valid")
        ):
            rejection_reason = bucket_profile.get("bucket_reason") or "edge_bucket"
        elif final_strength < self.owner.weighted_noise_guard_min_strength:
            rejection_reason = "noise_guard"

        eligible = rejection_reason is None
        entry_risk_multiplier = 0.0
        trade = None
        candidate = None

        if eligible:
            bucket_risk_mult = float(
                bucket_profile.get("bucket_risk_mult", 1.0) or 1.0
            )
            if (
                bucket_profile.get("edge_selector_enabled")
                and bucket_profile.get("edge_selector_active")
                and bucket_profile.get("bucket_valid")
                and getattr(self.owner, "edge_selection_risk_mode", "blend") == "bucket_only"
            ):
                entry_risk_multiplier = max(
                    self.owner.weighted_min_entry_risk_multiplier,
                    min(
                        bucket_risk_mult,
                        self.owner.weighted_max_strength_multiplier,
                    ),
                )
            else:
                entry_risk_multiplier = max(
                    self.owner.weighted_min_entry_risk_multiplier,
                    min(
                        final_strength * bucket_risk_mult,
                        self.owner.weighted_max_strength_multiplier,
                    ),
                )
            trade = Trade(row, score, side=side, config=self.owner.config)
            trade.entry_risk_multiplier = entry_risk_multiplier
            trade.entry_role = "core"
            trade.entry_priority = 1
            if hasattr(trade, "annotate_signal_family"):
                trade.annotate_signal_family("trend")
            if hasattr(trade, "annotate_weighted_context"):
                trade.annotate_weighted_context(
                    score_norm=score_norm,
                    momentum_strength=momentum_strength,
                    final_strength=final_strength,
                    bias_weight=bias_weight,
                    regime_weight=regime_weight,
                    event_bonus=event_bonus,
                )
            if hasattr(trade, "annotate_edge_bucket"):
                trade.annotate_edge_bucket(
                    edge_type=bucket_profile.get("edge_type"),
                    body_bucket=bucket_profile.get("body_bucket"),
                    vwap_bucket=bucket_profile.get("vwap_bucket"),
                    bucket_key=bucket_profile.get("bucket_key_text"),
                    bucket_expected_return=bucket_profile.get("bucket_expected_return"),
                    bucket_risk_mult=bucket_profile.get("bucket_risk_mult"),
                )

            selection_value = float(final_strength)
            if (
                bucket_profile.get("edge_selector_enabled")
                and bucket_profile.get("edge_selector_active")
                and bucket_profile.get("bucket_expected_return") is not None
            ):
                selection_value = float(
                    bucket_profile["bucket_expected_return"]
                    * bucket_profile.get("bucket_risk_mult", 1.0)
                )
            candidate = {
                "side": side,
                "score": float(score),
                "selection_value": selection_value,
                "trade": trade,
                "trade_regime": regime_score,
                "regime_class": regime_class,
                "entry_threshold": self.owner.weighted_noise_guard_min_strength,
                "entry_risk_multiplier": entry_risk_multiplier,
                "entry_role": "core",
                "entry_priority": 1,
                "signal_family": "trend",
                "edge_type": bucket_profile.get("edge_type"),
                "body_bucket": bucket_profile.get("body_bucket"),
                "vwap_bucket": bucket_profile.get("vwap_bucket"),
                "bucket_key_text": bucket_profile.get("bucket_key_text"),
                "bucket_expected_return": bucket_profile.get("bucket_expected_return"),
                "bucket_risk_mult": bucket_profile.get("bucket_risk_mult"),
            }

        return {
            "timestamp": row.name,
            "side": side,
            "signal_family": "trend",
            "bias": bias,
            "regime_score": regime_score,
            "regime_class": regime_class,
            "raw_score": float(score),
            "score_norm": score_norm,
            "score_max": score_max,
            "score_components": score_components,
            "momentum_strength": momentum_strength,
            "signal_strength": signal_strength,
            "bias_weight": bias_weight,
            "regime_weight": regime_weight,
            "event_bonus": event_bonus,
            "final_strength": final_strength,
            "entry_risk_multiplier": entry_risk_multiplier,
            "entry_role": "core",
            "eligible": eligible,
            "rejection_reason": rejection_reason,
            "structural_floor_passed": structural_floor_passed,
            "breakout_event": bool(
                row.get("breakout" if side == "long" else "breakdown", False)
            ),
            "price_to_fast_ema_ratio": float(
                row.get("price_to_fast_ema_ratio", 0.0) or 0.0
            ),
            "ema_gap_ratio": float(row.get("ema_gap_ratio", 0.0) or 0.0),
            "vwap_distance_ratio": float(
                row.get("vwap_distance_ratio", 0.0) or 0.0
            ),
            "atr_rising": bool(row.get("atr_rising", False)),
            "macd_hist": float(row.get("macd_hist", 0.0) or 0.0),
            "momentum_components": momentum_components,
            "edge_type": bucket_profile.get("edge_type"),
            "body_bucket": bucket_profile.get("body_bucket"),
            "vwap_bucket": bucket_profile.get("vwap_bucket"),
            "bucket_key": bucket_profile.get("bucket_key_text"),
            "bucket_valid": bucket_profile.get("bucket_valid"),
            "bucket_expected_return": bucket_profile.get("bucket_expected_return"),
            "bucket_risk_mult": bucket_profile.get("bucket_risk_mult"),
            "bucket_signal_count": bucket_profile.get("bucket_signal_count"),
            "bucket_selected_horizon": bucket_profile.get("bucket_selected_horizon"),
            "candidate": candidate,
        }
