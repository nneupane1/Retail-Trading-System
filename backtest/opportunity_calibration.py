"""Builds calibration reports from logged opportunities and executed trades."""

from pathlib import Path

import pandas as pd

from config import AppConfig


TRADE_EXPORT_COLUMNS = [
    "trade_id",
    "opportunity_id",
    "side",
    "signal_family",
    "score",
    "entry_time",
    "exit_time",
    "entry_price",
    "exit_price",
    "pnl",
    "pnl_R_total",
    "pnl_R_initial",
    "equity_return_fraction",
    "entry_risk_multiplier",
    "entry_threshold",
    "exit_reason",
]


def _coerce_bool(series):
    if series is None:
        return pd.Series(dtype=bool)
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    normalized = (
        series.astype(str)
        .str.strip()
        .str.lower()
    )
    truthy = {"true", "1", "yes", "y"}
    return normalized.isin(truthy)


def _build_fallback_match_key(df, *, time_column, score_column):
    timestamp_text = pd.to_datetime(df[time_column], errors="coerce").dt.strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    side = df.get("side", pd.Series(["unknown"] * len(df), index=df.index)).astype(str)
    signal_family = df.get(
        "signal_family",
        pd.Series(["trend"] * len(df), index=df.index),
    ).astype(str)
    score = pd.to_numeric(df.get(score_column), errors="coerce").fillna(-1).astype(float)
    return (
        timestamp_text.fillna("missing-time")
        + "|"
        + side
        + "|"
        + signal_family
        + "|"
        + score.map(lambda value: f"{value:.6f}")
    )


def _assign_strength_bucket(joined_df, bucket_count):
    numeric = pd.to_numeric(joined_df["final_strength"], errors="coerce")
    valid = numeric.dropna()
    if valid.empty:
        return pd.Series(["unknown"] * len(joined_df), index=joined_df.index)

    effective_buckets = max(1, min(int(bucket_count), int(valid.nunique())))
    if effective_buckets <= 1:
        return pd.Series(["q1"] * len(joined_df), index=joined_df.index)

    ranked = valid.rank(method="first")
    labels = [f"q{i + 1}" for i in range(effective_buckets)]
    bucketed = pd.qcut(ranked, q=effective_buckets, labels=labels)
    series = pd.Series(["unknown"] * len(joined_df), index=joined_df.index)
    series.loc[valid.index] = bucketed.astype(str)
    return series


def load_opportunities(path):
    opportunities = pd.read_csv(path)
    if opportunities.empty:
        return opportunities

    opportunities["timestamp"] = pd.to_datetime(opportunities["timestamp"], errors="coerce")
    opportunities["eligible"] = _coerce_bool(opportunities.get("eligible"))
    opportunities["structural_floor_passed"] = _coerce_bool(
        opportunities.get("structural_floor_passed")
    )
    opportunities["breakout_event"] = _coerce_bool(opportunities.get("breakout_event"))

    numeric_columns = [
        "regime_score",
        "raw_score",
        "score_norm",
        "score_max",
        "momentum_strength",
        "signal_strength",
        "bias_weight",
        "regime_weight",
        "event_bonus",
        "final_strength",
        "entry_risk_multiplier",
        "bucket_expected_return",
        "bucket_risk_mult",
        "price_to_fast_ema_ratio",
        "ema_gap_ratio",
        "vwap_distance_ratio",
        "macd_hist",
        "bias_directional_strength",
        "bias_price_vs_ema_ratio",
        "bias_ema_slope",
        "regime_max_score",
        "regime_normalized_strength",
        "bias_points",
        "trend_points",
        "vwap_points",
        "compression_points",
        "event_points",
        "body_strength_points",
        "close_position_points",
        "wick_points",
        "atr_points",
        "macd_points",
        "bollinger_points",
    ]
    for column in numeric_columns:
        if column in opportunities.columns:
            opportunities[column] = pd.to_numeric(opportunities[column], errors="coerce")

    return opportunities


