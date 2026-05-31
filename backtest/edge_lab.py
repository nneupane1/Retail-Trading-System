"""Isolates simple edge families and builds a lean deployable edge table."""

import json
from pathlib import Path

import pandas as pd

from config import AppConfig
from data.downloader import load_from_csv
from data.resampler import TimeframeBuilder
from entry.edge_buckets import (
    build_signal_bucket,
    classify_bias_bucket,
    classify_body_bucket,
    classify_vwap_bucket,
    infer_edge_type,
)
from features.feature_pipeline import compute_features


DEFAULT_HORIZONS = (1, 3, 5)
DEFAULT_ROUND_TRIP_FEE_RATE = 0.001


def _parse_storage_timestamp(value):
    return pd.Timestamp(str(value).replace("T", " ").replace(".", ":"))


def _resolve_base_history_file(base_folder, symbol, base_label, start_date, end_date):
    exact_path = base_folder / f"{symbol}_{base_label}_{start_date}_to_{end_date}.csv"
    if exact_path.exists():
        return exact_path

    requested_start = pd.Timestamp(start_date)
    requested_end = pd.Timestamp(end_date)
    candidates = []
    for candidate in base_folder.glob(f"{symbol}_{base_label}_*.csv"):
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
            candidates.append((candidate_end >= requested_end, candidate_end, candidate_start, candidate))

    if not candidates:
        raise FileNotFoundError(f"CSV file not found: {exact_path}")

    candidates.sort(key=lambda item: (item[0], item[1], -item[2].value), reverse=True)
    return candidates[0][3]


def _load_execution_features(
    *,
    symbol,
    base_path,
    start_date,
    end_date,
    config,
):
    base_label = config.require("timeframes", "base", "label")
    base_folder = Path(base_path) / symbol / base_label
    base_file = _resolve_base_history_file(
        base_folder,
        symbol,
        base_label,
        start_date,
        end_date,
    )
    df_1m = load_from_csv(base_file)
    builder = TimeframeBuilder(config=config)
    execution_rule = config.require("timeframes", "execution", "rule")
    df_execution = builder.resample(df_1m, execution_rule)
    return compute_features(df_execution, config=config)


def _side_sign(side):
    return 1.0 if str(side).lower() == "long" else -1.0


def _build_forward_metrics(df, horizon, side):
    sign = _side_sign(side)
    close = pd.to_numeric(df["close"], errors="coerce")
    future_close = close.shift(-horizon)

    future_high = pd.concat(
        [pd.to_numeric(df["high"], errors="coerce").shift(-step) for step in range(1, horizon + 1)],
        axis=1,
    ).max(axis=1)
    future_low = pd.concat(
        [pd.to_numeric(df["low"], errors="coerce").shift(-step) for step in range(1, horizon + 1)],
        axis=1,
    ).min(axis=1)

    gross_return = sign * ((future_close / close) - 1.0)
    favorable_excursion = (
        ((future_high / close) - 1.0)
        if sign > 0
        else ((close / future_low) - 1.0)
    )
    adverse_excursion = (
        ((future_low / close) - 1.0)
        if sign > 0
        else ((close / future_high) - 1.0)
    )
    future_range_ratio = (future_high - future_low) / (close + 1e-9)
    current_vwap_dev = pd.to_numeric(df.get("vwap_distance_ratio"), errors="coerce").abs()
    future_vwap_dev = current_vwap_dev.shift(-horizon)
    vwap_reversion_ratio = (current_vwap_dev - future_vwap_dev) / (current_vwap_dev + 1e-9)

    return pd.DataFrame(
        {
            "gross_return": gross_return,
            "favorable_excursion": favorable_excursion,
            "adverse_excursion": adverse_excursion,
            "future_range_ratio": future_range_ratio,
            "vwap_reversion_ratio": vwap_reversion_ratio,
        },
        index=df.index,
    )


