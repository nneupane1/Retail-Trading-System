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


def _resolve_equity_return_fractions(trades_df, initial_equity, fallback_risk_per_trade):
    if trades_df.empty:
        return np.array([], dtype=float)

    resolved = np.full(len(trades_df), np.nan, dtype=float)

    if "equity_return_fraction" in trades_df.columns:
        explicit = pd.to_numeric(
            trades_df["equity_return_fraction"],
            errors="coerce",
        ).to_numpy(dtype=float)
        valid = np.isfinite(explicit)
        resolved[valid] = explicit[valid]

    if {"pnl", "equity_at_entry"}.issubset(trades_df.columns):
        pnls = pd.to_numeric(trades_df["pnl"], errors="coerce").to_numpy(dtype=float)
        equity_at_entry = pd.to_numeric(
            trades_df["equity_at_entry"],
            errors="coerce",
        ).to_numpy(dtype=float)
        valid = (~np.isfinite(resolved)) & np.isfinite(pnls) & np.isfinite(equity_at_entry) & (equity_at_entry > 0)
        resolved[valid] = pnls[valid] / equity_at_entry[valid]

    risks = _resolve_risk_fractions(
        trades_df,
        initial_equity=initial_equity,
        fallback_risk_per_trade=fallback_risk_per_trade,
    )
    r_values = pd.to_numeric(trades_df["pnl_R_initial"], errors="coerce").to_numpy(dtype=float)
    valid = (~np.isfinite(resolved)) & np.isfinite(r_values)
    resolved[valid] = risks[valid] * r_values[valid]

    resolved[~np.isfinite(resolved)] = 0.0
    return resolved.astype(float)


def _resolve_event_times(trades_df):
    for column in ["exit_time", "entry_time"]:
        if column in trades_df.columns:
            timestamps = pd.to_datetime(trades_df[column], errors="coerce")
            if not timestamps.isna().all():
                if timestamps.isna().any():
                    fallback = pd.date_range(
                        "2000-01-01",
                        periods=len(trades_df),
                        freq="15min",
                    )
                    timestamps = timestamps.fillna(pd.Series(fallback, index=timestamps.index))
                return pd.Series(timestamps).reset_index(drop=True)

    return pd.Series(
        pd.date_range("2000-01-01", periods=len(trades_df), freq="15min")
    )


def _build_portfolio_channel_payloads(trades_df, fallback_risk_per_trade):
    payloads = []
    if "portfolio_channel" not in trades_df.columns:
        return payloads

    for channel_name, group in trades_df.groupby("portfolio_channel", dropna=False):
        ordered = _ordered_trades_for_path_analysis(group)
        if ordered.empty:
            continue

        if "channel_initial_equity" in ordered.columns:
            channel_initial_equity = float(
                pd.to_numeric(
                    ordered["channel_initial_equity"],
                    errors="coerce",
                ).dropna().iloc[0]
            )
        else:
            channel_initial_equity = float(
                pd.to_numeric(
                    ordered.get("equity_at_entry"),
                    errors="coerce",
                ).dropna().iloc[0]
            )

        payloads.append(
            {
                "channel": channel_name,
                "initial_equity": channel_initial_equity,
                "event_times": _resolve_event_times(ordered).to_numpy(),
                "return_fractions": _resolve_equity_return_fractions(
                    ordered,
                    initial_equity=channel_initial_equity,
                    fallback_risk_per_trade=fallback_risk_per_trade,
                ),
            }
        )

    return payloads


def _simulate_portfolio_from_channel_returns(
    channel_payloads,
    sampled_returns_by_channel,
    duration_years,
):
    frames = []
    channel_columns = []
    total_initial_equity = 0.0

    for payload in channel_payloads:
        channel_name = payload["channel"]
        channel_column = f"equity__{channel_name}"
        channel_columns.append(channel_column)
        total_initial_equity += float(payload["initial_equity"])
        returns = np.asarray(sampled_returns_by_channel[channel_name], dtype=float)
        equity = float(payload["initial_equity"])

        if len(returns) == 0:
            continue

        channel_equities = []
        for trade_return in returns:
            equity *= (1.0 + float(trade_return))
            channel_equities.append(equity)

        frames.append(
            pd.DataFrame(
                {
                    "timestamp": pd.to_datetime(payload["event_times"]),
                    channel_column: channel_equities,
                }
            )
        )

    if not frames:
        final_equity = total_initial_equity
        peak_equity = total_initial_equity
        max_drawdown_pct = 0.0
        cagr_pct = 0.0
        if duration_years > 0:
            cagr_pct = ((final_equity / total_initial_equity) ** (1.0 / duration_years) - 1.0) * 100
        return {
            "final_equity": final_equity,
            "peak_equity": peak_equity,
            "max_drawdown_pct": max_drawdown_pct,
            "cagr_pct": cagr_pct,
        }

    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on="timestamp", how="outer")

    merged = merged.sort_values("timestamp").reset_index(drop=True)
    for payload in channel_payloads:
        channel_column = f"equity__{payload['channel']}"
        if channel_column not in merged.columns:
            merged[channel_column] = float(payload["initial_equity"])
        merged[channel_column] = (
            merged[channel_column]
            .ffill()
            .fillna(float(payload["initial_equity"]))
        )

    portfolio_equity = merged[channel_columns].sum(axis=1)
    final_equity = float(portfolio_equity.iloc[-1])
    peak_equity = float(portfolio_equity.cummax().max())
    drawdown_pct = ((portfolio_equity - portfolio_equity.cummax()) / portfolio_equity.cummax()) * 100
    max_drawdown_pct = float(drawdown_pct.min()) if not drawdown_pct.empty else 0.0
    cagr_pct = ((final_equity / total_initial_equity) ** (1.0 / duration_years) - 1.0) * 100

    return {
        "final_equity": final_equity,
        "peak_equity": peak_equity,
        "max_drawdown_pct": max_drawdown_pct,
        "cagr_pct": cagr_pct,
    }


