"""Walk-forward validation and trade-distribution analysis helpers."""

from copy import deepcopy
import csv
import json
from pathlib import Path

import pandas as pd

from backtest.engine import BacktestEngine
from backtest.equity_logger import EquityLogger
from backtest.logger import TradeLogger
from common.debug import configure_debug
from config import AppConfig
from data.downloader import load_from_csv
from data.resampler import TimeframeBuilder
from features.feature_pipeline import compute_features
from simulation.simulator import Simulator
from simulation.trade import TRADE_LOG_FIELDS


def _parse_storage_timestamp(value):
    return pd.Timestamp(str(value).replace("T", " ").replace(".", ":"))


def _resolve_base_history_file(base_folder, symbol, base_label, start_date, end_date):
    exact_path = base_folder / f"{symbol}_{base_label}_{start_date}_to_{end_date}.csv"
    if exact_path.exists():
        return exact_path

    requested_start = pd.Timestamp(start_date)
    requested_end = pd.Timestamp(end_date)
    candidates = []
    for candidate in Path(base_folder).glob(f"{symbol}_{base_label}_*.csv"):
        if candidate.name.endswith("_live_runtime.csv"):
            continue

        stem = candidate.stem
        prefix = f"{symbol}_{base_label}_"
        if not stem.startswith(prefix) or "_to_" not in stem:
            continue

        remainder = stem[len(prefix):]
        start_text, end_text = remainder.split("_to_", 1)
        try:
            candidate_start = _parse_storage_timestamp(start_text)
            candidate_end = _parse_storage_timestamp(end_text)
        except Exception:
            continue

        if candidate_start <= requested_start:
            candidates.append(
                (
                    candidate_end >= requested_end,
                    candidate_end,
                    -candidate_start.value,
                    candidate,
                )
            )

    if not candidates:
        raise FileNotFoundError(f"CSV file not found: {exact_path}")

    candidates.sort(reverse=True)
    return candidates[0][3]


def _set_nested(mapping, dotted_path, value):
    parts = dotted_path.split(".")
    node = mapping
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _clone_config(base_config, overrides=None):
    overrides = overrides or {}
    cloned = deepcopy(base_config.data)
    for dotted_path, value in overrides.items():
        _set_nested(cloned, dotted_path, value)
    return AppConfig(
        data=cloned,
        config_path=base_config.config_path,
        root_dir=base_config.root_dir,
    )


def build_expanding_yearly_windows(
    start_date,
    end_date,
    min_train_years=4,
    test_years=1,
):
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    first_test_year = start_ts.year + int(min_train_years)
    windows = []

    for test_start_year in range(first_test_year, end_ts.year + 1, int(test_years)):
        eval_start = pd.Timestamp(year=test_start_year, month=1, day=1)
        if eval_start > end_ts:
            break

        next_eval_start = pd.Timestamp(
            year=test_start_year + int(test_years),
            month=1,
            day=1,
        )
        eval_end = min(next_eval_start - pd.Timedelta(days=1), end_ts)
        train_end = eval_start - pd.Timedelta(days=1)

        if train_end < start_ts:
            continue

        train_label = (
            f"{start_ts.year}_{train_end.year}"
            if start_ts.year != train_end.year
            else f"{start_ts.year}"
        )
        test_label = (
            f"{eval_start.year}_{eval_end.year}"
            if eval_start.year != eval_end.year
            else f"{eval_start.year}"
        )

        windows.append(
            {
                "label": f"train_{train_label}__test_{test_label}",
                "train_start": start_ts.strftime("%Y-%m-%d"),
                "train_end": train_end.strftime("%Y-%m-%d"),
                "start_date": eval_start.strftime("%Y-%m-%d"),
                "end_date": eval_end.strftime("%Y-%m-%d"),
            }
        )

    return windows


