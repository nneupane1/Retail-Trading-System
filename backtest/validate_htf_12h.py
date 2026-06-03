"""Stage-based validation and calibration report for the 12H HTF moonshot engine."""

from __future__ import annotations

import json
import math
import shutil
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.portfolio_runner import (
    _build_strategy_timeframes,
    _discover_portfolio_symbols,
    _load_full_history,
    run_portfolio_backtest,
)
from config import AppConfig
from entry.htf_moonshot import build_htf_12h_snapshots


def _clone_config(base: AppConfig) -> AppConfig:
    return AppConfig(
        data=deepcopy(base.data),
        config_path=base.config_path,
        root_dir=base.root_dir,
    )


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    roll_max = equity.cummax()
    drawdown = (equity / roll_max) - 1.0
    return float(drawdown.min())


def _profit_factor(pnl: pd.Series) -> float:
    pos = float(pnl[pnl > 0].sum())
    neg = float(pnl[pnl < 0].sum())
    if neg == 0.0:
        return float("inf") if pos > 0 else 0.0
    return pos / abs(neg)


def _safe_pct(numerator: float, denominator: float) -> float:
    if denominator == 0.0:
        return 0.0
    return float(numerator) / float(denominator)


def _monthly_stats(daily: pd.DataFrame) -> dict:
    if daily.empty:
        return {
            "avg_monthly_pnl": 0.0,
            "median_monthly_pnl": 0.0,
            "months_gte_10k_count": 0,
            "months_gte_10k_ratio": 0.0,
            "months_count": 0,
        }

    working = daily.copy()
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working = working.dropna(subset=["date"])
    working["month"] = working["date"].dt.to_period("M")
    monthly = working.groupby("month", as_index=False)["realized_pnl"].sum()
    count = int(len(monthly))
    gte_10k = int((monthly["realized_pnl"] >= 10_000.0).sum())
    return {
        "avg_monthly_pnl": float(monthly["realized_pnl"].mean()) if count else 0.0,
        "median_monthly_pnl": float(monthly["realized_pnl"].median()) if count else 0.0,
        "months_gte_10k_count": gte_10k,
        "months_gte_10k_ratio": _safe_pct(float(gte_10k), float(count)),
        "months_count": count,
    }


def _top5_contribution_percent(trades: pd.DataFrame) -> float:
    if trades.empty:
        return 0.0
    pnl = pd.to_numeric(trades.get("pnl"), errors="coerce").fillna(0.0)
    total = float(pnl.sum())
    if total == 0.0:
        return 0.0
    top5 = float(pnl.sort_values(ascending=False).head(5).sum())
    return _safe_pct(top5, total)


