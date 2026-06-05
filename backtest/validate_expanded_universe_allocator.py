"""Checkpoint-safe validation for the expanded liquid Binance universe."""

from __future__ import annotations

import json
import os
import traceback
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.portfolio_runner import (
    _build_strategy_timeframes,
    _load_full_history,
)
from backtest.validate_htf_12h import (
    _clone_config,
    _load_progress,
    _run_or_resume_scenario,
    _safe_pct,
    _save_progress,
    _top5_contribution_percent,
)
from common.binance_universe import (
    discover_binance_candidate_universe,
    get_discovery_settings,
    write_discovery_reports,
)
from common.universe import get_named_universe
from config import AppConfig
from entry.htf_moonshot import build_htf_12h_snapshots
from entry.htf_rotation import build_htf_rotation_snapshots_by_symbol


@contextmanager
def _suppress_feature_generation_output():
    with open(os.devnull, "w", encoding="utf-8", errors="ignore") as sink:
        with redirect_stdout(sink), redirect_stderr(sink):
            yield


def _quality_progress_path(report_root: Path) -> Path:
    return report_root / "quality_progress.json"


def _load_quality_progress(report_root: Path) -> dict:
    path = _quality_progress_path(report_root)
    if not path.exists():
        return {"symbols": {}}
    try:
        with path.open(encoding="utf-8") as file_handle:
            payload = json.load(file_handle)
    except Exception:
        return {"symbols": {}}
    payload.setdefault("symbols", {})
    return payload


def _save_quality_progress(report_root: Path, payload: dict) -> None:
    with _quality_progress_path(report_root).open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2, default=str)


def _safe_float(value, default=0.0):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float(default)
    if pd.isna(numeric):
        return float(default)
    return numeric


def _quality_thresholds(config):
    getter = getattr(config, "get", None)

    def read(name, default):
        if callable(getter):
            return getter("universe", "quality", name, default=default)
        return default

    return {
        "max_missing_1m_ratio": float(read("max_missing_1m_ratio", 0.02) or 0.02),
        "max_missing_15m_ratio": float(read("max_missing_15m_ratio", 0.05) or 0.05),
        "max_duplicate_1m_ratio": float(read("max_duplicate_1m_ratio", 0.001) or 0.001),
        "max_ohlcv_nan_ratio": float(read("max_ohlcv_nan_ratio", 0.001) or 0.001),
        "min_recent_execution_rows": int(read("min_recent_execution_rows", 500) or 500),
        "min_recent_12h_rows": int(read("min_recent_12h_rows", 40) or 40),
        "min_recent_1d_rows": int(read("min_recent_1d_rows", 30) or 30),
        "min_recent_median_daily_quote_volume": float(
            read("min_recent_median_daily_quote_volume", 5_000_000.0) or 5_000_000.0
        ),
        "min_recent_min_daily_quote_volume": float(
            read("min_recent_min_daily_quote_volume", 750_000.0) or 750_000.0
        ),
        "max_recent_spread_proxy": float(read("max_recent_spread_proxy", 0.08) or 0.08),
        "min_daily_bar_coverage_ratio_for_liquidity_stats": float(
            read("min_daily_bar_coverage_ratio_for_liquidity_stats", 0.95) or 0.95
        ),
        "max_recent_terminal_gap_minutes": float(
            read("max_recent_terminal_gap_minutes", 1440.0) or 1440.0
        ),
    }


def _resolve_candidate_symbols(base_config: AppConfig, report_root: Path) -> tuple[list[str], dict]:
    discovery_settings = get_discovery_settings(base_config)
    if discovery_settings["enabled"]:
        payload = discover_binance_candidate_universe(base_config)
        discovery_report = write_discovery_reports(report_root, payload)
        return list(payload["candidate_symbols"]), {
            "source": "binance_discovery",
            "summary": payload.get("summary", {}),
            "report": discovery_report,
        }

    universe_name = "expanded_liquid_28"
    symbols = list(get_named_universe(base_config, universe_name))
    return symbols, {
        "source": f"named:{universe_name}",
        "summary": {
            "candidate_symbol_count": len(symbols),
            "candidate_symbols": list(symbols),
        },
        "report": None,
    }


def _curation_thresholds(config):
    getter = getattr(config, "get", None)

    def read(name, default):
        if callable(getter):
            return getter("universe", "curation", name, default=default)
        return default

    return {
        "min_keep_trade_count": int(read("min_keep_trade_count", 75) or 75),
        "min_keep_net_pnl": float(read("min_keep_net_pnl", 0.0) or 0.0),
        "min_keep_avg_R": float(read("min_keep_avg_R", 0.0) or 0.0),
        "min_keep_profit_factor": float(read("min_keep_profit_factor", 1.0) or 1.0),
        "min_review_trade_count": int(read("min_review_trade_count", 40) or 40),
    }


def _read_raw_history_csv(source_path: Path) -> pd.DataFrame:
    frame = pd.read_csv(source_path, parse_dates=["timestamp"])
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    return frame


def _expected_bar_count(index: pd.Index, frequency: str) -> int:
    if len(index) <= 1:
        return len(index)
    expected = pd.date_range(index.min(), index.max(), freq=frequency)
    return int(len(expected))


def _index_gap_metrics(index: pd.Index, frequency: str) -> tuple[int, float]:
    if len(index) <= 1:
        return 0, 0.0
    expected = _expected_bar_count(index, frequency)
    missing = max(0, expected - int(len(index)))
    return missing, _safe_pct(missing, expected)


def _daily_quote_volume_stats(
    frame: pd.DataFrame,
    *,
    min_bar_coverage_ratio: float = 0.95,
    bars_per_day: int = 1440,
) -> tuple[float, float, int]:
    if frame.empty:
        return 0.0, 0.0, 0
    working = frame.copy()
    working["quote_volume_proxy"] = (
        pd.to_numeric(working["close"], errors="coerce").fillna(0.0)
        * pd.to_numeric(working["volume"], errors="coerce").fillna(0.0)
    )
    daily = working.groupby(working.index.floor("D")).agg(
        quote_volume_proxy=("quote_volume_proxy", "sum"),
        bar_count=("quote_volume_proxy", "size"),
    )
    if daily.empty:
        return 0.0, 0.0, 0
    min_bars = max(1, int(bars_per_day * float(min_bar_coverage_ratio)))
    full_days = daily.loc[daily["bar_count"] >= min_bars, "quote_volume_proxy"]
    if full_days.empty:
        return 0.0, 0.0, 0
    return float(full_days.min()), float(full_days.median()), int(len(full_days))