def build_default_validation_windows(
    start_date,
    end_date,
    scheme="single_split",
    min_train_years=4,
    test_years=1,
):
    if scheme == "multifold":
        return build_expanding_yearly_windows(
            start_date=start_date,
            end_date=end_date,
            min_train_years=min_train_years,
            test_years=test_years,
        )

    if scheme == "full_range":
        return [
            {
                "label": "full_range",
                "train_start": start_date,
                "train_end": end_date,
                "start_date": start_date,
                "end_date": end_date,
            }
        ]

    return [
        {
            "label": "train_2018_2021",
            "train_start": start_date,
            "train_end": "2021-12-31",
            "start_date": start_date,
            "end_date": "2021-12-31",
        },
        {
            "label": "test_2022_2026",
            "train_start": start_date,
            "train_end": "2021-12-31",
            "start_date": "2022-01-01",
            "end_date": end_date,
        },
    ]


def load_branch_specs(branch_spec_path):
    branch_spec_path = Path(branch_spec_path)
    with branch_spec_path.open(encoding="utf-8") as file_handle:
        payload = json.load(file_handle)

    branches = payload.get("branches", [])
    if not branches:
        raise ValueError(f"No branches defined in {branch_spec_path}")

    return branches


def _history_source_path(config):
    symbol = config.require("app", "default_symbol")
    base_path = Path(config.require("storage", "base_path"))
    start_date = config.require("history", "start_date")
    end_date = config.require("history", "end_date")
    base_tf = config.require("timeframes", "base")
    base_folder = base_path / symbol / base_tf["label"]
    return _resolve_base_history_file(
        base_folder=base_folder,
        symbol=symbol,
        base_label=base_tf["label"],
        start_date=start_date,
        end_date=end_date,
    )


def _validation_output_dir(config, baseline_name, label, branch_name=None):
    root_output_dir = Path(config.path("backtest", "output_dir"))
    output_dir = root_output_dir / "validation" / baseline_name
    if branch_name:
        output_dir = output_dir / branch_name
    output_dir = output_dir / label
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _build_timeframes(df_1m, config):
    builder = TimeframeBuilder(config=config)
    timeframes = config.require("timeframes")

    df_15m = builder.resample(df_1m, timeframes["execution"]["rule"])
    df_1h = builder.resample(df_1m, timeframes["direction"]["rule"])
    df_5h = builder.resample(df_1m, timeframes["trend"]["rule"])
    df_12h = builder.resample(df_1m, timeframes["macro"]["rule"])

    return (
        compute_features(df_15m, config=config),
        compute_features(df_1h, config=config),
        compute_features(df_5h, config=config),
        compute_features(df_12h, config=config),
    )


def _top_trade_share(trades_df, top_n):
    if trades_df.empty:
        return 0.0, 0.0

    net = float(trades_df["pnl"].sum())
    gross_profit = float(trades_df.loc[trades_df["pnl"] > 0, "pnl"].sum())
    top_sum = float(trades_df.nlargest(min(top_n, len(trades_df)), "pnl")["pnl"].sum())

    top_net_pct = 0.0 if net == 0 else (top_sum / net) * 100
    top_gross_pct = 0.0 if gross_profit == 0 else (top_sum / gross_profit) * 100
    return top_net_pct, top_gross_pct


def _categorical_breakdown(trades_df, column):
    if trades_df.empty or column not in trades_df.columns:
        return []

    grouped = (
        trades_df.groupby(column, dropna=False)["pnl"]
        .agg(["count", "sum", "mean"])
        .reset_index()
        .rename(
            columns={
                column: "bucket",
                "count": "trade_count",
                "sum": "net_pnl",
                "mean": "avg_pnl",
            }
        )
    )
    grouped.insert(0, "dimension", column)
    return grouped.to_dict("records")


def _write_breakdown_reports(output_dir):
    output_dir = Path(output_dir)
    trades_path = output_dir / "trades.csv"
    if not trades_path.exists():
        return

    trades = pd.read_csv(trades_path)
    breakdown_rows = []
    for column in ["side", "score", "exit_reason", "pyramid_level", "regime_class"]:
        breakdown_rows.extend(_categorical_breakdown(trades, column))

    if not breakdown_rows:
        return

    report_path = output_dir / "trade_breakdowns.csv"
    with report_path.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(
            file_handle,
            fieldnames=["dimension", "bucket", "trade_count", "net_pnl", "avg_pnl"],
        )
        writer.writeheader()
        writer.writerows(breakdown_rows)