def _trade_metrics(trades: pd.DataFrame, equity: pd.DataFrame, daily: pd.DataFrame) -> dict:
    def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
        if not isinstance(frame, pd.DataFrame) or column not in frame.columns:
            return pd.Series(dtype=float)
        return pd.to_numeric(frame[column], errors="coerce")

    pnl = _numeric_series(trades, "pnl").fillna(0.0)
    r_values = _numeric_series(trades, "pnl_R_initial").fillna(0.0)
    bars_held = _numeric_series(trades, "bars_held")
    bars_held = bars_held.replace([np.inf, -np.inf], np.nan).dropna()
    equity_series = _numeric_series(equity, "equity").dropna()

    recent_daily = daily.copy()
    if not recent_daily.empty:
        recent_daily["date"] = pd.to_datetime(recent_daily["date"], errors="coerce")
        recent_daily = recent_daily.loc[recent_daily["date"] >= pd.Timestamp("2025-01-01")]

    monthly = _monthly_stats(daily)

    return {
        "final_equity": float(equity_series.iloc[-1]) if not equity_series.empty else 0.0,
        "net_pnl": float(pnl.sum()),
        "trade_count": int(len(trades)),
        "profit_factor": float(_profit_factor(pnl)),
        "avg_R": float(r_values.mean()) if not r_values.empty else 0.0,
        "median_R": float(r_values.median()) if not r_values.empty else 0.0,
        "max_R": float(r_values.max()) if not r_values.empty else 0.0,
        "win_rate": float((pnl > 0).mean()) if not pnl.empty else 0.0,
        "max_drawdown": float(_max_drawdown(equity_series)),
        "avg_hold_bars": float(bars_held.mean()) if not bars_held.empty else 0.0,
        "median_hold_bars": float(bars_held.median()) if not bars_held.empty else 0.0,
        "avg_hold_hours": float((bars_held / 4.0).mean()) if not bars_held.empty else 0.0,
        "median_hold_hours": float((bars_held / 4.0).median()) if not bars_held.empty else 0.0,
        "median_daily_pnl": float(pd.to_numeric(daily.get("realized_pnl"), errors="coerce").median())
        if not daily.empty
        else 0.0,
        "recent_2025_plus_median_daily_pnl": float(
            pd.to_numeric(recent_daily.get("realized_pnl"), errors="coerce").median()
        )
        if not recent_daily.empty
        else 0.0,
        "avg_monthly_pnl": monthly["avg_monthly_pnl"],
        "median_monthly_pnl": monthly["median_monthly_pnl"],
        "months_gte_10k_count": monthly["months_gte_10k_count"],
        "months_gte_10k_ratio": monthly["months_gte_10k_ratio"],
        "top5_trades_contribution_pct": _top5_contribution_percent(trades),
    }


def _load_run_artifacts(output_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    trades_path = output_dir / "trades.csv"
    equity_path = output_dir / "equity.csv"
    daily_path = output_dir / "daily_summary.csv"
    signals_path = output_dir / "signals.csv"

    trades = (
        pd.read_csv(trades_path, on_bad_lines="skip", engine="python")
        if trades_path.exists()
        else pd.DataFrame()
    )
    if not trades.empty and "trade_id" not in trades.columns:
        trades = pd.DataFrame()
    elif not trades.empty:
        dedupe_columns = [
            column
            for column in [
                "entry_time",
                "exit_time",
                "symbol",
                "strategy_type",
                "side",
                "entry_price",
                "exit_price",
            ]
            if column in trades.columns
        ]
        if dedupe_columns:
            trades = trades.drop_duplicates(subset=dedupe_columns, keep="last").reset_index(drop=True)
        else:
            trades = trades.drop_duplicates(subset=["trade_id"], keep="last").reset_index(drop=True)

    equity = (
        pd.read_csv(equity_path, on_bad_lines="skip", engine="python")
        if equity_path.exists()
        else pd.DataFrame()
    )
    if not equity.empty and "timestamp" not in equity.columns:
        equity = pd.read_csv(
            equity_path,
            on_bad_lines="skip",
            engine="python",
            names=["timestamp", "equity"],
            header=None,
        )
    if not equity.empty and "timestamp" in equity.columns:
        equity = equity.drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)

    daily = (
        pd.read_csv(daily_path, on_bad_lines="skip", engine="python")
        if daily_path.exists()
        else pd.DataFrame()
    )
    if not daily.empty and "date" not in daily.columns:
        daily = pd.DataFrame()
    elif not daily.empty:
        daily = daily.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)

    signals = (
        pd.read_csv(signals_path, on_bad_lines="skip", engine="python")
        if signals_path.exists()
        else pd.DataFrame()
    )
    if not signals.empty and "selection_reason" not in signals.columns:
        signals = pd.DataFrame()
    elif not signals.empty:
        dedupe_columns = [
            column
            for column in ["timestamp", "symbol", "side", "strategy_type", "selection_reason"]
            if column in signals.columns
        ]
        if dedupe_columns:
            signals = signals.drop_duplicates(subset=dedupe_columns, keep="last").reset_index(drop=True)

    return trades, equity, daily, signals


