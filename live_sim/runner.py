"""Runs the near-live simulation loop using recent Binance data and shared strategy components."""

import shutil
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd
from pandas.errors import ParserError

from bias.bias_detector import BiasDetector
from data.binance_client import BinanceClient
from common.debug import configure_debug, debug_print as print
from common.universe import resolve_symbols_from_config
from config import AppConfig
from data.downloader import MarketDataDownloader, fetch_recent, load_from_csv
from data.resampler import TimeframeBuilder
from entry.edge_buckets import build_signal_bucket
from entry.edge_selector import EdgeSelector
from entry.h1_execution import H1ExecutionEngine, build_h1_execution_snapshots
from entry.htf_moonshot import (
    HTFMoonshotEngine,
    HTFStandardEngine,
    build_htf_12h_snapshots,
)
from entry.htf_rotation import (
    HTFRotationEngine,
    build_htf_rotation_snapshots_by_symbol,
)
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

    htf_enabled = bool(
        (
            getter("strategy", "htf_12h_moonshot", "enabled", default=False)
            or getter("strategy", "htf_12h_standard", "enabled", default=False)
        )
        if callable(getter)
        else False
    )
    if htf_enabled:
        htf_breakout_lookback = int(
            getter("strategy", "htf_12h_moonshot", "breakout_lookback", default=20)
            if callable(getter)
            else 20
        )
        htf_daily_breakout_lookback = int(
            getter("strategy", "htf_12h_moonshot", "daily_breakout_lookback", default=20)
            if callable(getter)
            else 20
        )
        htf_weekly_breakout_lookback = int(
            getter("strategy", "htf_12h_moonshot", "weekly_breakout_lookback", default=8)
            if callable(getter)
            else 8
        )
        htf_daily_momentum = int(
            getter("strategy", "htf_12h_moonshot", "daily_momentum_lookback", default=10)
            if callable(getter)
            else 10
        )
        htf_weekly_momentum = int(
            getter("strategy", "htf_12h_moonshot", "weekly_momentum_lookback", default=4)
            if callable(getter)
            else 4
        )
        htf_minutes = max(
            (htf_breakout_lookback + 6) * 12 * 60,
            (htf_daily_breakout_lookback + htf_daily_momentum + 5) * 24 * 60,
            (htf_weekly_breakout_lookback + htf_weekly_momentum + 3) * 7 * 24 * 60,
        )
    else:
        htf_minutes = 0

    rotation_enabled = bool(
        getter("strategy", "htf_12h_rotation", "enabled", default=False)
        if callable(getter)
        else False
    )
    if rotation_enabled:
        rotation_min_history_bars = int(
            getter("strategy", "htf_12h_rotation", "min_history_bars", default=8)
            if callable(getter)
            else 8
        )
        rotation_daily_momentum = int(
            getter("strategy", "htf_12h_rotation", "daily_momentum_lookback", default=10)
            if callable(getter)
            else 10
        )
        rotation_weekly_momentum = int(
            getter("strategy", "htf_12h_rotation", "weekly_momentum_lookback", default=4)
            if callable(getter)
            else 4
        )
        rotation_minutes = max(
            (rotation_min_history_bars + 6) * 12 * 60,
            (rotation_daily_momentum + 10) * 24 * 60,
            (rotation_weekly_momentum + 4) * 7 * 24 * 60,
        )
    else:
        rotation_minutes = 0

    return max(
        execution_bars * execution_minutes,
        direction_bars * direction_minutes,
        trend_bars * trend_minutes,
        macro_bars * macro_minutes,
        swing_minutes,
        htf_minutes,
        rotation_minutes,
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


def _runtime_state_path(symbol, interval, config):
    base_path = Path(config.require("storage", "base_path"))
    folder = base_path / symbol / interval
    return folder / f"{symbol}_{interval}_live_runtime.csv"


def _recover_runtime_state_csv(runtime_path, config):
    try:
        return load_from_csv(runtime_path)
    except ParserError as error:
        print(
            f"Runtime state CSV is malformed and will be recovered: {runtime_path} | "
            f"{error}"
        )
    except ValueError as error:
        print(
            f"Runtime state CSV failed validation and will be recovered: {runtime_path} | "
            f"{error}"
        )

    try:
        repaired = pd.read_csv(
            runtime_path,
            parse_dates=["timestamp"],
            on_bad_lines="skip",
        )
    except Exception as repair_error:
        print(
            f"Runtime state CSV recovery failed while parsing repaired rows: "
            f"{runtime_path} | {repair_error}"
        )
        backup_path = runtime_path.with_name(f"{runtime_path.stem}.corrupt.csv")
        shutil.move(str(runtime_path), str(backup_path))
        print(f"Quarantined corrupt runtime state: {backup_path}")
        return None

    if repaired.empty:
        backup_path = runtime_path.with_name(f"{runtime_path.stem}.corrupt.csv")
        shutil.move(str(runtime_path), str(backup_path))
        print(f"Runtime state contained no salvageable rows. Quarantined: {backup_path}")
        return None

    repaired.set_index("timestamp", inplace=True)
    try:
        repaired = MarketDataDownloader._validate_ohlcv(repaired)
    except Exception as repair_error:
        backup_path = runtime_path.with_name(f"{runtime_path.stem}.corrupt.csv")
        shutil.move(str(runtime_path), str(backup_path))
        print(
            f"Runtime state recovery produced invalid OHLCV rows. Quarantined: "
            f"{backup_path} | {repair_error}"
        )
        return None

    backup_path = runtime_path.with_name(f"{runtime_path.stem}.corrupt.csv")
    shutil.copyfile(runtime_path, backup_path)
    repaired.to_csv(runtime_path, index_label="timestamp")
    print(
        f"Recovered runtime state CSV by skipping malformed rows. "
        f"Backup: {backup_path} | Repaired rows: {len(repaired)}"
    )
    return repaired


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

        overlaps_window = candidate_end >= requested_start and candidate_start <= requested_end
        if overlaps_window:
            candidates.append(
                (
                    candidate_end >= requested_end,
                    candidate_start <= requested_start,
                    candidate_end,
                    -candidate_start.value,
                    candidate,
                )
            )

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][4]


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
    runtime_path = _runtime_state_path(symbol, interval, config)
    if runtime_path.exists():
        runtime_df = _recover_runtime_state_csv(runtime_path, config)
        if runtime_df is not None:
            df_1m = _merge_recent_into_state(df_1m, runtime_df, warmup_minutes)
            return df_1m, runtime_path
    return df_1m, source_path


