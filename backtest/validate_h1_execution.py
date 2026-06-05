"""Checkpoint-safe candidate and execution validation for the dormant 1H sleeve."""

from __future__ import annotations

import json
import os
import traceback
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.portfolio_runner import _discover_portfolio_symbols, _load_full_history
from config import AppConfig
from data.resampler import TimeframeBuilder
from entry.h1_execution import H1ExecutionEngine, build_h1_execution_snapshots
from features.feature_pipeline import compute_features


def _clone_config(base: AppConfig) -> AppConfig:
    return AppConfig(
        data=deepcopy(base.data),
        config_path=base.config_path,
        root_dir=base.root_dir,
    )


def _safe_float(value, default=0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float(default)
    if np.isnan(numeric):
        return float(default)
    return float(numeric)


@contextmanager
def _suppress_pipeline_output():
    with open(os.devnull, "w", encoding="utf-8", errors="ignore") as sink:
        with redirect_stdout(sink), redirect_stderr(sink):
            yield


def _report_root(base: AppConfig) -> Path:
    return Path(base.require("backtest", "output_dir")) / "h1_execution_validation_current"


def _progress_path(report_root: Path) -> Path:
    return report_root / "progress.json"


def _load_progress(report_root: Path) -> dict:
    path = _progress_path(report_root)
    if not path.exists():
        return {"symbols": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"symbols": {}}


def _save_progress(report_root: Path, payload: dict) -> None:
    _progress_path(report_root).write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )


def _build_h1_research_timeframes(df_1m: pd.DataFrame, config: AppConfig):
    builder = TimeframeBuilder(config=config)
    execution_rule = config.require("timeframes", "execution", "rule")

    with _suppress_pipeline_output():
        df_15m = builder.resample(df_1m, execution_rule)
        df_1h = builder.resample(df_1m, "1h")
        df_6h = builder.resample(df_1m, "6h")
        df_12h = builder.resample(df_1m, "12h")

        df_15m = compute_features(df_15m, config=config)
        df_1h = compute_features(df_1h, config=config)
        df_6h = compute_features(df_6h, config=config)
        df_12h = compute_features(df_12h, config=config)

    return df_15m, df_1h, df_6h, df_12h


def _find_exit_bar(
    future_rows: pd.DataFrame,
    *,
    stop_price: float,
    side: str,
    max_hold_bars: int,
) -> tuple[str, pd.Timestamp | None, pd.Series | None]:
    sliced = future_rows.head(max_hold_bars)
    if sliced.empty:
        return "no_future_bars", None, None

    for timestamp, bar in sliced.iterrows():
        low = _safe_float(bar.get("low"), default=np.nan)
        high = _safe_float(bar.get("high"), default=np.nan)
        if side == "long":
            if np.isfinite(low) and low <= stop_price:
                return "stop", timestamp, bar
        else:
            if np.isfinite(high) and high >= stop_price:
                return "stop", timestamp, bar

    exit_ts = sliced.index[-1]
    return "time_exit", exit_ts, sliced.iloc[-1]


