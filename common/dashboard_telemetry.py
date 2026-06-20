"""Telemetry loaders for the live-paper dashboard."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from capital.phase1_diagnostics import diagnostics_report_paths
from capital.phase1_evidence_review import review_report_paths
from config import AppConfig
from common.structural_lab_locator import (
    load_structural_lab_settings_data,
    structural_lab_output_root as resolve_structural_lab_output_root,
    structural_lab_package_root as resolve_structural_lab_package_root,
    structural_lab_settings_paths,
)
from data.downloader import load_from_csv
from data.resampler import TimeframeBuilder
from common.runtime_readiness import build_runtime_readiness
from market_structure import scaffold_inventory_path as market_structure_scaffold_inventory_path


ROOT_PATH = Path(__file__).resolve().parents[1]
_RAW_CANDLE_CACHE: dict[tuple[str, int], pd.DataFrame] = {}
_RESAMPLED_CANDLE_CACHE: dict[tuple[str, int, str], pd.DataFrame] = {}
_CSV_ROWS_CACHE: dict[tuple[str, int], list[dict[str, Any]]] = {}


def _capital_refactor_output_root(config: AppConfig) -> Path:
    return Path(config.require("backtest", "output_dir")) / "capital_refactor"


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


def _safe_number_or_none(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    return None


def _trade_frequency_period(timestamp: pd.Timestamp, period: str) -> str:
    normalized = str(period).lower()
    if normalized == "daily":
        return timestamp.strftime("%Y-%m-%d")
    if normalized == "weekly":
        iso = timestamp.isocalendar()
        return f"{int(iso.year):04d}-W{int(iso.week):02d}"
    if normalized == "monthly":
        return timestamp.strftime("%Y-%m")
    return timestamp.strftime("%Y")


def _top_group_by_pnl(rows: list[dict[str, Any]], key: str) -> str:
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        label = str(row.get(key) or "n/a")
        totals[label] += float(row["realized_pnl"])
    if not totals:
        return "N/A"
    return max(totals.items(), key=lambda item: (item[1], item[0]))[0]


def build_trade_frequency_pnl(
    trade_rows: list[dict[str, Any]],
    *,
    source_files: list[str] | None = None,
) -> dict[str, Any]:
    source_files = source_files or []
    normalized_rows: list[dict[str, Any]] = []
    missing_fields: set[str] = set()
    excluded_open_or_unrealized = 0

    for row in trade_rows:
        close_time = _first_present(row, ("exit_time", "closed_at", "exit_timestamp", "close_time"))
        entry_time = _first_present(row, ("entry_time", "opened_at", "entry_timestamp", "timestamp", "time"))
        timestamp = _row_timestamp(close_time or entry_time)
        if timestamp is None:
            missing_fields.add("timestamp")
            continue

        realized_pnl = _safe_number_or_none(_first_present(row, ("realized_pnl", "pnl", "pnl_value")))
        unrealized_pnl = _safe_number_or_none(_first_present(row, ("unrealized_pnl", "open_pnl")))
        is_open = str(_first_present(row, ("status", "position_status")) or "").lower() in {"open", "active"}
        if realized_pnl is None and unrealized_pnl is not None:
            excluded_open_or_unrealized += 1
            continue
        if is_open and close_time is None and realized_pnl is None:
            excluded_open_or_unrealized += 1
            continue
        if realized_pnl is None:
            missing_fields.add("realized_pnl")
            continue

        net_pnl = _safe_number_or_none(_first_present(row, ("net_pnl", "realized_net_pnl")))
        pnl_r = _safe_number_or_none(_first_present(row, ("r_multiple", "pnl_r", "pnl_R", "pnl_R_initial")))
        side = str(_first_present(row, ("side",)) or "").lower()
        strategy = str(_first_present(row, ("strategy_type", "sleeve", "setup_type", "setup_class")) or "N/A")
        reason = str(_first_present(row, ("exit_reason", "entry_reason", "selection_reason")) or "N/A")

        if side == "":
            missing_fields.add("side")
        if net_pnl is None:
            missing_fields.add("net_pnl")
        if pnl_r is None:
            missing_fields.add("r_multiple")
        if strategy == "N/A":
            missing_fields.add("strategy_type")
        if reason == "N/A":
            missing_fields.add("trade_reason")

        normalized_rows.append(
            {
                "timestamp": timestamp,
                "period_anchor": timestamp,
                "symbol": str(_first_present(row, ("symbol",)) or "N/A").upper(),
                "side": side or "n/a",
                "strategy": strategy,
                "reason": reason,
                "realized_pnl": realized_pnl,
                "net_pnl": net_pnl,
                "pnl_r": pnl_r,
            }
        )

    if not normalized_rows:
        now = pd.Timestamp.now("UTC")
        return {
            "summary": {
                "current_day_trade_count": 0,
                "current_week_trade_count": 0,
                "current_month_trade_count": 0,
                "current_year_trade_count": 0,
                "avg_pnl_per_trade": 0.0,
                "avg_r_per_trade": None,
                "win_rate": 0.0,
                "best_trade_pnl": None,
                "worst_trade_pnl": None,
            },
            "daily": [],
            "weekly": [],
            "monthly": [],
            "yearly": [],
            "metadata": {
                "source_files": source_files,
                "last_updated": now.isoformat(),
                "row_count": 0,
                "missing_fields": sorted(missing_fields),
                "excluded_open_or_unrealized_rows": excluded_open_or_unrealized,
                "pnl_basis": "realized_only",
                "read_only": True,
            },
        }

    normalized_rows.sort(key=lambda item: item["timestamp"])
    anchor = normalized_rows[-1]["timestamp"]

    def build_period_rows(period: str) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in normalized_rows:
            grouped[_trade_frequency_period(row["period_anchor"], period)].append(row)
        rows_out: list[dict[str, Any]] = []
        for period_key, rows_for_period in sorted(grouped.items()):
            pnl_values = [float(item["realized_pnl"]) for item in rows_for_period]
            net_values = [float(item["net_pnl"]) for item in rows_for_period if item["net_pnl"] is not None]
            r_values = [float(item["pnl_r"]) for item in rows_for_period if item["pnl_r"] is not None]
            winning = [value for value in pnl_values if value > 0]
            losing = [value for value in pnl_values if value < 0]
            rows_out.append(
                {
                    "period": period_key,
                    "trade_count": len(rows_for_period),
                    "winning_trades": len(winning),
                    "losing_trades": len(losing),
                    "win_rate": (len(winning) / len(rows_for_period)) if rows_for_period else 0.0,
                    "gross_pnl": sum(pnl_values),
                    "net_pnl": sum(net_values) if net_values else None,
                    "avg_pnl_per_trade": (sum(pnl_values) / len(rows_for_period)) if rows_for_period else 0.0,
                    "median_pnl_per_trade": float(pd.Series(pnl_values).median()) if pnl_values else 0.0,
                    "total_R": sum(r_values) if r_values else None,
                    "avg_R": (sum(r_values) / len(r_values)) if r_values else None,
                    "best_trade_pnl": max(pnl_values) if pnl_values else None,
                    "worst_trade_pnl": min(pnl_values) if pnl_values else None,
                    "top_symbol": _top_group_by_pnl(rows_for_period, "symbol"),
                    "top_strategy_or_sleeve": _top_group_by_pnl(rows_for_period, "strategy"),
                    "top_trade_reason": _top_group_by_pnl(rows_for_period, "reason"),
                    "long_count": sum(1 for item in rows_for_period if item["side"] == "long"),
                    "short_count": sum(1 for item in rows_for_period if item["side"] == "short"),
                }
            )
        return rows_out

    daily = build_period_rows("daily")
    weekly = build_period_rows("weekly")
    monthly = build_period_rows("monthly")
    yearly = build_period_rows("yearly")

    pnl_values = [float(item["realized_pnl"]) for item in normalized_rows]
    r_values = [float(item["pnl_r"]) for item in normalized_rows if item["pnl_r"] is not None]
    current_day = _trade_frequency_period(anchor, "daily")
    current_week = _trade_frequency_period(anchor, "weekly")
    current_month = _trade_frequency_period(anchor, "monthly")
    current_year = _trade_frequency_period(anchor, "yearly")

    def current_trade_count(period_rows: list[dict[str, Any]], period_key: str) -> int:
        for row in period_rows:
            if row["period"] == period_key:
                return int(row["trade_count"])
        return 0

    return {
        "summary": {
            "current_day_trade_count": current_trade_count(daily, current_day),
            "current_week_trade_count": current_trade_count(weekly, current_week),
            "current_month_trade_count": current_trade_count(monthly, current_month),
            "current_year_trade_count": current_trade_count(yearly, current_year),
            "avg_pnl_per_trade": (sum(pnl_values) / len(pnl_values)) if pnl_values else 0.0,
            "avg_r_per_trade": (sum(r_values) / len(r_values)) if r_values else None,
            "win_rate": (sum(1 for value in pnl_values if value > 0) / len(pnl_values)) if pnl_values else 0.0,
            "best_trade_pnl": max(pnl_values) if pnl_values else None,
            "worst_trade_pnl": min(pnl_values) if pnl_values else None,
        },
        "daily": daily,
        "weekly": weekly,
        "monthly": monthly,
        "yearly": yearly,
        "metadata": {
            "source_files": source_files,
            "last_updated": anchor.isoformat(),
            "row_count": len(normalized_rows),
            "missing_fields": sorted(missing_fields),
            "excluded_open_or_unrealized_rows": excluded_open_or_unrealized,
            "pnl_basis": "realized_only",
            "read_only": True,
        },
    }


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
    config: AppConfig,
) -> dict[str, dict[str, Any]]:
    summary_path = Path(readiness["summary_path"]) if readiness.get("summary_path") else parent_root / "missing_summary.json"
    report_path = (
        Path(readiness["promotion_readiness_report_path"])
        if readiness.get("promotion_readiness_report_path")
        else parent_root / "missing_promotion_readiness_report.json"
    )
    checkpoint = _read_latest_checkpoint(parent_root)
    checkpoint_path = Path(checkpoint["path"]) if checkpoint.get("path") else parent_root / "_checkpoints" / "missing.checkpoint.json"
    capital_root = _capital_refactor_output_root(config)
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
        "capital_refactor_master_plan": _artifact_status(capital_root / "master_capital_refactor_plan.json", stale_after_seconds=7 * 24 * 3600.0),
        "capital_refactor_candidate_registry": _artifact_status(capital_root / "candidate_registry.json", stale_after_seconds=7 * 24 * 3600.0),
        "capital_refactor_validation_ladder": _artifact_status(capital_root / "validation_ladder.json", stale_after_seconds=7 * 24 * 3600.0),
        "capital_refactor_promotion_governance": _artifact_status(capital_root / "promotion_governance.json", stale_after_seconds=7 * 24 * 3600.0),
        "capital_refactor_execution_cost_research": _artifact_status(capital_root / "execution_cost_research.json", stale_after_seconds=7 * 24 * 3600.0),
        "capital_refactor_execution_cost_model": _artifact_status(capital_root / "execution_realism" / "execution_cost_model.json", stale_after_seconds=7 * 24 * 3600.0),
        "capital_refactor_execution_cost_sensitivity": _artifact_status(capital_root / "execution_realism" / "execution_cost_sensitivity.json", stale_after_seconds=7 * 24 * 3600.0),
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
        "capital_refactor_master_plan": {},
        "capital_refactor_candidate_registry": {},
        "capital_refactor_validation_ladder": {},
        "capital_refactor_promotion_governance": {},
        "capital_refactor_execution_realism": {},
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
        "trade_frequency_pnl": build_trade_frequency_pnl([], source_files=[]),
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
    trade_frequency_pnl = build_trade_frequency_pnl(
        trade_rows,
        source_files=[str(scenario_root / "trades.csv")],
    )
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
    artifact_freshness = _build_backtest_artifact_freshness(scenario_root, parent_root, readiness, config)
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
        "capital_refactor_master_plan": _read_json(_capital_refactor_output_root(config) / "master_capital_refactor_plan.json", {}),
        "capital_refactor_candidate_registry": _read_json(_capital_refactor_output_root(config) / "candidate_registry.json", {}),
        "capital_refactor_validation_ladder": _read_json(_capital_refactor_output_root(config) / "validation_ladder.json", {}),
        "capital_refactor_promotion_governance": _read_json(_capital_refactor_output_root(config) / "promotion_governance.json", {}),
        "capital_refactor_execution_realism": _read_json(_capital_refactor_output_root(config) / "execution_cost_research.json", {}),
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
        "trade_frequency_pnl": trade_frequency_pnl,
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
    capital_root = _capital_refactor_output_root(config)
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
        "capital_refactor_master_plan": _artifact_status(capital_root / "master_capital_refactor_plan.json", stale_after_seconds=7 * 24 * 3600.0),
        "capital_refactor_candidate_registry": _artifact_status(capital_root / "candidate_registry.json", stale_after_seconds=7 * 24 * 3600.0),
        "capital_refactor_validation_ladder": _artifact_status(capital_root / "validation_ladder.json", stale_after_seconds=7 * 24 * 3600.0),
        "capital_refactor_promotion_governance": _artifact_status(capital_root / "promotion_governance.json", stale_after_seconds=7 * 24 * 3600.0),
        "capital_refactor_execution_cost_research": _artifact_status(capital_root / "execution_cost_research.json", stale_after_seconds=7 * 24 * 3600.0),
        "capital_refactor_execution_cost_model": _artifact_status(capital_root / "execution_realism" / "execution_cost_model.json", stale_after_seconds=7 * 24 * 3600.0),
        "capital_refactor_execution_cost_sensitivity": _artifact_status(capital_root / "execution_realism" / "execution_cost_sensitivity.json", stale_after_seconds=7 * 24 * 3600.0),
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
    capital_refactor_root = _capital_refactor_output_root(config)
    capital_refactor_master_plan = _read_json(capital_refactor_root / "master_capital_refactor_plan.json", {})
    capital_refactor_candidate_registry = _read_json(capital_refactor_root / "candidate_registry.json", {})
    capital_refactor_validation_ladder = _read_json(capital_refactor_root / "validation_ladder.json", {})
    capital_refactor_promotion_governance = _read_json(capital_refactor_root / "promotion_governance.json", {})
    capital_refactor_execution_realism = _read_json(capital_refactor_root / "execution_cost_research.json", {})
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
    trade_frequency_pnl = build_trade_frequency_pnl(
        trade_rows,
        source_files=[str(root / "trades.csv")],
    )
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
        "capital_refactor_master_plan": capital_refactor_master_plan,
        "capital_refactor_candidate_registry": capital_refactor_candidate_registry,
        "capital_refactor_validation_ladder": capital_refactor_validation_ladder,
        "capital_refactor_promotion_governance": capital_refactor_promotion_governance,
        "capital_refactor_execution_realism": capital_refactor_execution_realism,
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
        "trade_frequency_pnl": trade_frequency_pnl,
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


def structural_compounding_lab_root(root_dir: Path | None = None) -> Path:
    return resolve_structural_lab_package_root(root_dir)


def structural_compounding_lab_output_root(root_dir: Path | None = None) -> Path:
    return resolve_structural_lab_output_root(root_dir)


def _read_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return default


def _prefer_existing_structural_artifact(*candidates: Path) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _structural_artifact_paths(root_dir: Path | None = None) -> dict[str, Path]:
    output_root = structural_compounding_lab_output_root(root_dir)
    lab_root = structural_compounding_lab_root(root_dir)
    settings_paths = structural_lab_settings_paths(root_dir)
    refined_root = output_root / "daily_opportunity_definition_refinement_001"
    legacy_root = output_root / "daily_structural_opportunity_001"
    five_year_root = output_root / "five_year_compounding_audit_001"
    long_short_root = output_root / "long_short_edge_repair_audit_001"
    long_damage_patch_root = output_root / "long_damage_control_patch_audit_001"
    frozen_patch_validation_root = output_root / "frozen_patch_validation_audit_001"
    frozen_patch_forensic_root = output_root / "frozen_patch_forensic_integrity_audit_001"
    broad_historical_replay_root = output_root / "broad_historical_structural_replay_001"
    broad_frozen_patch_root = output_root / "broad_frozen_patch_validation_001"
    native_sr_strict_stress_root = output_root / "native_sr_aware_strict_stress_monte_carlo_audit_001"
    return {
        "summary": output_root / "summary.json",
        "master_lab_plan": output_root / "master_lab_plan.md",
        "candidate_registry": output_root / "candidate_registry.json",
        "feature_flags": output_root / "feature_flags.json",
        "equity": output_root / "equity.csv",
        "trades": output_root / "trades.csv",
        "setup_log": output_root / "setup_log.csv",
        "level_log": output_root / "level_log.csv",
        "liquidity_events": output_root / "liquidity_events.csv",
        "profit_vault": output_root / "profit_vault.json",
        "cooldown_log": output_root / "cooldown_log.csv",
        "pyramiding_log": output_root / "pyramiding_log.csv",
        "report": output_root / "report.md",
        "entry_quality_report": output_root / "diagnostics" / "entry_quality_report.json",
        "pullback_quality_report": output_root / "diagnostics" / "pullback_quality_report.json",
        "pullback_type_performance_report": output_root / "diagnostics" / "pullback_type_performance_report.json",
        "personality_performance_report": output_root / "diagnostics" / "personality_performance_report.json",
        "indicator_confluence_report": output_root / "diagnostics" / "indicator_confluence_report.json",
        "pullback_compounding_readiness_report": output_root / "diagnostics" / "pullback_compounding_readiness_report.json",
        "promotion_packet": output_root / "reports" / "promotion_packet.json",
        "five_year_compounding_status": five_year_root / "status.json",
        "five_year_compounding_summary": five_year_root / "five_year_compounding_summary.json",
        "five_year_compounding_report": five_year_root / "five_year_compounding_report.md",
        "five_year_compounding_long_short_breakdown": five_year_root / "diagnostics" / "long_short_compounding_breakdown.csv",
        "five_year_compounding_monthly_summary": five_year_root / "diagnostics" / "monthly_compounding_summary.csv",
        "five_year_compounding_asymmetric_payoff": five_year_root / "diagnostics" / "asymmetric_payoff_report.json",
        "five_year_compounding_moonshot_contribution": five_year_root / "diagnostics" / "moonshot_contribution_report.json",
        "five_year_compounding_scaling_safety": five_year_root / "diagnostics" / "scaling_safety_report.json",
        "five_year_compounding_failure_modes": five_year_root / "diagnostics" / "failure_modes_report.json",
        "long_short_edge_repair_status": long_short_root / "status.json",
        "long_short_edge_repair_summary": long_short_root / "long_short_edge_repair_summary.json",
        "long_short_edge_repair_report": long_short_root / "long_short_edge_repair_report.md",
        "long_short_edge_repair_long_breakdown": long_short_root / "diagnostics" / "long_edge_breakdown.csv",
        "long_short_edge_repair_short_breakdown": long_short_root / "diagnostics" / "short_edge_breakdown.csv",
        "long_short_edge_repair_archetype_breakdown": long_short_root / "diagnostics" / "archetype_expectancy_breakdown.csv",
        "long_short_edge_repair_personality_breakdown": long_short_root / "diagnostics" / "personality_expectancy_breakdown.csv",
        "long_short_edge_repair_long_failure_modes": long_short_root / "diagnostics" / "long_failure_modes.csv",
        "long_short_edge_repair_short_success_modes": long_short_root / "diagnostics" / "short_success_modes.csv",
        "long_short_edge_repair_moonshot_repeatability": long_short_root / "diagnostics" / "moonshot_repeatability_report.csv",
        "long_short_edge_repair_moonshot_dependency": long_short_root / "diagnostics" / "moonshot_dependency_report.json",
        "long_short_edge_repair_long_filters": long_short_root / "diagnostics" / "long_filters_research_candidates.json",
        "long_short_edge_repair_short_preservation": long_short_root / "diagnostics" / "short_preservation_rules.json",
        "long_short_edge_repair_recommendation": long_short_root / "diagnostics" / "edge_repair_recommendation.json",
        "long_short_edge_repair_next_step": long_short_root / "reports" / "next_research_recommendation.json",
        "long_damage_control_patch_status": long_damage_patch_root / "status.json",
        "long_damage_control_patch_summary": long_damage_patch_root / "long_damage_control_patch_summary.json",
        "long_damage_control_patch_report": long_damage_patch_root / "long_damage_control_patch_report.md",
        "long_damage_control_patch_variant_summary": long_damage_patch_root / "diagnostics" / "patch_variant_summary.csv",
        "long_damage_control_patch_trade_replay": long_damage_patch_root / "diagnostics" / "patch_variant_trade_replay.csv",
        "long_damage_control_patch_disabled_longs": long_damage_patch_root / "diagnostics" / "disabled_long_archetype_impact.csv",
        "long_damage_control_patch_preserved_shorts": long_damage_patch_root / "diagnostics" / "preserved_short_edge_impact.csv",
        "long_damage_control_patch_moonshot_dependency": long_damage_patch_root / "diagnostics" / "moonshot_dependency_after_patch.json",
        "long_damage_control_patch_full_capital_curve": long_damage_patch_root / "diagnostics" / "full_capital_compounding_after_patch.csv",
        "long_damage_control_patch_drawdown": long_damage_patch_root / "diagnostics" / "drawdown_after_patch.csv",
        "long_damage_control_patch_best_candidate": long_damage_patch_root / "diagnostics" / "best_patch_candidate.json",
        "long_damage_control_patch_rejected_candidates": long_damage_patch_root / "diagnostics" / "rejected_patch_candidates.json",
        "long_damage_control_patch_recommendation": long_damage_patch_root / "diagnostics" / "research_only_patch_recommendation.json",
        "long_damage_control_patch_next_step": long_damage_patch_root / "reports" / "next_research_recommendation.json",
        "frozen_patch_validation_status": frozen_patch_validation_root / "status.json",
        "frozen_patch_validation_summary": frozen_patch_validation_root / "frozen_patch_validation_summary.json",
        "frozen_patch_validation_report": frozen_patch_validation_root / "frozen_patch_validation_report.md",
        "frozen_patch_validation_rules": frozen_patch_validation_root / "diagnostics" / "frozen_patch_rules.json",
        "frozen_patch_validation_window_summary": frozen_patch_validation_root / "diagnostics" / "validation_window_summary.csv",
        "frozen_patch_validation_year_by_year": frozen_patch_validation_root / "diagnostics" / "year_by_year_validation.csv",
        "frozen_patch_validation_regime_summary": frozen_patch_validation_root / "diagnostics" / "regime_validation_summary.csv",
        "frozen_patch_validation_walk_forward": frozen_patch_validation_root / "diagnostics" / "walk_forward_validation.csv",
        "frozen_patch_validation_out_of_sample": frozen_patch_validation_root / "diagnostics" / "out_of_sample_validation.csv",
        "frozen_patch_validation_trade_replay": frozen_patch_validation_root / "diagnostics" / "frozen_patch_trade_replay.csv",
        "frozen_patch_validation_capital_curve": frozen_patch_validation_root / "diagnostics" / "full_active_capital_validation_curve.csv",
        "frozen_patch_validation_drawdown": frozen_patch_validation_root / "diagnostics" / "drawdown_validation_report.csv",
        "frozen_patch_validation_moonshot_dependency": frozen_patch_validation_root / "diagnostics" / "moonshot_dependency_validation.json",
        "frozen_patch_validation_long_short_breakdown": frozen_patch_validation_root / "diagnostics" / "long_short_validation_breakdown.csv",
        "frozen_patch_validation_failure_modes": frozen_patch_validation_root / "diagnostics" / "validation_failure_modes.csv",
        "frozen_patch_validation_promotion_gate": frozen_patch_validation_root / "diagnostics" / "promotion_gate_report.json",
        "frozen_patch_validation_next_step": frozen_patch_validation_root / "reports" / "next_research_recommendation.json",
        "frozen_patch_forensic_status": frozen_patch_forensic_root / "status.json",
        "frozen_patch_forensic_summary": frozen_patch_forensic_root / "forensic_integrity_summary.json",
        "frozen_patch_forensic_report": frozen_patch_forensic_root / "forensic_integrity_report.md",
        "frozen_patch_forensic_artifact_lineage": frozen_patch_forensic_root / "diagnostics" / "artifact_lineage_report.json",
        "frozen_patch_forensic_data_coverage": frozen_patch_forensic_root / "diagnostics" / "data_coverage_report.json",
        "frozen_patch_forensic_sample_reuse": frozen_patch_forensic_root / "diagnostics" / "sample_reuse_report.json",
        "frozen_patch_forensic_leakage_risk": frozen_patch_forensic_root / "diagnostics" / "leakage_risk_report.json",
        "frozen_patch_forensic_rule_origin": frozen_patch_forensic_root / "diagnostics" / "frozen_rule_origin_report.json",
        "frozen_patch_forensic_source_history": frozen_patch_forensic_root / "diagnostics" / "source_history_availability_report.json",
        "frozen_patch_forensic_validation_gap": frozen_patch_forensic_root / "diagnostics" / "validation_gap_report.json",
        "frozen_patch_forensic_required_next_replay": frozen_patch_forensic_root / "diagnostics" / "required_next_replay_plan.json",
        "frozen_patch_forensic_no_go_risks": frozen_patch_forensic_root / "diagnostics" / "no_go_risks.json",
        "frozen_patch_forensic_next_step": frozen_patch_forensic_root / "reports" / "next_research_recommendation.json",
        "broad_historical_replay_status": broad_historical_replay_root / "status.json",
        "broad_historical_replay_summary": broad_historical_replay_root / "broad_historical_replay_summary.json",
        "broad_historical_replay_report": broad_historical_replay_root / "broad_historical_replay_report.md",
        "broad_historical_replay_source_data_coverage": broad_historical_replay_root / "diagnostics" / "source_data_coverage.json",
        "broad_historical_replay_window_manifest": broad_historical_replay_root / "diagnostics" / "replay_window_manifest.json",
        "broad_historical_replay_yearly_trade_counts": broad_historical_replay_root / "diagnostics" / "yearly_trade_counts.csv",
        "broad_historical_replay_monthly_trade_counts": broad_historical_replay_root / "diagnostics" / "monthly_trade_counts.csv",
        "broad_historical_replay_health_report": broad_historical_replay_root / "diagnostics" / "replay_health_report.json",
        "broad_historical_replay_failure_report": broad_historical_replay_root / "diagnostics" / "replay_failure_report.json",
        "broad_historical_replay_data_gap_report": broad_historical_replay_root / "diagnostics" / "data_gap_report.json",
        "broad_historical_replay_no_future_leakage": broad_historical_replay_root / "diagnostics" / "no_future_leakage_checks.json",
        "broad_historical_replay_generated_ledger_manifest": broad_historical_replay_root / "diagnostics" / "generated_ledger_manifest.json",
        "broad_historical_replay_next_step": broad_historical_replay_root / "reports" / "next_research_recommendation.json",
        "broad_frozen_patch_status": broad_frozen_patch_root / "status.json",
        "broad_frozen_patch_summary": broad_frozen_patch_root / "broad_frozen_patch_summary.json",
        "broad_frozen_patch_report": broad_frozen_patch_root / "broad_frozen_patch_report.md",
        "broad_frozen_patch_raw_vs_patch_json": broad_frozen_patch_root / "diagnostics" / "raw_vs_frozen_patch_comparison.json",
        "broad_frozen_patch_raw_vs_patch_csv": broad_frozen_patch_root / "diagnostics" / "raw_vs_frozen_patch_comparison.csv",
        "broad_frozen_patch_yearly": broad_frozen_patch_root / "diagnostics" / "yearly_raw_vs_patch.csv",
        "broad_frozen_patch_monthly": broad_frozen_patch_root / "diagnostics" / "monthly_raw_vs_patch.csv",
        "broad_frozen_patch_long_short": broad_frozen_patch_root / "diagnostics" / "long_short_raw_vs_patch.json",
        "broad_frozen_patch_archetypes": broad_frozen_patch_root / "diagnostics" / "archetype_raw_vs_patch.csv",
        "broad_frozen_patch_disabled_trade_impact": broad_frozen_patch_root / "diagnostics" / "disabled_trade_impact.csv",
        "broad_frozen_patch_preserved_trade_impact": broad_frozen_patch_root / "diagnostics" / "preserved_trade_impact.csv",
        "broad_frozen_patch_moonshot": broad_frozen_patch_root / "diagnostics" / "moonshot_dependency_broad_patch.json",
        "broad_frozen_patch_execution_costs": broad_frozen_patch_root / "diagnostics" / "execution_cost_sensitivity_broad_patch.json",
        "broad_frozen_patch_drawdown": broad_frozen_patch_root / "diagnostics" / "drawdown_comparison.csv",
        "broad_frozen_patch_profit_vault": broad_frozen_patch_root / "diagnostics" / "profit_vault_comparison.json",
        "broad_frozen_patch_survival": broad_frozen_patch_root / "diagnostics" / "patch_survival_by_year.json",
        "broad_frozen_patch_no_go": broad_frozen_patch_root / "diagnostics" / "no_go_risks.json",
        "broad_frozen_patch_next_step_json": broad_frozen_patch_root / "reports" / "next_research_recommendation.json",
        "broad_frozen_patch_next_step_md": broad_frozen_patch_root / "reports" / "next_research_recommendation.md",
        "native_sr_strict_stress_status": native_sr_strict_stress_root / "status.json",
        "native_sr_strict_stress_summary": native_sr_strict_stress_root / "native_sr_aware_strict_stress_monte_carlo_summary.json",
        "native_sr_strict_stress_report": native_sr_strict_stress_root / "native_sr_aware_strict_stress_monte_carlo_report.md",
        "native_sr_strict_stress_frozen_variant_spec": native_sr_strict_stress_root / "diagnostics" / "frozen_variant_spec.json",
        "native_sr_strict_stress_pf_sanity": native_sr_strict_stress_root / "diagnostics" / "pf_42_sanity_audit.json",
        "native_sr_strict_stress_pre_entry_integrity": native_sr_strict_stress_root / "diagnostics" / "pre_entry_rule_integrity_audit.json",
        "native_sr_strict_stress_matrix": native_sr_strict_stress_root / "diagnostics" / "stress_test_matrix.csv",
        "native_sr_strict_stress_rolling": native_sr_strict_stress_root / "diagnostics" / "rolling_5y_stress_summary.csv",
        "native_sr_strict_stress_monte_carlo_summary": native_sr_strict_stress_root / "diagnostics" / "monte_carlo_summary.json",
        "native_sr_strict_stress_monte_carlo_distribution": native_sr_strict_stress_root / "diagnostics" / "monte_carlo_distribution.csv",
        "native_sr_strict_stress_drawdown_distribution": native_sr_strict_stress_root / "diagnostics" / "monte_carlo_drawdown_distribution.csv",
        "native_sr_strict_stress_ruin_risk": native_sr_strict_stress_root / "diagnostics" / "monte_carlo_ruin_risk.json",
        "native_sr_strict_stress_mission_gap": native_sr_strict_stress_root / "diagnostics" / "mission_gap_report.json",
        "native_sr_strict_stress_promotion_gate": native_sr_strict_stress_root / "diagnostics" / "promotion_gate_report.json",
        "native_sr_strict_stress_next_step": native_sr_strict_stress_root / "reports" / "next_research_recommendation.json",
        "daily_structural_opportunity_status": _prefer_existing_structural_artifact(
            refined_root / "status.json",
            legacy_root / "status.json",
        ),
        "daily_structural_opportunity_summary": _prefer_existing_structural_artifact(
            refined_root / "definition_refinement_summary.json",
            legacy_root / "daily_structural_opportunity_summary.json",
        ),
        "daily_structural_opportunity_report": _prefer_existing_structural_artifact(
            refined_root / "definition_refinement_report.md",
            legacy_root / "daily_structural_opportunity_report.md",
        ),
        "daily_structural_opportunity_top_rows": _prefer_existing_structural_artifact(
            refined_root / "diagnostics" / "top_opportunity_by_day.csv",
            legacy_root / "diagnostics" / "top_opportunity_by_day.csv",
        ),
        "daily_structural_opportunity_candidates": _prefer_existing_structural_artifact(
            refined_root / "diagnostics" / "participation_routed_daily_candidates.csv",
            legacy_root / "diagnostics" / "participation_routed_daily_candidates.csv",
        ),
        "daily_structural_opportunity_participation_distribution": _prefer_existing_structural_artifact(
            refined_root / "diagnostics" / "participation_mode_distribution.json",
            legacy_root / "diagnostics" / "participation_mode_distribution.json",
        ),
        "daily_structural_opportunity_sr_zone_report": _prefer_existing_structural_artifact(
            refined_root / "diagnostics" / "sr_zone_opportunity_report.json",
            legacy_root / "diagnostics" / "sr_zone_opportunity_report.json",
        ),
        "daily_structural_opportunity_breakout_report": _prefer_existing_structural_artifact(
            refined_root / "diagnostics" / "breakout_retest_report.json",
            legacy_root / "diagnostics" / "breakout_retest_report.json",
        ),
        "daily_structural_opportunity_missed_report": _prefer_existing_structural_artifact(
            refined_root / "diagnostics" / "missed_daily_opportunity_report.json",
            legacy_root / "diagnostics" / "missed_daily_opportunity_report.json",
        ),
        "daily_structural_opportunity_too_tight_report": _prefer_existing_structural_artifact(
            refined_root / "diagnostics" / "too_tight_inactivity_report.json",
            legacy_root / "diagnostics" / "too_tight_inactivity_report.json",
        ),
        "daily_structural_opportunity_noise_report": _prefer_existing_structural_artifact(
            refined_root / "diagnostics" / "noise_chasing_guard_report.json",
            legacy_root / "diagnostics" / "noise_chasing_guard_report.json",
        ),
        "daily_structural_opportunity_high_r_report": _prefer_existing_structural_artifact(
            refined_root / "diagnostics" / "high_r_opportunity_report.json",
            legacy_root / "diagnostics" / "high_r_opportunity_report.json",
        ),
        "daily_structural_opportunity_next_step": _prefer_existing_structural_artifact(
            refined_root / "reports" / "next_research_recommendation.json",
            legacy_root / "reports" / "next_research_recommendation.json",
        ),
        "settings": settings_paths["json"],
        "symbols": settings_paths["symbols"],
        "package_root": lab_root,
    }


def _structural_has_run(paths: dict[str, Path]) -> bool:
    return any(
        paths[key].exists()
        for key in (
            "summary",
            "equity",
            "trades",
            "setup_log",
            "level_log",
            "liquidity_events",
            "profit_vault",
            "cooldown_log",
            "pyramiding_log",
            "report",
        )
    )


def _structural_row_time(row: dict[str, Any], *candidates: str) -> pd.Timestamp | None:
    for key in candidates:
        value = row.get(key)
        if value is None or str(value).strip() == "":
            continue
        parsed = _row_timestamp(value)
        if parsed is not None:
            return parsed
    return None


def _structural_rows_by_symbol(rows: list[dict[str, Any]], symbol: str) -> list[dict[str, Any]]:
    symbol_key = str(symbol).upper()
    return [row for row in rows if str(row.get("symbol", symbol_key)).upper() == symbol_key]


def _structural_point_series(rows: list[dict[str, Any]], value_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for row in rows:
        timestamp = _structural_row_time(row, "timestamp", "time", "datetime", "date")
        if timestamp is None:
            continue
        value: float | None = None
        for key in value_keys:
            raw_value = row.get(key)
            if raw_value is None or str(raw_value).strip() == "":
                continue
            try:
                value = float(raw_value)
                break
            except (TypeError, ValueError):
                continue
        if value is None:
            continue
        points.append({"label": timestamp.isoformat(), "value": value})
    return points[-240:]


def _structural_available_symbols(
    symbols_config: dict[str, Any],
    *row_groups: list[dict[str, Any]],
) -> list[str]:
    discovered = {
        str(row.get("symbol", "")).upper()
        for rows in row_groups
        for row in rows
        if row.get("symbol")
    }
    configured = {
        str(symbol).upper()
        for symbol in symbols_config.get("symbols", []) or symbols_config.get("primary", []) or []
    }
    fallback = {"BTCUSDT"}
    return sorted(discovered | configured | fallback)


def _structural_available_timeframes(settings: dict[str, Any]) -> list[str]:
    configured = settings.get("visual_timeframes") or settings.get("timeframes") or settings.get("research_timeframes")
    if isinstance(configured, list) and configured:
        return [str(value) for value in configured]
    return ["1h", "4h", "12h", "1d"]


def load_structural_lab_snapshot(
    *,
    root_dir: Path | None = None,
) -> dict[str, Any]:
    lab_root = structural_compounding_lab_root(root_dir)
    output_root = structural_compounding_lab_output_root(root_dir)
    paths = _structural_artifact_paths(root_dir)

    settings = _read_json(paths["settings"], {})
    symbols_config = _read_json(paths["symbols"], {})
    summary = _read_json(paths["summary"], {})
    candidate_registry = _read_json(paths["candidate_registry"], {})
    feature_flags = _read_json(paths["feature_flags"], {})
    profit_vault = _read_json(paths["profit_vault"], {})
    entry_quality_report = _read_json(paths["entry_quality_report"], {})
    pullback_quality_report = _read_json(paths["pullback_quality_report"], {})
    pullback_type_performance_report = _read_json(paths["pullback_type_performance_report"], {})
    personality_performance_report = _read_json(paths["personality_performance_report"], {})
    indicator_confluence_report = _read_json(paths["indicator_confluence_report"], {})
    pullback_compounding_readiness_report = _read_json(paths["pullback_compounding_readiness_report"], {})
    promotion_packet = _read_json(paths["promotion_packet"], {})
    five_year_compounding_status = _read_json(paths["five_year_compounding_status"], {})
    five_year_compounding_summary = _read_json(paths["five_year_compounding_summary"], {})
    five_year_compounding_asymmetric_payoff = _read_json(paths["five_year_compounding_asymmetric_payoff"], {})
    five_year_compounding_moonshot_contribution = _read_json(paths["five_year_compounding_moonshot_contribution"], {})
    five_year_compounding_scaling_safety = _read_json(paths["five_year_compounding_scaling_safety"], {})
    five_year_compounding_failure_modes = _read_json(paths["five_year_compounding_failure_modes"], {})
    long_short_edge_repair_status = _read_json(paths["long_short_edge_repair_status"], {})
    long_short_edge_repair_summary = _read_json(paths["long_short_edge_repair_summary"], {})
    long_short_edge_repair_moonshot_dependency = _read_json(paths["long_short_edge_repair_moonshot_dependency"], {})
    long_short_edge_repair_long_filters = _read_json(paths["long_short_edge_repair_long_filters"], {})
    long_short_edge_repair_short_preservation = _read_json(paths["long_short_edge_repair_short_preservation"], {})
    long_short_edge_repair_recommendation = _read_json(paths["long_short_edge_repair_recommendation"], {})
    long_short_edge_repair_next_step = _read_json(paths["long_short_edge_repair_next_step"], {})
    long_damage_control_patch_status = _read_json(paths["long_damage_control_patch_status"], {})
    long_damage_control_patch_summary = _read_json(paths["long_damage_control_patch_summary"], {})
    long_damage_control_patch_moonshot_dependency = _read_json(paths["long_damage_control_patch_moonshot_dependency"], {})
    long_damage_control_patch_best_candidate = _read_json(paths["long_damage_control_patch_best_candidate"], {})
    long_damage_control_patch_rejected_candidates = _read_json(paths["long_damage_control_patch_rejected_candidates"], {})
    long_damage_control_patch_recommendation = _read_json(paths["long_damage_control_patch_recommendation"], {})
    long_damage_control_patch_next_step = _read_json(paths["long_damage_control_patch_next_step"], {})
    frozen_patch_validation_status = _read_json(paths["frozen_patch_validation_status"], {})
    frozen_patch_validation_summary = _read_json(paths["frozen_patch_validation_summary"], {})
    frozen_patch_validation_rules = _read_json(paths["frozen_patch_validation_rules"], {})
    frozen_patch_validation_moonshot_dependency = _read_json(paths["frozen_patch_validation_moonshot_dependency"], {})
    frozen_patch_validation_promotion_gate = _read_json(paths["frozen_patch_validation_promotion_gate"], {})
    frozen_patch_validation_next_step = _read_json(paths["frozen_patch_validation_next_step"], {})
    frozen_patch_forensic_status = _read_json(paths["frozen_patch_forensic_status"], {})
    frozen_patch_forensic_summary = _read_json(paths["frozen_patch_forensic_summary"], {})
    frozen_patch_forensic_artifact_lineage = _read_json(paths["frozen_patch_forensic_artifact_lineage"], {})
    frozen_patch_forensic_data_coverage = _read_json(paths["frozen_patch_forensic_data_coverage"], {})
    frozen_patch_forensic_sample_reuse = _read_json(paths["frozen_patch_forensic_sample_reuse"], {})
    frozen_patch_forensic_leakage_risk = _read_json(paths["frozen_patch_forensic_leakage_risk"], {})
    frozen_patch_forensic_rule_origin = _read_json(paths["frozen_patch_forensic_rule_origin"], {})
    frozen_patch_forensic_source_history = _read_json(paths["frozen_patch_forensic_source_history"], {})
    frozen_patch_forensic_validation_gap = _read_json(paths["frozen_patch_forensic_validation_gap"], {})
    frozen_patch_forensic_required_next_replay = _read_json(paths["frozen_patch_forensic_required_next_replay"], {})
    frozen_patch_forensic_no_go_risks = _read_json(paths["frozen_patch_forensic_no_go_risks"], {})
    frozen_patch_forensic_next_step = _read_json(paths["frozen_patch_forensic_next_step"], {})
    broad_historical_replay_status = _read_json(paths["broad_historical_replay_status"], {})
    broad_historical_replay_summary = _read_json(paths["broad_historical_replay_summary"], {})
    broad_historical_replay_source_data_coverage = _read_json(paths["broad_historical_replay_source_data_coverage"], {})
    broad_historical_replay_window_manifest = _read_json(paths["broad_historical_replay_window_manifest"], {})
    broad_historical_replay_health_report = _read_json(paths["broad_historical_replay_health_report"], {})
    broad_historical_replay_failure_report = _read_json(paths["broad_historical_replay_failure_report"], {})
    broad_historical_replay_data_gap_report = _read_json(paths["broad_historical_replay_data_gap_report"], {})
    broad_historical_replay_no_future_leakage = _read_json(paths["broad_historical_replay_no_future_leakage"], {})
    broad_historical_replay_generated_ledger_manifest = _read_json(paths["broad_historical_replay_generated_ledger_manifest"], {})
    broad_historical_replay_next_step = _read_json(paths["broad_historical_replay_next_step"], {})
    broad_frozen_patch_status = _read_json(paths["broad_frozen_patch_status"], {})
    broad_frozen_patch_summary = _read_json(paths["broad_frozen_patch_summary"], {})
    broad_frozen_patch_raw_vs_patch_json = _read_json(paths["broad_frozen_patch_raw_vs_patch_json"], {})
    broad_frozen_patch_long_short = _read_json(paths["broad_frozen_patch_long_short"], {})
    broad_frozen_patch_moonshot = _read_json(paths["broad_frozen_patch_moonshot"], {})
    broad_frozen_patch_execution_costs = _read_json(paths["broad_frozen_patch_execution_costs"], {})
    broad_frozen_patch_profit_vault = _read_json(paths["broad_frozen_patch_profit_vault"], {})
    broad_frozen_patch_survival = _read_json(paths["broad_frozen_patch_survival"], {})
    broad_frozen_patch_no_go = _read_json(paths["broad_frozen_patch_no_go"], {})
    broad_frozen_patch_next_step = _read_json(paths["broad_frozen_patch_next_step_json"], {})
    native_sr_strict_stress_status = _read_json(paths["native_sr_strict_stress_status"], {})
    native_sr_strict_stress_summary = _read_json(paths["native_sr_strict_stress_summary"], {})
    native_sr_strict_stress_frozen_variant_spec = _read_json(paths["native_sr_strict_stress_frozen_variant_spec"], {})
    native_sr_strict_stress_pf_sanity = _read_json(paths["native_sr_strict_stress_pf_sanity"], {})
    native_sr_strict_stress_pre_entry_integrity = _read_json(paths["native_sr_strict_stress_pre_entry_integrity"], {})
    native_sr_strict_stress_monte_carlo_summary = _read_json(paths["native_sr_strict_stress_monte_carlo_summary"], {})
    native_sr_strict_stress_ruin_risk = _read_json(paths["native_sr_strict_stress_ruin_risk"], {})
    native_sr_strict_stress_mission_gap = _read_json(paths["native_sr_strict_stress_mission_gap"], {})
    native_sr_strict_stress_promotion_gate = _read_json(paths["native_sr_strict_stress_promotion_gate"], {})
    native_sr_strict_stress_next_step = _read_json(paths["native_sr_strict_stress_next_step"], {})
    daily_structural_opportunity_summary = _read_json(paths["daily_structural_opportunity_summary"], {})
    daily_structural_opportunity_status = _read_json(paths["daily_structural_opportunity_status"], {})
    daily_structural_opportunity_participation_distribution = _read_json(
        paths["daily_structural_opportunity_participation_distribution"], {}
    )
    daily_structural_opportunity_sr_zone_report = _read_json(paths["daily_structural_opportunity_sr_zone_report"], {})
    daily_structural_opportunity_breakout_report = _read_json(paths["daily_structural_opportunity_breakout_report"], {})
    daily_structural_opportunity_missed_report = _read_json(paths["daily_structural_opportunity_missed_report"], {})
    daily_structural_opportunity_too_tight_report = _read_json(paths["daily_structural_opportunity_too_tight_report"], {})
    daily_structural_opportunity_noise_report = _read_json(paths["daily_structural_opportunity_noise_report"], {})
    daily_structural_opportunity_high_r_report = _read_json(paths["daily_structural_opportunity_high_r_report"], {})
    daily_structural_opportunity_next_step = _read_json(paths["daily_structural_opportunity_next_step"], {})
    trades = _read_csv_rows(paths["trades"])
    setup_log = _read_csv_rows(paths["setup_log"])
    level_log = _read_csv_rows(paths["level_log"])
    liquidity_events = _read_csv_rows(paths["liquidity_events"])
    cooldown_log = _read_csv_rows(paths["cooldown_log"])
    pyramiding_log = _read_csv_rows(paths["pyramiding_log"])
    equity_rows = _read_csv_rows(paths["equity"])
    daily_structural_opportunity_top_rows = _read_csv_rows(paths["daily_structural_opportunity_top_rows"])
    daily_structural_opportunity_candidates = _read_csv_rows(paths["daily_structural_opportunity_candidates"])
    five_year_compounding_long_short_breakdown = _read_csv_rows(paths["five_year_compounding_long_short_breakdown"])
    five_year_compounding_monthly_summary = _read_csv_rows(paths["five_year_compounding_monthly_summary"])
    long_short_edge_repair_long_breakdown = _read_csv_rows(paths["long_short_edge_repair_long_breakdown"])
    long_short_edge_repair_short_breakdown = _read_csv_rows(paths["long_short_edge_repair_short_breakdown"])
    long_short_edge_repair_archetype_breakdown = _read_csv_rows(paths["long_short_edge_repair_archetype_breakdown"])
    long_short_edge_repair_personality_breakdown = _read_csv_rows(paths["long_short_edge_repair_personality_breakdown"])
    long_short_edge_repair_long_failure_modes = _read_csv_rows(paths["long_short_edge_repair_long_failure_modes"])
    long_short_edge_repair_short_success_modes = _read_csv_rows(paths["long_short_edge_repair_short_success_modes"])
    long_short_edge_repair_moonshot_repeatability = _read_csv_rows(paths["long_short_edge_repair_moonshot_repeatability"])
    long_damage_control_patch_variant_summary = _read_csv_rows(paths["long_damage_control_patch_variant_summary"])
    long_damage_control_patch_trade_replay = _read_csv_rows(paths["long_damage_control_patch_trade_replay"])
    long_damage_control_patch_disabled_longs = _read_csv_rows(paths["long_damage_control_patch_disabled_longs"])
    long_damage_control_patch_preserved_shorts = _read_csv_rows(paths["long_damage_control_patch_preserved_shorts"])
    long_damage_control_patch_full_capital_curve = _read_csv_rows(paths["long_damage_control_patch_full_capital_curve"])
    long_damage_control_patch_drawdown = _read_csv_rows(paths["long_damage_control_patch_drawdown"])
    frozen_patch_validation_window_summary = _read_csv_rows(paths["frozen_patch_validation_window_summary"])
    frozen_patch_validation_year_by_year = _read_csv_rows(paths["frozen_patch_validation_year_by_year"])
    frozen_patch_validation_regime_summary = _read_csv_rows(paths["frozen_patch_validation_regime_summary"])
    frozen_patch_validation_walk_forward = _read_csv_rows(paths["frozen_patch_validation_walk_forward"])
    frozen_patch_validation_out_of_sample = _read_csv_rows(paths["frozen_patch_validation_out_of_sample"])
    frozen_patch_validation_trade_replay = _read_csv_rows(paths["frozen_patch_validation_trade_replay"])
    frozen_patch_validation_capital_curve = _read_csv_rows(paths["frozen_patch_validation_capital_curve"])
    frozen_patch_validation_drawdown = _read_csv_rows(paths["frozen_patch_validation_drawdown"])
    frozen_patch_validation_long_short_breakdown = _read_csv_rows(paths["frozen_patch_validation_long_short_breakdown"])
    frozen_patch_validation_failure_modes = _read_csv_rows(paths["frozen_patch_validation_failure_modes"])
    broad_frozen_patch_raw_vs_patch_csv = _read_csv_rows(paths["broad_frozen_patch_raw_vs_patch_csv"])
    broad_frozen_patch_yearly = _read_csv_rows(paths["broad_frozen_patch_yearly"])
    broad_frozen_patch_monthly = _read_csv_rows(paths["broad_frozen_patch_monthly"])
    broad_frozen_patch_archetypes = _read_csv_rows(paths["broad_frozen_patch_archetypes"])
    broad_frozen_patch_disabled_trade_impact = _read_csv_rows(paths["broad_frozen_patch_disabled_trade_impact"])
    broad_frozen_patch_preserved_trade_impact = _read_csv_rows(paths["broad_frozen_patch_preserved_trade_impact"])
    broad_frozen_patch_drawdown = _read_csv_rows(paths["broad_frozen_patch_drawdown"])
    native_sr_strict_stress_matrix = _read_csv_rows(paths["native_sr_strict_stress_matrix"])
    native_sr_strict_stress_rolling = _read_csv_rows(paths["native_sr_strict_stress_rolling"])
    native_sr_strict_stress_monte_carlo_distribution = _read_csv_rows(paths["native_sr_strict_stress_monte_carlo_distribution"])
    native_sr_strict_stress_drawdown_distribution = _read_csv_rows(paths["native_sr_strict_stress_drawdown_distribution"])
    report_markdown = _read_text(paths["report"], "")
    five_year_compounding_report = _read_text(paths["five_year_compounding_report"], "")
    long_short_edge_repair_report = _read_text(paths["long_short_edge_repair_report"], "")
    long_damage_control_patch_report = _read_text(paths["long_damage_control_patch_report"], "")
    frozen_patch_validation_report = _read_text(paths["frozen_patch_validation_report"], "")
    frozen_patch_forensic_report = _read_text(paths["frozen_patch_forensic_report"], "")
    broad_historical_replay_report = _read_text(paths["broad_historical_replay_report"], "")
    broad_frozen_patch_report = _read_text(paths["broad_frozen_patch_report"], "")
    native_sr_strict_stress_report = _read_text(paths["native_sr_strict_stress_report"], "")
    has_run = _structural_has_run(paths)
    trade_frequency_pnl = build_trade_frequency_pnl(
        trades,
        source_files=[str(paths["trades"])],
    )

    available_symbols = _structural_available_symbols(
        symbols_config,
        trades,
        setup_log,
        level_log,
        liquidity_events,
        cooldown_log,
        pyramiding_log,
    )
    available_timeframes = _structural_available_timeframes(settings)

    current_equity = _safe_float(
        summary.get("current_equity")
        or summary.get("ending_equity")
        or summary.get("final_equity")
        or (equity_rows[-1].get("equity") if equity_rows else None),
        default=_safe_float(settings.get("base_capital"), default=20000.0),
    )
    base_capital = _safe_float(
        profit_vault.get("base_capital") or settings.get("base_capital"),
        default=20000.0,
    )
    locked_profit = _safe_float(
        profit_vault.get("locked_profit") or summary.get("locked_profit"),
        default=0.0,
    )
    active_trading_capital = _safe_float(
        profit_vault.get("active_trading_capital") or summary.get("active_trading_capital"),
        default=base_capital,
    )
    floating_profit = _safe_float(
        profit_vault.get("floating_profit") or summary.get("floating_profit"),
        default=max(0.0, current_equity - base_capital - locked_profit),
    )

    summary_metrics = summary.get("metrics", {}) if isinstance(summary.get("metrics"), dict) else {}
    profit_lock_count = _safe_int(summary.get("profit_lock_count"), default=sum(1 for row in pyramiding_log if str(row.get("event_type")) == "profit_lock"))
    add_on_event_count = _safe_int(
        summary.get("add_on_event_count"),
        default=sum(1 for row in pyramiding_log if str(row.get("event_type") or row.get("add_type")) != "profit_lock"),
    )
    cooldown_release_count = sum(1 for row in cooldown_log if str(row.get("event_type")) == "cooldown_release")
    artifact_freshness = {
        key: _artifact_status(path, stale_after_seconds=24 * 60 * 60)
        for key, path in paths.items()
    }
    warnings: list[str] = []
    if not has_run:
        warnings.append("No structural backtest run found yet.")
    if not artifact_freshness["summary"]["exists"]:
        warnings.append("No summary.json found yet.")
    if not artifact_freshness["profit_vault"]["exists"]:
        warnings.append("No profit vault state yet.")

    return {
        "lab": {
            "name": "Structural Compounding Lab",
            "root_path": str(lab_root),
            "output_path": str(output_root),
            "has_run": has_run,
            "empty_state": "No structural backtest run found yet." if not has_run else None,
        },
        "summary": summary,
        "summary_metrics": summary_metrics,
        "settings": settings,
        "symbols_config": symbols_config,
        "candidate_registry": candidate_registry,
        "feature_flags": feature_flags,
        "profit_vault": profit_vault,
        "report_markdown": report_markdown,
        "artifact_freshness": artifact_freshness,
        "available_symbols": available_symbols,
        "available_timeframes": available_timeframes,
        "trade_rows": trades,
        "trade_frequency_pnl": trade_frequency_pnl,
        "setup_rows": setup_log,
        "level_rows": level_log,
        "liquidity_rows": liquidity_events,
        "cooldown_rows": cooldown_log,
        "pyramiding_rows": pyramiding_log,
        "equity_rows": equity_rows,
        "research_reports": {
            "entry_quality_report": entry_quality_report,
            "pullback_quality_report": pullback_quality_report,
            "pullback_type_performance_report": pullback_type_performance_report,
            "personality_performance_report": personality_performance_report,
            "indicator_confluence_report": indicator_confluence_report,
            "pullback_compounding_readiness_report": pullback_compounding_readiness_report,
            "promotion_packet": promotion_packet,
        },
        "five_year_full_capital_audit": {
            "summary": five_year_compounding_summary,
            "status": five_year_compounding_status,
            "report_markdown": five_year_compounding_report,
            "long_short_breakdown": five_year_compounding_long_short_breakdown,
            "monthly_summary": five_year_compounding_monthly_summary,
            "asymmetric_payoff": five_year_compounding_asymmetric_payoff,
            "moonshot_contribution": five_year_compounding_moonshot_contribution,
            "scaling_safety": five_year_compounding_scaling_safety,
            "failure_modes": five_year_compounding_failure_modes,
            "metadata": {
                "last_updated": five_year_compounding_summary.get("resolved_at_utc")
                or five_year_compounding_status.get("resolved_at_utc"),
                "classification": five_year_compounding_summary.get("compounding_readiness_classification")
                or five_year_compounding_status.get("classification"),
                "read_only": True,
            },
        },
        "long_short_edge_repair": {
            "summary": long_short_edge_repair_summary,
            "status": long_short_edge_repair_status,
            "report_markdown": long_short_edge_repair_report,
            "long_edge_breakdown": long_short_edge_repair_long_breakdown,
            "short_edge_breakdown": long_short_edge_repair_short_breakdown,
            "archetype_expectancy_breakdown": long_short_edge_repair_archetype_breakdown,
            "personality_expectancy_breakdown": long_short_edge_repair_personality_breakdown,
            "long_failure_modes": long_short_edge_repair_long_failure_modes,
            "short_success_modes": long_short_edge_repair_short_success_modes,
            "moonshot_repeatability": long_short_edge_repair_moonshot_repeatability,
            "moonshot_dependency": long_short_edge_repair_moonshot_dependency,
            "long_filters_research_candidates": long_short_edge_repair_long_filters,
            "short_preservation_rules": long_short_edge_repair_short_preservation,
            "edge_repair_recommendation": long_short_edge_repair_recommendation,
            "next_research_recommendation": long_short_edge_repair_next_step,
            "metadata": {
                "source_files": [
                    str(paths["trades"]),
                    str(paths["setup_log"]),
                    str(paths["level_log"]),
                    str(paths["liquidity_events"]),
                ],
                "last_updated": long_short_edge_repair_summary.get("resolved_at_utc")
                or long_short_edge_repair_status.get("resolved_at_utc"),
                "classification": long_short_edge_repair_recommendation.get("recommended_next_research_patch")
                or long_short_edge_repair_status.get("state"),
                "read_only": True,
            },
        },
        "long_damage_control_patch": {
            "summary": long_damage_control_patch_summary,
            "status": long_damage_control_patch_status,
            "report_markdown": long_damage_control_patch_report,
            "patch_variant_summary": long_damage_control_patch_variant_summary,
            "patch_variant_trade_replay": long_damage_control_patch_trade_replay,
            "disabled_long_archetype_impact": long_damage_control_patch_disabled_longs,
            "preserved_short_edge_impact": long_damage_control_patch_preserved_shorts,
            "moonshot_dependency_after_patch": long_damage_control_patch_moonshot_dependency,
            "full_capital_compounding_after_patch": long_damage_control_patch_full_capital_curve,
            "drawdown_after_patch": long_damage_control_patch_drawdown,
            "best_patch_candidate": long_damage_control_patch_best_candidate,
            "rejected_patch_candidates": long_damage_control_patch_rejected_candidates,
            "research_only_patch_recommendation": long_damage_control_patch_recommendation,
            "next_research_recommendation": long_damage_control_patch_next_step,
            "metadata": {
                "source_files": [
                    str(paths["trades"]),
                    str(paths["setup_log"]),
                    str(paths["long_short_edge_repair_summary"]),
                ],
                "last_updated": long_damage_control_patch_summary.get("resolved_at_utc")
                or long_damage_control_patch_status.get("resolved_at_utc"),
                "classification": long_damage_control_patch_recommendation.get("recommended_research_only_patch")
                or long_damage_control_patch_status.get("state"),
                "read_only": True,
            },
        },
        "frozen_patch_validation": {
            "summary": frozen_patch_validation_summary,
            "status": frozen_patch_validation_status,
            "report_markdown": frozen_patch_validation_report,
            "frozen_patch_rules": frozen_patch_validation_rules,
            "validation_window_summary": frozen_patch_validation_window_summary,
            "year_by_year_validation": frozen_patch_validation_year_by_year,
            "regime_validation_summary": frozen_patch_validation_regime_summary,
            "walk_forward_validation": frozen_patch_validation_walk_forward,
            "out_of_sample_validation": frozen_patch_validation_out_of_sample,
            "frozen_patch_trade_replay": frozen_patch_validation_trade_replay,
            "full_active_capital_validation_curve": frozen_patch_validation_capital_curve,
            "drawdown_validation_report": frozen_patch_validation_drawdown,
            "moonshot_dependency_validation": frozen_patch_validation_moonshot_dependency,
            "long_short_validation_breakdown": frozen_patch_validation_long_short_breakdown,
            "validation_failure_modes": frozen_patch_validation_failure_modes,
            "promotion_gate_report": frozen_patch_validation_promotion_gate,
            "next_research_recommendation": frozen_patch_validation_next_step,
            "metadata": {
                "source_files": [
                    str(paths["trades"]),
                    str(paths["setup_log"]),
                    str(paths["long_damage_control_patch_summary"]),
                ],
                "last_updated": frozen_patch_validation_summary.get("resolved_at_utc")
                or frozen_patch_validation_status.get("resolved_at_utc"),
                "classification": frozen_patch_validation_promotion_gate.get("classification")
                or frozen_patch_validation_status.get("state"),
                "read_only": True,
            },
        },
        "frozen_patch_forensic_integrity": {
            "summary": frozen_patch_forensic_summary,
            "status": frozen_patch_forensic_status,
            "report_markdown": frozen_patch_forensic_report,
            "artifact_lineage": frozen_patch_forensic_artifact_lineage,
            "data_coverage": frozen_patch_forensic_data_coverage,
            "sample_reuse": frozen_patch_forensic_sample_reuse,
            "leakage_risk": frozen_patch_forensic_leakage_risk,
            "frozen_rule_origin": frozen_patch_forensic_rule_origin,
            "source_history_availability": frozen_patch_forensic_source_history,
            "validation_gap": frozen_patch_forensic_validation_gap,
            "required_next_replay_plan": frozen_patch_forensic_required_next_replay,
            "no_go_risks": frozen_patch_forensic_no_go_risks,
            "next_research_recommendation": frozen_patch_forensic_next_step,
            "metadata": {
                "source_files": [
                    str(paths["trades"]),
                    str(paths["setup_log"]),
                    str(paths["frozen_patch_validation_summary"]),
                    str(paths["long_damage_control_patch_summary"]),
                ],
                "last_updated": frozen_patch_forensic_summary.get("resolved_at_utc")
                or frozen_patch_forensic_status.get("resolved_at_utc"),
                "classification": frozen_patch_forensic_summary.get("current_proof_status_label")
                or frozen_patch_forensic_status.get("state"),
                "read_only": True,
            },
        },
        "broad_historical_structural_replay": {
            "summary": broad_historical_replay_summary,
            "status": broad_historical_replay_status,
            "report_markdown": broad_historical_replay_report,
            "source_data_coverage": broad_historical_replay_source_data_coverage,
            "replay_window_manifest": broad_historical_replay_window_manifest,
            "yearly_trade_counts": _read_csv_rows(paths["broad_historical_replay_yearly_trade_counts"]),
            "monthly_trade_counts": _read_csv_rows(paths["broad_historical_replay_monthly_trade_counts"]),
            "replay_health_report": broad_historical_replay_health_report,
            "replay_failure_report": broad_historical_replay_failure_report,
            "data_gap_report": broad_historical_replay_data_gap_report,
            "no_future_leakage_checks": broad_historical_replay_no_future_leakage,
            "generated_ledger_manifest": broad_historical_replay_generated_ledger_manifest,
            "next_research_recommendation": broad_historical_replay_next_step,
            "metadata": {
                "source_files": [
                    str(paths["broad_historical_replay_status"]),
                    str(paths["broad_historical_replay_summary"]),
                    str(paths["broad_historical_replay_source_data_coverage"]),
                    str(paths["broad_historical_replay_generated_ledger_manifest"]),
                ],
                "last_updated": broad_historical_replay_summary.get("resolved_at_utc")
                or broad_historical_replay_status.get("resolved_at_utc"),
                "classification": broad_historical_replay_summary.get("next_required_step")
                or broad_historical_replay_status.get("state"),
                "read_only": True,
            },
        },
        "broad_frozen_patch_validation": {
            "summary": broad_frozen_patch_summary,
            "status": broad_frozen_patch_status,
            "report_markdown": broad_frozen_patch_report,
            "raw_vs_patch": broad_frozen_patch_raw_vs_patch_json,
            "raw_vs_patch_rows": broad_frozen_patch_raw_vs_patch_csv,
            "yearly_raw_vs_patch": broad_frozen_patch_yearly,
            "monthly_raw_vs_patch": broad_frozen_patch_monthly,
            "long_short_raw_vs_patch": broad_frozen_patch_long_short,
            "archetype_raw_vs_patch": broad_frozen_patch_archetypes,
            "disabled_trade_impact": broad_frozen_patch_disabled_trade_impact,
            "preserved_trade_impact": broad_frozen_patch_preserved_trade_impact,
            "moonshot_dependency": broad_frozen_patch_moonshot,
            "execution_cost_sensitivity": broad_frozen_patch_execution_costs,
            "drawdown_comparison": broad_frozen_patch_drawdown,
            "profit_vault_comparison": broad_frozen_patch_profit_vault,
            "patch_survival_by_year": broad_frozen_patch_survival,
            "no_go_risks": broad_frozen_patch_no_go,
            "next_research_recommendation": broad_frozen_patch_next_step,
            "metadata": {
                "source_files": [
                    str(paths["broad_historical_replay_summary"]),
                    str(paths["broad_historical_replay_status"]),
                    str(paths["frozen_patch_validation_rules"]),
                    str(paths["broad_frozen_patch_summary"]),
                ],
                "last_updated": broad_frozen_patch_summary.get("resolved_at_utc")
                or broad_frozen_patch_status.get("resolved_at_utc"),
                "classification": broad_frozen_patch_summary.get("final_patch_classification")
                or broad_frozen_patch_status.get("state"),
                "read_only": True,
            },
        },
        "native_sr_aware_strict_stress_monte_carlo": {
            "summary": native_sr_strict_stress_summary,
            "status": native_sr_strict_stress_status,
            "report_markdown": native_sr_strict_stress_report,
            "frozen_variant": native_sr_strict_stress_frozen_variant_spec,
            "pf_42_sanity": native_sr_strict_stress_pf_sanity,
            "pre_entry_rule_integrity": native_sr_strict_stress_pre_entry_integrity,
            "stress_test_matrix": native_sr_strict_stress_matrix,
            "rolling_5y_stress_summary": native_sr_strict_stress_rolling,
            "monte_carlo_summary": native_sr_strict_stress_monte_carlo_summary,
            "monte_carlo_distribution": native_sr_strict_stress_monte_carlo_distribution,
            "monte_carlo_drawdown_distribution": native_sr_strict_stress_drawdown_distribution,
            "mission_gap_report": native_sr_strict_stress_mission_gap,
            "promotion_gate_report": native_sr_strict_stress_promotion_gate,
            "monte_carlo_ruin_risk": native_sr_strict_stress_ruin_risk,
            "next_research_recommendation": native_sr_strict_stress_next_step,
            "metadata": {
                "source_files": [
                    str(paths["native_sr_strict_stress_summary"]),
                    str(paths["native_sr_strict_stress_pf_sanity"]),
                    str(paths["native_sr_strict_stress_pre_entry_integrity"]),
                    str(paths["native_sr_strict_stress_monte_carlo_summary"]),
                    str(paths["native_sr_strict_stress_promotion_gate"]),
                ],
                "last_updated": native_sr_strict_stress_summary.get("resolved_at_utc")
                or native_sr_strict_stress_status.get("resolved_at_utc"),
                "classification": native_sr_strict_stress_summary.get("promotion_gate_classification")
                or native_sr_strict_stress_promotion_gate.get("classification")
                or native_sr_strict_stress_status.get("state"),
                "read_only": True,
            },
        },
        "daily_structural_opportunity": {
            "summary": daily_structural_opportunity_summary,
            "status": daily_structural_opportunity_status,
            "top_opportunity_by_day": daily_structural_opportunity_top_rows,
            "candidate_rows": daily_structural_opportunity_candidates,
            "participation_distribution": daily_structural_opportunity_participation_distribution,
            "sr_zone_report": daily_structural_opportunity_sr_zone_report,
            "breakout_retest_report": daily_structural_opportunity_breakout_report,
            "missed_report": daily_structural_opportunity_missed_report,
            "too_tight_report": daily_structural_opportunity_too_tight_report,
            "noise_chasing_report": daily_structural_opportunity_noise_report,
            "high_r_report": daily_structural_opportunity_high_r_report,
            "next_research_recommendation": daily_structural_opportunity_next_step,
            "metadata": {
                "source_files": daily_structural_opportunity_summary.get("source_files", []),
                "last_updated": daily_structural_opportunity_summary.get("resolved_at_utc")
                or daily_structural_opportunity_status.get("resolved_at_utc"),
                "classification": daily_structural_opportunity_summary.get("classification")
                or daily_structural_opportunity_status.get("classification"),
                "read_only": True,
            },
        },
        "overview": {
            "base_capital": base_capital,
            "active_trading_capital": active_trading_capital,
            "locked_profit": locked_profit,
            "floating_profit": floating_profit,
            "current_equity": current_equity,
            "current_compounding_cycle": profit_vault.get("current_compounding_cycle_id")
            or summary.get("current_compounding_cycle")
            or "cycle-0",
            "cooldown_state": (
                "active"
                if str(
                    profit_vault.get("cooldown_active")
                    or summary.get("cooldown_active")
                    or False
                ).lower()
                == "true"
                else "inactive"
            ),
            "total_return_pct": _safe_float(
                summary_metrics.get("total_return_pct") or summary.get("total_return_pct"),
                default=((current_equity + locked_profit - base_capital) / base_capital) if base_capital else 0.0,
            ),
            "max_drawdown_pct": _safe_float(
                summary_metrics.get("max_drawdown_pct") or summary.get("max_drawdown_pct"),
                default=0.0,
            ),
            "win_rate": _safe_float(summary_metrics.get("win_rate") or summary.get("win_rate"), default=0.0),
            "profit_factor": _safe_float(
                summary_metrics.get("profit_factor") or summary.get("profit_factor"),
                default=0.0,
            ),
            "profit_lock_count": profit_lock_count,
            "add_on_event_count": add_on_event_count,
            "cooldown_release_count": cooldown_release_count,
            "r_multiple_summary": summary_metrics.get("r_multiple_summary")
            or summary.get("r_multiple_summary")
            or "No R-multiple summary yet.",
        },
        "structural_state": {
            "latest_trade": trades[-1] if trades else {},
            "latest_setup": setup_log[-1] if setup_log else {},
            "latest_cooldown_event": cooldown_log[-1] if cooldown_log else {},
            "latest_pyramiding_event": pyramiding_log[-1] if pyramiding_log else {},
        },
        "chart_points": {
            "equity": _structural_point_series(equity_rows, ("equity", "balance", "active_equity")),
            "locked_profit": _structural_point_series(pyramiding_log, ("locked_profit", "profit_locked", "vault_after")),
        },
        "warnings": warnings,
    }


def _build_structural_markers(
    trades: list[dict[str, Any]],
    pyramiding_rows: list[dict[str, Any]],
    cooldown_rows: list[dict[str, Any]],
    *,
    symbol: str,
) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    for row in _structural_rows_by_symbol(trades, symbol):
        entry_time = _structural_row_time(row, "entry_time", "entry_timestamp", "opened_at")
        exit_time = _structural_row_time(row, "exit_time", "exit_timestamp", "closed_at")
        side = str(row.get("side", "long")).lower()
        if entry_time is not None:
            markers.append(
                {
                    "time": int(entry_time.timestamp()),
                    "position": "belowBar" if side == "long" else "aboveBar",
                    "color": "#22c55e" if side == "long" else "#f97316",
                    "shape": "arrowUp" if side == "long" else "arrowDown",
                    "text": f"{row.get('setup_class', 'entry')} entry",
                }
            )
        if exit_time is not None:
            pnl_value = _safe_float(row.get("pnl") or row.get("pnl_value"), default=0.0)
            markers.append(
                {
                    "time": int(exit_time.timestamp()),
                    "position": "aboveBar" if side == "long" else "belowBar",
                    "color": "#22c55e" if pnl_value >= 0.0 else "#ef4444",
                    "shape": "circle",
                    "text": f"{row.get('exit_reason', 'exit')} {pnl_value:.2f}",
                }
            )
    for row in _structural_rows_by_symbol(pyramiding_rows, symbol):
        event_time = _structural_row_time(row, "timestamp", "event_time", "added_at")
        if event_time is None:
            continue
        event_type = str(row.get("event_type") or row.get("add_type") or "add-on")
        markers.append(
            {
                "time": int(event_time.timestamp()),
                "position": "aboveBar" if event_type == "profit_lock" else "belowBar",
                "color": "#f59e0b" if event_type == "profit_lock" else "#38bdf8",
                "shape": "circle",
                "text": event_type,
            }
        )
    for row in _structural_rows_by_symbol(cooldown_rows, symbol):
        event_time = _structural_row_time(row, "timestamp", "cooldown_start", "event_time")
        if event_time is None:
            continue
        markers.append(
            {
                "time": int(event_time.timestamp()),
                "position": "aboveBar",
                "color": "#f59e0b",
                "shape": "circle",
                "text": row.get("reason") or "cooldown",
            }
        )
    return markers


def _build_structural_trade_events(trades: list[dict[str, Any]], *, symbol: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in _structural_rows_by_symbol(trades, symbol):
        entry_time = _structural_row_time(row, "entry_time", "entry_timestamp", "opened_at")
        exit_time = _structural_row_time(row, "exit_time", "exit_timestamp", "closed_at")
        side = str(row.get("side", "long")).lower()
        events.append(
            {
                "kind": "trade",
                "trade_id": row.get("trade_id") or row.get("id"),
                "symbol": row.get("symbol", symbol),
                "side": side,
                "strategy_type": row.get("setup_type") or row.get("setup_class") or "structural_compounding",
                "timeframe_band": row.get("execution_timeframe") or row.get("timeframe") or "1h",
                "entry_time": entry_time.isoformat() if entry_time is not None else row.get("entry_time"),
                "entry_time_unix": int(entry_time.timestamp()) if entry_time is not None else None,
                "exit_time": exit_time.isoformat() if exit_time is not None else row.get("exit_time"),
                "exit_time_unix": int(exit_time.timestamp()) if exit_time is not None else None,
                "entry_price": _safe_float(row.get("entry_price")),
                "exit_price": _safe_float(row.get("exit_price")),
                "stop_price": _safe_float(row.get("initial_stop") or row.get("stop_price")),
                "active_stop_price": _safe_float(row.get("trail_stop") or row.get("active_stop_price")),
                "score": _safe_float(row.get("entry_score") or row.get("score")),
                "score_bucket": row.get("setup_class"),
                "capital_lane": row.get("cycle_id") or row.get("compounding_cycle"),
                "risk_group": row.get("risk_profile") or "structural",
                "pnl": _safe_float(row.get("pnl") or row.get("pnl_value")),
                "pnl_r": _safe_float(row.get("r_multiple") or row.get("pnl_r")),
                "exit_reason": row.get("exit_reason"),
                "trail_state": row.get("trailing_state") or row.get("trail_state"),
                "convexity_state": row.get("moonshot_state") or row.get("extension_state"),
                "pyramid_level": _safe_int(row.get("add_on_count") or row.get("pyramid_level")),
                "holding_bars": _safe_int(row.get("holding_bars") or row.get("bars_held")),
                "risk_multiplier": _safe_float(row.get("risk_multiplier"), default=1.0),
                "cooldown_fast_clear_eligible": str(row.get("cooldown_fast_clear_eligible", "")).lower() == "true",
                "explanation": (
                    row.get("entry_reason")
                    or "Structural-compounding trade. Detailed entry reasoning will appear once setup_log.csv is populated."
                ),
            }
        )
    return events


def _build_structural_setup_events(setup_rows: list[dict[str, Any]], *, symbol: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in _structural_rows_by_symbol(setup_rows, symbol):
        timestamp = _structural_row_time(row, "timestamp", "decision_time", "setup_time")
        if timestamp is None:
            continue
        accepted_text = str(row.get("accepted") or row.get("opened") or row.get("selected") or "").lower()
        accepted = accepted_text == "true" or str(row.get("classification", "")).upper() in {"A", "B", "C"}
        structure_score = _safe_float(row.get("structure_score"), default=0.0)
        liquidity_score = _safe_float(row.get("liquidity_score"), default=0.0)
        ema_score = _safe_float(row.get("ema_score"), default=0.0)
        htf_score = _safe_float(row.get("htf_score") or row.get("htf_confirmation_score"), default=0.0)
        volatility_score = _safe_float(row.get("volatility_score"), default=0.0)
        rr_score = _safe_float(row.get("rr_score") or row.get("risk_reward_score"), default=0.0)
        events.append(
            {
                "kind": "decision",
                "timestamp": timestamp.isoformat(),
                "time_unix": int(timestamp.timestamp()),
                "symbol": row.get("symbol", symbol),
                "side": str(row.get("side", "long")).lower(),
                "strategy_type": row.get("setup_type") or "structural_compounding",
                "timeframe_band": row.get("execution_timeframe") or row.get("timeframe") or "1h",
                "accepted": accepted,
                "final_reason": row.get("decision") or row.get("status") or ("opened" if accepted else "review_only"),
                "score": _safe_float(row.get("total_score") or row.get("score")),
                "score_bucket": row.get("classification") or row.get("setup_class"),
                "threshold": _safe_float(row.get("threshold"), default=0.0),
                "capital_lane": row.get("cycle_id") or row.get("compounding_cycle"),
                "allocation_rank": row.get("ranking") or row.get("priority"),
                "allocation_priority": _safe_float(row.get("priority"), default=0.0),
                "blocking_constraint": row.get("blocking_reason") or "",
                "risk_multiplier": _safe_float(row.get("risk_multiplier"), default=1.0),
                "convexity_label": row.get("convexity_label"),
                "conditions": [
                    {"label": "structure", "value": f"{structure_score:.2f}", "passed": structure_score > 0.0},
                    {"label": "liquidity", "value": f"{liquidity_score:.2f}", "passed": liquidity_score > 0.0},
                    {"label": "ema", "value": f"{ema_score:.2f}", "passed": ema_score > 0.0},
                    {"label": "htf", "value": f"{htf_score:.2f}", "passed": htf_score > 0.0},
                    {"label": "volatility", "value": f"{volatility_score:.2f}", "passed": volatility_score > 0.0},
                    {"label": "risk_reward", "value": f"{rr_score:.2f}", "passed": rr_score > 0.0},
                ],
                "explanation": (
                    row.get("explanation")
                    or row.get("entry_reason")
                    or "Structural setup candidate. Research explanations will become richer once setup_log.csv is populated."
                ),
            }
        )
    return events


def _structural_overlay_levels(
    level_rows: list[dict[str, Any]],
    *,
    symbol: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for row in _structural_rows_by_symbol(level_rows, symbol):
        price = _safe_float(row.get("price"))
        if price <= 0:
            continue
        kind = str(row.get("type") or row.get("level_type") or "level")
        if "support" in kind:
            color = "#22c55e"
        elif "resistance" in kind:
            color = "#ef4444"
        elif "mid" in kind:
            color = "#94a3b8"
        else:
            color = "#38bdf8"
        ranked.append(
            {
                "price": price,
                "label": f"{kind} {price:.2f}",
                "kind": kind,
                "color": color,
                "lineStyle": 2 if "prev_" in kind or "range_" in kind else 1,
                "strength": _safe_float(row.get("strength"), default=0.0),
                "timeframe_source": row.get("timeframe_source") or row.get("timeframe") or "1h",
                "touch_count": _safe_int(row.get("touch_count"), default=1),
            }
        )
    ranked.sort(key=lambda item: (item["strength"], item["touch_count"]), reverse=True)
    return ranked[:limit]


def _structural_overlay_liquidity(
    liquidity_rows: list[dict[str, Any]],
    *,
    symbol: str,
    limit: int = 8,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in _structural_rows_by_symbol(liquidity_rows, symbol):
        price = _safe_float(row.get("price"))
        if price <= 0:
            continue
        kind = str(row.get("type") or row.get("event_type") or "liquidity")
        side_implication = str(row.get("side_implication") or row.get("side") or "")
        color = "#f59e0b" if side_implication in {"long", "bullish_if_swept"} else "#c084fc"
        items.append(
            {
                "price": price,
                "label": f"{kind} {price:.2f}",
                "kind": kind,
                "color": color,
                "lineStyle": 0,
                "confidence": _safe_float(row.get("confidence"), default=0.0),
                "side_implication": side_implication,
                "timestamp": row.get("timestamp") or row.get("event_time"),
            }
        )
    items.sort(key=lambda item: (item["confidence"], str(item["timestamp"] or "")), reverse=True)
    return items[:limit]


def load_structural_lab_candles(
    symbol: str,
    *,
    timeframe: str = "1h",
    limit: int = 500,
    config: AppConfig | None = None,
    root_dir: Path | None = None,
    until_time: Any = None,
) -> dict[str, Any]:
    config = config or AppConfig.load()
    structural_cfg = load_structural_lab_settings_data(root_dir)
    symbol = str(symbol).upper()
    data_block = structural_cfg.get("data", {}) if isinstance(structural_cfg, dict) else {}
    interval = str(data_block.get("default_interval", "1m"))
    data_base_path_value = data_block.get("base_path")
    if not data_base_path_value:
        raise FileNotFoundError("Structural lab data.base_path is not configured.")
    data_base_path = Path(str(data_base_path_value))
    if not data_base_path.is_absolute():
        data_base_path = (structural_compounding_lab_root(root_dir) / data_base_path).resolve()
    folder = data_base_path / symbol / interval
    source_path = _resolve_history_file(
        folder,
        symbol=symbol,
        interval=interval,
        start_date=str(data_block.get("history_start_date", "2018-01-01")),
        end_date=str(data_block.get("history_end_date", "2026-06-13")),
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
        display_frame["vwap_display"] = (typical_price * display_frame["volume"]).cumsum() / display_frame["volume"].cumsum().replace(0, pd.NA)

    candles: list[dict[str, Any]] = []
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

    paths = _structural_artifact_paths(root_dir)
    summary = _read_json(paths["summary"], {})
    trades = _read_csv_rows(paths["trades"])
    setups = _read_csv_rows(paths["setup_log"])
    level_rows = _read_csv_rows(paths["level_log"])
    liquidity_rows = _read_csv_rows(paths["liquidity_events"])
    cooldown_rows = _read_csv_rows(paths["cooldown_log"])
    pyramiding_rows = _read_csv_rows(paths["pyramiding_log"])
    trade_events = _build_structural_trade_events(trades, symbol=symbol)
    decision_events = _build_structural_setup_events(setups, symbol=symbol)
    markers = _build_structural_markers(trades, pyramiding_rows, cooldown_rows, symbol=symbol)
    structure_levels = _structural_overlay_levels(level_rows, symbol=symbol)
    liquidity_levels = _structural_overlay_liquidity(liquidity_rows, symbol=symbol)
    replay_checkpoint_timestamp = (
        summary.get("replay_checkpoint_timestamp")
        or summary.get("latest_replay_timestamp")
        or (candles[-1]["timestamp"] if candles else None)
    )
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "source_path": str(source_path),
        "candles": candles,
        "markers": markers,
        "trade_events": trade_events,
        "decision_events": decision_events,
        "structure_levels": structure_levels,
        "liquidity_levels": liquidity_levels,
        "indicators": {
            "ema_20": _display_indicator_points(display_frame, "ema_20"),
            "ema_50": _display_indicator_points(display_frame, "ema_50"),
            "vwap_display": _display_indicator_points(display_frame, "vwap_display"),
        },
        "replay_checkpoint_timestamp": replay_checkpoint_timestamp,
        "window_start_timestamp": candles[0]["timestamp"] if candles else None,
        "window_end_timestamp": candles[-1]["timestamp"] if candles else None,
        "debug": {
            "selected_symbol": symbol,
            "selected_timeframe": timeframe,
            "candle_count": len(candles),
            "source_path": str(source_path),
            "lab_root": str(structural_compounding_lab_root(root_dir)),
            "has_structural_run": _structural_has_run(paths),
            "trade_events_count": len(trade_events),
            "decision_events_count": len(decision_events),
            "structure_level_count": len(structure_levels),
            "liquidity_level_count": len(liquidity_levels),
        },
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