def _persist_runtime_state(symbol, interval, df_1m, config):
    runtime_path = _runtime_state_path(symbol, interval, config)
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    df_1m.to_csv(runtime_path, index_label="timestamp")
    return runtime_path


def _frame_end_utc_ms(frame):
    if frame is None or frame.empty:
        return None
    latest = pd.Timestamp(frame.index.max())
    if latest.tzinfo is None:
        latest = latest.tz_localize("UTC")
    else:
        latest = latest.tz_convert("UTC")
    return int(latest.timestamp() * 1000)


def _fetch_closed_range(symbol, interval, start_ts, end_ts, config, *, client=None):
    if start_ts is None or end_ts is None or int(start_ts) > int(end_ts):
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    client = client or BinanceClient(config=config)
    limit = int(config.require("binance", "historical_limit"))
    throttle = float(config.require("binance", "throttle_seconds"))
    closed_only = bool(config.require("binance", "closed_klines_only"))
    frames = []
    cursor = int(start_ts)

    while cursor <= int(end_ts):
        raw = client.get_klines(
            symbol=symbol,
            interval=interval,
            startTime=cursor,
            endTime=int(end_ts),
            limit=limit,
            verbose=True,
        )
        if not raw:
            break

        frame = MarketDataDownloader.klines_to_df(raw, closed_only=closed_only)
        if frame.empty:
            break

        frames.append(frame)
        latest_ms = MarketDataDownloader._to_utc_ms(frame.index.max())
        next_cursor = latest_ms + 60_000
        if next_cursor <= cursor:
            break

        cursor = next_cursor
        if throttle > 0:
            time.sleep(throttle)

    if not frames:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    combined = pd.concat(frames)
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    return combined


