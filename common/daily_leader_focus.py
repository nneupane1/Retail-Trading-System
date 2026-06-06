"""Research-only helpers for prior-day leader concentration studies."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def _safe_float(value, default=0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float(default)
    if np.isnan(numeric):
        return float(default)
    return float(numeric)


def _normalize_daily_frame(frame: pd.DataFrame) -> pd.DataFrame:
    daily = frame.copy()
    if "timestamp" in daily.columns:
        daily["timestamp"] = pd.to_datetime(daily["timestamp"])
        daily = daily.set_index("timestamp")

    if not isinstance(daily.index, pd.DatetimeIndex):
        raise ValueError("Daily leader focus frames must use a DatetimeIndex or timestamp column.")

    daily = daily.sort_index()
    if "close" not in daily.columns:
        raise ValueError("Daily leader focus frames require a close column.")

    if "quote_volume" not in daily.columns:
        if "volume" not in daily.columns:
            raise ValueError("Daily leader focus frames require volume or quote_volume.")
        daily["quote_volume"] = (
            pd.to_numeric(daily["close"], errors="coerce")
            * pd.to_numeric(daily["volume"], errors="coerce")
        )

    daily["close"] = pd.to_numeric(daily["close"], errors="coerce")
    daily["quote_volume"] = pd.to_numeric(daily["quote_volume"], errors="coerce").fillna(0.0)
    daily = daily.loc[daily["close"].notna()].copy()
    daily.index = pd.to_datetime(daily.index).normalize()
    return daily


def build_daily_leader_candidates(
    daily_frames_by_symbol: dict[str, pd.DataFrame],
    *,
    lookback_days: int = 1,
    min_history_days: int = 90,
    min_daily_quote_volume: float = 0.0,
    require_positive_return: bool = False,
) -> pd.DataFrame:
    rows: list[dict] = []
    lookback_days = max(1, int(lookback_days))
    min_history_days = max(1, int(min_history_days))
    min_daily_quote_volume = float(min_daily_quote_volume or 0.0)

    for symbol, frame in dict(daily_frames_by_symbol or {}).items():
        daily = _normalize_daily_frame(frame)
        if daily.empty:
            continue

        prior_return = daily["close"].pct_change(lookback_days)
        focus_score = prior_return.shift(1)
        signal_quote_volume = daily["quote_volume"].shift(1)
        signal_close = daily["close"].shift(1)
        signal_date = daily.index.to_series().shift(1)
        history_count = np.arange(len(daily))

        for idx, trade_date in enumerate(daily.index):
            candidate = {
                "trade_date": pd.Timestamp(trade_date),
                "signal_date": signal_date.iloc[idx],
                "symbol": str(symbol).upper(),
                "focus_score": _safe_float(focus_score.iloc[idx], default=np.nan),
                "signal_return": _safe_float(prior_return.shift(1).iloc[idx], default=np.nan),
                "signal_quote_volume": _safe_float(signal_quote_volume.iloc[idx], default=0.0),
                "signal_close": _safe_float(signal_close.iloc[idx], default=np.nan),
                "history_days_available": int(history_count[idx]),
            }

            eligible = (
                pd.notna(candidate["signal_date"])
                and np.isfinite(candidate["focus_score"])
                and np.isfinite(candidate["signal_close"])
                and candidate["history_days_available"] >= min_history_days
                and candidate["signal_quote_volume"] >= min_daily_quote_volume
            )
            if require_positive_return:
                eligible = eligible and candidate["focus_score"] > 0.0

            candidate["eligible"] = bool(eligible)
            rows.append(candidate)

    if not rows:
        return pd.DataFrame(
            columns=[
                "trade_date",
                "signal_date",
                "symbol",
                "focus_score",
                "signal_return",
                "signal_quote_volume",
                "signal_close",
                "history_days_available",
                "eligible",
            ]
        )

    return pd.DataFrame(rows).sort_values(["trade_date", "symbol"]).reset_index(drop=True)


def build_daily_leader_schedule(
    daily_frames_by_symbol: dict[str, pd.DataFrame],
    *,
    top_n: int = 1,
    lookback_days: int = 1,
    min_history_days: int = 90,
    min_daily_quote_volume: float = 0.0,
    require_positive_return: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    candidates = build_daily_leader_candidates(
        daily_frames_by_symbol,
        lookback_days=lookback_days,
        min_history_days=min_history_days,
        min_daily_quote_volume=min_daily_quote_volume,
        require_positive_return=require_positive_return,
    )
    if candidates.empty:
        return candidates.copy(), candidates

    top_n = max(1, int(top_n))
    eligible = candidates.loc[candidates["eligible"]].copy()
    if eligible.empty:
        return eligible, candidates

    eligible = eligible.sort_values(
        ["trade_date", "focus_score", "signal_quote_volume", "symbol"],
        ascending=[True, False, False, True],
    )
    schedule = eligible.groupby("trade_date", group_keys=False).head(top_n).copy()
    schedule["selected_rank"] = schedule.groupby("trade_date").cumcount() + 1
    schedule["selected_weight"] = 1.0 / schedule.groupby("trade_date")["symbol"].transform("count")
    return schedule.reset_index(drop=True), candidates


def build_daily_leader_summary(
    *,
    schedule: pd.DataFrame,
    candidates: pd.DataFrame,
    top_n: int,
    lookback_days: int,
    source_symbols: list[str],
) -> dict:
    selected_days = int(schedule["trade_date"].nunique()) if not schedule.empty else 0
    focus_days = int(candidates["trade_date"].nunique()) if not candidates.empty else 0
    symbol_usage = (
        schedule["symbol"].value_counts().sort_values(ascending=False).to_dict()
        if not schedule.empty
        else {}
    )
    return {
        "mode": "research_scaffold_only",
        "source_symbol_count": len(source_symbols),
        "source_symbols": [str(symbol).upper() for symbol in source_symbols],
        "top_n": int(top_n),
        "lookback_days": int(lookback_days),
        "focus_days_considered": focus_days,
        "selected_trade_days": selected_days,
        "selected_row_count": int(len(schedule)),
        "first_trade_date": str(schedule["trade_date"].min().date()) if not schedule.empty else None,
        "last_trade_date": str(schedule["trade_date"].max().date()) if not schedule.empty else None,
        "average_selected_focus_score": _safe_float(schedule["focus_score"].mean(), default=0.0)
        if not schedule.empty
        else 0.0,
        "symbol_usage": symbol_usage,
    }


def write_daily_leader_focus_reports(
    report_root: Path,
    *,
    schedule: pd.DataFrame,
    candidates: pd.DataFrame,
    summary: dict,
) -> dict:
    report_root = Path(report_root)
    report_root.mkdir(parents=True, exist_ok=True)

    schedule_path = report_root / "leader_schedule.csv"
    candidates_path = report_root / "leader_candidates.csv"
    summary_path = report_root / "summary.json"

    schedule.to_csv(schedule_path, index=False)
    candidates.to_csv(candidates_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return {
        "leader_schedule_csv": str(schedule_path),
        "leader_candidates_csv": str(candidates_path),
        "summary_json": str(summary_path),
    }