def _infer_edge_family(row, config):
    signals = []
    scoring = config.get("strategy", "scoring", default={}) or {}
    body_min = float(scoring.get("body_strength_min", 1.3))
    close_min = float(scoring.get("close_position_min", 0.6))
    close_max = float(scoring.get("close_position_max", 0.4))
    pressure = config.get("features", "pressure", default={}) or {}
    vwap_threshold = float(
        pressure.get("mean_reversion_vwap_distance_threshold", 0.01)
    )
    wick_threshold = float(
        pressure.get("mean_reversion_wick_threshold", 1.2)
    )

    if (
        bool(row.get("breakout"))
        and float(row.get("body_strength", 0.0) or 0.0) >= body_min
        and float(row.get("close_position", 0.0) or 0.0) >= close_min
    ):
        signals.append(("momentum_breakout", "long"))
    if (
        bool(row.get("breakdown"))
        and float(row.get("body_strength", 0.0) or 0.0) >= body_min
        and float(row.get("close_position", 1.0) or 1.0) <= close_max
    ):
        signals.append(("momentum_breakout", "short"))

    if bool(row.get("compression")) and bool(row.get("breakout")):
        signals.append(("compression_expansion", "long"))
    if bool(row.get("compression")) and bool(row.get("breakdown")):
        signals.append(("compression_expansion", "short"))

    vwap_distance = float(row.get("vwap_distance_ratio", 0.0) or 0.0)
    upper_wick_ratio = float(row.get("upper_wick_ratio", 0.0) or 0.0)
    lower_wick_ratio = float(row.get("lower_wick_ratio", 0.0) or 0.0)
    close_position = float(row.get("close_position", 0.5) or 0.5)
    if (
        vwap_distance <= -vwap_threshold
        and lower_wick_ratio >= wick_threshold
        and close_position >= 0.45
    ):
        signals.append(("mean_reversion_vwap", "long"))
    if (
        vwap_distance >= vwap_threshold
        and upper_wick_ratio >= wick_threshold
        and close_position <= 0.55
    ):
        signals.append(("mean_reversion_vwap", "short"))
    return signals


def _infer_bias_bucket(row, config):
    fast_period = int(config.require("features", "ema_periods", "fast"))
    slow_period = int(config.require("features", "ema_periods", "slow"))
    fast_column = f"ema{fast_period}"
    slow_column = f"ema{slow_period}"
    close = float(row.get("close", 0.0) or 0.0)
    fast_ema = float(row.get(fast_column, close) or close)
    slow_ema = float(row.get(slow_column, close) or close)
    ema_gap_ratio = float(row.get("ema_gap_ratio", 0.0) or 0.0)
    if close > slow_ema and close > fast_ema and ema_gap_ratio > 0:
        return "bullish"
    if close < slow_ema and close < fast_ema and ema_gap_ratio < 0:
        return "bearish"
    return "neutral"


def _runtime_edge_type(edge_family, side):
    family_map = {
        ("momentum_breakout", "long"): "momentum_long",
        ("momentum_breakout", "short"): "momentum_short",
        ("compression_expansion", "long"): "compression_long",
        ("compression_expansion", "short"): "compression_short",
        ("mean_reversion_vwap", "long"): "mean_reversion_long",
        ("mean_reversion_vwap", "short"): "mean_reversion_short",
    }
    return family_map.get((edge_family, side))


def extract_edge_signals(
    df,
    *,
    symbol,
    horizons=DEFAULT_HORIZONS,
    round_trip_fee_rate=DEFAULT_ROUND_TRIP_FEE_RATE,
    config=None,
):
    config = config or AppConfig.load()
    signal_rows = []

    for horizon in horizons:
        long_metrics = _build_forward_metrics(df, horizon, "long")
        short_metrics = _build_forward_metrics(df, horizon, "short")

        for timestamp, row in df.iterrows():
            families = _infer_edge_family(row, config)
            if not families:
                continue

            for edge_family, side in families:
                metrics = long_metrics.loc[timestamp] if side == "long" else short_metrics.loc[timestamp]
                gross_return = metrics["gross_return"]
                if pd.isna(gross_return):
                    continue

                net_return = gross_return - float(round_trip_fee_rate)
                signal_rows.append(
                    {
                        "symbol": symbol,
                        "timestamp": timestamp,
                        "edge_family": edge_family,
                        "side": side,
                        "horizon_candles": int(horizon),
                        "entry_close": float(row.get("close", 0.0) or 0.0),
                        "body_strength": float(row.get("body_strength", 0.0) or 0.0),
                        "close_position": float(row.get("close_position", 0.0) or 0.0),
                        "compression": bool(row.get("compression", False)),
                        "breakout": bool(row.get("breakout", False)),
                        "breakdown": bool(row.get("breakdown", False)),
                        "vwap_distance_ratio": float(row.get("vwap_distance_ratio", 0.0) or 0.0),
                        "upper_wick_ratio": float(row.get("upper_wick_ratio", 0.0) or 0.0),
                        "lower_wick_ratio": float(row.get("lower_wick_ratio", 0.0) or 0.0),
                        "atr_rising": bool(row.get("atr_rising", False)),
                        "future_return_gross": float(gross_return),
                        "future_return_net": float(net_return),
                        "future_range_ratio": float(metrics["future_range_ratio"]),
                        "favorable_excursion": float(metrics["favorable_excursion"]),
                        "adverse_excursion": float(metrics["adverse_excursion"]),
                        "vwap_reversion_ratio": float(metrics["vwap_reversion_ratio"]),
                        "round_trip_fee_rate": float(round_trip_fee_rate),
                        "bias_bucket": _infer_bias_bucket(row, config),
                        "body_bucket": classify_body_bucket(row, config=config),
                        "vwap_bucket": classify_vwap_bucket(row, config=config),
                        "edge_type": _runtime_edge_type(edge_family, side),
                    }
                )

    return pd.DataFrame(signal_rows)


