"""Runs the near-live simulation loop using recent Binance data and shared strategy components."""

import time
from pathlib import Path

import pandas as pd

from bias.bias_detector import BiasDetector
from common.debug import configure_debug, debug_print as print
from config import AppConfig
from data.downloader import fetch_recent, load_from_csv
from data.resampler import TimeframeBuilder
from entry.edge_buckets import build_signal_bucket
from entry.edge_selector import EdgeSelector
from entry.moonshot import MoonshotOverlay, build_swing_snapshots
from features.feature_pipeline import compute_features
from live_sim.candle_clock import is_new_15m_candle
from live_sim.logger import (
    LivePortfolioStateLogger,
    LiveSignalLogger,
    LiveTradeLogger,
)
from live_sim.paper_portfolio import LivePaperPortfolio
from simulation.simulator import Simulator


def _parse_storage_timestamp(value):
    return pd.Timestamp(str(value).replace("T", " ").replace(".", ":"))


def _extract_period_from_column(column_name, fallback):
    digits = "".join(character for character in str(column_name) if character.isdigit())
    return int(digits) if digits else fallback


def _required_live_warmup_minutes(config):
    fast_ema_period = config.require("features", "ema_periods", "fast")
    slow_ema_period = config.require("features", "ema_periods", "slow")
    high_period = config.require("features", "structure", "high_period")
    low_period = config.require("features", "structure", "low_period")
    slow_range_period = config.require("features", "compression", "slow_range_period")
    average_body_period = config.require("features", "candle_metrics", "average_body_period")
    bias_ema_period = _extract_period_from_column(
        config.require("strategy", "bias", "ema_column"),
        fallback=slow_ema_period,
    )
    regime_ema_period = _extract_period_from_column(
        config.require("strategy", "regime", "ema_column"),
        fallback=slow_ema_period,
    )
    bias_slope_lookback = config.require("strategy", "bias", "slope_lookback")
    regime_slope_lookback = config.require("strategy", "regime", "slope_lookback")
    execution_rule = config.require("timeframes", "execution", "rule")
    direction_rule = config.require("timeframes", "direction", "rule")
    trend_rule = config.require("timeframes", "trend", "rule")
    macro_rule = config.require("timeframes", "macro", "rule")

    shared_feature_bars = max(
        fast_ema_period,
        slow_ema_period,
        high_period + 1,
        low_period,
        slow_range_period,
        average_body_period,
    )
    buffer_bars = 10

    execution_bars = shared_feature_bars + buffer_bars
    direction_bars = max(shared_feature_bars, bias_ema_period) + bias_slope_lookback + buffer_bars
    trend_bars = max(shared_feature_bars, regime_ema_period) + buffer_bars
    macro_bars = max(shared_feature_bars, regime_ema_period) + regime_slope_lookback + buffer_bars

    execution_minutes = int(pd.Timedelta(execution_rule).total_seconds() // 60)
    direction_minutes = int(pd.Timedelta(direction_rule).total_seconds() // 60)
    trend_minutes = int(pd.Timedelta(trend_rule).total_seconds() // 60)
    macro_minutes = int(pd.Timedelta(macro_rule).total_seconds() // 60)
    getter = getattr(config, "get", None)
    moonshot_enabled = bool(
        getter("strategy", "moonshots", "enabled", default=False)
        if callable(getter)
        else False
    )
    if moonshot_enabled:
        swing_daily_lookback = int(
            getter("strategy", "moonshots", "swing", "daily_breakout_lookback", default=20)
            if callable(getter)
            else 20
        )
        swing_weekly_lookback = int(
            getter("strategy", "moonshots", "swing", "weekly_breakout_lookback", default=8)
            if callable(getter)
            else 8
        )
        swing_daily_momentum = int(
            getter("strategy", "moonshots", "swing", "daily_momentum_lookback", default=10)
            if callable(getter)
            else 10
        )
        swing_weekly_momentum = int(
            getter("strategy", "moonshots", "swing", "weekly_momentum_lookback", default=4)
            if callable(getter)
            else 4
        )
        swing_minutes = max(
            (swing_daily_lookback + swing_daily_momentum + 5) * 24 * 60,
            (swing_weekly_lookback + swing_weekly_momentum + 2) * 7 * 24 * 60,
        )
    else:
        swing_minutes = 0

    return max(
        execution_bars * execution_minutes,
        direction_bars * direction_minutes,
        trend_bars * trend_minutes,
        macro_bars * macro_minutes,
        swing_minutes,
    )


def _trim_live_window(df_1m, warmup_minutes):
    if df_1m.empty:
        return df_1m

    cutoff = df_1m.index.max() - pd.Timedelta(minutes=warmup_minutes)
    trimmed = df_1m.loc[df_1m.index >= cutoff].copy()
    trimmed = trimmed[~trimmed.index.duplicated(keep="last")].sort_index()
    return trimmed


def _merge_recent_into_state(df_existing, df_recent, warmup_minutes):
    combined = pd.concat([df_existing, df_recent])
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    return _trim_live_window(combined, warmup_minutes)


def _bootstrap_history_paths(symbol, interval, config):
    base_path = Path(config.require("storage", "base_path"))
    start_date = config.require("history", "start_date")
    end_date = config.require("history", "end_date")
    partial_suffix = config.require("downloads", "history")["partial_suffix"]
    folder = base_path / symbol / interval
    filename = f"{symbol}_{interval}_{start_date}_to_{end_date}.csv"
    final_path = folder / filename
    partial_path = folder / f"{filename}{partial_suffix}"
    return final_path, partial_path


def _resolve_live_history_file(folder, symbol, interval, start_date, end_date):
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


def _load_live_bootstrap_history(symbol, interval, warmup_minutes, config):
    final_path, partial_path = _bootstrap_history_paths(symbol, interval, config)
    start_date = config.require("history", "start_date")
    end_date = config.require("history", "end_date")
    history_folder = final_path.parent

    if final_path.exists():
        source_path = final_path
    elif partial_path.exists():
        source_path = partial_path
    elif (resolved := _resolve_live_history_file(history_folder, symbol, interval, start_date, end_date)) is not None:
        source_path = resolved
    else:
        raise FileNotFoundError(
            "Live simulation requires local 1m bootstrap history. "
            f"Expected either {final_path} or {partial_path}. "
            "Run `python main_download.py` first."
        )

    df_1m = load_from_csv(source_path)
    df_1m = _trim_live_window(df_1m, warmup_minutes)
    return df_1m, source_path


def _discover_live_symbols(config):
    getter = getattr(config, "get", None)
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


def _build_live_timeframes(df_1m, builder, config):
    execution_rule = config.require("timeframes", "execution", "rule")
    direction_rule = config.require("timeframes", "direction", "rule")
    trend_rule = config.require("timeframes", "trend", "rule")
    macro_rule = config.require("timeframes", "macro", "rule")

    df_15m = builder.resample(df_1m, execution_rule)
    df_1h = builder.resample(df_1m, direction_rule)
    df_5h = builder.resample(df_1m, trend_rule)
    df_12h = builder.resample(df_1m, macro_rule)
    df_1d = builder.resample(df_1m, "1D")
    df_1w = builder.resample(df_1m, "1W")

    df_15m = compute_features(df_15m, config=config)
    df_1h = compute_features(df_1h, config=config)
    df_5h = compute_features(df_5h, config=config)
    df_12h = compute_features(df_12h, config=config)
    df_1d = compute_features(df_1d, config=config)
    df_1w = compute_features(df_1w, config=config)
    return df_15m, df_1h, df_5h, df_12h, df_1d, df_1w


def _momentum_ranks(execution_frames, lookback_bars):
    scores = {}
    for symbol, df_15m in execution_frames.items():
        if len(df_15m) <= lookback_bars:
            continue
        current_close = float(df_15m["close"].iloc[-1])
        prior_close = float(df_15m["close"].iloc[-1 - lookback_bars])
        if prior_close == 0:
            continue
        scores[symbol] = (current_close / prior_close) - 1.0

    if not scores:
        return {}, []

    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    total = max(1, len(ordered) - 1)
    ranks = {}
    for index, (symbol, _) in enumerate(ordered):
        ranks[symbol] = 1.0 - (index / total) if total else 1.0
    top_symbols = [symbol for symbol, _ in ordered[: max(1, min(3, len(ordered)))]]
    return ranks, top_symbols


def _run_single_symbol_live_sim(symbol=None, config=None):
    config = config or AppConfig.load()
    configure_debug(config=config)
    symbol = symbol or config.require("app", "default_symbol")
    interval = config.require("binance", "default_interval")
    recent_limit = config.require("binance", "recent_limit")
    poll_seconds = config.require("live_sim", "poll_seconds")
    warmup_minutes = _required_live_warmup_minutes(config)

    print("\nSTARTING LIVE SIMULATION\n")
    print(
        "Bootstrapping live state from local 1m history "
        f"with ~{warmup_minutes / (60 * 24):.1f} days of warmup"
    )

    sim = Simulator(
        trade_logger=LiveTradeLogger(config=config),
        config=config
    )

    last_candle_time = None
    df_1m_state, source_path = _load_live_bootstrap_history(
        symbol=symbol,
        interval=interval,
        warmup_minutes=warmup_minutes,
        config=config,
    )

    print(f"Loaded live bootstrap source: {source_path}")
    print(f"Bootstrap rows retained in memory: {len(df_1m_state)}")
    builder = TimeframeBuilder(config=config)

    while True:
        cycle_start = time.time()

        print("\nFetching latest 1m data...")
        df_recent = fetch_recent(
            symbol=symbol,
            interval=interval,
            limit=recent_limit
        )
        df_1m_state = _merge_recent_into_state(
            df_existing=df_1m_state,
            df_recent=df_recent,
            warmup_minutes=warmup_minutes,
        )

        print("Building timeframes...")
        df_15m, df_1h, df_5h, df_12h = _build_live_timeframes(
            df_1m_state,
            builder=builder,
            config=config,
        )

        is_new, last_candle_time = is_new_15m_candle(df_15m, last_candle_time)
        if is_new:
            print("\nNew 15m candle detected -> running strategy")
            row = df_15m.iloc[-1]
            df_1h_context = df_1h.loc[:row.name]
            df_5h_context = df_5h.loc[:row.name]
            df_12h_context = df_12h.loc[:row.name]
            if df_1h_context.empty or df_5h_context.empty or df_12h_context.empty:
                print("Waiting for higher-timeframe candles to close before strategy run")
                continue
            sim.step(row, df_1h_context, df_5h_context, df_12h_context)
        else:
            print("No new 15m candle yet")

        cycle_time = time.time() - cycle_start
        print(f"\nTime: Cycle completed in {cycle_time:.2f}s")
        time.sleep(poll_seconds)


def _build_live_candidate(
    *,
    symbol,
    row,
    df_1h,
    momentum_rank,
    top_symbols,
    bias_detector,
    edge_selector,
    moonshot_overlay,
    portfolio,
    swing_snapshot=None,
    config,
):
    bias_snapshot = bias_detector.get_bias_snapshot(df_1h)
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

    candidate = {
        "symbol": symbol,
        "timestamp": row.name,
        "side": "long",
        "row": row,
        "bias": bias,
        "bias_snapshot": bias_snapshot,
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
        "selection_score": float(score_info["score"]),
        "strategy_type": "core",
        "signal_family": "live_paper",
        "risk_group": "core",
        "moonshot_score": None,
        "range_expansion_factor": float(row.get("range_expansion_factor", 0.0) or 0.0),
        "execution_profile": {},
        "feature_values": {
            "body_strength": score_info["components"]["body_strength"],
            "close_position": score_info["components"]["close_position"],
            "vwap_score": score_info["components"]["vwap_score"],
            "momentum": score_info["components"]["momentum"],
        },
    }
    return moonshot_overlay.apply_to_candidate(candidate, swing_snapshot=swing_snapshot)


def _run_portfolio_live_paper_sim(config=None):
    config = config or AppConfig.load()
    configure_debug(config=config)
    interval = config.require("binance", "default_interval")
    recent_limit = config.require("binance", "recent_limit")
    poll_seconds = config.require("live_sim", "poll_seconds")
    getter = getattr(config, "get", None)
    max_cycles = (
        getter("live_sim", "max_cycles", default=None)
        if callable(getter)
        else None
    )
    fetch_pause_seconds = float(
        getter("live_sim", "universe", "fetch_pause_seconds", default=0.0)
        if callable(getter)
        else 0.0
    )
    momentum_lookback_bars = int(
        getter("live_sim", "universe", "momentum_lookback_bars", default=4)
        if callable(getter)
        else 4
    )

    warmup_minutes = _required_live_warmup_minutes(config)
    symbols = _discover_live_symbols(config)
    print("\nSTARTING LIVE PAPER PORTFOLIO\n")
    print(f"Universe: {', '.join(symbols)}")
    print(
        "Bootstrapping live state from local 1m history "
        f"with ~{warmup_minutes / (60 * 24):.1f} days of warmup"
    )

    states = {}
    for symbol in symbols:
        df_1m_state, source_path = _load_live_bootstrap_history(
            symbol=symbol,
            interval=interval,
            warmup_minutes=warmup_minutes,
            config=config,
        )
        states[symbol] = df_1m_state
        print(f"Loaded {symbol} bootstrap source: {source_path}")

    builder = TimeframeBuilder(config=config)
    bias_detector = BiasDetector(config=config)
    edge_selector = EdgeSelector(config=config)
    moonshot_overlay = MoonshotOverlay(config=config)
    portfolio = LivePaperPortfolio(
        trade_logger=LiveTradeLogger(config=config),
        signal_logger=LiveSignalLogger(config=config),
        state_logger=LivePortfolioStateLogger(config=config),
        config=config,
    )
    last_candle_times = {symbol: None for symbol in symbols}
    cycle_count = 0

    while True:
        cycle_count += 1
        cycle_start = time.time()
        execution_frames = {}
        swing_snapshots = {}
        latest_rows_by_symbol = {}
        new_symbols = []

        for index, symbol in enumerate(symbols):
            print(f"\nFetching latest 1m data for {symbol}...")
            df_recent = fetch_recent(symbol=symbol, interval=interval, limit=recent_limit)
            states[symbol] = _merge_recent_into_state(
                df_existing=states[symbol],
                df_recent=df_recent,
                warmup_minutes=warmup_minutes,
            )
            df_15m, df_1h, df_5h, df_12h, df_1d, df_1w = _build_live_timeframes(
                states[symbol],
                builder=builder,
                config=config,
            )
            execution_frames[symbol] = df_15m
            swing_snapshots[symbol] = build_swing_snapshots(
                df_15m.index,
                df_1d,
                df_1w,
                config=config,
            )
            is_new, last_candle_times[symbol] = is_new_15m_candle(
                df_15m,
                last_candle_times[symbol],
            )
            if is_new:
                row = df_15m.iloc[-1]
                latest_rows_by_symbol[symbol] = row
                new_symbols.append(
                    {
                        "symbol": symbol,
                        "row": row,
                        "df_1h": df_1h.loc[:row.name],
                        "df_5h": df_5h.loc[:row.name],
                        "df_12h": df_12h.loc[:row.name],
                        "swing_snapshot": (
                            swing_snapshots[symbol].loc[row.name].to_dict()
                            if row.name in swing_snapshots[symbol].index
                            else {}
                        ),
                    }
                )

            if fetch_pause_seconds > 0 and index < len(symbols) - 1:
                time.sleep(fetch_pause_seconds)

        if new_symbols:
            timestamp = max(item["row"].name for item in new_symbols)
            portfolio.reset_daily_state_if_needed(timestamp)
            portfolio.manage_open_positions(latest_rows_by_symbol)
            momentum_ranks, top_symbols = _momentum_ranks(
                execution_frames,
                lookback_bars=momentum_lookback_bars,
            )

            candidates = []
            for item in new_symbols:
                if item["df_1h"].empty or item["df_5h"].empty or item["df_12h"].empty:
                    continue
                candidate = _build_live_candidate(
                    symbol=item["symbol"],
                    row=item["row"],
                    df_1h=item["df_1h"],
                    momentum_rank=momentum_ranks.get(item["symbol"], 0.5),
                    top_symbols=top_symbols,
                    bias_detector=bias_detector,
                    edge_selector=edge_selector,
                    moonshot_overlay=moonshot_overlay,
                    portfolio=portfolio,
                    swing_snapshot=item.get("swing_snapshot"),
                    config=config,
                )
                if candidate is not None:
                    candidates.append(candidate)

            if candidates:
                portfolio.select_and_open(candidates, timestamp)
            else:
                print("No live paper candidates qualified on this 15m step")
                portfolio.flush_state()
        else:
            print("No new 15m candle across the universe yet")
            portfolio.flush_state()

        cycle_time = time.time() - cycle_start
        print(f"\nPortfolio cycle completed in {cycle_time:.2f}s")
        if max_cycles is not None and cycle_count >= int(max_cycles):
            break
        time.sleep(poll_seconds)


def run_live_sim(symbol=None, config=None):
    config = config or AppConfig.load()
    getter = getattr(config, "get", None)
    mode = (
        getter("live_sim", "mode", default="single_symbol")
        if callable(getter)
        else "single_symbol"
    )
    if str(mode).lower() == "portfolio_paper":
        return _run_portfolio_live_paper_sim(config=config)
    return _run_single_symbol_live_sim(symbol=symbol, config=config)


if __name__ == "__main__":
    run_live_sim()