def _aggregate_window_summaries(summaries):
    if not summaries:
        return {}

    summary_df = pd.DataFrame(summaries)
    profitable_fold_pct = float((summary_df["net_pnl"] > 0).mean() * 100)

    return {
        "fold_count": int(len(summary_df)),
        "total_net_pnl": float(summary_df["net_pnl"].sum()),
        "avg_profit_factor": float(summary_df["profit_factor"].mean()),
        "median_profit_factor": float(summary_df["profit_factor"].median()),
        "min_profit_factor": float(summary_df["profit_factor"].min()),
        "avg_r_mean": float(summary_df["avg_r_initial"].mean()),
        "min_avg_r": float(summary_df["avg_r_initial"].min()),
        "worst_max_drawdown_pct": float(summary_df["max_drawdown_pct"].min()),
        "profitable_fold_pct": profitable_fold_pct,
        "avg_top10_net_pct": float(summary_df["top10_net_pct"].mean()),
        "avg_top20_net_pct": float(summary_df["top20_net_pct"].mean()),
        "avg_trade_count": float(summary_df["trade_count"].mean()),
    }


def summarize_backtest_output(output_dir, initial_equity):
    output_dir = Path(output_dir)
    trades_path = output_dir / "trades.csv"
    equity_path = output_dir / "equity.csv"

    trades = pd.read_csv(trades_path) if trades_path.exists() else pd.DataFrame()
    equity = pd.read_csv(equity_path, parse_dates=["timestamp"]) if equity_path.exists() else pd.DataFrame()

    final_equity = float(equity["equity"].iloc[-1]) if not equity.empty else float(initial_equity)
    net_pnl = final_equity - float(initial_equity)
    trade_count = int(len(trades))
    win_count = int((trades["pnl"] > 0).sum()) if trade_count else 0
    loss_count = int((trades["pnl"] <= 0).sum()) if trade_count else 0
    win_rate = 0.0 if trade_count == 0 else (win_count / trade_count) * 100

    gross_profit = float(trades.loc[trades["pnl"] > 0, "pnl"].sum()) if trade_count else 0.0
    gross_loss = float(abs(trades.loc[trades["pnl"] < 0, "pnl"].sum())) if trade_count else 0.0
    if gross_loss == 0:
        profit_factor = float("inf") if gross_profit > 0 else 0.0
    else:
        profit_factor = gross_profit / gross_loss

    avg_r = float(trades["pnl_R_initial"].mean()) if trade_count else 0.0
    median_r = float(trades["pnl_R_initial"].median()) if trade_count else 0.0

    if not equity.empty:
        rolling_max = equity["equity"].cummax()
        drawdown = equity["equity"] - rolling_max
        drawdown_pct = (drawdown / rolling_max) * 100
        max_drawdown = float(drawdown.min())
        max_drawdown_pct = float(drawdown_pct.min())
    else:
        max_drawdown = 0.0
        max_drawdown_pct = 0.0

    top10_net_pct, top10_gross_pct = _top_trade_share(trades, 10)
    top20_net_pct, top20_gross_pct = _top_trade_share(trades, 20)

    pyramided_count = int((trades["pyramid_level"] > 0).sum()) if trade_count else 0
    pyramided_pnl = float(trades.loc[trades["pyramid_level"] > 0, "pnl"].sum()) if trade_count else 0.0
    pyramided_profit_share = 0.0 if net_pnl == 0 else (pyramided_pnl / net_pnl) * 100

    return {
        "final_equity": final_equity,
        "net_pnl": net_pnl,
        "trade_count": trade_count,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate_pct": win_rate,
        "profit_factor": profit_factor,
        "avg_r_initial": avg_r,
        "median_r_initial": median_r,
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown_pct,
        "top10_net_pct": top10_net_pct,
        "top10_gross_pct": top10_gross_pct,
        "top20_net_pct": top20_net_pct,
        "top20_gross_pct": top20_gross_pct,
        "pyramided_trade_count": pyramided_count,
        "pyramided_profit_share_pct": pyramided_profit_share,
    }


