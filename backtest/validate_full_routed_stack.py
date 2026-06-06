"""Run the full-history validation for the current routed stack."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from backtest.validate_allocator_coordination_portfolio import (
    _routed_h1_paper_overrides,
)
from backtest.validate_expanded_universe_allocator import _scenario_snapshot
from backtest.validate_htf_12h import (
    _clone_config,
    _load_progress,
    _run_or_resume_scenario,
    _save_progress,
)
from common.universe import get_named_universe
from config import AppConfig


def _report_root(base: AppConfig) -> Path:
    return Path(base.require("backtest", "output_dir")) / "full_routed_stack_validation_current"


def _load_monitoring_snapshot(output_dir: Path) -> dict:
    portfolio_status_path = output_dir / "portfolio_status.json"
    selection_reason_path = output_dir / "selection_reason_summary.csv"
    selection_by_strategy_path = output_dir / "selection_reason_by_strategy_summary.csv"
    runtime_policy_path = output_dir / "runtime_policy_summary.csv"

    portfolio_status = {}
    if portfolio_status_path.exists():
        portfolio_status = json.loads(portfolio_status_path.read_text(encoding="utf-8"))

    selection_reason_rows = []
    if selection_reason_path.exists():
        selection_reason_rows = (
            pd.read_csv(selection_reason_path)
            .fillna("")
            .to_dict(orient="records")
        )

    selection_by_strategy_rows = []
    if selection_by_strategy_path.exists():
        selection_by_strategy_rows = (
            pd.read_csv(selection_by_strategy_path)
            .fillna("")
            .to_dict(orient="records")
        )

    runtime_policy_rows = []
    if runtime_policy_path.exists():
        runtime_policy_rows = (
            pd.read_csv(runtime_policy_path)
            .fillna("")
            .to_dict(orient="records")
        )

    return {
        "portfolio_status_path": str(portfolio_status_path),
        "selection_reason_summary_path": str(selection_reason_path),
        "selection_reason_by_strategy_summary_path": str(selection_by_strategy_path),
        "runtime_policy_summary_path": str(runtime_policy_path),
        "cap_pressure_summary": dict(portfolio_status.get("cap_pressure_summary") or {}),
        "runtime_policy_states": dict(portfolio_status.get("runtime_policy_states") or {}),
        "selection_reason_counts": dict(portfolio_status.get("selection_reason_counts") or {}),
        "recent_selection_reason_counts": dict(
            portfolio_status.get("recent_selection_reason_counts") or {}
        ),
        "top_selection_reasons": selection_reason_rows[:10],
        "top_selection_reasons_by_strategy": selection_by_strategy_rows[:20],
        "runtime_policy_rows": runtime_policy_rows,
        "open_positions": int(portfolio_status.get("open_positions", 0) or 0),
        "last_top_symbols": list(portfolio_status.get("top_symbols") or []),
    }


def _write_status(report_root: Path, payload: dict) -> None:
    with (report_root / "status.json").open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2, default=str)


def main() -> None:
    base = AppConfig.load()
    report_root = _report_root(base)
    report_root.mkdir(parents=True, exist_ok=True)
    progress = _load_progress(report_root)
    current_symbols = get_named_universe(base, "current_9") or [
        str(symbol).upper()
        for symbol in base.require("backtest", "portfolio_replay", "symbols")
    ]
    history_start = str(base.require("history", "start_date"))
    history_end = str(base.require("history", "end_date"))

    _write_status(
        report_root,
        {
            "stage": "running",
            "history_window": {
                "start_date": history_start,
                "end_date": history_end,
            },
            "current_symbols": current_symbols,
            "scenario_name": "scenario_current_routed_stack_full_history",
        },
    )

    scenario = _run_or_resume_scenario(
        "scenario_current_routed_stack_full_history",
        _clone_config(base),
        report_root,
        progress,
        history_start_date=history_start,
        history_end_date=history_end,
        core_enabled=True,
        swing_enabled=True,
        htf_enabled=True,
        convexity_enabled=True,
        paper_portfolio_overrides=_routed_h1_paper_overrides(
            base,
            coordination_enabled=False,
        ),
    )
    snapshot = _scenario_snapshot(
        scenario,
        current_symbols,
        report_root,
        "current_routed_stack_full_history",
    )
    monitoring = _load_monitoring_snapshot(Path(scenario["output_dir"]))

    summary = {
        "report_root": str(report_root),
        "history_window": {
            "start_date": history_start,
            "end_date": history_end,
        },
        "current_symbols": current_symbols,
        "scenario": snapshot,
        "monitoring": monitoring,
    }
    (report_root / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )
    _save_progress(report_root, progress)
    _write_status(
        report_root,
        {
            "stage": "complete",
            "summary_path": str(report_root / "summary.json"),
            "scenario_output_dir": str(scenario["output_dir"]),
            "metrics": snapshot.get("metrics", {}),
            "monitoring": {
                "cap_pressure_summary": monitoring.get("cap_pressure_summary", {}),
                "runtime_policy_states": monitoring.get("runtime_policy_states", {}),
            },
        },
    )


if __name__ == "__main__":
    main()