def build_trade_object_audit(trades_df, initial_equity, fallback_risk_per_trade):
    ordered = _ordered_trades_for_path_analysis(trades_df)
    risk_fractions = _resolve_risk_fractions(
        ordered,
        initial_equity=initial_equity,
        fallback_risk_per_trade=fallback_risk_per_trade,
    )
    equity_returns = _resolve_equity_return_fractions(
        ordered,
        initial_equity=initial_equity,
        fallback_risk_per_trade=fallback_risk_per_trade,
    )

    audit = ordered.copy()
    audit["resolved_effective_risk_fraction"] = risk_fractions
    audit["resolved_equity_return_fraction"] = equity_returns
    audit["is_pyramided"] = (
        pd.to_numeric(audit.get("pyramid_level"), errors="coerce").fillna(0).astype(float) > 0
        if "pyramid_level" in audit.columns
        else False
    )

    preferred_columns = [
        "trade_id",
        "portfolio_channel",
        "channel_initial_equity",
        "side",
        "signal_family",
        "entry_role",
        "entry_time",
        "exit_time",
        "score",
        "pressure_score",
        "active_stop_price",
        "trail_state",
        "trail_anchor_column",
        "trail_anchor_price",
        "trail_open_r_multiple",
        "trail_momentum_score",
        "trail_decay_score",
        "pyramid_level",
        "exit_reason",
        "pnl",
        "pnl_R_initial",
        "initial_risk_amount",
        "equity_at_entry",
        "entry_risk_multiplier",
        "effective_risk_fraction",
        "equity_return_fraction",
        "resolved_effective_risk_fraction",
        "resolved_equity_return_fraction",
        "is_pyramided",
    ]
    available_columns = [column for column in preferred_columns if column in audit.columns]
    return audit[available_columns]


def _summarize_group_contribution(audit_df, column):
    if audit_df.empty or column not in audit_df.columns:
        return []

    rows = []
    for bucket, group in audit_df.groupby(column, dropna=False):
        trade_count = int(len(group))
        gross_profit = float(group.loc[group["pnl"] > 0, "pnl"].sum())
        gross_loss = float(abs(group.loc[group["pnl"] < 0, "pnl"].sum()))
        if gross_loss == 0:
            profit_factor = float("inf") if gross_profit > 0 else 0.0
        else:
            profit_factor = gross_profit / gross_loss

        rows.append(
            {
                column: bucket,
                "trade_count": trade_count,
                "win_rate_pct": float((group["pnl"] > 0).mean() * 100),
                "net_pnl": float(group["pnl"].sum()),
                "gross_profit": gross_profit,
                "gross_loss": gross_loss,
                "profit_factor": float(profit_factor),
                "avg_pnl": float(group["pnl"].mean()),
                "median_pnl": float(group["pnl"].median()),
                "avg_pnl_R_initial": float(group["pnl_R_initial"].mean()) if "pnl_R_initial" in group.columns else 0.0,
                "avg_entry_risk_multiplier": float(pd.to_numeric(group.get("entry_risk_multiplier"), errors="coerce").fillna(1.0).mean())
                if "entry_risk_multiplier" in group.columns
                else 1.0,
                "avg_effective_risk_fraction": float(group["resolved_effective_risk_fraction"].mean()),
                "avg_equity_return_fraction": float(group["resolved_equity_return_fraction"].mean()),
                "total_equity_return_fraction": float(group["resolved_equity_return_fraction"].sum()),
                "total_initial_risk_amount": float(group["initial_risk_amount"].fillna(0).sum())
                if "initial_risk_amount" in group.columns
                else 0.0,
                "pyramided_trade_pct": float(group["is_pyramided"].mean() * 100),
            }
        )

    return rows


