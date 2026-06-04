"""Historical multi-asset replay that reuses the live paper-portfolio logic."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
import json

import numpy as np
import pandas as pd

from backtest.checkpoint import BacktestCheckpointStore
from bias.bias_detector import BiasDetector
from common.debug import configure_debug, debug_print as print
from common.universe import resolve_symbols_from_config
from config import AppConfig
from data.downloader import load_from_csv
from data.resampler import TimeframeBuilder
from entry.edge_buckets import build_signal_bucket
from entry.edge_selector import EdgeSelector
from entry.htf_moonshot import HTFMoonshotEngine, build_htf_12h_snapshots
from entry.htf_rotation import (
    HTFRotationEngine,
    build_htf_rotation_snapshots_by_symbol,
)
from entry.moonshot import MoonshotOverlay, build_swing_snapshots
from entry.opportunity_ranking import OpportunityScorer
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
    configured = resolve_symbols_from_config(
        config,
        explicit_paths=[
            ("backtest", "portfolio_replay", "symbols"),
            ("live_sim", "universe", "symbols"),
        ],
        active_name_paths=[
            ("backtest", "portfolio_replay", "universe_name"),
            ("live_sim", "universe", "active_set"),
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


def _build_checkpoint_store(config, output_dir, symbols):
    if not config.get("backtest", "resume_enabled", default=True):
        return None

    checkpoint_dir_value = config.get("backtest", "checkpoint_dir", default="_checkpoints")
    output_dir = Path(output_dir).expanduser().resolve()
    checkpoint_dir = Path(checkpoint_dir_value)
    if not checkpoint_dir.is_absolute():
        checkpoint_dir = output_dir / checkpoint_dir

    suffix = config.get("backtest", "checkpoint_suffix", default=".checkpoint.json")
    start_date = config.require("history", "start_date")
    end_date = config.require("history", "end_date")
    symbol_key = f"{len(symbols)}symbols"
    digest_source = "|".join(
        [str(output_dir), symbol_key, str(start_date), str(end_date), *[str(symbol).upper() for symbol in symbols]]
    )
    digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:12]
    filename = f"portfolio_replay_{symbol_key}_{start_date}_to_{end_date}{suffix}"
    checkpoint_path = (checkpoint_dir / filename).expanduser().resolve()
    if len(str(checkpoint_path.with_name(f"{checkpoint_path.name}.tmp"))) >= 240:
        compact_start = str(start_date).replace("-", "")
        compact_end = str(end_date).replace("-", "")
        checkpoint_dir = output_dir.parent / "_checkpoints"
        checkpoint_path = checkpoint_dir / f"pr_{symbol_key}_{compact_start}_{compact_end}_{digest}{suffix}"
    return BacktestCheckpointStore(checkpoint_path)


def _resume_metadata(config, symbols):
    return {
        "mode": "portfolio_replay",
        "symbols": [str(symbol).upper() for symbol in symbols],
        "start_date": config.require("history", "start_date"),
        "end_date": config.require("history", "end_date"),
        "interval": config.require("binance", "default_interval"),
    }


def _resume_metadata_matches(payload, expected_metadata):
    if not payload:
        return False

    metadata = payload.get("metadata", {}) or {}
    return all(metadata.get(key) == value for key, value in expected_metadata.items())


def _payload_next_index(payload):
    if not payload:
        return -1
    try:
        return int(payload.get("next_index", -1) or -1)
    except (TypeError, ValueError):
        return -1


def _load_existing_rows(path):
    path = Path(path)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _safe_float(value, default=0.0):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float(default)

    if pd.isna(numeric):
        return float(default)
    return numeric


def _load_equity_rows(path):
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=["timestamp", "equity"])

    frame = pd.read_csv(
        path,
        usecols=["timestamp", "equity"],
        on_bad_lines="skip",
        engine="python",
    )
    if "timestamp" in frame.columns:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
        frame["equity"] = pd.to_numeric(frame["equity"], errors="coerce")
        frame = (
            frame.dropna(subset=["timestamp", "equity"])
            .sort_values("timestamp")
            .reset_index(drop=True)
        )
    return frame


def _build_score_stats_from_trades(trades_df):
    score_stats = {}
    if trades_df.empty or "score_bucket" not in trades_df.columns:
        return score_stats

    working = trades_df.copy()
    working["score_bucket"] = working["score_bucket"].fillna("<0.6").astype(str)
    working["pnl"] = pd.to_numeric(working.get("pnl"), errors="coerce").fillna(0.0)
    working["pnl_R_initial"] = pd.to_numeric(
        working.get("pnl_R_initial"),
        errors="coerce",
    ).fillna(0.0)

    for bucket, group in working.groupby("score_bucket"):
        score_stats[str(bucket)] = {
            "count": int(len(group)),
            "wins": int((group["pnl"] > 0).sum()),
            "total_R": float(group["pnl_R_initial"].sum()),
            "total_pnl": float(group["pnl"].sum()),
        }

    return score_stats


def _build_strategy_stats_from_trades(trades_df):
    strategy_stats = {}
    if trades_df.empty or "strategy_type" not in trades_df.columns:
        return strategy_stats

    working = trades_df.copy()
    working["strategy_type"] = working["strategy_type"].fillna("core").astype(str)
    working["pnl"] = pd.to_numeric(working.get("pnl"), errors="coerce").fillna(0.0)
    working["pnl_R_initial"] = pd.to_numeric(
        working.get("pnl_R_initial"),
        errors="coerce",
    ).fillna(0.0)

    for strategy_type, group in working.groupby("strategy_type"):
        strategy_stats[str(strategy_type)] = {
            "count": int(len(group)),
            "wins": int((group["pnl"] > 0).sum()),
            "total_R": float(group["pnl_R_initial"].sum()),
            "total_pnl": float(group["pnl"].sum()),
        }
    return strategy_stats


def _build_feature_stats_from_trades(trades_df, scorer):
    feature_stats = {
        feature: {"sum_pos": 0.0, "sum_neg": 0.0}
        for feature in scorer.weights
    }
    if trades_df.empty:
        return feature_stats

    required_columns = {"body_strength", "close_position", "vwap_bucket", "momentum_rank", "pnl_R_initial"}
    missing = [column for column in required_columns if column not in trades_df.columns]
    if missing:
        return feature_stats

    for _, trade_row in trades_df.iterrows():
        pseudo_row = {
            "body_strength": _safe_float(
                pd.to_numeric(trade_row.get("body_strength"), errors="coerce"),
                default=0.0,
            ),
            "close_position": _safe_float(
                pd.to_numeric(trade_row.get("close_position"), errors="coerce"),
                default=0.0,
            ),
        }
        components = scorer.compute_components(
            row=pseudo_row,
            momentum_rank=_safe_float(
                pd.to_numeric(trade_row.get("momentum_rank"), errors="coerce"),
                default=0.5,
            ),
            vwap_bucket=trade_row.get("vwap_bucket"),
            edge_type=trade_row.get("edge_type"),
            is_top_mover=False,
        )
        positive = _safe_float(
            pd.to_numeric(trade_row.get("pnl_R_initial"), errors="coerce"),
            default=0.0,
        ) > 0.0
        for feature in scorer.weights:
            bucket = "sum_pos" if positive else "sum_neg"
            feature_stats[feature][bucket] += float(components.get(feature, 0.0) or 0.0)

    return feature_stats


def _build_artifact_resume_payload(output_dir, common_index, config):
    output_dir = Path(output_dir)
    equity_path = output_dir / "equity.csv"
    status_path = output_dir / "portfolio_status.json"
    if not equity_path.exists() or not status_path.exists():
        return None

    equity_df = _load_equity_rows(equity_path)
    if equity_df.empty:
        return None

    common_index = pd.Index(common_index)
    last_timestamp = pd.Timestamp(equity_df["timestamp"].iloc[-1])
    next_index = int(common_index.searchsorted(last_timestamp, side="right"))
    if next_index <= 0:
        return None

    with status_path.open(encoding="utf-8") as file_handle:
        status = json.load(file_handle)
    if int(status.get("open_positions", 0) or 0) > 0:
        return None

    trades_df = _load_existing_rows(output_dir / "trades.csv")
    daily_df = _load_existing_rows(output_dir / "daily_summary.csv")
    if not daily_df.empty and "date" in daily_df.columns:
        daily_df["date"] = pd.to_datetime(daily_df["date"], errors="coerce").dt.date

    scorer = OpportunityScorer(config=config)
    current_day = last_timestamp.date()
    day_start_equity = None
    if "daily_closed_pnl" in status and "equity" in status:
        try:
            day_start_equity = float(status["equity"]) - float(status["daily_closed_pnl"] or 0.0)
        except (TypeError, ValueError):
            day_start_equity = None
    if day_start_equity is None:
        current_day_rows = equity_df.loc[equity_df["timestamp"].dt.date == current_day]
        if not current_day_rows.empty:
            day_start_equity = float(current_day_rows["equity"].iloc[0])
    if day_start_equity is None:
        day_start_equity = float(status.get("equity", config.require("account", "initial_equity")))

    account_snapshot = {
        "initial_equity": _safe_float(
            status.get("initial_equity", config.require("account", "initial_equity")),
            default=config.require("account", "initial_equity"),
        ),
        "equity": _safe_float(
            status.get("equity", config.require("account", "initial_equity")),
            default=config.require("account", "initial_equity"),
        ),
        "trade_count": int(len(trades_df)),
        "win_count": (
            int((pd.to_numeric(trades_df["pnl"], errors="coerce").fillna(0.0) > 0).sum())
            if (not trades_df.empty and "pnl" in trades_df.columns)
            else 0
        ),
        "loss_count": (
            int((pd.to_numeric(trades_df["pnl"], errors="coerce").fillna(0.0) <= 0).sum())
            if (not trades_df.empty and "pnl" in trades_df.columns)
            else 0
        ),
    }

    portfolio_state = {
        "account": account_snapshot,
        "current_threshold": _safe_float(status.get("current_threshold", 0.0), default=0.0),
        "score_weights": dict(status.get("score_weights") or {}),
        "current_trading_day": str(current_day),
        "day_start_equity": _safe_float(day_start_equity, default=account_snapshot["equity"]),
        "daily_entries_taken": int(status.get("daily_entries_taken", 0) or 0),
        "daily_closed_trades": int(status.get("daily_closed_trades", 0) or 0),
        "daily_closed_pnl": _safe_float(status.get("daily_closed_pnl", 0.0), default=0.0),
        "daily_history": (
            daily_df.to_dict("records")
            if not daily_df.empty
            else []
        ),
        "score_stats": _build_score_stats_from_trades(trades_df),
        "strategy_stats": _build_strategy_stats_from_trades(trades_df),
        "feature_stats": _build_feature_stats_from_trades(trades_df, scorer),
        "last_top_symbols": list(status.get("top_symbols") or []),
        "open_positions": [],
    }
    return {
        "version": 1,
        "next_index": next_index,
        "next_candle_time": (
            None if next_index >= len(common_index) else common_index[next_index]
        ),
        "portfolio_state": portfolio_state,
        "metadata": _resume_metadata(config, _discover_portfolio_symbols(config)),
        "resume_source": "artifacts",
    }


def _save_checkpoint(*, checkpoint_store, next_index, common_index, portfolio_state, metadata):
    if checkpoint_store is None:
        return

    next_candle_time = None
    if 0 <= int(next_index) < len(common_index):
        next_candle_time = common_index[int(next_index)]

    payload = {
        "version": 1,
        "updated_at": pd.Timestamp.now(tz="UTC"),
        "next_index": max(0, int(next_index)),
        "next_candle_time": next_candle_time,
        "portfolio_state": portfolio_state,
        "metadata": dict(metadata or {}),
    }
    checkpoint_store.save(payload)


def _build_strategy_timeframes(df_1m, config):
    builder = TimeframeBuilder(config=config)
    execution_rule = config.require("timeframes", "execution", "rule")
    direction_rule = config.require("timeframes", "direction", "rule")
    getter = getattr(config, "get", None)
    macro_rule = (
        getter("timeframes", "macro", "rule", default="12h")
        if callable(getter)
        else "12h"
    )

    df_15m = builder.resample(df_1m, execution_rule)
    df_1h = builder.resample(df_1m, direction_rule)
    df_12h = builder.resample(df_1m, macro_rule)
    df_1d = builder.resample(df_1m, "1D")
    df_1w = builder.resample(df_1m, "1W")

    df_15m = compute_features(df_15m, config=config)
    df_1h = compute_features(df_1h, config=config)
    df_12h = compute_features(df_12h, config=config)
    df_1d = compute_features(df_1d, config=config)
    df_1w = compute_features(df_1w, config=config)
    return df_15m, df_1h, df_12h, df_1d, df_1w


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
    moonshot_overlay,
    portfolio,
    swing_snapshot=None,
    htf_snapshot=None,
    htf_engine=None,
    htf_rotation_snapshot=None,
    htf_rotation_engine=None,
    config,
):
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
                "selection_score": float(score_info["score"]),
                "strategy_type": "core",
                "signal_family": "portfolio_replay",
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


def run_portfolio_backtest(config=None):
    config = config or AppConfig.load()
    configure_debug(config=config)

    interval = config.require("binance", "default_interval")
    start_date = config.require("history", "start_date")
    end_date = config.require("history", "end_date")
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
    checkpoint_every_steps = int(
        getter("backtest", "save_every_steps", default=250)
        if callable(getter)
        else 250
    )
    resume_enabled = bool(
        getter("backtest", "resume_enabled", default=True)
        if callable(getter)
        else True
    )

    symbols = _discover_portfolio_symbols(config)
    checkpoint_store = _build_checkpoint_store(config, output_dir, symbols)
    expected_resume_metadata = _resume_metadata(config, symbols)
    print("\nSTARTING PORTFOLIO BACKTEST REPLAY\n")
    print(f"Universe: {', '.join(symbols)}")

    execution_frames = {}
    bias_frames = {}
    swing_frames = {}
    htf_frames = {}
    htf_macro_frames = {}
    htf_daily_frames = {}
    htf_weekly_frames = {}
    source_paths = {}
    bias_detector = BiasDetector(config=config)

    for symbol in symbols:
        print(f"\nLoading full history for {symbol}...")
        df_1m, source_path = _load_full_history(symbol, interval, config)
        df_15m, df_1h, df_12h, df_1d, df_1w = _build_strategy_timeframes(df_1m, config=config)
        execution_frames[symbol] = df_15m
        bias_frames[symbol] = _aligned_bias_snapshots(df_15m, df_1h, bias_detector)
        swing_frames[symbol] = build_swing_snapshots(
            df_15m.index,
            df_1d,
            df_1w,
            config=config,
        )
        htf_macro_frames[symbol] = df_12h
        htf_daily_frames[symbol] = df_1d
        htf_weekly_frames[symbol] = df_1w
        htf_frames[symbol] = build_htf_12h_snapshots(
            df_15m.index,
            df_12h,
            df_1d,
            df_1w,
            config=config,
        )
        source_paths[symbol] = source_path
        print(f"  Source: {source_path}")
        print(f"  Execution rows: {len(df_15m):,}")

    htf_rotation_frames = build_htf_rotation_snapshots_by_symbol(
        {symbol: frame.index for symbol, frame in execution_frames.items()},
        htf_macro_frames,
        htf_daily_frames,
        htf_weekly_frames,
        structural_snapshots_by_symbol=htf_frames,
        config=config,
    )

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

    checkpoint_candidate = None
    if checkpoint_store is not None and checkpoint_store.exists():
        candidate = checkpoint_store.load()
        if _resume_metadata_matches(candidate, expected_resume_metadata):
            checkpoint_candidate = candidate
        else:
            checkpoint_store.clear()

    artifact_candidate = None
    if resume_enabled:
        try:
            candidate = _build_artifact_resume_payload(output_dir, common_index, config)
        except Exception as exc:
            print(f"Artifact resume ignored due to parse error: {exc}")
            candidate = None
        if _resume_metadata_matches(candidate, expected_resume_metadata):
            artifact_candidate = candidate

    resume_payload = None
    resume_index = 0
    resume_active = False
    resume_source = None
    for source_name, candidate in (
        ("checkpoint", checkpoint_candidate),
        ("artifacts", artifact_candidate),
    ):
        if _payload_next_index(candidate) > resume_index:
            resume_payload = candidate
            resume_index = _payload_next_index(candidate)
            resume_active = resume_index > 0
            resume_source = candidate.get("resume_source", source_name)

    trade_logger = TradeLogger(config=config, reset=not resume_active)
    equity_logger = EquityLogger(config=config, reset=not resume_active)
    signal_logger = LiveSignalLogger(
        filepath=str(output_dir / signal_log_filename),
        config=config,
        reset=not resume_active,
    )
    state_logger = LivePortfolioStateLogger(output_dir=output_dir, config=config)
    portfolio = LivePaperPortfolio(
        trade_logger=trade_logger,
        signal_logger=signal_logger,
        state_logger=state_logger,
        config=config,
    )
    if resume_active and resume_payload:
        portfolio.restore_state(resume_payload.get("portfolio_state"))
        print(
            f"Resuming portfolio replay from {resume_source} at index "
            f"{resume_index:,}/{len(common_index):,}"
        )
    edge_selector = EdgeSelector(config=config)
    moonshot_overlay = MoonshotOverlay(config=config)
    htf_engine = HTFMoonshotEngine(config=config)
    htf_rotation_engine = HTFRotationEngine(config=config)

    latest_rows_by_symbol = {}
    latest_htf_context_by_symbol = {}
    start_time = time.time()
    if resume_index >= len(common_index):
        if checkpoint_store is not None:
            checkpoint_store.clear()
        portfolio.backtest_completed = True
        portfolio.source_paths = source_paths
        return portfolio

    last_stable_state = portfolio.snapshot_state()
    last_completed_index = max(-1, resume_index - 1)
    try:
        for step_index in range(resume_index, len(common_index)):
            timestamp = common_index[step_index]
            portfolio.reset_daily_state_if_needed(timestamp)

            candidates = []
            latest_rows_by_symbol = {}
            latest_htf_context_by_symbol = {}
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
                latest_htf_context_by_symbol[symbol] = (
                    htf_frames[symbol].loc[timestamp].to_dict()
                    if timestamp in htf_frames[symbol].index
                    else {}
                )

            if latest_rows_by_symbol:
                portfolio.manage_open_positions(
                    latest_rows_by_symbol,
                    htf_context_by_symbol=latest_htf_context_by_symbol,
                )

            for symbol, row in latest_rows_by_symbol.items():
                bias_frame = bias_frames[symbol]
                if timestamp not in bias_frame.index:
                    continue
                bias_snapshot = bias_frame.loc[timestamp].to_dict()
                if pd.isna(bias_snapshot.get("label")):
                    continue
                swing_snapshot = (
                    swing_frames[symbol].loc[timestamp].to_dict()
                    if timestamp in swing_frames[symbol].index
                    else {}
                )
                symbol_candidates = _build_candidate(
                    symbol=symbol,
                    row=row,
                    bias_snapshot=bias_snapshot,
                    momentum_rank=float(rank_row.get(symbol, 0.5) or 0.5),
                    top_symbols=top_symbols,
                    edge_selector=edge_selector,
                    moonshot_overlay=moonshot_overlay,
                    portfolio=portfolio,
                    swing_snapshot=swing_snapshot,
                    htf_snapshot=latest_htf_context_by_symbol.get(symbol),
                    htf_engine=htf_engine,
                    htf_rotation_snapshot=(
                        htf_rotation_frames[symbol].loc[timestamp].to_dict()
                        if timestamp in htf_rotation_frames[symbol].index
                        else {}
                    ),
                    htf_rotation_engine=htf_rotation_engine,
                    config=config,
                )
                candidates.extend(symbol_candidates)

            if candidates:
                portfolio.select_and_open(candidates, timestamp)
            else:
                portfolio.flush_state()

            equity_logger.log(timestamp, portfolio.account.equity)
            last_completed_index = step_index
            last_stable_state = portfolio.snapshot_state()

            processed_steps = (step_index - resume_index) + 1
            if (
                checkpoint_store is not None
                and checkpoint_every_steps > 0
                and (
                    processed_steps == 1
                    or processed_steps % checkpoint_every_steps == 0
                )
            ):
                _save_checkpoint(
                    checkpoint_store=checkpoint_store,
                    next_index=step_index + 1,
                    common_index=common_index,
                    portfolio_state=last_stable_state,
                    metadata=expected_resume_metadata,
                )

            if (
                processed_steps == 1
                or processed_steps % 500 == 0
                or step_index == len(common_index) - 1
            ):
                elapsed = time.time() - start_time
                print(
                    "\nPORTFOLIO BACKTEST PROGRESS\n"
                    f"  Step: {step_index + 1:,}/{len(common_index):,}\n"
                    f"  Candle: {timestamp}\n"
                    f"  Equity: {portfolio.account.equity:.2f}\n"
                    f"  Open positions: {len(portfolio.open_positions)}\n"
                    f"  Entries today: {portfolio.daily_entries_taken}\n"
                    f"  Threshold: {portfolio.current_threshold:.2f}\n"
                    f"  Elapsed: {elapsed:.2f}s"
                )
    except KeyboardInterrupt:
        _save_checkpoint(
            checkpoint_store=checkpoint_store,
            next_index=max(0, last_completed_index + 1),
            common_index=common_index,
            portfolio_state=last_stable_state,
            metadata=expected_resume_metadata,
        )
        print("\nPORTFOLIO BACKTEST PAUSED")
        print("Checkpoint saved. Re-run the same command to resume.")
        portfolio.backtest_completed = False
        return portfolio
    except Exception:
        _save_checkpoint(
            checkpoint_store=checkpoint_store,
            next_index=max(0, last_completed_index + 1),
            common_index=common_index,
            portfolio_state=last_stable_state,
            metadata=expected_resume_metadata,
        )
        raise

    portfolio.finalize_backtest(
        latest_rows_by_symbol=latest_rows_by_symbol,
        close_open_positions=close_open_positions,
    )
    if latest_rows_by_symbol:
        final_timestamp = max(latest_rows_by_symbol.values(), key=lambda row: row.name).name
        equity_logger.log(final_timestamp, portfolio.account.equity)

    if checkpoint_store is not None:
        checkpoint_store.clear()
    portfolio.backtest_completed = True
    portfolio.source_paths = source_paths
    return portfolio