def _spread_proxy(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 0.0
    working = frame.copy()
    proxy = (
        (
            pd.to_numeric(working["high"], errors="coerce")
            - pd.to_numeric(working["low"], errors="coerce")
        )
        / pd.to_numeric(working["close"], errors="coerce").replace(0.0, np.nan)
    )
    proxy = proxy.replace([np.inf, -np.inf], np.nan).dropna()
    return float(proxy.mean()) if not proxy.empty else 0.0


def _nan_ratio(frame: pd.DataFrame, columns: list[str]) -> float:
    if frame.empty:
        return 1.0
    subset = frame.loc[:, columns].copy()
    total = float(subset.shape[0] * subset.shape[1])
    if total <= 0:
        return 1.0
    return float(subset.isna().sum().sum()) / total


def _recent_slice(frame: pd.DataFrame, start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return frame.loc[(frame.index >= start_ts) & (frame.index < end_ts)].copy()


def _terminal_gap_minutes(last_timestamp, expected_terminal_ts: pd.Timestamp) -> float:
    if last_timestamp is None or pd.isna(last_timestamp):
        return float("inf")
    gap = (expected_terminal_ts - pd.Timestamp(last_timestamp)).total_seconds() / 60.0
    return float(max(0.0, gap))


def _first_true_timestamp(frame: pd.DataFrame, column: str):
    if frame.empty or column not in frame.columns:
        return None
    mask = frame[column].fillna(False).astype(bool)
    if not mask.any():
        return None
    return frame.index[mask.argmax()]


def _serialize_timestamp(value):
    if value is None:
        return None
    try:
        return str(pd.Timestamp(value))
    except Exception:
        return None


def _validate_symbol_quality(
    symbol: str,
    *,
    base_config: AppConfig,
    recent_start: str,
    recent_end: str,
    thresholds: dict,
) -> dict:
    row = {
        "symbol": str(symbol).upper(),
        "accepted": False,
        "eligible_core": False,
        "eligible_htf_moonshot": False,
        "eligible_htf_rotation": False,
        "reasons": [],
    }

    try:
        df_1m, source_path = _load_full_history(symbol, base_config.require("binance", "default_interval"), base_config)
    except FileNotFoundError as exc:
        row["reasons"] = ["missing_local_history"]
        row["reject_reason"] = "missing_local_history"
        row["error_stage"] = "history_load"
        row["source_path"] = None
        row["error"] = str(exc)
        return row
    except Exception as exc:
        row["reasons"] = ["history_load_failed"]
        row["reject_reason"] = "history_load_failed"
        row["error_stage"] = "history_load"
        row["source_path"] = None
        row["error"] = str(exc)
        row["traceback"] = traceback.format_exc(limit=8)
        return row

    source_path = Path(source_path)
    raw_frame = _read_raw_history_csv(source_path)
    raw_frame = raw_frame.loc[
        (raw_frame["timestamp"] >= pd.Timestamp(base_config.require("history", "start_date")))
        & (
            raw_frame["timestamp"]
            < (pd.Timestamp(base_config.require("history", "end_date")) + pd.Timedelta(days=1))
        )
    ].copy()
    duplicate_timestamp_count = int(raw_frame["timestamp"].duplicated().sum())

    row["source_path"] = str(source_path)
    row["first_available_timestamp"] = _serialize_timestamp(raw_frame["timestamp"].min() if not raw_frame.empty else None)
    row["last_available_timestamp"] = _serialize_timestamp(raw_frame["timestamp"].max() if not raw_frame.empty else None)
    row["total_1m_candles"] = int(len(raw_frame))
    row["duplicate_timestamp_count"] = duplicate_timestamp_count
    row["duplicate_1m_ratio"] = _safe_pct(duplicate_timestamp_count, max(len(raw_frame), 1))

    clean_1m = df_1m.copy()
    clean_1m = clean_1m.sort_index()
    missing_1m_count, missing_1m_ratio = _index_gap_metrics(clean_1m.index, "1min")
    row["missing_1m_count"] = missing_1m_count
    row["missing_1m_ratio"] = missing_1m_ratio
    row["ohlcv_nan_ratio"] = _nan_ratio(clean_1m.reset_index(drop=True), ["open", "high", "low", "close", "volume"])

    recent_start_ts = pd.Timestamp(recent_start)
    recent_end_ts = pd.Timestamp(recent_end) + pd.Timedelta(days=1)
    recent_1m = _recent_slice(clean_1m, recent_start_ts, recent_end_ts)
    row["recent_first_timestamp"] = _serialize_timestamp(recent_1m.index.min() if not recent_1m.empty else None)
    row["recent_last_timestamp"] = _serialize_timestamp(recent_1m.index.max() if not recent_1m.empty else None)
    row["recent_1m_candles"] = int(len(recent_1m))
    recent_missing_1m_count, recent_missing_1m_ratio = _index_gap_metrics(recent_1m.index, "1min")
    row["recent_missing_1m_count"] = recent_missing_1m_count
    row["recent_missing_1m_ratio"] = recent_missing_1m_ratio
    row["recent_ohlcv_nan_ratio"] = _nan_ratio(
        recent_1m.reset_index(drop=True),
        ["open", "high", "low", "close", "volume"],
    )
    row["avg_spread_proxy"] = _spread_proxy(clean_1m.reset_index(drop=True))
    row["recent_avg_spread_proxy"] = _spread_proxy(recent_1m.reset_index(drop=True))
    min_daily_quote, median_daily_quote, full_daily_count = _daily_quote_volume_stats(
        clean_1m,
        min_bar_coverage_ratio=thresholds["min_daily_bar_coverage_ratio_for_liquidity_stats"],
    )
    recent_min_daily_quote, recent_median_daily_quote, recent_full_daily_count = _daily_quote_volume_stats(
        recent_1m,
        min_bar_coverage_ratio=thresholds["min_daily_bar_coverage_ratio_for_liquidity_stats"],
    )
    row["min_daily_quote_volume_proxy"] = min_daily_quote
    row["median_daily_quote_volume_proxy"] = median_daily_quote
    row["full_daily_quote_volume_day_count"] = full_daily_count
    row["recent_min_daily_quote_volume_proxy"] = recent_min_daily_quote
    row["recent_median_daily_quote_volume_proxy"] = recent_median_daily_quote
    row["recent_full_daily_quote_volume_day_count"] = recent_full_daily_count

    expected_recent_terminal_ts = recent_end_ts - pd.Timedelta(minutes=1)
    recent_last_timestamp = recent_1m.index.max() if not recent_1m.empty else None
    row["recent_expected_terminal_timestamp"] = _serialize_timestamp(expected_recent_terminal_ts)
    row["recent_terminal_gap_minutes"] = _terminal_gap_minutes(
        recent_last_timestamp,
        expected_recent_terminal_ts,
    )
    row["recent_terminal_gap_days"] = row["recent_terminal_gap_minutes"] / 1440.0

    try:
        with _suppress_feature_generation_output():
            df_15m, _, df_12h, df_1d, df_1w = _build_strategy_timeframes(clean_1m, config=base_config)
    except Exception as exc:
        row["reasons"] = ["feature_generation_failed"]
        row["reject_reason"] = "feature_generation_failed"
        row["error_stage"] = "timeframe_build"
        row["error"] = str(exc)
        row["traceback"] = traceback.format_exc(limit=8)
        return row

    try:
        with _suppress_feature_generation_output():
            htf_snapshots = build_htf_12h_snapshots(df_15m.index, df_12h, df_1d, df_1w, config=base_config)
    except Exception as exc:
        row["reasons"] = ["feature_generation_failed"]
        row["reject_reason"] = "feature_generation_failed"
        row["error_stage"] = "htf_snapshot_build"
        row["error"] = str(exc)
        row["traceback"] = traceback.format_exc(limit=8)
        return row

    try:
        with _suppress_feature_generation_output():
            rotation_snapshots = build_htf_rotation_snapshots_by_symbol(
                {symbol: df_15m.index},
                {symbol: df_12h},
                {symbol: df_1d},
                {symbol: df_1w},
                structural_snapshots_by_symbol={symbol: htf_snapshots},
                config=base_config,
            ).get(symbol, pd.DataFrame())
    except Exception as exc:
        row["reasons"] = ["feature_generation_failed"]
        row["reject_reason"] = "feature_generation_failed"
        row["error_stage"] = "rotation_snapshot_build"
        row["error"] = str(exc)
        row["traceback"] = traceback.format_exc(limit=8)
        return row

    recent_15m = _recent_slice(df_15m, recent_start_ts, recent_end_ts)
    recent_12h = _recent_slice(df_12h, recent_start_ts, recent_end_ts)
    recent_1d = _recent_slice(df_1d, recent_start_ts, recent_end_ts)
    recent_htf = _recent_slice(htf_snapshots, recent_start_ts, recent_end_ts)
    recent_rotation = _recent_slice(rotation_snapshots, recent_start_ts, recent_end_ts)

    missing_15m_count, missing_15m_ratio = _index_gap_metrics(recent_15m.index, "15min")
    row["recent_15m_rows"] = int(len(recent_15m))
    row["recent_12h_rows"] = int(len(recent_12h))
    row["recent_1d_rows"] = int(len(recent_1d))
    row["recent_missing_15m_count"] = missing_15m_count
    row["recent_missing_15m_ratio"] = missing_15m_ratio
    row["core_first_eligible_timestamp"] = _serialize_timestamp(recent_15m.index.min() if not recent_15m.empty else None)
    row["htf_first_eligible_timestamp"] = _serialize_timestamp(
        _first_true_timestamp(recent_htf, "htf_12h_new_candle")
    )
    row["rotation_first_eligible_timestamp"] = _serialize_timestamp(
        _first_true_timestamp(recent_rotation, "htf_rotation_new_candle")
    )
    row["recent_htf_new_candle_count"] = int(
        recent_htf["htf_12h_new_candle"].fillna(False).astype(bool).sum()
    ) if not recent_htf.empty and "htf_12h_new_candle" in recent_htf.columns else 0
    row["recent_rotation_new_candle_count"] = int(
        recent_rotation["htf_rotation_new_candle"].fillna(False).astype(bool).sum()
    ) if not recent_rotation.empty and "htf_rotation_new_candle" in recent_rotation.columns else 0

    row["eligible_core"] = bool(
        len(recent_15m) >= int(thresholds["min_recent_execution_rows"])
    )
    row["eligible_htf_moonshot"] = bool(
        len(recent_12h) >= int(thresholds["min_recent_12h_rows"])
        and len(recent_1d) >= int(thresholds["min_recent_1d_rows"])
        and row["recent_htf_new_candle_count"] > 0
    )
    row["eligible_htf_rotation"] = bool(
        len(recent_12h) >= int(thresholds["min_recent_12h_rows"])
        and len(recent_1d) >= int(thresholds["min_recent_1d_rows"])
        and row["recent_rotation_new_candle_count"] > 0
    )

    reasons = []
    if row["duplicate_1m_ratio"] > thresholds["max_duplicate_1m_ratio"]:
        reasons.append("high_duplicate_1m_ratio")
    if row["recent_ohlcv_nan_ratio"] > thresholds["max_ohlcv_nan_ratio"]:
        reasons.append("high_recent_ohlcv_nan_ratio")
    if row["recent_missing_1m_ratio"] > thresholds["max_missing_1m_ratio"]:
        reasons.append("high_recent_missing_1m_ratio")
    if row["recent_missing_15m_ratio"] > thresholds["max_missing_15m_ratio"]:
        reasons.append("high_recent_missing_15m_ratio")
    if row["recent_terminal_gap_minutes"] > thresholds["max_recent_terminal_gap_minutes"]:
        reasons.append("insufficient_terminal_coverage")
    if row["recent_median_daily_quote_volume_proxy"] < thresholds["min_recent_median_daily_quote_volume"]:
        reasons.append("low_recent_median_quote_volume")
    if row["recent_min_daily_quote_volume_proxy"] < thresholds["min_recent_min_daily_quote_volume"]:
        reasons.append("low_recent_min_quote_volume")
    if row["recent_avg_spread_proxy"] > thresholds["max_recent_spread_proxy"]:
        reasons.append("high_recent_spread_proxy")
    if not row["eligible_core"] and not row["eligible_htf_moonshot"] and not row["eligible_htf_rotation"]:
        reasons.append("insufficient_recent_strategy_context")

    row["reasons"] = reasons
    row["reject_reason"] = reasons[0] if reasons else ""
    row["accepted"] = len(reasons) == 0
    row["eligible_strategy_types"] = ",".join(
        strategy_type
        for strategy_type, enabled in [
            ("core", row["eligible_core"]),
            ("htf_12h_moonshot", row["eligible_htf_moonshot"]),
            ("htf_12h_rotation", row["eligible_htf_rotation"]),
        ]
        if enabled
    )
    return row


def _write_universe_quality_reports(report_root: Path, rows: list[dict]) -> dict:
    quality_df = pd.DataFrame(rows).sort_values(["accepted", "symbol"], ascending=[False, True]).reset_index(drop=True)
    accepted_df = quality_df.loc[quality_df["accepted"].fillna(False)].copy()
    rejected_df = quality_df.loc[~quality_df["accepted"].fillna(False)].copy()

    quality_path = report_root / "expanded_universe_quality.csv"
    accepted_path = report_root / "expanded_universe_accepted_symbols.csv"
    rejected_path = report_root / "expanded_universe_rejected_symbols.csv"
    summary_path = report_root / "expanded_universe_summary.json"

    quality_df.to_csv(quality_path, index=False)
    accepted_df.to_csv(accepted_path, index=False)
    rejected_df.to_csv(rejected_path, index=False)

    rejection_reasons = {}
    if not rejected_df.empty and "reject_reason" in rejected_df.columns:
        rejection_reasons = {
            str(key): int(value)
            for key, value in rejected_df["reject_reason"].fillna("unknown").astype(str).value_counts().items()
        }

    summary = {
        "quality_report": str(quality_path),
        "accepted_report": str(accepted_path),
        "rejected_report": str(rejected_path),
        "candidate_symbol_count": int(len(quality_df)),
        "accepted_symbol_count": int(len(accepted_df)),
        "rejected_symbol_count": int(len(rejected_df)),
        "accepted_symbols": accepted_df["symbol"].astype(str).tolist() if not accepted_df.empty else [],
        "rejected_symbols": rejected_df["symbol"].astype(str).tolist() if not rejected_df.empty else [],
        "rejection_reasons": rejection_reasons,
    }
    with summary_path.open("w", encoding="utf-8") as file_handle:
        json.dump(summary, file_handle, indent=2, default=str)
    summary["summary_path"] = str(summary_path)
    return summary


def _build_or_resume_quality_report(
    *,
    base_config: AppConfig,
    report_root: Path,
    candidate_symbols: list[str],
    recent_start: str,
    recent_end: str,
) -> dict:
    thresholds = _quality_thresholds(base_config)
    progress = _load_quality_progress(report_root)
    for symbol in candidate_symbols:
        symbol_key = str(symbol).upper()
        row = _validate_symbol_quality(
            symbol_key,
            base_config=base_config,
            recent_start=recent_start,
            recent_end=recent_end,
            thresholds=thresholds,
        )
        row["complete"] = True
        progress["symbols"][symbol_key] = row
        _save_quality_progress(report_root, progress)

    rows = [progress["symbols"][str(symbol).upper()] for symbol in candidate_symbols if str(symbol).upper() in progress["symbols"]]
    summary = _write_universe_quality_reports(report_root, rows)
    return {
        "rows": rows,
        "summary": summary,
        "accepted_symbols": summary["accepted_symbols"],
        "rejected_symbols": summary["rejected_symbols"],
    }


def _strategy_breakdown(trades: pd.DataFrame) -> list[dict]:
    if trades.empty or "strategy_type" not in trades.columns:
        return []
    working = trades.copy()
    working["strategy_type"] = working["strategy_type"].fillna("core").astype(str)
    working["pnl"] = pd.to_numeric(working.get("pnl"), errors="coerce").fillna(0.0)
    working["pnl_R_initial"] = pd.to_numeric(working.get("pnl_R_initial"), errors="coerce").fillna(0.0)
    rows = []
    for strategy_type, group in working.groupby("strategy_type"):
        pos = float(group.loc[group["pnl"] > 0, "pnl"].sum())
        neg = float(group.loc[group["pnl"] < 0, "pnl"].sum())
        pf = float("inf") if neg == 0.0 and pos > 0 else (pos / abs(neg) if neg != 0.0 else 0.0)
        rows.append(
            {
                "strategy_type": str(strategy_type),
                "trade_count": int(len(group)),
                "net_pnl": float(group["pnl"].sum()),
                "avg_R": float(group["pnl_R_initial"].mean()) if not group.empty else 0.0,
                "median_R": float(group["pnl_R_initial"].median()) if not group.empty else 0.0,
                "max_R": float(group["pnl_R_initial"].max()) if not group.empty else 0.0,
                "win_rate": float((group["pnl"] > 0).mean()) if not group.empty else 0.0,
                "profit_factor": pf,
            }
        )
    rows.sort(key=lambda item: item["net_pnl"], reverse=True)
    return rows


def _symbol_breakdown(trades: pd.DataFrame) -> list[dict]:
    if trades.empty or "symbol" not in trades.columns:
        return []
    working = trades.copy()
    working["symbol"] = working["symbol"].fillna("UNKNOWN").astype(str)
    working["pnl"] = pd.to_numeric(working.get("pnl"), errors="coerce").fillna(0.0)
    working["pnl_R_initial"] = pd.to_numeric(working.get("pnl_R_initial"), errors="coerce").fillna(0.0)
    rows = []
    for symbol, group in working.groupby("symbol"):
        pos = float(group.loc[group["pnl"] > 0, "pnl"].sum())
        neg = float(group.loc[group["pnl"] < 0, "pnl"].sum())
        pf = float("inf") if neg == 0.0 and pos > 0 else (pos / abs(neg) if neg != 0.0 else 0.0)
        loss_contribution = float(group.loc[group["pnl"] < 0, "pnl"].sum())
        rows.append(
            {
                "symbol": str(symbol),
                "trade_count": int(len(group)),
                "net_pnl": float(group["pnl"].sum()),
                "avg_R": float(group["pnl_R_initial"].mean()) if not group.empty else 0.0,
                "median_R": float(group["pnl_R_initial"].median()) if not group.empty else 0.0,
                "max_R": float(group["pnl_R_initial"].max()) if not group.empty else 0.0,
                "win_rate": float((group["pnl"] > 0).mean()) if not group.empty else 0.0,
                "profit_factor": pf,
                "loss_contribution_proxy": loss_contribution,
            }
        )
    rows.sort(key=lambda item: item["net_pnl"], reverse=True)
    return rows


def _selection_reason_counts(signals: pd.DataFrame) -> dict:
    if signals.empty or "selection_reason" not in signals.columns:
        return {}
    return {
        str(key): int(value)
        for key, value in signals["selection_reason"].fillna("unknown").astype(str).value_counts().items()
    }


def _write_breakdown_csvs(report_root: Path, scenario_key: str, strategy_rows: list[dict], symbol_rows: list[dict], selection_reasons: dict) -> None:
    pd.DataFrame(strategy_rows).to_csv(report_root / f"{scenario_key}_strategy_breakdown.csv", index=False)
    pd.DataFrame(symbol_rows).to_csv(report_root / f"{scenario_key}_symbol_breakdown.csv", index=False)
    pd.DataFrame(
        [{"selection_reason": key, "count": value} for key, value in selection_reasons.items()]
    ).to_csv(report_root / f"{scenario_key}_selection_reasons.csv", index=False)


def _scenario_snapshot(result: dict, symbols_used: list[str], report_root: Path, scenario_key: str) -> dict:
    trades = result["trades"]
    strategy_rows = _strategy_breakdown(trades)
    symbol_rows = _symbol_breakdown(trades)
    selection_reasons = _selection_reason_counts(result["signals"])
    _write_breakdown_csvs(report_root, scenario_key, strategy_rows, symbol_rows, selection_reasons)

    strategy_pnl = {row["strategy_type"]: row["net_pnl"] for row in strategy_rows}
    net_pnl = float(result["metrics"]["net_pnl"])
    core_share = _safe_pct(strategy_pnl.get("core", 0.0), net_pnl) if net_pnl != 0.0 else 0.0
    htf_total = strategy_pnl.get("htf_12h_moonshot", 0.0) + strategy_pnl.get("htf_12h_rotation", 0.0)

    return {
        "name": result["name"],
        "artifacts_complete": bool(result.get("artifacts_complete", False)),
        "last_equity_timestamp": result.get("last_equity_timestamp"),
        "symbols_used": [str(symbol).upper() for symbol in symbols_used],
        "metrics": result["metrics"],
        "top5_trades_contribution_pct": _top5_contribution_percent(trades),
        "strategy_breakdown": strategy_rows,
        "symbol_breakdown": symbol_rows,
        "selection_reasons": selection_reasons,
        "strategy_pnl": strategy_pnl,
        "core_pnl_share": core_share,
        "htf_total_pnl": htf_total,
    }


def _build_comparison(baseline: dict, expanded: dict) -> dict:
    baseline_metrics = baseline["metrics"]
    expanded_metrics = expanded["metrics"]
    baseline_pnl = baseline.get("strategy_pnl", {})
    expanded_pnl = expanded.get("strategy_pnl", {})

    return {
        "delta_final_equity": float(expanded_metrics["final_equity"]) - float(baseline_metrics["final_equity"]),
        "delta_net_pnl": float(expanded_metrics["net_pnl"]) - float(baseline_metrics["net_pnl"]),
        "delta_trade_count": int(expanded_metrics["trade_count"]) - int(baseline_metrics["trade_count"]),
        "delta_profit_factor": float(expanded_metrics["profit_factor"]) - float(baseline_metrics["profit_factor"]),
        "delta_avg_R": float(expanded_metrics["avg_R"]) - float(baseline_metrics["avg_R"]),
        "delta_median_daily_pnl": float(expanded_metrics["median_daily_pnl"]) - float(baseline_metrics["median_daily_pnl"]),
        "delta_recent_2025_plus_median_daily_pnl": float(expanded_metrics["recent_2025_plus_median_daily_pnl"]) - float(
            baseline_metrics["recent_2025_plus_median_daily_pnl"]
        ),
        "delta_max_drawdown": float(expanded_metrics["max_drawdown"]) - float(baseline_metrics["max_drawdown"]),
        "delta_avg_monthly_pnl": float(expanded_metrics["avg_monthly_pnl"]) - float(baseline_metrics["avg_monthly_pnl"]),
        "delta_months_gte_10k_count": int(expanded_metrics["months_gte_10k_count"]) - int(
            baseline_metrics["months_gte_10k_count"]
        ),
        "delta_top5_trades_contribution_pct": float(expanded["top5_trades_contribution_pct"]) - float(
            baseline["top5_trades_contribution_pct"]
        ),
        "delta_htf_rotation_pnl": float(expanded_pnl.get("htf_12h_rotation", 0.0)) - float(
            baseline_pnl.get("htf_12h_rotation", 0.0)
        ),
        "delta_htf_moonshot_pnl": float(expanded_pnl.get("htf_12h_moonshot", 0.0)) - float(
            baseline_pnl.get("htf_12h_moonshot", 0.0)
        ),
        "delta_core_pnl_share": float(expanded.get("core_pnl_share", 0.0)) - float(
            baseline.get("core_pnl_share", 0.0)
        ),
    }


def _build_verdict(*, quality: dict, baseline: dict, expanded: dict, comparison: dict) -> dict:
    expanded_pnl = expanded.get("strategy_pnl", {})
    baseline_pnl = baseline.get("strategy_pnl", {})
    accepted = quality["accepted_symbols"]
    rejected = quality["rejected_symbols"]
    net_new_symbols = [str(symbol).upper() for symbol in quality["summary"].get("net_new_accepted_symbols", [])]
    removed = [item["symbol"] for item in pd.DataFrame(quality["rows"]).loc[~pd.DataFrame(quality["rows"])["accepted"], ["symbol"]].to_dict("records")] if quality["rows"] else []
    return {
        "expanded_universe_accepted_symbols": accepted,
        "expanded_universe_rejected_symbols": rejected,
        "net_new_accepted_symbols": net_new_symbols,
        "did_expand_tradable_universe": bool(net_new_symbols),
        "expanded_validation_was_skipped": bool(expanded.get("skipped_due_to_identical_universe", False)),
        "expanded_validation_skip_reason": expanded.get("not_run_reason"),
        "did_expanded_universe_improve_opportunity_flow": bool(
            int(expanded["metrics"]["trade_count"]) > int(baseline["metrics"]["trade_count"])
        ),
        "did_htf_rotation_contribution_rise": bool(
            float(expanded_pnl.get("htf_12h_rotation", 0.0)) > float(baseline_pnl.get("htf_12h_rotation", 0.0))
        ),
        "did_htf_moonshot_contribution_rise": bool(
            float(expanded_pnl.get("htf_12h_moonshot", 0.0)) >= float(baseline_pnl.get("htf_12h_moonshot", 0.0))
        ),
        "did_core_dominance_reduce": bool(float(expanded.get("core_pnl_share", 0.0)) < float(baseline.get("core_pnl_share", 0.0))),
        "did_drawdown_remain_acceptable": bool(comparison["delta_max_drawdown"] >= -0.02),
        "is_expanded_universe_better_than_current_9_symbol_branch": bool(
            comparison["delta_final_equity"] > 0.0
            and comparison["delta_profit_factor"] >= -0.02
            and comparison["delta_median_daily_pnl"] >= -0.05
            and comparison["delta_max_drawdown"] >= -0.02
        ),
        "symbols_to_remove_or_review": removed,
        "symbols_to_keep": accepted,
        "should_proceed_to_full_history_validation": bool(
            comparison["delta_final_equity"] > 0.0 and comparison["delta_profit_factor"] >= -0.02
        ),
        "should_proceed_to_6h_candidate_study_after_this": False,
    }


def _build_candidate_branch_verdict(*, baseline: dict, candidate: dict, comparison: dict) -> dict:
    candidate_pnl = candidate.get("strategy_pnl", {})
    baseline_pnl = baseline.get("strategy_pnl", {})
    return {
        "is_better_than_current_9_symbol_branch": bool(
            comparison["delta_final_equity"] > 0.0
            and comparison["delta_profit_factor"] >= -0.02
            and comparison["delta_median_daily_pnl"] >= -0.05
            and comparison["delta_max_drawdown"] >= -0.02
        ),
        "did_drawdown_remain_acceptable": bool(comparison["delta_max_drawdown"] >= -0.02),
        "did_median_daily_improve": bool(comparison["delta_median_daily_pnl"] > 0.0),
        "did_profit_factor_hold_up": bool(comparison["delta_profit_factor"] >= -0.02),
        "did_core_dominance_reduce": bool(
            float(candidate.get("core_pnl_share", 0.0)) < float(baseline.get("core_pnl_share", 0.0))
        ),
        "did_htf_rotation_contribution_rise": bool(
            float(candidate_pnl.get("htf_12h_rotation", 0.0)) > float(baseline_pnl.get("htf_12h_rotation", 0.0))
        ),
        "did_htf_moonshot_contribution_rise": bool(
            float(candidate_pnl.get("htf_12h_moonshot", 0.0)) >= float(baseline_pnl.get("htf_12h_moonshot", 0.0))
        ),
    }


def _build_lean_sleeve_report(report_root: Path, baseline: dict, candidate: dict, label: str) -> dict:
    baseline_rows = {row["strategy_type"]: row for row in baseline.get("strategy_breakdown", [])}
    candidate_rows = {row["strategy_type"]: row for row in candidate.get("strategy_breakdown", [])}
    strategy_types = sorted(set(baseline_rows) | set(candidate_rows))
    rows = []
    for strategy_type in strategy_types:
        base_row = baseline_rows.get(strategy_type, {})
        cand_row = candidate_rows.get(strategy_type, {})
        delta_pnl = float(cand_row.get("net_pnl", 0.0)) - float(base_row.get("net_pnl", 0.0))
        rows.append(
            {
                "strategy_type": strategy_type,
                "baseline_trade_count": int(base_row.get("trade_count", 0) or 0),
                "candidate_trade_count": int(cand_row.get("trade_count", 0) or 0),
                "baseline_net_pnl": float(base_row.get("net_pnl", 0.0) or 0.0),
                "candidate_net_pnl": float(cand_row.get("net_pnl", 0.0) or 0.0),
                "delta_net_pnl": delta_pnl,
                "baseline_avg_R": float(base_row.get("avg_R", 0.0) or 0.0),
                "candidate_avg_R": float(cand_row.get("avg_R", 0.0) or 0.0),
                "baseline_profit_factor": float(base_row.get("profit_factor", 0.0) or 0.0),
                "candidate_profit_factor": float(cand_row.get("profit_factor", 0.0) or 0.0),
                "status": "improved" if delta_pnl > 0.0 else ("flat" if delta_pnl == 0.0 else "weakened"),
            }
        )
    rows.sort(key=lambda item: item["delta_net_pnl"], reverse=True)
    csv_path = report_root / f"lean_sleeve_report_{label}.csv"
    json_path = report_root / f"lean_sleeve_report_{label}.json"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    payload = {
        "label": label,
        "rows": rows,
        "csv_path": str(csv_path),
        "json_path": str(json_path),
    }
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return payload


def _classify_curated_symbol(row: dict, thresholds: dict) -> str:
    trade_count = int(row.get("trade_count", 0) or 0)
    net_pnl = float(row.get("net_pnl", 0.0) or 0.0)
    avg_r = float(row.get("avg_R", 0.0) or 0.0)
    profit_factor = float(row.get("profit_factor", 0.0) or 0.0)
    if (
        trade_count >= thresholds["min_keep_trade_count"]
        and net_pnl > thresholds["min_keep_net_pnl"]
        and avg_r > thresholds["min_keep_avg_R"]
        and profit_factor >= thresholds["min_keep_profit_factor"]
    ):
        return "keep"
    if trade_count >= thresholds["min_review_trade_count"] and net_pnl > 0.0 and avg_r > 0.0:
        return "review"
    return "drop"


def _build_symbol_curation_report(
    *,
    base_config: AppConfig,
    report_root: Path,
    baseline_symbols: list[str],
    expanded_snapshot: dict,
    accepted_symbols: list[str],
) -> dict:
    thresholds = _curation_thresholds(base_config)
    baseline_set = set(_effective_symbol_set(baseline_symbols))
    accepted_set = set(_effective_symbol_set(accepted_symbols))
    rows = []
    for item in expanded_snapshot.get("symbol_breakdown", []):
        symbol = str(item.get("symbol", "")).upper()
        if not symbol or symbol not in accepted_set or symbol in baseline_set:
            continue
        status = _classify_curated_symbol(item, thresholds)
        net_pnl = float(item.get("net_pnl", 0.0) or 0.0)
        rows.append(
            {
                "symbol": symbol,
                "trade_count": int(item.get("trade_count", 0) or 0),
                "net_pnl": net_pnl,
                "avg_R": float(item.get("avg_R", 0.0) or 0.0),
                "median_R": float(item.get("median_R", 0.0) or 0.0),
                "max_R": float(item.get("max_R", 0.0) or 0.0),
                "win_rate": float(item.get("win_rate", 0.0) or 0.0),
                "profit_factor": float(item.get("profit_factor", 0.0) or 0.0),
                "loss_contribution_proxy": float(item.get("loss_contribution_proxy", 0.0) or 0.0),
                "expanded_contribution_pct": _safe_pct(net_pnl, float(expanded_snapshot["metrics"]["net_pnl"])),
                "status": status,
            }
        )
    rows.sort(key=lambda item: ({"keep": 0, "review": 1, "drop": 2}.get(item["status"], 3), -item["net_pnl"]))
    keep_symbols = [row["symbol"] for row in rows if row["status"] == "keep"]
    review_symbols = [row["symbol"] for row in rows if row["status"] == "review"]
    drop_symbols = [row["symbol"] for row in rows if row["status"] == "drop"]
    curated_symbols = [str(symbol).upper() for symbol in baseline_symbols] + keep_symbols
    csv_path = report_root / "lean_symbol_report.csv"
    json_path = report_root / "lean_symbol_report.json"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    payload = {
        "thresholds": thresholds,
        "rows": rows,
        "keep_symbols": keep_symbols,
        "review_symbols": review_symbols,
        "drop_symbols": drop_symbols,
        "curated_symbols": curated_symbols,
        "csv_path": str(csv_path),
        "json_path": str(json_path),
    }
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return payload


def _scenario_base_with_symbols(base: AppConfig, symbols: list[str]) -> AppConfig:
    cfg = _clone_config(base)
    cfg.data.setdefault("backtest", {}).setdefault("portfolio_replay", {})["symbols"] = list(symbols)
    cfg.data.setdefault("live_sim", {}).setdefault("universe", {})["symbols"] = list(symbols)
    return cfg


def _build_skipped_expanded_snapshot(baseline_snapshot: dict, symbols_used: list[str], reason: str) -> dict:
    snapshot = deepcopy(baseline_snapshot)
    snapshot["name"] = "scenario_expanded_universe_calibrated_allocator"
    snapshot["symbols_used"] = [str(symbol).upper() for symbol in symbols_used]
    snapshot["skipped_due_to_identical_universe"] = True
    snapshot["not_run_reason"] = reason
    return snapshot


def _effective_symbol_set(values) -> list[str]:
    return [str(symbol).upper() for symbol in list(values or [])]


def _should_skip_expanded_scenario(current_symbols: list[str], accepted_symbols: list[str]) -> tuple[bool, str | None]:
    current_set = set(_effective_symbol_set(current_symbols))
    accepted_set = set(_effective_symbol_set(accepted_symbols))
    net_new = accepted_set - current_set
    if not net_new:
        return True, "no_net_universe_expansion_after_quality_validation"
    return False, None


def _progress_symbols_for_scenario(progress: dict, scenario_key: str) -> list[str]:
    snapshot = progress.get(scenario_key) or {}
    if not snapshot and scenario_key.startswith("scenario_"):
        snapshot = progress.get(scenario_key.removeprefix("scenario_")) or {}
    symbols_used = snapshot.get("symbols_used")
    if isinstance(symbols_used, list):
        return _effective_symbol_set(symbols_used)
    return []


def _scenario_requires_symbol_reset(progress: dict, scenario_key: str, symbols_used: list[str]) -> bool:
    previous = set(_progress_symbols_for_scenario(progress, scenario_key))
    current = set(_effective_symbol_set(symbols_used))
    return bool(previous) and previous != current


def _scenario_artifacts_require_symbol_reset(
    report_root: Path,
    scenario_key: str,
    symbols_used: list[str],
) -> bool:
    trades_path = report_root / scenario_key / "trades.csv"
    if not trades_path.exists():
        return False
    try:
        trades = pd.read_csv(trades_path, usecols=["symbol"], on_bad_lines="skip", engine="python")
    except Exception:
        return True
    if trades.empty or "symbol" not in trades.columns:
        return False

    observed = trades["symbol"].fillna("").astype(str).str.strip()
    if observed.eq("").any():
        return True

    expected = set(_effective_symbol_set(symbols_used))
    observed_set = {value.upper() for value in observed.tolist() if value}
    return bool(observed_set - expected)


def _seed_scenario_progress(
    progress: dict,
    scenario_key: str,
    symbols_used: list[str],
    *,
    status: str,
    reset_output: bool = False,
) -> dict:
    entry = progress.setdefault(scenario_key, {})
    entry["symbols_used"] = [str(symbol).upper() for symbol in symbols_used]
    entry["status"] = str(status)
    entry["reset_output_requested"] = bool(reset_output)
    entry.setdefault("completed", False)
    return entry


def main():
    base = AppConfig.load()
    base_output = Path(base.require("backtest", "output_dir"))
    discovery_settings = get_discovery_settings(base)
    report_root_name = (
        discovery_settings["validation_report_root_name"]
        if discovery_settings["enabled"]
        else "expanded_universe_allocator_validation_20260604"
    )
    report_root = base_output / report_root_name
    report_root.mkdir(parents=True, exist_ok=True)

    recent_start = "2025-01-01"
    recent_end = str(base.require("history", "end_date"))

    current_symbols = get_named_universe(base, "current_9") or [
        str(symbol).upper() for symbol in base.require("backtest", "portfolio_replay", "symbols")
    ]
    candidate_symbols, candidate_source = _resolve_candidate_symbols(base, report_root)
    if not candidate_symbols:
        raise ValueError("No candidate universe resolved from discovery or static config.")

    quality = _build_or_resume_quality_report(
        base_config=base,
        report_root=report_root,
        candidate_symbols=candidate_symbols,
        recent_start=recent_start,
        recent_end=recent_end,
    )
    if not quality["accepted_symbols"]:
        raise RuntimeError(
            "Expanded universe quality validation accepted zero symbols. "
            "Inspect expanded_universe_rejected_symbols.csv for rejection reasons."
        )

    current_symbol_set = {str(symbol).upper() for symbol in current_symbols}
    accepted_symbol_set = {str(symbol).upper() for symbol in quality["accepted_symbols"]}
    net_new_symbols = [symbol for symbol in quality["accepted_symbols"] if str(symbol).upper() not in current_symbol_set]
    quality["summary"]["current_symbol_count"] = len(current_symbol_set)
    quality["summary"]["net_new_accepted_symbol_count"] = len(net_new_symbols)
    quality["summary"]["net_new_accepted_symbols"] = [str(symbol).upper() for symbol in net_new_symbols]
    quality["summary"]["candidate_source"] = candidate_source["source"]
    quality["summary"]["candidate_symbol_count_before_quality"] = int(
        candidate_source["summary"].get("candidate_symbol_count", len(candidate_symbols))
    )
    quality["summary"]["candidate_symbols_before_quality"] = list(candidate_symbols)

    progress = _load_progress(report_root)
    baseline_scenario_name = "scenario_current_9_symbol_calibrated_allocator"
    baseline_summary_key = "current_9_symbol_calibrated_allocator"
    expanded_scenario_name = "scenario_expanded_universe_calibrated_allocator"
    expanded_summary_key = "expanded_universe_calibrated_allocator"
    curated_scenario_name = "scenario_curated_expanded_universe_calibrated_allocator"
    curated_summary_key = "curated_expanded_universe_calibrated_allocator"
    scenarios = {}
    baseline_flags = {
        "core_enabled": True,
        "swing_enabled": True,
        "htf_enabled": True,
        "convexity_enabled": True,
        "history_start_date": recent_start,
        "history_end_date": recent_end,
    }
    baseline_reset_output = (
        _scenario_requires_symbol_reset(
            progress,
            baseline_scenario_name,
            current_symbols,
        )
        or _scenario_artifacts_require_symbol_reset(
            report_root,
            baseline_scenario_name,
            current_symbols,
        )
    )
    _seed_scenario_progress(
        progress,
        baseline_scenario_name,
        current_symbols,
        status="in_progress",
        reset_output=baseline_reset_output,
    )
    _save_progress(report_root, progress)
    baseline_result = _run_or_resume_scenario(
        baseline_scenario_name,
        _scenario_base_with_symbols(base, current_symbols),
        report_root,
        progress,
        reset_output=baseline_reset_output,
        **baseline_flags,
    )
    baseline_snapshot = _scenario_snapshot(
        baseline_result,
        current_symbols,
        report_root,
        baseline_summary_key,
    )
    scenarios[baseline_summary_key] = baseline_snapshot
    baseline_progress = progress.setdefault(baseline_scenario_name, {})
    baseline_progress["symbols_used"] = baseline_snapshot["symbols_used"]
    baseline_progress["status"] = "completed"
    _save_progress(report_root, progress)

    skip_expanded, skip_reason = _should_skip_expanded_scenario(
        current_symbols,
        quality["accepted_symbols"],
    )
    if skip_expanded:
        expanded_snapshot = _build_skipped_expanded_snapshot(
            baseline_snapshot,
            quality["accepted_symbols"],
            reason=skip_reason or "no_net_universe_expansion_after_quality_validation",
        )
        scenarios[expanded_summary_key] = expanded_snapshot
        expanded_progress = progress.setdefault(expanded_scenario_name, {})
        expanded_progress["symbols_used"] = expanded_snapshot["symbols_used"]
        expanded_progress["status"] = "skipped"
        expanded_progress["completed"] = True
        _save_progress(report_root, progress)
    else:
        expanded_reset_output = (
            _scenario_requires_symbol_reset(
                progress,
                expanded_scenario_name,
                quality["accepted_symbols"],
            )
            or _scenario_artifacts_require_symbol_reset(
                report_root,
                expanded_scenario_name,
                quality["accepted_symbols"],
            )
        )
        _seed_scenario_progress(
            progress,
            expanded_scenario_name,
            quality["accepted_symbols"],
            status="in_progress",
            reset_output=expanded_reset_output,
        )
        _save_progress(report_root, progress)
        expanded_result = _run_or_resume_scenario(
            expanded_scenario_name,
            _scenario_base_with_symbols(base, quality["accepted_symbols"]),
            report_root,
            progress,
            reset_output=expanded_reset_output,
            **baseline_flags,
        )
        expanded_snapshot = _scenario_snapshot(
            expanded_result,
            quality["accepted_symbols"],
            report_root,
            expanded_summary_key,
        )
        scenarios[expanded_summary_key] = expanded_snapshot
        expanded_progress = progress.setdefault(expanded_scenario_name, {})
        expanded_progress["symbols_used"] = expanded_snapshot["symbols_used"]
        expanded_progress["status"] = "completed"
        _save_progress(report_root, progress)

    comparison = _build_comparison(
        scenarios[baseline_summary_key],
        scenarios[expanded_summary_key],
    )
    verdict = _build_verdict(
        quality=quality,
        baseline=scenarios[baseline_summary_key],
        expanded=scenarios[expanded_summary_key],
        comparison=comparison,
    )

    lean_reports = {
        expanded_summary_key: _build_lean_sleeve_report(
            report_root,
            scenarios[baseline_summary_key],
            scenarios[expanded_summary_key],
            label=expanded_summary_key,
        )
    }
    curation = _build_symbol_curation_report(
        base_config=base,
        report_root=report_root,
        baseline_symbols=current_symbols,
        expanded_snapshot=scenarios[expanded_summary_key],
        accepted_symbols=quality["accepted_symbols"],
    )

    curated_comparison = None
    curated_verdict = None
    curated_symbols = curation["curated_symbols"]
    if set(_effective_symbol_set(curated_symbols)) != set(_effective_symbol_set(current_symbols)):
        curated_reset_output = (
            _scenario_requires_symbol_reset(
                progress,
                curated_scenario_name,
                curated_symbols,
            )
            or _scenario_artifacts_require_symbol_reset(
                report_root,
                curated_scenario_name,
                curated_symbols,
            )
        )
        _seed_scenario_progress(
            progress,
            curated_scenario_name,
            curated_symbols,
            status="in_progress",
            reset_output=curated_reset_output,
        )
        _save_progress(report_root, progress)
        curated_result = _run_or_resume_scenario(
            curated_scenario_name,
            _scenario_base_with_symbols(base, curated_symbols),
            report_root,
            progress,
            reset_output=curated_reset_output,
            **baseline_flags,
        )
        curated_snapshot = _scenario_snapshot(
            curated_result,
            curated_symbols,
            report_root,
            curated_summary_key,
        )
        scenarios[curated_summary_key] = curated_snapshot
        curated_progress = progress.setdefault(curated_scenario_name, {})
        curated_progress["symbols_used"] = curated_snapshot["symbols_used"]
        curated_progress["status"] = "completed"
        _save_progress(report_root, progress)
        curated_comparison = _build_comparison(
            scenarios[baseline_summary_key],
            scenarios[curated_summary_key],
        )
        curated_verdict = _build_candidate_branch_verdict(
            baseline=scenarios[baseline_summary_key],
            candidate=scenarios[curated_summary_key],
            comparison=curated_comparison,
        )
        lean_reports[curated_summary_key] = _build_lean_sleeve_report(
            report_root,
            scenarios[baseline_summary_key],
            scenarios[curated_summary_key],
            label=curated_summary_key,
        )
    else:
        scenarios[curated_summary_key] = _build_skipped_expanded_snapshot(
            scenarios[baseline_summary_key],
            curated_symbols,
            reason="no_curated_net_new_symbols_after_post_validation_report",
        )
        curated_progress = progress.setdefault(curated_scenario_name, {})
        curated_progress["symbols_used"] = [str(symbol).upper() for symbol in curated_symbols]
        curated_progress["status"] = "skipped"
        curated_progress["completed"] = True
        _save_progress(report_root, progress)

    summary = {
        "report_root": str(report_root),
        "recent_window": {
            "start_date": recent_start,
            "end_date": recent_end,
        },
        "candidate_source": candidate_source,
        "quality": quality["summary"],
        "scenarios": scenarios,
        "comparison": comparison,
        "verdict": verdict,
        "lean_reports": lean_reports,
        "curation": curation,
        "curated_comparison": curated_comparison,
        "curated_verdict": curated_verdict,
    }
    with (report_root / "summary.json").open("w", encoding="utf-8") as file_handle:
        json.dump(summary, file_handle, indent=2, default=str)


if __name__ == "__main__":
    main()