def _simulate_h1_trade(
    *,
    symbol: str,
    side: str,
    timestamp: pd.Timestamp,
    execution_row: pd.Series,
    snapshot: dict,
    execution_frame: pd.DataFrame,
    engine: H1ExecutionEngine,
) -> dict | None:
    entry_price = _safe_float(execution_row.get("close"), default=np.nan)
    stop_price = _safe_float(snapshot.get(f"h1_stop_{side}"), default=np.nan)
    if not np.isfinite(entry_price) or not np.isfinite(stop_price):
        return None
    if side == "long" and stop_price >= entry_price:
        return None
    if side == "short" and stop_price <= entry_price:
        return None

    risk_per_unit = abs(entry_price - stop_price)
    if risk_per_unit <= 0.0:
        return None

    future_rows = execution_frame.loc[execution_frame.index > timestamp]
    max_hold_bars = int(engine.max_hold_1h_candles) * 4
    exit_reason, exit_timestamp, exit_row = _find_exit_bar(
        future_rows,
        stop_price=stop_price,
        side=side,
        max_hold_bars=max_hold_bars,
    )
    if exit_row is None or exit_timestamp is None:
        return None

    if exit_reason == "stop":
        exit_price = stop_price
        realized_r = -1.0
    else:
        exit_price = _safe_float(exit_row.get("close"), default=entry_price)
        if side == "long":
            realized_r = (exit_price - entry_price) / risk_per_unit
        else:
            realized_r = (entry_price - exit_price) / risk_per_unit

    sliced = future_rows.head(max_hold_bars)
    max_high = _safe_float(sliced["high"].max(), default=entry_price) if not sliced.empty else entry_price
    min_low = _safe_float(sliced["low"].min(), default=entry_price) if not sliced.empty else entry_price
    if side == "long":
        mfe_r = (max_high - entry_price) / risk_per_unit
        mae_r = (min_low - entry_price) / risk_per_unit
        hit_1r = bool((sliced["high"] >= entry_price + risk_per_unit).any()) if not sliced.empty else False
        hit_2r = bool((sliced["high"] >= entry_price + (2.0 * risk_per_unit)).any()) if not sliced.empty else False
    else:
        mfe_r = (entry_price - min_low) / risk_per_unit
        mae_r = (entry_price - max_high) / risk_per_unit
        hit_1r = bool((sliced["low"] <= entry_price - risk_per_unit).any()) if not sliced.empty else False
        hit_2r = bool((sliced["low"] <= entry_price - (2.0 * risk_per_unit)).any()) if not sliced.empty else False

    bars_held = int(execution_frame.index.get_loc(exit_timestamp) - execution_frame.index.get_loc(timestamp))
    return {
        "symbol": str(symbol).upper(),
        "timestamp": str(pd.Timestamp(timestamp)),
        "year": int(pd.Timestamp(timestamp).year),
        "side": side,
        "signal_family": str(snapshot.get(f"signal_family_{side}") or "h1_structure_continuation"),
        "entry_price": entry_price,
        "stop_price": stop_price,
        "risk_per_unit": risk_per_unit,
        "exit_price": exit_price,
        "exit_timestamp": str(pd.Timestamp(exit_timestamp)),
        "exit_reason": exit_reason,
        "realized_R": float(realized_r),
        "mfe_R": float(mfe_r),
        "mae_R": float(mae_r),
        "hit_1R": bool(hit_1r),
        "hit_2R": bool(hit_2r),
        "bars_held": bars_held,
        "hold_hours": float(bars_held) / 4.0,
        "h1_score": _safe_float(snapshot.get(f"h1_score_{side}"), default=0.0),
        "h1_body_strength": _safe_float(snapshot.get("h1_body_strength"), default=0.0),
        "h1_close_position": _safe_float(snapshot.get("h1_close_position"), default=0.0),
        "h1_range_expansion": _safe_float(snapshot.get("h1_range_expansion"), default=0.0),
        "h1_context_6h": str(snapshot.get("h1_context_6h") or "neutral"),
        "h1_context_12h": str(snapshot.get("h1_context_12h") or "neutral"),
    }


def _validate_symbol(
    *,
    symbol: str,
    recent_start: str,
    recent_end: str,
    config: AppConfig,
    engine: H1ExecutionEngine,
) -> dict:
    df_1m, source_path = _load_full_history(
        symbol,
        config.require("binance", "default_interval"),
        config,
    )
    df_15m, df_1h, df_6h, df_12h = _build_h1_research_timeframes(df_1m, config=config)
    snapshots = build_h1_execution_snapshots(
        df_15m.index,
        df_1h,
        df_6h,
        df_12h,
        config=config,
    )

    recent_start_ts = pd.Timestamp(recent_start)
    recent_end_ts = pd.Timestamp(recent_end) + pd.Timedelta(days=1)
    eligible_index = df_15m.index[(df_15m.index >= recent_start_ts) & (df_15m.index < recent_end_ts)]
    recent_snapshots = snapshots.reindex(eligible_index)
    recent_exec = df_15m.reindex(eligible_index)
    h1_steps = recent_snapshots.loc[
        recent_snapshots["h1_new_candle"].fillna(False).astype(bool)
    ].copy()

    score_floor = float(engine.raw.get("min_score", 0.72))
    funnel = {
        "symbol": str(symbol).upper(),
        "source_path": str(source_path),
        "raw_1h_events": int(len(h1_steps)),
        "passed_structure_long": int(h1_steps["h1_pass_structure_long"].fillna(False).astype(bool).sum()),
        "passed_structure_short": int(h1_steps["h1_pass_structure_short"].fillna(False).astype(bool).sum()),
        "passed_shape_long": int(h1_steps["h1_pass_shape_long"].fillna(False).astype(bool).sum()),
        "passed_shape_short": int(h1_steps["h1_pass_shape_short"].fillna(False).astype(bool).sum()),
        "passed_6h_context_long": int(h1_steps["h1_pass_6h_context_long"].fillna(False).astype(bool).sum()),
        "passed_6h_context_short": int(h1_steps["h1_pass_6h_context_short"].fillna(False).astype(bool).sum()),
        "passed_12h_context_long": int(h1_steps["h1_pass_12h_context_long"].fillna(False).astype(bool).sum()),
        "passed_12h_context_short": int(h1_steps["h1_pass_12h_context_short"].fillna(False).astype(bool).sum()),
        "passed_score_long": int(
            (pd.to_numeric(h1_steps["h1_score_long"], errors="coerce").fillna(0.0) >= score_floor).sum()
        ),
        "passed_score_short": int(
            (pd.to_numeric(h1_steps["h1_score_short"], errors="coerce").fillna(0.0) >= score_floor).sum()
        ),
        "opened_long_candidates": int(h1_steps["signal_event_long"].fillna(False).astype(bool).sum()),
        "opened_short_candidates": int(h1_steps["signal_event_short"].fillna(False).astype(bool).sum()),
    }

    event_rows = []
    for timestamp, snapshot_row in h1_steps.iterrows():
        snapshot = snapshot_row.to_dict()
        execution_row = recent_exec.loc[timestamp]
        for side in ("long", "short"):
            if not bool(snapshot.get(f"signal_event_{side}")):
                continue
            candidate = engine.build_candidate(
                symbol=symbol,
                timestamp=timestamp,
                execution_row=execution_row,
                snapshot=snapshot,
                momentum_rank=0.0,
                top_symbols=[],
            )
            if candidate is None:
                continue
            trade_row = _simulate_h1_trade(
                symbol=symbol,
                side=side,
                timestamp=timestamp,
                execution_row=execution_row,
                snapshot=snapshot,
                execution_frame=df_15m,
                engine=engine,
            )
            if trade_row is not None:
                event_rows.append(trade_row)

    return {
        "funnel": funnel,
        "events": event_rows,
    }


