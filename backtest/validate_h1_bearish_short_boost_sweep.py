"""Sweep milder bearish 12H short-boost variants for the research-only h1 sleeve."""

from __future__ import annotations

import json
from pathlib import Path

from backtest.validate_expanded_universe_allocator import (
    _build_comparison,
    _build_lean_sleeve_report,
    _scenario_snapshot,
)
from backtest.validate_h1_bearish_short_boost_portfolio import (
    ALL_SYMBOL_ROOT,
    ALL_SYMBOL_SCENARIO,
    SHORT_ONLY_ROOT,
    SHORT_ONLY_SCENARIO,
)
from backtest.validate_h1_context_policy_portfolio import _current_symbols
from backtest.validate_h1_portfolio import (
    HOLDOUT_START,
    _build_verdict,
    _load_existing_baseline,
    _paper_portfolio_overrides,
)
from backtest.validate_h1_side_policy_portfolio import _load_existing_snapshot
from backtest.validate_h6_standard_portfolio import _build_competition_report
from backtest.validate_htf_12h import (
    _clone_config,
    _load_progress,
    _run_or_resume_scenario,
    _save_progress,
)
from config import AppConfig


SWEEP_VARIANTS = [
    {
        "name": "mild_a",
        "bearish_short_selection_threshold_offset": -0.05,
        "bearish_short_risk_multiplier": 1.15,
    },
    {
        "name": "mild_b",
        "bearish_short_selection_threshold_offset": -0.055,
        "bearish_short_risk_multiplier": 1.15,
    },
    {
        "name": "mild_c",
        "bearish_short_selection_threshold_offset": -0.05,
        "bearish_short_risk_multiplier": 1.20,
    },
]


def _report_root(base: AppConfig) -> Path:
    return Path(base.require("backtest", "output_dir")) / "h1_bearish_short_boost_sweep_current"


def _variant_strategy_overrides(symbols: list[str], *, bearish_offset: float, bearish_risk: float) -> dict:
    return {
        "h1_execution": {
            "enabled": True,
            "allowed_symbols": [str(symbol).upper() for symbol in symbols],
            "blocked_symbols": [],
            "allowed_sides": ["short"],
            "short_selection_threshold_offset": -0.04,
            "short_risk_multiplier": 1.10,
            "context_side_policy": {
                "bearish": {
                    "allowed_sides": ["short"],
                    "short_selection_threshold_offset": float(bearish_offset),
                    "short_risk_multiplier": float(bearish_risk),
                },
                "neutral": {
                    "allowed_sides": ["short"],
                    "short_selection_threshold_offset": -0.04,
                    "short_risk_multiplier": 1.10,
                },
                "bullish": {
                    "allowed_sides": ["short"],
                    "short_selection_threshold_offset": -0.04,
                    "short_risk_multiplier": 1.10,
                },
            },
            "elite_long_exception": {
                "enabled": False,
            },
        }
    }


def _write_status(report_root: Path, payload: dict) -> None:
    with (report_root / "status.json").open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2, default=str)


def _rank_variant(snapshot: dict, comparison_vs_short_only: dict, verdict: dict) -> dict:
    metrics = snapshot["metrics"]
    return {
        "scenario_name": snapshot["name"],
        "final_equity": float(metrics["final_equity"]),
        "profit_factor": float(metrics["profit_factor"]),
        "median_daily_pnl": float(metrics["median_daily_pnl"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "trade_count": int(metrics["trade_count"]),
        "delta_final_equity_vs_short_only": float(comparison_vs_short_only["delta_final_equity"]),
        "delta_profit_factor_vs_short_only": float(comparison_vs_short_only["delta_profit_factor"]),
        "delta_median_daily_pnl_vs_short_only": float(comparison_vs_short_only["delta_median_daily_pnl"]),
        "delta_max_drawdown_vs_short_only": float(comparison_vs_short_only["delta_max_drawdown"]),
        "delta_trade_count_vs_short_only": int(comparison_vs_short_only["delta_trade_count"]),
        "is_additive_to_baseline": bool(verdict["is_h1_additive_to_portfolio"]),
    }


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
    all_symbol_snapshot = _load_existing_snapshot(
        base,
        ALL_SYMBOL_ROOT,
        ALL_SYMBOL_SCENARIO,
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

    variant_results = {}
    comparisons = {
        "baseline_vs_all": _build_comparison(baseline_snapshot, all_symbol_snapshot),
        "baseline_vs_short_only": _build_comparison(baseline_snapshot, short_only_snapshot),
    }
    rankings = []

    for variant in SWEEP_VARIANTS:
        scenario_name = f"scenario_current_9_plus_h1_bearish_short_boost_{variant['name']}"
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
            paper_portfolio_overrides=_paper_portfolio_overrides(base),
            strategy_overrides=_variant_strategy_overrides(
                current_symbols,
                bearish_offset=variant["bearish_short_selection_threshold_offset"],
                bearish_risk=variant["bearish_short_risk_multiplier"],
            ),
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
        short_only_key = f"short_only_vs_{variant['name']}"
        all_key = f"all_vs_{variant['name']}"
        comparisons[baseline_key] = _build_comparison(baseline_snapshot, snapshot)
        comparisons[short_only_key] = _build_comparison(short_only_snapshot, snapshot)
        comparisons[all_key] = _build_comparison(all_symbol_snapshot, snapshot)

        label = f"h1_execution_bearish_short_boost_{variant['name']}_overlay"
        competition_report = _build_competition_report(
            report_root,
            baseline_snapshot,
            snapshot,
            label,
        )
        lean_sleeve_report = _build_lean_sleeve_report(
            report_root,
            baseline_snapshot,
            snapshot,
            label,
        )
        verdict = _build_verdict(
            baseline=baseline_snapshot,
            candidate=snapshot,
            comparison=comparisons[baseline_key],
        )
        variant_results[variant["name"]]["competition_report"] = competition_report
        variant_results[variant["name"]]["lean_sleeve_report"] = lean_sleeve_report
        variant_results[variant["name"]]["verdict"] = verdict
        rankings.append(
            _rank_variant(
                snapshot,
                comparisons[short_only_key],
                verdict,
            )
        )

    rankings.sort(
        key=lambda row: (
            row["delta_profit_factor_vs_short_only"],
            row["delta_median_daily_pnl_vs_short_only"],
            row["delta_final_equity_vs_short_only"],
            row["delta_trade_count_vs_short_only"],
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
            "current_9_plus_h1_all": all_symbol_snapshot,
            "current_9_plus_h1_short_only": short_only_snapshot,
            **{
                f"current_9_plus_h1_bearish_short_boost_{name}": data["snapshot"]
                for name, data in variant_results.items()
            },
        },
        "comparisons": comparisons,
        "variant_rankings": rankings,
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
