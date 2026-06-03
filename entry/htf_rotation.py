"""Cross-sectional 12H leader-rotation engine for Binance crypto breadth."""

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


def _label_trend(close_series, fast_series, slow_series, slope_series, slope_threshold):
    bullish = (
        (close_series > fast_series)
        & (fast_series > slow_series)
        & (slope_series > slope_threshold)
    )
    bearish = (
        (close_series < fast_series)
        & (fast_series < slow_series)
        & (slope_series < -slope_threshold)
    )
    return pd.Series(
        np.where(bullish, "bullish", np.where(bearish, "bearish", "neutral")),
        index=close_series.index,
    )


def _vwap_bucket(abs_distance_ratio, near_threshold, moderate_threshold):
    if abs_distance_ratio <= near_threshold:
        return "near"
    if abs_distance_ratio <= moderate_threshold:
        return "moderate"
    return "far"


def _empty_rotation_frame(execution_index):
    frame = pd.DataFrame(index=pd.Index(execution_index))
    frame["htf_rotation_new_candle"] = False
    frame["signal_event_long"] = False
    frame["signal_family_long"] = ""
    return frame


def build_htf_rotation_snapshots_by_symbol(
    execution_indexes_by_symbol,
    df_12h_by_symbol,
    df_1d_by_symbol,
    df_1w_by_symbol,
    *,
    structural_snapshots_by_symbol=None,
    config=None,
):
    """Build aligned 12H leader-rotation snapshots for each symbol."""

    config = config or AppConfig.load()
    getter = getattr(config, "get", None)
    raw = (
        getter("strategy", "htf_12h_rotation", default={})
        if callable(getter)
        else {}
    ) or {}
    if not bool(raw.get("enabled", False)):
        return {
            symbol: _empty_rotation_frame(execution_indexes_by_symbol.get(symbol, []))
            for symbol in df_12h_by_symbol
        }

    ema_periods = config.require("features", "ema_periods")
    fast_column = f"ema{ema_periods['fast']}"
    slow_column = f"ema{ema_periods['slow']}"

    ret_12h_weight = _safe_float(raw.get("ret_12h_weight", 0.25), default=0.25)
    ret_24h_weight = _safe_float(raw.get("ret_24h_weight", 0.30), default=0.30)
    ret_48h_weight = _safe_float(raw.get("ret_48h_weight", 0.20), default=0.20)
    expansion_weight = _safe_float(raw.get("expansion_weight", 0.15), default=0.15)
    relative_strength_weight = _safe_float(
        raw.get("relative_strength_weight", 0.10),
        default=0.10,
    )
    rank_change_weight = _safe_float(raw.get("rank_change_weight", 0.08), default=0.08)
    overlap_penalty = _safe_float(raw.get("structure_overlap_penalty", 0.03), default=0.03)
    min_history_bars = int(raw.get("min_history_bars", 8))
    top_k = int(raw.get("top_k", 4))
    min_leader_score = _safe_float(raw.get("min_leader_score", 0.78), default=0.78)
    min_relative_strength = _safe_float(
        raw.get("min_relative_strength", 0.82),
        default=0.82,
    )
    min_liquidity_percentile = _safe_float(
        raw.get("min_liquidity_percentile", 0.30),
        default=0.30,
    )
    min_volume_expansion = _safe_float(
        raw.get("min_volume_expansion", 1.05),
        default=1.05,
    )
    min_range_expansion = _safe_float(
        raw.get("min_range_expansion", 1.05),
        default=1.05,
    )
    min_positive_periods = int(raw.get("min_positive_periods", 2))
    max_vwap_distance = _safe_float(raw.get("max_vwap_distance", 0.03), default=0.03)
    max_ema_distance = _safe_float(raw.get("max_ema_distance", 0.08), default=0.08)
    strong_body_min = _safe_float(raw.get("strong_body_strength", 1.3), default=1.3)
    strong_close_min = _safe_float(raw.get("strong_close_position", 0.65), default=0.65)
    supportive_expansion = _safe_float(
        raw.get("supportive_expansion", 1.15),
        default=1.15,
    )
    strong_expansion = _safe_float(raw.get("strong_expansion", 1.60), default=1.60)
    trailing_lookback = int(raw.get("trailing_lookback", 6))
    atr_stop_buffer = _safe_float(raw.get("atr_stop_buffer", 0.6), default=0.6)
    liquidity_lookback = int(raw.get("liquidity_lookback", 10))
    volume_expansion_lookback = int(raw.get("volume_expansion_lookback", 10))
    daily_momentum_lookback = int(raw.get("daily_momentum_lookback", 10))
    weekly_momentum_lookback = int(raw.get("weekly_momentum_lookback", 4))
    daily_slope_lookback = int(raw.get("daily_slope_lookback", 3))
    weekly_slope_lookback = int(raw.get("weekly_slope_lookback", 2))
    daily_momentum_min = _safe_float(raw.get("min_daily_momentum", 0.0), default=0.0)
    weekly_momentum_min = _safe_float(raw.get("min_weekly_momentum", -0.02), default=-0.02)
    slope_threshold = _safe_float(raw.get("slope_threshold", 0.0), default=0.0)
    allow_daily_or_weekly_confirmation = bool(
        raw.get("allow_daily_or_weekly_confirmation", True)
    )
    decay_12h_candles = int(raw.get("decay_12h_candles", 2))
    decay_rank_floor = _safe_float(raw.get("decay_rank_floor", 0.70), default=0.70)
    decay_leader_score = _safe_float(raw.get("decay_leader_score", 0.68), default=0.68)
    rank_entry_floor = _safe_float(raw.get("rank_entry_floor", 0.55), default=0.55)
    require_rank_improvement = bool(raw.get("require_rank_improvement", False))

    common_index = sorted(
        set().union(*(frame.index for frame in df_12h_by_symbol.values()))
    )
    common_index = pd.Index(common_index)

    close_df = pd.DataFrame(
        {symbol: frame["close"] for symbol, frame in df_12h_by_symbol.items()},
        index=common_index,
    )
    volume_df = pd.DataFrame(
        {symbol: frame["volume"] for symbol, frame in df_12h_by_symbol.items()},
        index=common_index,
    )
    range_exp_df = pd.DataFrame(
        {
            symbol: frame["range_expansion_factor"]
            for symbol, frame in df_12h_by_symbol.items()
        },
        index=common_index,
    )
    body_strength_df = pd.DataFrame(
        {symbol: frame["body_strength"] for symbol, frame in df_12h_by_symbol.items()},
        index=common_index,
    )
    close_position_df = pd.DataFrame(
        {symbol: frame["close_position"] for symbol, frame in df_12h_by_symbol.items()},
        index=common_index,
    )
    vwap_distance_df = pd.DataFrame(
        {
            symbol: frame["vwap_distance_ratio"].abs()
            for symbol, frame in df_12h_by_symbol.items()
        },
        index=common_index,
    )
    ema_gap_df = pd.DataFrame(
        {
            symbol: frame["ema_gap_ratio"].abs()
            for symbol, frame in df_12h_by_symbol.items()
        },
        index=common_index,
    )

    ret_12h = close_df.pct_change(1)
    ret_24h = close_df.pct_change(2)
    ret_48h = close_df.pct_change(4)
    ret_12h_rank = ret_12h.rank(axis=1, pct=True, ascending=True)
    ret_24h_rank = ret_24h.rank(axis=1, pct=True, ascending=True)
    ret_48h_rank = ret_48h.rank(axis=1, pct=True, ascending=True)
    momentum_score = (
        (ret_12h_rank * ret_12h_weight)
        + (ret_24h_rank * ret_24h_weight)
        + (ret_48h_rank * ret_48h_weight)
    )
    relative_strength = momentum_score.rank(axis=1, pct=True, ascending=True)

    volume_baseline = volume_df.rolling(volume_expansion_lookback).mean()
    volume_expansion = (
        volume_df / (volume_baseline + 1e-9)
    ).replace([np.inf, -np.inf], np.nan)
    volume_rank = volume_expansion.rank(axis=1, pct=True, ascending=True)
    range_rank = range_exp_df.rank(axis=1, pct=True, ascending=True)
    expansion_score = (0.6 * range_rank) + (0.4 * volume_rank)

    rank_change = (relative_strength - relative_strength.shift(1)).fillna(0.0)
    rank_change_rank = rank_change.rank(axis=1, pct=True, ascending=True).fillna(0.5)
    leader_score = (
        momentum_score
        + (expansion_score * expansion_weight)
        + (relative_strength * relative_strength_weight)
        + (rank_change_rank * rank_change_weight)
    )

    notional_volume = close_df * volume_df
    rolling_notional = notional_volume.rolling(liquidity_lookback).mean()
    liquidity_rank = rolling_notional.rank(axis=1, pct=True, ascending=True)

    if structural_snapshots_by_symbol:
        structure_overlap_df = pd.DataFrame(
            {
                symbol: (
                    structural_snapshots_by_symbol[symbol]
                    .reindex(common_index)
                    .get("signal_event_long", False)
                    .astype(bool)
                )
                for symbol in df_12h_by_symbol
            },
            index=common_index,
        )
        leader_score = leader_score - (structure_overlap_df.astype(float) * overlap_penalty)
    else:
        structure_overlap_df = pd.DataFrame(False, index=common_index, columns=close_df.columns)

    positive_periods = (
        (ret_12h > 0).astype(int)
        + (ret_24h > 0).astype(int)
        + (ret_48h > 0).astype(int)
    )
    strong_multi_period = (ret_24h > 0) & (ret_48h > 0)
    dominant_leadership = relative_strength >= max(min_relative_strength + 0.10, 0.92)
    pass_persistence = (
        (relative_strength >= min_relative_strength)
        & (
            (positive_periods >= min_positive_periods)
            | strong_multi_period
            | dominant_leadership
        )
        & ((rank_change_rank >= rank_entry_floor) | (~require_rank_improvement))
    )
    pass_expansion = (
        (range_exp_df >= min_range_expansion)
        & (volume_expansion >= min_volume_expansion)
    )
    pass_stretch = (
        (vwap_distance_df <= max_vwap_distance)
        & (ema_gap_df <= max_ema_distance)
    )
    pass_quality = (
        ((body_strength_df >= strong_body_min) | (close_position_df >= strong_close_min))
        & (range_exp_df >= supportive_expansion)
    )
    pass_liquidity = liquidity_rank >= min_liquidity_percentile
    pass_score = leader_score >= min_leader_score
    enough_history = (
        close_df.notna().rolling(min_history_bars).sum() >= min_history_bars
    )
    leader_rank = leader_score.rank(axis=1, method="first", ascending=False)
    pass_top_rank = leader_rank <= max(1, top_k)

    snapshots = {}
    for symbol, df_12h in df_12h_by_symbol.items():
        if df_12h.empty:
            snapshots[symbol] = _empty_rotation_frame(execution_indexes_by_symbol.get(symbol, []))
            continue

        df_1d = df_1d_by_symbol[symbol]
        df_1w = df_1w_by_symbol[symbol]
        execution_index = execution_indexes_by_symbol.get(symbol, [])
        fast_ema_12h = df_12h[fast_column].astype(float)
        slow_ema_12h = df_12h[slow_column].astype(float)
        atr_12h = df_12h["atr"].astype(float)

        daily_fast = df_1d[fast_column].astype(float)
        daily_slow = df_1d[slow_column].astype(float)
        daily_slope = (
            (daily_fast - daily_fast.shift(daily_slope_lookback))
            / daily_fast.shift(daily_slope_lookback)
        ).replace([np.inf, -np.inf], 0.0).fillna(0.0)
        daily_momentum = (
            df_1d["close"].pct_change(daily_momentum_lookback)
        ).replace([np.inf, -np.inf], 0.0).fillna(0.0)
        daily_label = _label_trend(
            df_1d["close"].astype(float),
            daily_fast,
            daily_slow,
            daily_slope,
            slope_threshold,
        )

        weekly_fast = df_1w[fast_column].astype(float)
        weekly_slow = df_1w[slow_column].astype(float)
        weekly_slope = (
            (weekly_fast - weekly_fast.shift(weekly_slope_lookback))
            / weekly_fast.shift(weekly_slope_lookback)
        ).replace([np.inf, -np.inf], 0.0).fillna(0.0)
        weekly_momentum = (
            df_1w["close"].pct_change(weekly_momentum_lookback)
        ).replace([np.inf, -np.inf], 0.0).fillna(0.0)
        weekly_label = _label_trend(
            df_1w["close"].astype(float),
            weekly_fast,
            weekly_slow,
            weekly_slope,
            slope_threshold,
        )

        daily_snapshot = pd.DataFrame(
            {
                "daily_label": daily_label,
                "daily_momentum": daily_momentum,
                "daily_slope": daily_slope,
            },
            index=df_1d.index,
        ).reindex(df_12h.index, method="ffill")
        weekly_snapshot = pd.DataFrame(
            {
                "weekly_label": weekly_label,
                "weekly_momentum": weekly_momentum,
                "weekly_slope": weekly_slope,
            },
            index=df_1w.index,
        ).reindex(df_12h.index, method="ffill")

        symbol_score = leader_score[symbol].reindex(df_12h.index).fillna(0.0)
        symbol_relative_strength = relative_strength[symbol].reindex(df_12h.index).fillna(0.0)
        symbol_rank_change = rank_change[symbol].reindex(df_12h.index).fillna(0.0)
        symbol_rank_change_rank = rank_change_rank[symbol].reindex(df_12h.index).fillna(0.5)
        symbol_range_expansion = range_exp_df[symbol].reindex(df_12h.index).fillna(0.0)
        symbol_volume_expansion = volume_expansion[symbol].reindex(df_12h.index).fillna(0.0)
        symbol_momentum_score = momentum_score[symbol].reindex(df_12h.index).fillna(0.0)
        symbol_liquidity_rank = liquidity_rank[symbol].reindex(df_12h.index).fillna(0.0)
        symbol_leader_rank = leader_rank[symbol].reindex(df_12h.index).fillna(float(len(df_12h_by_symbol)))
        symbol_pass_top_rank = pass_top_rank[symbol].reindex(df_12h.index).fillna(False)
        symbol_pass_liquidity = pass_liquidity[symbol].reindex(df_12h.index).fillna(False)
        symbol_pass_persistence = pass_persistence[symbol].reindex(df_12h.index).fillna(False)
        symbol_pass_expansion = pass_expansion[symbol].reindex(df_12h.index).fillna(False)
        symbol_pass_stretch = pass_stretch[symbol].reindex(df_12h.index).fillna(False)
        symbol_pass_quality = pass_quality[symbol].reindex(df_12h.index).fillna(False)
        symbol_pass_score = pass_score[symbol].reindex(df_12h.index).fillna(False)
        symbol_history_ok = enough_history[symbol].reindex(df_12h.index).fillna(False)
        symbol_structure_overlap = (
            structure_overlap_df[symbol].reindex(df_12h.index).fillna(False)
        )

        daily_bullish = daily_snapshot["daily_label"].eq("bullish")
        weekly_bullish = weekly_snapshot["weekly_label"].eq("bullish")
        daily_support_long = (
            (daily_snapshot["daily_momentum"] >= daily_momentum_min)
            & (~daily_snapshot["daily_label"].eq("bearish"))
        )
        weekly_support_long = (
            (weekly_snapshot["weekly_momentum"] >= weekly_momentum_min)
            & (~weekly_snapshot["weekly_label"].eq("bearish"))
        )
        supportive_long_context = (
            daily_bullish
            | (
                daily_support_long
                & (
                    weekly_bullish
                    | (symbol_range_expansion >= supportive_expansion)
                )
            )
        )

        pass_1d_context = supportive_long_context.astype(bool)
        pass_1w_context = weekly_support_long.astype(bool)
        if allow_daily_or_weekly_confirmation:
            pass_context_gate = pass_1d_context | (
                pass_1w_context & (~daily_snapshot["daily_label"].eq("bearish"))
            )
        else:
            pass_context_gate = pass_1d_context & pass_1w_context

        signal_low = np.minimum(
            df_12h["low"].astype(float),
            df_12h["low"].rolling(trailing_lookback).min().shift(1).fillna(df_12h["low"]).astype(float),
        )
        htf_stop_long = signal_low - (atr_12h * atr_stop_buffer)

        trailing_confirmation = np.maximum(
            fast_ema_12h - (0.9 * atr_12h),
            df_12h["low"].rolling(trailing_lookback).min().shift(1).fillna(df_12h["low"]).astype(float),
        )
        trailing_expansion = np.maximum(
            fast_ema_12h - (1.4 * atr_12h),
            slow_ema_12h - (0.6 * atr_12h),
        )
        trailing_decay = np.maximum(
            df_12h["low"].shift(1).fillna(df_12h["low"]).astype(float),
            fast_ema_12h - (0.35 * atr_12h),
        )
        trailing_state = np.where(
            daily_bullish & (symbol_range_expansion >= strong_expansion),
            "expansion",
            np.where(daily_bullish, "confirmation", "decay"),
        )
        htf_trailing_long = pd.Series(
            np.where(
                trailing_state == "expansion",
                trailing_expansion,
                np.where(trailing_state == "decay", trailing_decay, trailing_confirmation),
            ),
            index=df_12h.index,
        )

        decay_active = (
            (~supportive_long_context)
            | (~weekly_support_long)
            | (symbol_relative_strength < decay_rank_floor)
            | (symbol_score < decay_leader_score)
        ).astype(bool)

        signal_family = pd.Series("", index=df_12h.index, dtype=object)
        signal_family.loc[
            (symbol_range_expansion >= strong_expansion) & (symbol_rank_change > 0)
        ] = "leader_acceleration"
        signal_family.loc[
            signal_family.eq("") & symbol_relative_strength.ge(min_relative_strength)
        ] = "leader_persistence"

        signal_event = (
            signal_family.ne("")
            & pass_context_gate
            & symbol_pass_persistence
            & symbol_pass_expansion
            & symbol_pass_stretch
            & symbol_pass_quality
            & symbol_pass_liquidity
            & symbol_pass_score
            & symbol_pass_top_rank
            & symbol_history_ok
        )

        rotation_snapshot = pd.DataFrame(
            {
                "htf_rotation_new_candle": True,
                "signal_event_long": signal_event.astype(bool),
                "signal_family_long": signal_family,
                "htf_score_long": (symbol_score * 10.0).astype(float),
                "htf_rotation_leader_score": symbol_score.astype(float),
                "htf_rotation_momentum_score": symbol_momentum_score.astype(float),
                "htf_rotation_relative_strength": symbol_relative_strength.astype(float),
                "htf_rotation_rank_change": symbol_rank_change.astype(float),
                "htf_rotation_rank_change_rank": symbol_rank_change_rank.astype(float),
                "htf_rotation_leader_rank": symbol_leader_rank.astype(float),
                "htf_rotation_liquidity_rank": symbol_liquidity_rank.astype(float),
                "htf_rotation_volume_expansion": symbol_volume_expansion.astype(float),
                "htf_rotation_structure_overlap": symbol_structure_overlap.astype(bool),
                "htf_rotation_top_rank_pass": symbol_pass_top_rank.astype(bool),
                "htf_stop_long": htf_stop_long.astype(float),
                "htf_trailing_long": htf_trailing_long.astype(float),
                "htf_trailing_state_long": pd.Series(trailing_state, index=df_12h.index),
                "htf_decay_active_long": decay_active.astype(bool),
                "htf_decay_12h_candles": decay_12h_candles,
                "htf_context_1d": daily_snapshot["daily_label"],
                "htf_context_1w": weekly_snapshot["weekly_label"],
                "htf_daily_momentum": daily_snapshot["daily_momentum"].astype(float),
                "htf_weekly_momentum": weekly_snapshot["weekly_momentum"].astype(float),
                "htf_range_expansion_12h": symbol_range_expansion.astype(float),
                "htf_body_strength_12h": body_strength_df[symbol].reindex(df_12h.index).astype(float),
                "htf_close_position_12h": close_position_df[symbol].reindex(df_12h.index).astype(float),
                "htf_vwap_distance_ratio_12h": vwap_distance_df[symbol].reindex(df_12h.index).astype(float),
                "htf_ema_gap_ratio_12h": ema_gap_df[symbol].reindex(df_12h.index).astype(float),
                "htf_pass_structure_long": signal_family.ne("").astype(bool),
                "htf_pass_1d_context_long": pass_1d_context.astype(bool),
                "htf_pass_1w_context_long": pass_1w_context.astype(bool),
                "htf_pass_context_gate_long": pass_context_gate.astype(bool),
                "htf_pass_stretch_long": symbol_pass_stretch.astype(bool),
                "htf_pass_score_long": symbol_pass_score.astype(bool),
                "htf_pass_expansion_long": symbol_pass_expansion.astype(bool),
                "htf_pass_liquidity_long": symbol_pass_liquidity.astype(bool),
                "htf_pass_persistence_long": symbol_pass_persistence.astype(bool),
                "htf_pass_quality_long": symbol_pass_quality.astype(bool),
                "htf_entry_reason_long": signal_family.replace(
                    {
                        "leader_acceleration": "12h rotation leader acceleration",
                        "leader_persistence": "12h rotation persistent leadership",
                    }
                ),
                "htf_stop_reason_long": "12h rotation structural low with ATR buffer",
            },
            index=df_12h.index,
        )

        aligned = rotation_snapshot.reindex(execution_index, method="ffill")
        aligned["htf_rotation_new_candle"] = pd.Index(execution_index).isin(df_12h.index)
        aligned["signal_event_long"] = signal_event.reindex(execution_index, fill_value=False)
        aligned["signal_family_long"] = signal_family.reindex(execution_index, fill_value="")
        snapshots[symbol] = aligned

    return snapshots