def _configure_scenario(
    config: AppConfig,
    *,
    output_dir: Path,
    core_enabled: bool,
    swing_enabled: bool,
    htf_enabled: bool,
    convexity_enabled: bool,
    htf_strategy_allowed_sides: list[str] | None = None,
    htf_short_risk_multiplier: float | None = None,
    history_start_date: str | None = None,
    history_end_date: str | None = None,
    paper_portfolio_overrides: dict | None = None,
    strategy_overrides: dict | None = None,
) -> None:
    config.data.setdefault("app", {})["debug"] = False
    config.data.setdefault("backtest", {})["resume_enabled"] = True
    config.data["backtest"]["save_every_steps"] = int(
        config.data.setdefault("backtest", {}).get("save_every_steps", 250)
    )
    config.data["backtest"]["output_dir"] = str(output_dir.as_posix())
    config.data.setdefault("live_sim", {}).setdefault("paper_portfolio", {})
    config.data["live_sim"]["paper_portfolio"].setdefault("convexity", {})
    config.data["live_sim"]["paper_portfolio"]["convexity"]["enabled"] = bool(convexity_enabled)
    config.data["live_sim"]["paper_portfolio"].setdefault("strategy_allowed_sides", {})

    if core_enabled:
        config.data["live_sim"]["paper_portfolio"]["allowed_edge_types"] = ["impulse_breakout"]
    else:
        config.data["live_sim"]["paper_portfolio"]["allowed_edge_types"] = ["__no_core__"]

    config.data.setdefault("strategy", {}).setdefault("moonshots", {}).setdefault("swing", {})
    config.data["strategy"]["moonshots"]["swing"]["enabled"] = bool(swing_enabled)
    config.data.setdefault("strategy", {}).setdefault("htf_12h_moonshot", {})
    config.data["strategy"]["htf_12h_moonshot"]["enabled"] = bool(htf_enabled)
    config.data["strategy"]["htf_12h_moonshot"]["allow_pyramiding"] = False
    if htf_strategy_allowed_sides is not None:
        config.data["live_sim"]["paper_portfolio"]["strategy_allowed_sides"][
            "htf_12h_moonshot"
        ] = list(htf_strategy_allowed_sides)
    if htf_short_risk_multiplier is not None:
        config.data["strategy"]["htf_12h_moonshot"]["short_risk_multiplier"] = float(
            htf_short_risk_multiplier
        )
    if history_start_date is not None:
        config.data.setdefault("history", {})["start_date"] = str(history_start_date)
    if history_end_date is not None:
        config.data.setdefault("history", {})["end_date"] = str(history_end_date)
    if paper_portfolio_overrides:
        config.data.setdefault("live_sim", {}).setdefault("paper_portfolio", {}).update(
            deepcopy(paper_portfolio_overrides)
        )
    if strategy_overrides:
        strategy_section = config.data.setdefault("strategy", {})
        for key, value in deepcopy(strategy_overrides).items():
            if isinstance(value, dict) and isinstance(strategy_section.get(key), dict):
                strategy_section[key].update(value)
            else:
                strategy_section[key] = value


def _expected_completion_timestamp(config: AppConfig) -> pd.Timestamp:
    return pd.Timestamp(config.require("history", "end_date")) + pd.Timedelta(days=1)


def _scenario_artifacts_complete(output_dir: Path, config: AppConfig) -> bool:
    _, equity, _, _ = _load_run_artifacts(output_dir)
    if equity.empty or "timestamp" not in equity.columns:
        return False
    try:
        last_timestamp = pd.Timestamp(equity["timestamp"].iloc[-1])
    except Exception:
        return False
    return last_timestamp >= _expected_completion_timestamp(config)


def _progress_path(report_root: Path) -> Path:
    return report_root / "scenario_progress.json"


def _load_progress(report_root: Path) -> dict:
    path = _progress_path(report_root)
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as file_handle:
            return json.load(file_handle)
    except Exception:
        return {}


def _save_progress(report_root: Path, progress: dict) -> None:
    with _progress_path(report_root).open("w", encoding="utf-8") as file_handle:
        json.dump(progress, file_handle, indent=2, default=str)