def _catch_up_live_state(symbol, interval, df_1m_state, warmup_minutes, config, *, client=None):
    latest_ms = _frame_end_utc_ms(df_1m_state)
    if latest_ms is None:
        return df_1m_state

    catchup_end = pd.Timestamp.utcnow().floor("min") - pd.Timedelta(minutes=1)
    catchup_end_ms = int(catchup_end.timestamp() * 1000)
    if latest_ms >= catchup_end_ms:
        return df_1m_state

    catchup_end_label = catchup_end if catchup_end.tzinfo is not None else catchup_end.tz_localize("UTC")
    print(
        f"Catching up {symbol} live state from "
        f"{pd.Timestamp(latest_ms, unit='ms', tz='UTC')} to {catchup_end_label}"
    )
    catchup = _fetch_closed_range(
        symbol=symbol,
        interval=interval,
        start_ts=latest_ms + 60_000,
        end_ts=catchup_end_ms,
        config=config,
        client=client,
    )
    if catchup.empty:
        return df_1m_state

    return _merge_recent_into_state(df_1m_state, catchup, warmup_minutes)


def _discover_live_symbols(config):
    configured = resolve_symbols_from_config(
        config,
        explicit_paths=[("live_sim", "universe", "symbols")],
        active_name_paths=[
            ("live_sim", "universe", "active_set"),
            ("backtest", "portfolio_replay", "universe_name"),
            ("universe", "active_set"),
        ],
    )
    if configured:
        return configured

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
    getter = getattr(config, "get", None)
    macro_rule = (
        getter("timeframes", "macro", "rule", default="12h")
        if callable(getter)
        else "12h"
    )

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


def _frame_latest_timestamp(frame):
    if frame is None or frame.empty:
        return None
    return str(pd.Timestamp(frame.index.max()))


def _build_symbol_pipeline_rows(
    *,
    symbols,
    execution_frames,
    direction_frames,
    trend_frames,
    macro_frames,
    daily_frames,
    states,
    recent_row_counts,
    recent_timestamps,
    new_symbols_by_name,
    momentum_ranks,
    top_symbols,
    candidate_counts_by_symbol,
    candidate_strategies_by_symbol,
):
    top_symbol_set = set(top_symbols or [])
    rows = []
    for symbol in symbols:
        rows.append(
            {
                "symbol": symbol,
                "recent_rows_1m": int(recent_row_counts.get(symbol, 0)),
                "state_rows_1m": int(len(states.get(symbol, []))),
                "latest_recent_1m_timestamp": recent_timestamps.get(symbol),
                "latest_15m_timestamp": _frame_latest_timestamp(execution_frames.get(symbol)),
                "latest_1h_timestamp": _frame_latest_timestamp(direction_frames.get(symbol)),
                "latest_6h_timestamp": _frame_latest_timestamp(trend_frames.get(symbol)),
                "latest_12h_timestamp": _frame_latest_timestamp(macro_frames.get(symbol)),
                "latest_1d_timestamp": _frame_latest_timestamp(daily_frames.get(symbol)),
                "new_15m_candle": symbol in new_symbols_by_name,
                "candidate_count": int(candidate_counts_by_symbol.get(symbol, 0)),
                "candidate_strategies": ",".join(sorted(candidate_strategies_by_symbol.get(symbol, set()))),
                "top_mover": symbol in top_symbol_set,
                "momentum_rank": float(momentum_ranks.get(symbol, 0.0)),
            }
        )
    return rows


