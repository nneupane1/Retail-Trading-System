"""Filtered portfolio integration validation for the research-only h1_execution sleeve."""

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
    return Path(base.require("backtest", "output_dir")) / "h1_filtered_portfolio_validation_current"


def _load_policy(base: AppConfig) -> dict:
    path = Path(base.require("backtest", "output_dir")) / "h1_policy_current" / "h1_policy.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing h1 policy artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_symbols(values) -> list[str]:
    return [str(symbol).upper() for symbol in (values or [])]


def _load_existing_snapshot(base: AppConfig, root_name: str, scenario_name: str, symbols_used: list[str], report_root: Path, scenario_key: str) -> dict:
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


def _strategy_overrides(allowed_symbols: list[str], allowed_sides: list[str]) -> dict:
    return {
        "h1_execution": {
            "enabled": True,
            "allowed_symbols": _normalize_symbols(allowed_symbols),
            "blocked_symbols": [],
            "allowed_sides": [str(side).lower() for side in (allowed_sides or [])],
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
    keep_symbols = _normalize_symbols(policy.get("recommended_keep_symbols"))
    keep_review_symbols = _normalize_symbols(policy.get("allowed_symbols_for_filtered_overlay"))
    allowed_sides = [str(side).lower() for side in (policy.get("recommended_allowed_sides") or ["long", "short"])]

    _write_status(
        report_root,
        {
            "stage": "running",
            "holdout_window": {
                "start_date": HOLDOUT_START,
                "end_date": str(base.require("history", "end_date")),
            },
            "current_symbols": current_symbols,
            "keep_symbols": keep_symbols,
            "keep_review_symbols": keep_review_symbols,
            "allowed_sides": allowed_sides,
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

    keep_cfg = _clone_config(base)
    keep_result = _run_or_resume_scenario(
        "scenario_current_9_plus_h1_keep_only",
        keep_cfg,
        report_root,
        progress,
        history_start_date=HOLDOUT_START,
        history_end_date=str(base.require("history", "end_date")),
        core_enabled=True,
        swing_enabled=True,
        htf_enabled=True,
        convexity_enabled=True,
        paper_portfolio_overrides=_paper_portfolio_overrides(base),
        strategy_overrides=_strategy_overrides(keep_symbols, allowed_sides),
    )
    keep_snapshot = _scenario_snapshot(
        keep_result,
        keep_symbols,
        report_root,
        "current_9_plus_h1_keep_only",
    )

    keep_review_snapshot = None
    keep_review_redundant = set(keep_review_symbols) == set(current_symbols)
    if keep_review_redundant:
        keep_review_snapshot = all_symbol_snapshot
    else:
        keep_review_cfg = _clone_config(base)
        keep_review_result = _run_or_resume_scenario(
            "scenario_current_9_plus_h1_keep_review",
            keep_review_cfg,
            report_root,
            progress,
            history_start_date=HOLDOUT_START,
            history_end_date=str(base.require("history", "end_date")),
            core_enabled=True,
            swing_enabled=True,
            htf_enabled=True,
            convexity_enabled=True,
            paper_portfolio_overrides=_paper_portfolio_overrides(base),
            strategy_overrides=_strategy_overrides(keep_review_symbols, allowed_sides),
        )
        keep_review_snapshot = _scenario_snapshot(
            keep_review_result,
            keep_review_symbols,
            report_root,
            "current_9_plus_h1_keep_review",
        )

    baseline_vs_all = _build_comparison(baseline_snapshot, all_symbol_snapshot)
    baseline_vs_keep = _build_comparison(baseline_snapshot, keep_snapshot)
    all_vs_keep = _build_comparison(all_symbol_snapshot, keep_snapshot)
    baseline_vs_keep_review = _build_comparison(baseline_snapshot, keep_review_snapshot)

    keep_competition_report = _build_competition_report(
        report_root,
        baseline_snapshot,
        keep_snapshot,
        "h1_execution_keep_only_overlay",
    )
    keep_lean_sleeve_report = _build_lean_sleeve_report(
        report_root,
        baseline_snapshot,
        keep_snapshot,
        "h1_execution_keep_only_overlay",
    )
    keep_verdict = _build_verdict(
        baseline=baseline_snapshot,
        candidate=keep_snapshot,
        comparison=baseline_vs_keep,
    )

    summary = {
        "report_root": str(report_root),
        "current_symbols": current_symbols,
        "keep_symbols": keep_symbols,
        "keep_review_symbols": keep_review_symbols,
        "allowed_sides": allowed_sides,
        "keep_review_redundant_with_all_symbols": keep_review_redundant,
        "scenarios": {
            "current_9_baseline": baseline_snapshot,
            "current_9_plus_h1_all": all_symbol_snapshot,
            "current_9_plus_h1_keep_only": keep_snapshot,
            "current_9_plus_h1_keep_review": keep_review_snapshot,
        },
        "comparisons": {
            "baseline_vs_all": baseline_vs_all,
            "baseline_vs_keep_only": baseline_vs_keep,
            "all_vs_keep_only": all_vs_keep,
            "baseline_vs_keep_review": baseline_vs_keep_review,
        },
        "keep_only_competition_report": keep_competition_report,
        "keep_only_lean_sleeve_report": keep_lean_sleeve_report,
        "keep_only_verdict": keep_verdict,
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
            "keep_review_redundant_with_all_symbols": keep_review_redundant,
            "keep_only_verdict": keep_verdict,
        },
    )


if __name__ == "__main__":
    main()
