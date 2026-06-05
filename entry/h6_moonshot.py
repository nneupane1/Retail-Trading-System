"""Dormant 6H bridge-layer scaffolding between 15m execution and 12H moonshots."""

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


def _empty_h6_frame(execution_index):
    frame = pd.DataFrame(index=pd.Index(execution_index))
    frame["h6_new_candle"] = False
    frame["signal_event_long"] = False
    frame["signal_family_long"] = ""
    return frame


def _build_h6_candidate(
    *,
    symbol,
    timestamp,
    execution_row,
    snapshot,
    momentum_rank,
    top_symbols,
    strategy_type,
    base_risk_fraction,
    max_group_risk_fraction,
    max_open_positions,
    max_hold_6h_candles,
    selection_threshold_offset,
    selection_min_threshold,
    selection_max_threshold,
    min_score,
    require_signal_event,
    top_mover_bonus,
    selection_bonus,
):
    if not snapshot or not _bool_value(snapshot.get("h6_new_candle")):
        return None
    if require_signal_event and not _bool_value(snapshot.get("signal_event_long")):
        return None
    if not _bool_value(snapshot.get("h6_pass_structure_long")):
        return None
    if not _bool_value(snapshot.get("h6_pass_shape_long")):
        return None
    if not _bool_value(snapshot.get("h6_pass_12h_context_long")):
        return None
    if not _bool_value(snapshot.get("h6_pass_1d_context_long")):
        return None

    raw_score = clamp(_safe_float(snapshot.get("h6_score_long"), default=0.0))
    if raw_score < float(min_score):
        return None

    stop_price = _safe_float(snapshot.get("h6_stop_long"), default=np.nan)
    entry_price = _safe_float(execution_row.get("close"), default=np.nan)
    if not np.isfinite(stop_price) or not np.isfinite(entry_price) or stop_price >= entry_price:
        return None

    is_top_mover = symbol in set(top_symbols or [])
    selection_score = clamp(
        0.85 * raw_score
        + 0.15 * float(momentum_rank or 0.0)
        + float(selection_bonus or 0.0)
        + (float(top_mover_bonus or 0.0) if is_top_mover else 0.0)
    )

    return {
        "symbol": symbol,
        "timestamp": timestamp,
        "side": "long",
        "row": execution_row,
        "bias": str(snapshot.get("h6_context_12h", "neutral") or "neutral"),
        "edge_type": strategy_type,
        "body_bucket": "strong" if _safe_float(snapshot.get("h6_body_strength"), 0.0) >= 1.5 else "weak",
        "vwap_bucket": "moderate",
        "bucket_key_text": f"{strategy_type}|placeholder|scaffold|moderate",
        "bucket_valid": True,
        "bucket_expected_return": None,
        "bucket_risk_mult": 1.0,
        "risk_mult": 1.0,
        "momentum_rank": float(momentum_rank or 0.0),
        "is_top_mover": is_top_mover,
        "score": raw_score,
        "score_bucket": score_bucket_label(raw_score),
        "selection_score": selection_score,
        "strategy_type": strategy_type,
        "signal_family": str(snapshot.get("signal_family_long", strategy_type) or strategy_type),
        "risk_group": strategy_type,
        "group_risk_cap": max_group_risk_fraction,
        "max_open_positions_for_strategy": max_open_positions,
        "block_same_symbol_same_side": True,
        "apply_score_bucket_filters": False,
        "selection_threshold_offset": selection_threshold_offset,
        "selection_min_threshold": selection_min_threshold,
        "selection_max_threshold": selection_max_threshold,
        "risk_fraction_override": base_risk_fraction,
        "moonshot_score": raw_score if strategy_type.endswith("moonshot") else None,
        "range_expansion_factor": _safe_float(snapshot.get("h6_range_expansion"), default=0.0),
        "execution_profile": {
            "disable_pyramiding": True,
            "disable_trailing": True,
            "max_hold_candles": max_hold_6h_candles * 24,
        },
        "stop_price_override": stop_price,
        "deferred_layer": True,
    }


