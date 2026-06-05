"""Dormant 1H execution-layer scaffolding for future cross-timeframe promotion."""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import AppConfig
from entry.opportunity_ranking import clamp, score_bucket_label


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return float(default)
        numeric = float(value)
    except (TypeError, ValueError):
        return float(default)
    if np.isnan(numeric):
        return float(default)
    return numeric


def _bool_value(value):
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return False
    return bool(value)


def _symbol_filter_set(values):
    return {str(value).upper() for value in (values or []) if str(value).strip()}


def _symbol_is_allowed(symbol: str, raw: dict) -> bool:
    symbol_key = str(symbol).upper()
    blocked = _symbol_filter_set(raw.get("blocked_symbols"))
    if symbol_key in blocked:
        return False
    allowed = _symbol_filter_set(raw.get("allowed_symbols"))
    if allowed and symbol_key not in allowed:
        return False
    return True


def _side_is_allowed(side: str, raw: dict) -> bool:
    allowed = {str(value).lower() for value in (raw.get("allowed_sides") or []) if str(value).strip()}
    if not allowed:
        return True
    return str(side).lower() in allowed


def _normalize_context_label(value) -> str:
    label = str(value or "neutral").strip().lower()
    if label not in {"bullish", "bearish", "neutral"}:
        return "neutral"
    return label


def _empty_h1_frame(execution_index):
    frame = pd.DataFrame(index=pd.Index(execution_index))
    frame["h1_new_candle"] = False
    frame["signal_event_long"] = False
    frame["signal_event_short"] = False
    frame["signal_family_long"] = ""
    frame["signal_family_short"] = ""
    return frame


