"""Legacy gated entry conversion logic extracted from the mixed entry engine."""

import time

from common.debug import debug_print as print
from simulation.trade import Trade


class LegacyEntryEngine:
    """Converts a scored setup into an executable candidate using legacy gates."""

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
        start = time.time()
        side = str(side).lower()

        print("\nRunning legacy entry engine...")

        profile = {
            "timestamp": row.name,
            "side": side,
            "signal_family": "trend",
            "bias": bias,
            "regime_score": regime_score,
            "regime_class": regime_class,
            "raw_score": float(score),
            "entry_role": None,
            "entry_risk_multiplier": 0.0,
            "eligible": False,
            "rejection_reason": None,
            "candidate": None,
        }

        required_bias = "bullish" if side == "long" else "bearish"
        event_column = "breakout" if side == "long" else "breakdown"
        entry_metadata = self.owner.preview_entry_metadata(score, side)
        entry_threshold = entry_metadata["entry_threshold"]
        entry_role = entry_metadata["entry_role"]

        profile["entry_role"] = entry_role
        profile["entry_risk_multiplier"] = float(
            entry_metadata["entry_risk_multiplier"]
        )
        profile["entry_threshold"] = entry_threshold

        if bias != required_bias:
            print(f"No entry: bias not {required_bias}")
            profile["rejection_reason"] = "bias"
            return profile

        if (
            self.owner.allowed_entry_roles is not None
            and entry_role not in self.owner.allowed_entry_roles
        ):
            print(
                f"No entry: role {entry_role} blocked by channel configuration"
            )
            profile["rejection_reason"] = "role_blocked"
            return profile

        if score < entry_threshold:
            print(f"No entry: score too low ({score} < {entry_threshold})")
            profile["rejection_reason"] = "score_threshold"
            return profile

        side_blocked_scores = self.owner.blocked_scores_by_side.get(side, set())
        if score in self.owner.blocked_scores or score in side_blocked_scores:
            print(f"No entry: score {score} blocked by configuration")
            profile["rejection_reason"] = "blocked_score"
            return profile

        min_body_strength = self.owner.min_body_strength_by_score.get(score)
        if min_body_strength is not None:
            body_strength = float(row.get("body_strength", 0.0))
            if body_strength < min_body_strength:
                print(
                    "No entry: body strength below score-specific minimum "
                    f"({body_strength:.4f} < {min_body_strength:.4f})"
                )
                profile["rejection_reason"] = "body_strength"
                return profile

        wick_ranges_by_score = (
            self.owner.blocked_upper_wick_ranges_by_score
            if side == "long"
            else self.owner.blocked_lower_wick_ranges_by_score
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
                    profile["rejection_reason"] = "wick_band"
                    return profile

        filter_context = row.to_dict()
        if regime_score is not None:
            filter_context["regime_score"] = regime_score
        if regime_class is not None:
            filter_context["regime_class"] = regime_class

        directional_filters = self.owner.directional_filters.get(side, {})
        if not self.owner._passes_filter_set(
            filter_context,
            directional_filters,
            score,
            side,
            label="directional",
        ):
            profile["rejection_reason"] = "directional_filter"
            return profile

        score_filters = self.owner.conditional_filters_by_score.get(score, {}).get(
            side,
            {},
        )
        if not self.owner._passes_filter_set(
            filter_context,
            score_filters,
            score,
            side,
            label="conditional score",
        ):
            profile["rejection_reason"] = "conditional_filter"
            return profile

        if not row[event_column]:
            print(f"No entry: {event_column} event not confirmed")
            profile["rejection_reason"] = "event_gate"
            return profile

        if (
            self.owner.block_compression
            and side in self.owner.block_compression_sides
            and bool(row.get("compression", False))
        ):
            print("No entry: compressed setup blocked by configuration")
            profile["rejection_reason"] = "compression"
            return profile

        trade = Trade(row, score, side=side, config=self.owner.config)
        trade.entry_risk_multiplier = entry_metadata["entry_risk_multiplier"]
        trade.entry_role = entry_role
        trade.entry_priority = entry_metadata["entry_priority"]
        if hasattr(trade, "annotate_signal_family"):
            trade.annotate_signal_family("trend")

        print("\nENTRY SIGNAL GENERATED")
        print(f"  Side: {side.upper()}")
        print(f"  Time: {row.name}")
        print(f"  Price: {row['close']:.2f}")
        print(f"  Score: {score}")
        print(f"  Bias: {bias}")
        print(f"  Role: {trade.entry_role.upper()}")
        print(f"  Risk multiplier: {trade.entry_risk_multiplier:.2f}x")
        print(f"Elapsed: {time.time() - start:.4f}s")

        candidate = {
            "side": side,
            "score": float(score),
            "selection_value": float(score),
            "trade": trade,
            "trade_regime": regime_score,
            "regime_class": regime_class,
            "entry_threshold": entry_threshold,
            "entry_risk_multiplier": float(trade.entry_risk_multiplier),
            "entry_role": str(trade.entry_role).lower(),
            "entry_priority": int(trade.entry_priority),
            "signal_family": "trend",
        }
        profile["eligible"] = True
        profile["candidate"] = candidate
        return profile

    def generate_entry(
        self,
        row,
        score,
        bias,
        side="long",
        regime_score=None,
        regime_class=None,
    ):
        profile = self.build_candidate(
            row,
            score,
            bias,
            side=side,
            regime_score=regime_score,
            regime_class=regime_class,
        )
        candidate = profile.get("candidate")
        if candidate is None:
            return None
        return candidate["trade"]
