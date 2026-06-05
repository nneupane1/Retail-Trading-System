"""Side-policy portfolio validation for the research-only h1_execution sleeve."""

from __future__ import annotations

import json
from pathlib import Path

from backtest.validate_expanded_universe_allocator import (
    _build_comparison,
    _build_lean_sleeve_report,
    _scenario_snapshot,
)
from backtest.validate_h1_portfolio import (
    BASELINE_SOURCE_ROOT,
    BASELINE_SOURCE_SCENARIO,
    HOLDOUT_START,
    _build_verdict,
    _load_existing_baseline,
    _paper_portfolio_overrides,
)
from backtest.validate_h6_standard_portfolio import _build_competition_report
from backtest.validate_htf_12h import (
    _clone_config,
    _load_progress,
    _run_or_resume_scenario,
    _save_progress,
)
from config import AppConfig


ALL_SYMBOL_ROOT = "h1_execution_portfolio_validation_current"
ALL_SYMBOL_SCENARIO = "scenario_current_9_plus_h1_execution"


def _report_root(base: AppConfig) -> Path:
    return Path(base.require("backtest", "output_dir")) / "h1_side_policy_portfolio_validation_current"


def _load_policy(base: AppConfig) -> dict:
    path = Path(base.require("backtest", "output_dir")) / "h1_policy_current" / "h1_policy.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing h1 policy artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_symbols(values) -> list[str]:
    return [str(symbol).upper() for symbol in (values or [])]


def _load_existing_snapshot(
    base: AppConfig,
    root_name: str,
    scenario_name: str,
    symbols_used: list[str],
    report_root: Path,
    scenario_key: str,
) -> dict:
    output_dir = Path(base.require("backtest", "output_dir")) / root_name / scenario_name
    from backtest.validate_htf_12h import _load_run_artifacts, _trade_metrics

    trades, equity, daily, signals = _load_run_artifacts(output_dir)
    if trades.empty and equity.empty:
        raise FileNotFoundError(f"Missing completed artifacts for {scenario_name}: {output_dir}")
    metrics = _trade_metrics(trades, equity, daily)
    last_equity_ts = None
    if not equity.empty and "timestamp" in equity.columns:
        last_equity_ts = str(equity["timestamp"].iloc[-1])
    result = {
        "name": scenario_name,
        "output_dir": str(output_dir),
        "backtest_completed": True,
        "last_equity_timestamp": last_equity_ts,
        "artifacts_complete": True,
        "metrics": metrics,
        "trades": trades,
        "equity": equity,
        "daily": daily,
        "signals": signals,
        "resumed_from_artifacts": True,
    }
    return _scenario_snapshot(result, symbols_used, report_root, scenario_key)