def run_validation_window(
    base_config,
    source_df_1m,
    baseline_name,
    label,
    eval_start,
    eval_end,
    branch_name=None,
    train_start=None,
    train_end=None,
):
    output_dir = _validation_output_dir(
        config=base_config,
        baseline_name=baseline_name,
        label=label,
        branch_name=branch_name,
    )

    window_config = _clone_config(
        base_config,
        overrides={
            "app.debug": False,
            "history.start_date": eval_start,
            "history.end_date": eval_end,
            "backtest.resume_enabled": False,
            "backtest.output_dir": str(output_dir.resolve()),
        },
    )

    source_slice = source_df_1m.loc[:eval_end].copy()
    df_15m, df_1h, df_5h, df_12h = _build_timeframes(source_slice, config=window_config)
    df_15m_eval = df_15m.loc[eval_start:eval_end].copy()

    sim = Simulator(
        trade_logger=TradeLogger(config=window_config, reset=True),
        equity_logger=EquityLogger(config=window_config, reset=True),
        config=window_config,
    )

    engine = BacktestEngine(
        df_15m=df_15m_eval,
        df_1h=df_1h,
        df_5h=df_5h,
        df_12h=df_12h,
        simulator=sim,
        minimum_warmup_bars=0,
    )
    engine.run()

    summary = summarize_backtest_output(
        output_dir=output_dir,
        initial_equity=window_config.require("account", "initial_equity"),
    )
    _write_breakdown_reports(output_dir)
    summary.update(
        {
            "label": label,
            "branch_name": branch_name or "baseline",
            "train_start": train_start,
            "train_end": train_end,
            "start_date": eval_start,
            "end_date": eval_end,
            "output_dir": str(output_dir),
        }
    )
    return summary


def _combine_channel_equity_curves(channel_runs, combined_output_dir):
    combined_output_dir = Path(combined_output_dir)
    frames = []
    channel_columns = []

    for channel_run in channel_runs:
        channel_name = channel_run["channel_name"]
        channel_column = f"equity__{channel_name}"
        channel_columns.append(channel_column)
        equity_path = Path(channel_run["output_dir"]) / "equity.csv"
        if not equity_path.exists():
            continue

        equity_df = pd.read_csv(equity_path, parse_dates=["timestamp"])
        if equity_df.empty:
            continue

        frames.append(
            equity_df[["timestamp", "equity"]].rename(
                columns={"equity": channel_column}
            )
        )

    if not frames:
        breakdown_path = combined_output_dir / "channel_equity_breakdown.csv"
        pd.DataFrame(columns=["timestamp", "equity"]).to_csv(
            combined_output_dir / "equity.csv",
            index=False,
        )
        pd.DataFrame(columns=["timestamp", "equity"]).to_csv(
            breakdown_path,
            index=False,
        )
        return

    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on="timestamp", how="outer")

    merged = merged.sort_values("timestamp").reset_index(drop=True)
    for channel_run in channel_runs:
        channel_column = f"equity__{channel_run['channel_name']}"
        if channel_column not in merged.columns:
            merged[channel_column] = float(channel_run["initial_equity"])
        merged[channel_column] = (
            merged[channel_column]
            .ffill()
            .fillna(float(channel_run["initial_equity"]))
        )

    merged["equity"] = merged[channel_columns].sum(axis=1)
    merged[["timestamp", "equity"]].to_csv(
        combined_output_dir / "equity.csv",
        index=False,
    )
    merged.to_csv(
        combined_output_dir / "channel_equity_breakdown.csv",
        index=False,
    )


def _combine_channel_trade_logs(channel_runs, combined_output_dir):
    combined_output_dir = Path(combined_output_dir)
    combined_columns = list(TRADE_LOG_FIELDS) + [
        "portfolio_channel",
        "channel_allocation_fraction",
        "channel_initial_equity",
    ]
    frames = []

    for channel_run in channel_runs:
        trades_path = Path(channel_run["output_dir"]) / "trades.csv"
        if not trades_path.exists():
            continue

        trades_df = pd.read_csv(trades_path)
        if trades_df.empty:
            continue

        trades_df["portfolio_channel"] = channel_run["channel_name"]
        trades_df["channel_allocation_fraction"] = float(
            channel_run["allocation_fraction"]
        )
        trades_df["channel_initial_equity"] = float(channel_run["initial_equity"])
        frames.append(trades_df)

    if frames:
        combined = pd.concat(frames, ignore_index=True, sort=False)
        sort_columns = []
        for column in ["entry_time", "exit_time"]:
            if column in combined.columns:
                combined[column] = pd.to_datetime(combined[column], errors="coerce")
                sort_columns.append(column)
        if sort_columns:
            combined = combined.sort_values(sort_columns, kind="stable")
        combined.to_csv(combined_output_dir / "trades.csv", index=False)
        return

    pd.DataFrame(columns=combined_columns).to_csv(
        combined_output_dir / "trades.csv",
        index=False,
    )


