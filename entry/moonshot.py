"""Minimal moonshot overlays for intraday expansion and higher-timeframe persistence."""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import AppConfig
from entry.opportunity_ranking import clamp, normalize


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


def build_swing_snapshots(execution_index, df_1d, df_1w, config=None):
    """Builds higher-timeframe moonshot state aligned to the execution index."""

    config = config or AppConfig.load()
    getter = getattr(config, "get", None)
    raw = (
        getter("strategy", "moonshots", "swing", default={})
        if callable(getter)
        else {}
    ) or {}

    daily_breakout_lookback = int(raw.get("daily_breakout_lookback", 20))
    weekly_breakout_lookback = int(raw.get("weekly_breakout_lookback", 8))
    daily_momentum_lookback = int(raw.get("daily_momentum_lookback", 10))
    weekly_momentum_lookback = int(raw.get("weekly_momentum_lookback", 4))
    daily_expansion_lookback = int(raw.get("daily_expansion_lookback", 20))
    weekly_expansion_lookback = int(raw.get("weekly_expansion_lookback", 8))

    daily_prior_high = df_1d["high"].rolling(daily_breakout_lookback).max().shift(1)
    weekly_prior_high = df_1w["high"].rolling(weekly_breakout_lookback).max().shift(1)
    daily_breakout = (df_1d["close"] > daily_prior_high).fillna(False)
    weekly_breakout = (df_1w["close"] > weekly_prior_high).fillna(False)

    daily_momentum = df_1d["close"].pct_change(daily_momentum_lookback).replace(
        [np.inf, -np.inf],
        0.0,
    ).fillna(0.0)
    weekly_momentum = df_1w["close"].pct_change(weekly_momentum_lookback).replace(
        [np.inf, -np.inf],
        0.0,
    ).fillna(0.0)

    daily_range = (df_1d["high"] - df_1d["low"]).astype(float)
    weekly_range = (df_1w["high"] - df_1w["low"]).astype(float)
    daily_range_expansion = (
        daily_range / (daily_range.rolling(daily_expansion_lookback).mean() + 1e-9)
    ).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    weekly_range_expansion = (
        weekly_range / (weekly_range.rolling(weekly_expansion_lookback).mean() + 1e-9)
    ).replace([np.inf, -np.inf], 0.0).fillna(0.0)

    daily_strength = (
        0.40 * daily_breakout.astype(float)
        + 0.25 * clamp_series(normalize_series(daily_momentum, 0.0, 0.25))
        + 0.35 * clamp_series(normalize_series(daily_range_expansion, 1.0, 2.5))
    )
    weekly_strength = (
        0.45 * weekly_breakout.astype(float)
        + 0.25 * clamp_series(normalize_series(weekly_momentum, 0.0, 0.50))
        + 0.30 * clamp_series(normalize_series(weekly_range_expansion, 1.0, 2.0))
    )

    daily_snapshot = pd.DataFrame(
        {
            "daily_breakout_active": daily_breakout.astype(bool),
            "daily_momentum": daily_momentum,
            "daily_range_expansion": daily_range_expansion,
            "daily_strength": daily_strength,
        },
        index=df_1d.index,
    )
    weekly_snapshot = pd.DataFrame(
        {
            "weekly_breakout_active": weekly_breakout.astype(bool),
            "weekly_momentum": weekly_momentum,
            "weekly_range_expansion": weekly_range_expansion,
            "weekly_strength": weekly_strength,
        },
        index=df_1w.index,
    )

    aligned_daily = daily_snapshot.reindex(execution_index, method="ffill")
    aligned_weekly = weekly_snapshot.reindex(execution_index, method="ffill")
    combined = aligned_daily.join(aligned_weekly, how="outer").fillna(
        {
            "daily_breakout_active": False,
            "weekly_breakout_active": False,
            "daily_momentum": 0.0,
            "weekly_momentum": 0.0,
            "daily_range_expansion": 0.0,
            "weekly_range_expansion": 0.0,
            "daily_strength": 0.0,
            "weekly_strength": 0.0,
        }
    )
    combined["swing_active"] = (
        combined["daily_breakout_active"]
        | combined["weekly_breakout_active"]
    ) & (
        (combined["daily_momentum"] > 0.0)
        & (combined["weekly_momentum"] > 0.0)
    )
    combined["swing_strength"] = (
        0.5 * combined["daily_strength"] + 0.5 * combined["weekly_strength"]
    ).clip(lower=0.0, upper=1.0)
    return combined