def _strategy_overrides(
    *,
    allowed_symbols: list[str],
    allowed_sides: list[str],
    long_selection_threshold_offset: float,
    short_selection_threshold_offset: float,
    long_risk_multiplier: float,
    short_risk_multiplier: float,
) -> dict:
    return {
        "h1_execution": {
            "enabled": True,
            "allowed_symbols": _normalize_symbols(allowed_symbols),
            "blocked_symbols": [],
            "allowed_sides": [str(side).lower() for side in (allowed_sides or [])],
            "long_selection_threshold_offset": float(long_selection_threshold_offset),
            "short_selection_threshold_offset": float(short_selection_threshold_offset),
            "long_risk_multiplier": float(long_risk_multiplier),
            "short_risk_multiplier": float(short_risk_multiplier),
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

    policy = _load_policy(base)
    current_symbols = _normalize_symbols(policy.get("current_9_symbols"))
    preferred_side_bias = str(policy.get("preferred_side_bias") or "balanced").lower()

    _write_status(
        report_root,
        {
            "stage": "running",
            "holdout_window": {
                "start_date": HOLDOUT_START,
                "end_date": str(base.require("history", "end_date")),
            },
            "current_symbols": current_symbols,
            "preferred_side_bias": preferred_side_bias,
        },
    )

    baseline_result = _load_existing_baseline(base)
    if baseline_result is None:
        raise FileNotFoundError(
            f"Missing baseline artifacts under {BASELINE_SOURCE_ROOT}/{BASELINE_SOURCE_SCENARIO}"
        )
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

    short_biased_cfg = _clone_config(base)
    short_biased_result = _run_or_resume_scenario(
        "scenario_current_9_plus_h1_short_biased",
        short_biased_cfg,
        report_root,
        progress,
        history_start_date=HOLDOUT_START,
        history_end_date=str(base.require("history", "end_date")),
        core_enabled=True,
        swing_enabled=True,
        htf_enabled=True,
        convexity_enabled=True,
        paper_portfolio_overrides=_paper_portfolio_overrides(base),
        strategy_overrides=_strategy_overrides(
            allowed_symbols=current_symbols,
            allowed_sides=["long", "short"],
            long_selection_threshold_offset=0.00,
            short_selection_threshold_offset=-0.04,
            long_risk_multiplier=0.90,
            short_risk_multiplier=1.10,
        ),
    )
    short_biased_snapshot = _scenario_snapshot(
        short_biased_result,
        current_symbols,
        report_root,
        "current_9_plus_h1_short_biased",
    )

    short_only_cfg = _clone_config(base)
    short_only_result = _run_or_resume_scenario(
        "scenario_current_9_plus_h1_short_only",
        short_only_cfg,
        report_root,
        progress,
        history_start_date=HOLDOUT_START,
        history_end_date=str(base.require("history", "end_date")),
        core_enabled=True,
        swing_enabled=True,
        htf_enabled=True,
        convexity_enabled=True,
        paper_portfolio_overrides=_paper_portfolio_overrides(base),
        strategy_overrides=_strategy_overrides(
            allowed_symbols=current_symbols,
            allowed_sides=["short"],
            long_selection_threshold_offset=0.00,
            short_selection_threshold_offset=-0.04,
            long_risk_multiplier=0.90,
            short_risk_multiplier=1.10,
        ),
    )
    short_only_snapshot = _scenario_snapshot(
        short_only_result,
        current_symbols,
        report_root,
        "current_9_plus_h1_short_only",
    )

    comparisons = {
        "baseline_vs_all": _build_comparison(baseline_snapshot, all_symbol_snapshot),
        "baseline_vs_short_biased": _build_comparison(baseline_snapshot, short_biased_snapshot),
        "baseline_vs_short_only": _build_comparison(baseline_snapshot, short_only_snapshot),
        "all_vs_short_biased": _build_comparison(all_symbol_snapshot, short_biased_snapshot),
        "all_vs_short_only": _build_comparison(all_symbol_snapshot, short_only_snapshot),
        "short_biased_vs_short_only": _build_comparison(short_biased_snapshot, short_only_snapshot),
    }

    short_biased_competition_report = _build_competition_report(
        report_root,
        baseline_snapshot,
        short_biased_snapshot,
        "h1_execution_short_biased_overlay",
    )
    short_biased_lean_sleeve_report = _build_lean_sleeve_report(
        report_root,
        baseline_snapshot,
        short_biased_snapshot,
        "h1_execution_short_biased_overlay",
    )
    short_biased_verdict = _build_verdict(
        baseline=baseline_snapshot,
        candidate=short_biased_snapshot,
        comparison=comparisons["baseline_vs_short_biased"],
    )

    short_only_competition_report = _build_competition_report(
        report_root,
        baseline_snapshot,
        short_only_snapshot,
        "h1_execution_short_only_overlay",
    )
    short_only_lean_sleeve_report = _build_lean_sleeve_report(
        report_root,
        baseline_snapshot,
        short_only_snapshot,
        "h1_execution_short_only_overlay",
    )
    short_only_verdict = _build_verdict(
        baseline=baseline_snapshot,
        candidate=short_only_snapshot,
        comparison=comparisons["baseline_vs_short_only"],
    )

    summary = {
        "report_root": str(report_root),
        "current_symbols": current_symbols,
        "preferred_side_bias": preferred_side_bias,
        "scenarios": {
            "current_9_baseline": baseline_snapshot,
            "current_9_plus_h1_all": all_symbol_snapshot,
            "current_9_plus_h1_short_biased": short_biased_snapshot,
            "current_9_plus_h1_short_only": short_only_snapshot,
        },
        "comparisons": comparisons,
        "short_biased_competition_report": short_biased_competition_report,
        "short_biased_lean_sleeve_report": short_biased_lean_sleeve_report,
        "short_biased_verdict": short_biased_verdict,
        "short_only_competition_report": short_only_competition_report,
        "short_only_lean_sleeve_report": short_only_lean_sleeve_report,
        "short_only_verdict": short_only_verdict,
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
            "short_biased_verdict": short_biased_verdict,
            "short_only_verdict": short_only_verdict,
        },
    )


if __name__ == "__main__":
    main()
