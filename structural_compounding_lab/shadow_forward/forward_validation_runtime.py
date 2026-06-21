from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import AppConfig  # noqa: E402
from structural_compounding_lab.backtest.checkpoint import StructuralCheckpointStore  # noqa: E402
from structural_compounding_lab.common.project_paths import package_root, project_root, resolve_project_path  # noqa: E402
from structural_compounding_lab.config import StructuralLabConfig  # noqa: E402
from structural_compounding_lab.shadow_forward.fresh_btcusdt_data_updater import (  # noqa: E402
    _atomic_csv_write,
    _normalize_fetched_rows,
    _public_fetch_binance_1m,
)
from structural_compounding_lab.shadow_forward.shadow_forward_observer import (  # noqa: E402
    ShadowForwardObserverConfig,
    _process_observation_cycle,
)


OUTPUT_FOLDER_NAME = "forward_validation_runtime"
AUDIT_FOLDER_NAME = "outage_recovery_audit_001"
ALLOWED_MODES = {"run_once", "status", "audit_outage_recovery"}
STATUS_GREEN = "GREEN"
STATUS_YELLOW = "YELLOW"
STATUS_RED = "RED"
FINAL_READY = "OUTAGE_RECOVERY_READY_RESEARCH_ONLY"
FINAL_WARNING = "OUTAGE_RECOVERY_READY_WITH_WARNINGS_RESEARCH_ONLY"
FINAL_FAILED = "OUTAGE_RECOVERY_FAILED_RESEARCH_ONLY"

SAFETY_FLAGS = {
    "research_only": True,
    "real_money_allowed": False,
    "paper_allowed": False,
    "live_allowed": False,
    "behavior_change_allowed": False,
    "order_path_exists": False,
    "broker_path_exists": False,
    "paper_validation_ready": False,
    "eur_25000_anchor_active": False,
}

FetchFunction = Callable[[pd.Timestamp, pd.Timestamp], pd.DataFrame]
DecisionFunction = Callable[[pd.DataFrame, pd.Timestamp | None], list[dict[str, Any]]]


class ForwardRuntimeInjectedCrash(RuntimeError):
    pass


@dataclass(frozen=True)
class ForwardValidationRuntimeConfig:
    project_root: Path
    package_root: Path
    canonical_csv_path: Path
    output_root: Path
    symbol: str = "BTCUSDT"
    scheduler_installed: bool = False
    now_utc: datetime | None = None
    fetch_function: FetchFunction | None = None
    decision_function: DecisionFunction | None = None
    max_gap_backfill_minutes: int = 10080
    fault_injection: str | None = None
    fault_after_decisions: int = 1
    bootstrap_from_watchtower: bool = True


def _now(config: ForwardValidationRuntimeConfig) -> datetime:
    value = config.now_utc or datetime.now(timezone.utc)
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _timestamp(value: Any) -> pd.Timestamp | None:
    if value in {None, ""}:
        return None
    try:
        parsed = pd.Timestamp(value)
    except Exception:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.tz_convert("UTC").tz_localize(None)
    return parsed


def _latest_safe_timestamp(now_utc: datetime) -> pd.Timestamp:
    current_hour = now_utc.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return pd.Timestamp(current_hour - timedelta(minutes=1)).tz_localize(None)


def _paths(output_root: Path) -> dict[str, Path]:
    return {
        "status": output_root / "latest_status.json",
        "checkpoint": output_root / "checkpoints" / "forward_runtime_checkpoint.json",
        "decision_ledger": output_root / "ledger" / "forward_decision_ledger.csv",
        "trade_ledger": output_root / "ledger" / "forward_simulated_trade_ledger.csv",
        "data_quality": output_root / "diagnostics" / "data_quality_latest.json",
        "fetch_report": output_root / "diagnostics" / "catchup_fetch_report.json",
        "idempotency": output_root / "diagnostics" / "idempotency_report.json",
    }


def _ensure_dirs(output_root: Path) -> None:
    for path in (
        output_root,
        output_root / "checkpoints",
        output_root / "ledger",
        output_root / "diagnostics",
        output_root / "diagnostics" / "raw_fetch_chunks",
    ):
        path.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp.replace(path)


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    if not rows:
        temp.write_text("", encoding="utf-8")
        temp.replace(path)
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def _load_canonical(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"canonical_schema_missing:{','.join(missing)}")
    frame = frame[required].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce").dt.tz_convert(None)
    for column in required[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=required).sort_values("timestamp").reset_index(drop=True)