def summarize_edge_buckets(
    signals_df,
    *,
    min_count=300,
    min_avg_return_net=0.0,
):
    if signals_df.empty:
        return pd.DataFrame(
            columns=[
                "edge_type",
                "bias_bucket",
                "body_bucket",
                "vwap_bucket",
                "selected_horizon",
                "signal_count",
                "avg_return_net",
                "median_return_net",
                "win_rate_net",
                "risk_mult",
                "valid",
                "bucket_key",
            ]
        )

    grouped = signals_df.groupby(
        [
            "edge_type",
            "bias_bucket",
            "body_bucket",
            "vwap_bucket",
            "horizon_candles",
        ],
        dropna=False,
    )
    bucketed = grouped.agg(
        signal_count=("edge_type", "size"),
        avg_return_net=("future_return_net", "mean"),
        median_return_net=("future_return_net", "median"),
        avg_return_gross=("future_return_gross", "mean"),
    ).reset_index()
    bucketed["win_rate_net"] = (
        grouped["future_return_net"].apply(lambda values: (values > 0).mean()).values
    )

    bucketed = bucketed.sort_values(
        [
            "edge_type",
            "bias_bucket",
            "body_bucket",
            "vwap_bucket",
            "avg_return_net",
            "signal_count",
        ],
        ascending=[True, True, True, True, False, False],
    )
    best = bucketed.drop_duplicates(
        subset=["edge_type", "bias_bucket", "body_bucket", "vwap_bucket"],
        keep="first",
    ).reset_index(drop=True)
    best["valid"] = (
        (best["signal_count"] >= int(min_count))
        & (best["avg_return_net"] > float(min_avg_return_net))
    )
    scaled = 1.0 + (best["avg_return_net"].clip(lower=0.0) * 100.0)
    best["risk_mult"] = scaled.clip(lower=1.0, upper=1.5).round(4)
    best["selected_horizon"] = best["horizon_candles"].astype(int)
    best["bucket_key"] = best.apply(
        lambda row: "|".join(
            [
                str(row["edge_type"]),
                str(row["bias_bucket"]),
                str(row["body_bucket"]),
                str(row["vwap_bucket"]),
            ]
        ),
        axis=1,
    )
    return best[
        [
            "edge_type",
            "bias_bucket",
            "body_bucket",
            "vwap_bucket",
            "selected_horizon",
            "signal_count",
            "avg_return_gross",
            "avg_return_net",
            "median_return_net",
            "win_rate_net",
            "risk_mult",
            "valid",
            "bucket_key",
        ]
    ]


def export_edge_table_json(bucket_summary_df, path, *, min_count, min_avg_return_net):
    payload = {
        "metadata": {
            "min_count": int(min_count),
            "min_avg_return_net": float(min_avg_return_net),
        },
        "buckets": {},
    }
    for _, row in bucket_summary_df.iterrows():
        payload["buckets"][str(row["bucket_key"])] = {
            "valid": bool(row["valid"]),
            "expected_return": float(row["avg_return_net"]),
            "risk_mult": float(row["risk_mult"]),
            "signal_count": int(row["signal_count"]),
            "selected_horizon": int(row["selected_horizon"]),
            "win_rate_net": float(row["win_rate_net"]),
            "reason": None if bool(row["valid"]) else "edge_table_filter",
        }

    with Path(path).open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2)


def summarize_edge_signals(signals_df):
    if signals_df.empty:
        return pd.DataFrame(
            columns=[
                "edge_family",
                "side",
                "horizon_candles",
                "signal_count",
                "avg_return_gross",
                "avg_return_net",
                "median_return_net",
                "win_rate_net",
                "avg_future_range_ratio",
                "avg_favorable_excursion",
                "avg_adverse_excursion",
                "avg_vwap_reversion_ratio",
            ]
        )

    grouped = signals_df.groupby(["edge_family", "side", "horizon_candles"], dropna=False)
    summary = grouped.agg(
        signal_count=("edge_family", "size"),
        avg_return_gross=("future_return_gross", "mean"),
        avg_return_net=("future_return_net", "mean"),
        median_return_net=("future_return_net", "median"),
        avg_future_range_ratio=("future_range_ratio", "mean"),
        avg_favorable_excursion=("favorable_excursion", "mean"),
        avg_adverse_excursion=("adverse_excursion", "mean"),
        avg_vwap_reversion_ratio=("vwap_reversion_ratio", "mean"),
    ).reset_index()
    summary["win_rate_net"] = (
        grouped["future_return_net"].apply(lambda values: (values > 0).mean()).values
    )
    return summary.sort_values(["edge_family", "side", "horizon_candles"]).reset_index(drop=True)