def _events_metrics(events_df: pd.DataFrame) -> dict:
    if events_df.empty:
        return {
            "trade_count": 0,
            "avg_R": 0.0,
            "median_R": 0.0,
            "max_R": 0.0,
            "win_rate": 0.0,
            "hit_1R_rate": 0.0,
            "hit_2R_rate": 0.0,
            "avg_mfe_R": 0.0,
            "avg_mae_R": 0.0,
            "avg_hold_hours": 0.0,
            "median_hold_hours": 0.0,
            "profit_factor": 0.0,
            "exit_reasons": {},
            "long_short_split": {},
        }

    realized = pd.to_numeric(events_df["realized_R"], errors="coerce").fillna(0.0)
    pos = float(realized[realized > 0].sum())
    neg = float(realized[realized < 0].sum())
    pf = float("inf") if neg == 0.0 and pos > 0 else (pos / abs(neg) if neg != 0.0 else 0.0)
    exit_reasons = (
        events_df["exit_reason"].fillna("unknown").astype(str).value_counts().to_dict()
        if "exit_reason" in events_df.columns
        else {}
    )
    side_split = (
        events_df["side"].fillna("unknown").astype(str).value_counts().to_dict()
        if "side" in events_df.columns
        else {}
    )
    return {
        "trade_count": int(len(events_df)),
        "net_R": float(realized.sum()),
        "avg_R": float(realized.mean()),
        "median_R": float(realized.median()),
        "max_R": float(realized.max()),
        "win_rate": float((realized > 0).mean()),
        "hit_1R_rate": float(events_df["hit_1R"].fillna(False).mean()),
        "hit_2R_rate": float(events_df["hit_2R"].fillna(False).mean()),
        "avg_mfe_R": float(pd.to_numeric(events_df["mfe_R"], errors="coerce").mean()),
        "avg_mae_R": float(pd.to_numeric(events_df["mae_R"], errors="coerce").mean()),
        "avg_hold_hours": float(pd.to_numeric(events_df["hold_hours"], errors="coerce").mean()),
        "median_hold_hours": float(pd.to_numeric(events_df["hold_hours"], errors="coerce").median()),
        "profit_factor": float(pf),
        "exit_reasons": {str(k): int(v) for k, v in exit_reasons.items()},
        "long_short_split": {str(k): int(v) for k, v in side_split.items()},
    }