def summarize_dimension_contribution(
    trades_df,
    column,
    initial_equity,
    fallback_risk_per_trade,
):
    if trades_df.empty:
        return []

    audit = build_trade_object_audit(
        trades_df,
        initial_equity=initial_equity,
        fallback_risk_per_trade=fallback_risk_per_trade,
    )
    return _summarize_group_contribution(audit, column)


def summarize_side_contribution(trades_df, initial_equity, fallback_risk_per_trade):
    return summarize_dimension_contribution(
        trades_df,
        column="side",
        initial_equity=initial_equity,
        fallback_risk_per_trade=fallback_risk_per_trade,
    )


def simulate_compounded_equity(
    r_multiples,
    initial_equity,
    risk_per_trade=None,
    duration_years=1.0,
    *,
    return_fractions=None,
):
    equity = float(initial_equity)
    peak_equity = equity
    max_drawdown_pct = 0.0

    if return_fractions is not None:
        compounded_returns = np.asarray(return_fractions, dtype=float)
    else:
        if risk_per_trade is None:
            raise ValueError("risk_per_trade is required when return_fractions is not provided")
        if np.isscalar(risk_per_trade):
            risk_schedule = np.full(len(r_multiples), float(risk_per_trade), dtype=float)
        else:
            risk_schedule = np.asarray(risk_per_trade, dtype=float)
            if len(risk_schedule) != len(r_multiples):
                raise ValueError("risk_per_trade schedule length must match r_multiples length")
        compounded_returns = np.asarray(r_multiples, dtype=float) * risk_schedule

    for trade_return in compounded_returns:
        equity *= (1.0 + float(trade_return))
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
    initial_equity = float(samples_df["initial_equity"].iloc[0])
    return {
        "method": method,
        "iterations": int(len(samples_df)),
        "median_final_equity": float(samples_df["final_equity"].median()),
        "p05_final_equity": float(samples_df["final_equity"].quantile(0.05)),
        "p95_final_equity": float(samples_df["final_equity"].quantile(0.95)),
        "worst_final_equity": float(samples_df["final_equity"].min()),
        "best_final_equity": float(samples_df["final_equity"].max()),
        "median_peak_equity": float(samples_df["peak_equity"].median()),
        "median_cagr_pct": float(samples_df["cagr_pct"].median()),
        "p05_cagr_pct": float(samples_df["cagr_pct"].quantile(0.05)),
        "p95_cagr_pct": float(samples_df["cagr_pct"].quantile(0.95)),
        "median_max_drawdown_pct": float(samples_df["max_drawdown_pct"].median()),
        "p05_max_drawdown_pct": float(samples_df["max_drawdown_pct"].quantile(0.05)),
        "p95_max_drawdown_pct": float(samples_df["max_drawdown_pct"].quantile(0.95)),
        "worst_max_drawdown_pct": float(samples_df["max_drawdown_pct"].min()),
        "profitable_pct": float((samples_df["final_equity"] > samples_df["initial_equity"]).mean() * 100),
        "double_equity_pct": float((samples_df["final_equity"] >= (initial_equity * 2.0)).mean() * 100),
        "triple_equity_pct": float((samples_df["final_equity"] >= (initial_equity * 3.0)).mean() * 100),
        "half_equity_or_worse_pct": float((samples_df["final_equity"] <= (initial_equity * 0.5)).mean() * 100),
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
    config_initial_equity = float(config.require("account", "initial_equity"))
    risk_per_trade = float(config.require("account", "risk_per_trade"))
    duration_years = _trade_duration_years(trades_df)
    rng = np.random.default_rng(seed)

    output_dir = _build_output_dir(config, analysis_name)

    concentration = summarize_trade_concentration(trades_df)
    portfolio_channel_contribution = summarize_dimension_contribution(
        trades_df,
        column="portfolio_channel",
        initial_equity=config_initial_equity,
        fallback_risk_per_trade=risk_per_trade,
    )
    side_contribution = summarize_side_contribution(
        trades_df,
        initial_equity=config_initial_equity,
        fallback_risk_per_trade=risk_per_trade,
    )
    entry_role_contribution = summarize_dimension_contribution(
        trades_df,
        column="entry_role",
        initial_equity=config_initial_equity,
        fallback_risk_per_trade=risk_per_trade,
    )
    signal_family_contribution = summarize_dimension_contribution(
        trades_df,
        column="signal_family",
        initial_equity=config_initial_equity,
        fallback_risk_per_trade=risk_per_trade,
    )
    top_trades = ordered_trades.nlargest(min(20, len(ordered_trades)), "pnl").copy()

    channel_payloads = _build_portfolio_channel_payloads(
        ordered_trades,
        fallback_risk_per_trade=risk_per_trade,
    )
    portfolio_mode = len(channel_payloads) >= 2
    if portfolio_mode:
        initial_equity = float(
            sum(payload["initial_equity"] for payload in channel_payloads)
        )
        trade_audit = build_trade_object_audit(
            ordered_trades,
            initial_equity=config_initial_equity,
            fallback_risk_per_trade=risk_per_trade,
        )
        actual_returns_by_channel = {
            payload["channel"]: payload["return_fractions"]
            for payload in channel_payloads
        }
    else:
        initial_equity = config_initial_equity
        trade_audit = build_trade_object_audit(
            ordered_trades,
            initial_equity=initial_equity,
            fallback_risk_per_trade=risk_per_trade,
        )
        equity_return_fractions = trade_audit["resolved_equity_return_fraction"].astype(float).to_numpy()

    sample_sets = []

    if portfolio_mode:
        actual_result = _simulate_portfolio_from_channel_returns(
            channel_payloads=channel_payloads,
            sampled_returns_by_channel=actual_returns_by_channel,
            duration_years=duration_years,
        )
    else:
        actual_result = simulate_compounded_equity(
            r_multiples=[],
            initial_equity=initial_equity,
            return_fractions=equity_return_fractions,
            duration_years=duration_years,
        )
    actual_result.update({
        "method": "actual",
        "iteration": 0,
        "initial_equity": initial_equity,
    })
    sample_sets.append(actual_result)

    random_methods = {
        "shuffle": lambda size: rng.permutation(size),
        "bootstrap": lambda size: rng.choice(size, size=size, replace=True),
    }

    for method, generator in random_methods.items():
        for iteration in range(1, iterations + 1):
            if portfolio_mode:
                sampled_returns_by_channel = {}
                for payload in channel_payloads:
                    channel_returns = payload["return_fractions"]
                    sample_index = generator(len(channel_returns))
                    sampled_returns_by_channel[payload["channel"]] = channel_returns[sample_index]

                result = _simulate_portfolio_from_channel_returns(
                    channel_payloads=channel_payloads,
                    sampled_returns_by_channel=sampled_returns_by_channel,
                    duration_years=duration_years,
                )
            else:
                sample_index = generator(len(equity_return_fractions))
                sampled_returns = equity_return_fractions[sample_index]
                result = simulate_compounded_equity(
                    r_multiples=[],
                    initial_equity=initial_equity,
                    return_fractions=sampled_returns,
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

    side_contribution_path = output_dir / "side_contribution_summary.csv"
    if side_contribution:
        with side_contribution_path.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=list(side_contribution[0].keys()))
            writer.writeheader()
            writer.writerows(side_contribution)
    else:
        side_contribution_path.touch()

    channel_contribution_path = output_dir / "channel_contribution_summary.csv"
    if portfolio_channel_contribution:
        with channel_contribution_path.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(
                file_handle,
                fieldnames=list(portfolio_channel_contribution[0].keys()),
            )
            writer.writeheader()
            writer.writerows(portfolio_channel_contribution)
    else:
        channel_contribution_path.touch()

    role_contribution_path = output_dir / "entry_role_contribution_summary.csv"
    if entry_role_contribution:
        with role_contribution_path.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(
                file_handle,
                fieldnames=list(entry_role_contribution[0].keys()),
            )
            writer.writeheader()
            writer.writerows(entry_role_contribution)
    else:
        role_contribution_path.touch()

    signal_family_contribution_path = output_dir / "signal_family_contribution_summary.csv"
    if signal_family_contribution:
        with signal_family_contribution_path.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(
                file_handle,
                fieldnames=list(signal_family_contribution[0].keys()),
            )
            writer.writeheader()
            writer.writerows(signal_family_contribution)
    else:
        signal_family_contribution_path.touch()

    trade_audit_path = output_dir / "trade_object_audit.csv"
    trade_audit.to_csv(trade_audit_path, index=False)

    top_trades_path = output_dir / "top_20_trades.csv"
    top_trades.to_csv(top_trades_path, index=False)

    return {
        "analysis_name": analysis_name,
        "trades_path": str(trades_path),
        "summary_path": str(summary_path),
        "samples_path": str(samples_path),
        "concentration_path": str(concentration_path),
        "side_contribution_path": str(side_contribution_path),
        "trade_audit_path": str(trade_audit_path),
        "top_trades_path": str(top_trades_path),
        "summary_rows": summary_rows,
        "concentration": concentration,
        "side_contribution": side_contribution,
        "portfolio_channel_contribution": portfolio_channel_contribution,
        "entry_role_contribution": entry_role_contribution,
        "signal_family_contribution": signal_family_contribution,
        "channel_contribution_path": str(channel_contribution_path),
        "role_contribution_path": str(role_contribution_path),
        "signal_family_contribution_path": str(signal_family_contribution_path),
        "portfolio_mode": portfolio_mode,
    }