def load_trades(path):
    trades = pd.read_csv(path)
    if trades.empty:
        return trades

    for column in ["entry_time", "exit_time"]:
        if column in trades.columns:
            trades[column] = pd.to_datetime(trades[column], errors="coerce")

    numeric_columns = [
        "entry_price",
        "exit_price",
        "pnl",
        "pnl_R_total",
        "pnl_R_initial",
        "equity_return_fraction",
        "entry_risk_multiplier",
        "entry_threshold",
        "score",
    ]
    for column in numeric_columns:
        if column in trades.columns:
            trades[column] = pd.to_numeric(trades[column], errors="coerce")

    return trades


def build_opportunity_trade_join(opportunities_df, trades_df):
    joined = opportunities_df.copy()
    trades = trades_df.copy()

    if joined.empty:
        joined["executed"] = pd.Series(dtype=bool)
        joined["match_method"] = pd.Series(dtype=str)
        return joined

    join_on_opportunity_id = (
        "opportunity_id" in joined.columns
        and "opportunity_id" in trades.columns
        and joined["opportunity_id"].notna().any()
        and trades["opportunity_id"].notna().any()
    )

    trade_export = trades.copy()
    match_method = "opportunity_id"

    if join_on_opportunity_id:
        trade_export = trade_export.drop_duplicates(subset=["opportunity_id"], keep="last")
        trade_export = trade_export.rename(
            columns={column: f"trade_{column}" for column in TRADE_EXPORT_COLUMNS if column in trade_export.columns}
        )
        joined = joined.merge(
            trade_export,
            left_on="opportunity_id",
            right_on="trade_opportunity_id",
            how="left",
        )
    else:
        match_method = "fallback_time_side_signal_score"
        joined["_fallback_match_key"] = _build_fallback_match_key(
            joined,
            time_column="timestamp",
            score_column="raw_score",
        )
        trade_export["_fallback_match_key"] = _build_fallback_match_key(
            trade_export,
            time_column="entry_time",
            score_column="score",
        )
        trade_export = trade_export.drop_duplicates(
            subset=["_fallback_match_key"],
            keep="last",
        )
        trade_export = trade_export.rename(
            columns={column: f"trade_{column}" for column in TRADE_EXPORT_COLUMNS if column in trade_export.columns}
        )
        joined = joined.merge(
            trade_export,
            on="_fallback_match_key",
            how="left",
        )
        joined = joined.drop(columns=["_fallback_match_key"])

    joined["executed"] = joined.get("trade_trade_id").notna()
    joined["match_method"] = match_method
    joined["opportunity_day"] = pd.to_datetime(joined["timestamp"], errors="coerce").dt.date
    joined["strength_bucket"] = _assign_strength_bucket(joined, bucket_count=8)
    return joined


def summarize_strength_buckets(joined_df, bucket_count=8):
    working = joined_df.copy()
    working["strength_bucket"] = _assign_strength_bucket(working, bucket_count=bucket_count)
    grouped = working.groupby("strength_bucket", dropna=False)
    summary = grouped.agg(
        opportunity_count=("strength_bucket", "size"),
        eligible_count=("eligible", "sum"),
        executed_trade_count=("executed", "sum"),
        avg_final_strength=("final_strength", "mean"),
        avg_raw_score=("raw_score", "mean"),
        avg_entry_risk_multiplier=("entry_risk_multiplier", "mean"),
        avg_pnl=("trade_pnl", "mean"),
        avg_pnl_R_initial=("trade_pnl_R_initial", "mean"),
        avg_equity_return_fraction=("trade_equity_return_fraction", "mean"),
    ).reset_index()
    summary["execution_rate"] = (
        summary["executed_trade_count"] / summary["opportunity_count"]
    ).fillna(0.0)
    return summary.sort_values("strength_bucket").reset_index(drop=True)


def summarize_signal_families(joined_df):
    grouped = joined_df.groupby(["side", "signal_family"], dropna=False)
    summary = grouped.agg(
        opportunity_count=("signal_family", "size"),
        eligible_count=("eligible", "sum"),
        executed_trade_count=("executed", "sum"),
        avg_final_strength=("final_strength", "mean"),
        avg_raw_score=("raw_score", "mean"),
        avg_pnl_R_initial=("trade_pnl_R_initial", "mean"),
        avg_equity_return_fraction=("trade_equity_return_fraction", "mean"),
    ).reset_index()
    summary["execution_rate"] = (
        summary["executed_trade_count"] / summary["opportunity_count"]
    ).fillna(0.0)
    return summary.sort_values(["side", "signal_family"]).reset_index(drop=True)


