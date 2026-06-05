"""Portfolio integration validation for the research-only h1_execution sleeve."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from backtest.validate_expanded_universe_allocator import (
    _build_comparison,
    _build_lean_sleeve_report,
    _scenario_snapshot,
)
from backtest.validate_h6_standard_portfolio import _build_competition_report
from backtest.validate_htf_12h import (
    _clone_config,
    _load_run_artifacts,
    _load_progress,
    _run_or_resume_scenario,
    _save_progress,
    _trade_metrics,
)
from common.universe import get_named_universe
from config import AppConfig


HOLDOUT_START = "2026-01-01"
BASELINE_SOURCE_ROOT = "curated_holdout_validation_20260604_lean"
BASELINE_SOURCE_SCENARIO = "scenario_holdout_current_9"


def _report_root(base: AppConfig) -> Path:
    return Path(base.require("backtest", "output_dir")) / "h1_execution_portfolio_validation_current"


def _load_h1_keep_symbols(base: AppConfig) -> list[str]:
    summary_path = (
        Path(base.require("backtest", "output_dir"))
        / "h1_execution_holdout_current"
        / "summary.json"
    )
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing h1 execution holdout summary: {summary_path}")
    with summary_path.open(encoding="utf-8") as file_handle:
        summary = json.load(file_handle)
    symbols = [
        str(symbol).upper()
        for symbol in summary.get("training_symbol_curation", {}).get("keep_symbols", [])
    ]
    if not symbols:
        raise ValueError("No curated h1 keep symbols found in holdout summary.")
    return symbols


def _paper_portfolio_overrides(base: AppConfig) -> dict:
    raw = deepcopy(base.get("live_sim", "paper_portfolio", default={}) or {})

    strategy_allowed = dict(raw.get("strategy_allowed_sides", {}) or {})
    strategy_allowed["h1_execution"] = ["long", "short"]
    raw["strategy_allowed_sides"] = strategy_allowed

    threshold_offsets = dict(raw.get("strategy_threshold_offsets", {}) or {})
    threshold_offsets["h1_execution"] = -0.02
    raw["strategy_threshold_offsets"] = threshold_offsets

    sleeves = dict(raw.get("strategy_sleeves", {}) or {})
    sleeve_cfg = dict(sleeves.get("h1_execution", {}) or {})
    sleeve_cfg.update(
        {
            "enabled": True,
            "reserved_risk_fraction": 0.0025,
            "max_new_positions_per_step": 2,
            "block_if_symbol_has_other_strategy_position": False,
            "ignore_global_step_cap": False,
        }
    )
    sleeves["h1_execution"] = sleeve_cfg
    raw["strategy_sleeves"] = sleeves

    strategy_health_profiles = dict(raw.get("strategy_health_profiles", {}) or {})
    strategy_health_profiles.setdefault(
        "h1_execution",
        {
            "recency_lookback_days": 120,
            "recency_max_trades": 120,
            "recency_min_trades": 20,
            "neutral_below_min_trades": True,
            "disable_when_negative": False,
            "negative_risk_multiplier": 0.85,
            "positive_floor_multiplier": 0.90,
            "positive_cap": 1.10,
            "emergency_disable_min_trades": 30,
            "emergency_disable_avg_r": -0.20,
        },
    )
    raw["strategy_health_profiles"] = strategy_health_profiles

    strategy_bucket_health_profiles = dict(raw.get("strategy_bucket_health_profiles", {}) or {})
    strategy_bucket_health_profiles.setdefault(
        "h1_execution",
        {
            "enabled": True,
            "recency_lookback_days": 120,
            "recency_max_trades": 120,
            "recency_min_trades": 20,
            "neutral_below_min_trades": True,
            "disable_when_negative": False,
            "negative_risk_multiplier": 0.85,
            "positive_floor_multiplier": 0.90,
            "positive_cap": 1.10,
            "apply_to_threshold_derivation": False,
        },
    )
    raw["strategy_bucket_health_profiles"] = strategy_bucket_health_profiles

    allocator = dict(raw.get("allocator_v2", {}) or {})
    allocator_sleeves = dict(allocator.get("sleeves", {}) or {})
    allocator_sleeves["h1_execution"] = {
        "priority_multiplier": 0.90,
        "rank_weights": [1.0, 0.70, 0.40],
        "max_candidates": 3,
        "max_risk_fraction_multiplier": 1.10,
        "absolute_max_risk_fraction": 0.0025,
    }
    allocator["sleeves"] = allocator_sleeves
    raw["allocator_v2"] = allocator

    return raw


def _strategy_overrides(keep_symbols: list[str]) -> dict:
    return {
        "h1_execution": {
            "enabled": True,
            "allowed_symbols": [str(symbol).upper() for symbol in keep_symbols],
            "blocked_symbols": [],
        }
    }


def _write_status(report_root: Path, payload: dict) -> None:
    with (report_root / "status.json").open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2, default=str)


def _build_verdict(*, baseline: dict, candidate: dict, comparison: dict) -> dict:
    candidate_pnl = candidate.get("strategy_pnl", {})
    baseline_pnl = baseline.get("strategy_pnl", {})
    h1_delta = float(candidate_pnl.get("h1_execution", 0.0)) - float(
        baseline_pnl.get("h1_execution", 0.0)
    )
    return {
        "did_h1_add_positive_pnl": bool(h1_delta > 0.0),
        "did_trade_flow_hold_up": bool(
            float(candidate["metrics"]["trade_count"]) >= 0.95 * float(baseline["metrics"]["trade_count"])
        ),
        "did_median_daily_hold_up": bool(comparison["delta_median_daily_pnl"] >= -0.10),
        "did_drawdown_remain_acceptable": bool(comparison["delta_max_drawdown"] >= -0.02),
        "is_h1_additive_to_portfolio": bool(
            comparison["delta_final_equity"] > 0.0
            and comparison["delta_profit_factor"] >= -0.02
            and comparison["delta_median_daily_pnl"] >= -0.10
            and comparison["delta_max_drawdown"] >= -0.02
            and h1_delta > 0.0
        ),
    }


def _load_existing_baseline(base: AppConfig) -> dict | None:
    output_dir = (
        Path(base.require("backtest", "output_dir"))
        / BASELINE_SOURCE_ROOT
        / BASELINE_SOURCE_SCENARIO
    )
    trades, equity, daily, signals = _load_run_artifacts(output_dir)
    if trades.empty and equity.empty:
        return None
    metrics = _trade_metrics(trades, equity, daily)
    last_equity_ts = None
    if not equity.empty and "timestamp" in equity.columns:
        last_equity_ts = str(equity["timestamp"].iloc[-1])
    return {
        "name": BASELINE_SOURCE_SCENARIO,
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
        "loaded_from_existing_holdout": True,
    }


def main() -> None:
    base = AppConfig.load()
    report_root = _report_root(base)
    report_root.mkdir(parents=True, exist_ok=True)
    progress = _load_progress(report_root)

    symbols = get_named_universe(base, "current_9") or [
        str(symbol).upper()
        for symbol in base.require("backtest", "portfolio_replay", "symbols")
    ]
    keep_symbols = _load_h1_keep_symbols(base)

    scenarios = {}
    _write_status(
        report_root,
        {
            "stage": "running",
            "holdout_window": {
                "start_date": HOLDOUT_START,
                "end_date": str(base.require("history", "end_date")),
            },
            "current_symbols": [str(symbol).upper() for symbol in symbols],
            "h1_keep_symbols": keep_symbols,
        },
    )

    baseline_result = _load_existing_baseline(base)
    if baseline_result is None:
        baseline_cfg = _clone_config(base)
        baseline_result = _run_or_resume_scenario(
            "scenario_current_9_baseline",
            baseline_cfg,
            report_root,
            progress,
            history_start_date=HOLDOUT_START,
            history_end_date=str(base.require("history", "end_date")),
            core_enabled=True,
            swing_enabled=True,
            htf_enabled=True,
            convexity_enabled=True,
        )
    scenarios["current_9_baseline"] = baseline_result

    overlay_cfg = _clone_config(base)
    scenarios["current_9_plus_h1_execution"] = _run_or_resume_scenario(
        "scenario_current_9_plus_h1_execution",
        overlay_cfg,
        report_root,
        progress,
        history_start_date=HOLDOUT_START,
        history_end_date=str(base.require("history", "end_date")),
        core_enabled=True,
        swing_enabled=True,
        htf_enabled=True,
        convexity_enabled=True,
        paper_portfolio_overrides=_paper_portfolio_overrides(base),
        strategy_overrides=_strategy_overrides(keep_symbols),
    )

    baseline_snapshot = _scenario_snapshot(
        baseline_result,
        [str(symbol).upper() for symbol in symbols],
        report_root,
        "current_9_baseline",
    )
    overlay_snapshot = _scenario_snapshot(
        scenarios["current_9_plus_h1_execution"],
        [str(symbol).upper() for symbol in keep_symbols],
        report_root,
        "current_9_plus_h1_execution",
    )
    comparison = _build_comparison(baseline_snapshot, overlay_snapshot)
    lean_sleeve_report = _build_lean_sleeve_report(
        report_root,
        baseline_snapshot,
        overlay_snapshot,
        "h1_execution_overlay",
    )
    competition_report = _build_competition_report(
        report_root,
        baseline_snapshot,
        overlay_snapshot,
        "h1_execution_overlay",
    )
    verdict = _build_verdict(
        baseline=baseline_snapshot,
        candidate=overlay_snapshot,
        comparison=comparison,
    )

    summary = {
        "report_root": str(report_root),
        "current_symbols": [str(symbol).upper() for symbol in symbols],
        "h1_keep_symbols": keep_symbols,
        "scenarios": {
            "current_9_baseline": baseline_snapshot,
            "current_9_plus_h1_execution": overlay_snapshot,
        },
        "comparison": comparison,
        "lean_sleeve_report": lean_sleeve_report,
        "competition_report": competition_report,
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