class HTFRotationEngine:
    """Builds 12H cross-sectional leader candidates separate from structural breakout HTF."""

    MAX_SCORE = 10.0

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        getter = getattr(self.config, "get", None)
        self.raw = (
            getter("strategy", "htf_12h_rotation", default={})
            if callable(getter)
            else {}
        ) or {}
        self.enabled = bool(self.raw.get("enabled", False))
        self.base_risk_fraction = _safe_float(
            self.raw.get("base_risk_fraction", 0.0025),
            default=0.0025,
        )
        self.max_group_risk_fraction = _safe_float(
            self.raw.get("max_total_risk_fraction", 0.008),
            default=0.008,
        )
        self.max_open_positions = int(self.raw.get("max_open_positions", 2))
        self.max_hold_12h_candles = int(self.raw.get("max_hold_12h_candles", 144))
        self.long_risk_multiplier = _safe_float(
            self.raw.get("long_risk_multiplier", 1.0),
            default=1.0,
        )
        self.selection_threshold_offset = _safe_float(
            self.raw.get("selection_threshold_offset", -0.04),
            default=-0.04,
        )
        self.selection_min_threshold = _safe_float(
            self.raw.get("selection_min_threshold", 0.74),
            default=0.74,
        )
        self.selection_max_threshold = _safe_float(
            self.raw.get("selection_max_threshold", 0.90),
            default=0.90,
        )
        self.selection_bonus = _safe_float(
            self.raw.get("selection_bonus", 0.02),
            default=0.02,
        )
        self.structure_overlap_penalty = _safe_float(
            self.raw.get("structure_overlap_penalty", 0.03),
            default=0.03,
        )
        self.allow_pyramiding = bool(self.raw.get("allow_pyramiding", False))
        self.vwap_near_threshold = _safe_float(
            self.raw.get("vwap_near_threshold", 0.01),
            default=0.01,
        )
        self.vwap_moderate_threshold = _safe_float(
            self.raw.get("vwap_moderate_threshold", 0.02),
            default=0.02,
        )

    def build_candidate(
        self,
        *,
        symbol,
        timestamp,
        execution_row,
        snapshot,
        momentum_rank,
        top_symbols,
    ):
        del top_symbols
        if not self.enabled or not snapshot:
            return None
        if not _bool_value(snapshot.get("htf_rotation_new_candle")):
            return None
        if not _bool_value(snapshot.get("signal_event_long")):
            return None

        leader_score = _safe_float(snapshot.get("htf_rotation_leader_score"), default=0.0)
        raw_score = _safe_float(snapshot.get("htf_score_long"), default=leader_score * 10.0)
        signal_family = str(snapshot.get("signal_family_long", "") or "")
        if raw_score <= 0.0 or not signal_family:
            return None

        stop_price = _safe_float(snapshot.get("htf_stop_long"), default=np.nan)
        entry_price = _safe_float(execution_row.get("close"), default=np.nan)
        if not np.isfinite(stop_price) or not np.isfinite(entry_price) or stop_price >= entry_price:
            return None

        overlap_penalty = (
            self.structure_overlap_penalty
            if _bool_value(snapshot.get("htf_rotation_structure_overlap"))
            else 0.0
        )
        selection_score = clamp(
            (0.75 * leader_score)
            + (0.15 * float(momentum_rank or 0.0))
            + self.selection_bonus
            - overlap_penalty
        )

        abs_vwap_distance = abs(
            _safe_float(snapshot.get("htf_vwap_distance_ratio_12h"), default=0.0)
        )
        body_strength = _safe_float(snapshot.get("htf_body_strength_12h"), default=0.0)
        close_position = _safe_float(snapshot.get("htf_close_position_12h"), default=0.5)
        vwap_bucket = _vwap_bucket(
            abs_vwap_distance,
            self.vwap_near_threshold,
            self.vwap_moderate_threshold,
        )
        body_bucket = "strong" if body_strength >= 1.5 else "weak"
        bias = str(snapshot.get("htf_context_1d", "neutral") or "neutral")
        entry_reason = str(snapshot.get("htf_entry_reason_long", signal_family) or signal_family)
        stop_reason = str(
            snapshot.get("htf_stop_reason_long", "12h rotation structure") or "12h rotation structure"
        )

        return {
            "symbol": symbol,
            "timestamp": timestamp,
            "side": "long",
            "row": execution_row,
            "bias": bias,
            "edge_type": "htf_12h_rotation",
            "body_bucket": body_bucket,
            "vwap_bucket": vwap_bucket,
            "bucket_key_text": f"htf_12h_rotation|{bias}|{body_bucket}|{vwap_bucket}",
            "bucket_valid": True,
            "bucket_expected_return": None,
            "bucket_risk_mult": 1.0,
            "risk_mult": 1.0,
            "momentum_rank": float(momentum_rank or 0.0),
            "is_top_mover": leader_score >= 0.90,
            "score": clamp(leader_score),
            "score_bucket": score_bucket_label(clamp(leader_score)),
            "selection_score": selection_score,
            "strategy_type": "htf_12h_rotation",
            "signal_family": "htf_12h_rotation",
            "risk_group": "htf_12h_rotation",
            "group_risk_cap": self.max_group_risk_fraction,
            "max_open_positions_for_strategy": self.max_open_positions,
            "block_same_symbol_same_side": True,
            "apply_score_bucket_filters": False,
            "selection_threshold_offset": self.selection_threshold_offset,
            "selection_min_threshold": self.selection_min_threshold,
            "selection_max_threshold": self.selection_max_threshold,
            "risk_fraction_override": self.base_risk_fraction * self.long_risk_multiplier,
            "moonshot_score": clamp(leader_score),
            "range_expansion_factor": _safe_float(
                snapshot.get("htf_range_expansion_12h"),
                default=0.0,
            ),
            "feature_values": {
                "body_strength": body_strength,
                "close_position": close_position,
                "vwap_score": {"near": 0.3, "moderate": 0.6, "far": 1.0}[vwap_bucket],
                "momentum": _safe_float(
                    snapshot.get("htf_rotation_relative_strength"),
                    default=float(momentum_rank or 0.0),
                ),
            },
            "execution_profile": {
                "disable_pyramiding": not self.allow_pyramiding,
                "disable_trailing": True,
                "max_hold_candles": self.max_hold_12h_candles * 48,
                "slow_grind_max_bars": self.max_hold_12h_candles * 48,
                "slow_grind_open_r_max": -999.0,
            },
            "stop_price_override": stop_price,
            "htf_signal_family": signal_family,
            "htf_score": raw_score,
            "htf_context_1d": bias,
            "htf_context_1w": str(snapshot.get("htf_context_1w", "neutral") or "neutral"),
            "htf_entry_reason": entry_reason,
            "htf_stop_reason": stop_reason,
            "htf_trailing_state": str(snapshot.get("htf_trailing_state_long", "init") or "init"),
            "htf_decay_reason": None,
            "htf_candidate_rank": leader_score,
        }