def normalize_series(series, minimum, maximum):
    if maximum <= minimum:
        return pd.Series(0.0, index=series.index)
    return (series.astype(float) - float(minimum)) / (float(maximum) - float(minimum))


def clamp_series(series):
    return series.clip(lower=0.0, upper=1.0)


class MoonshotOverlay:
    """Applies layered moonshot logic on top of the existing candidate stream."""

    def __init__(self, config=None):
        self.config = config or AppConfig.load()
        getter = getattr(self.config, "get", None)
        raw = (
            getter("strategy", "moonshots", default={})
            if callable(getter)
            else {}
        ) or {}

        self.enabled = bool(raw.get("enabled", False))
        self.intraday = dict(raw.get("intraday") or {})
        self.swing = dict(raw.get("swing") or {})

    def _intraday_overlay(self, candidate):
        if not self.enabled or not bool(self.intraday.get("enabled", False)):
            return None

        score = _safe_float(candidate.get("score"), default=0.0)
        expansion = _safe_float(candidate.get("range_expansion_factor"), default=0.0)
        momentum_rank = _safe_float(candidate.get("momentum_rank"), default=0.0)
        if score < _safe_float(self.intraday.get("min_score", 0.85), default=0.85):
            return None
        if expansion < _safe_float(self.intraday.get("min_expansion", 1.4), default=1.4):
            return None
        if momentum_rank < _safe_float(self.intraday.get("min_momentum_rank", 0.75), default=0.75):
            return None

        expansion_score = normalize(
            expansion,
            _safe_float(self.intraday.get("min_expansion", 1.4), default=1.4),
            _safe_float(self.intraday.get("max_expansion_for_score", 2.5), default=2.5),
        )
        moonshot_score = clamp(
            0.55 * score
            + 0.25 * expansion_score
            + 0.20 * momentum_rank
        )
        selection_bonus = _safe_float(self.intraday.get("selection_bonus", 0.06), default=0.06)
        selection_score = clamp(max(score, moonshot_score) + selection_bonus)

        risk_fraction = _safe_float(
            self.intraday.get("base_risk_fraction", 0.0025),
            default=0.0025,
        )
        for tier in self.intraday.get("risk_by_expansion", []) or []:
            min_expansion = tier.get("min_expansion")
            if min_expansion not in (None, "") and expansion >= float(min_expansion):
                risk_fraction = _safe_float(
                    tier.get("risk_fraction", risk_fraction),
                    default=risk_fraction,
                )

        return {
            "strategy_type": "intraday_moonshot",
            "signal_family": "moonshot",
            "risk_group": "intraday_moonshot",
            "group_risk_cap": _safe_float(
                self.intraday.get("max_group_risk_fraction", 0.015),
                default=0.015,
            ),
            "risk_fraction_override": risk_fraction,
            "selection_score": selection_score,
            "moonshot_score": moonshot_score,
            "execution_profile": {
                "disable_pyramiding": True,
                "disable_trailing": bool(
                    self.intraday.get("disable_trailing", False)
                ),
                "max_hold_candles": self.intraday.get("max_hold_candles"),
                "profit_lock_trigger_r": self.intraday.get("profit_lock_trigger_r", 1.0),
                "profit_lock_stop_r": self.intraday.get("profit_lock_stop_r", 0.15),
                "trailing_activation_r": self.intraday.get("trailing_activation_r", 1.5),
                "slow_grind_max_bars": self.intraday.get("slow_grind_max_bars", 12),
                "slow_grind_open_r_max": self.intraday.get("slow_grind_open_r_max", 0.8),
            },
        }

    def _swing_overlay(self, candidate, swing_snapshot):
        if not self.enabled or not bool(self.swing.get("enabled", False)):
            return None
        if not swing_snapshot:
            return None

        score = _safe_float(candidate.get("score"), default=0.0)
        momentum_rank = _safe_float(candidate.get("momentum_rank"), default=0.0)
        min_score = _safe_float(self.swing.get("min_score", 0.82), default=0.82)
        min_rank = _safe_float(self.swing.get("min_rank", 0.75), default=0.75)
        if score < min_score or momentum_rank < min_rank:
            return None

        daily_breakout_active = _bool_value(swing_snapshot.get("daily_breakout_active"))
        weekly_breakout_active = _bool_value(swing_snapshot.get("weekly_breakout_active"))
        daily_momentum = _safe_float(swing_snapshot.get("daily_momentum"), default=0.0)
        weekly_momentum = _safe_float(swing_snapshot.get("weekly_momentum"), default=0.0)
        daily_expansion = _safe_float(
            swing_snapshot.get("daily_range_expansion"),
            default=0.0,
        )
        weekly_expansion = _safe_float(
            swing_snapshot.get("weekly_range_expansion"),
            default=0.0,
        )
        if not (daily_breakout_active or weekly_breakout_active):
            return None
        if daily_momentum <= 0.0 or weekly_momentum <= 0.0:
            return None
        if daily_expansion < _safe_float(self.swing.get("daily_expansion_threshold", 1.1), default=1.1):
            return None
        if weekly_expansion < _safe_float(self.swing.get("weekly_expansion_threshold", 1.0), default=1.0):
            return None

        strength = clamp(
            0.35 * float(daily_breakout_active)
            + 0.15 * float(weekly_breakout_active)
            + 0.15 * normalize(daily_momentum, 0.0, 0.25)
            + 0.10 * normalize(weekly_momentum, 0.0, 0.50)
            + 0.15 * normalize(daily_expansion, 1.0, 2.5)
            + 0.10 * normalize(weekly_expansion, 1.0, 2.0)
        )
        selection_bonus = _safe_float(self.swing.get("selection_bonus", 0.10), default=0.10)
        selection_score = clamp(max(score, strength) + selection_bonus)
        return {
            "strategy_type": "swing_moonshot",
            "signal_family": "swing_moonshot",
            "risk_group": "swing_moonshot",
            "group_risk_cap": _safe_float(
                self.swing.get("max_group_risk_fraction", 0.01),
                default=0.01,
            ),
            "risk_fraction_override": _safe_float(
                self.swing.get("risk_fraction", 0.0015),
                default=0.0015,
            ),
            "selection_score": selection_score,
            "moonshot_score": strength,
            "execution_profile": {
                "disable_pyramiding": True,
                "disable_trailing": bool(self.swing.get("disable_trailing", False)),
                "max_hold_candles": self.swing.get("max_hold_candles"),
                "profit_lock_trigger_r": self.swing.get("profit_lock_trigger_r", 1.5),
                "profit_lock_stop_r": self.swing.get("profit_lock_stop_r", 0.25),
                "trailing_activation_r": self.swing.get("trailing_activation_r", 2.0),
                "slow_grind_max_bars": self.swing.get("slow_grind_max_bars", 2880),
                "slow_grind_open_r_max": self.swing.get("slow_grind_open_r_max", 1.2),
            },
        }

    def apply_to_candidate(self, candidate, *, swing_snapshot=None):
        if candidate is None:
            return None

        enriched = dict(candidate)
        enriched.setdefault("selection_score", _safe_float(enriched.get("score"), default=0.0))
        enriched.setdefault("strategy_type", "core")
        enriched.setdefault("signal_family", "live_paper")
        enriched.setdefault("risk_group", "core")
        enriched.setdefault("group_risk_cap", None)
        enriched.setdefault("risk_fraction_override", None)
        enriched.setdefault("moonshot_score", None)
        enriched.setdefault("execution_profile", {})
        row = enriched.get("row")
        enriched["range_expansion_factor"] = _safe_float(
            None if row is None else row.get("range_expansion_factor"),
            default=0.0,
        )

        overlays = [
            overlay
            for overlay in (
                self._intraday_overlay(enriched),
                self._swing_overlay(enriched, swing_snapshot),
            )
            if overlay is not None
        ]
        if not overlays:
            return enriched

        best_overlay = max(
            overlays,
            key=lambda item: (
                _safe_float(item.get("selection_score"), default=0.0),
                _safe_float(item.get("moonshot_score"), default=0.0),
            ),
        )
        enriched.update(best_overlay)
        return enriched
