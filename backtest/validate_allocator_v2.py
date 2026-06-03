"""Checkpoint-safe recent-regime validation for allocator-v2 routing."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.validate_htf_12h import (
    _load_progress,
    _run_or_resume_scenario,
    _save_progress,
    _top5_contribution_percent,
)
from config import AppConfig


def _strategy_subset(trades: pd.DataFrame, strategy_type: str) -> pd.DataFrame:
    if trades.empty or "strategy_type" not in trades.columns:
        return pd.DataFrame()
    return trades.loc[trades["strategy_type"].fillna("").astype(str) == str(strategy_type)].copy()


def _strategy_pnl(trades: pd.DataFrame, strategy_type: str) -> float:
    subset = _strategy_subset(trades, strategy_type)
    if subset.empty:
        return 0.0
    return float(pd.to_numeric(subset.get("pnl"), errors="coerce").fillna(0.0).sum())


def _strategy_trade_count(trades: pd.DataFrame, strategy_type: str) -> int:
    return int(len(_strategy_subset(trades, strategy_type)))


def _selection_reason_counts(signals: pd.DataFrame) -> dict:
    if signals.empty or "selection_reason" not in signals.columns:
        return {}
    return {
        str(key): int(value)
        for key, value in signals["selection_reason"].fillna("unknown").astype(str).value_counts().items()
    }


def _scenario_snapshot(result: dict) -> dict:
    trades = result["trades"]
    signals = result["signals"]
    return {
        "name": result["name"],
        "artifacts_complete": bool(result.get("artifacts_complete", False)),
        "last_equity_timestamp": result.get("last_equity_timestamp"),
        "metrics": result["metrics"],
        "top5_trades_contribution_pct": _top5_contribution_percent(trades),
        "strategy_pnl": {
            "core": _strategy_pnl(trades, "core"),
            "swing_moonshot": _strategy_pnl(trades, "swing_moonshot"),
            "htf_12h_moonshot": _strategy_pnl(trades, "htf_12h_moonshot"),
            "htf_12h_rotation": _strategy_pnl(trades, "htf_12h_rotation"),
        },
        "strategy_trade_count": {
            "core": _strategy_trade_count(trades, "core"),
            "swing_moonshot": _strategy_trade_count(trades, "swing_moonshot"),
            "htf_12h_moonshot": _strategy_trade_count(trades, "htf_12h_moonshot"),
            "htf_12h_rotation": _strategy_trade_count(trades, "htf_12h_rotation"),
        },
        "selection_reasons": _selection_reason_counts(signals),
    }


def _allocator_overrides(
    base: AppConfig,
    *,
    enabled: bool,
    agreement_enabled: bool,
) -> dict:
    paper = deepcopy(base.data.get("live_sim", {}).get("paper_portfolio", {}) or {})
    allocator = deepcopy(paper.get("allocator_v2", {}) or {})
    allocator["enabled"] = bool(enabled)
    agreement = deepcopy(allocator.get("agreement_bonus", {}) or {})
    agreement["enabled"] = bool(agreement_enabled)
    allocator["agreement_bonus"] = agreement

    return {
        "strategy_sleeves": deepcopy(paper.get("strategy_sleeves", {}) or {}) if enabled else {},
        "allocator_v2": allocator,
    }


def _scenario_flags(
    base: AppConfig,
    *,
    recent_start: str,
    recent_end: str,
    allocator_enabled: bool,
    agreement_enabled: bool,
) -> dict:
    return {
        "core_enabled": True,
        "swing_enabled": True,
        "htf_enabled": True,
        "convexity_enabled": True,
        "history_start_date": recent_start,
        "history_end_date": recent_end,
        "strategy_overrides": {
            "htf_12h_rotation": {
                "enabled": True,
                "allow_pyramiding": False,
            }
        },
        "paper_portfolio_overrides": _allocator_overrides(
            base,
            enabled=allocator_enabled,
            agreement_enabled=agreement_enabled,
        ),
    }


def main():
    base = AppConfig.load()
    base_output = Path(base.require("backtest", "output_dir"))
    report_root = base_output / "allocator_v2_validation_calibrated_20260603"
    report_root.mkdir(parents=True, exist_ok=True)
    progress = _load_progress(report_root)
    recent_start = "2025-01-01"
    recent_end = str(base.require("history", "end_date"))

    scenario_defs = [
        (
            "baseline_full_stack",
            "scenario_baseline_full_stack",
            _scenario_flags(
                base,
                recent_start=recent_start,
                recent_end=recent_end,
                allocator_enabled=False,
                agreement_enabled=False,
            ),
        ),
        (
            "allocator_v2_no_agreement",
            "scenario_allocator_v2_no_agreement",
            _scenario_flags(
                base,
                recent_start=recent_start,
                recent_end=recent_end,
                allocator_enabled=True,
                agreement_enabled=False,
            ),
        ),
        (
            "allocator_v2_agreement",
            "scenario_allocator_v2_agreement",
            _scenario_flags(
                base,
                recent_start=recent_start,
                recent_end=recent_end,
                allocator_enabled=True,
                agreement_enabled=True,
            ),
        ),
    ]

    scenarios = {}
    for key, name, flags in scenario_defs:
        result = _run_or_resume_scenario(name, base, report_root, progress, **flags)
        scenarios[key] = _scenario_snapshot(result)
        progress[key] = scenarios[key]
        _save_progress(report_root, progress)

    baseline_metrics = scenarios["baseline_full_stack"]["metrics"]
    no_agreement_metrics = scenarios["allocator_v2_no_agreement"]["metrics"]
    agreement_metrics = scenarios["allocator_v2_agreement"]["metrics"]

    comparisons = {
        "allocator_v2_no_agreement_vs_baseline": {
            "delta_final_equity": float(no_agreement_metrics["final_equity"]) - float(
                baseline_metrics["final_equity"]
            ),
            "delta_profit_factor": float(no_agreement_metrics["profit_factor"]) - float(
                baseline_metrics["profit_factor"]
            ),
            "delta_avg_R": float(no_agreement_metrics["avg_R"]) - float(
                baseline_metrics["avg_R"]
            ),
            "delta_median_daily_pnl": float(
                no_agreement_metrics["median_daily_pnl"]
            ) - float(baseline_metrics["median_daily_pnl"]),
            "delta_recent_2025_plus_median_daily_pnl": float(
                no_agreement_metrics["recent_2025_plus_median_daily_pnl"]
            ) - float(baseline_metrics["recent_2025_plus_median_daily_pnl"]),
            "delta_max_drawdown": float(no_agreement_metrics["max_drawdown"]) - float(
                baseline_metrics["max_drawdown"]
            ),
            "delta_trade_count": int(no_agreement_metrics["trade_count"]) - int(
                baseline_metrics["trade_count"]
            ),
            "delta_top5_contribution_pct": float(
                scenarios["allocator_v2_no_agreement"]["top5_trades_contribution_pct"]
            ) - float(scenarios["baseline_full_stack"]["top5_trades_contribution_pct"]),
        },
        "allocator_v2_agreement_vs_baseline": {
            "delta_final_equity": float(agreement_metrics["final_equity"]) - float(
                baseline_metrics["final_equity"]
            ),
            "delta_profit_factor": float(agreement_metrics["profit_factor"]) - float(
                baseline_metrics["profit_factor"]
            ),
            "delta_avg_R": float(agreement_metrics["avg_R"]) - float(
                baseline_metrics["avg_R"]
            ),
            "delta_median_daily_pnl": float(
                agreement_metrics["median_daily_pnl"]
            ) - float(baseline_metrics["median_daily_pnl"]),
            "delta_recent_2025_plus_median_daily_pnl": float(
                agreement_metrics["recent_2025_plus_median_daily_pnl"]
            ) - float(baseline_metrics["recent_2025_plus_median_daily_pnl"]),
            "delta_max_drawdown": float(agreement_metrics["max_drawdown"]) - float(
                baseline_metrics["max_drawdown"]
            ),
            "delta_trade_count": int(agreement_metrics["trade_count"]) - int(
                baseline_metrics["trade_count"]
            ),
            "delta_top5_contribution_pct": float(
                scenarios["allocator_v2_agreement"]["top5_trades_contribution_pct"]
            ) - float(scenarios["baseline_full_stack"]["top5_trades_contribution_pct"]),
        },
        "agreement_vs_no_agreement": {
            "delta_final_equity": float(agreement_metrics["final_equity"]) - float(
                no_agreement_metrics["final_equity"]
            ),
            "delta_profit_factor": float(agreement_metrics["profit_factor"]) - float(
                no_agreement_metrics["profit_factor"]
            ),
            "delta_avg_R": float(agreement_metrics["avg_R"]) - float(
                no_agreement_metrics["avg_R"]
            ),
            "delta_median_daily_pnl": float(
                agreement_metrics["median_daily_pnl"]
            ) - float(no_agreement_metrics["median_daily_pnl"]),
            "delta_recent_2025_plus_median_daily_pnl": float(
                agreement_metrics["recent_2025_plus_median_daily_pnl"]
            ) - float(no_agreement_metrics["recent_2025_plus_median_daily_pnl"]),
            "delta_max_drawdown": float(agreement_metrics["max_drawdown"]) - float(
                no_agreement_metrics["max_drawdown"]
            ),
            "delta_trade_count": int(agreement_metrics["trade_count"]) - int(
                no_agreement_metrics["trade_count"]
            ),
            "delta_top5_contribution_pct": float(
                scenarios["allocator_v2_agreement"]["top5_trades_contribution_pct"]
            ) - float(scenarios["allocator_v2_no_agreement"]["top5_trades_contribution_pct"]),
        },
    }

    summary = {
        "report_root": str(report_root),
        "recent_window": {
            "start_date": recent_start,
            "end_date": recent_end,
        },
        "scenarios": scenarios,
        "comparisons": comparisons,
    }

    with (report_root / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, default=str)

    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