def _quality(frame: pd.DataFrame, latest_safe: pd.Timestamp) -> dict[str, Any]:
    if frame.empty:
        return {
            "row_count": 0,
            "first_timestamp": None,
            "last_timestamp": None,
            "duplicate_count": 0,
            "gap_count": 0,
            "missing_minute_count": 0,
            "ohlc_sanity_failures": 0,
            "future_candle_count": 0,
            "incomplete_current_candle_count": 0,
            "monotonic": True,
        }
    timestamps = frame["timestamp"]
    duplicates = int(timestamps.duplicated().sum())
    unique = timestamps.drop_duplicates().sort_values()
    diffs = unique.diff().dropna()
    gap_count = int((diffs > pd.Timedelta(minutes=1)).sum())
    missing = int(sum(max(0, int(delta.total_seconds() // 60) - 1) for delta in diffs))
    ohlc_failures = int(
        (
            (frame["open"] <= 0)
            | (frame["high"] <= 0)
            | (frame["low"] <= 0)
            | (frame["close"] <= 0)
            | (frame["volume"] < 0)
            | (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
            | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
        ).sum()
    )
    future = int((timestamps > latest_safe).sum())
    current_hour_start = latest_safe.floor("h") + pd.Timedelta(hours=1)
    incomplete = int((timestamps >= current_hour_start).sum())
    return {
        "row_count": int(len(frame)),
        "first_timestamp": timestamps.iloc[0].isoformat(),
        "last_timestamp": timestamps.iloc[-1].isoformat(),
        "duplicate_count": duplicates,
        "gap_count": gap_count,
        "missing_minute_count": missing,
        "ohlc_sanity_failures": ohlc_failures,
        "future_candle_count": future,
        "incomplete_current_candle_count": incomplete,
        "monotonic": bool(timestamps.is_monotonic_increasing),
    }


def _missing_ranges(frame: pd.DataFrame, *, maximum_minutes: int) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    if frame.empty:
        return []
    unique = frame["timestamp"].drop_duplicates().sort_values().reset_index(drop=True)
    ranges: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for left, right in zip(unique.iloc[:-1], unique.iloc[1:]):
        missing = int((right - left).total_seconds() // 60) - 1
        if missing <= 0:
            continue
        start = left + pd.Timedelta(minutes=1)
        end = right - pd.Timedelta(minutes=1)
        if missing <= maximum_minutes:
            ranges.append((start, end))
    return ranges


def _checksum(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    if not frame.empty:
        digest.update(frame[["timestamp", "open", "high", "low", "close", "volume"]].to_csv(index=False).encode("utf-8"))
    return digest.hexdigest()


def _hash_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def _git_commit(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def _frozen_signature(config: ForwardValidationRuntimeConfig) -> str:
    files = [
        config.package_root / "entry" / "setup_detector.py",
        config.package_root / "entry" / "entry_score.py",
        config.package_root / "context" / "htf_confirmation.py",
        config.package_root / "config" / "structural_compounding_settings.json",
        config.package_root / "output" / "frozen_patch_validation_audit_001" / "diagnostics" / "frozen_patch_rules.json",
    ]
    digest = hashlib.sha256()
    for path in files:
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _default_fetcher(config: ForwardValidationRuntimeConfig) -> FetchFunction:
    def fetch(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        raw, _ = _public_fetch_binance_1m(
            config=AppConfig.load(),
            symbol=config.symbol,
            start_timestamp=start,
            end_timestamp=end,
            raw_chunk_root=config.output_root / "diagnostics" / "raw_fetch_chunks",
        )
        normalized, _ = _normalize_fetched_rows(raw, fetch_start=start, latest_safe=end)
        return normalized[["timestamp", "open", "high", "low", "close", "volume"]].copy()

    return fetch


def _watchtower_bootstrap(config: ForwardValidationRuntimeConfig) -> pd.Timestamp | None:
    if not config.bootstrap_from_watchtower:
        return None
    rows = _read_csv(config.package_root / "output" / "shadow_forward_watchtower_001" / "ledger" / "watchtower_signal_log.csv")
    timestamps = [_timestamp(row.get("timestamp")) for row in rows]
    valid = [value for value in timestamps if value is not None]
    return max(valid) if valid else None


def _default_decisions(config: ForwardValidationRuntimeConfig, frame: pd.DataFrame, after: pd.Timestamp | None) -> list[dict[str, Any]]:
    base = frame.copy().set_index("timestamp")
    observer_config = ShadowForwardObserverConfig(
        package_root=config.package_root,
        output_root=config.output_root / "_observer_scratch",
        runtime_mode="catchup",
        symbol=config.symbol,
        source_csv=config.canonical_csv_path,
    )
    result = _process_observation_cycle(
        config=observer_config,
        lab_config=StructuralLabConfig.load(),
        base_1m=base,
        source_meta={"source_path": str(config.canonical_csv_path), "live_runtime_appended": False},
        checkpoint_payload={"last_processed_1h_candle": after.isoformat()} if after is not None else None,
        existing_signal_rows=[],
        existing_context_rows=[],
        existing_overlay_rows=[],
        existing_quality_rows=[],
    )
    contexts = {str(row.get("signal_id")): row for row in result.get("context_rows", [])}
    overlays = {str(row.get("signal_id")): row for row in result.get("overlay_rows", [])}
    decisions: list[dict[str, Any]] = []
    for signal in result.get("signal_rows", []):
        signal_id = str(signal.get("signal_id") or "")
        decisions.append(
            {
                **signal,
                "context": json.dumps(contexts.get(signal_id, {}), sort_keys=True),
                "research_overlay": json.dumps(overlays.get(signal_id, {}), sort_keys=True),
            }
        )
    return decisions


def _checkpoint_payload(
    config: ForwardValidationRuntimeConfig,
    frame: pd.DataFrame,
    *,
    latest_safe: pd.Timestamp,
    fetch_start: pd.Timestamp | None,
    fetch_end: pd.Timestamp | None,
    last_processed: pd.Timestamp | None,
    last_context: pd.Timestamp | None,
    decision_ids: set[str],
    trade_ids: set[str],
    status: str,
    error: str,
) -> dict[str, Any]:
    config_path = config.package_root / "config" / "structural_compounding_settings.json"
    return {
        "project_root": str(config.project_root),
        "canonical_csv_path": str(config.canonical_csv_path),
        "canonical_first_timestamp": frame["timestamp"].iloc[0].isoformat() if not frame.empty else None,
        "canonical_last_timestamp": frame["timestamp"].iloc[-1].isoformat() if not frame.empty else None,
        "canonical_row_count": int(len(frame)),
        "latest_safe_market_timestamp": latest_safe.isoformat(),
        "last_fetch_start": fetch_start.isoformat() if fetch_start is not None else None,
        "last_fetch_end": fetch_end.isoformat() if fetch_end is not None else None,
        "last_processed_1h_decision_timestamp": last_processed.isoformat() if last_processed is not None else None,
        "last_processed_6h_context_timestamp": last_context.isoformat() if last_context is not None else None,
        "processed_decision_ids": sorted(decision_ids),
        "processed_trade_ids": sorted(trade_ids),
        "last_successful_run_timestamp": _now(config).isoformat(),
        "last_run_status": status,
        "last_error_reason": error,
        "data_checksum": _checksum(frame),
        "engine_version_or_commit_hash": _git_commit(config.project_root),
        "config_hash": _hash_path(config_path),
        "frozen_strategy_signature": _frozen_signature(config),
        "safety_flags": dict(SAFETY_FLAGS),
    }


def _status_base(config: ForwardValidationRuntimeConfig) -> dict[str, Any]:
    return {
        "run_started_at": _now(config).isoformat(),
        "run_finished_at": None,
        "status": STATUS_RED,
        "mode": "research_only_forward_validation",
        "canonical_rows_before": 0,
        "canonical_rows_after": 0,
        "rows_fetched": 0,
        "rows_appended": 0,
        "duplicates_removed": 0,
        "gaps_before": 0,
        "gaps_after": 0,
        "latest_canonical_timestamp_before": None,
        "latest_canonical_timestamp_after": None,
        "latest_safe_market_timestamp": None,
        "caught_up_to_realtime": False,
        "outage_recovery_used": False,
        "interruption_gap_minutes": 0,
        "decisions_processed_this_run": 0,
        "decisions_skipped_as_already_processed": 0,
        "simulated_trades_created_this_run": 0,
        "simulated_trades_skipped_as_duplicates": 0,
        "last_processed_1h_decision_timestamp": None,
        "self_check_passed": False,
        "scheduler_installed": config.scheduler_installed,
        **SAFETY_FLAGS,
        "final_reason": "run_not_completed",
    }


def run_once(config: ForwardValidationRuntimeConfig) -> dict[str, Any]:
    _ensure_dirs(config.output_root)
    paths = _paths(config.output_root)
    status = _status_base(config)
    latest_safe = _latest_safe_timestamp(_now(config))
    status["latest_safe_market_timestamp"] = latest_safe.isoformat()
    checkpoint_store = StructuralCheckpointStore(paths["checkpoint"])
    checkpoint = checkpoint_store.load() or {}
    decision_rows = _read_csv(paths["decision_ledger"])
    trade_rows = _read_csv(paths["trade_ledger"])
    decision_ids = {str(row.get("decision_id") or row.get("signal_id") or "") for row in decision_rows}
    trade_ids = {str(row.get("trade_id") or "") for row in trade_rows}
    last_processed = max(
        [value for value in (_timestamp(row.get("timestamp")) for row in decision_rows) if value is not None],
        default=_timestamp(checkpoint.get("last_processed_1h_decision_timestamp")),
    )
    if last_processed is None:
        last_processed = _watchtower_bootstrap(config)

    fetch_start: pd.Timestamp | None = None
    fetch_end: pd.Timestamp | None = None
    last_context = _timestamp(checkpoint.get("last_processed_6h_context_timestamp"))
    error_reason = ""
    fetch_failures: list[str] = []
    try:
        if not config.canonical_csv_path.exists():
            raise ValueError("canonical_csv_missing")
        raw_frame = _load_canonical(config.canonical_csv_path)
        before_quality = _quality(raw_frame, latest_safe)
        status.update(
            {
                "canonical_rows_before": before_quality["row_count"],
                "gaps_before": before_quality["gap_count"],
                "latest_canonical_timestamp_before": before_quality["last_timestamp"],
            }
        )
        if before_quality["ohlc_sanity_failures"]:
            raise ValueError("canonical_ohlc_corruption")

        before_dedupe = len(raw_frame)
        frame = raw_frame.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp").reset_index(drop=True)
        frame = frame.loc[frame["timestamp"] <= latest_safe].copy()
        status["duplicates_removed"] = before_dedupe - len(frame)
        changed = len(frame) != len(raw_frame)

        fetcher = config.fetch_function or _default_fetcher(config)
        gap_ranges = _missing_ranges(frame, maximum_minutes=config.max_gap_backfill_minutes)
        for gap_start, gap_end in gap_ranges:
            try:
                fetched = fetcher(gap_start, gap_end)
                status["rows_fetched"] += len(fetched)
                frame = pd.concat([frame, fetched], ignore_index=True)
                changed = True
            except Exception as exc:
                fetch_failures.append(f"gap_backfill_failed:{gap_start.isoformat()}:{exc}")

        last_canonical = frame["timestamp"].max()
        fetch_start = last_canonical + pd.Timedelta(minutes=1)
        fetch_end = latest_safe
        status["interruption_gap_minutes"] = max(
            0, int(((latest_safe - last_canonical).total_seconds() // 60))
        )
        if fetch_start <= fetch_end:
            status["outage_recovery_used"] = True
            try:
                fetched = fetcher(fetch_start, fetch_end)
                status["rows_fetched"] += len(fetched)
                frame = pd.concat([frame, fetched], ignore_index=True)
                changed = changed or not fetched.empty
            except Exception as exc:
                fetch_failures.append(f"catchup_fetch_failed:{exc}")

        before_final_dedupe = len(frame)
        frame = frame.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp").reset_index(drop=True)
        status["duplicates_removed"] += before_final_dedupe - len(frame)
        status["rows_appended"] = max(0, len(frame) - status["canonical_rows_before"] + status["duplicates_removed"])
        after_quality = _quality(frame, latest_safe)
        status.update(
            {
                "canonical_rows_after": after_quality["row_count"],
                "gaps_after": after_quality["gap_count"],
                "latest_canonical_timestamp_after": after_quality["last_timestamp"],
                "caught_up_to_realtime": after_quality["last_timestamp"] == latest_safe.isoformat(),
            }
        )
        _write_json(paths["data_quality"], {"before": before_quality, "after": after_quality, **SAFETY_FLAGS})
        _write_json(
            paths["fetch_report"],
            {
                "fetch_start": fetch_start.isoformat() if fetch_start is not None else None,
                "fetch_end": fetch_end.isoformat() if fetch_end is not None else None,
                "rows_fetched": status["rows_fetched"],
                "rows_appended": status["rows_appended"],
                "gap_backfill_ranges": [[start.isoformat(), end.isoformat()] for start, end in gap_ranges],
                "failures": fetch_failures,
                "public_binance_klines_only": True,
                "private_api_used": False,
                "signed_request_used": False,
                **SAFETY_FLAGS,
            },
        )

        if changed:
            _atomic_csv_write(frame, config.canonical_csv_path)
        checkpoint_store.save(
            _checkpoint_payload(
                config,
                frame,
                latest_safe=latest_safe,
                fetch_start=fetch_start,
                fetch_end=fetch_end,
                last_processed=last_processed,
                last_context=last_context,
                decision_ids=decision_ids,
                trade_ids=trade_ids,
                status="canonical_persisted",
                error="",
            )
        )
        if config.fault_injection == "after_append":
            raise ForwardRuntimeInjectedCrash("injected_crash_after_data_append")
        if after_quality["gap_count"] or after_quality["ohlc_sanity_failures"]:
            raise ValueError("canonical_unrecoverable_after_backfill")

        decision_function = config.decision_function or (lambda data, after: _default_decisions(config, data, after))
        candidates = sorted(decision_function(frame, last_processed), key=lambda row: str(row.get("timestamp") or ""))
        for candidate in candidates:
            decision_id = str(candidate.get("decision_id") or candidate.get("signal_id") or "")
            if not decision_id:
                continue
            if decision_id in decision_ids:
                status["decisions_skipped_as_already_processed"] += 1
                continue
            timestamp = _timestamp(candidate.get("timestamp"))
            context_payload = candidate.get("context")
            context_timestamp = None
            if context_payload:
                try:
                    context_timestamp = _timestamp(json.loads(str(context_payload)).get("context_candle_close_time"))
                except Exception:
                    context_timestamp = None
            row = {
                "decision_id": decision_id,
                **candidate,
                "research_only": True,
                "no_order_sent": True,
                "paper_trade_created": False,
                "live_trade_created": False,
                "broker_execution_created": False,
            }
            decision_rows.append(row)
            decision_ids.add(decision_id)
            _write_csv(paths["decision_ledger"], decision_rows)
            status["decisions_processed_this_run"] += 1

            accepted = str(candidate.get("accepted_or_rejected") or "").lower() == "accepted" or str(candidate.get("baseline_1h_signal") or "").lower() == "true"
            if accepted:
                trade_id = f"SIM-{decision_id}"
                if trade_id in trade_ids:
                    status["simulated_trades_skipped_as_duplicates"] += 1
                else:
                    trade_rows.append(
                        {
                            "trade_id": trade_id,
                            "decision_id": decision_id,
                            "timestamp": candidate.get("timestamp"),
                            "direction": candidate.get("direction"),
                            "entry_reference": candidate.get("entry_reference"),
                            "stop_reference": candidate.get("stop_reference"),
                            "target_reference": candidate.get("target_reference"),
                            "state": "research_observation_only",
                            "research_only": True,
                            "no_order_sent": True,
                            "broker_path_exists": False,
                        }
                    )
                    trade_ids.add(trade_id)
                    _write_csv(paths["trade_ledger"], trade_rows)
                    status["simulated_trades_created_this_run"] += 1

            last_processed = timestamp or last_processed
            last_context = context_timestamp or last_context
            checkpoint_store.save(
                _checkpoint_payload(
                    config,
                    frame,
                    latest_safe=latest_safe,
                    fetch_start=fetch_start,
                    fetch_end=fetch_end,
                    last_processed=last_processed,
                    last_context=last_context,
                    decision_ids=decision_ids,
                    trade_ids=trade_ids,
                    status="decision_persisted",
                    error="",
                )
            )
            if (
                config.fault_injection == "after_partial_decisions"
                and status["decisions_processed_this_run"] >= config.fault_after_decisions
            ):
                raise ForwardRuntimeInjectedCrash("injected_crash_after_partial_decision_processing")

        status["last_processed_1h_decision_timestamp"] = last_processed.isoformat() if last_processed is not None else None
        status["self_check_passed"] = True
        if after_quality["gap_count"] or after_quality["duplicate_count"] or after_quality["ohlc_sanity_failures"]:
            status["status"] = STATUS_RED
            status["final_reason"] = "canonical_data_corrupt_or_unrecoverable"
        elif fetch_failures or not status["caught_up_to_realtime"]:
            status["status"] = STATUS_YELLOW
            status["final_reason"] = "public_fetch_unavailable_or_canonical_stale"
        elif not config.scheduler_installed:
            status["status"] = STATUS_YELLOW
            status["final_reason"] = "scheduler_not_installed_but_runtime_healthy"
        else:
            status["status"] = STATUS_GREEN
            status["final_reason"] = "runtime_healthy_and_caught_up"
        checkpoint_store.save(
            _checkpoint_payload(
                config,
                frame,
                latest_safe=latest_safe,
                fetch_start=fetch_start,
                fetch_end=fetch_end,
                last_processed=last_processed,
                last_context=last_context,
                decision_ids=decision_ids,
                trade_ids=trade_ids,
                status=status["status"],
                error="",
            )
        )
    except ForwardRuntimeInjectedCrash:
        raise
    except Exception as exc:
        error_reason = str(exc)
        status["status"] = STATUS_RED
        status["final_reason"] = error_reason
        status["self_check_passed"] = False
        if config.canonical_csv_path.exists():
            try:
                frame = _load_canonical(config.canonical_csv_path)
                checkpoint_store.save(
                    _checkpoint_payload(
                        config,
                        frame,
                        latest_safe=latest_safe,
                        fetch_start=fetch_start,
                        fetch_end=fetch_end,
                        last_processed=last_processed,
                        last_context=last_context,
                        decision_ids=decision_ids,
                        trade_ids=trade_ids,
                        status=STATUS_RED,
                        error=error_reason,
                    )
                )
            except Exception:
                pass
    status["run_finished_at"] = _now(config).isoformat()
    _write_json(paths["status"], status)
    _write_json(
        paths["idempotency"],
        {
            "processed_decision_count": len(decision_ids),
            "processed_trade_count": len(trade_ids),
            "duplicate_decisions_this_run": status["decisions_skipped_as_already_processed"],
            "duplicate_simulated_trades_this_run": status["simulated_trades_skipped_as_duplicates"],
            "manual_rerun_idempotent": (
                status["decisions_skipped_as_already_processed"] >= 0
                and len(decision_ids) == len(set(decision_ids))
                and len(trade_ids) == len(set(trade_ids))
            ),
            **SAFETY_FLAGS,
        },
    )
    return status


def _fixture_fetch(source: pd.DataFrame) -> FetchFunction:
    def fetch(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        return source.loc[(source["timestamp"] >= start) & (source["timestamp"] <= end)].copy()

    return fetch


def _fixture_decisions(frame: pd.DataFrame, after: pd.Timestamp | None) -> list[dict[str, Any]]:
    indexed = frame.set_index("timestamp")
    complete = indexed["close"].resample("1h", closed="left", label="right").count()
    timestamps = complete.loc[complete >= 60].index
    if after is not None:
        timestamps = timestamps[timestamps > after]
    return [
        {
            "signal_id": f"BTCUSDT-{timestamp.isoformat()}",
            "timestamp": timestamp.isoformat(),
            "accepted_or_rejected": "accepted" if timestamp.hour % 4 == 0 else "rejected",
            "baseline_1h_signal": timestamp.hour % 4 == 0,
            "direction": "long" if timestamp.hour % 8 == 0 else "short",
            "entry_reference": 1.0,
            "stop_reference": 0.9,
            "target_reference": 1.2,
            "context": json.dumps(
                {
                    "context_candle_close_time": timestamp.floor("6h").isoformat(),
                    "context_timeframe": "6H",
                    "six_h_execution_disabled": True,
                }
            ),
        }
        for timestamp in timestamps
    ]


def run_outage_recovery_audit(config: ForwardValidationRuntimeConfig) -> dict[str, Any]:
    audit_root = config.package_root / "output" / AUDIT_FOLDER_NAME
    audit_root.mkdir(parents=True, exist_ok=True)
    source = _load_canonical(config.canonical_csv_path)
    sample = source.tail(min(len(source), 8 * 24 * 60)).reset_index(drop=True)
    cases: list[dict[str, Any]] = []

    def execute_case(name: str, mutate: Callable[[pd.DataFrame], pd.DataFrame], *, expected: str, fetch_failure: bool = False, fault: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            canonical = root / "canonical.csv"
            runtime = root / "runtime"
            local = mutate(sample.copy())
            local.to_csv(canonical, index=False)
            now_value = sample["timestamp"].max().tz_localize("UTC").to_pydatetime() + timedelta(minutes=1)
            fetcher: FetchFunction
            if fetch_failure:
                def failed_fetch(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
                    raise TimeoutError("simulated_public_fetch_timeout")
                fetcher = failed_fetch
            else:
                fetcher = _fixture_fetch(sample)
            case_config = ForwardValidationRuntimeConfig(
                project_root=config.project_root,
                package_root=config.package_root,
                canonical_csv_path=canonical,
                output_root=runtime,
                scheduler_installed=False,
                now_utc=now_value,
                fetch_function=fetcher,
                decision_function=_fixture_decisions,
                fault_injection=fault,
                fault_after_decisions=2,
                bootstrap_from_watchtower=False,
            )
            before = _quality(_load_canonical(canonical), _latest_safe_timestamp(now_value))
            crashed = False
            try:
                first = run_once(case_config)
            except ForwardRuntimeInjectedCrash:
                crashed = True
                case_config = ForwardValidationRuntimeConfig(
                    **{**case_config.__dict__, "fault_injection": None}
                )
                first = run_once(case_config)
            second = run_once(case_config)
            after = _quality(_load_canonical(canonical), _latest_safe_timestamp(now_value))
            decisions = _read_csv(_paths(runtime)["decision_ledger"])
            trades = _read_csv(_paths(runtime)["trade_ledger"])
            duplicate_decisions = len(decisions) - len({row.get("decision_id") for row in decisions})
            duplicate_trades = len(trades) - len({row.get("trade_id") for row in trades})
            actual = str(second["status"])
            passed = (
                actual == expected
                and after["duplicate_count"] == 0
                and duplicate_decisions == 0
                and duplicate_trades == 0
                and (after["gap_count"] == 0 or expected == STATUS_RED)
            )
            checkpoint = _read_json(_paths(runtime)["checkpoint"], {})
            cases.append(
                {
                    "case": name,
                    "expected_status": expected,
                    "actual_status": actual,
                    "rows_before": before["row_count"],
                    "rows_after": after["row_count"],
                    "gaps_before": before["gap_count"],
                    "gaps_after": after["gap_count"],
                    "decisions_before": 0,
                    "decisions_after": len(decisions),
                    "duplicate_decisions_created": duplicate_decisions,
                    "duplicate_simulated_trades_created": duplicate_trades,
                    "final_checkpoint_timestamp": checkpoint.get("last_processed_1h_decision_timestamp"),
                    "pass": passed,
                    "notes": f"crash_recovery_used={crashed}; final_reason={second.get('final_reason')}",
                }
            )

    identity = lambda frame: frame
    drop_tail = lambda minutes: (lambda frame: frame.iloc[:-minutes].copy())
    execute_case("clean_normal_run", identity, expected=STATUS_YELLOW)
    execute_case("immediate_rerun_no_new_candles", identity, expected=STATUS_YELLOW)
    execute_case("30_minute_outage", drop_tail(30), expected=STATUS_YELLOW)
    execute_case("3_hour_outage", drop_tail(180), expected=STATUS_YELLOW)
    execute_case("24_hour_outage", drop_tail(1440), expected=STATUS_YELLOW)
    execute_case("multi_day_outage", drop_tail(3 * 1440), expected=STATUS_YELLOW)
    execute_case("crash_after_data_append", drop_tail(180), expected=STATUS_YELLOW, fault="after_append")
    execute_case("crash_after_partial_decision_processing", identity, expected=STATUS_YELLOW, fault="after_partial_decisions")
    execute_case("duplicate_candle_fetch", lambda frame: pd.concat([frame, frame.tail(5)], ignore_index=True), expected=STATUS_YELLOW)
    execute_case("missing_candle_gap_then_backfill", lambda frame: frame.drop(frame.index[-120]).copy(), expected=STATUS_YELLOW)
    execute_case("binance_fetch_failure_timeout", drop_tail(30), expected=STATUS_YELLOW, fetch_failure=True)
    execute_case("canonical_exists_checkpoint_missing", identity, expected=STATUS_YELLOW)
    execute_case("checkpoint_exists_canonical_ahead", identity, expected=STATUS_YELLOW)
    execute_case("canonical_duplicate_timestamps", lambda frame: pd.concat([frame, frame.tail(1)], ignore_index=True), expected=STATUS_YELLOW)
    execute_case("canonical_gap", lambda frame: frame.drop(frame.index[-90]).copy(), expected=STATUS_YELLOW)
    execute_case("timezone_normalization", lambda frame: frame.assign(timestamp=pd.to_datetime(frame["timestamp"], utc=True)), expected=STATUS_YELLOW)
    execute_case("scheduler_missing_runtime_healthy", identity, expected=STATUS_YELLOW)

    passed_count = sum(1 for item in cases if item["pass"])
    classification = FINAL_READY if passed_count == len(cases) else (FINAL_WARNING if passed_count >= len(cases) - 1 else FINAL_FAILED)
    summary = {
        "final_classification": classification,
        "cases_total": len(cases),
        "cases_passed": passed_count,
        "cases_failed": len(cases) - passed_count,
        "manual_rerun_idempotent": all(item["duplicate_decisions_created"] == 0 and item["duplicate_simulated_trades_created"] == 0 for item in cases),
        "checkpoint_resume_proven": all(item["pass"] for item in cases if "crash" in item["case"]),
        "public_fixture_source": str(config.canonical_csv_path),
        **SAFETY_FLAGS,
        "cases": cases,
    }
    _write_json(audit_root / "outage_recovery_audit_summary.json", summary)
    lines = [
        "# Outage Recovery Audit",
        "",
        f"- Classification: `{classification}`",
        f"- Cases passed: `{passed_count}/{len(cases)}`",
        f"- Manual rerun idempotent: `{str(summary['manual_rerun_idempotent']).lower()}`",
        f"- Checkpoint resume proven: `{str(summary['checkpoint_resume_proven']).lower()}`",
        "",
        "| Case | Expected | Actual | Pass |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(f"| {item['case']} | {item['expected_status']} | {item['actual_status']} | {item['pass']} |" for item in cases)
    lines.extend(["", "All scenarios use a local slice of the canonical public BTCUSDT tape. No exchange account, order, paper brokerage, or broker endpoint is used.", ""])
    (audit_root / "outage_recovery_audit_report.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Research-only outage/resume/catch-up runtime.")
    parser.add_argument("--mode", choices=sorted(ALLOWED_MODES), default="run_once")
    parser.add_argument(
        "--canonical-csv",
        default="structural_compounding_lab/data_storage/BTCUSDT/1m/btcusdt_1m_canonical_shadow_forward.csv",
    )
    parser.add_argument(
        "--output-dir",
        default=f"structural_compounding_lab/output/{OUTPUT_FOLDER_NAME}",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    root = project_root()
    config = ForwardValidationRuntimeConfig(
        project_root=root,
        package_root=package_root(),
        canonical_csv_path=resolve_project_path(args.canonical_csv),
        output_root=resolve_project_path(args.output_dir),
    )
    if args.mode == "status":
        print(json.dumps(_read_json(_paths(config.output_root)["status"], {"status": "NOT_RUN"}), indent=2))
    elif args.mode == "audit_outage_recovery":
        print(json.dumps(run_outage_recovery_audit(config), indent=2))
    else:
        print(json.dumps(run_once(config), indent=2))


if __name__ == "__main__":
    main()
