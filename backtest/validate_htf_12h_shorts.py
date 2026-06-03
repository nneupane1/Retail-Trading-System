"""Recent-regime validation for controlled 12H HTF short-side activation."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from config import AppConfig
from backtest.validate_htf_12h import (
    _htf_exit_audit,
    _load_progress,
    _load_run_artifacts,
    _overlap_stats,
    _run_or_resume_scenario,
    _safe_pct,
    _save_progress,
    _top5_contribution_percent,
)


def _load_recent_long_only_baselines(base_output: Path) -> dict:
    summary_path = base_output / "htf_12h_validation_recent_20260601" / "recent_summary.json"
    if not summary_path.exists():
        return {}
    with summary_path.open(encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _htf_trade_breakdown(trades: pd.DataFrame) -> dict:
    if trades.empty or "strategy_type" not in trades.columns:
        return {}
    working = trades.loc[
        trades["strategy_type"].fillna("").astype(str) == "htf_12h_moonshot"
    ].copy()
    if working.empty:
        return {}

    working["pnl"] = pd.to_numeric(working.get("pnl"), errors="coerce").fillna(0.0)
    working["pnl_R_initial"] = pd.to_numeric(
        working.get("pnl_R_initial"),
        errors="coerce",
    ).fillna(0.0)
    breakdown = {}
    for side, group in working.groupby(working["side"].fillna("unknown").astype(str)):
        breakdown[str(side)] = {
            "trade_count": int(len(group)),
            "net_pnl": float(group["pnl"].sum()),
            "avg_R": float(group["pnl_R_initial"].mean()) if len(group) else 0.0,
            "median_R": float(group["pnl_R_initial"].median()) if len(group) else 0.0,
            "max_R": float(group["pnl_R_initial"].max()) if len(group) else 0.0,
            "win_rate": float((group["pnl"] > 0).mean()) if len(group) else 0.0,
        }
    return breakdown


def _htf_signal_breakdown(signals: pd.DataFrame) -> dict:
    if signals.empty or "strategy_type" not in signals.columns:
        return {}
    working = signals.loc[
        signals["strategy_type"].fillna("").astype(str) == "htf_12h_moonshot"
    ].copy()
    if working.empty:
        return {}
    return {
        "by_reason": {
            str(key): int(value)
            for key, value in working["selection_reason"].fillna("unknown").astype(str).value_counts().items()
        },
        "by_side_and_reason": {
            f"{side}|{reason}": int(count)
            for (side, reason), count in working.groupby(
                [
                    working["side"].fillna("unknown").astype(str),
                    working["selection_reason"].fillna("unknown").astype(str),
                ]
            ).size().items()
        },
    }


def _scenario_snapshot(result: dict) -> dict:
    trades = result["trades"]
    signals = result["signals"]
    htf_pnl = 0.0
    if not trades.empty and "strategy_type" in trades.columns:
        htf_mask = trades["strategy_type"].fillna("").astype(str) == "htf_12h_moonshot"
        htf_pnl = float(
            pd.to_numeric(trades.loc[htf_mask, "pnl"], errors="coerce").fillna(0.0).sum()
        )

    return {
        "name": result["name"],
        "artifacts_complete": bool(result.get("artifacts_complete", False)),
        "last_equity_timestamp": result.get("last_equity_timestamp"),
        "metrics": result["metrics"],
        "htf_incremental_pnl_direct": htf_pnl,
        "htf_trade_breakdown": _htf_trade_breakdown(trades),
        "htf_signal_breakdown": _htf_signal_breakdown(signals),
        "htf_exit_behavior": _htf_exit_audit(trades),
        "htf_overlap": _overlap_stats(trades),
        "htf_top5_trades_contribution_pct": _top5_contribution_percent(
            trades.loc[
                trades.get("strategy_type", "").fillna("").astype(str) == "htf_12h_moonshot"
            ].copy()
            if not trades.empty and "strategy_type" in trades.columns
            else pd.DataFrame()
        ),
    }


def main():
    base = AppConfig.load()
    base_output = Path(base.require("backtest", "output_dir"))
    report_root = base_output / "htf_12h_short_validation_recent_20260603"
    report_root.mkdir(parents=True, exist_ok=True)
    progress = _load_progress(report_root)
    baselines = _load_recent_long_only_baselines(base_output)
    recent_start = "2025-01-01"
    recent_end = str(base.require("history", "end_date"))

    scenario_defs = [
        {
            "key": "htf_only_longs",
            "name": "scenario_htf_only_longs",
            "flags": {
                "core_enabled": False,
                "swing_enabled": False,
                "htf_enabled": True,
                "convexity_enabled": False,
                "htf_strategy_allowed_sides": ["long"],
                "htf_short_risk_multiplier": 0.6,
                "history_start_date": recent_start,
                "history_end_date": recent_end,
            },
        },
        {
            "key": "htf_only_long_short",
            "name": "scenario_htf_only_long_short",
            "flags": {
                "core_enabled": False,
                "swing_enabled": False,
                "htf_enabled": True,
                "convexity_enabled": False,
                "htf_strategy_allowed_sides": ["long", "short"],
                "htf_short_risk_multiplier": 0.6,
                "history_start_date": recent_start,
                "history_end_date": recent_end,
            },
        },
        {
            "key": "core_plus_htf_long_short",
            "name": "scenario_core_plus_htf_long_short",
            "flags": {
                "core_enabled": True,
                "swing_enabled": False,
                "htf_enabled": True,
                "convexity_enabled": True,
                "htf_strategy_allowed_sides": ["long", "short"],
                "htf_short_risk_multiplier": 0.6,
                "history_start_date": recent_start,
                "history_end_date": recent_end,
            },
            "baseline_key": "core_plus_htf",
        },
        {
            "key": "core_plus_swing_plus_htf_long_short",
            "name": "scenario_core_plus_swing_plus_htf_long_short",
            "flags": {
                "core_enabled": True,
                "swing_enabled": True,
                "htf_enabled": True,
                "convexity_enabled": True,
                "htf_strategy_allowed_sides": ["long", "short"],
                "htf_short_risk_multiplier": 0.6,
                "history_start_date": recent_start,
                "history_end_date": recent_end,
            },
            "baseline_key": "core_plus_swing_plus_htf",
        },
    ]

    results = {}
    for scenario in scenario_defs:
        result = _run_or_resume_scenario(
            scenario["name"],
            base,
            report_root,
            progress,
            **scenario["flags"],
        )
        results[scenario["key"]] = _scenario_snapshot(result)
        progress[scenario["key"]] = results[scenario["key"]]
        _save_progress(report_root, progress)

    comparisons = {}
    for scenario in scenario_defs:
        baseline_key = scenario.get("baseline_key")
        if not baseline_key:
            continue
        baseline = baselines.get(baseline_key, {})
        baseline_metrics = baseline.get("metrics", {})
        current_metrics = results[scenario["key"]]["metrics"]
        comparisons[scenario["key"]] = {
            "baseline_key": baseline_key,
            "baseline_metrics": baseline_metrics,
            "delta_final_equity": float(current_metrics.get("final_equity", 0.0)) - float(
                baseline_metrics.get("final_equity", 0.0)
            ),
            "delta_net_pnl": float(current_metrics.get("net_pnl", 0.0)) - float(
                baseline_metrics.get("net_pnl", 0.0)
            ),
            "delta_profit_factor": float(current_metrics.get("profit_factor", 0.0)) - float(
                baseline_metrics.get("profit_factor", 0.0)
            ),
            "delta_median_daily_pnl": float(
                current_metrics.get("median_daily_pnl", 0.0)
            ) - float(baseline_metrics.get("median_daily_pnl", 0.0)),
            "delta_recent_2025_plus_median_daily_pnl": float(
                current_metrics.get("recent_2025_plus_median_daily_pnl", 0.0)
            ) - float(baseline_metrics.get("recent_2025_plus_median_daily_pnl", 0.0)),
            "delta_max_drawdown": float(current_metrics.get("max_drawdown", 0.0)) - float(
                baseline_metrics.get("max_drawdown", 0.0)
            ),
        }

    summary = {
        "report_root": str(report_root),
        "baseline_source": str(
            base_output / "htf_12h_validation_recent_20260601" / "recent_summary.json"
        ),
        "recent_window": {
            "start_date": recent_start,
            "end_date": recent_end,
        },
        "scenario_results": results,
        "comparisons_vs_long_only_recent": comparisons,
        "short_activation_verdict": {
            "htf_only_short_trade_count": results["htf_only_long_short"]
            .get("htf_trade_breakdown", {})
            .get("short", {})
            .get("trade_count", 0),
            "htf_only_short_net_pnl": results["htf_only_long_short"]
            .get("htf_trade_breakdown", {})
            .get("short", {})
            .get("net_pnl", 0.0),
            "core_plus_htf_short_trade_count": results["core_plus_htf_long_short"]
            .get("htf_trade_breakdown", {})
            .get("short", {})
            .get("trade_count", 0),
            "core_plus_htf_short_net_pnl": results["core_plus_htf_long_short"]
            .get("htf_trade_breakdown", {})
            .get("short", {})
            .get("net_pnl", 0.0),
            "core_plus_swing_plus_htf_short_trade_count": results[
                "core_plus_swing_plus_htf_long_short"
            ]
            .get("htf_trade_breakdown", {})
            .get("short", {})
            .get("trade_count", 0),
            "core_plus_swing_plus_htf_short_net_pnl": results[
                "core_plus_swing_plus_htf_long_short"
            ]
            .get("htf_trade_breakdown", {})
            .get("short", {})
            .get("net_pnl", 0.0),
        },
    }

    with (report_root / "short_validation_summary.json").open("w", encoding="utf-8") as file_handle:
        json.dump(summary, file_handle, indent=2, default=str)

    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
