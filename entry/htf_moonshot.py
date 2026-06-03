"""High-timeframe 12H moonshot engine isolated from the 15m core flow."""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import AppConfig
from entry.opportunity_ranking import clamp, normalize, score_bucket_label


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


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


def build_htf_12h_snapshots(execution_index, df_12h, df_1d, df_1w, config=None):
    """Aligns isolated 12H moonshot state to the 15m execution index."""

    config = config or AppConfig.load()
    getter = getattr(config, "get", None)
    raw = (
        getter("strategy", "htf_12h_moonshot", default={})
        if callable(getter)
        else {}
    ) or {}
    ema_periods = config.require("features", "ema_periods")

    breakout_lookback = int(raw.get("breakout_lookback", 20))
    daily_breakout_lookback = int(raw.get("daily_breakout_lookback", 20))
    weekly_breakout_lookback = int(raw.get("weekly_breakout_lookback", 8))
    compression_lookback = int(raw.get("compression_lookback", 10))
    trailing_lookback = int(raw.get("trailing_lookback", 6))
    atr_stop_buffer = _safe_float(raw.get("atr_stop_buffer", 0.5), default=0.5)
    max_vwap_distance = _safe_float(raw.get("max_vwap_distance", 0.03), default=0.03)
    max_ema_distance = _safe_float(raw.get("max_ema_distance", 0.08), default=0.08)
    strong_body_min = _safe_float(raw.get("strong_body_strength", 1.6), default=1.6)
    strong_close_min = _safe_float(raw.get("strong_close_position", 0.72), default=0.72)
    supportive_expansion = _safe_float(raw.get("supportive_expansion", 1.15), default=1.15)
    strong_expansion = _safe_float(raw.get("strong_expansion", 1.50), default=1.50)
    compression_ratio_max = _safe_float(raw.get("compression_ratio_max", 0.85), default=0.85)
    pullback_tolerance = _safe_float(raw.get("pullback_ema_tolerance", 0.012), default=0.012)
    daily_momentum_lookback = int(raw.get("daily_momentum_lookback", 10))
    weekly_momentum_lookback = int(raw.get("weekly_momentum_lookback", 4))
    daily_momentum_min = _safe_float(raw.get("min_daily_momentum", 0.0), default=0.0)
    weekly_momentum_min = _safe_float(raw.get("min_weekly_momentum", -0.02), default=-0.02)
    daily_slope_lookback = int(raw.get("daily_slope_lookback", 3))
    weekly_slope_lookback = int(raw.get("weekly_slope_lookback", 2))
    slope_threshold = _safe_float(raw.get("slope_threshold", 0.0), default=0.0)
    allow_daily_or_weekly_confirmation = bool(
        raw.get("allow_daily_or_weekly_confirmation", True)
    )
    decay_12h_candles = int(raw.get("decay_12h_candles", 3))

    fast_column = f"ema{ema_periods['fast']}"
    slow_column = f"ema{ema_periods['slow']}"

    range_12h = (df_12h["high"] - df_12h["low"]).astype(float)
    avg_range_12h = range_12h.rolling(compression_lookback).mean()
    range_expansion_12h = (
        range_12h / (avg_range_12h + 1e-9)
    ).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    compression_active = (range_12h <= avg_range_12h * compression_ratio_max).fillna(False)
    recent_compression = (
        compression_active.rolling(3).max().shift(1).fillna(False).astype(bool)
    )

    prior_high_12h = df_12h["high"].rolling(breakout_lookback).max().shift(1)
    prior_low_12h = df_12h["low"].rolling(breakout_lookback).min().shift(1)
    breakout_long = (df_12h["close"] > prior_high_12h).fillna(False)
    breakout_short = (df_12h["close"] < prior_low_12h).fillna(False)
    compression_breakout_long = breakout_long & recent_compression
    compression_breakout_short = breakout_short & recent_compression

    fast_ema_12h = df_12h[fast_column].astype(float)
    slow_ema_12h = df_12h[slow_column].astype(float)
    atr_12h = df_12h["atr"].astype(float)
    body_strength = df_12h["body_strength"].astype(float)
    close_position = df_12h["close_position"].astype(float)
    vwap_distance = df_12h["vwap_distance_ratio"].astype(float).abs()
    ema_gap = df_12h["ema_gap_ratio"].astype(float).abs()

    signal_low = np.minimum(df_12h["low"].astype(float), df_12h["low"].rolling(trailing_lookback).min().shift(1).fillna(df_12h["low"].astype(float)))
    signal_high = np.maximum(df_12h["high"].astype(float), df_12h["high"].rolling(trailing_lookback).max().shift(1).fillna(df_12h["high"].astype(float)))

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
    daily_prior_high = df_1d["high"].rolling(daily_breakout_lookback).max().shift(1)
    daily_prior_low = df_1d["low"].rolling(daily_breakout_lookback).min().shift(1)
    daily_breakout_long = (df_1d["close"] > daily_prior_high).fillna(False)
    daily_breakout_short = (df_1d["close"] < daily_prior_low).fillna(False)

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
    weekly_prior_high = df_1w["high"].rolling(weekly_breakout_lookback).max().shift(1)
    weekly_prior_low = df_1w["low"].rolling(weekly_breakout_lookback).min().shift(1)
    weekly_breakout_long = (df_1w["close"] > weekly_prior_high).fillna(False)
    weekly_breakout_short = (df_1w["close"] < weekly_prior_low).fillna(False)

    daily_snapshot = pd.DataFrame(
        {
            "daily_label": daily_label,
            "daily_momentum": daily_momentum,
            "daily_slope": daily_slope,
            "daily_breakout_long": daily_breakout_long.astype(bool),
            "daily_breakout_short": daily_breakout_short.astype(bool),
        },
        index=df_1d.index,
    ).reindex(df_12h.index, method="ffill")
    weekly_snapshot = pd.DataFrame(
        {
            "weekly_label": weekly_label,
            "weekly_momentum": weekly_momentum,
            "weekly_slope": weekly_slope,
            "weekly_breakout_long": weekly_breakout_long.astype(bool),
            "weekly_breakout_short": weekly_breakout_short.astype(bool),
        },
        index=df_1w.index,
    ).reindex(df_12h.index, method="ffill")

    daily_bullish = daily_snapshot["daily_label"].eq("bullish")
    daily_bearish = daily_snapshot["daily_label"].eq("bearish")
    weekly_bullish = weekly_snapshot["weekly_label"].eq("bullish")
    weekly_bearish = weekly_snapshot["weekly_label"].eq("bearish")

    pullback_long = (
        daily_bullish
        & (df_12h["low"].astype(float) <= fast_ema_12h * (1.0 + pullback_tolerance))
        & (df_12h["close"].astype(float) > fast_ema_12h)
        & (body_strength >= strong_body_min)
        & (close_position >= strong_close_min)
    )
    pullback_short = (
        daily_bearish
        & (df_12h["high"].astype(float) >= fast_ema_12h * (1.0 - pullback_tolerance))
        & (df_12h["close"].astype(float) < fast_ema_12h)
        & (body_strength >= strong_body_min)
        & (close_position <= (1.0 - strong_close_min))
    )

    supportive_long_context = (
        daily_bullish
        | (
            allow_daily_or_weekly_confirmation
            and weekly_bullish
        )
    ) & (daily_snapshot["daily_momentum"] >= daily_momentum_min)
    supportive_short_context = (
        daily_bearish
        | (
            allow_daily_or_weekly_confirmation
            and weekly_bearish
        )
    ) & (daily_snapshot["daily_momentum"] <= -daily_momentum_min)

    weekly_support_long = (
        (weekly_snapshot["weekly_momentum"] >= weekly_momentum_min)
        & (~weekly_bearish)
    )
    weekly_support_short = (
        (weekly_snapshot["weekly_momentum"] <= -weekly_momentum_min)
        & (~weekly_bullish)
    )

    structure_long = breakout_long
    structure_short = breakout_short
    valid_pullback_long = pullback_long & supportive_long_context & weekly_support_long
    valid_pullback_short = pullback_short & supportive_short_context & weekly_support_short

    htf_score_long = (
        2.0 * structure_long.astype(float)
        + 1.0 * (close_position >= strong_close_min).astype(float)
        + 1.0 * (body_strength >= strong_body_min).astype(float)
        + 1.0 * (range_expansion_12h >= supportive_expansion).astype(float)
        + 1.0 * compression_breakout_long.astype(float)
        + 2.0 * daily_bullish.astype(float)
        + 1.0 * (daily_snapshot["daily_slope"] > slope_threshold).astype(float)
        + 1.0 * daily_snapshot["daily_breakout_long"].astype(float)
        + 1.0 * weekly_support_long.astype(float)
        + 1.0 * (
            (vwap_distance <= max_vwap_distance)
            & (ema_gap <= max_ema_distance)
        ).astype(float)
    )
    htf_score_short = (
        2.0 * structure_short.astype(float)
        + 1.0 * (close_position <= (1.0 - strong_close_min)).astype(float)
        + 1.0 * (body_strength >= strong_body_min).astype(float)
        + 1.0 * (range_expansion_12h >= supportive_expansion).astype(float)
        + 1.0 * compression_breakout_short.astype(float)
        + 2.0 * daily_bearish.astype(float)
        + 1.0 * (daily_snapshot["daily_slope"] < -slope_threshold).astype(float)
        + 1.0 * daily_snapshot["daily_breakout_short"].astype(float)
        + 1.0 * weekly_support_short.astype(float)
        + 1.0 * (
            (vwap_distance <= max_vwap_distance)
            & (ema_gap <= max_ema_distance)
        ).astype(float)
    )

    signal_family_long = pd.Series("", index=df_12h.index, dtype=object)
    signal_family_long.loc[structure_long] = "structure_breakout"
    signal_family_long.loc[compression_breakout_long] = "compression_breakout"
    signal_family_long.loc[valid_pullback_long] = "trend_pullback"

    signal_family_short = pd.Series("", index=df_12h.index, dtype=object)
    signal_family_short.loc[structure_short] = "structure_breakout"
    signal_family_short.loc[compression_breakout_short] = "compression_breakout"
    signal_family_short.loc[valid_pullback_short] = "trend_pullback"

    min_score = _safe_float(raw.get("min_score", 7.0), default=7.0)
    signal_event_long = (
        supportive_long_context
        & weekly_support_long
        & (htf_score_long >= min_score)
        & (range_expansion_12h >= supportive_expansion)
        & signal_family_long.ne("")
    )
    signal_event_short = (
        supportive_short_context
        & weekly_support_short
        & (htf_score_short >= min_score)
        & (range_expansion_12h >= supportive_expansion)
        & signal_family_short.ne("")
    )

    htf_stop_long = signal_low - (atr_12h * atr_stop_buffer)
    htf_stop_short = signal_high + (atr_12h * atr_stop_buffer)

    trailing_long_confirmation = np.maximum(
        fast_ema_12h - (0.9 * atr_12h),
        df_12h["low"].rolling(trailing_lookback).min().shift(1).fillna(df_12h["low"]).astype(float),
    )
    trailing_long_expansion = np.maximum(
        fast_ema_12h - (1.4 * atr_12h),
        slow_ema_12h - (0.6 * atr_12h),
    )
    trailing_long_decay = np.maximum(
        df_12h["low"].shift(1).fillna(df_12h["low"]).astype(float),
        fast_ema_12h - (0.35 * atr_12h),
    )

    trailing_short_confirmation = np.minimum(
        fast_ema_12h + (0.9 * atr_12h),
        df_12h["high"].rolling(trailing_lookback).max().shift(1).fillna(df_12h["high"]).astype(float),
    )
    trailing_short_expansion = np.minimum(
        fast_ema_12h + (1.4 * atr_12h),
        slow_ema_12h + (0.6 * atr_12h),
    )
    trailing_short_decay = np.minimum(
        df_12h["high"].shift(1).fillna(df_12h["high"]).astype(float),
        fast_ema_12h + (0.35 * atr_12h),
    )

    long_trailing_state = np.where(
        daily_bullish & (range_expansion_12h >= strong_expansion),
        "expansion",
        np.where(daily_bullish, "confirmation", "decay"),
    )
    short_trailing_state = np.where(
        daily_bearish & (range_expansion_12h >= strong_expansion),
        "expansion",
        np.where(daily_bearish, "confirmation", "decay"),
    )
    htf_trailing_long = pd.Series(
        np.where(
            long_trailing_state == "expansion",
            trailing_long_expansion,
            np.where(long_trailing_state == "decay", trailing_long_decay, trailing_long_confirmation),
        ),
        index=df_12h.index,
    )
    htf_trailing_short = pd.Series(
        np.where(
            short_trailing_state == "expansion",
            trailing_short_expansion,
            np.where(short_trailing_state == "decay", trailing_short_decay, trailing_short_confirmation),
        ),
        index=df_12h.index,
    )

    long_decay_active = (
        (~daily_bullish)
        & (
            (~weekly_support_long)
            | (weekly_snapshot["weekly_momentum"] < weekly_momentum_min)
        )
    )
    short_decay_active = (
        (~daily_bearish)
        & (
            (~weekly_support_short)
            | (weekly_snapshot["weekly_momentum"] > -weekly_momentum_min)
        )
    )

    htf_snapshot = pd.DataFrame(
        {
            "htf_12h_new_candle": True,
            "signal_event_long": signal_event_long.astype(bool),
            "signal_event_short": signal_event_short.astype(bool),
            "signal_family_long": signal_family_long,
            "signal_family_short": signal_family_short,
            "htf_score_long": htf_score_long.astype(float),
            "htf_score_short": htf_score_short.astype(float),
            "htf_stop_long": htf_stop_long.astype(float),
            "htf_stop_short": htf_stop_short.astype(float),
            "htf_trailing_long": htf_trailing_long.astype(float),
            "htf_trailing_short": htf_trailing_short.astype(float),
            "htf_trailing_state_long": pd.Series(long_trailing_state, index=df_12h.index),
            "htf_trailing_state_short": pd.Series(short_trailing_state, index=df_12h.index),
            "htf_decay_active_long": long_decay_active.astype(bool),
            "htf_decay_active_short": short_decay_active.astype(bool),
            "htf_decay_12h_candles": decay_12h_candles,
            "htf_context_1d": daily_snapshot["daily_label"],
            "htf_context_1w": weekly_snapshot["weekly_label"],
            "htf_daily_momentum": daily_snapshot["daily_momentum"].astype(float),
            "htf_weekly_momentum": weekly_snapshot["weekly_momentum"].astype(float),
            "htf_range_expansion_12h": range_expansion_12h.astype(float),
            "htf_body_strength_12h": body_strength.astype(float),
            "htf_close_position_12h": close_position.astype(float),
            "htf_vwap_distance_ratio_12h": vwap_distance.astype(float),
            "htf_ema_gap_ratio_12h": ema_gap.astype(float),
            "htf_pass_structure_long": signal_family_long.ne("").astype(bool),
            "htf_pass_structure_short": signal_family_short.ne("").astype(bool),
            "htf_pass_1d_context_long": supportive_long_context.astype(bool),
            "htf_pass_1d_context_short": supportive_short_context.astype(bool),
            "htf_pass_1w_context_long": weekly_support_long.astype(bool),
            "htf_pass_1w_context_short": weekly_support_short.astype(bool),
            "htf_pass_stretch_long": (
                (vwap_distance <= max_vwap_distance)
                & (ema_gap <= max_ema_distance)
            ).astype(bool),
            "htf_pass_stretch_short": (
                (vwap_distance <= max_vwap_distance)
                & (ema_gap <= max_ema_distance)
            ).astype(bool),
            "htf_pass_score_long": (htf_score_long >= min_score).astype(bool),
            "htf_pass_score_short": (htf_score_short >= min_score).astype(bool),
            "htf_pass_expansion_long": (
                range_expansion_12h >= supportive_expansion
            ).astype(bool),
            "htf_pass_expansion_short": (
                range_expansion_12h >= supportive_expansion
            ).astype(bool),
            "htf_signal_candle_low": df_12h["low"].astype(float),
            "htf_signal_candle_high": df_12h["high"].astype(float),
            "htf_entry_reason_long": signal_family_long.replace(
                {
                    "structure_breakout": "12h structure breakout",
                    "compression_breakout": "12h compression breakout",
                    "trend_pullback": "12h continuation after pullback",
                }
            ),
            "htf_entry_reason_short": signal_family_short.replace(
                {
                    "structure_breakout": "12h structure breakout",
                    "compression_breakout": "12h compression breakout",
                    "trend_pullback": "12h continuation after pullback",
                }
            ),
            "htf_stop_reason_long": "12h structural low with ATR buffer",
            "htf_stop_reason_short": "12h structural high with ATR buffer",
        },
        index=df_12h.index,
    )

    aligned = htf_snapshot.reindex(execution_index, method="ffill")
    aligned["htf_12h_new_candle"] = pd.Index(execution_index).isin(df_12h.index)

    def _event_series(series, default):
        return series.reindex(execution_index, fill_value=default)

    aligned["signal_event_long"] = _event_series(signal_event_long.astype(bool), False)
    aligned["signal_event_short"] = _event_series(signal_event_short.astype(bool), False)
    aligned["signal_family_long"] = _event_series(signal_family_long, "")
    aligned["signal_family_short"] = _event_series(signal_family_short, "")
    return aligned


