"""HTF-context-aware portfolio validation for the research-only h1_execution sleeve."""

from __future__ import annotations

import json
from pathlib import Path

from backtest.validate_expanded_universe_allocator import (
    _build_comparison,
    _build_lean_sleeve_report,
    _scenario_snapshot,
)
from backtest.validate_h1_portfolio import (
    HOLDOUT_START,
    _build_verdict,
    _load_existing_baseline,
    _paper_portfolio_overrides,
)
from backtest.validate_h1_side_policy_portfolio import (
    ALL_SYMBOL_ROOT,
    _load_existing_snapshot,
)
from backtest.validate_h6_standard_portfolio import _build_competition_report
from backtest.validate_htf_12h import (
    _clone_config,
    _load_progress,
    _run_or_resume_scenario,
    _save_progress,
)
from common.universe import get_named_universe
from config import AppConfig


SHORT_ONLY_ROOT = "h1_side_policy_portfolio_validation_current"
SHORT_ONLY_SCENARIO = "scenario_current_9_plus_h1_short_only"


def _report_root(base: AppConfig) -> Path:
    return Path(base.require("backtest", "output_dir")) / "h1_context_policy_portfolio_validation_current"


def _current_symbols(base: AppConfig) -> list[str]:
    return get_named_universe(base, "current_9") or [
        str(symbol).upper()
        for symbol in base.require("backtest", "portfolio_replay", "symbols")
    ]


def _context_strategy_overrides(symbols: list[str]) -> dict:
    return {
        "h1_execution": {
            "enabled": True,
            "allowed_symbols": [str(symbol).upper() for symbol in symbols],
            "blocked_symbols": [],
            "allowed_sides": ["long", "short"],
            "selection_threshold_offset": -0.02,
            "long_selection_threshold_offset": -0.02,
            "short_selection_threshold_offset": -0.02,
            "long_risk_multiplier": 1.0,
            "short_risk_multiplier": 1.0,
            "context_side_policy": {
                "bearish": {
                    "allowed_sides": ["short"],
                    "short_selection_threshold_offset": -0.04,
                    "short_risk_multiplier": 1.10,
                },
                "neutral": {
                    "allowed_sides": ["long", "short"],
                    "long_selection_threshold_offset": 0.00,
                    "short_selection_threshold_offset": -0.03,
                    "long_risk_multiplier": 0.95,
                    "short_risk_multiplier": 1.05,
                },
                "bullish": {
                    "allowed_sides": ["long", "short"],
                    "long_selection_threshold_offset": -0.03,
                    "short_selection_threshold_offset": 0.02,
                    "long_risk_multiplier": 1.05,
                    "short_risk_multiplier": 0.90,
                },
            },
        }
    }


def _write_status(report_root: Path, payload: dict) -> None:
    with (report_root / "status.json").open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2, default=str)


def main() -> None:
    base = AppConfig.load()
    report_root = _report_root(base)
    report_root.mkdir(parents=True, exist_ok=True)
    progress = _load_progress(report_root)
    current_symbols = [str(symbol).upper() for symbol in _current_symbols(base)]

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

    all_symbol_snapshot = _load_existing_snapshot(
        base,
        ALL_SYMBOL_ROOT,
        "scenario_current_9_plus_h1_execution",
        current_symbols,
        report_root,
        "current_9_plus_h1_all",
    )
    short_only_snapshot = _load_existing_snapshot(
        base,
        SHORT_ONLY_ROOT,
        SHORT_ONLY_SCENARIO,
        current_symbols,
        report_root,
        "current_9_plus_h1_short_only",
    )

    context_cfg = _clone_config(base)
    context_result = _run_or_resume_scenario(
        "scenario_current_9_plus_h1_context_policy",
        context_cfg,
        report_root,
        progress,
        history_start_date=HOLDOUT_START,
        history_end_date=str(base.require("history", "end_date")),
        core_enabled=True,
        swing_enabled=True,
        htf_enabled=True,
        convexity_enabled=True,
        paper_portfolio_overrides=_paper_portfolio_overrides(base),
        strategy_overrides=_context_strategy_overrides(current_symbols),
    )
    context_snapshot = _scenario_snapshot(
        context_result,
        current_symbols,
        report_root,
        "current_9_plus_h1_context_policy",
    )

    comparisons = {
        "baseline_vs_all": _build_comparison(baseline_snapshot, all_symbol_snapshot),
        "baseline_vs_short_only": _build_comparison(baseline_snapshot, short_only_snapshot),
        "baseline_vs_context_policy": _build_comparison(baseline_snapshot, context_snapshot),
        "all_vs_context_policy": _build_comparison(all_symbol_snapshot, context_snapshot),
        "short_only_vs_context_policy": _build_comparison(short_only_snapshot, context_snapshot),
    }

    competition_report = _build_competition_report(
        report_root,
        baseline_snapshot,
        context_snapshot,
        "h1_execution_context_policy_overlay",
    )
    lean_sleeve_report = _build_lean_sleeve_report(
        report_root,
        baseline_snapshot,
        context_snapshot,
        "h1_execution_context_policy_overlay",
    )
    verdict = _build_verdict(
        baseline=baseline_snapshot,
        candidate=context_snapshot,
        comparison=comparisons["baseline_vs_context_policy"],
    )

    summary = {
        "report_root": str(report_root),
        "current_symbols": current_symbols,
        "context_policy": _context_strategy_overrides(current_symbols)["h1_execution"]["context_side_policy"],
        "scenarios": {
            "current_9_baseline": baseline_snapshot,
            "current_9_plus_h1_all": all_symbol_snapshot,
            "current_9_plus_h1_short_only": short_only_snapshot,
            "current_9_plus_h1_context_policy": context_snapshot,
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