def _run_scenario(
    name: str,
    base_config: AppConfig,
    root_output: Path,
    *,
    reset_output: bool = False,
    **flags,
) -> dict:
    output_dir = root_output / name
    if reset_output and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cfg = _clone_config(base_config)
    _configure_scenario(cfg, output_dir=output_dir, **flags)
    portfolio = run_portfolio_backtest(config=cfg)
    trades, equity, daily, signals = _load_run_artifacts(output_dir)
    metrics = _trade_metrics(trades, equity, daily)
    last_equity_ts = None
    if not equity.empty and "timestamp" in equity.columns:
        last_equity_ts = str(equity["timestamp"].iloc[-1])
    return {
        "name": name,
        "output_dir": str(output_dir),
        "backtest_completed": bool(getattr(portfolio, "backtest_completed", False)),
        "last_equity_timestamp": last_equity_ts,
        "expected_last_equity_timestamp": str(_expected_completion_timestamp(cfg)),
        "artifacts_complete": _scenario_artifacts_complete(output_dir, cfg),
        "metrics": metrics,
        "trades": trades,
        "equity": equity,
        "daily": daily,
        "signals": signals,
    }


def _run_or_resume_scenario(
    name: str,
    base_config: AppConfig,
    root_output: Path,
    progress: dict,
    *,
    reset_output: bool = False,
    **flags,
) -> dict:
    output_dir = root_output / name
    cfg = _clone_config(base_config)
    _configure_scenario(cfg, output_dir=output_dir, **flags)
    if not reset_output and _scenario_artifacts_complete(output_dir, cfg):
        trades, equity, daily, signals = _load_run_artifacts(output_dir)
        metrics = _trade_metrics(trades, equity, daily)
        last_equity_ts = None
        if not equity.empty and "timestamp" in equity.columns:
            last_equity_ts = str(equity["timestamp"].iloc[-1])
        result = {
            "name": name,
            "output_dir": str(output_dir),
            "backtest_completed": True,
            "last_equity_timestamp": last_equity_ts,
            "expected_last_equity_timestamp": str(_expected_completion_timestamp(cfg)),
            "artifacts_complete": True,
            "metrics": metrics,
            "trades": trades,
            "equity": equity,
            "daily": daily,
            "signals": signals,
            "resumed_from_artifacts": True,
        }
    else:
        result = _run_scenario(
            name,
            base_config,
            root_output,
            reset_output=reset_output,
            **flags,
        )
        result["resumed_from_artifacts"] = False

    progress[name] = {
        "completed": bool(result.get("artifacts_complete", False)),
        "last_equity_timestamp": result.get("last_equity_timestamp"),
        "expected_last_equity_timestamp": result.get("expected_last_equity_timestamp"),
        "resumed_from_artifacts": bool(result.get("resumed_from_artifacts", False)),
        "metrics": result.get("metrics", {}),
    }
    _save_progress(root_output, progress)
    return result