def _write_channel_summary(channel_runs, combined_output_dir):
    combined_output_dir = Path(combined_output_dir)
    rows = []
    for channel_run in channel_runs:
        row = {
            "channel_name": channel_run["channel_name"],
            "allocation_fraction": float(channel_run["allocation_fraction"]),
            "initial_equity": float(channel_run["initial_equity"]),
            "output_dir": str(channel_run["output_dir"]),
        }
        row.update(channel_run["summary"])
        rows.append(row)

    summary_path = combined_output_dir / "channel_summary.csv"
    if rows:
        with summary_path.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    else:
        summary_path.touch()


def run_portfolio_validation_window(
    base_config,
    source_df_1m,
    baseline_name,
    label,
    eval_start,
    eval_end,
    channel_specs,
    branch_name=None,
    train_start=None,
    train_end=None,
):
    total_initial_equity = float(base_config.require("account", "initial_equity"))
    total_allocation = sum(
        float(channel_spec["allocation_fraction"])
        for channel_spec in (channel_specs or [])
    )
    if total_allocation <= 0:
        raise ValueError("Portfolio validation requires positive channel allocation")
    if abs(total_allocation - 1.0) > 1e-9:
        raise ValueError(
            "Portfolio channel allocations must sum to 1.0, "
            f"received {total_allocation:.6f}"
        )

    combined_output_dir = _validation_output_dir(
        config=base_config,
        baseline_name=baseline_name,
        label=label,
        branch_name=branch_name,
    )

    channel_runs = []
    for channel_spec in channel_specs:
        channel_name = channel_spec["name"]
        allocation_fraction = float(channel_spec["allocation_fraction"])
        channel_initial_equity = total_initial_equity * allocation_fraction

        if "config" in channel_spec:
            loaded_config = AppConfig.load(config_path=channel_spec["config"])
            channel_config = _clone_config(
                loaded_config,
                overrides={
                    **(channel_spec.get("overrides", {}) or {}),
                    "account.initial_equity": channel_initial_equity,
                },
            )
        else:
            channel_config = _clone_config(
                base_config,
                overrides={
                    **(channel_spec.get("overrides", {}) or {}),
                    "account.initial_equity": channel_initial_equity,
                },
            )

        channel_summary = run_validation_window(
            base_config=channel_config,
            source_df_1m=source_df_1m,
            baseline_name=baseline_name,
            branch_name=f"{branch_name}/channels/{channel_name}" if branch_name else f"channels/{channel_name}",
            label=label,
            eval_start=eval_start,
            eval_end=eval_end,
            train_start=train_start,
            train_end=train_end,
        )
        channel_runs.append(
            {
                "channel_name": channel_name,
                "allocation_fraction": allocation_fraction,
                "initial_equity": channel_initial_equity,
                "output_dir": channel_summary["output_dir"],
                "summary": channel_summary,
            }
        )

    _combine_channel_equity_curves(channel_runs, combined_output_dir)
    _combine_channel_trade_logs(channel_runs, combined_output_dir)
    _write_channel_summary(channel_runs, combined_output_dir)
    _write_breakdown_reports(combined_output_dir)

    summary = summarize_backtest_output(
        output_dir=combined_output_dir,
        initial_equity=total_initial_equity,
    )
    summary.update(
        {
            "label": label,
            "branch_name": branch_name or "portfolio",
            "train_start": train_start,
            "train_end": train_end,
            "start_date": eval_start,
            "end_date": eval_end,
            "output_dir": str(combined_output_dir),
        }
    )
    return summary