def summarize_daily_frequency(joined_df):
    daily = joined_df.groupby("opportunity_day", dropna=False).agg(
        opportunity_count=("opportunity_day", "size"),
        eligible_count=("eligible", "sum"),
        executed_trade_count=("executed", "sum"),
        avg_final_strength=("final_strength", "mean"),
    ).reset_index()
    daily["execution_rate"] = (
        daily["executed_trade_count"] / daily["opportunity_count"]
    ).fillna(0.0)
    return daily.sort_values("opportunity_day").reset_index(drop=True)


def summarize_overview(joined_df):
    opportunity_days = joined_df["opportunity_day"].dropna()
    distinct_days = int(opportunity_days.nunique()) if not opportunity_days.empty else 0
    summary = {
        "opportunity_count": int(len(joined_df)),
        "eligible_count": int(joined_df["eligible"].sum()),
        "executed_trade_count": int(joined_df["executed"].sum()),
        "avg_final_strength": float(joined_df["final_strength"].mean()),
        "avg_raw_score": float(joined_df["raw_score"].mean()),
        "avg_pnl_R_initial": float(joined_df["trade_pnl_R_initial"].mean()),
        "avg_equity_return_fraction": float(joined_df["trade_equity_return_fraction"].mean()),
        "match_method": str(joined_df["match_method"].iloc[0]) if not joined_df.empty else "none",
        "days_observed": distinct_days,
        "avg_opportunities_per_day": (
            float(len(joined_df) / distinct_days) if distinct_days else 0.0
        ),
        "avg_executed_trades_per_day": (
            float(joined_df["executed"].sum() / distinct_days) if distinct_days else 0.0
        ),
    }
    summary["execution_rate"] = (
        float(summary["executed_trade_count"]) / float(summary["opportunity_count"])
        if summary["opportunity_count"]
        else 0.0
    )
    return pd.DataFrame([summary])


def run_opportunity_calibration(
    *,
    opportunities_path=None,
    trades_path=None,
    output_dir=None,
    bucket_count=8,
    config=None,
):
    config = config or AppConfig.load()
    opportunities_path = Path(
        opportunities_path or config.path("backtest", "output_dir") / "opportunities.csv"
    )
    trades_path = Path(
        trades_path or config.path("backtest", "output_dir") / "trades.csv"
    )
    output_dir = Path(
        output_dir
        or config.get("backtest", "calibration_output_dir", default="backtest/output/calibration")
    )
    if not output_dir.is_absolute():
        output_dir = config.root_dir / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if not opportunities_path.exists():
        raise FileNotFoundError(
            "Opportunities CSV not found. Run a backtest with "
            "`backtest.opportunity_log_enabled = true` first, or pass "
            "`--opportunities` explicitly."
        )
    if not trades_path.exists():
        raise FileNotFoundError(
            "Trades CSV not found. Run a backtest first, or pass `--trades` "
            "explicitly."
        )

    opportunities_df = load_opportunities(opportunities_path)
    trades_df = load_trades(trades_path)
    joined_df = build_opportunity_trade_join(opportunities_df, trades_df)

    strength_summary = summarize_strength_buckets(joined_df, bucket_count=bucket_count)
    signal_family_summary = summarize_signal_families(joined_df)
    daily_summary = summarize_daily_frequency(joined_df)
    overview = summarize_overview(joined_df)

    joined_path = output_dir / "opportunity_trade_join.csv"
    strength_path = output_dir / "strength_bucket_summary.csv"
    family_path = output_dir / "signal_family_summary.csv"
    daily_path = output_dir / "daily_frequency_summary.csv"
    overview_path = output_dir / "calibration_overview.csv"

    joined_df.to_csv(joined_path, index=False)
    strength_summary.to_csv(strength_path, index=False)
    signal_family_summary.to_csv(family_path, index=False)
    daily_summary.to_csv(daily_path, index=False)
    overview.to_csv(overview_path, index=False)

    return {
        "joined_path": str(joined_path),
        "strength_summary_path": str(strength_path),
        "signal_family_summary_path": str(family_path),
        "daily_summary_path": str(daily_path),
        "overview_path": str(overview_path),
        "overview": overview.iloc[0].to_dict() if not overview.empty else {},
    }