def _build_htf_funnel(base_config: AppConfig) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    config = _clone_config(base_config)
    config.data.setdefault("app", {})["debug"] = False
    symbols = _discover_portfolio_symbols(config)
    interval = config.require("binance", "default_interval")
    min_weekly_enabled = bool(
        config.get("strategy", "htf_12h_moonshot", "confirmation_timeframes", default=["1d", "1w"])
        and "1w" in [str(item).lower() for item in config.get("strategy", "htf_12h_moonshot", "confirmation_timeframes", default=["1d", "1w"])]
    )

    rows = []
    for symbol in symbols:
        df_1m, _ = _load_full_history(symbol, interval, config)
        df_15m, _, df_12h, df_1d, df_1w = _build_strategy_timeframes(df_1m, config=config)
        snapshot = build_htf_12h_snapshots(df_15m.index, df_12h, df_1d, df_1w, config=config)
        new_candles = snapshot.loc[snapshot["htf_12h_new_candle"] == True].copy()  # noqa: E712

        for side in ("long", "short"):
            side_df = pd.DataFrame(index=new_candles.index)
            side_df["timestamp"] = new_candles.index
            side_df["symbol"] = symbol
            side_df["side"] = side
            side_df["year"] = pd.DatetimeIndex(new_candles.index).year
            side_df["signal_family"] = new_candles[f"signal_family_{side}"].astype(str).replace("", "none")
            side_df["raw_12h_events"] = 1
            side_df["passed_12h_structure"] = new_candles[f"htf_pass_structure_{side}"].astype(bool)
            side_df["passed_1d_context"] = new_candles[f"htf_pass_1d_context_{side}"].astype(bool)
            side_df["passed_1w_context"] = new_candles[f"htf_pass_1w_context_{side}"].astype(bool)
            side_df["passed_stretch_filter"] = new_candles[f"htf_pass_stretch_{side}"].astype(bool)
            side_df["passed_score"] = new_candles[f"htf_pass_score_{side}"].astype(bool)
            side_df["passed_expansion"] = new_candles[f"htf_pass_expansion_{side}"].astype(bool)
            rows.append(side_df)

    funnel_rows = pd.concat(rows, ignore_index=True)
    sequential_pass = (
        funnel_rows["passed_12h_structure"]
        & funnel_rows["passed_1d_context"]
        & ((~min_weekly_enabled) | funnel_rows["passed_1w_context"])
        & funnel_rows["passed_stretch_filter"]
        & funnel_rows["passed_score"]
    )
    funnel_rows["passed_funnel_pre_open"] = sequential_pass
    funnel_rows["rejection_gate"] = np.select(
        [
            ~funnel_rows["passed_12h_structure"],
            funnel_rows["passed_12h_structure"] & ~funnel_rows["passed_1d_context"],
            funnel_rows["passed_12h_structure"] & funnel_rows["passed_1d_context"] & min_weekly_enabled & ~funnel_rows["passed_1w_context"],
            funnel_rows["passed_12h_structure"] & funnel_rows["passed_1d_context"] & ((~min_weekly_enabled) | funnel_rows["passed_1w_context"]) & ~funnel_rows["passed_stretch_filter"],
            funnel_rows["passed_12h_structure"] & funnel_rows["passed_1d_context"] & ((~min_weekly_enabled) | funnel_rows["passed_1w_context"]) & funnel_rows["passed_stretch_filter"] & ~funnel_rows["passed_score"],
        ],
        [
            "structure_gate",
            "context_1d_gate",
            "context_1w_gate",
            "stretch_gate",
            "score_gate",
        ],
        default="passed_pre_open",
    )

    totals = {
        "raw_12h_events": int(funnel_rows["raw_12h_events"].sum()),
        "passed_12h_structure": int(funnel_rows["passed_12h_structure"].sum()),
        "passed_1d_context": int(
            (funnel_rows["passed_12h_structure"] & funnel_rows["passed_1d_context"]).sum()
        ),
        "passed_1w_context": int(
            (
                funnel_rows["passed_12h_structure"]
                & funnel_rows["passed_1d_context"]
                & ((~min_weekly_enabled) | funnel_rows["passed_1w_context"])
            ).sum()
        ),
        "passed_stretch_filter": int(
            (
                funnel_rows["passed_12h_structure"]
                & funnel_rows["passed_1d_context"]
                & ((~min_weekly_enabled) | funnel_rows["passed_1w_context"])
                & funnel_rows["passed_stretch_filter"]
            ).sum()
        ),
        "passed_score": int(
            (
                funnel_rows["passed_12h_structure"]
                & funnel_rows["passed_1d_context"]
                & ((~min_weekly_enabled) | funnel_rows["passed_1w_context"])
                & funnel_rows["passed_stretch_filter"]
                & funnel_rows["passed_score"]
            ).sum()
        ),
    }
    return funnel_rows, pd.DataFrame([totals]), totals