def build_h1_execution_snapshots(
    execution_index,
    df_1h,
    df_6h=None,
    df_12h=None,
    *,
    config=None,
):
    """Builds aligned dormant 1H execution snapshots without wiring them live."""

    config = config or AppConfig.load()
    getter = getattr(config, "get", None)
    raw = getter("strategy", "h1_execution", default={}) if callable(getter) else {}
    raw = raw or {}
    if not bool(raw.get("enabled", False)):
        return _empty_h1_frame(execution_index)

    breakout_lookback = int(raw.get("breakout_lookback", 12))
    body_strength_min = _safe_float(raw.get("body_strength_min", 1.4), default=1.4)
    close_position_min = _safe_float(raw.get("close_position_min", 0.72), default=0.72)
    expansion_min = _safe_float(raw.get("expansion_min", 1.08), default=1.08)
    max_abs_vwap_distance = _safe_float(raw.get("max_abs_vwap_distance", 0.02), default=0.02)
    context_momentum_6h_min = _safe_float(raw.get("context_6h_momentum_min", 0.0), default=0.0)
    context_momentum_12h_min = _safe_float(raw.get("context_12h_momentum_min", -0.01), default=-0.01)
    score_floor = _safe_float(raw.get("min_score", 0.72), default=0.72)
    require_6h_context = bool(raw.get("require_6h_context", True))
    allow_12h_context_override = bool(raw.get("allow_12h_context_override", True))
    trailing_lookback = int(raw.get("trailing_lookback", 4))
    atr_stop_buffer = _safe_float(raw.get("atr_stop_buffer", 0.6), default=0.6)

    df_1h = df_1h.copy().sort_index()
    breakout_high = df_1h["high"].rolling(breakout_lookback).max().shift(1)
    breakout_low = df_1h["low"].rolling(breakout_lookback).min().shift(1)
    structure_long = (df_1h["close"] > breakout_high).fillna(False)
    structure_short = (df_1h["close"] < breakout_low).fillna(False)

    body_strength = df_1h["body_strength"].astype(float)
    close_position = df_1h["close_position"].astype(float)
    expansion = df_1h.get("range_expansion_factor", pd.Series(0.0, index=df_1h.index)).astype(float)
    abs_vwap_distance = df_1h["vwap_distance_ratio"].abs().astype(float)
    ema_gap = df_1h.get("ema_gap_ratio", pd.Series(0.0, index=df_1h.index)).abs().astype(float)

    pass_shape_long = (
        (body_strength >= body_strength_min)
        & (close_position >= close_position_min)
        & (expansion >= expansion_min)
        & (abs_vwap_distance <= max_abs_vwap_distance)
    )
    pass_shape_short = (
        (body_strength >= body_strength_min)
        & (close_position <= (1.0 - close_position_min))
        & (expansion >= expansion_min)
        & (abs_vwap_distance <= max_abs_vwap_distance)
    )

    if df_6h is not None and not df_6h.empty:
        momentum_6h = df_6h["close"].pct_change(1).replace([np.inf, -np.inf], 0.0).fillna(0.0)
        label_6h = pd.Series(
            np.where(
                (df_6h["close"] > df_6h["ema20"]) & (df_6h["ema20"] > df_6h["ema50"]),
                "bullish",
                np.where(
                    (df_6h["close"] < df_6h["ema20"]) & (df_6h["ema20"] < df_6h["ema50"]),
                    "bearish",
                    "neutral",
                ),
            ),
            index=df_6h.index,
        )
        snapshot_6h = pd.DataFrame(
            {
                "label_6h": label_6h,
                "momentum_6h": momentum_6h,
            },
            index=df_6h.index,
        ).reindex(df_1h.index, method="ffill")
    else:
        snapshot_6h = pd.DataFrame(
            {"label_6h": "neutral", "momentum_6h": 0.0},
            index=df_1h.index,
        )

    if df_12h is not None and not df_12h.empty:
        momentum_12h = df_12h["close"].pct_change(1).replace([np.inf, -np.inf], 0.0).fillna(0.0)
        label_12h = pd.Series(
            np.where(
                (df_12h["close"] > df_12h["ema20"]) & (df_12h["ema20"] > df_12h["ema50"]),
                "bullish",
                np.where(
                    (df_12h["close"] < df_12h["ema20"]) & (df_12h["ema20"] < df_12h["ema50"]),
                    "bearish",
                    "neutral",
                ),
            ),
            index=df_12h.index,
        )
        snapshot_12h = pd.DataFrame(
            {
                "label_12h": label_12h,
                "momentum_12h": momentum_12h,
            },
            index=df_12h.index,
        ).reindex(df_1h.index, method="ffill")
    else:
        snapshot_12h = pd.DataFrame(
            {"label_12h": "neutral", "momentum_12h": 0.0},
            index=df_1h.index,
        )

    pass_6h_long = (
        snapshot_6h["label_6h"].eq("bullish")
        & (snapshot_6h["momentum_6h"] >= context_momentum_6h_min)
    )
    pass_6h_short = (
        snapshot_6h["label_6h"].eq("bearish")
        & (snapshot_6h["momentum_6h"] <= -context_momentum_6h_min)
    )
    pass_12h_long = (
        snapshot_12h["label_12h"].eq("bullish")
        & (snapshot_12h["momentum_12h"] >= context_momentum_12h_min)
    )
    pass_12h_short = (
        snapshot_12h["label_12h"].eq("bearish")
        & (snapshot_12h["momentum_12h"] <= -context_momentum_12h_min)
    )

    context_gate_long = (
        pass_6h_long
        if require_6h_context
        else pd.Series(True, index=df_1h.index)
    )
    context_gate_short = (
        pass_6h_short
        if require_6h_context
        else pd.Series(True, index=df_1h.index)
    )
    if allow_12h_context_override:
        context_gate_long = context_gate_long | pass_12h_long
        context_gate_short = context_gate_short | pass_12h_short

    raw_score_long = (
        0.40 * structure_long.astype(float)
        + 0.25 * pass_shape_long.astype(float)
        + 0.20 * pass_6h_long.astype(float)
        + 0.15 * pass_12h_long.astype(float)
    ).clip(lower=0.0, upper=1.0)
    raw_score_short = (
        0.40 * structure_short.astype(float)
        + 0.25 * pass_shape_short.astype(float)
        + 0.20 * pass_6h_short.astype(float)
        + 0.15 * pass_12h_short.astype(float)
    ).clip(lower=0.0, upper=1.0)
    signal_event_long = structure_long & pass_shape_long & context_gate_long & (raw_score_long >= score_floor)
    signal_event_short = structure_short & pass_shape_short & context_gate_short & (raw_score_short >= score_floor)

    stop_long = (
        df_1h["low"].rolling(trailing_lookback).min().shift(1).fillna(df_1h["low"]).astype(float)
        - (df_1h["atr"].astype(float) * atr_stop_buffer)
    )
    stop_short = (
        df_1h["high"].rolling(trailing_lookback).max().shift(1).fillna(df_1h["high"]).astype(float)
        + (df_1h["atr"].astype(float) * atr_stop_buffer)
    )

    snapshot = pd.DataFrame(
        {
            "h1_new_candle": True,
            "signal_event_long": signal_event_long.astype(bool),
            "signal_event_short": signal_event_short.astype(bool),
            "signal_family_long": np.where(structure_long, "h1_structure_continuation", ""),
            "signal_family_short": np.where(structure_short, "h1_structure_continuation", ""),
            "h1_pass_structure_long": structure_long.astype(bool),
            "h1_pass_structure_short": structure_short.astype(bool),
            "h1_pass_shape_long": pass_shape_long.astype(bool),
            "h1_pass_shape_short": pass_shape_short.astype(bool),
            "h1_score_long": raw_score_long.astype(float),
            "h1_score_short": raw_score_short.astype(float),
            "h1_stop_long": stop_long.astype(float),
            "h1_stop_short": stop_short.astype(float),
            "h1_pass_6h_context_long": pass_6h_long.astype(bool),
            "h1_pass_6h_context_short": pass_6h_short.astype(bool),
            "h1_pass_12h_context_long": pass_12h_long.astype(bool),
            "h1_pass_12h_context_short": pass_12h_short.astype(bool),
            "h1_context_gate_long": context_gate_long.astype(bool),
            "h1_context_gate_short": context_gate_short.astype(bool),
            "h1_range_expansion": expansion.astype(float),
            "h1_body_strength": body_strength.astype(float),
            "h1_close_position": close_position.astype(float),
            "h1_vwap_distance_ratio": abs_vwap_distance.astype(float),
            "h1_ema_gap_ratio": ema_gap.astype(float),
            "h1_context_6h": snapshot_6h["label_6h"],
            "h1_context_12h": snapshot_12h["label_12h"],
        },
        index=df_1h.index,
    )

    aligned = snapshot.reindex(execution_index, method="ffill")
    aligned["h1_new_candle"] = pd.Index(execution_index).isin(df_1h.index)
    aligned["signal_event_long"] = signal_event_long.reindex(execution_index, fill_value=False)
    aligned["signal_event_short"] = signal_event_short.reindex(execution_index, fill_value=False)
    aligned["signal_family_long"] = pd.Series(snapshot["signal_family_long"], index=df_1h.index).reindex(execution_index, fill_value="")
    aligned["signal_family_short"] = pd.Series(snapshot["signal_family_short"], index=df_1h.index).reindex(execution_index, fill_value="")
    return aligned