def _build_engine_heartbeat(
    *,
    cycle_count,
    cycle_started_at,
    cycle_completed_at,
    cycle_duration_seconds,
    poll_seconds,
    symbols,
    states,
    recent_row_counts,
    recent_timestamps,
    new_symbols,
    candidates,
    selection_summary,
    top_symbols,
    portfolio,
    status,
):
    latest_recent_timestamp = None
    recent_values = [value for value in recent_timestamps.values() if value]
    if recent_values:
        latest_recent_timestamp = max(recent_values)
    return {
        "cycle_count": int(cycle_count),
        "status": str(status),
        "cycle_started_at": str(pd.Timestamp(cycle_started_at)),
        "cycle_completed_at": str(pd.Timestamp(cycle_completed_at)),
        "cycle_duration_seconds": float(cycle_duration_seconds),
        "poll_seconds": float(poll_seconds),
        "symbol_count": int(len(symbols)),
        "symbols_with_recent_fetch": int(sum(1 for count in recent_row_counts.values() if count > 0)),
        "total_recent_1m_rows": int(sum(recent_row_counts.values())),
        "total_state_1m_rows": int(sum(len(frame) for frame in states.values())),
        "latest_recent_1m_timestamp": latest_recent_timestamp,
        "new_15m_symbol_count": int(len(new_symbols)),
        "new_15m_symbols": [item["symbol"] for item in new_symbols],
        "candidates_built": int(len(candidates)),
        "eligible_candidates": int(selection_summary.get("eligible_candidates", 0)),
        "allocated_candidates": int(selection_summary.get("allocated_candidates", 0)),
        "opened_count": int(selection_summary.get("opened_count", 0)),
        "opened_by_strategy": dict(selection_summary.get("opened_by_strategy", {})),
        "selection_reason_counts": dict(selection_summary.get("final_reason_counts", {})),
        "top_symbols": list(top_symbols or []),
        "portfolio_open_positions": int(len(getattr(portfolio, "open_positions", []))),
        "equity": float(getattr(portfolio.account, "equity", 0.0)),
    }


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
        df_15m, df_1h, df_5h, df_12h, df_1d, df_1w = _build_live_timeframes(
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
    h1_snapshot=None,
    h1_engine=None,
    htf_snapshot=None,
    htf_standard_engine=None,
    htf_engine=None,
    htf_rotation_snapshot=None,
    htf_rotation_engine=None,
    config,
):
    bias_snapshot = bias_detector.get_bias_snapshot(df_1h)
    bias = str(bias_snapshot.get("label", "neutral"))
    candidates = []
    bucket = build_signal_bucket(row, bias=bias, side="long", config=config)
    if bucket is not None:
        getter = getattr(config, "get", None)
        allowed_edge_types = (
            getter("live_sim", "paper_portfolio", "allowed_edge_types", default=["impulse_breakout"])
            if callable(getter)
            else ["impulse_breakout"]
        )
        if not allowed_edge_types or bucket["edge_type"] in {str(item) for item in allowed_edge_types}:
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
                "htf_context_1d": (
                    str((htf_snapshot or {}).get("htf_context_1d", "neutral") or "neutral")
                    if htf_snapshot is not None
                    else "neutral"
                ),
                "htf_context_1w": (
                    str((htf_snapshot or {}).get("htf_context_1w", "neutral") or "neutral")
                    if htf_snapshot is not None
                    else "neutral"
                ),
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
            candidates.append(
                moonshot_overlay.apply_to_candidate(candidate, swing_snapshot=swing_snapshot)
            )
    if htf_standard_engine is not None:
        htf_standard_candidate = htf_standard_engine.build_candidate(
            symbol=symbol,
            timestamp=row.name,
            execution_row=row,
            snapshot=htf_snapshot or {},
            momentum_rank=momentum_rank,
            top_symbols=top_symbols,
        )
        if htf_standard_candidate is not None:
            candidates.append(htf_standard_candidate)
    if h1_engine is not None:
        h1_runtime_policy_state = None
        runtime_policy_resolver = getattr(portfolio, "strategy_runtime_policy_state", None)
        if callable(runtime_policy_resolver):
            h1_runtime_policy_state = runtime_policy_resolver(
                "h1_execution",
                getattr(h1_engine, "runtime_policy_guard", None),
            )
        h1_candidate = h1_engine.build_candidate(
            symbol=symbol,
            timestamp=row.name,
            execution_row=row,
            snapshot=h1_snapshot or {},
            momentum_rank=momentum_rank,
            top_symbols=top_symbols,
            runtime_policy_state=h1_runtime_policy_state,
        )
        if h1_candidate is not None:
            candidates.append(h1_candidate)
    if htf_engine is not None:
        htf_candidate = htf_engine.build_candidate(
            symbol=symbol,
            timestamp=row.name,
            execution_row=row,
            snapshot=htf_snapshot or {},
            momentum_rank=momentum_rank,
            top_symbols=top_symbols,
        )
        if htf_candidate is not None:
            candidates.append(htf_candidate)
    if htf_rotation_engine is not None:
        rotation_candidate = htf_rotation_engine.build_candidate(
            symbol=symbol,
            timestamp=row.name,
            execution_row=row,
            snapshot=htf_rotation_snapshot or {},
            momentum_rank=momentum_rank,
            top_symbols=top_symbols,
        )
        if rotation_candidate is not None:
            candidates.append(rotation_candidate)
    return [item for item in candidates if item is not None]


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
    binance_client = BinanceClient(config=config)
    persisted_state_timestamps = {}
    for symbol in symbols:
        df_1m_state, source_path = _load_live_bootstrap_history(
            symbol=symbol,
            interval=interval,
            warmup_minutes=warmup_minutes,
            config=config,
        )
        df_1m_state = _catch_up_live_state(
            symbol=symbol,
            interval=interval,
            df_1m_state=df_1m_state,
            warmup_minutes=warmup_minutes,
            config=config,
            client=binance_client,
        )
        states[symbol] = df_1m_state
        runtime_path = _persist_runtime_state(symbol, interval, df_1m_state, config)
        persisted_state_timestamps[symbol] = _frame_end_utc_ms(df_1m_state)
        print(f"Loaded {symbol} bootstrap source: {source_path}")
        print(f"Persisted runtime state: {runtime_path}")

    builder = TimeframeBuilder(config=config)
    bias_detector = BiasDetector(config=config)
    edge_selector = EdgeSelector(config=config)
    moonshot_overlay = MoonshotOverlay(config=config)
    h1_engine = H1ExecutionEngine(config=config)
    htf_standard_engine = HTFStandardEngine(config=config)
    htf_engine = HTFMoonshotEngine(config=config)
    htf_rotation_engine = HTFRotationEngine(config=config)
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
        cycle_started_at = pd.Timestamp.utcnow()
        execution_frames = {}
        direction_frames = {}
        trend_frames = {}
        swing_snapshots = {}
        h1_snapshots = {}
        htf_snapshots = {}
        htf_macro_frames = {}
        htf_daily_frames = {}
        htf_weekly_frames = {}
        latest_rows_by_symbol = {}
        latest_htf_context_by_symbol = {}
        new_symbols = []
        recent_row_counts = {}
        recent_timestamps = {}

        for index, symbol in enumerate(symbols):
            print(f"\nFetching latest 1m data for {symbol}...")
            df_recent = fetch_recent(symbol=symbol, interval=interval, limit=recent_limit)
            recent_row_counts[symbol] = int(len(df_recent))
            recent_timestamps[symbol] = _frame_latest_timestamp(df_recent)
            states[symbol] = _merge_recent_into_state(
                df_existing=states[symbol],
                df_recent=df_recent,
                warmup_minutes=warmup_minutes,
            )
            latest_state_ms = _frame_end_utc_ms(states[symbol])
            if latest_state_ms and latest_state_ms > int(persisted_state_timestamps.get(symbol, 0) or 0):
                _persist_runtime_state(symbol, interval, states[symbol], config)
                persisted_state_timestamps[symbol] = latest_state_ms
            df_15m, df_1h, df_5h, df_12h, df_1d, df_1w = _build_live_timeframes(
                states[symbol],
                builder=builder,
                config=config,
            )
            execution_frames[symbol] = df_15m
            direction_frames[symbol] = df_1h
            trend_frames[symbol] = df_5h
            htf_macro_frames[symbol] = df_12h
            htf_daily_frames[symbol] = df_1d
            htf_weekly_frames[symbol] = df_1w
            swing_snapshots[symbol] = build_swing_snapshots(
                df_15m.index,
                df_1d,
                df_1w,
                config=config,
            )
            h1_snapshots[symbol] = build_h1_execution_snapshots(
                df_15m.index,
                df_1h,
                df_5h,
                df_12h,
                config=config,
            )
            htf_snapshots[symbol] = build_htf_12h_snapshots(
                df_15m.index,
                df_12h,
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
                latest_htf_context_by_symbol[symbol] = (
                    htf_snapshots[symbol].loc[row.name].to_dict()
                    if row.name in htf_snapshots[symbol].index
                    else {}
                )
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
                        "h1_snapshot": (
                            h1_snapshots[symbol].loc[row.name].to_dict()
                            if row.name in h1_snapshots[symbol].index
                            else {}
                        ),
                        "htf_snapshot": latest_htf_context_by_symbol[symbol],
                    }
                )

            if fetch_pause_seconds > 0 and index < len(symbols) - 1:
                time.sleep(fetch_pause_seconds)

        htf_rotation_snapshots = build_htf_rotation_snapshots_by_symbol(
            {symbol: frame.index for symbol, frame in execution_frames.items()},
            htf_macro_frames,
            htf_daily_frames,
            htf_weekly_frames,
            structural_snapshots_by_symbol=htf_snapshots,
            config=config,
        )
        momentum_ranks, top_symbols = _momentum_ranks(
            execution_frames,
            lookback_bars=momentum_lookback_bars,
        )
        candidates = []
        selection_summary = {
            "eligible_candidates": 0,
            "allocated_candidates": 0,
            "opened_count": 0,
            "opened_by_strategy": {},
            "final_reason_counts": {},
        }
        status = "waiting_for_new_15m"

        if new_symbols:
            timestamp = max(item["row"].name for item in new_symbols)
            portfolio.reset_daily_state_if_needed(timestamp)
            portfolio.manage_open_positions(
                latest_rows_by_symbol,
                htf_context_by_symbol=latest_htf_context_by_symbol,
            )
            for item in new_symbols:
                if item["df_1h"].empty or item["df_5h"].empty or item["df_12h"].empty:
                    continue
                symbol_candidates = _build_live_candidate(
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
                    h1_snapshot=item.get("h1_snapshot"),
                    h1_engine=h1_engine,
                    htf_snapshot=item.get("htf_snapshot"),
                    htf_standard_engine=htf_standard_engine,
                    htf_engine=htf_engine,
                    htf_rotation_snapshot=(
                        htf_rotation_snapshots[item["symbol"]].loc[item["row"].name].to_dict()
                        if item["row"].name in htf_rotation_snapshots[item["symbol"]].index
                        else {}
                    ),
                    htf_rotation_engine=htf_rotation_engine,
                    config=config,
                )
                candidates.extend(symbol_candidates)

            if candidates:
                selection_summary = portfolio.select_and_open(candidates, timestamp) or selection_summary
                status = "routed_candidates"
            else:
                print("No live paper candidates qualified on this 15m step")
                portfolio.flush_state()
                status = "evaluated_no_candidates"
        else:
            print("No new 15m candle across the universe yet")
            portfolio.flush_state()

        candidate_counts_by_symbol = defaultdict(int)
        candidate_strategies_by_symbol = defaultdict(set)
        for candidate in candidates:
            symbol_key = str(candidate.get("symbol", ""))
            if not symbol_key:
                continue
            candidate_counts_by_symbol[symbol_key] += 1
            strategy_name = str(candidate.get("strategy_type", ""))
            if strategy_name:
                candidate_strategies_by_symbol[symbol_key].add(strategy_name)
        new_symbols_by_name = {item["symbol"] for item in new_symbols}
        symbol_pipeline_rows = _build_symbol_pipeline_rows(
            symbols=symbols,
            execution_frames=execution_frames,
            direction_frames=direction_frames,
            trend_frames=trend_frames,
            macro_frames=htf_macro_frames,
            daily_frames=htf_daily_frames,
            states=states,
            recent_row_counts=recent_row_counts,
            recent_timestamps=recent_timestamps,
            new_symbols_by_name=new_symbols_by_name,
            momentum_ranks=momentum_ranks,
            top_symbols=top_symbols,
            candidate_counts_by_symbol=candidate_counts_by_symbol,
            candidate_strategies_by_symbol=candidate_strategies_by_symbol,
        )
        cycle_time = time.time() - cycle_start
        cycle_completed_at = pd.Timestamp.utcnow()
        engine_heartbeat = _build_engine_heartbeat(
            cycle_count=cycle_count,
            cycle_started_at=cycle_started_at,
            cycle_completed_at=cycle_completed_at,
            cycle_duration_seconds=cycle_time,
            poll_seconds=poll_seconds,
            symbols=symbols,
            states=states,
            recent_row_counts=recent_row_counts,
            recent_timestamps=recent_timestamps,
            new_symbols=new_symbols,
            candidates=candidates,
            selection_summary=selection_summary,
            top_symbols=top_symbols,
            portfolio=portfolio,
            status=status,
        )
        portfolio.state_logger.write_engine_heartbeat(engine_heartbeat)
        portfolio.state_logger.append_engine_cycle(engine_heartbeat)
        portfolio.state_logger.write_symbol_pipeline_status(symbol_pipeline_rows)
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
