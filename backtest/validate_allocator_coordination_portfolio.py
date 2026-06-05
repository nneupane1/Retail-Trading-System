"""Validate modest allocator-level coordination across routed sleeves."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from backtest.validate_expanded_universe_allocator import (
    _build_comparison,
    _build_lean_sleeve_report,
    _scenario_snapshot,
)
from backtest.validate_h1_portfolio import HOLDOUT_START, _load_existing_baseline
from backtest.validate_h6_standard_portfolio import _build_competition_report
from backtest.validate_htf_12h import (
    _clone_config,
    _load_progress,
    _run_or_resume_scenario,
    _save_progress,
)
from common.universe import get_named_universe
from config import AppConfig


def _report_root(base: AppConfig) -> Path:
    return (
        Path(base.require("backtest", "output_dir"))
        / "allocator_coordination_portfolio_validation_current"
    )


def _routed_h1_paper_overrides(
    base: AppConfig,
    *,
    coordination_enabled: bool,
) -> dict:
    raw = deepcopy(base.get("live_sim", "paper_portfolio", default={}) or {})
    allocator = dict(raw.get("allocator_v2", {}) or {})
    coordination = dict(allocator.get("cross_sleeve_coordination", {}) or {})
    coordination["enabled"] = bool(coordination_enabled)
    allocator["cross_sleeve_coordination"] = coordination
    raw["allocator_v2"] = allocator
    return raw


def _build_coordination_verdict(*, routed_h1: dict, coordinated: dict, comparison: dict) -> dict:
    return {
        "did_coordination_improve_equity": bool(comparison["delta_final_equity"] > 0.0),
        "did_coordination_improve_pf": bool(comparison["delta_profit_factor"] > 0.0),
        "did_coordination_improve_median_daily": bool(
            comparison["delta_median_daily_pnl"] >= 0.0
        ),
        "did_coordination_preserve_drawdown": bool(
            comparison["delta_max_drawdown"] >= -0.01
        ),
        "did_coordination_preserve_flow": bool(
            float(coordinated["metrics"]["trade_count"])
            >= 0.90 * float(routed_h1["metrics"]["trade_count"])
        ),
        "is_coordination_additive": bool(
            comparison["delta_final_equity"] > 0.0
            and comparison["delta_profit_factor"] >= 0.0
            and comparison["delta_median_daily_pnl"] >= -0.10
            and comparison["delta_max_drawdown"] >= -0.02
        ),
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

    _write_status(
        report_root,
        {
            "stage": "running",
            "holdout_window": {
                "start_date": HOLDOUT_START,
                "end_date": str(base.require("history", "end_date")),
            },
            "current_symbols": current_symbols,
        },
    )

    baseline_result = _load_existing_baseline(base)
    if baseline_result is None:
        raise FileNotFoundError("Missing current_9 baseline holdout artifacts.")
    baseline_snapshot = _scenario_snapshot(
        baseline_result,
        current_symbols,
        report_root,
        "current_9_baseline",
    )

    routed_cfg = _clone_config(base)
    routed_result = _run_or_resume_scenario(
        "scenario_current_9_plus_routed_h1",
        routed_cfg,
        report_root,
        progress,
        history_start_date=HOLDOUT_START,
        history_end_date=str(base.require("history", "end_date")),
        core_enabled=True,
        swing_enabled=True,
        htf_enabled=True,
        convexity_enabled=True,
        paper_portfolio_overrides=_routed_h1_paper_overrides(
            base,
            coordination_enabled=False,
        ),
    )
    routed_snapshot = _scenario_snapshot(
        routed_result,
        current_symbols,
        report_root,
        "current_9_plus_routed_h1",
    )

    coordinated_cfg = _clone_config(base)
    coordinated_result = _run_or_resume_scenario(
        "scenario_current_9_plus_routed_h1_coordination",
        coordinated_cfg,
        report_root,
        progress,
        history_start_date=HOLDOUT_START,
        history_end_date=str(base.require("history", "end_date")),
        core_enabled=True,
        swing_enabled=True,
        htf_enabled=True,
        convexity_enabled=True,
        paper_portfolio_overrides=_routed_h1_paper_overrides(
            base,
            coordination_enabled=True,
        ),
    )
    coordinated_snapshot = _scenario_snapshot(
        coordinated_result,
        current_symbols,
        report_root,
        "current_9_plus_routed_h1_coordination",
    )

    comparisons = {
        "baseline_vs_routed_h1": _build_comparison(
            baseline_snapshot,
            routed_snapshot,
        ),
        "baseline_vs_coordination": _build_comparison(
            baseline_snapshot,
            coordinated_snapshot,
        ),
        "routed_h1_vs_coordination": _build_comparison(
            routed_snapshot,
            coordinated_snapshot,
        ),
    }
    competition_report = _build_competition_report(
        report_root,
        routed_snapshot,
        coordinated_snapshot,
        "allocator_coordination_overlay",
    )
    lean_sleeve_report = _build_lean_sleeve_report(
        report_root,
        routed_snapshot,
        coordinated_snapshot,
        "allocator_coordination_overlay",
    )
    verdict = _build_coordination_verdict(
        routed_h1=routed_snapshot,
        coordinated=coordinated_snapshot,
        comparison=comparisons["routed_h1_vs_coordination"],
    )

    summary = {
        "report_root": str(report_root),
        "current_symbols": current_symbols,
        "coordination_rules": (
            _routed_h1_paper_overrides(base, coordination_enabled=True)
            .get("allocator_v2", {})
            .get("cross_sleeve_coordination", {})
        ),
        "scenarios": {
            "current_9_baseline": baseline_snapshot,
            "current_9_plus_routed_h1": routed_snapshot,
            "current_9_plus_routed_h1_coordination": coordinated_snapshot,
        },
        "comparisons": comparisons,
        "competition_report": competition_report,
        "lean_sleeve_report": lean_sleeve_report,
        "verdict": verdict,
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
            "verdict": verdict,
        },
    )


if __name__ == "__main__":
    main()
