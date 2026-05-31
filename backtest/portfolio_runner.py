"""Historical multi-asset replay that reuses the live paper-portfolio logic."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from bias.bias_detector import BiasDetector
from common.debug import configure_debug, debug_print as print
from config import AppConfig
from data.downloader import load_from_csv
from data.resampler import TimeframeBuilder
from entry.edge_buckets import build_signal_bucket
from entry.edge_selector import EdgeSelector
from features.feature_pipeline import compute_features
from live_sim.logger import LivePortfolioStateLogger, LiveSignalLogger
from live_sim.paper_portfolio import LivePaperPortfolio
from backtest.equity_logger import EquityLogger
from backtest.logger import TradeLogger


def _parse_storage_timestamp(value):
    return pd.Timestamp(str(value).replace("T", " ").replace(".", ":"))


def _resolve_history_file(folder, symbol, interval, start_date, end_date):
    exact_path = folder / f"{symbol}_{interval}_{start_date}_to_{end_date}.csv"
    if exact_path.exists():
        return exact_path

    requested_start = pd.Timestamp(start_date)
    requested_end = pd.Timestamp(end_date)
    candidates = []
    for candidate in Path(folder).glob(f"{symbol}_{interval}_*.csv"):
        if candidate.name.endswith("_live_runtime.csv"):
            continue

        stem = candidate.stem
        prefix = f"{symbol}_{interval}_"
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
                (candidate_end >= requested_end, candidate_end, -candidate_start.value, candidate)
            )

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][3]


def _load_full_history(symbol, interval, config):
    base_path = Path(config.require("storage", "base_path"))
    start_date = config.require("history", "start_date")
    end_date = config.require("history", "end_date")
    folder = base_path / symbol / interval
    source_path = _resolve_history_file(
        folder,
        symbol=symbol,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
    )
    if source_path is None:
        raise FileNotFoundError(
            f"No local {interval} history found for {symbol} covering "
            f"{start_date} -> {end_date}"
        )

    df_1m = load_from_csv(source_path)
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1)
    df_1m = df_1m.loc[(df_1m.index >= start_ts) & (df_1m.index < end_ts)].copy()
    return df_1m, source_path


def _discover_portfolio_symbols(config):
    getter = getattr(config, "get", None)
    configured = (
        getter("backtest", "portfolio_replay", "symbols", default=None)
        if callable(getter)
        else None
    )
    if configured:
        return [str(symbol).upper() for symbol in configured]

    configured = (
        getter("live_sim", "universe", "symbols", default=None)
        if callable(getter)
        else None
    )
    if configured:
        return [str(symbol).upper() for symbol in configured]

    base_path = Path(config.require("storage", "base_path"))
    if not base_path.exists():
        return [config.require("app", "default_symbol")]

    symbols = sorted(
        path.name.upper()
        for path in base_path.iterdir()
        if path.is_dir()
    )
    return symbols or [config.require("app", "default_symbol")]


def _build_strategy_timeframes(df_1m, config):
    builder = TimeframeBuilder(config=config)
    execution_rule = config.require("timeframes", "execution", "rule")
    direction_rule = config.require("timeframes", "direction", "rule")

    df_15m = builder.resample(df_1m, execution_rule)
    df_1h = builder.resample(df_1m, direction_rule)

    df_15m = compute_features(df_15m, config=config)
    df_1h = compute_features(df_1h, config=config)
    return df_15m, df_1h


def _aligned_bias_snapshots(df_15m, df_1h, detector):
    ema_column = detector.ema_column
    slope_threshold = float(detector.slope_threshold or 0.0)
    scale_distance = max(abs(slope_threshold), 0.001)
    scale_slope = max(abs(slope_threshold), 0.0005)

    ema_series = df_1h[ema_column].astype(float)
    close_series = df_1h["close"].astype(float)
    slope = (ema_series - ema_series.shift(detector.slope_lookback)) / ema_series.shift(
        detector.slope_lookback
    )
    slope = slope.replace([np.inf, -np.inf], 0.0).fillna(0.0)
    price_vs_ema_ratio = ((close_series - ema_series) / ema_series).replace(
        [np.inf, -np.inf],
        0.0,
    ).fillna(0.0)

    bullish = (close_series > ema_series) & (slope > slope_threshold)
    bearish = (close_series < ema_series) & (slope < -slope_threshold)
    labels = np.where(bullish, "bullish", np.where(bearish, "bearish", "neutral"))
    distance_strength = np.tanh(price_vs_ema_ratio / scale_distance)
    slope_strength = np.tanh(slope / scale_slope)
    directional_strength = 0.5 * (distance_strength + slope_strength)

    snapshots = pd.DataFrame(
        {
            "label": labels,
            "price_vs_ema_ratio": price_vs_ema_ratio,
            "ema_slope": slope,
            "directional_strength": directional_strength,
        },
        index=df_1h.index,
    )
    return snapshots.reindex(df_15m.index, method="ffill")


def _build_candidate(
    *,
    symbol,
    row,
    bias_snapshot,
    momentum_rank,
    top_symbols,
    edge_selector,
    portfolio,
    config,
):
    bias = str(bias_snapshot.get("label", "neutral"))
    bucket = build_signal_bucket(row, bias=bias, side="long", config=config)
    if bucket is None:
        return None

    getter = getattr(config, "get", None)
    allowed_edge_types = (
        getter("live_sim", "paper_portfolio", "allowed_edge_types", default=["impulse_breakout"])
        if callable(getter)
        else ["impulse_breakout"]
    )
    if allowed_edge_types and bucket["edge_type"] not in {str(item) for item in allowed_edge_types}:
        return None

    selector_profile = edge_selector.evaluate(row, bias=bias, side="long")
    is_top_mover = symbol in set(top_symbols)
    score_info = portfolio.scorer.compute_score(
        row=row,
        momentum_rank=momentum_rank,
        vwap_bucket=bucket["vwap_bucket"],
        edge_type=bucket["edge_type"],
        is_top_mover=is_top_mover,
    )
    bucket_risk_mult = selector_profile.get("bucket_risk_mult", 1.0) or 1.0

    return {
        "symbol": symbol,
        "timestamp": row.name,
        "side": "long",
        "row": row,
        "bias": bias,
        "bias_snapshot": dict(bias_snapshot),
        "edge_type": bucket["edge_type"],
        "body_bucket": bucket["body_bucket"],
        "vwap_bucket": bucket["vwap_bucket"],
        "bucket_key_text": bucket["bucket_key_text"],
        "bucket_valid": selector_profile.get("bucket_valid"),
        "bucket_expected_return": selector_profile.get("bucket_expected_return"),
        "bucket_risk_mult": bucket_risk_mult,
        "risk_mult": bucket_risk_mult,
        "momentum_rank": float(momentum_rank or 0.0),
        "is_top_mover": is_top_mover,
        "score": float(score_info["score"]),
        "score_bucket": score_info["score_bucket"],
        "feature_values": {
            "body_strength": score_info["components"]["body_strength"],
            "close_position": score_info["components"]["close_position"],
            "vwap_score": score_info["components"]["vwap_score"],
            "momentum": score_info["components"]["momentum"],
        },
    }


def run_portfolio_backtest(config=None):
    config = config or AppConfig.load()
    configure_debug(config=config)

    interval = config.require("binance", "default_interval")
    getter = getattr(config, "get", None)
    close_open_positions = bool(
        getter("backtest", "portfolio_replay", "close_open_positions_at_end", default=True)
        if callable(getter)
        else True
    )
    minimum_execution_bars = int(
        getter("backtest", "portfolio_replay", "minimum_execution_bars", default=50)
        if callable(getter)
        else 50
    )
    momentum_lookback_bars = int(
        getter("live_sim", "universe", "momentum_lookback_bars", default=4)
        if callable(getter)
        else 4
    )
    output_dir = Path(config.require("backtest", "output_dir"))
    signal_log_filename = (
        getter("backtest", "portfolio_replay", "signal_log_filename", default="signals.csv")
        if callable(getter)
        else "signals.csv"
    )

    symbols = _discover_portfolio_symbols(config)
    print("\nSTARTING PORTFOLIO BACKTEST REPLAY\n")
    print(f"Universe: {', '.join(symbols)}")

    execution_frames = {}
    bias_frames = {}
    source_paths = {}
    bias_detector = BiasDetector(config=config)

    for symbol in symbols:
        print(f"\nLoading full history for {symbol}...")
        df_1m, source_path = _load_full_history(symbol, interval, config)
        df_15m, df_1h = _build_strategy_timeframes(df_1m, config=config)
        execution_frames[symbol] = df_15m
        bias_frames[symbol] = _aligned_bias_snapshots(df_15m, df_1h, bias_detector)
        source_paths[symbol] = source_path
        print(f"  Source: {source_path}")
        print(f"  Execution rows: {len(df_15m):,}")

    common_index = sorted(
        set().union(*(frame.index for frame in execution_frames.values()))
    )
    if minimum_execution_bars > 0:
        common_index = common_index[minimum_execution_bars:]

    closes = pd.DataFrame(
        {symbol: frame["close"] for symbol, frame in execution_frames.items()}
    ).sort_index()
    momentum_scores = closes.pct_change(momentum_lookback_bars)
    momentum_ranks = momentum_scores.rank(axis=1, pct=True, ascending=True)

    trade_logger = TradeLogger(config=config, reset=True)
    equity_logger = EquityLogger(config=config, reset=True)
    signal_logger = LiveSignalLogger(
        filepath=str(output_dir / signal_log_filename),
        config=config,
    )
    state_logger = LivePortfolioStateLogger(output_dir=output_dir, config=config)
    portfolio = LivePaperPortfolio(
        trade_logger=trade_logger,
        signal_logger=signal_logger,
        state_logger=state_logger,
        config=config,
    )
    edge_selector = EdgeSelector(config=config)

    latest_rows_by_symbol = {}
    start_time = time.time()

    for step_index, timestamp in enumerate(common_index, start=1):
        portfolio.reset_daily_state_if_needed(timestamp)

        candidates = []
        latest_rows_by_symbol = {}
        rank_row = (
            momentum_ranks.loc[timestamp]
            if timestamp in momentum_ranks.index
            else pd.Series(dtype=float)
        )
        score_row = (
            momentum_scores.loc[timestamp]
            if timestamp in momentum_scores.index
            else pd.Series(dtype=float)
        )
        top_symbols = list(score_row.dropna().sort_values(ascending=False).head(3).index)

        for symbol, df_15m in execution_frames.items():
            if timestamp not in df_15m.index:
                continue

            row = df_15m.loc[timestamp]
            latest_rows_by_symbol[symbol] = row

        if latest_rows_by_symbol:
            portfolio.manage_open_positions(latest_rows_by_symbol)

        for symbol, row in latest_rows_by_symbol.items():
            bias_frame = bias_frames[symbol]
            if timestamp not in bias_frame.index:
                continue
            bias_snapshot = bias_frame.loc[timestamp].to_dict()
            if pd.isna(bias_snapshot.get("label")):
                continue
            candidate = _build_candidate(
                symbol=symbol,
                row=row,
                bias_snapshot=bias_snapshot,
                momentum_rank=float(rank_row.get(symbol, 0.5) or 0.5),
                top_symbols=top_symbols,
                edge_selector=edge_selector,
                portfolio=portfolio,
                config=config,
            )
            if candidate is not None:
                candidates.append(candidate)

        if candidates:
            portfolio.select_and_open(candidates, timestamp)
        else:
            portfolio.flush_state()

        equity_logger.log(timestamp, portfolio.account.equity)

        if step_index == 1 or step_index % 500 == 0 or step_index == len(common_index):
            elapsed = time.time() - start_time
            print(
                "\nPORTFOLIO BACKTEST PROGRESS\n"
                f"  Step: {step_index:,}/{len(common_index):,}\n"
                f"  Candle: {timestamp}\n"
                f"  Equity: {portfolio.account.equity:.2f}\n"
                f"  Open positions: {len(portfolio.open_positions)}\n"
                f"  Entries today: {portfolio.daily_entries_taken}\n"
                f"  Threshold: {portfolio.current_threshold:.2f}\n"
                f"  Elapsed: {elapsed:.2f}s"
            )

    portfolio.finalize_backtest(
        latest_rows_by_symbol=latest_rows_by_symbol,
        close_open_positions=close_open_positions,
    )
    if latest_rows_by_symbol:
        final_timestamp = max(latest_rows_by_symbol.values(), key=lambda row: row.name).name
        equity_logger.log(final_timestamp, portfolio.account.equity)

    portfolio.backtest_completed = True
    portfolio.source_paths = source_paths
    return portfolio
