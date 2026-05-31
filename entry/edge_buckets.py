"""Shared bucket helpers for lean edge selection and calibration."""

from common.debug import debug_print as print


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def classify_bias_bucket(bias):
    label = str(bias or "neutral").strip().lower()
    if label not in {"bullish", "bearish", "neutral"}:
        return "neutral"
    return label


def classify_body_bucket(row, config=None):
    configured = None
    getter = getattr(config, "get", None)
    if callable(getter):
        configured = getter(
            "strategy",
            "edge_selection",
            "strong_body_threshold",
            default=None,
        )
        if configured is None:
            configured = getter(
                "strategy",
                "scoring",
                "body_strength_min",
                default=1.3,
            )
    threshold = _safe_float(configured, default=1.3)
    return "strong" if _safe_float(row.get("body_strength"), default=0.0) >= threshold else "weak"


def classify_vwap_bucket(row, config=None):
    configured = None
    getter = getattr(config, "get", None)
    if callable(getter):
        configured = getter(
            "strategy",
            "edge_selection",
            "vwap_far_threshold",
            default=None,
        )
        if configured is None:
            configured = getter(
                "features",
                "pressure",
                "mean_reversion_vwap_distance_threshold",
                default=0.01,
            )
    threshold = abs(_safe_float(configured, default=0.01))
    distance = abs(_safe_float(row.get("vwap_distance_ratio"), default=0.0))
    return "far" if distance >= threshold else "near"


def infer_edge_type(row, side, config=None):
    side = str(side or "long").lower()
    close_position = _safe_float(row.get("close_position"), default=0.5)
    body_strength = _safe_float(row.get("body_strength"), default=0.0)
    vwap_distance = _safe_float(row.get("vwap_distance_ratio"), default=0.0)
    upper_wick_ratio = _safe_float(row.get("upper_wick_ratio"), default=0.0)
    lower_wick_ratio = _safe_float(row.get("lower_wick_ratio"), default=0.0)

    getter = getattr(config, "get", None)
    body_threshold = 1.3
    close_min = 0.6
    close_max = 0.4
    wick_threshold = 1.2
    vwap_threshold = 0.01
    if callable(getter):
        body_threshold = _safe_float(
            getter("strategy", "scoring", "body_strength_min", default=1.3),
            default=1.3,
        )
        close_min = _safe_float(
            getter("strategy", "scoring", "close_position_min", default=0.6),
            default=0.6,
        )
        close_max = _safe_float(
            getter("strategy", "scoring", "close_position_max", default=0.4),
            default=0.4,
        )
        wick_threshold = _safe_float(
            getter(
                "features",
                "pressure",
                "mean_reversion_wick_threshold",
                default=1.2,
            ),
            default=1.2,
        )
        vwap_threshold = abs(
            _safe_float(
                getter(
                    "features",
                    "pressure",
                    "mean_reversion_vwap_distance_threshold",
                    default=0.01,
                ),
                default=0.01,
            )
        )

    if side == "long":
        if bool(row.get("compression")) and bool(row.get("breakout")):
            return "compression_long"
        if (
            bool(row.get("breakout"))
            and body_strength >= body_threshold
            and close_position >= close_min
        ):
            return "momentum_long"
        if (
            vwap_distance <= -vwap_threshold
            and lower_wick_ratio >= wick_threshold
            and close_position >= 0.45
        ):
            return "mean_reversion_long"
    else:
        if bool(row.get("compression")) and bool(row.get("breakdown")):
            return "compression_short"
        if (
            bool(row.get("breakdown"))
            and body_strength >= body_threshold
            and close_position <= close_max
        ):
            return "momentum_short"
        if (
            vwap_distance >= vwap_threshold
            and upper_wick_ratio >= wick_threshold
            and close_position <= 0.55
        ):
            return "mean_reversion_short"

    return None


def build_bucket_key(*, edge_type, bias_bucket, body_bucket, vwap_bucket):
    return (
        str(edge_type or "unknown"),
        str(bias_bucket or "neutral"),
        str(body_bucket or "weak"),
        str(vwap_bucket or "near"),
    )


def bucket_key_to_text(bucket_key):
    return "|".join(str(part) for part in bucket_key)


def build_signal_bucket(row, *, bias, side, config=None):
    edge_type = infer_edge_type(row, side, config=config)
    if edge_type is None:
        return None

    bias_bucket = classify_bias_bucket(bias)
    body_bucket = classify_body_bucket(row, config=config)
    vwap_bucket = classify_vwap_bucket(row, config=config)
    bucket_key = build_bucket_key(
        edge_type=edge_type,
        bias_bucket=bias_bucket,
        body_bucket=body_bucket,
        vwap_bucket=vwap_bucket,
    )
    return {
        "edge_type": edge_type,
        "bias_bucket": bias_bucket,
        "body_bucket": body_bucket,
        "vwap_bucket": vwap_bucket,
        "bucket_key": bucket_key,
        "bucket_key_text": bucket_key_to_text(bucket_key),
    }
