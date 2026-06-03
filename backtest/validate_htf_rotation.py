"""Checkpoint-safe recent-regime validation for the 12H rotation engine."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.portfolio_runner import (
    _build_strategy_timeframes,
    _discover_portfolio_symbols,
    _load_full_history,
)
from backtest.validate_htf_12h import (
    _load_progress,
    _load_run_artifacts,
    _run_or_resume_scenario,
    _save_progress,
    _trade_metrics,
)
from config import AppConfig
from entry.htf_rotation import build_htf_rotation_snapshots_by_symbol


def _clone_config(base: AppConfig) -> AppConfig:
    return AppConfig(
        data=deepcopy(base.data),
        config_path=base.config_path,
        root_dir=base.root_dir,
    )


def _strategy_trades(trades: pd.DataFrame, strategy_type: str) -> pd.DataFrame:
    if trades.empty or "strategy_type" not in trades.columns:
        return pd.DataFrame()
    return trades.loc[trades["strategy_type"].fillna("").astype(str) == strategy_type].copy()


def _strategy_pnl(trades: pd.DataFrame, strategy_type: str) -> float:
    subset = _strategy_trades(trades, strategy_type)
    if subset.empty:
        return 0.0
    return float(pd.to_numeric(subset.get("pnl"), errors="coerce").fillna(0.0).sum())


def _top5_contribution_percent(trades: pd.DataFrame) -> float:
    if trades.empty:
        return 0.0
    pnl = pd.to_numeric(trades.get("pnl"), errors="coerce").fillna(0.0)
    total = float(pnl.sum())
    if total == 0.0:
        return 0.0
    top5 = float(pnl.sort_values(ascending=False).head(5).sum())
    return top5 / total


def _strategy_exit_behavior(trades: pd.DataFrame, strategy_type: str) -> dict:
    subset = _strategy_trades(trades, strategy_type)
    if subset.empty:
        return {"counts": {}, "noise_exits_count": 0}
    reasons = subset["exit_reason"].fillna("unknown").astype(str)
    counts = {str(key): int(value) for key, value in reasons.value_counts().items()}
    noise_patterns = ("trend weakness", "state exit", "slow grind exit", "time exit")
    noise_count = int(sum(counts.get(pattern, 0) for pattern in noise_patterns))
    return {"counts": counts, "noise_exits_count": noise_count}


def _strategy_overlap(trades: pd.DataFrame, strategy_type: str) -> dict:
    if trades.empty:
        return {
            "trade_count": 0,
            "overlap_count": 0,
            "overlap_ratio": 0.0,
        }
    working = trades.copy()
    working["entry_time"] = pd.to_datetime(working["entry_time"], errors="coerce")
    working["exit_time"] = pd.to_datetime(working["exit_time"], errors="coerce")
    working = working.dropna(subset=["entry_time", "exit_time"])
    target = working.loc[working["strategy_type"].fillna("").astype(str) == strategy_type].copy()
    other = working.loc[working["strategy_type"].fillna("").astype(str) != strategy_type].copy()
    if target.empty:
        return {
            "trade_count": 0,
            "overlap_count": 0,
            "overlap_ratio": 0.0,
        }

    overlap_count = 0
    for _, trade in target.iterrows():
        symbol_matches = other["symbol"].astype(str) == str(trade["symbol"])
        candidates = other.loc[symbol_matches]
        if candidates.empty:
            continue
        overlaps = candidates.loc[
            (candidates["entry_time"] <= trade["exit_time"])
            & (candidates["exit_time"] >= trade["entry_time"])
        ]
        if not overlaps.empty:
            overlap_count += 1

    trade_count = int(len(target))
    return {
        "trade_count": trade_count,
        "overlap_count": int(overlap_count),
        "overlap_ratio": float(overlap_count / trade_count) if trade_count else 0.0,
    }


def _scenario_snapshot(result: dict) -> dict:
    trades = result["trades"]
    signals = result["signals"]
    rotation_trades = _strategy_trades(trades, "htf_12h_rotation")
    signal_reason_counts = {}
    if not signals.empty and "selection_reason" in signals.columns:
        mask = signals.get("strategy_type", "").fillna("").astype(str) == "htf_12h_rotation"
        if mask.any():
            signal_reason_counts = {
                str(key): int(value)
                for key, value in signals.loc[mask, "selection_reason"].fillna("unknown").astype(str).value_counts().items()
            }
    return {
        "name": result["name"],
        "artifacts_complete": bool(result.get("artifacts_complete", False)),
        "last_equity_timestamp": result.get("last_equity_timestamp"),
        "metrics": result["metrics"],
        "rotation_pnl_direct": _strategy_pnl(trades, "htf_12h_rotation"),
        "rotation_trade_count": int(len(rotation_trades)),
        "rotation_exit_behavior": _strategy_exit_behavior(trades, "htf_12h_rotation"),
        "rotation_overlap": _strategy_overlap(trades, "htf_12h_rotation"),
        "rotation_top5_contribution_pct": _top5_contribution_percent(rotation_trades),
        "rotation_selection_reasons": signal_reason_counts,
    }


def _build_rotation_funnel(base_config: AppConfig, *, start_date: str, end_date: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    config = _clone_config(base_config)
    config.data.setdefault("history", {})["start_date"] = str(start_date)
    config.data.setdefault("history", {})["end_date"] = str(end_date)

    rows = []
    symbols = _discover_portfolio_symbols(config)
    interval = config.require("binance", "default_interval")
    for symbol in symbols:
        df_1m, _ = _load_full_history(symbol, interval, config)
        df_15m, _, df_12h, df_1d, df_1w = _build_strategy_timeframes(df_1m, config=config)
        snapshot = build_htf_rotation_snapshots_by_symbol(
            {symbol: df_15m.index},
            {symbol: df_12h},
            {symbol: df_1d},
            {symbol: df_1w},
            config=config,
        )[symbol]
        new_candles = snapshot.loc[snapshot["htf_rotation_new_candle"] == True].copy()  # noqa: E712
        frame = pd.DataFrame(index=new_candles.index)
        frame["timestamp"] = new_candles.index
        frame["symbol"] = symbol
        frame["side"] = "long"
        frame["year"] = pd.DatetimeIndex(new_candles.index).year
        frame["signal_family"] = new_candles["signal_family_long"].astype(str).replace("", "none")
        frame["raw_12h_events"] = 1
        frame["passed_12h_structure"] = new_candles["htf_pass_structure_long"].astype(bool)
        frame["passed_1d_context"] = new_candles["htf_pass_1d_context_long"].astype(bool)
        frame["passed_1w_context"] = new_candles["htf_pass_1w_context_long"].astype(bool)
        frame["passed_context_gate"] = new_candles["htf_pass_context_gate_long"].astype(bool)
        frame["passed_persistence"] = new_candles["htf_pass_persistence_long"].astype(bool)
        frame["passed_expansion"] = new_candles["htf_pass_expansion_long"].astype(bool)
        frame["passed_stretch_filter"] = new_candles["htf_pass_stretch_long"].astype(bool)
        frame["passed_quality"] = new_candles["htf_pass_quality_long"].astype(bool)
        frame["passed_liquidity"] = new_candles["htf_pass_liquidity_long"].astype(bool)
        frame["passed_score"] = new_candles["htf_pass_score_long"].astype(bool)
        frame["passed_top_rank"] = new_candles["htf_rotation_top_rank_pass"].astype(bool)
        frame["opened_rotation_trade"] = new_candles["signal_event_long"].astype(bool)
        rows.append(frame)

    funnel_rows = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if funnel_rows.empty:
        totals = {}
        return funnel_rows, pd.DataFrame(), totals

    funnel_rows["rejection_gate"] = pd.Series("opened", index=funnel_rows.index)
    for gate_name, gate_mask in [
        ("structure_gate", ~funnel_rows["passed_12h_structure"]),
        ("context_gate", funnel_rows["passed_12h_structure"] & ~funnel_rows["passed_context_gate"]),
        ("persistence_gate", funnel_rows["passed_12h_structure"] & funnel_rows["passed_context_gate"] & ~funnel_rows["passed_persistence"]),
        ("expansion_gate", funnel_rows["passed_12h_structure"] & funnel_rows["passed_context_gate"] & funnel_rows["passed_persistence"] & ~funnel_rows["passed_expansion"]),
        ("stretch_gate", funnel_rows["passed_12h_structure"] & funnel_rows["passed_context_gate"] & funnel_rows["passed_persistence"] & funnel_rows["passed_expansion"] & ~funnel_rows["passed_stretch_filter"]),
        ("quality_gate", funnel_rows["passed_12h_structure"] & funnel_rows["passed_context_gate"] & funnel_rows["passed_persistence"] & funnel_rows["passed_expansion"] & funnel_rows["passed_stretch_filter"] & ~funnel_rows["passed_quality"]),
        ("liquidity_gate", funnel_rows["passed_12h_structure"] & funnel_rows["passed_context_gate"] & funnel_rows["passed_persistence"] & funnel_rows["passed_expansion"] & funnel_rows["passed_stretch_filter"] & funnel_rows["passed_quality"] & ~funnel_rows["passed_liquidity"]),
        ("score_gate", funnel_rows["passed_12h_structure"] & funnel_rows["passed_context_gate"] & funnel_rows["passed_persistence"] & funnel_rows["passed_expansion"] & funnel_rows["passed_stretch_filter"] & funnel_rows["passed_quality"] & funnel_rows["passed_liquidity"] & ~funnel_rows["passed_score"]),
        ("top_rank_gate", funnel_rows["passed_12h_structure"] & funnel_rows["passed_context_gate"] & funnel_rows["passed_persistence"] & funnel_rows["passed_expansion"] & funnel_rows["passed_stretch_filter"] & funnel_rows["passed_quality"] & funnel_rows["passed_liquidity"] & funnel_rows["passed_score"] & ~funnel_rows["passed_top_rank"]),
    ]:
        funnel_rows.loc[gate_mask, "rejection_gate"] = gate_name

    totals = {
        "raw_12h_events": int(funnel_rows["raw_12h_events"].sum()),
        "passed_12h_structure": int(funnel_rows["passed_12h_structure"].sum()),
        "passed_context_gate": int((funnel_rows["passed_12h_structure"] & funnel_rows["passed_context_gate"]).sum()),
        "passed_persistence": int((funnel_rows["passed_12h_structure"] & funnel_rows["passed_context_gate"] & funnel_rows["passed_persistence"]).sum()),
        "passed_expansion": int((funnel_rows["passed_12h_structure"] & funnel_rows["passed_context_gate"] & funnel_rows["passed_persistence"] & funnel_rows["passed_expansion"]).sum()),
        "passed_stretch_filter": int((funnel_rows["passed_12h_structure"] & funnel_rows["passed_context_gate"] & funnel_rows["passed_persistence"] & funnel_rows["passed_expansion"] & funnel_rows["passed_stretch_filter"]).sum()),
        "passed_quality": int((funnel_rows["passed_12h_structure"] & funnel_rows["passed_context_gate"] & funnel_rows["passed_persistence"] & funnel_rows["passed_expansion"] & funnel_rows["passed_stretch_filter"] & funnel_rows["passed_quality"]).sum()),
        "passed_liquidity": int((funnel_rows["passed_12h_structure"] & funnel_rows["passed_context_gate"] & funnel_rows["passed_persistence"] & funnel_rows["passed_expansion"] & funnel_rows["passed_stretch_filter"] & funnel_rows["passed_quality"] & funnel_rows["passed_liquidity"]).sum()),
        "passed_score": int((funnel_rows["passed_12h_structure"] & funnel_rows["passed_context_gate"] & funnel_rows["passed_persistence"] & funnel_rows["passed_expansion"] & funnel_rows["passed_stretch_filter"] & funnel_rows["passed_quality"] & funnel_rows["passed_liquidity"] & funnel_rows["passed_score"]).sum()),
        "passed_top_rank": int((funnel_rows["passed_12h_structure"] & funnel_rows["passed_context_gate"] & funnel_rows["passed_persistence"] & funnel_rows["passed_expansion"] & funnel_rows["passed_stretch_filter"] & funnel_rows["passed_quality"] & funnel_rows["passed_liquidity"] & funnel_rows["passed_score"] & funnel_rows["passed_top_rank"]).sum()),
        "opened_rotation_trade": int(funnel_rows["opened_rotation_trade"].sum()),
    }
    return funnel_rows, pd.DataFrame([totals]), totals


def _scenario_flags(
    *,
    recent_start: str,
    recent_end: str,
    core_enabled: bool,
    swing_enabled: bool,
    htf_enabled: bool,
    rotation_enabled: bool,
) -> dict:
    return {
        "core_enabled": core_enabled,
        "swing_enabled": swing_enabled,
        "htf_enabled": htf_enabled,
        "convexity_enabled": True,
        "history_start_date": recent_start,
        "history_end_date": recent_end,
        "strategy_overrides": {
            "htf_12h_rotation": {
                "enabled": bool(rotation_enabled),
                "allow_pyramiding": False,
            }
        },
    }


def main():
    base = AppConfig.load()
    base_output = Path(base.require("backtest", "output_dir"))
    report_root = base_output / "htf_rotation_validation_20260603"
    report_root.mkdir(parents=True, exist_ok=True)
    progress = _load_progress(report_root)
    recent_start = "2025-01-01"
    recent_end = str(base.require("history", "end_date"))

    funnel_rows, funnel_totals_df, funnel_totals = _build_rotation_funnel(
        base,
        start_date=recent_start,
        end_date=recent_end,
    )
    if not funnel_rows.empty:
        funnel_rows.to_csv(report_root / "rotation_funnel_rows.csv", index=False)
        funnel_totals_df.to_csv(report_root / "rotation_funnel_totals.csv", index=False)
        (
            funnel_rows.groupby(
                ["symbol", "side", "signal_family", "year", "rejection_gate"],
                as_index=False,
            )
            .size()
            .rename(columns={"size": "count"})
            .to_csv(report_root / "rotation_gate_breakdown.csv", index=False)
        )

    scenarios = {}
    scenario_defs = [
        ("rotation_only", "scenario_rotation_only", _scenario_flags(
            recent_start=recent_start,
            recent_end=recent_end,
            core_enabled=False,
            swing_enabled=False,
            htf_enabled=False,
            rotation_enabled=True,
        )),
        ("core_only", "scenario_core_only", _scenario_flags(
            recent_start=recent_start,
            recent_end=recent_end,
            core_enabled=True,
            swing_enabled=False,
            htf_enabled=False,
            rotation_enabled=False,
        )),
        ("core_plus_rotation", "scenario_core_plus_rotation", _scenario_flags(
            recent_start=recent_start,
            recent_end=recent_end,
            core_enabled=True,
            swing_enabled=False,
            htf_enabled=False,
            rotation_enabled=True,
        )),
        ("core_plus_htf", "scenario_core_plus_htf", _scenario_flags(
            recent_start=recent_start,
            recent_end=recent_end,
            core_enabled=True,
            swing_enabled=False,
            htf_enabled=True,
            rotation_enabled=False,
        )),
        ("core_plus_htf_plus_rotation", "scenario_core_plus_htf_plus_rotation", _scenario_flags(
            recent_start=recent_start,
            recent_end=recent_end,
            core_enabled=True,
            swing_enabled=False,
            htf_enabled=True,
            rotation_enabled=True,
        )),
        ("full_stack", "scenario_full_stack", _scenario_flags(
            recent_start=recent_start,
            recent_end=recent_end,
            core_enabled=True,
            swing_enabled=True,
            htf_enabled=True,
            rotation_enabled=False,
        )),
        ("full_stack_plus_rotation", "scenario_full_stack_plus_rotation", _scenario_flags(
            recent_start=recent_start,
            recent_end=recent_end,
            core_enabled=True,
            swing_enabled=True,
            htf_enabled=True,
            rotation_enabled=True,
        )),
    ]

    for key, name, flags in scenario_defs:
        result = _run_or_resume_scenario(name, base, report_root, progress, **flags)
        scenarios[key] = _scenario_snapshot(result)
        progress[key] = scenarios[key]
        _save_progress(report_root, progress)

    comparisons = {
        "rotation_vs_core_only": {
            "delta_final_equity": float(scenarios["core_plus_rotation"]["metrics"]["final_equity"]) - float(scenarios["core_only"]["metrics"]["final_equity"]),
            "delta_median_daily_pnl": float(scenarios["core_plus_rotation"]["metrics"]["median_daily_pnl"]) - float(scenarios["core_only"]["metrics"]["median_daily_pnl"]),
            "delta_recent_median_daily_pnl": float(scenarios["core_plus_rotation"]["metrics"]["recent_2025_plus_median_daily_pnl"]) - float(scenarios["core_only"]["metrics"]["recent_2025_plus_median_daily_pnl"]),
            "rotation_incremental_pnl": scenarios["core_plus_rotation"]["rotation_pnl_direct"],
        },
        "rotation_vs_core_plus_htf": {
            "delta_final_equity": float(scenarios["core_plus_htf_plus_rotation"]["metrics"]["final_equity"]) - float(scenarios["core_plus_htf"]["metrics"]["final_equity"]),
            "delta_median_daily_pnl": float(scenarios["core_plus_htf_plus_rotation"]["metrics"]["median_daily_pnl"]) - float(scenarios["core_plus_htf"]["metrics"]["median_daily_pnl"]),
            "delta_recent_median_daily_pnl": float(scenarios["core_plus_htf_plus_rotation"]["metrics"]["recent_2025_plus_median_daily_pnl"]) - float(scenarios["core_plus_htf"]["metrics"]["recent_2025_plus_median_daily_pnl"]),
            "rotation_incremental_pnl": scenarios["core_plus_htf_plus_rotation"]["rotation_pnl_direct"],
        },
        "rotation_vs_full_stack": {
            "delta_final_equity": float(scenarios["full_stack_plus_rotation"]["metrics"]["final_equity"]) - float(scenarios["full_stack"]["metrics"]["final_equity"]),
            "delta_median_daily_pnl": float(scenarios["full_stack_plus_rotation"]["metrics"]["median_daily_pnl"]) - float(scenarios["full_stack"]["metrics"]["median_daily_pnl"]),
            "delta_recent_median_daily_pnl": float(scenarios["full_stack_plus_rotation"]["metrics"]["recent_2025_plus_median_daily_pnl"]) - float(scenarios["full_stack"]["metrics"]["recent_2025_plus_median_daily_pnl"]),
            "rotation_incremental_pnl": scenarios["full_stack_plus_rotation"]["rotation_pnl_direct"],
        },
    }

    summary = {
        "report_root": str(report_root),
        "recent_window": {
            "start_date": recent_start,
            "end_date": recent_end,
        },
        "funnel_totals": funnel_totals,
        "scenarios": scenarios,
        "comparisons": comparisons,
    }

    with (report_root / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, default=str)

    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
