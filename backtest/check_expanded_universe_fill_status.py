"""Summarize expanded-universe history fill progress and rerun readiness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from config import AppConfig


def _build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Summarize expanded-universe history fill progress and determine "
            "whether the expanded-universe allocator validation is ready to rerun."
        )
    )
    parser.add_argument(
        "--fill-report-root",
        help=(
            "Optional fill report root. Defaults to "
            "backtest/output/expanded_universe_history_fill_active."
        ),
    )
    parser.add_argument(
        "--validation-report-root",
        help=(
            "Optional validation report root. If omitted, the latest matching "
            "expanded_universe_allocator_validation folder is used."
        ),
    )
    return parser


def _default_fill_report_root(base_output: Path) -> Path:
    return base_output / "expanded_universe_history_fill_active"


def _find_latest_validation_root(base_output: Path) -> Path | None:
    candidates = []
    for candidate in base_output.glob("expanded_universe_allocator_validation*"):
        if (candidate / "expanded_universe_rejected_symbols.csv").exists():
            candidates.append(candidate)
    if not candidates:
        return None
    candidates.sort(key=lambda path: path.name, reverse=True)
    return candidates[0]


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _load_symbol_csv(path: Path, symbol_column: str = "symbol") -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame[symbol_column] = frame[symbol_column].astype(str).str.upper()
    return frame


def _expected_final_csv(fill_progress: dict, symbol: str) -> Path | None:
    record = fill_progress.get("symbols", {}).get(symbol, {})
    raw_path = record.get("final_csv_path")
    if not raw_path:
        return None
    return Path(raw_path)


def build_fill_readiness_summary(*, fill_report_root: Path, validation_report_root: Path | None) -> dict:
    fill_summary_path = fill_report_root / "history_fill_summary.json"
    fill_progress_path = fill_report_root / "history_fill_progress.json"
    fill_targets_path = fill_report_root / "history_fill_targets.csv"

    if not fill_summary_path.exists():
        raise FileNotFoundError(f"Fill summary not found: {fill_summary_path}")
    if not fill_progress_path.exists():
        raise FileNotFoundError(f"Fill progress not found: {fill_progress_path}")

    fill_summary = _load_json(fill_summary_path)
    fill_progress = _load_json(fill_progress_path)
    fill_targets = (
        _load_symbol_csv(fill_targets_path)
        if fill_targets_path.exists()
        else pd.DataFrame(columns=["symbol", "target_reason"])
    )

    validation_root = validation_report_root
    if validation_root is None:
        raw_validation_root = fill_summary.get("validation_report_root")
        validation_root = Path(raw_validation_root) if raw_validation_root else None

    rejected_symbols = []
    validation_summary = {}
    if validation_root is not None:
        rejected_path = validation_root / "expanded_universe_rejected_symbols.csv"
        summary_path = validation_root / "expanded_universe_summary.json"
        if rejected_path.exists():
            rejected_frame = _load_symbol_csv(rejected_path)
            rejected_symbols = rejected_frame["symbol"].astype(str).str.upper().tolist()
        if summary_path.exists():
            validation_summary = _load_json(summary_path)

    completed_symbols = [
        str(symbol).upper()
        for symbol in fill_summary.get("completed_symbols", [])
    ]
    in_progress_symbols = [
        symbol
        for symbol, record in fill_progress.get("symbols", {}).items()
        if str(record.get("status", "")).lower() == "in_progress"
    ]
    failed_symbols = [
        symbol
        for symbol, record in fill_progress.get("symbols", {}).items()
        if str(record.get("status", "")).lower() == "failed"
    ]

    recovered_symbols = sorted(set(rejected_symbols) & set(completed_symbols))
    remaining_rejected_symbols = sorted(set(rejected_symbols) - set(recovered_symbols))

    completed_missing_files = []
    for symbol in recovered_symbols:
        expected_path = _expected_final_csv(fill_progress, symbol)
        if expected_path is not None and not expected_path.exists():
            completed_missing_files.append(symbol)

    target_reason_counts = (
        fill_targets["target_reason"].value_counts().to_dict()
        if not fill_targets.empty and "target_reason" in fill_targets.columns
        else {}
    )

    ready_for_rerun = bool(rejected_symbols) and not remaining_rejected_symbols and not in_progress_symbols
    if completed_missing_files:
        ready_for_rerun = False

    action = (
        "rerun_expanded_universe_allocator"
        if ready_for_rerun
        else "continue_history_fill"
    )

    expected_accepted_count_after_rerun = None
    if validation_summary:
        expected_accepted_count_after_rerun = int(validation_summary.get("accepted_symbol_count", 0)) + len(recovered_symbols)

    return {
        "fill_report_root": str(fill_report_root),
        "validation_report_root": str(validation_root) if validation_root is not None else None,
        "fill_updated_at": fill_progress.get("updated_at"),
        "original_rejected_symbol_count": int(len(rejected_symbols)),
        "recovered_symbol_count": int(len(recovered_symbols)),
        "remaining_rejected_symbol_count": int(len(remaining_rejected_symbols)),
        "in_progress_symbol_count": int(len(in_progress_symbols)),
        "failed_symbol_count": int(len(failed_symbols)),
        "completed_symbol_count": int(len(completed_symbols)),
        "recovered_symbols": recovered_symbols,
        "remaining_rejected_symbols": remaining_rejected_symbols,
        "in_progress_symbols": in_progress_symbols,
        "failed_symbols": failed_symbols,
        "completed_symbols_missing_final_csv": completed_missing_files,
        "target_reason_counts": {
            str(key): int(value) for key, value in target_reason_counts.items()
        },
        "expected_accepted_symbol_count_after_rerun": expected_accepted_count_after_rerun,
        "ready_for_rerun": ready_for_rerun,
        "next_action": action,
        "recommended_command": (
            "python -m backtest.validate_expanded_universe_allocator"
            if ready_for_rerun
            else "python -m backtest.fill_expanded_universe_history"
        ),
    }


def main():
    args = _build_parser().parse_args()
    config = AppConfig.load()
    base_output = Path(config.require("backtest", "output_dir"))
    fill_report_root = (
        Path(args.fill_report_root)
        if args.fill_report_root
        else _default_fill_report_root(base_output)
    )
    validation_report_root = (
        Path(args.validation_report_root)
        if args.validation_report_root
        else _find_latest_validation_root(base_output)
    )

    summary = build_fill_readiness_summary(
        fill_report_root=fill_report_root,
        validation_report_root=validation_report_root,
    )
    output_path = fill_report_root / "history_fill_readiness_summary.json"
    with output_path.open("w", encoding="utf-8") as file_handle:
        json.dump(summary, file_handle, indent=2, default=str)

    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
