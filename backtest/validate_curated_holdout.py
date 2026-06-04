"""Lean holdout validation for curated expanded-universe additions.

This validator deliberately avoids rerunning the full training-period matrix.
It reuses the existing 2025-01-01 to 2026-05-22 expanded-universe replay to
derive a 2025 training curation slice, then runs only the shorter 2026 holdout
scenarios from scratch.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from backtest.validate_htf_12h import (
    _load_progress,
    _load_run_artifacts,
    _run_or_resume_scenario,
    _save_progress,
)
from backtest.validate_expanded_universe_allocator import (
    _build_candidate_branch_verdict,
    _build_comparison,
    _build_symbol_curation_report,
    _scenario_artifacts_require_symbol_reset,
    _scenario_base_with_symbols,
    _scenario_requires_symbol_reset,
    _scenario_snapshot,
    _symbol_breakdown,
)
from common.universe import get_named_universe
from config import AppConfig


SOURCE_REPORT_ROOT = "expanded_universe_allocator_validation_20260604"
SOURCE_BASELINE_SCENARIO = "scenario_current_9_symbol_calibrated_allocator"
SOURCE_EXPANDED_SCENARIO = "scenario_expanded_universe_calibrated_allocator"


def _symbol_union(base_symbols: list[str], additions: list[str]) -> list[str]:
    seen = {str(symbol).upper() for symbol in base_symbols}
    merged = [str(symbol).upper() for symbol in base_symbols]
    for symbol in additions:
        symbol_key = str(symbol).upper()
        if symbol_key in seen:
            continue
        merged.append(symbol_key)
        seen.add(symbol_key)
    return merged


def _scenario_definition(name: str, symbols: list[str]) -> dict:
    return {"name": name, "symbols": [str(symbol).upper() for symbol in symbols]}


def _write_status(report_root: Path, payload: dict) -> None:
    with (report_root / "status.json").open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2, default=str)


def _load_quality_summary(source_root: Path) -> dict:
    summary_path = source_root / "expanded_universe_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing source quality summary: {summary_path}")
    with summary_path.open(encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _filter_trades_to_window(trades: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    working = trades.copy()
    time_column = "exit_time" if "exit_time" in working.columns else "entry_time"
    working[time_column] = pd.to_datetime(working[time_column], errors="coerce")
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1)
    working = working.loc[(working[time_column] >= start_ts) & (working[time_column] < end_ts)].copy()
    return working.reset_index(drop=True)


def _training_snapshot_from_source(
    *,
    scenario_dir: Path,
    symbols_used: list[str],
    training_start: str,
    training_end: str,
    report_root: Path,
    label: str,
) -> dict:
    trades, _, _, signals = _load_run_artifacts(scenario_dir)
    training_trades = _filter_trades_to_window(trades, training_start, training_end)
    strategy_rows = []
    if not training_trades.empty and "strategy_type" in training_trades.columns:
        for strategy_type, group in training_trades.groupby(training_trades["strategy_type"].fillna("core").astype(str)):
            pnl = pd.to_numeric(group.get("pnl"), errors="coerce").fillna(0.0)
            pos = float(pnl[pnl > 0].sum())
            neg = float(pnl[pnl < 0].sum())
            strategy_rows.append(
                {
                    "strategy_type": str(strategy_type),
                    "trade_count": int(len(group)),
                    "net_pnl": float(pnl.sum()),
                    "profit_factor": float("inf") if neg == 0.0 and pos > 0 else (pos / abs(neg) if neg != 0.0 else 0.0),
                }
            )
    symbol_rows = _symbol_breakdown(training_trades)
    pd.DataFrame(symbol_rows).to_csv(report_root / f"{label}_training_symbol_breakdown.csv", index=False)
    pd.DataFrame(strategy_rows).to_csv(report_root / f"{label}_training_strategy_breakdown.csv", index=False)
    selection_reasons = {}
    if not signals.empty and "selection_reason" in signals.columns:
        selection_reasons = {
            str(key): int(value)
            for key, value in signals["selection_reason"].fillna("unknown").astype(str).value_counts().items()
        }
    return {
        "name": label,
        "symbols_used": [str(symbol).upper() for symbol in symbols_used],
        "metrics": {
            "net_pnl": float(pd.to_numeric(training_trades.get("pnl"), errors="coerce").fillna(0.0).sum()),
            "trade_count": int(len(training_trades)),
        },
        "strategy_breakdown": strategy_rows,
        "symbol_breakdown": symbol_rows,
        "selection_reasons": selection_reasons,
    }


def main():
    base = AppConfig.load()
    source_root = Path(base.require("backtest", "output_dir")) / SOURCE_REPORT_ROOT
    report_root = Path(base.require("backtest", "output_dir")) / "curated_holdout_validation_20260604_lean"
    report_root.mkdir(parents=True, exist_ok=True)

    current_symbols = get_named_universe(base, "current_9") or [
        str(symbol).upper() for symbol in base.require("backtest", "portfolio_replay", "symbols")
    ]
    training_start = "2025-01-01"
    training_end = "2025-12-31"
    holdout_start = "2026-01-01"
    holdout_end = str(base.require("history", "end_date"))

    quality_summary = _load_quality_summary(source_root)
    accepted_symbols = [str(symbol).upper() for symbol in quality_summary.get("accepted_symbols", [])]
    if not accepted_symbols:
        raise ValueError("No accepted expanded-universe symbols available from source validation.")

    baseline_training_snapshot = _training_snapshot_from_source(
        scenario_dir=source_root / SOURCE_BASELINE_SCENARIO,
        symbols_used=current_symbols,
        training_start=training_start,
        training_end=training_end,
        report_root=report_root,
        label="baseline_current_9",
    )
    expanded_training_snapshot = _training_snapshot_from_source(
        scenario_dir=source_root / SOURCE_EXPANDED_SCENARIO,
        symbols_used=accepted_symbols,
        training_start=training_start,
        training_end=training_end,
        report_root=report_root,
        label="expanded_accepted",
    )

    curation = _build_symbol_curation_report(
        base_config=base,
        report_root=report_root,
        baseline_symbols=current_symbols,
        expanded_snapshot=expanded_training_snapshot,
        accepted_symbols=accepted_symbols,
    )
    _write_status(
        report_root,
        {
            "stage": "training_curation_complete",
            "source_report_root": str(source_root),
            "training_window": {"start_date": training_start, "end_date": training_end},
            "keep_symbols": curation["keep_symbols"],
            "review_symbols": curation["review_symbols"],
            "drop_symbols": curation["drop_symbols"],
            "curated_symbols": curation["curated_symbols"],
        },
    )

    progress = _load_progress(report_root)
    base_flags = {
        "core_enabled": True,
        "swing_enabled": True,
        "htf_enabled": True,
        "convexity_enabled": True,
    }

    holdout_scenarios = [
        _scenario_definition("scenario_holdout_current_9", current_symbols),
        _scenario_definition("scenario_holdout_current_9_plus_dot", _symbol_union(current_symbols, ["DOTUSDT"])),
        _scenario_definition("scenario_holdout_current_9_plus_fil", _symbol_union(current_symbols, ["FILUSDT"])),
        _scenario_definition("scenario_holdout_current_9_plus_dot_fil", _symbol_union(current_symbols, ["DOTUSDT", "FILUSDT"])),
        _scenario_definition("scenario_holdout_current_9_plus_training_keeps", curation["curated_symbols"]),
    ]

    holdout_snapshots = {}
    for scenario in holdout_scenarios:
        name = scenario["name"]
        symbols = scenario["symbols"]
        _write_status(
            report_root,
            {
                "stage": "running_holdout_scenario",
                "scenario": name,
                "symbols": symbols,
                "holdout_window": {"start_date": holdout_start, "end_date": holdout_end},
            },
        )
        result = _run_or_resume_scenario(
            name,
            _scenario_base_with_symbols(base, symbols),
            report_root,
            progress,
            reset_output=(
                _scenario_requires_symbol_reset(progress, name, symbols)
                or _scenario_artifacts_require_symbol_reset(report_root, name, symbols)
            ),
            history_start_date=holdout_start,
            history_end_date=holdout_end,
            **base_flags,
        )
        summary_key = name.removeprefix("scenario_")
        snapshot = _scenario_snapshot(result, symbols, report_root, summary_key)
        holdout_snapshots[summary_key] = snapshot
        progress.setdefault(name, {})["symbols_used"] = snapshot["symbols_used"]
        _save_progress(report_root, progress)

    baseline_key = "holdout_current_9"
    comparisons = {}
    verdicts = {}
    for key, snapshot in holdout_snapshots.items():
        if key == baseline_key:
            continue
        comparison = _build_comparison(holdout_snapshots[baseline_key], snapshot)
        verdict = _build_candidate_branch_verdict(
            baseline=holdout_snapshots[baseline_key],
            candidate=snapshot,
            comparison=comparison,
        )
        comparisons[key] = comparison
        verdicts[key] = verdict

    summary = {
        "report_root": str(report_root),
        "source_report_root": str(source_root),
        "training_window": {"start_date": training_start, "end_date": training_end},
        "holdout_window": {"start_date": holdout_start, "end_date": holdout_end},
        "training_quality": quality_summary,
        "training_baseline_slice": baseline_training_snapshot,
        "training_expanded_slice": expanded_training_snapshot,
        "training_curation": curation,
        "holdout_scenarios": holdout_snapshots,
        "holdout_comparisons": comparisons,
        "holdout_verdicts": verdicts,
    }
    with (report_root / "summary.json").open("w", encoding="utf-8") as file_handle:
        json.dump(summary, file_handle, indent=2, default=str)
    _write_status(
        report_root,
        {
            "stage": "complete",
            "summary_path": str(report_root / "summary.json"),
        },
    )


if __name__ == "__main__":
    main()