def summarize_edge_frequency(signals_df):
    if signals_df.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "edge_family",
                "side",
                "day",
                "signal_count",
            ]
        )

    working = signals_df.copy()
    working["day"] = pd.to_datetime(working["timestamp"], errors="coerce").dt.date
    return (
        working.groupby(["symbol", "edge_family", "side", "day"], dropna=False)
        .size()
        .reset_index(name="signal_count")
        .sort_values(["symbol", "edge_family", "side", "day"])
        .reset_index(drop=True)
    )


def summarize_edge_overview(signals_df):
    if signals_df.empty:
        return pd.DataFrame(
            [
                {
                    "signal_count": 0,
                    "distinct_days": 0,
                    "avg_signals_per_day": 0.0,
                    "avg_return_net": 0.0,
                }
            ]
        )

    days = pd.to_datetime(signals_df["timestamp"], errors="coerce").dt.date.dropna()
    distinct_days = int(days.nunique()) if not days.empty else 0
    return pd.DataFrame(
        [
            {
                "signal_count": int(len(signals_df)),
                "distinct_days": distinct_days,
                "avg_signals_per_day": float(len(signals_df) / distinct_days) if distinct_days else 0.0,
                "avg_return_net": float(signals_df["future_return_net"].mean()),
            }
        ]
    )


def run_edge_lab(
    *,
    symbols,
    base_path=None,
    start_date=None,
    end_date=None,
    output_dir=None,
    horizons=DEFAULT_HORIZONS,
    round_trip_fee_rate=DEFAULT_ROUND_TRIP_FEE_RATE,
    bucket_min_count=300,
    bucket_min_avg_return_net=0.0,
    config=None,
):
    config = config or AppConfig.load()
    base_path = base_path or config.require("storage", "base_path")
    start_date = start_date or config.require("history", "start_date")
    end_date = end_date or config.require("history", "end_date")
    output_dir = Path(
        output_dir or (config.path("backtest", "output_dir") / "edge_lab")
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    all_signals = []
    for symbol in symbols:
        execution_df = _load_execution_features(
            symbol=symbol,
            base_path=base_path,
            start_date=start_date,
            end_date=end_date,
            config=config,
        )
        signals_df = extract_edge_signals(
            execution_df,
            symbol=symbol,
            horizons=horizons,
            round_trip_fee_rate=round_trip_fee_rate,
            config=config,
        )
        all_signals.append(signals_df)

    signals_df = (
        pd.concat(all_signals, ignore_index=True)
        if all_signals
        else pd.DataFrame()
    )
    summary_df = summarize_edge_signals(signals_df)
    frequency_df = summarize_edge_frequency(signals_df)
    overview_df = summarize_edge_overview(signals_df)
    bucket_summary_df = summarize_edge_buckets(
        signals_df,
        min_count=bucket_min_count,
        min_avg_return_net=bucket_min_avg_return_net,
    )

    signals_path = output_dir / "edge_signals.csv"
    summary_path = output_dir / "edge_summary.csv"
    frequency_path = output_dir / "edge_daily_frequency.csv"
    overview_path = output_dir / "edge_overview.csv"
    bucket_summary_path = output_dir / "edge_bucket_summary.csv"
    edge_table_json_path = output_dir / "edge_table.json"

    signals_df.to_csv(signals_path, index=False)
    summary_df.to_csv(summary_path, index=False)
    frequency_df.to_csv(frequency_path, index=False)
    overview_df.to_csv(overview_path, index=False)
    bucket_summary_df.to_csv(bucket_summary_path, index=False)
    export_edge_table_json(
        bucket_summary_df,
        edge_table_json_path,
        min_count=bucket_min_count,
        min_avg_return_net=bucket_min_avg_return_net,
    )

    return {
        "symbols": list(symbols),
        "signals_path": str(signals_path),
        "summary_path": str(summary_path),
        "frequency_path": str(frequency_path),
        "overview_path": str(overview_path),
        "bucket_summary_path": str(bucket_summary_path),
        "edge_table_json_path": str(edge_table_json_path),
        "signal_count": int(len(signals_df)),
    }
