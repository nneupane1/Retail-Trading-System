"""Telemetry loaders for the live-paper dashboard."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd

from config import AppConfig
from data.downloader import load_from_csv
from data.resampler import TimeframeBuilder


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _parse_storage_timestamp(value: str) -> pd.Timestamp:
    return pd.Timestamp(str(value).replace("T", " ").replace(".", ":"))


def _resolve_live_output_root(config: AppConfig) -> Path:
    return config.path("live_sim", "output_dir")


def _resolve_history_file(
    folder: Path,
    *,
    symbol: str,
    interval: str,
    start_date: str,
    end_date: str,
) -> Path | None:
    exact_path = folder / f"{symbol}_{interval}_{start_date}_to_{end_date}.csv"
    if exact_path.exists():
        return exact_path

    requested_start = pd.Timestamp(start_date)
    requested_end = pd.Timestamp(end_date)
    candidates = []
    prefix = f"{symbol}_{interval}_"
    for candidate in folder.glob(f"{symbol}_{interval}_*.csv"):
        if candidate.name.endswith("_live_runtime.csv"):
            continue
        stem = candidate.stem
        if not stem.startswith(prefix) or "_to_" not in stem:
            continue
        remainder = stem[len(prefix):]
        start_text, end_text = remainder.split("_to_", 1)
        try:
            candidate_start = _parse_storage_timestamp(start_text)
            candidate_end = _parse_storage_timestamp(end_text)
        except Exception:
            continue
        if candidate_end >= requested_start and candidate_start <= requested_end:
            candidates.append(
                (
                    candidate_end >= requested_end,
                    candidate_start <= requested_start,
                    candidate_end,
                    -candidate_start.value,
                    candidate,
                )
            )

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][4]


def list_live_runs(config: AppConfig | None = None) -> list[dict[str, Any]]:
    config = config or AppConfig.load()
    output_root = _resolve_live_output_root(config)
    if not output_root.exists():
        return []

    rows: list[dict[str, Any]] = []
    for path in output_root.iterdir():
        if not path.is_dir():
            continue
        status_path = path / "portfolio_status.json"
        rows.append(
            {
                "run_id": path.name,
                "path": str(path),
                "has_portfolio_status": status_path.exists(),
                "last_write_time": path.stat().st_mtime,
            }
        )
    rows.sort(key=lambda item: item["last_write_time"], reverse=True)
    return rows


def latest_live_run(config: AppConfig | None = None) -> Path | None:
    rows = list_live_runs(config=config)
    if not rows:
        return None
    return Path(rows[0]["path"])


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def _tail_csv_rows(path: Path, limit: int = 200) -> list[dict[str, Any]]:
    rows = _read_csv_rows(path)
    return rows[-limit:] if limit > 0 else rows


def load_live_dashboard_snapshot(
    run_dir: str | Path | None = None,
    *,
    config: AppConfig | None = None,
    trade_limit: int = 200,
    signal_limit: int = 200,
) -> dict[str, Any]:
    config = config or AppConfig.load()
    root = Path(run_dir) if run_dir else latest_live_run(config=config)
    if root is None or not root.exists():
        return {
            "run": None,
            "portfolio_status": {},
            "runtime_policy_rows": [],
            "selection_reason_rows": [],
            "recent_selection_reason_rows": [],
            "selection_reason_by_strategy_rows": [],
            "daily_summary_rows": [],
            "trade_rows": [],
            "signal_rows": [],
            "engine_heartbeat": {},
            "engine_cycle_rows": [],
            "symbol_pipeline_rows": [],
            "available_symbols": [],
        }

    portfolio_status = _read_json(root / "portfolio_status.json", {})
    runtime_policy_rows = _read_csv_rows(root / "runtime_policy_summary.csv")
    selection_reason_rows = _read_csv_rows(root / "selection_reason_summary.csv")
    recent_selection_reason_rows = _read_csv_rows(root / "recent_selection_reason_summary.csv")
    selection_reason_by_strategy_rows = _read_csv_rows(root / "selection_reason_by_strategy_summary.csv")
    daily_summary_rows = _read_csv_rows(root / "daily_summary.csv")
    trade_rows = _tail_csv_rows(root / "trades.csv", limit=trade_limit)
    signal_rows = _tail_csv_rows(root / "signals.csv", limit=signal_limit)
    engine_heartbeat = _read_json(root / "engine_heartbeat.json", {})
    engine_cycle_rows = _tail_csv_rows(root / "engine_cycle_history.csv", limit=120)
    symbol_pipeline_rows = _read_csv_rows(root / "symbol_pipeline_status.csv")

    latest_trade = trade_rows[-1] if trade_rows else None
    latest_signal = signal_rows[-1] if signal_rows else None
    available_symbols = sorted(
        {
            str(row.get("symbol", "")).upper()
            for row in [*trade_rows, *signal_rows, *symbol_pipeline_rows]
            if row.get("symbol")
        }
        | {str(symbol).upper() for symbol in portfolio_status.get("top_symbols", [])}
    )

    return {
        "run": {
            "run_id": root.name,
            "path": str(root),
            "last_write_time": root.stat().st_mtime,
        },
        "portfolio_status": portfolio_status,
        "runtime_policy_rows": runtime_policy_rows,
        "selection_reason_rows": selection_reason_rows,
        "recent_selection_reason_rows": recent_selection_reason_rows,
        "selection_reason_by_strategy_rows": selection_reason_by_strategy_rows,
        "daily_summary_rows": daily_summary_rows,
        "trade_rows": trade_rows,
        "signal_rows": signal_rows,
        "engine_heartbeat": engine_heartbeat,
        "engine_cycle_rows": engine_cycle_rows,
        "symbol_pipeline_rows": symbol_pipeline_rows,
        "latest_trade": latest_trade,
        "latest_signal": latest_signal,
        "available_symbols": available_symbols,
    }


def load_symbol_candles(
    symbol: str,
    *,
    timeframe: str = "15m",
    limit: int = 500,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    config = config or AppConfig.load()
    symbol = str(symbol).upper()
    interval = config.require("binance", "default_interval")
    folder = config.path("storage", "base_path") / symbol / interval
    source_path = _resolve_history_file(
        folder,
        symbol=symbol,
        interval=interval,
        start_date=config.require("history", "start_date"),
        end_date=config.require("history", "end_date"),
    )
    if source_path is None:
        raise FileNotFoundError(f"No base history found for {symbol}.")

    df_1m = load_from_csv(source_path)
    if str(timeframe).lower() in {"1m", "1min"}:
        frame = df_1m.copy()
    else:
        builder = TimeframeBuilder(config=config)
        frame = builder.resample(df_1m, timeframe)

    if limit:
        frame = frame.tail(int(limit))

    candles = []
    for timestamp, row in frame.iterrows():
        candles.append(
            {
                "time": int(pd.Timestamp(timestamp).timestamp()),
                "timestamp": str(pd.Timestamp(timestamp)),
                "open": _safe_float(row.get("open")),
                "high": _safe_float(row.get("high")),
                "low": _safe_float(row.get("low")),
                "close": _safe_float(row.get("close")),
                "volume": _safe_float(row.get("volume")),
            }
        )

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "source_path": str(source_path),
        "candles": candles,
    }


def build_trade_markers(
    trade_rows: list[dict[str, Any]],
    *,
    symbol: str,
) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    symbol_key = str(symbol).upper()
    for row in trade_rows:
        if str(row.get("symbol", "")).upper() != symbol_key:
            continue
        entry_time = row.get("entry_time")
        exit_time = row.get("exit_time")
        side = str(row.get("side", "")).lower()
        color = "#16a34a" if side == "long" else "#ef4444"
        if entry_time:
            markers.append(
                {
                    "time": int(pd.Timestamp(entry_time).timestamp()),
                    "position": "belowBar" if side == "long" else "aboveBar",
                    "color": color,
                    "shape": "arrowUp" if side == "long" else "arrowDown",
                    "text": f"{row.get('strategy_type', '')} entry",
                }
            )
        if exit_time:
            pnl = _safe_float(row.get("pnl"))
            markers.append(
                {
                    "time": int(pd.Timestamp(exit_time).timestamp()),
                    "position": "aboveBar" if side == "long" else "belowBar",
                    "color": "#22c55e" if pnl >= 0.0 else "#f97316",
                    "shape": "circle",
                    "text": f"exit {pnl:.2f}",
                }
            )
    return markers