def build_h6_moonshot_snapshots(execution_index, df_6h, df_12h=None, df_1d=None, *, config=None):
    """Builds dormant 6H bridge snapshots aligned to the 15m execution clock."""

    config = config or AppConfig.load()
    getter = getattr(config, "get", None)
    moonshot_raw = getter("strategy", "h6_moonshot", default={}) if callable(getter) else {}
    standard_raw = getter("strategy", "h6_standard", default={}) if callable(getter) else {}
    moonshot_raw = moonshot_raw or {}
    standard_raw = standard_raw or {}
    raw = moonshot_raw if bool(moonshot_raw.get("enabled", False)) else standard_raw
    raw = raw or {}
    if not bool(moonshot_raw.get("enabled", False)) and not bool(standard_raw.get("enabled", False)):
        return _empty_h6_frame(execution_index)

    breakout_lookback = int(raw.get("breakout_lookback", 8))
    body_strength_min = _safe_float(raw.get("body_strength_min", 1.5), default=1.5)
    close_position_min = _safe_float(raw.get("close_position_min", 0.75), default=0.75)
    expansion_min = _safe_float(raw.get("expansion_min", 1.12), default=1.12)
    max_abs_vwap_distance = _safe_float(raw.get("max_abs_vwap_distance", 0.025), default=0.025)
    min_score = _safe_float(raw.get("min_score", 0.76), default=0.76)
    atr_stop_buffer = _safe_float(raw.get("atr_stop_buffer", 0.55), default=0.55)
    trailing_lookback = int(raw.get("trailing_lookback", 3))
    context_12h_momentum_min = _safe_float(raw.get("context_12h_momentum_min", 0.0), default=0.0)
    context_1d_momentum_min = _safe_float(raw.get("context_1d_momentum_min", -0.01), default=-0.01)

    df_6h = df_6h.copy().sort_index()
    breakout_high = df_6h["high"].rolling(breakout_lookback).max().shift(1)
    structure_long = (df_6h["close"] > breakout_high).fillna(False)
    body_strength = df_6h["body_strength"].astype(float)
    close_position = df_6h["close_position"].astype(float)
    expansion = df_6h.get("range_expansion_factor", pd.Series(0.0, index=df_6h.index)).astype(float)
    abs_vwap_distance = df_6h["vwap_distance_ratio"].abs().astype(float)

    pass_shape_long = (
        (body_strength >= body_strength_min)
        & (close_position >= close_position_min)
        & (expansion >= expansion_min)
        & (abs_vwap_distance <= max_abs_vwap_distance)
    )

    if df_12h is not None and not df_12h.empty:
        snapshot_12h = pd.DataFrame(
            {
                "label_12h": np.where(
                    (df_12h["close"] > df_12h["ema20"]) & (df_12h["ema20"] > df_12h["ema50"]),
                    "bullish",
                    "neutral",
                ),
                "momentum_12h": df_12h["close"].pct_change(1).replace([np.inf, -np.inf], 0.0).fillna(0.0),
            },
            index=df_12h.index,
        ).reindex(df_6h.index, method="ffill")
    else:
        snapshot_12h = pd.DataFrame({"label_12h": "neutral", "momentum_12h": 0.0}, index=df_6h.index)

    if df_1d is not None and not df_1d.empty:
        snapshot_1d = pd.DataFrame(
            {
                "label_1d": np.where(
                    (df_1d["close"] > df_1d["ema20"]) & (df_1d["ema20"] > df_1d["ema50"]),
                    "bullish",
                    "neutral",
                ),
                "momentum_1d": df_1d["close"].pct_change(1).replace([np.inf, -np.inf], 0.0).fillna(0.0),
            },
            index=df_1d.index,
        ).reindex(df_6h.index, method="ffill")
    else:
        snapshot_1d = pd.DataFrame({"label_1d": "neutral", "momentum_1d": 0.0}, index=df_6h.index)

    pass_12h_context = snapshot_12h["label_12h"].eq("bullish") & (snapshot_12h["momentum_12h"] >= context_12h_momentum_min)
    pass_1d_context = snapshot_1d["label_1d"].eq("bullish") & (snapshot_1d["momentum_1d"] >= context_1d_momentum_min)

    raw_score = (
        0.45 * structure_long.astype(float)
        + 0.25 * pass_shape_long.astype(float)
        + 0.15 * pass_12h_context.astype(float)
        + 0.15 * pass_1d_context.astype(float)
    ).clip(lower=0.0, upper=1.0)
    signal_event_long = structure_long & pass_shape_long & pass_12h_context & pass_1d_context & (raw_score >= min_score)

    stop_long = (
        df_6h["low"].rolling(trailing_lookback).min().shift(1).fillna(df_6h["low"]).astype(float)
        - (df_6h["atr"].astype(float) * atr_stop_buffer)
    )

    snapshot = pd.DataFrame(
        {
            "h6_new_candle": True,
            "signal_event_long": signal_event_long.astype(bool),
            "signal_family_long": np.where(structure_long, "h6_bridge_breakout", ""),
            "h6_pass_structure_long": structure_long.astype(bool),
            "h6_pass_shape_long": pass_shape_long.astype(bool),
            "h6_score_long": raw_score.astype(float),
            "h6_stop_long": stop_long.astype(float),
            "h6_pass_12h_context_long": pass_12h_context.astype(bool),
            "h6_pass_1d_context_long": pass_1d_context.astype(bool),
            "h6_range_expansion": expansion.astype(float),
            "h6_body_strength": body_strength.astype(float),
            "h6_close_position": close_position.astype(float),
            "h6_vwap_distance_ratio": abs_vwap_distance.astype(float),
            "h6_context_12h": snapshot_12h["label_12h"],
            "h6_context_1d": snapshot_1d["label_1d"],
        },
        index=df_6h.index,
    )

    aligned = snapshot.reindex(execution_index, method="ffill")
    aligned["h6_new_candle"] = pd.Index(execution_index).isin(df_6h.index)
    aligned["signal_event_long"] = signal_event_long.reindex(execution_index, fill_value=False)
    aligned["signal_family_long"] = pd.Series(snapshot["signal_family_long"], index=df_6h.index).reindex(execution_index, fill_value="")
    return aligned


