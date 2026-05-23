"""Robustness analysis helpers for validated trade logs."""

import csv
from pathlib import Path

import numpy as np
import pandas as pd

from config import AppConfig


def _trade_duration_years(trades_df):
    if trades_df.empty or "entry_time" not in trades_df.columns or "exit_time" not in trades_df.columns:
        return 1.0

    entry_times = pd.to_datetime(trades_df["entry_time"])
    exit_times = pd.to_datetime(trades_df["exit_time"])
    duration_days = (exit_times.max() - entry_times.min()).total_seconds() / 86400
    return max(duration_days / 365.25, 1 / 365.25)


def _ordered_trades_for_path_analysis(trades_df):
    ordered = trades_df.copy()
    sort_columns = []
    for column in ["entry_time", "exit_time"]:
        if column in ordered.columns:
            ordered[column] = pd.to_datetime(ordered[column], errors="coerce")
            sort_columns.append(column)

    if sort_columns:
        ordered = ordered.sort_values(sort_columns, kind="stable")

    return ordered.reset_index(drop=True)


def _resolve_risk_fractions(trades_df, initial_equity, fallback_risk_per_trade):
    if trades_df.empty:
        return np.array([], dtype=float)

    if "effective_risk_fraction" in trades_df.columns:
        explicit = pd.to_numeric(
            trades_df["effective_risk_fraction"],
            errors="coerce",
        ).to_numpy(dtype=float)
        if np.isfinite(explicit).all() and (explicit >= 0).all():
            return explicit

    risks = []
    equity = float(initial_equity)
    initial_risk_amounts = (
        pd.to_numeric(trades_df.get("initial_risk_amount"), errors="coerce")
        if "initial_risk_amount" in trades_df.columns
        else pd.Series([np.nan] * len(trades_df))
    )
    pnls = (
        pd.to_numeric(trades_df.get("pnl"), errors="coerce")
        if "pnl" in trades_df.columns
        else pd.Series([np.nan] * len(trades_df))
    )
    r_values = pd.to_numeric(trades_df["pnl_R_initial"], errors="coerce")

    for idx in range(len(trades_df)):
        if equity <= 0:
            risk_fraction = 0.0
        else:
            initial_risk_amount = initial_risk_amounts.iloc[idx]
            if pd.notna(initial_risk_amount) and initial_risk_amount >= 0:
                risk_fraction = float(initial_risk_amount) / equity
            else:
                risk_fraction = float(fallback_risk_per_trade)

        risks.append(risk_fraction)

        pnl_value = pnls.iloc[idx]
        if pd.notna(pnl_value):
            equity += float(pnl_value)
        else:
            equity *= (1.0 + (risk_fraction * float(r_values.iloc[idx])))

    return np.asarray(risks, dtype=float)


def simulate_compounded_equity(r_multiples, initial_equity, risk_per_trade, duration_years=1.0):
    equity = float(initial_equity)
    peak_equity = equity
    max_drawdown_pct = 0.0

    if np.isscalar(risk_per_trade):
        risk_schedule = np.full(len(r_multiples), float(risk_per_trade), dtype=float)
    else:
        risk_schedule = np.asarray(risk_per_trade, dtype=float)
        if len(risk_schedule) != len(r_multiples):
            raise ValueError("risk_per_trade schedule length must match r_multiples length")

    for r_multiple, risk_fraction in zip(r_multiples, risk_schedule):
        equity *= (1.0 + (float(risk_fraction) * float(r_multiple)))
        peak_equity = max(peak_equity, equity)
        drawdown_pct = ((equity - peak_equity) / peak_equity) * 100
        max_drawdown_pct = min(max_drawdown_pct, drawdown_pct)

    cagr_pct = ((equity / initial_equity) ** (1.0 / duration_years) - 1.0) * 100
    return {
        "final_equity": equity,
        "peak_equity": peak_equity,
        "max_drawdown_pct": max_drawdown_pct,
        "cagr_pct": cagr_pct,
    }


def summarize_trade_concentration(trades_df):
    if trades_df.empty:
        return {
            "trade_count": 0,
            "top10_net_pct": 0.0,
            "top20_net_pct": 0.0,
            "top10_gross_pct": 0.0,
            "top20_gross_pct": 0.0,
        }

    gross_profit = float(trades_df.loc[trades_df["pnl"] > 0, "pnl"].sum())
    net_profit = float(trades_df["pnl"].sum())

    def _share(top_n, denominator):
        top_sum = float(trades_df.nlargest(min(top_n, len(trades_df)), "pnl")["pnl"].sum())
        if denominator == 0:
            return 0.0
        return (top_sum / denominator) * 100

    return {
        "trade_count": int(len(trades_df)),
        "top10_net_pct": _share(10, net_profit),
        "top20_net_pct": _share(20, net_profit),
        "top10_gross_pct": _share(10, gross_profit),
        "top20_gross_pct": _share(20, gross_profit),
    }


