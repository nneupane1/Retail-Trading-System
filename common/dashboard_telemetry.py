"""Telemetry loaders for the live-paper dashboard."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd

from capital.phase1_diagnostics import diagnostics_report_paths
from capital.phase1_evidence_review import review_report_paths
from config import AppConfig
from data.downloader import load_from_csv
from data.resampler import TimeframeBuilder
from common.runtime_readiness import build_runtime_readiness
from market_structure import scaffold_inventory_path as market_structure_scaffold_inventory_path


ROOT_PATH = Path(__file__).resolve().parents[1]
_RAW_CANDLE_CACHE: dict[tuple[str, int], pd.DataFrame] = {}
_RESAMPLED_CANDLE_CACHE: dict[tuple[str, int, str], pd.DataFrame] = {}
_CSV_ROWS_CACHE: dict[tuple[str, int], list[dict[str, Any]]] = {}


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


def _source_mtime_key(path: Path) -> tuple[str, int]:
    return str(path), int(path.stat().st_mtime_ns)


def _load_cached_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    key = _source_mtime_key(path)
    cached = _CSV_ROWS_CACHE.get(key)
    if cached is not None:
        return cached
    stale_keys = [cache_key for cache_key in _CSV_ROWS_CACHE if cache_key[0] == str(path) and cache_key != key]
    for stale_key in stale_keys:
        _CSV_ROWS_CACHE.pop(stale_key, None)
    rows = _read_csv_rows(path)
    _CSV_ROWS_CACHE[key] = rows
    return rows


def _load_cached_source_frame(source_path: Path) -> pd.DataFrame:
    key = _source_mtime_key(source_path)
    cached = _RAW_CANDLE_CACHE.get(key)
    if cached is not None:
        return cached
    stale_keys = [cache_key for cache_key in _RAW_CANDLE_CACHE if cache_key[0] == str(source_path) and cache_key != key]
    for stale_key in stale_keys:
        _RAW_CANDLE_CACHE.pop(stale_key, None)
    frame = load_from_csv(source_path)
    _RAW_CANDLE_CACHE[key] = frame
    return frame


def _load_cached_resampled_frame(source_path: Path, resample_rule: str, config: AppConfig) -> pd.DataFrame:
    source_key = _source_mtime_key(source_path)
    cache_key = (source_key[0], source_key[1], resample_rule)
    cached = _RESAMPLED_CANDLE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    stale_keys = [key for key in _RESAMPLED_CANDLE_CACHE if key[0] == source_key[0] and key[2] == resample_rule and key != cache_key]
    for stale_key in stale_keys:
        _RESAMPLED_CANDLE_CACHE.pop(stale_key, None)
    builder = TimeframeBuilder(config=config)
    frame = builder.resample(_load_cached_source_frame(source_path), resample_rule)
    _RESAMPLED_CANDLE_CACHE[cache_key] = frame
    return frame


def _parse_storage_timestamp(value: str) -> pd.Timestamp:
    return pd.Timestamp(str(value).replace("T", " ").replace(".", ":"))


def _normalized_resample_rule(timeframe: str) -> str:
    normalized = str(timeframe or "").strip()
    aliases = {
        "1m": "1min",
        "3m": "3min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "45m": "45min",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "6h": "6h",
        "8h": "8h",
        "12h": "12h",
        "1d": "1D",
    }
    return aliases.get(normalized.lower(), normalized)


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

    try:
        requested_start = pd.Timestamp(start_date)
    except Exception:
        requested_start = None
    try:
        requested_end = pd.Timestamp(end_date)
    except Exception:
        requested_end = None
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
        start_ok = requested_start is None or candidate_end >= requested_start
        end_ok = requested_end is None or candidate_start <= requested_end
        if start_ok and end_ok:
            candidates.append(
                (
                    requested_end is None or candidate_end >= requested_end,
                    requested_start is None or candidate_start <= requested_start,
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
    rows = _load_cached_csv_rows(path)
    return rows[-limit:] if limit > 0 else rows


def _is_backtest_scenario_dir(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "portfolio_status.json").exists()
        and (path / "trades.csv").exists()
        and (path / "validation_window.json").exists()
    )


def list_backtest_runs(config: AppConfig | None = None) -> list[dict[str, Any]]:
    config = config or AppConfig.load()
    output_root = config.path("backtest", "output_dir")
    if output_root is None or not output_root.exists():
        return []

    scenario_dirs: dict[str, Path] = {}
    for marker in output_root.rglob("validation_window.json"):
        scenario_dir = marker.parent
        if not _is_backtest_scenario_dir(scenario_dir):
            continue
        scenario_dirs[str(scenario_dir)] = scenario_dir

    rows: list[dict[str, Any]] = []
    for path in scenario_dirs.values():
        rows.append(
            {
                "run_id": path.name,
                "path": str(path),
                "has_portfolio_status": True,
                "last_write_time": _artifact_mtime(path),
            }
        )
    rows.sort(key=lambda item: item["last_write_time"], reverse=True)
    return rows


def _row_timestamp(value: Any) -> pd.Timestamp | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return _to_utc_timestamp(value)
    except Exception:
        return None


def _timeframe_band_for_strategy(strategy_type: Any) -> str | None:
    key = str(strategy_type or "").lower()
    if key in {"core", "swing_moonshot"}:
        return "15m"
    if key == "h1_execution":
        return "1h"
    if "h6" in key:
        return "6h"
    if "12h" in key:
        return "12h"
    return None


def _timeframe_window_seconds(timeframe: str) -> int:
    normalized = str(timeframe or "").lower()
    return {
        "1m": 60,
        "1min": 60,
        "15m": 15 * 60,
        "15min": 15 * 60,
        "1h": 60 * 60,
        "6h": 6 * 60 * 60,
        "12h": 12 * 60 * 60,
        "1d": 24 * 60 * 60,
    }.get(normalized, 15 * 60)


def _display_indicator_points(frame: pd.DataFrame, column: str) -> list[dict[str, Any]]:
    if column not in frame.columns:
        return []
    points: list[dict[str, Any]] = []
    for timestamp, value in frame[column].items():
        if pd.isna(value):
            continue
        points.append(
            {
                "time": int(pd.Timestamp(timestamp).timestamp()),
                "value": _safe_float(value),
            }
        )
    return points


def _extract_condition_rows(signal_row: dict[str, Any], allocator_row: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    allocator_row = allocator_row or {}
    checks: list[dict[str, Any]] = []
    mapping = [
        ("bias", signal_row.get("bias")),
        ("breakout", signal_row.get("breakout")),
        ("breakdown", signal_row.get("breakdown")),
        ("compression", signal_row.get("compression")),
        ("bucket_valid", signal_row.get("bucket_valid")),
        ("coordination_active", signal_row.get("coordination_active") or allocator_row.get("coordination_active")),
        ("allocation_brake_active", signal_row.get("allocation_brake_active") or allocator_row.get("allocation_brake_active")),
        ("htf_context_1d", signal_row.get("htf_context_1d")),
        ("htf_context_1w", signal_row.get("htf_context_1w")),
    ]
    for label, value in mapping:
        if value is None or str(value).strip() == "":
            continue
        text = str(value)
        checks.append(
            {
                "label": label,
                "value": text,
                "passed": text.lower() in {"true", "opened", "bullish", "bearish"},
            }
        )
    score = signal_row.get("selection_score") or signal_row.get("score")
    threshold = signal_row.get("threshold") or allocator_row.get("threshold")
    if score is not None and threshold is not None and str(score).strip() and str(threshold).strip():
        try:
            checks.append(
                {
                    "label": "score_vs_threshold",
                    "value": f"{_safe_float(score):.3f} / {_safe_float(threshold):.3f}",
                    "passed": _safe_float(score) >= _safe_float(threshold),
                }
            )
        except Exception:
            pass
    return checks


def _decision_explanation(signal_row: dict[str, Any], allocator_row: dict[str, Any] | None = None) -> str:
    allocator_row = allocator_row or {}
    strategy = str(signal_row.get("strategy_type") or allocator_row.get("strategy_type") or "strategy")
    side = str(signal_row.get("side") or allocator_row.get("side") or "flat")
    final_reason = str(allocator_row.get("final_reason") or signal_row.get("selection_reason") or "observed")
    if final_reason == "opened":
        return (
            f"Trade opened because {strategy} {side} cleared its score threshold, "
            f"passed the visual setup checks, and the allocator admitted the candidate."
        )
    return (
        f"Signal was not opened because the allocator returned '{final_reason}'. "
        f"The chart preserves the rejected candidate for review instead of hiding it."
    )


def _filter_rows_for_window(
    rows: list[dict[str, Any]],
    *,
    symbol: str,
    start_timestamp: pd.Timestamp | None,
    end_timestamp: pd.Timestamp | None,
    time_field: str,
) -> list[dict[str, Any]]:
    symbol_key = str(symbol).upper()
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("symbol", "")).upper() != symbol_key:
            continue
        event_timestamp = _row_timestamp(row.get(time_field))
        if event_timestamp is None:
            continue
        if start_timestamp is not None and event_timestamp < start_timestamp:
            continue
        if end_timestamp is not None and event_timestamp > end_timestamp:
            continue
        filtered.append(row)
    return filtered


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


def _resolve_backtest_scenario_root(root: Path) -> Path | None:
    if (
        (root / "portfolio_status.json").exists()
        and (root / "trades.csv").exists()
        and (root / "validation_window.json").exists()
    ):
        return root

    candidates: list[Path] = []
    for candidate in root.rglob("*"):
        if not candidate.is_dir():
            continue
        if (
            (candidate / "portfolio_status.json").exists()
            and (candidate / "trades.csv").exists()
            and (candidate / "validation_window.json").exists()
        ):
            candidates.append(candidate)

    if not candidates:
        return None

    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0]


def _resolve_backtest_parent_root(root: Path, scenario_root: Path) -> Path:
    if (scenario_root.parent / "status.json").exists():
        return scenario_root.parent
    return root


def _read_latest_checkpoint(parent_root: Path) -> dict[str, Any]:
    checkpoint_dir = parent_root / "_checkpoints"
    if not checkpoint_dir.exists():
        return {}
    candidates = sorted(checkpoint_dir.glob("*.checkpoint.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        return {}
    payload = _read_json(candidates[0], {})
    if isinstance(payload, dict):
        payload["path"] = str(candidates[0])
    return payload if isinstance(payload, dict) else {}


def _window_start_end(validation_window: dict[str, Any]) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    start_value = validation_window.get("holdout_start") or validation_window.get("train_start")
    end_value = validation_window.get("holdout_end") or validation_window.get("train_end")
    try:
        start = _to_utc_timestamp(start_value) if start_value else None
        end = _to_utc_timestamp(end_value) if end_value else None
    except Exception:
        return None, None
    return start, end


def _estimated_15m_bars(validation_window: dict[str, Any]) -> int | None:
    start, end = _window_start_end(validation_window)
    if start is None or end is None:
        return None
    total_seconds = max(0.0, float((end - start).total_seconds()))
    return int(total_seconds // (15 * 60))


def _checkpoint_progress_payload(
    checkpoint: dict[str, Any],
    validation_window: dict[str, Any],
) -> dict[str, Any]:
    next_index = _safe_int(checkpoint.get("next_index"), default=0)
    estimated_total_bars = _estimated_15m_bars(validation_window)
    if estimated_total_bars and estimated_total_bars > 0:
        progress_fraction = max(0.0, min(1.0, float(next_index) / float(estimated_total_bars)))
    else:
        progress_fraction = 0.0
    return {
        "path": checkpoint.get("path"),
        "updated_at": checkpoint.get("updated_at"),
        "next_index": next_index,
        "next_candle_time": checkpoint.get("next_candle_time"),
        "estimated_total_bars": estimated_total_bars,
        "progress_fraction": progress_fraction,
        "progress_percent": progress_fraction * 100.0,
    }


def _build_backtest_artifact_freshness(
    scenario_root: Path,
    parent_root: Path,
    readiness: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    summary_path = Path(readiness["summary_path"]) if readiness.get("summary_path") else parent_root / "missing_summary.json"
    report_path = (
        Path(readiness["promotion_readiness_report_path"])
        if readiness.get("promotion_readiness_report_path")
        else parent_root / "missing_promotion_readiness_report.json"
    )
    checkpoint = _read_latest_checkpoint(parent_root)
    checkpoint_path = Path(checkpoint["path"]) if checkpoint.get("path") else parent_root / "_checkpoints" / "missing.checkpoint.json"
    return {
        "backtest_portfolio_status": _artifact_status(scenario_root / "portfolio_status.json", stale_after_seconds=120.0),
        "backtest_portfolio_runtime_state": _artifact_status(scenario_root / "portfolio_runtime_state.json", stale_after_seconds=120.0),
        "backtest_trades": _artifact_status(scenario_root / "trades.csv", stale_after_seconds=120.0),
        "backtest_signals": _artifact_status(scenario_root / "signals.csv", stale_after_seconds=120.0),
        "backtest_daily_summary": _artifact_status(scenario_root / "daily_summary.csv", stale_after_seconds=120.0),
        "backtest_allocator_decisions": _artifact_status(scenario_root / "allocator_decisions.csv", stale_after_seconds=120.0),
        "backtest_validation_window": _artifact_status(scenario_root / "validation_window.json", stale_after_seconds=7 * 24 * 3600.0),
        "backtest_phase_status": _artifact_status(parent_root / "status.json", stale_after_seconds=120.0),
        "backtest_phase_progress": _artifact_status(parent_root / "scenario_progress.json", stale_after_seconds=120.0),
        "backtest_phase_checkpoint": _artifact_status(checkpoint_path, stale_after_seconds=120.0),
        "production_gate_summary": _artifact_status(summary_path, stale_after_seconds=7 * 24 * 3600.0),
        "promotion_readiness_report": _artifact_status(report_path, stale_after_seconds=7 * 24 * 3600.0),
    }


def _build_synthetic_backtest_heartbeat(
    checkpoint: dict[str, Any],
    replay_status: dict[str, Any],
    validation_window: dict[str, Any],
    runtime_state: dict[str, Any],
    signal_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    next_candle_time = checkpoint.get("next_candle_time")
    signal_count_at_checkpoint = 0
    if next_candle_time:
        signal_count_at_checkpoint = sum(
            1
            for row in signal_rows
            if str(row.get("timestamp", "")) == str(next_candle_time)
        )
    return {
        "status": "replay_running" if str(replay_status.get("stage")) == "running" else "replay_complete",
        "cycle_count": _safe_int(checkpoint.get("next_index"), default=0),
        "cycle_completed_at": checkpoint.get("updated_at") or replay_status.get("updated_at_utc"),
        "latest_recent_1m_timestamp": next_candle_time,
        "symbol_count": len(list(validation_window.get("universe_symbols") or [])),
        "candidates_built": signal_count_at_checkpoint,
        "opened_count": 0,
        "selection_reason_counts": dict(runtime_state.get("selection_reason_counts") or {}),
        "total_recent_1m_rows": None,
        "total_state_1m_rows": None,
    }


def _build_backtest_symbol_pipeline_rows(
    available_symbols: list[str],
    checkpoint: dict[str, Any],
    signal_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current_timestamp = checkpoint.get("next_candle_time")
    recent_signals = signal_rows[-200:] if signal_rows else []
    for symbol in available_symbols:
        symbol_rows = [
            row
            for row in recent_signals
            if str(row.get("symbol", "")).upper() == str(symbol).upper()
        ]
        strategies = sorted(
            {
                str(row.get("strategy_type", ""))
                for row in symbol_rows
                if row.get("strategy_type")
            }
        )
        rows.append(
            {
                "symbol": symbol,
                "latest_recent_1m_timestamp": current_timestamp,
                "recent_rows_1m": 1 if current_timestamp else 0,
                "state_rows_1m": 0,
                "candidate_count": len(symbol_rows),
                "candidate_strategies": ", ".join(strategies),
            }
        )
    return rows


def _backtest_source_path_for_symbol(run_dir: Path, symbol: str) -> Path | None:
    scenario_root = _resolve_backtest_scenario_root(run_dir)
    if scenario_root is None:
        return None
    validation_window = _read_json(scenario_root / "validation_window.json", {})
    symbol_rows = list(validation_window.get("symbol_latest_timestamps") or [])
    symbol_key = str(symbol).upper()
    for row in symbol_rows:
        if str(row.get("symbol", "")).upper() != symbol_key:
            continue
        source_path = row.get("source_path")
        if source_path:
            candidate = Path(str(source_path))
            if not candidate.is_absolute():
                candidate = ROOT_PATH / candidate
            if candidate.exists():
                return candidate
    return None


def _empty_snapshot_payload(readiness: dict[str, Any], artifact_freshness: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "run": None,
        "portfolio_status": {},
        "readiness": readiness,
        "paper_soak_status": {},
        "paper_soak_daily_report": {},
        "paper_soak_review": {},
        "baseline_freeze_snapshot": {},
        "market_structure_scaffold_inventory": {},
        "capital_refactor_scaffold_inventory": {},
        "capital_refactor_phase1_diagnostics": {},
        "capital_refactor_phase1_evidence_review": {},
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
        "replay_status": {},
        "replay_checkpoint": {},
        "validation_window": {},
    }


def _load_backtest_dashboard_snapshot(
    root: Path | None,
    *,
    config: AppConfig,
    trade_limit: int,
    signal_limit: int,
) -> dict[str, Any]:
    readiness = build_runtime_readiness(config, mode="portfolio_paper")
    if root is None or not root.exists():
        artifact_freshness = _build_artifact_freshness(_resolve_live_output_root(config), readiness, config)
        return _empty_snapshot_payload(readiness, artifact_freshness)

    scenario_root = _resolve_backtest_scenario_root(root)
    if scenario_root is None:
        artifact_freshness = _build_artifact_freshness(root, readiness, config)
        return _empty_snapshot_payload(readiness, artifact_freshness)

    parent_root = _resolve_backtest_parent_root(root, scenario_root)
    portfolio_status = _read_json(scenario_root / "portfolio_status.json", {})
    validation_window = _read_json(scenario_root / "validation_window.json", {})
    runtime_state = _read_json(scenario_root / "portfolio_runtime_state.json", {})
    replay_status = _read_json(parent_root / "status.json", {})
    replay_progress = _read_json(parent_root / "scenario_progress.json", {})
    replay_summary = _read_json(parent_root / "summary.json", {})
    replay_report = _read_json(parent_root / "phase2_experiment_report.md", "")
    checkpoint = _read_latest_checkpoint(parent_root)
    checkpoint_payload = _checkpoint_progress_payload(checkpoint, validation_window)

    runtime_policy_rows = _read_csv_rows(scenario_root / "runtime_policy_summary.csv")
    selection_reason_rows = _read_csv_rows(scenario_root / "selection_reason_summary.csv")
    recent_selection_reason_rows = _read_csv_rows(scenario_root / "recent_selection_reason_summary.csv")
    selection_reason_by_strategy_rows = _read_csv_rows(scenario_root / "selection_reason_by_strategy_summary.csv")
    allocator_decision_rows = _tail_csv_rows(scenario_root / "allocator_decisions.csv", limit=120)
    daily_summary_rows = _read_csv_rows(scenario_root / "daily_summary.csv")
    trade_rows = _tail_csv_rows(scenario_root / "trades.csv", limit=trade_limit)
    signal_rows = _tail_csv_rows(scenario_root / "signals.csv", limit=signal_limit)
    latest_trade = trade_rows[-1] if trade_rows else None
    latest_signal = signal_rows[-1] if signal_rows else None
    available_symbols = sorted(
        {
            str(row.get("symbol", "")).upper()
            for row in [*trade_rows, *signal_rows]
            if row.get("symbol")
        }
        | {
            str(symbol).upper()
            for symbol in list(validation_window.get("universe_symbols") or [])
            if symbol
        }
    )

    engine_heartbeat = _build_synthetic_backtest_heartbeat(
        checkpoint,
        replay_status if isinstance(replay_status, dict) else {},
        validation_window if isinstance(validation_window, dict) else {},
        runtime_state if isinstance(runtime_state, dict) else {},
        signal_rows,
    )
    symbol_pipeline_rows = _build_backtest_symbol_pipeline_rows(available_symbols, checkpoint, signal_rows)
    artifact_freshness = _build_backtest_artifact_freshness(scenario_root, parent_root, readiness)
    operator_warning_list = _build_operator_warning_list(readiness, {}, artifact_freshness)
    if str(replay_status.get("stage") or "") == "running":
        operator_warning_list.append("backtest_replay_running")
    operator_warning_list = list(dict.fromkeys(operator_warning_list))

    return {
        "run": {
            "run_id": scenario_root.name,
            "path": str(scenario_root),
            "last_write_time": scenario_root.stat().st_mtime,
        },
        "portfolio_status": portfolio_status,
        "readiness": readiness,
        "paper_soak_status": {},
        "paper_soak_daily_report": {},
        "paper_soak_review": {},
        "baseline_freeze_snapshot": {},
        "market_structure_scaffold_inventory": _read_json(
            market_structure_scaffold_inventory_path(config.root_dir),
            {},
        ),
        "capital_refactor_scaffold_inventory": {},
        "capital_refactor_phase1_diagnostics": {},
        "capital_refactor_phase1_evidence_review": {},
        "validation_truth": _build_validation_truth(readiness),
        "artifact_freshness": artifact_freshness,
        "last_runtime_event": {},
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
        "engine_cycle_rows": [],
        "symbol_pipeline_rows": symbol_pipeline_rows,
        "latest_trade": latest_trade,
        "latest_signal": latest_signal,
        "available_symbols": available_symbols,
        "replay_status": {
            **(replay_status if isinstance(replay_status, dict) else {}),
            "scenario_progress": replay_progress,
            "summary_exists": bool(replay_summary),
            "report_exists": bool(replay_report),
        },
        "replay_checkpoint": checkpoint_payload,
        "validation_window": validation_window,
    }


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


def _build_artifact_freshness(
    root: Path,
    readiness: dict[str, Any],
    config: AppConfig,
) -> dict[str, dict[str, Any]]:
    summary_path = Path(readiness["summary_path"]) if readiness.get("summary_path") else root / "missing_summary.json"
    report_path = (
        Path(readiness["promotion_readiness_report_path"])
        if readiness.get("promotion_readiness_report_path")
        else root / "missing_promotion_readiness_report.json"
    )
    phase1_paths = diagnostics_report_paths(config)
    phase1_review_paths = review_report_paths(config)
    artifacts = {
        "baseline_freeze_snapshot": _artifact_status(root / "baseline_freeze_snapshot.json", stale_after_seconds=24 * 3600.0),
        "market_structure_scaffold_inventory": _artifact_status(
            market_structure_scaffold_inventory_path(config.root_dir),
            stale_after_seconds=7 * 24 * 3600.0,
        ),
        "capital_refactor_phase1_diagnostics_summary": _artifact_status(
            phase1_paths["diagnostics_summary"],
            stale_after_seconds=7 * 24 * 3600.0,
        ),
        "capital_refactor_phase1_rejection_shadow_book": _artifact_status(
            phase1_paths["rejection_shadow_book"],
            stale_after_seconds=7 * 24 * 3600.0,
        ),
        "capital_refactor_phase1_capital_blocked_winners": _artifact_status(
            phase1_paths["capital_blocked_winners"],
            stale_after_seconds=7 * 24 * 3600.0,
        ),
        "capital_refactor_phase1_top_winner_forensics": _artifact_status(
            phase1_paths["top_winner_forensics"],
            stale_after_seconds=7 * 24 * 3600.0,
        ),
        "capital_refactor_phase1_strategy_bucket_capital_efficiency": _artifact_status(
            phase1_paths["strategy_bucket_capital_efficiency"],
            stale_after_seconds=7 * 24 * 3600.0,
        ),
        "capital_refactor_phase1_opportunity_cost_report": _artifact_status(
            phase1_paths["opportunity_cost_report"],
            stale_after_seconds=7 * 24 * 3600.0,
        ),
        "capital_refactor_phase1_evidence_review_json": _artifact_status(
            phase1_review_paths["json"],
            stale_after_seconds=7 * 24 * 3600.0,
        ),
        "capital_refactor_phase1_evidence_review_md": _artifact_status(
            phase1_review_paths["markdown"],
            stale_after_seconds=7 * 24 * 3600.0,
        ),
        "capital_refactor_phase2_experiment_brief_md": _artifact_status(
            phase1_review_paths["phase2_brief"],
            stale_after_seconds=7 * 24 * 3600.0,
        ),
        "capital_refactor_phase1_review_status": _artifact_status(
            phase1_review_paths["status"],
            stale_after_seconds=7 * 24 * 3600.0,
        ),
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
    mode: str = "paper",
) -> dict[str, Any]:
    config = config or AppConfig.load()
    if str(mode).lower() == "backtest":
        root = Path(run_dir) if run_dir else None
        return _load_backtest_dashboard_snapshot(
            root,
            config=config,
            trade_limit=trade_limit,
            signal_limit=signal_limit,
        )

    root = Path(run_dir) if run_dir else latest_live_run(config=config)
    if root is None or not root.exists():
        readiness = build_runtime_readiness(config, mode="portfolio_paper")
        output_root = _resolve_live_output_root(config)
        artifact_freshness = _build_artifact_freshness(output_root, readiness, config)
        return _empty_snapshot_payload(readiness, artifact_freshness)

    portfolio_status = _read_json(root / "portfolio_status.json", {})
    readiness = build_runtime_readiness(config, mode="portfolio_paper")
    paper_soak_status = _read_json(root / "paper_soak_status.json", {})
    paper_soak_daily_report = _read_json(root / "paper_soak_daily_report.json", {})
    paper_soak_review = _read_json(root / "paper_soak_review.json", {})
    baseline_freeze_snapshot = _read_json(root / "baseline_freeze_snapshot.json", {})
    market_structure_scaffold_inventory = _read_json(
        market_structure_scaffold_inventory_path(config.root_dir),
        {},
    )
    capital_refactor_scaffold_inventory = _read_json(root / "capital_refactor" / "scaffold_inventory.json", {})
    capital_refactor_phase1_diagnostics = _read_json(
        diagnostics_report_paths(config)["diagnostics_summary"],
        {},
    )
    capital_refactor_phase1_evidence_review = _read_json(
        review_report_paths(config)["json"],
        {},
    )
    if isinstance(paper_soak_status, dict) and paper_soak_status:
        paper_soak_status["display_warning_list"] = _display_soak_warnings(root, paper_soak_status)
    validation_truth = _build_validation_truth(readiness)
    artifact_freshness = _build_artifact_freshness(root, readiness, config)
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
        "market_structure_scaffold_inventory": market_structure_scaffold_inventory,
        "capital_refactor_scaffold_inventory": capital_refactor_scaffold_inventory,
        "capital_refactor_phase1_diagnostics": capital_refactor_phase1_diagnostics,
        "capital_refactor_phase1_evidence_review": capital_refactor_phase1_evidence_review,
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
        "replay_status": {},
        "replay_checkpoint": {},
        "validation_window": {},
    }


def load_symbol_candles(
    symbol: str,
    *,
    timeframe: str = "15m",
    limit: int = 500,
    config: AppConfig | None = None,
    run_dir: str | Path | None = None,
    mode: str = "paper",
    until_time: Any = None,
) -> dict[str, Any]:
    config = config or AppConfig.load()
    symbol = str(symbol).upper()
    interval = config.require("binance", "default_interval")
    mode_normalized = str(mode or "paper").lower()
    folder = config.path("storage", "base_path") / symbol / interval
    runtime_path = _runtime_state_path(folder, symbol=symbol, interval=interval)

    source_path: Path | None = None
    if mode_normalized == "backtest" and run_dir:
        source_path = _backtest_source_path_for_symbol(Path(run_dir), symbol)
    if source_path is None:
        source_path = runtime_path if runtime_path.exists() else _resolve_history_file(
            folder,
            symbol=symbol,
            interval=interval,
            start_date=config.require("history", "start_date"),
            end_date=config.require("history", "end_date"),
        )
    if source_path is None:
        raise FileNotFoundError(f"No base history found for {symbol}.")

    df_1m = _load_cached_source_frame(source_path)
    resample_rule = _normalized_resample_rule(timeframe)
    if str(timeframe).lower() in {"1m", "1min"}:
        frame = df_1m.copy()
    else:
        frame = _load_cached_resampled_frame(source_path, resample_rule, config).copy()

    if until_time is not None and str(until_time).strip() != "":
        try:
            if isinstance(until_time, (int, float)):
                cutoff = pd.Timestamp(float(until_time), unit="s", tz="UTC")
            else:
                text_value = str(until_time).strip()
                if text_value.replace(".", "", 1).isdigit():
                    cutoff = pd.Timestamp(float(text_value), unit="s", tz="UTC")
                else:
                    cutoff = _to_utc_timestamp(text_value)
            frame_index = pd.DatetimeIndex(frame.index)
            if frame_index.tz is None:
                frame_index = frame_index.tz_localize("UTC")
            else:
                frame_index = frame_index.tz_convert("UTC")
            frame = frame.loc[frame_index <= cutoff]
        except Exception:
            pass

    if limit:
        frame = frame.tail(int(limit))

    display_frame = frame.copy()
    if not display_frame.empty:
        typical_price = (display_frame["high"] + display_frame["low"] + display_frame["close"]) / 3.0
        display_frame["ema_20"] = display_frame["close"].ewm(span=20, adjust=False).mean()
        display_frame["ema_50"] = display_frame["close"].ewm(span=50, adjust=False).mean()
        cumulative_volume = display_frame["volume"].cumsum().replace(0, pd.NA)
        display_frame["vwap_display"] = (typical_price * display_frame["volume"]).cumsum() / cumulative_volume

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

    window_start = _row_timestamp(candles[0]["timestamp"]) if candles else None
    window_end = _row_timestamp(candles[-1]["timestamp"]) if candles else None
    replay_checkpoint_timestamp = None
    trade_events: list[dict[str, Any]] = []
    decision_events: list[dict[str, Any]] = []
    rejected_markers: list[dict[str, Any]] = []
    debug: dict[str, Any] = {
        "selected_symbol": symbol,
        "selected_timeframe": timeframe,
        "candle_count": len(candles),
        "first_candle_timestamp": candles[0]["timestamp"] if candles else None,
        "last_candle_timestamp": candles[-1]["timestamp"] if candles else None,
        "replay_checkpoint_timestamp": None,
        "source_path": str(source_path),
        "run_id": Path(run_dir).name if run_dir else None,
        "trade_events_count": 0,
        "decision_events_count": 0,
        "rejected_events_count": 0,
    }
    if mode_normalized == "backtest" and run_dir:
        run_path = Path(run_dir)
        scenario_root = _resolve_backtest_scenario_root(run_path)
        if scenario_root is not None:
            parent_root = _resolve_backtest_parent_root(run_path, scenario_root)
            checkpoint_payload = _read_latest_checkpoint(parent_root)
            replay_checkpoint_timestamp = checkpoint_payload.get("next_candle_time")
            debug["replay_checkpoint_timestamp"] = replay_checkpoint_timestamp

            window_padding = pd.Timedelta(seconds=_timeframe_window_seconds(timeframe) * 6)
            padded_start = window_start - window_padding if window_start is not None else None
            padded_end = window_end + window_padding if window_end is not None else None
            trade_rows = _filter_rows_for_window(
                _tail_csv_rows(scenario_root / "trades.csv", limit=12000),
                symbol=symbol,
                start_timestamp=padded_start,
                end_timestamp=padded_end,
                time_field="entry_time",
            )
            signal_rows = _filter_rows_for_window(
                _tail_csv_rows(scenario_root / "signals.csv", limit=24000),
                symbol=symbol,
                start_timestamp=padded_start,
                end_timestamp=padded_end,
                time_field="timestamp",
            )
            allocator_rows = _filter_rows_for_window(
                _tail_csv_rows(scenario_root / "allocator_decisions.csv", limit=24000),
                symbol=symbol,
                start_timestamp=padded_start,
                end_timestamp=padded_end,
                time_field="timestamp",
            )
            trade_events = _build_trade_events(trade_rows)
            decision_events = _build_decision_events(signal_rows, allocator_rows)
            rejected_markers = _build_rejected_markers(decision_events)
            debug["trade_events_count"] = len(trade_events)
            debug["decision_events_count"] = len(decision_events)
            debug["rejected_events_count"] = sum(1 for event in decision_events if not event.get("accepted", False))
            debug["source_run_path"] = str(scenario_root)

    trade_markers = build_trade_markers(trade_events, symbol=symbol)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "source_path": str(source_path),
        "candles": candles,
        "markers": [*trade_markers, *rejected_markers],
        "trade_events": trade_events,
        "decision_events": decision_events,
        "indicators": {
            "ema_20": _display_indicator_points(display_frame, "ema_20"),
            "ema_50": _display_indicator_points(display_frame, "ema_50"),
            "vwap_display": _display_indicator_points(display_frame, "vwap_display"),
        },
        "replay_checkpoint_timestamp": replay_checkpoint_timestamp,
        "window_start_timestamp": candles[0]["timestamp"] if candles else None,
        "window_end_timestamp": candles[-1]["timestamp"] if candles else None,
        "debug": debug,
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


def _build_trade_events(trade_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in trade_rows:
        entry_time = _row_timestamp(row.get("entry_time"))
        exit_time = _row_timestamp(row.get("exit_time"))
        side = str(row.get("side", "flat")).lower()
        events.append(
            {
                "kind": "trade",
                "trade_id": row.get("trade_id"),
                "symbol": row.get("symbol"),
                "side": side,
                "strategy_type": row.get("strategy_type"),
                "timeframe_band": _timeframe_band_for_strategy(row.get("strategy_type")),
                "entry_time": row.get("entry_time"),
                "entry_time_unix": int(entry_time.timestamp()) if entry_time is not None else None,
                "exit_time": row.get("exit_time"),
                "exit_time_unix": int(exit_time.timestamp()) if exit_time is not None else None,
                "entry_price": _safe_float(row.get("entry_price")),
                "exit_price": _safe_float(row.get("exit_price")),
                "stop_price": _safe_float(row.get("stop_price")),
                "active_stop_price": _safe_float(row.get("active_stop_price")),
                "score": _safe_float(row.get("selection_score") or row.get("score")),
                "score_bucket": row.get("score_bucket"),
                "capital_lane": row.get("capital_lane"),
                "risk_group": row.get("risk_group"),
                "pnl": _safe_float(row.get("pnl")),
                "pnl_r": _safe_float(row.get("pnl_R") or row.get("pnl_R_initial")),
                "exit_reason": row.get("exit_reason"),
                "trail_state": row.get("trail_state"),
                "convexity_state": row.get("convexity_state"),
                "pyramid_level": _safe_int(row.get("pyramid_level")),
                "holding_bars": _safe_int(row.get("bars_held")),
                "explanation": (
                    f"{row.get('strategy_type', 'strategy')} {side} opened at {row.get('entry_price')} "
                    f"and exited via {row.get('exit_reason') or 'exit'}."
                ),
            }
        )
    return events


def _build_decision_events(
    signal_rows: list[dict[str, Any]],
    allocator_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    signal_map: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for signal_row in signal_rows:
        key = (
            str(signal_row.get("timestamp", "")),
            str(signal_row.get("symbol", "")).upper(),
            str(signal_row.get("strategy_type", "")),
            str(signal_row.get("side", "")).lower(),
        )
        signal_map[key] = signal_row

    events: list[dict[str, Any]] = []
    for row in allocator_rows:
        key = (
            str(row.get("timestamp", "")),
            str(row.get("symbol", "")).upper(),
            str(row.get("strategy_type", "")),
            str(row.get("side", "")).lower(),
        )
        signal_row = signal_map.get(key, {})
        timestamp = _row_timestamp(row.get("timestamp") or signal_row.get("timestamp"))
        accepted = str(row.get("opened") or signal_row.get("selected") or "").lower() == "true"
        final_reason = str(row.get("final_reason") or signal_row.get("selection_reason") or "")
        events.append(
            {
                "kind": "decision",
                "timestamp": row.get("timestamp") or signal_row.get("timestamp"),
                "time_unix": int(timestamp.timestamp()) if timestamp is not None else None,
                "symbol": row.get("symbol") or signal_row.get("symbol"),
                "side": str(row.get("side") or signal_row.get("side") or "flat").lower(),
                "strategy_type": row.get("strategy_type") or signal_row.get("strategy_type"),
                "timeframe_band": _timeframe_band_for_strategy(row.get("strategy_type") or signal_row.get("strategy_type")),
                "accepted": accepted or final_reason == "opened",
                "final_reason": final_reason or "observed",
                "score": _safe_float(signal_row.get("selection_score") or signal_row.get("score") or row.get("selection_score")),
                "score_bucket": signal_row.get("score_bucket"),
                "threshold": _safe_float(signal_row.get("threshold") or row.get("threshold")),
                "capital_lane": row.get("capital_lane") or signal_row.get("capital_lane"),
                "allocation_rank": row.get("allocation_rank") or signal_row.get("allocation_rank"),
                "allocation_priority": _safe_float(row.get("allocation_priority") or signal_row.get("allocation_priority")),
                "blocking_constraint": final_reason if final_reason != "opened" else "",
                "conditions": _extract_condition_rows(signal_row, row),
                "explanation": _decision_explanation(signal_row, row),
            }
        )

    events.sort(key=lambda item: (item.get("time_unix") or 0, str(item.get("strategy_type") or "")))
    return events


def _build_rejected_markers(decision_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    for event in decision_events:
        if event.get("accepted", False):
            continue
        time_unix = event.get("time_unix")
        if time_unix is None:
            continue
        side = str(event.get("side") or "flat").lower()
        markers.append(
            {
                "time": int(time_unix),
                "position": "aboveBar" if side != "long" else "belowBar",
                "color": "#f59e0b",
                "shape": "circle",
                "text": f"rejected {event.get('final_reason')}",
            }
        )
    return markers