class H6MoonshotEngine:
    """Dormant 6H bridge sleeve scaffold. Disabled by default and not wired live."""

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        getter = getattr(self.config, "get", None)
        self.raw = getter("strategy", "h6_moonshot", default={}) if callable(getter) else {}
        self.raw = self.raw or {}
        self.enabled = bool(self.raw.get("enabled", False))
        self.base_risk_fraction = _safe_float(self.raw.get("base_risk_fraction", 0.0025), default=0.0025)
        self.max_group_risk_fraction = _safe_float(self.raw.get("max_total_risk_fraction", 0.008), default=0.008)
        self.max_open_positions = int(self.raw.get("max_open_positions", 2))
        self.max_hold_6h_candles = int(self.raw.get("max_hold_6h_candles", 30))
        self.selection_threshold_offset = _safe_float(self.raw.get("selection_threshold_offset", -0.03), default=-0.03)
        self.selection_min_threshold = _safe_float(self.raw.get("selection_min_threshold", 0.74), default=0.74)
        self.selection_max_threshold = _safe_float(self.raw.get("selection_max_threshold", 0.92), default=0.92)

    def build_candidate(self, *, symbol, timestamp, execution_row, snapshot, momentum_rank, top_symbols):
        if not self.enabled:
            return None
        if not _symbol_is_allowed(symbol, self.raw):
            return None
        return _build_h6_candidate(
            symbol=symbol,
            timestamp=timestamp,
            execution_row=execution_row,
            snapshot=snapshot,
            momentum_rank=momentum_rank,
            top_symbols=top_symbols,
            strategy_type="h6_moonshot",
            base_risk_fraction=self.base_risk_fraction,
            max_group_risk_fraction=self.max_group_risk_fraction,
            max_open_positions=self.max_open_positions,
            max_hold_6h_candles=self.max_hold_6h_candles,
            selection_threshold_offset=self.selection_threshold_offset,
            selection_min_threshold=self.selection_min_threshold,
            selection_max_threshold=self.selection_max_threshold,
            min_score=_safe_float(self.raw.get("min_score", 0.76), default=0.76),
            require_signal_event=True,
            top_mover_bonus=0.0,
            selection_bonus=0.0,
        )


class H6StandardEngine:
    """Research-only 6H standard sleeve companion to the stricter moonshot layer."""

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        getter = getattr(self.config, "get", None)
        self.raw = getter("strategy", "h6_standard", default={}) if callable(getter) else {}
        self.raw = self.raw or {}
        self.enabled = bool(self.raw.get("enabled", False))
        self.base_risk_fraction = _safe_float(self.raw.get("base_risk_fraction", 0.0018), default=0.0018)
        self.max_group_risk_fraction = _safe_float(self.raw.get("max_total_risk_fraction", 0.0055), default=0.0055)
        self.max_open_positions = int(self.raw.get("max_open_positions", 2))
        self.max_hold_6h_candles = int(self.raw.get("max_hold_6h_candles", 18))
        self.selection_threshold_offset = _safe_float(self.raw.get("selection_threshold_offset", -0.10), default=-0.10)
        self.selection_min_threshold = _safe_float(self.raw.get("selection_min_threshold", 0.62), default=0.62)
        self.selection_max_threshold = _safe_float(self.raw.get("selection_max_threshold", 0.88), default=0.88)
        self.min_score = _safe_float(self.raw.get("min_score", 0.68), default=0.68)
        self.top_mover_bonus = _safe_float(self.raw.get("top_mover_bonus", 0.02), default=0.02)
        self.selection_bonus = _safe_float(self.raw.get("selection_bonus", 0.02), default=0.02)

    def build_candidate(self, *, symbol, timestamp, execution_row, snapshot, momentum_rank, top_symbols):
        if not self.enabled:
            return None
        if not _symbol_is_allowed(symbol, self.raw):
            return None
        return _build_h6_candidate(
            symbol=symbol,
            timestamp=timestamp,
            execution_row=execution_row,
            snapshot=snapshot,
            momentum_rank=momentum_rank,
            top_symbols=top_symbols,
            strategy_type="h6_standard",
            base_risk_fraction=self.base_risk_fraction,
            max_group_risk_fraction=self.max_group_risk_fraction,
            max_open_positions=self.max_open_positions,
            max_hold_6h_candles=self.max_hold_6h_candles,
            selection_threshold_offset=self.selection_threshold_offset,
            selection_min_threshold=self.selection_min_threshold,
            selection_max_threshold=self.selection_max_threshold,
            min_score=self.min_score,
            require_signal_event=False,
            top_mover_bonus=self.top_mover_bonus,
            selection_bonus=self.selection_bonus,
        )