def _write_walkforward_reports(summary_dir, summaries):
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / "walkforward_summary.csv"

    fieldnames = [
        "branch_name",
        "label",
        "train_start",
        "train_end",
        "start_date",
        "end_date",
        "final_equity",
        "net_pnl",
        "trade_count",
        "win_count",
        "loss_count",
        "win_rate_pct",
        "profit_factor",
        "avg_r_initial",
        "median_r_initial",
        "max_drawdown",
        "max_drawdown_pct",
        "top10_net_pct",
        "top10_gross_pct",
        "top20_net_pct",
        "top20_gross_pct",
        "pyramided_trade_count",
        "pyramided_profit_share_pct",
        "output_dir",
    ]

    with summary_path.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summaries)

    drift_rows = []
    if len(summaries) >= 2:
        base = summaries[0]
        for summary in summaries[1:]:
            drift_rows.append(
                {
                    "baseline_window": base["label"],
                    "comparison_window": summary["label"],
                    "profit_factor_delta": summary["profit_factor"] - base["profit_factor"],
                    "avg_r_delta": summary["avg_r_initial"] - base["avg_r_initial"],
                    "max_drawdown_pct_delta": summary["max_drawdown_pct"] - base["max_drawdown_pct"],
                    "win_rate_pct_delta": summary["win_rate_pct"] - base["win_rate_pct"],
                    "trade_count_delta": summary["trade_count"] - base["trade_count"],
                    "top10_net_pct_delta": summary["top10_net_pct"] - base["top10_net_pct"],
                    "top20_net_pct_delta": summary["top20_net_pct"] - base["top20_net_pct"],
                }
            )

    drift_path = summary_dir / "walkforward_drift.csv"
    with drift_path.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(
            file_handle,
            fieldnames=[
                "baseline_window",
                "comparison_window",
                "profit_factor_delta",
                "avg_r_delta",
                "max_drawdown_pct_delta",
                "win_rate_pct_delta",
                "trade_count_delta",
                "top10_net_pct_delta",
                "top20_net_pct_delta",
            ],
        )
        writer.writeheader()
        writer.writerows(drift_rows)

    aggregate = _aggregate_window_summaries(summaries)
    aggregate_path = summary_dir / "walkforward_aggregate.csv"
    if aggregate:
        with aggregate_path.open("w", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=list(aggregate.keys()))
            writer.writeheader()
            writer.writerow(aggregate)
    else:
        aggregate_path.touch()

    return summary_path, drift_path, aggregate_path, aggregate


def _run_walkforward_validation_for_config(
    config,
    source_df_1m,
    baseline_name,
    windows,
    branch_name=None,
    channel_specs=None,
):
    summaries = []
    for window in windows:
        if channel_specs:
            summaries.append(
                run_portfolio_validation_window(
                    base_config=config,
                    source_df_1m=source_df_1m,
                    baseline_name=baseline_name,
                    branch_name=branch_name,
                    channel_specs=channel_specs,
                    label=window["label"],
                    eval_start=window["start_date"],
                    eval_end=window["end_date"],
                    train_start=window.get("train_start"),
                    train_end=window.get("train_end"),
                )
            )
        else:
            summaries.append(
                run_validation_window(
                    base_config=config,
                    source_df_1m=source_df_1m,
                    baseline_name=baseline_name,
                    branch_name=branch_name,
                    label=window["label"],
                    eval_start=window["start_date"],
                    eval_end=window["end_date"],
                    train_start=window.get("train_start"),
                    train_end=window.get("train_end"),
                )
            )

    summary_dir = Path(config.path("backtest", "output_dir")) / "validation" / baseline_name
    if branch_name:
        summary_dir = summary_dir / branch_name

    summary_path, drift_path, aggregate_path, aggregate = _write_walkforward_reports(
        summary_dir=summary_dir,
        summaries=summaries,
    )

    return {
        "baseline_name": baseline_name,
        "branch_name": branch_name or "baseline",
        "summary_path": str(summary_path),
        "drift_path": str(drift_path),
        "aggregate_path": str(aggregate_path),
        "aggregate": aggregate,
        "windows": summaries,
    }


