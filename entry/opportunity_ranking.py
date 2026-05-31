"""Continuous opportunity scoring helpers for live scanning and paper trading."""

from config import AppConfig


SCORE_BUCKETS = (
    (0.9, "0.9-1.0"),
    (0.8, "0.8-0.9"),
    (0.7, "0.7-0.8"),
    (0.6, "0.6-0.7"),
    (0.0, "<0.6"),
)


def clamp(value, minimum=0.0, maximum=1.0):
    return max(float(minimum), min(float(maximum), float(value)))


def normalize(value, min_value, max_value):
    if max_value <= min_value:
        return 0.0
    return clamp((float(value) - float(min_value)) / (float(max_value) - float(min_value)))


def score_bucket_label(score):
    score = float(score)
    for threshold, label in SCORE_BUCKETS:
        if score >= threshold:
            return label
    return "<0.6"


def bucket_floor(label):
    mapping = {
        "0.9-1.0": 0.9,
        "0.8-0.9": 0.8,
        "0.7-0.8": 0.7,
        "0.6-0.7": 0.6,
        "<0.6": 0.0,
    }
    return float(mapping.get(label, 0.0))


class OpportunityScorer:
    """Small interpretable scorer with slowly adaptive feature weights."""

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        getter = getattr(self.config, "get", None)
        raw = (
            getter("live_sim", "opportunity_scoring", default={})
            if callable(getter)
            else {}
        ) or {}

        raw_weights = raw.get(
            "weights",
            {
                "body_strength": 0.35,
                "close_position": 0.25,
                "vwap_score": 0.25,
                "momentum": 0.15,
            },
        )
        self.weights = {
            "body_strength": float(raw_weights.get("body_strength", 0.35)),
            "close_position": float(raw_weights.get("close_position", 0.25)),
            "vwap_score": float(raw_weights.get("vwap_score", 0.25)),
            "momentum": float(raw_weights.get("momentum", 0.15)),
        }
        self.body_range = tuple(raw.get("body_strength_range", [1.0, 3.0]))
        self.close_range = tuple(raw.get("close_position_range", [0.55, 1.0]))
        self.vwap_bucket_values = dict(
            raw.get(
                "vwap_bucket_values",
                {
                    "near": 0.3,
                    "moderate": 0.6,
                    "far": 1.0,
                },
            )
        )
        self.edge_type_bonus = dict(
            raw.get(
                "edge_type_bonus",
                {
                    "impulse_breakout": 0.08,
                    "breakout_pullback": 0.04,
                    "pressure_breakout": 0.02,
                    "momentum_breakout": 0.03,
                },
            )
        )
        self.top_mover_bonus = float(raw.get("top_mover_bonus", 0.05))
        self.min_weight = float(raw.get("min_weight", 0.10))
        self.max_weight = float(raw.get("max_weight", 0.50))
        self.update_smoothing = float(raw.get("update_smoothing", 0.20))

    def vwap_bucket_score(self, bucket):
        return clamp(self.vwap_bucket_values.get(str(bucket), 0.3))

    def compute_components(
        self,
        *,
        row,
        momentum_rank=0.5,
        vwap_bucket=None,
        edge_type=None,
        is_top_mover=False,
    ):
        body_value = normalize(
            row.get("body_strength", 0.0) or 0.0,
            self.body_range[0],
            self.body_range[1],
        )
        close_value = normalize(
            row.get("close_position", 0.0) or 0.0,
            self.close_range[0],
            self.close_range[1],
        )
        vwap_value = self.vwap_bucket_score(vwap_bucket)
        momentum_value = clamp(momentum_rank)
        edge_bonus = float(self.edge_type_bonus.get(str(edge_type), 0.0))
        mover_bonus = self.top_mover_bonus if is_top_mover else 0.0
        return {
            "body_strength": body_value,
            "close_position": close_value,
            "vwap_score": vwap_value,
            "momentum": momentum_value,
            "edge_type_bonus": edge_bonus,
            "top_mover_bonus": mover_bonus,
        }

    def compute_score(
        self,
        *,
        row,
        momentum_rank=0.5,
        vwap_bucket=None,
        edge_type=None,
        is_top_mover=False,
    ):
        components = self.compute_components(
            row=row,
            momentum_rank=momentum_rank,
            vwap_bucket=vwap_bucket,
            edge_type=edge_type,
            is_top_mover=is_top_mover,
        )
        score = (
            self.weights["body_strength"] * components["body_strength"]
            + self.weights["close_position"] * components["close_position"]
            + self.weights["vwap_score"] * components["vwap_score"]
            + self.weights["momentum"] * components["momentum"]
            + components["edge_type_bonus"]
            + components["top_mover_bonus"]
        )
        score = clamp(score)
        return {
            "score": score,
            "score_bucket": score_bucket_label(score),
            "components": components,
            "weights": dict(self.weights),
        }

    def update_weights(self, feature_stats):
        if not feature_stats:
            return dict(self.weights)

        effectiveness = {}
        for feature in self.weights:
            stats = feature_stats.get(feature, {}) or {}
            pos = float(stats.get("sum_pos", 0.0) or 0.0)
            neg = float(stats.get("sum_neg", 0.0) or 0.0)
            total = pos + neg
            if total <= 0:
                effectiveness[feature] = self.weights[feature]
            else:
                effectiveness[feature] = pos / total

        total_effectiveness = sum(effectiveness.values()) or 1.0
        proposed = {
            feature: clamp(
                effectiveness[feature] / total_effectiveness,
                self.min_weight,
                self.max_weight,
            )
            for feature in self.weights
        }
        total_proposed = sum(proposed.values()) or 1.0
        proposed = {
            feature: proposed[feature] / total_proposed
            for feature in proposed
        }

        for feature in self.weights:
            self.weights[feature] = (
                (1.0 - self.update_smoothing) * self.weights[feature]
                + self.update_smoothing * proposed[feature]
            )

        total_weights = sum(self.weights.values()) or 1.0
        self.weights = {
            feature: clamp(
                self.weights[feature] / total_weights,
                self.min_weight,
                self.max_weight,
            )
            for feature in self.weights
        }
        total_weights = sum(self.weights.values()) or 1.0
        self.weights = {
            feature: self.weights[feature] / total_weights
            for feature in self.weights
        }
        return dict(self.weights)
