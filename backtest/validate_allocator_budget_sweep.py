"""Sweep allocator constraint variants for the routed h1 sleeve."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from backtest.validate_allocator_coordination_portfolio import _report_root as _coordination_report_root
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


SWEEP_VARIANTS = [
    {
        "name": "h1_lane_mild",
        "h1_reserved_risk_fraction": 0.0030,
        "h1_absolute_max_risk_fraction": 0.0028,
        "h1_max_risk_fraction_multiplier": 1.15,
        "core_priority_multiplier": 0.78,
        "core_absolute_max_risk_fraction": 0.0025,
    },
    {
        "name": "h1_lane_balanced",
        "h1_reserved_risk_fraction": 0.0030,
        "h1_absolute_max_risk_fraction": 0.0028,
        "h1_max_risk_fraction_multiplier": 1.15,
        "core_priority_multiplier": 0.76,
        "core_absolute_max_risk_fraction": 0.0023,
    },
    {
        "name": "h1_lane_stronger",
        "h1_reserved_risk_fraction": 0.0032,
        "h1_absolute_max_risk_fraction": 0.0030,
        "h1_max_risk_fraction_multiplier": 1.20,
        "core_priority_multiplier": 0.75,
        "core_absolute_max_risk_fraction": 0.0023,
    },
]


def _report_root(base: AppConfig) -> Path:
    return (
        Path(base.require("backtest", "output_dir"))
        / "allocator_budget_sweep_current"
    )


def _budget_variant_paper_overrides(base: AppConfig, variant: dict) -> dict:
    raw = deepcopy(base.get("live_sim", "paper_portfolio", default={}) or {})
    sleeves = dict(raw.get("strategy_sleeves", {}) or {})
    h1_sleeve = dict(sleeves.get("h1_execution", {}) or {})
    h1_sleeve["enabled"] = True
    h1_sleeve["reserved_risk_fraction"] = float(
        variant["h1_reserved_risk_fraction"]
    )
    sleeves["h1_execution"] = h1_sleeve
    raw["strategy_sleeves"] = sleeves

    allocator = dict(raw.get("allocator_v2", {}) or {})
    allocator["cross_sleeve_coordination"] = dict(
        allocator.get("cross_sleeve_coordination", {}) or {}
    )
    allocator["cross_sleeve_coordination"]["enabled"] = False
    allocator_sleeves = dict(allocator.get("sleeves", {}) or {})
    h1_allocator = dict(allocator_sleeves.get("h1_execution", {}) or {})
    h1_allocator["absolute_max_risk_fraction"] = float(
        variant["h1_absolute_max_risk_fraction"]
    )
    h1_allocator["max_risk_fraction_multiplier"] = float(
        variant["h1_max_risk_fraction_multiplier"]
    )
    allocator_sleeves["h1_execution"] = h1_allocator

    core_allocator = dict(allocator_sleeves.get("core", {}) or {})
    core_allocator["priority_multiplier"] = float(variant["core_priority_multiplier"])
    core_allocator["absolute_max_risk_fraction"] = float(
        variant["core_absolute_max_risk_fraction"]
    )
    allocator_sleeves["core"] = core_allocator
    allocator["sleeves"] = allocator_sleeves
    raw["allocator_v2"] = allocator
    return raw


def _load_existing_routed_snapshot(
    base: AppConfig,
    current_symbols: list[str],
    report_root: Path,
) -> dict:
    summary_path = _coordination_report_root(base) / "summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing routed h1 coordination summary: {summary_path}")
    with summary_path.open(encoding="utf-8") as file_handle:
        summary = json.load(file_handle)
    return summary["scenarios"]["current_9_plus_routed_h1"]


def _rank_variant(snapshot: dict, comparison_vs_routed: dict, verdict: dict) -> dict:
    metrics = snapshot["metrics"]
    return {
        "scenario_name": snapshot["name"],
        "final_equity": float(metrics["final_equity"]),
        "profit_factor": float(metrics["profit_factor"]),
        "median_daily_pnl": float(metrics["median_daily_pnl"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "trade_count": int(metrics["trade_count"]),
        "delta_final_equity_vs_routed_h1": float(
            comparison_vs_routed["delta_final_equity"]
        ),
        "delta_profit_factor_vs_routed_h1": float(
            comparison_vs_routed["delta_profit_factor"]
        ),
        "delta_median_daily_pnl_vs_routed_h1": float(
            comparison_vs_routed["delta_median_daily_pnl"]
        ),
        "delta_max_drawdown_vs_routed_h1": float(
            comparison_vs_routed["delta_max_drawdown"]
        ),
        "delta_trade_count_vs_routed_h1": int(
            comparison_vs_routed["delta_trade_count"]
        ),
        "is_additive_to_routed_h1": bool(verdict["is_variant_additive"]),
    }


def _build_variant_verdict(*, routed_h1: dict, candidate: dict, comparison: dict) -> dict:
    return {
        "did_variant_improve_equity": bool(comparison["delta_final_equity"] > 0.0),
        "did_variant_improve_pf": bool(comparison["delta_profit_factor"] > 0.0),
        "did_variant_improve_median_daily": bool(
            comparison["delta_median_daily_pnl"] >= 0.0
        ),
        "did_variant_preserve_drawdown": bool(
            comparison["delta_max_drawdown"] >= -0.01
        ),
        "did_variant_preserve_flow": bool(
            float(candidate["metrics"]["trade_count"])
            >= 0.95 * float(routed_h1["metrics"]["trade_count"])
        ),
        "is_variant_additive": bool(
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
            "variants": SWEEP_VARIANTS,
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
    routed_snapshot = _load_existing_routed_snapshot(base, current_symbols, report_root)

    variant_results = {}
    comparisons = {
        "baseline_vs_routed_h1": _build_comparison(
            baseline_snapshot,
            routed_snapshot,
        )
    }
    rankings = []

    for variant in SWEEP_VARIANTS:
        scenario_name = f"scenario_current_9_plus_{variant['name']}"
        variant_cfg = _clone_config(base)
        variant_result = _run_or_resume_scenario(
            scenario_name,
            variant_cfg,
            report_root,
            progress,
            history_start_date=HOLDOUT_START,
            history_end_date=str(base.require("history", "end_date")),
            core_enabled=True,
            swing_enabled=True,
            htf_enabled=True,
            convexity_enabled=True,
            paper_portfolio_overrides=_budget_variant_paper_overrides(base, variant),
        )
        snapshot = _scenario_snapshot(
            variant_result,
            current_symbols,
            report_root,
            scenario_name,
        )
        variant_results[variant["name"]] = {
            "variant": variant,
            "snapshot": snapshot,
        }
        baseline_key = f"baseline_vs_{variant['name']}"
        routed_key = f"routed_h1_vs_{variant['name']}"
        comparisons[baseline_key] = _build_comparison(baseline_snapshot, snapshot)
        comparisons[routed_key] = _build_comparison(routed_snapshot, snapshot)

        label = f"allocator_budget_{variant['name']}_overlay"
        competition_report = _build_competition_report(
            report_root,
            routed_snapshot,
            snapshot,
            label,
        )
        lean_sleeve_report = _build_lean_sleeve_report(
            report_root,
            routed_snapshot,
            snapshot,
            label,
        )
        verdict = _build_variant_verdict(
            routed_h1=routed_snapshot,
            candidate=snapshot,
            comparison=comparisons[routed_key],
        )
        variant_results[variant["name"]]["competition_report"] = competition_report
        variant_results[variant["name"]]["lean_sleeve_report"] = lean_sleeve_report
        variant_results[variant["name"]]["verdict"] = verdict
        rankings.append(
            _rank_variant(
                snapshot,
                comparisons[routed_key],
                verdict,
            )
        )

    rankings.sort(
        key=lambda row: (
            row["delta_profit_factor_vs_routed_h1"],
            row["delta_median_daily_pnl_vs_routed_h1"],
            row["delta_final_equity_vs_routed_h1"],
            row["delta_trade_count_vs_routed_h1"],
        ),
        reverse=True,
    )
    best_variant = rankings[0] if rankings else None
    summary = {
        "report_root": str(report_root),
        "current_symbols": current_symbols,
        "variants": SWEEP_VARIANTS,
        "scenarios": {
            "current_9_baseline": baseline_snapshot,
            "current_9_plus_routed_h1": routed_snapshot,
            **{
                f"current_9_plus_{name}": data["snapshot"]
                for name, data in variant_results.items()
            },
        },
        "comparisons": comparisons,
        "rankings": rankings,
        "best_variant": best_variant,
        "variant_reports": {
            name: {
                "competition_report": data["competition_report"],
                "lean_sleeve_report": data["lean_sleeve_report"],
                "verdict": data["verdict"],
            }
            for name, data in variant_results.items()
        },
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
            "best_variant": best_variant,
        },
    )


if __name__ == "__main__":
    main()
