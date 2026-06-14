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
from common.runtime_readiness import build_runtime_readiness


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


def _runtime_state_path(folder: Path, *, symbol: str, interval: str) -> Path:
    return folder / f"{symbol}_{interval}_live_runtime.csv"


def _has_live_artifacts(path: Path) -> bool:
    artifact_names = [
        "portfolio_status.json",
        "engine_heartbeat.json",
        "engine_cycle_history.csv",
        "symbol_pipeline_status.csv",
        "trades.csv",
        "signals.csv",
    ]
    return any((path / name).exists() for name in artifact_names)


def _artifact_mtime(path: Path) -> float:
    artifact_names = [
        "portfolio_status.json",
        "engine_heartbeat.json",
        "engine_cycle_history.csv",
        "symbol_pipeline_status.csv",
        "trades.csv",
        "signals.csv",
    ]
    times = [(path / name).stat().st_mtime for name in artifact_names if (path / name).exists()]
    if times:
        return max(times)
    return path.stat().st_mtime


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
    if _has_live_artifacts(output_root):
        rows.append(
            {
                "run_id": output_root.name,
                "path": str(output_root),
                "has_portfolio_status": (output_root / "portfolio_status.json").exists(),
                "last_write_time": _artifact_mtime(output_root),
            }
        )
    for path in output_root.iterdir():
        if not path.is_dir():
            continue
        if not _has_live_artifacts(path):
            continue
        status_path = path / "portfolio_status.json"
        rows.append(
            {
                "run_id": path.name,
                "path": str(path),
                "has_portfolio_status": status_path.exists(),
                "last_write_time": _artifact_mtime(path),
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


def _to_utc_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _artifact_timestamp(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC").isoformat()
    except Exception:
        return None


def _artifact_status(path: Path, *, stale_after_seconds: float) -> dict[str, Any]:
    exists = path.exists()
    last_modified_timestamp = _artifact_timestamp(path)
    if not exists:
        return {
            "path": str(path),
            "exists": False,
            "last_modified_timestamp": None,
            "age_seconds": None,
            "status": "missing",
            "stale": True,
            "stale_after_seconds": stale_after_seconds,
        }
    try:
        age_seconds = max(
            0.0,
            float(pd.Timestamp.now("UTC").timestamp() - path.stat().st_mtime),
        )
    except Exception:
        age_seconds = None
    stale = age_seconds is None or age_seconds > stale_after_seconds
    return {
        "path": str(path),
        "exists": True,
        "last_modified_timestamp": last_modified_timestamp,
        "age_seconds": age_seconds,
        "status": "stale" if stale else "healthy",
        "stale": stale,
        "stale_after_seconds": stale_after_seconds,
    }


def _latest_jsonl_record(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception:
        return {}
    if not lines:
        return {}
    try:
        payload = json.loads(lines[-1])
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _report_check_status(report: dict[str, Any], check_name: str) -> str:
    for row in list(report.get("checks") or []):
        if str(row.get("name")) != check_name:
            continue
        if "status" in row:
            return str(row.get("status"))
        if row.get("passed") is True:
            return "pass"
        if row.get("passed") is False:
            return "fail"
    return "unknown"


def _build_validation_truth(readiness: dict[str, Any]) -> dict[str, Any]:
    status = dict(readiness.get("status") or {})
    summary_path = Path(readiness["summary_path"]) if readiness.get("summary_path") else None
    report_path = (
        Path(readiness["promotion_readiness_report_path"])
        if readiness.get("promotion_readiness_report_path")
        else None
    )
    summary = _read_json(summary_path, {}) if summary_path else {}
    report = _read_json(report_path, {}) if report_path else {}
    scenarios = dict(summary.get("scenarios") or {})
    full_history = dict(scenarios.get("full_history_latest_closed_day") or {})
    holdout = dict(scenarios.get("trailing_12m_holdout") or {})
    return {
        "validation_status": str(status.get("stage") or "missing"),
        "full_history_verdict": _report_check_status(report, "full_history_positive_expectancy"),
        "trailing_holdout_verdict": _report_check_status(report, "holdout_positive_expectancy"),
        "full_history_artifacts_verdict": _report_check_status(report, "full_history_artifacts_complete"),
        "trailing_holdout_artifacts_verdict": _report_check_status(report, "holdout_artifacts_complete"),
        "latest_data_timestamp": readiness.get("latest_common_data_timestamp"),
        "validated_boundary": readiness.get("validated_boundary"),
        "full_history_metrics": dict(full_history.get("metrics") or {}),
        "trailing_holdout_metrics": dict(holdout.get("metrics") or {}),
        "gate_report_blockers": list(report.get("blockers") or []),
        "gate_status_blockers": list(status.get("blockers") or []),
        "holdout_is_thin": bool(readiness.get("holdout_is_thin", True)),
    }


def _build_artifact_freshness(root: Path, readiness: dict[str, Any]) -> dict[str, dict[str, Any]]:
    summary_path = Path(readiness["summary_path"]) if readiness.get("summary_path") else root / "missing_summary.json"
    report_path = (
        Path(readiness["promotion_readiness_report_path"])
        if readiness.get("promotion_readiness_report_path")
        else root / "missing_promotion_readiness_report.json"
    )
    artifacts = {
        "baseline_freeze_snapshot": _artifact_status(root / "baseline_freeze_snapshot.json", stale_after_seconds=24 * 3600.0),
        "capital_refactor_scaffold_inventory": _artifact_status(root / "capital_refactor" / "scaffold_inventory.json", stale_after_seconds=24 * 3600.0),
        "paper_soak_daily_report": _artifact_status(root / "paper_soak_daily_report.json", stale_after_seconds=24 * 3600.0),
        "paper_soak_review": _artifact_status(root / "paper_soak_review.json", stale_after_seconds=24 * 3600.0),
        "paper_soak_review_history": _artifact_status(root / "paper_soak_review_history.jsonl", stale_after_seconds=24 * 3600.0),
        "paper_soak_status": _artifact_status(root / "paper_soak_status.json", stale_after_seconds=300.0),
        "paper_runtime_events": _artifact_status(root / "paper_runtime_events.jsonl", stale_after_seconds=900.0),
        "portfolio_runtime_state": _artifact_status(root / "portfolio_runtime_state.json", stale_after_seconds=900.0),
        "portfolio_status": _artifact_status(root / "portfolio_status.json", stale_after_seconds=300.0),
        "production_gate_summary": _artifact_status(summary_path, stale_after_seconds=7 * 24 * 3600.0),
        "promotion_readiness_report": _artifact_status(report_path, stale_after_seconds=7 * 24 * 3600.0),
    }
    return artifacts


def _build_operator_warning_list(
    readiness: dict[str, Any],
    soak_status: dict[str, Any],
    artifact_freshness: dict[str, dict[str, Any]],
) -> list[str]:
    warnings: list[str] = []
    if str(readiness.get("classification") or "") == "paper-only":
        warnings.append("classification_paper_only")
    if not bool(readiness.get("real_money_allowed", False)):
        warnings.append("real_money_blocked")
    if bool(readiness.get("holdout_is_thin", True)):
        warnings.append("holdout_edge_thin")
    warnings.extend(list(readiness.get("warnings") or []))
    warnings.extend(list(soak_status.get("display_warning_list") or []))
    for artifact_key, artifact in artifact_freshness.items():
        if not artifact.get("exists"):
            warnings.append(f"missing_artifact:{artifact_key}")
        elif artifact.get("stale"):
            warnings.append(f"stale_artifact:{artifact_key}")
    return list(dict.fromkeys(warnings))


def _display_soak_warnings(root: Path, soak_status: dict[str, Any]) -> list[str]:
    warnings = list(soak_status.get("warning_list") or [])
    heartbeat = dict(soak_status.get("heartbeat") or {})
    heartbeat_ts = heartbeat.get("last_heartbeat_timestamp") or soak_status.get("last_heartbeat_timestamp")
    soak_path = root / "paper_soak_status.json"
    if heartbeat_ts:
        try:
            lag_seconds = max(
                0.0,
                float(
                    (
                        _to_utc_timestamp(pd.Timestamp.now("UTC"))
                        - _to_utc_timestamp(heartbeat_ts)
                    ).total_seconds()
                ),
            )
        except Exception:
            lag_seconds = None
        if lag_seconds is not None and lag_seconds > 300.0:
            warnings.append(f"dashboard_detected_stale_heartbeat:{int(lag_seconds)}s")
    try:
        artifact_lag_seconds = max(
            0.0,
            float(
                (
                    pd.Timestamp.now("UTC").timestamp()
                    - (soak_path.stat().st_mtime if soak_path.exists() else root.stat().st_mtime)
                )
            ),
        )
    except Exception:
        artifact_lag_seconds = None
    if artifact_lag_seconds is not None and artifact_lag_seconds > 300.0:
        warnings.append(f"dashboard_detected_stale_artifacts:{int(artifact_lag_seconds)}s")
    return list(dict.fromkeys(warnings))


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
        readiness = build_runtime_readiness(config, mode="portfolio_paper")
        output_root = _resolve_live_output_root(config)
        artifact_freshness = _build_artifact_freshness(output_root, readiness)
        return {
            "run": None,
            "portfolio_status": {},
            "readiness": readiness,
            "paper_soak_status": {},
            "paper_soak_daily_report": {},
            "paper_soak_review": {},
            "baseline_freeze_snapshot": {},
            "capital_refactor_scaffold_inventory": {},
            "validation_truth": _build_validation_truth(readiness),
            "artifact_freshness": artifact_freshness,
            "last_runtime_event": {},
            "operator_warning_list": _build_operator_warning_list(readiness, {}, artifact_freshness),
            "runtime_policy_rows": [],
            "selection_reason_rows": [],
            "recent_selection_reason_rows": [],
            "selection_reason_by_strategy_rows": [],
            "allocator_decision_rows": [],
            "daily_summary_rows": [],
            "trade_rows": [],
            "signal_rows": [],
            "engine_heartbeat": {},
            "engine_cycle_rows": [],
            "symbol_pipeline_rows": [],
            "available_symbols": [],
        }

    portfolio_status = _read_json(root / "portfolio_status.json", {})
    readiness = build_runtime_readiness(config, mode="portfolio_paper")
    paper_soak_status = _read_json(root / "paper_soak_status.json", {})
    paper_soak_daily_report = _read_json(root / "paper_soak_daily_report.json", {})
    paper_soak_review = _read_json(root / "paper_soak_review.json", {})
    baseline_freeze_snapshot = _read_json(root / "baseline_freeze_snapshot.json", {})
    capital_refactor_scaffold_inventory = _read_json(root / "capital_refactor" / "scaffold_inventory.json", {})
    if isinstance(paper_soak_status, dict) and paper_soak_status:
        paper_soak_status["display_warning_list"] = _display_soak_warnings(root, paper_soak_status)
    validation_truth = _build_validation_truth(readiness)
    artifact_freshness = _build_artifact_freshness(root, readiness)
    last_runtime_event = _latest_jsonl_record(root / "paper_runtime_events.jsonl")
    operator_warning_list = _build_operator_warning_list(
        readiness,
        paper_soak_status if isinstance(paper_soak_status, dict) else {},
        artifact_freshness,
    )
    runtime_policy_rows = _read_csv_rows(root / "runtime_policy_summary.csv")
    selection_reason_rows = _read_csv_rows(root / "selection_reason_summary.csv")
    recent_selection_reason_rows = _read_csv_rows(root / "recent_selection_reason_summary.csv")
    selection_reason_by_strategy_rows = _read_csv_rows(root / "selection_reason_by_strategy_summary.csv")
    allocator_decision_rows = _tail_csv_rows(root / "allocator_decisions.csv", limit=120)
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
        "readiness": readiness,
        "paper_soak_status": paper_soak_status,
        "paper_soak_daily_report": paper_soak_daily_report,
        "paper_soak_review": paper_soak_review,
        "baseline_freeze_snapshot": baseline_freeze_snapshot,
        "capital_refactor_scaffold_inventory": capital_refactor_scaffold_inventory,
        "validation_truth": validation_truth,
        "artifact_freshness": artifact_freshness,
        "last_runtime_event": last_runtime_event,
        "operator_warning_list": operator_warning_list,
        "runtime_policy_rows": runtime_policy_rows,
        "selection_reason_rows": selection_reason_rows,
        "recent_selection_reason_rows": recent_selection_reason_rows,
        "selection_reason_by_strategy_rows": selection_reason_by_strategy_rows,
        "allocator_decision_rows": allocator_decision_rows,
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
    runtime_path = _runtime_state_path(folder, symbol=symbol, interval=interval)
    source_path = runtime_path if runtime_path.exists() else _resolve_history_file(
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