def _samples_summary(samples_df, method, target_equity):
    return {
        "method": method,
        "iterations": int(len(samples_df)),
        "median_final_equity": float(samples_df["final_equity"].median()),
        "p05_final_equity": float(samples_df["final_equity"].quantile(0.05)),
        "p95_final_equity": float(samples_df["final_equity"].quantile(0.95)),
        "worst_final_equity": float(samples_df["final_equity"].min()),
        "best_final_equity": float(samples_df["final_equity"].max()),
        "median_cagr_pct": float(samples_df["cagr_pct"].median()),
        "p05_cagr_pct": float(samples_df["cagr_pct"].quantile(0.05)),
        "p95_cagr_pct": float(samples_df["cagr_pct"].quantile(0.95)),
        "median_max_drawdown_pct": float(samples_df["max_drawdown_pct"].median()),
        "worst_max_drawdown_pct": float(samples_df["max_drawdown_pct"].min()),
        "profitable_pct": float((samples_df["final_equity"] > samples_df["initial_equity"]).mean() * 100),
        "end_above_target_pct": float((samples_df["final_equity"] >= target_equity).mean() * 100),
        "peak_above_target_pct": float((samples_df["peak_equity"] >= target_equity).mean() * 100),
    }


def _build_output_dir(config, analysis_name):
    root_output_dir = Path(config.path("backtest", "output_dir"))
    output_dir = root_output_dir / "robustness" / analysis_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def run_monte_carlo_analysis(
    trades_path,
    config_path=None,
    analysis_name="baseline_v3_compound_strong",
    iterations=5000,
    seed=42,
    target_equity=100000.0,
):
    config = AppConfig.load(config_path=config_path)
    trades_path = Path(trades_path)
    trades_df = pd.read_csv(trades_path)
    if trades_df.empty:
        raise ValueError(f"No trades found at {trades_path}")

    ordered_trades = _ordered_trades_for_path_analysis(trades_df)
    r_multiples = ordered_trades["pnl_R_initial"].astype(float).to_numpy()
    initial_equity = float(config.require("account", "initial_equity"))
    risk_per_trade = float(config.require("account", "risk_per_trade"))
    risk_fractions = _resolve_risk_fractions(
        ordered_trades,
        initial_equity=initial_equity,
        fallback_risk_per_trade=risk_per_trade,
    )
    duration_years = _trade_duration_years(trades_df)
    rng = np.random.default_rng(seed)

    output_dir = _build_output_dir(config, analysis_name)

    concentration = summarize_trade_concentration(trades_df)
    top_trades = trades_df.nlargest(min(20, len(trades_df)), "pnl").copy()

    sample_sets = []

    actual_result = simulate_compounded_equity(
        r_multiples=r_multiples,
        initial_equity=initial_equity,
        risk_per_trade=risk_fractions,
        duration_years=duration_years,
    )
    actual_result.update({
        "method": "actual",
        "iteration": 0,
        "initial_equity": initial_equity,
    })
    sample_sets.append(actual_result)

    random_methods = {
        "shuffle": lambda values: rng.permutation(len(values)),
        "bootstrap": lambda values: rng.choice(len(values), size=len(values), replace=True),
    }

    for method, generator in random_methods.items():
        for iteration in range(1, iterations + 1):
            sample_index = generator(r_multiples)
            sampled_r = r_multiples[sample_index]
            sampled_risk = risk_fractions[sample_index]
            result = simulate_compounded_equity(
                r_multiples=sampled_r,
                initial_equity=initial_equity,
                risk_per_trade=sampled_risk,
                duration_years=duration_years,
            )
            result.update({
                "method": method,
                "iteration": iteration,
                "initial_equity": initial_equity,
            })
            sample_sets.append(result)

    samples_df = pd.DataFrame(sample_sets)

    summary_rows = [
        _samples_summary(samples_df[samples_df["method"] == method], method, target_equity)
        for method in ["actual", "shuffle", "bootstrap"]
    ]

    samples_path = output_dir / "monte_carlo_samples.csv"
    samples_df.to_csv(samples_path, index=False)

    summary_path = output_dir / "monte_carlo_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    concentration_path = output_dir / "trade_concentration_summary.csv"
    with concentration_path.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=list(concentration.keys()))
        writer.writeheader()
        writer.writerow(concentration)

    top_trades_path = output_dir / "top_20_trades.csv"
    top_trades.to_csv(top_trades_path, index=False)

    return {
        "analysis_name": analysis_name,
        "trades_path": str(trades_path),
        "summary_path": str(summary_path),
        "samples_path": str(samples_path),
        "concentration_path": str(concentration_path),
        "top_trades_path": str(top_trades_path),
        "summary_rows": summary_rows,
        "concentration": concentration,
    }