def _summarize_rejections(signals: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return pd.DataFrame(columns=["symbol", "side", "year", "signal_family", "selection_reason", "count"])
    working = signals.copy()
    working = working.loc[working.get("strategy_type", "").astype(str) == "htf_12h_moonshot"].copy()
    if working.empty:
        return pd.DataFrame(columns=["symbol", "side", "year", "signal_family", "selection_reason", "count"])

    working["timestamp"] = pd.to_datetime(working["timestamp"], errors="coerce")
    working["year"] = working["timestamp"].dt.year
    if "htf_signal_family" in working.columns:
        working["signal_family"] = working["htf_signal_family"].fillna("").replace("", "unknown")
    else:
        working["signal_family"] = "unknown"
    working["selection_reason"] = working["selection_reason"].fillna("unknown")
    grouped = (
        working.groupby(
            ["symbol", "side", "signal_family", "year", "selection_reason"],
            dropna=False,
            as_index=False,
        )
        .size()
        .rename(columns={"size": "count"})
    )
    return grouped


def _htf_exit_audit(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"counts": {}, "noise_exits_count": 0}
    htf = trades.loc[trades.get("strategy_type", "").astype(str) == "htf_12h_moonshot"].copy()
    if htf.empty:
        return {"counts": {}, "noise_exits_count": 0}
    reasons = htf["exit_reason"].fillna("unknown").astype(str)
    counts = reasons.value_counts().to_dict()
    noise_patterns = ("trend weakness", "state exit", "slow grind exit", "time exit")
    noise_count = int(sum(int(counts.get(pattern, 0)) for pattern in noise_patterns))
    return {"counts": counts, "noise_exits_count": noise_count}


def _overlap_stats(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {
            "htf_trade_count": 0,
            "htf_overlap_count": 0,
            "htf_overlap_ratio": 0.0,
        }
    working = trades.copy()
    working["entry_time"] = pd.to_datetime(working["entry_time"], errors="coerce")
    working["exit_time"] = pd.to_datetime(working["exit_time"], errors="coerce")
    working = working.dropna(subset=["entry_time", "exit_time"])

    htf = working.loc[working["strategy_type"].astype(str) == "htf_12h_moonshot"].copy()
    other = working.loc[working["strategy_type"].astype(str) != "htf_12h_moonshot"].copy()
    if htf.empty:
        return {
            "htf_trade_count": 0,
            "htf_overlap_count": 0,
            "htf_overlap_ratio": 0.0,
        }

    overlap_count = 0
    for _, htf_trade in htf.iterrows():
        symbol_mask = other["symbol"].astype(str) == str(htf_trade["symbol"])
        candidates = other.loc[symbol_mask]
        if candidates.empty:
            continue
        overlaps = candidates.loc[
            (candidates["entry_time"] <= htf_trade["exit_time"])
            & (candidates["exit_time"] >= htf_trade["entry_time"])
        ]
        if not overlaps.empty:
            overlap_count += 1

    htf_count = int(len(htf))
    return {
        "htf_trade_count": htf_count,
        "htf_overlap_count": int(overlap_count),
        "htf_overlap_ratio": _safe_pct(float(overlap_count), float(htf_count)),
    }


def main():
    base = AppConfig.load()
    base_output = Path(base.require("backtest", "output_dir"))
    report_root = base_output / "htf_12h_validation_20260601"
    report_root.mkdir(parents=True, exist_ok=True)
    progress = _load_progress(report_root)

    funnel_rows, funnel_totals_df, funnel_totals = _build_htf_funnel(base)
    funnel_rows.to_csv(report_root / "htf_funnel_rows.csv", index=False)
    funnel_totals_df.to_csv(report_root / "htf_funnel_totals.csv", index=False)
    (
        funnel_rows.groupby(["symbol", "side", "signal_family", "year", "rejection_gate"], as_index=False)
        .size()
        .rename(columns={"size": "count"})
        .to_csv(report_root / "htf_gate_breakdown.csv", index=False)
    )

    scenarios = {}
    scenarios["htf_only"] = _run_or_resume_scenario(
        "scenario_htf_only",
        base,
        report_root,
        progress,
        core_enabled=False,
        swing_enabled=False,
        htf_enabled=True,
        convexity_enabled=False,
    )
    scenarios["core_only"] = _run_or_resume_scenario(
        "scenario_core_only",
        base,
        report_root,
        progress,
        core_enabled=True,
        swing_enabled=False,
        htf_enabled=False,
        convexity_enabled=True,
    )
    scenarios["core_plus_htf"] = _run_or_resume_scenario(
        "scenario_core_plus_htf",
        base,
        report_root,
        progress,
        core_enabled=True,
        swing_enabled=False,
        htf_enabled=True,
        convexity_enabled=True,
    )
    scenarios["core_plus_swing"] = _run_or_resume_scenario(
        "scenario_core_plus_swing",
        base,
        report_root,
        progress,
        core_enabled=True,
        swing_enabled=True,
        htf_enabled=False,
        convexity_enabled=True,
    )
    scenarios["core_plus_swing_plus_htf"] = _run_or_resume_scenario(
        "scenario_core_plus_swing_plus_htf",
        base,
        report_root,
        progress,
        core_enabled=True,
        swing_enabled=True,
        htf_enabled=True,
        convexity_enabled=True,
    )

    combined_signals = scenarios["core_plus_swing_plus_htf"]["signals"]
    rejection_summary = _summarize_rejections(combined_signals)
    rejection_summary.to_csv(report_root / "htf_rejection_breakdown.csv", index=False)

    combined_metrics = {
        key: value["metrics"]
        for key, value in scenarios.items()
    }

    htf_only_trades = scenarios["htf_only"]["trades"]
    htf_only_subset = htf_only_trades.loc[
        htf_only_trades.get("strategy_type", "").astype(str) == "htf_12h_moonshot"
    ].copy()
    htf_only_exit_counts = (
        htf_only_subset["exit_reason"].fillna("unknown").astype(str).value_counts().to_dict()
        if not htf_only_subset.empty
        else {}
    )

    combined_trades = scenarios["core_plus_swing_plus_htf"]["trades"]
    combined_signal_htf = combined_signals.loc[
        combined_signals.get("strategy_type", "").astype(str) == "htf_12h_moonshot"
    ].copy()
    duplicate_rejections = int(
        (combined_signal_htf.get("selection_reason", "").astype(str) == "same_symbol_same_side_cap").sum()
    )
    risk_rejections = int(
        combined_signal_htf.get("selection_reason", "").astype(str).isin(
            ["risk_cap", "strategy_risk_cap"]
        ).sum()
    )
    opened_htf_trades = int(
        (combined_signal_htf.get("selection_reason", "").astype(str) == "opened").sum()
    )

    overlap = _overlap_stats(combined_trades)
    htf_exit_behavior = _htf_exit_audit(combined_trades)

    htf_pnl_in_combined = float(
        pd.to_numeric(
            combined_trades.loc[
                combined_trades.get("strategy_type", "").astype(str) == "htf_12h_moonshot",
                "pnl",
            ],
            errors="coerce",
        ).fillna(0.0).sum()
    )
    incremental_vs_core_swing = (
        combined_metrics["core_plus_swing_plus_htf"]["final_equity"]
        - combined_metrics["core_plus_swing"]["final_equity"]
    )

    summary = {
        "report_root": str(report_root),
        "funnel_totals": {
            **funnel_totals,
            "rejected_by_duplicate_exposure": duplicate_rejections,
            "rejected_by_risk_cap": risk_rejections,
            "opened_htf_trades": opened_htf_trades,
        },
        "scenario_metrics": combined_metrics,
        "htf_only": {
            "metrics": combined_metrics["htf_only"],
            "exit_reasons": htf_only_exit_counts,
            "top5_trades_contribution_pct": _top5_contribution_percent(htf_only_subset),
        },
        "comparison": {
            "htf_incremental_pnl_direct_in_combined": htf_pnl_in_combined,
            "incremental_equity_vs_core_plus_swing": float(incremental_vs_core_swing),
            "overlap": overlap,
        },
        "htf_exit_behavior_in_combined": htf_exit_behavior,
    }

    with (report_root / "summary.json").open("w", encoding="utf-8") as file_handle:
        json.dump(summary, file_handle, indent=2, default=str)

    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