class H1ExecutionEngine:
    """Dormant 1H strategy scaffold. Safe to import, disabled by default."""

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        getter = getattr(self.config, "get", None)
        self.raw = getter("strategy", "h1_execution", default={}) if callable(getter) else {}
        self.raw = self.raw or {}
        self.enabled = bool(self.raw.get("enabled", False))
        self.base_risk_fraction = _safe_float(self.raw.get("base_risk_fraction", 0.0020), default=0.0020)
        self.max_group_risk_fraction = _safe_float(self.raw.get("max_total_risk_fraction", 0.006), default=0.006)
        self.max_open_positions = int(self.raw.get("max_open_positions", 2))
        self.max_hold_1h_candles = int(self.raw.get("max_hold_1h_candles", 36))
        self.selection_threshold_offset = _safe_float(self.raw.get("selection_threshold_offset", -0.02), default=-0.02)
        self.long_selection_threshold_offset = _safe_float(
            self.raw.get("long_selection_threshold_offset", self.selection_threshold_offset),
            default=self.selection_threshold_offset,
        )
        self.short_selection_threshold_offset = _safe_float(
            self.raw.get("short_selection_threshold_offset", self.selection_threshold_offset),
            default=self.selection_threshold_offset,
        )
        self.selection_min_threshold = _safe_float(self.raw.get("selection_min_threshold", 0.74), default=0.74)
        self.selection_max_threshold = _safe_float(self.raw.get("selection_max_threshold", 0.92), default=0.92)
        self.long_risk_multiplier = _safe_float(
            self.raw.get("long_risk_multiplier", 1.0),
            default=1.0,
        )
        self.short_risk_multiplier = _safe_float(
            self.raw.get("short_risk_multiplier", 1.0),
            default=1.0,
        )
        self.context_side_policy = dict(self.raw.get("context_side_policy", {}) or {})
        self.elite_long_exception = dict(self.raw.get("elite_long_exception", {}) or {})
        self.runtime_policy_guard = dict(self.raw.get("runtime_policy_guard", {}) or {})

    def _resolve_context_side_policy(self, snapshot: dict, runtime_policy_state: dict | None = None) -> dict:
        context_label = _normalize_context_label(
            snapshot.get("h1_context_12h") or snapshot.get("h1_context_6h")
        )
        runtime_policy_state = dict(runtime_policy_state or {})
        fallback_to_short_only = bool(runtime_policy_state.get("fallback_to_short_only", False))
        raw_policy = (
            {}
            if fallback_to_short_only
            else dict(self.context_side_policy.get(context_label, {}) or {})
        )
        allowed_sides = raw_policy.get("allowed_sides", self.raw.get("allowed_sides", []))
        return {
            "context_label": context_label,
            "policy_source": "fallback_short_only" if fallback_to_short_only else "context_policy",
            "fallback_to_short_only": fallback_to_short_only,
            "boost_active": bool(not fallback_to_short_only and context_label == "bearish" and raw_policy),
            "allowed_sides": [str(side).lower() for side in (allowed_sides or []) if str(side).strip()],
            "long_selection_threshold_offset": _safe_float(
                raw_policy.get(
                    "long_selection_threshold_offset",
                    self.long_selection_threshold_offset,
                ),
                default=self.long_selection_threshold_offset,
            ),
            "short_selection_threshold_offset": _safe_float(
                raw_policy.get(
                    "short_selection_threshold_offset",
                    self.short_selection_threshold_offset,
                ),
                default=self.short_selection_threshold_offset,
            ),
            "long_risk_multiplier": _safe_float(
                raw_policy.get("long_risk_multiplier", self.long_risk_multiplier),
                default=self.long_risk_multiplier,
            ),
            "short_risk_multiplier": _safe_float(
                raw_policy.get("short_risk_multiplier", self.short_risk_multiplier),
                default=self.short_risk_multiplier,
            ),
        }

    def _resolve_elite_long_exception(self, snapshot: dict) -> dict:
        raw = self.elite_long_exception
        context_6h = _normalize_context_label(snapshot.get("h1_context_6h"))
        context_12h = _normalize_context_label(snapshot.get("h1_context_12h"))
        pass_6h = _bool_value(snapshot.get("h1_pass_6h_context_long"))
        pass_12h = _bool_value(snapshot.get("h1_pass_12h_context_long"))
        score_value = _safe_float(snapshot.get("h1_score_long"), default=0.0)
        body_strength = _safe_float(snapshot.get("h1_body_strength"), default=0.0)
        close_position = _safe_float(snapshot.get("h1_close_position"), default=0.0)
        range_expansion = _safe_float(snapshot.get("h1_range_expansion"), default=0.0)

        enabled = bool(raw.get("enabled", False))
        min_score = _safe_float(raw.get("min_score", 0.92), default=0.92)
        min_body_strength = _safe_float(raw.get("min_body_strength", 1.8), default=1.8)
        min_close_position = _safe_float(raw.get("min_close_position", 0.82), default=0.82)
        min_range_expansion = _safe_float(raw.get("min_range_expansion", 1.15), default=1.15)
        require_6h_context = bool(raw.get("require_6h_context", True))
        require_12h_context = bool(raw.get("require_12h_context", True))
        require_bullish_6h = bool(raw.get("require_bullish_6h_label", True))
        require_bullish_12h = bool(raw.get("require_bullish_12h_label", True))
        passed = bool(
            enabled
            and score_value >= min_score
            and body_strength >= min_body_strength
            and close_position >= min_close_position
            and range_expansion >= min_range_expansion
            and (not require_6h_context or pass_6h)
            and (not require_12h_context or pass_12h)
            and (not require_bullish_6h or context_6h == "bullish")
            and (not require_bullish_12h or context_12h == "bullish")
        )
        return {
            "enabled": enabled,
            "passed": passed,
            "selection_threshold_offset": _safe_float(
                raw.get("selection_threshold_offset", -0.01),
                default=-0.01,
            ),
            "risk_multiplier": _safe_float(
                raw.get("risk_multiplier", 0.80),
                default=0.80,
            ),
        }

    def build_candidate(
        self,
        *,
        symbol,
        timestamp,
        execution_row,
        snapshot,
        momentum_rank,
        top_symbols,
        runtime_policy_state=None,
    ):
        del top_symbols
        if not self.enabled or not snapshot or not _bool_value(snapshot.get("h1_new_candle")):
            return None
        if not _symbol_is_allowed(symbol, self.raw):
            return None

        side = None
        if _bool_value(snapshot.get("signal_event_long")):
            side = "long"
        elif _bool_value(snapshot.get("signal_event_short")):
            side = "short"
        else:
            return None
        context_policy = self._resolve_context_side_policy(
            snapshot,
            runtime_policy_state=runtime_policy_state,
        )
        elite_long_exception = self._resolve_elite_long_exception(snapshot)
        exception_applied = False
        if not _side_is_allowed(side, {"allowed_sides": context_policy["allowed_sides"]}):
            if side == "long" and elite_long_exception["passed"]:
                exception_applied = True
            else:
                return None

        score_value = _safe_float(snapshot.get(f"h1_score_{side}"), default=0.0)
        stop_price = _safe_float(snapshot.get(f"h1_stop_{side}"), default=np.nan)
        entry_price = _safe_float(execution_row.get("close"), default=np.nan)
        if not np.isfinite(stop_price) or not np.isfinite(entry_price):
            return None
        if side == "long" and stop_price >= entry_price:
            return None
        if side == "short" and stop_price <= entry_price:
            return None

        raw_score = clamp(score_value)
        strategy_type = "h1_execution"
        if exception_applied:
            side_threshold_offset = elite_long_exception["selection_threshold_offset"]
            side_risk_multiplier = elite_long_exception["risk_multiplier"]
        else:
            side_threshold_offset = (
                context_policy["short_selection_threshold_offset"]
                if side == "short"
                else context_policy["long_selection_threshold_offset"]
            )
            side_risk_multiplier = (
                context_policy["short_risk_multiplier"]
                if side == "short"
                else context_policy["long_risk_multiplier"]
            )
        return {
            "symbol": symbol,
            "timestamp": timestamp,
            "side": side,
            "row": execution_row,
            "bias": context_policy["context_label"],
            "edge_type": strategy_type,
            "body_bucket": "strong" if _safe_float(snapshot.get("h1_body_strength"), 0.0) >= 1.5 else "weak",
            "vwap_bucket": "moderate",
            "bucket_key_text": f"{strategy_type}|placeholder|scaffold|moderate",
            "bucket_valid": True,
            "bucket_expected_return": None,
            "bucket_risk_mult": 1.0,
            "risk_mult": 1.0,
            "momentum_rank": float(momentum_rank or 0.0),
            "is_top_mover": False,
            "score": raw_score,
            "score_bucket": score_bucket_label(raw_score),
            "selection_score": clamp(0.80 * raw_score + 0.20 * float(momentum_rank or 0.0)),
            "strategy_type": strategy_type,
            "signal_family": str(snapshot.get(f"signal_family_{side}", strategy_type) or strategy_type),
            "risk_group": strategy_type,
            "group_risk_cap": self.max_group_risk_fraction,
            "max_open_positions_for_strategy": self.max_open_positions,
            "block_same_symbol_same_side": True,
            "apply_score_bucket_filters": False,
            "selection_threshold_offset": side_threshold_offset,
            "selection_min_threshold": self.selection_min_threshold,
            "selection_max_threshold": self.selection_max_threshold,
            "risk_fraction_override": self.base_risk_fraction * side_risk_multiplier,
            "moonshot_score": raw_score,
            "context_side_policy_label": context_policy["context_label"],
            "context_policy_source": context_policy["policy_source"],
            "context_policy_fallback_active": context_policy["fallback_to_short_only"],
            "context_policy_boost_active": context_policy["boost_active"],
            "policy_monitor_label": runtime_policy_state.get("label") if runtime_policy_state else None,
            "policy_monitor_count": int(runtime_policy_state.get("count", 0) or 0)
            if runtime_policy_state
            else 0,
            "policy_monitor_profit_factor": _safe_float(
                runtime_policy_state.get("profit_factor"),
                default=np.nan,
            )
            if runtime_policy_state
            else np.nan,
            "policy_monitor_avg_r": _safe_float(
                runtime_policy_state.get("avg_R"),
                default=np.nan,
            )
            if runtime_policy_state
            else np.nan,
            "elite_long_exception_applied": exception_applied,
            "range_expansion_factor": _safe_float(snapshot.get("h1_range_expansion"), default=0.0),
            "execution_profile": {
                "disable_pyramiding": True,
                "disable_trailing": True,
                "max_hold_candles": self.max_hold_1h_candles * 4,
            },
            "stop_price_override": stop_price,
            "deferred_layer": True,
        }
