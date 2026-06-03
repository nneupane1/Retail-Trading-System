"""Recent-regime validation for recency-aware control calibration."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pandas as pd

from config import AppConfig
from backtest.validate_htf_12h import (
    _htf_exit_audit,
    _load_progress,
    _overlap_stats,
    _run_or_resume_scenario,
    _save_progress,
    _top5_contribution_percent,
)


def _load_recent_baselines(base_output: Path) -> dict:
    summary_path = base_output / "htf_12h_validation_recent_20260601" / "recent_summary.json"
    if not summary_path.exists():
        return {}
    with summary_path.open(encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _strategy_bucket_profiles(*, core_disable_when_negative: bool, core_negative_risk_multiplier: float) -> dict:
    return {
        "core": {
            "enabled": True,
            "recency_lookback_days": 60,
            "recency_max_trades": 300,
            "recency_min_trades": 100,
            "neutral_below_min_trades": True,
            "disable_when_negative": bool(core_disable_when_negative),
            "negative_risk_multiplier": float(core_negative_risk_multiplier),
            "positive_floor_multiplier": 0.95,
            "positive_cap": 1.10,
            "apply_to_threshold_derivation": True,
        },
        "swing_moonshot": {
            "enabled": True,
            "recency_lookback_days": 180,
            "recency_max_trades": 60,
            "recency_min_trades": 12,
            "neutral_below_min_trades": True,
            "disable_when_negative": True,
            "negative_risk_multiplier": 0.0,
            "positive_floor_multiplier": 0.85,
            "positive_cap": 1.10,
            "apply_to_threshold_derivation": False,
        },
        "htf_12h_moonshot": {
            "enabled": True,
            "recency_lookback_days": 180,
            "recency_max_trades": 50,
            "recency_min_trades": 8,
            "neutral_below_min_trades": True,
            "disable_when_negative": False,
            "negative_risk_multiplier": 0.75,
            "positive_floor_multiplier": 0.90,
            "positive_cap": 1.10,
            "apply_to_threshold_derivation": False,
        },
    }


def _trade_bucket_breakdown(trades: pd.DataFrame) -> list[dict]:
    if trades.empty:
        return []
    working = trades.copy()
    if "strategy_type" not in working.columns or "score_bucket" not in working.columns:
        return []
    working["strategy_type"] = working["strategy_type"].fillna("core").astype(str)
    working["score_bucket"] = working["score_bucket"].fillna("<0.6").astype(str)
    working["pnl"] = pd.to_numeric(working.get("pnl"), errors="coerce").fillna(0.0)
    working["pnl_R_initial"] = pd.to_numeric(
        working.get("pnl_R_initial"),
        errors="coerce",
    ).fillna(0.0)
    rows = []
    for (strategy_type, score_bucket), group in working.groupby(["strategy_type", "score_bucket"]):
        rows.append(
            {
                "strategy_type": str(strategy_type),
                "score_bucket": str(score_bucket),
                "trade_count": int(len(group)),
                "net_pnl": float(group["pnl"].sum()),
                "avg_R": float(group["pnl_R_initial"].mean()) if len(group) else 0.0,
                "median_R": float(group["pnl_R_initial"].median()) if len(group) else 0.0,
                "win_rate": float((group["pnl"] > 0).mean()) if len(group) else 0.0,
            }
        )
    return sorted(rows, key=lambda item: (item["strategy_type"], item["score_bucket"]))


def _scenario_snapshot(result: dict) -> dict:
    trades = result["trades"]
    signals = result["signals"]
    htf_pnl = 0.0
    if not trades.empty and "strategy_type" in trades.columns:
        htf_mask = trades["strategy_type"].fillna("").astype(str) == "htf_12h_moonshot"
        htf_pnl = float(
            pd.to_numeric(trades.loc[htf_mask, "pnl"], errors="coerce").fillna(0.0).sum()
        )

    signal_reason_counts = {}
    if not signals.empty and "selection_reason" in signals.columns:
        signal_reason_counts = {
            str(key): int(value)
            for key, value in signals["selection_reason"].fillna("unknown").astype(str).value_counts().items()
        }

    return {
        "name": result["name"],
        "artifacts_complete": bool(result.get("artifacts_complete", False)),
        "last_equity_timestamp": result.get("last_equity_timestamp"),
        "metrics": result["metrics"],
        "htf_incremental_pnl_direct": htf_pnl,
        "bucket_participation": _trade_bucket_breakdown(trades),
        "selection_reasons": signal_reason_counts,
        "htf_exit_behavior": _htf_exit_audit(trades),
        "htf_overlap": _overlap_stats(trades),
        "top5_trades_contribution_pct": _top5_contribution_percent(trades),
    }


def main():
    base = AppConfig.load()
    base_output = Path(base.require("backtest", "output_dir"))
    report_root = base_output / "recent_control_validation_20260603"
    report_root.mkdir(parents=True, exist_ok=True)
    progress = _load_progress(report_root)
    baselines = _load_recent_baselines(base_output)
    recent_start = "2025-01-01"
    recent_end = str(base.require("history", "end_date"))

    control_profiles = {
        "soft": _strategy_bucket_profiles(
            core_disable_when_negative=False,
            core_negative_risk_multiplier=0.10,
        ),
        "hard": _strategy_bucket_profiles(
            core_disable_when_negative=True,
            core_negative_risk_multiplier=0.0,
        ),
    }

    base_flags = {
        "convexity_enabled": True,
        "htf_strategy_allowed_sides": ["long"],
        "htf_short_risk_multiplier": 0.6,
        "history_start_date": recent_start,
        "history_end_date": recent_end,
    }

    scenario_defs = []
    for profile_name, profile in control_profiles.items():
        overrides = {
            "strategy_bucket_health_profiles": deepcopy(profile),
        }
        scenario_defs.extend(
            [
                {
                    "key": f"{profile_name}_core_only",
                    "name": f"scenario_{profile_name}_core_only",
                    "flags": {
                        **base_flags,
                        "core_enabled": True,
                        "swing_enabled": False,
                        "htf_enabled": False,
                        "paper_portfolio_overrides": overrides,
                    },
                    "baseline_key": "core_only",
                },
                {
                    "key": f"{profile_name}_core_plus_htf",
                    "name": f"scenario_{profile_name}_core_plus_htf",
                    "flags": {
                        **base_flags,
                        "core_enabled": True,
                        "swing_enabled": False,
                        "htf_enabled": True,
                        "paper_portfolio_overrides": overrides,
                    },
                    "baseline_key": "core_plus_htf",
                },
                {
                    "key": f"{profile_name}_core_plus_swing_plus_htf",
                    "name": f"scenario_{profile_name}_core_plus_swing_plus_htf",
                    "flags": {
                        **base_flags,
                        "core_enabled": True,
                        "swing_enabled": True,
                        "htf_enabled": True,
                        "paper_portfolio_overrides": overrides,
                    },
                    "baseline_key": "core_plus_swing_plus_htf",
                },
            ]
        )

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
        baseline_key = scenario["baseline_key"]
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
            "delta_trade_count": int(current_metrics.get("trade_count", 0)) - int(
                baseline_metrics.get("trade_count", 0)
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
        "control_profiles": control_profiles,
        "scenario_results": results,
        "comparisons_vs_recent_baseline": comparisons,
    }

    with (report_root / "recent_control_summary.json").open("w", encoding="utf-8") as file_handle:
        json.dump(summary, file_handle, indent=2, default=str)

    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