def run_walkforward_validation(
    config_path=None,
    baseline_name="baseline_v3_compound_strong",
    windows=None,
    branch_name=None,
    scheme="single_split",
    min_train_years=4,
    test_years=1,
):
    configure_debug(enabled=False)
    config = AppConfig.load(config_path=config_path)
    source_path = _history_source_path(config)
    if not source_path.exists():
        raise FileNotFoundError(
            "Canonical 1m history file not found for validation: "
            f"{source_path}"
        )

    source_df_1m = load_from_csv(source_path)
    history_start = config.require("history", "start_date")
    history_end = config.require("history", "end_date")
    if windows is None:
        windows = build_default_validation_windows(
            start_date=history_start,
            end_date=history_end,
            scheme=scheme,
            min_train_years=min_train_years,
            test_years=test_years,
        )

    result = _run_walkforward_validation_for_config(
        config=config,
        source_df_1m=source_df_1m,
        baseline_name=baseline_name,
        windows=windows,
        branch_name=branch_name,
    )

    return {
        **result,
        "source_path": str(source_path),
        "scheme": scheme,
        "windows": result["windows"],
    }


def run_branch_walkforward_validation(
    config_path=None,
    baseline_name="baseline_v3_compound_strong",
    branch_specs=None,
    branch_spec_path=None,
    windows=None,
    scheme="multifold",
    min_train_years=4,
    test_years=1,
    comparison_tag=None,
):
    configure_debug(enabled=False)
    base_config = AppConfig.load(config_path=config_path)
    source_path = _history_source_path(base_config)
    if not source_path.exists():
        raise FileNotFoundError(
            "Canonical 1m history file not found for validation: "
            f"{source_path}"
        )

    source_df_1m = load_from_csv(source_path)
    history_start = base_config.require("history", "start_date")
    history_end = base_config.require("history", "end_date")

    if branch_specs is None:
        if branch_spec_path is None:
            raise ValueError("branch_specs or branch_spec_path is required for branch testing")
        branch_specs = load_branch_specs(branch_spec_path)
        if comparison_tag is None:
            comparison_tag = Path(branch_spec_path).stem

    if windows is None:
        windows = build_default_validation_windows(
            start_date=history_start,
            end_date=history_end,
            scheme=scheme,
            min_train_years=min_train_years,
            test_years=test_years,
        )

    branch_results = []
    comparison_rows = []

    for branch_spec in branch_specs:
        branch_name = branch_spec["name"]
        if "config" in branch_spec:
            branch_config = AppConfig.load(config_path=branch_spec["config"])
        else:
            branch_config = _clone_config(
                base_config,
                overrides=branch_spec.get("overrides", {}),
            )

        result = _run_walkforward_validation_for_config(
            config=branch_config,
            source_df_1m=source_df_1m,
            baseline_name=baseline_name,
            windows=windows,
            branch_name=branch_name,
            channel_specs=branch_spec.get("channels"),
        )
        branch_results.append(result)

        aggregate = dict(result["aggregate"])
        aggregate["branch_name"] = branch_name
        comparison_rows.append(aggregate)

    comparison_dir = Path(base_config.path("backtest", "output_dir")) / "validation" / baseline_name
    comparison_dir.mkdir(parents=True, exist_ok=True)
    comparison_suffix = f"__{comparison_tag}" if comparison_tag else ""
    comparison_path = comparison_dir / f"branch_comparison{comparison_suffix}.csv"
    fieldnames = ["branch_name"] + list(branch_results[0]["aggregate"].keys())
    with comparison_path.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(comparison_rows)

    branch_window_rows = []
    for branch in branch_results:
        branch_window_rows.extend(branch["windows"])

    branch_window_path = comparison_dir / f"branch_window_comparison{comparison_suffix}.csv"
    branch_window_fieldnames = list(branch_window_rows[0].keys()) if branch_window_rows else []
    with branch_window_path.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(
            file_handle,
            fieldnames=branch_window_fieldnames,
        )
        writer.writeheader()
        writer.writerows(branch_window_rows)

    return {
        "baseline_name": baseline_name,
        "source_path": str(source_path),
        "comparison_path": str(comparison_path),
        "branch_window_path": str(branch_window_path),
        "branch_results": branch_results,
        "scheme": scheme,
        "windows": windows,
    }