def _write_reports(report_root: Path, funnel_rows: list[dict], event_rows: list[dict], symbols: list[str]) -> dict:
    funnel_df = pd.DataFrame(funnel_rows).sort_values("symbol").reset_index(drop=True)
    events_df = (
        pd.DataFrame(event_rows).sort_values(["timestamp", "symbol", "side"]).reset_index(drop=True)
        if event_rows
        else pd.DataFrame()
    )
    summary = {
        "report_root": str(report_root),
        "symbols": [str(symbol).upper() for symbol in symbols],
        "funnel_totals": {
            key: int(funnel_df[key].sum())
            for key in [
                "raw_1h_events",
                "passed_structure_long",
                "passed_structure_short",
                "passed_shape_long",
                "passed_shape_short",
                "passed_6h_context_long",
                "passed_6h_context_short",
                "passed_12h_context_long",
                "passed_12h_context_short",
                "passed_score_long",
                "passed_score_short",
                "opened_long_candidates",
                "opened_short_candidates",
            ]
            if key in funnel_df.columns
        },
        "metrics": _events_metrics(events_df),
    }

    funnel_path = report_root / "h1_funnel_by_symbol.csv"
    funnel_df.to_csv(funnel_path, index=False)
    summary["funnel_by_symbol_report"] = str(funnel_path)

    events_path = report_root / "h1_event_trades.csv"
    if not events_df.empty:
        events_df.to_csv(events_path, index=False)
        summary["event_trade_report"] = str(events_path)

        by_symbol = (
            events_df.groupby("symbol")
            .agg(
                trade_count=("realized_R", "size"),
                net_R=("realized_R", "sum"),
                avg_R=("realized_R", "mean"),
                median_R=("realized_R", "median"),
                max_R=("realized_R", "max"),
                win_rate=("realized_R", lambda s: float((pd.to_numeric(s, errors="coerce").fillna(0.0) > 0).mean())),
                hit_1R_rate=("hit_1R", "mean"),
                hit_2R_rate=("hit_2R", "mean"),
            )
            .reset_index()
            .sort_values(["net_R", "avg_R"], ascending=[False, False])
        )
        by_symbol_path = report_root / "h1_event_summary_by_symbol.csv"
        by_symbol.to_csv(by_symbol_path, index=False)
        summary["event_summary_by_symbol_report"] = str(by_symbol_path)

        by_year = (
            events_df.groupby("year")
            .agg(
                trade_count=("realized_R", "size"),
                net_R=("realized_R", "sum"),
                avg_R=("realized_R", "mean"),
                win_rate=("realized_R", lambda s: float((pd.to_numeric(s, errors="coerce").fillna(0.0) > 0).mean())),
                hit_1R_rate=("hit_1R", "mean"),
                hit_2R_rate=("hit_2R", "mean"),
            )
            .reset_index()
            .sort_values("year")
        )
        by_year_path = report_root / "h1_event_summary_by_year.csv"
        by_year.to_csv(by_year_path, index=False)
        summary["event_summary_by_year_report"] = str(by_year_path)

        by_side = (
            events_df.groupby("side")
            .agg(
                trade_count=("realized_R", "size"),
                net_R=("realized_R", "sum"),
                avg_R=("realized_R", "mean"),
                median_R=("realized_R", "median"),
                win_rate=("realized_R", lambda s: float((pd.to_numeric(s, errors="coerce").fillna(0.0) > 0).mean())),
                hit_1R_rate=("hit_1R", "mean"),
                hit_2R_rate=("hit_2R", "mean"),
            )
            .reset_index()
            .sort_values("side")
        )
        by_side_path = report_root / "h1_event_summary_by_side.csv"
        by_side.to_csv(by_side_path, index=False)
        summary["event_summary_by_side_report"] = str(by_side_path)

    summary_path = report_root / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def main():
    base = AppConfig.load()
    report_root = _report_root(base)
    report_root.mkdir(parents=True, exist_ok=True)

    config = _clone_config(base)
    config.data.setdefault("strategy", {}).setdefault("h1_execution", {})
    config.data["strategy"]["h1_execution"]["enabled"] = True
    engine = H1ExecutionEngine(config=config)

    recent_start = "2025-01-01"
    recent_end = str(config.require("history", "end_date"))
    symbols = _discover_portfolio_symbols(config)
    progress = _load_progress(report_root)
    progress["symbols_expected"] = [str(symbol).upper() for symbol in symbols]
    progress["recent_start"] = recent_start
    progress["recent_end"] = recent_end

    for symbol in symbols:
        symbol_key = str(symbol).upper()
        entry = progress.setdefault("symbols", {}).get(symbol_key, {})
        if entry.get("completed"):
            continue
        try:
            payload = _validate_symbol(
                symbol=symbol_key,
                recent_start=recent_start,
                recent_end=recent_end,
                config=config,
                engine=engine,
            )
            progress["symbols"][symbol_key] = {
                "completed": True,
                "funnel": payload["funnel"],
                "events": payload["events"],
            }
        except Exception as exc:
            progress["symbols"][symbol_key] = {
                "completed": False,
                "error": str(exc),
                "traceback": traceback.format_exc(limit=12),
            }
            _save_progress(report_root, progress)
            raise
        _save_progress(report_root, progress)

    funnel_rows = []
    event_rows = []
    for symbol in symbols:
        row = progress.get("symbols", {}).get(str(symbol).upper(), {})
        funnel = row.get("funnel")
        if funnel:
            funnel_rows.append(funnel)
        event_rows.extend(row.get("events", []))

    _write_reports(report_root, funnel_rows, event_rows, symbols)


if __name__ == "__main__":
    main()