class HTFMoonshotEngine:
    """Builds isolated 12H moonshot candidates without contaminating 15m core logic."""

    MAX_SCORE = 11.0

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        getter = getattr(self.config, "get", None)
        self.raw = (
            getter("strategy", "htf_12h_moonshot", default={})
            if callable(getter)
            else {}
        ) or {}
        self.enabled = bool(self.raw.get("enabled", False))
        self.min_score = _safe_float(self.raw.get("min_score", 7.0), default=7.0)
        self.base_risk_fraction = _safe_float(
            self.raw.get("base_risk_fraction", 0.0035),
            default=0.0035,
        )
        self.max_group_risk_fraction = _safe_float(
            self.raw.get("max_total_risk_fraction", 0.012),
            default=0.012,
        )
        self.max_open_positions = int(self.raw.get("max_open_positions", 2))
        self.max_hold_12h_candles = int(self.raw.get("max_hold_12h_candles", 120))
        self.selection_bonus = _safe_float(self.raw.get("selection_bonus", 0.08), default=0.08)
        self.top_mover_bonus = _safe_float(self.raw.get("top_mover_bonus", 0.03), default=0.03)
        self.long_risk_multiplier = _safe_float(
            self.raw.get("long_risk_multiplier", 1.0),
            default=1.0,
        )
        self.short_risk_multiplier = _safe_float(
            self.raw.get("short_risk_multiplier", 0.6),
            default=0.6,
        )
        self.selection_threshold_offset = _safe_float(
            self.raw.get("selection_threshold_offset", 0.0),
            default=0.0,
        )
        self.selection_min_threshold = _safe_float(
            self.raw.get("selection_min_threshold", 0.50),
            default=0.50,
        )
        self.selection_max_threshold = _safe_float(
            self.raw.get("selection_max_threshold", 0.92),
            default=0.92,
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
        if not self.enabled or not snapshot:
            return None
        if not _bool_value(snapshot.get("htf_12h_new_candle")):
            return None

        event_long = _bool_value(snapshot.get("signal_event_long"))
        event_short = _bool_value(snapshot.get("signal_event_short"))
        if not event_long and not event_short:
            return None

        side = None
        raw_score = 0.0
        if event_long and event_short:
            long_score = _safe_float(snapshot.get("htf_score_long"), default=0.0)
            short_score = _safe_float(snapshot.get("htf_score_short"), default=0.0)
            side = "long" if long_score >= short_score else "short"
            raw_score = max(long_score, short_score)
        elif event_long:
            side = "long"
            raw_score = _safe_float(snapshot.get("htf_score_long"), default=0.0)
        else:
            side = "short"
            raw_score = _safe_float(snapshot.get("htf_score_short"), default=0.0)

        if raw_score < self.min_score:
            return None

        signal_family = str(snapshot.get(f"signal_family_{side}", "") or "")
        if not signal_family:
            return None

        score_norm = clamp(raw_score / self.MAX_SCORE)
        is_top_mover = symbol in set(top_symbols or [])
        selection_score = clamp(
            0.70 * score_norm
            + 0.20 * float(momentum_rank or 0.0)
            + self.selection_bonus
            + (self.top_mover_bonus if is_top_mover else 0.0)
        )

        stop_price = _safe_float(snapshot.get(f"htf_stop_{side}"), default=np.nan)
        if not np.isfinite(stop_price):
            return None
        entry_price = _safe_float(execution_row.get("close"), default=np.nan)
        if not np.isfinite(entry_price):
            return None
        if side == "long" and stop_price >= entry_price:
            return None
        if side == "short" and stop_price <= entry_price:
            return None

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
        daily_context = str(snapshot.get("htf_context_1d", "neutral") or "neutral")
        entry_reason = str(snapshot.get(f"htf_entry_reason_{side}", signal_family) or signal_family)
        stop_reason = str(snapshot.get(f"htf_stop_reason_{side}", "12h structure") or "12h structure")
        risk_fraction_override = self.base_risk_fraction * (
            self.short_risk_multiplier if side == "short" else self.long_risk_multiplier
        )

        return {
            "symbol": symbol,
            "timestamp": timestamp,
            "side": side,
            "row": execution_row,
            "bias": daily_context,
            "edge_type": "htf_12h_moonshot",
            "body_bucket": body_bucket,
            "vwap_bucket": vwap_bucket,
            "bucket_key_text": f"htf_12h_moonshot|{daily_context}|{body_bucket}|{vwap_bucket}",
            "bucket_valid": True,
            "bucket_expected_return": None,
            "bucket_risk_mult": 1.0,
            "risk_mult": 1.0,
            "momentum_rank": float(momentum_rank or 0.0),
            "is_top_mover": is_top_mover,
            "score": score_norm,
            "score_bucket": score_bucket_label(score_norm),
            "selection_score": selection_score,
            "strategy_type": "htf_12h_moonshot",
            "signal_family": "htf_12h_moonshot",
            "risk_group": "htf_12h_moonshot",
            "group_risk_cap": self.max_group_risk_fraction,
            "max_open_positions_for_strategy": self.max_open_positions,
            "block_same_symbol_same_side": True,
            "apply_score_bucket_filters": False,
            "selection_threshold_offset": self.selection_threshold_offset,
            "selection_min_threshold": self.selection_min_threshold,
            "selection_max_threshold": self.selection_max_threshold,
            "risk_fraction_override": risk_fraction_override,
            "moonshot_score": score_norm,
            "range_expansion_factor": _safe_float(
                snapshot.get("htf_range_expansion_12h"),
                default=0.0,
            ),
            "feature_values": {
                "body_strength": body_strength,
                "close_position": close_position,
                "vwap_score": {"near": 0.3, "moderate": 0.6, "far": 1.0}[vwap_bucket],
                "momentum": float(momentum_rank or 0.0),
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
            "htf_context_1d": daily_context,
            "htf_context_1w": str(snapshot.get("htf_context_1w", "neutral") or "neutral"),
            "htf_entry_reason": entry_reason,
            "htf_stop_reason": stop_reason,
            "htf_trailing_state": str(snapshot.get(f"htf_trailing_state_{side}", "init") or "init"),
            "htf_decay_reason": None,
            "htf_candidate_rank": selection_score,
        }
