"""Runs the near-live simulation loop using recent Binance data and shared strategy components."""

import json
import hashlib
import subprocess
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
from capital import write_scaffold_inventory
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
from common.runtime_readiness import build_runtime_readiness

PAPER_SOAK_STRATEGY_ORDER = [
    "core",
    "swing_moonshot",
    "h1_execution",
    "htf_12h_standard",
    "htf_12h_moonshot",
    "htf_12h_rotation",
]

ALLOCATOR_DECISION_KEYS = [
    "opened",
    "score_bucket_filtered",
    "score_below_threshold",
    "shared_risk_cap",
    "strategy_sleeve_cap",
    "asset_cap",
    "direction_cap",
    "same_symbol_same_side_cap",
    "allocator_rank_filtered",
    "strategy_health_filtered",
]

PAPER_SOAK_MIN_DAYS = 14


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


def _portfolio_runtime_state_path(config):
    output_dir = Path(config.require("live_sim", "output_dir"))
    return output_dir / "portfolio_runtime_state.json"


def _paper_runtime_startup_report_path(config):
    output_dir = Path(config.require("live_sim", "output_dir"))
    return output_dir / "paper_runtime_startup_report.json"


def _paper_soak_status_path(config):
    output_dir = Path(config.require("live_sim", "output_dir"))
    return output_dir / "paper_soak_status.json"


def _paper_runtime_events_path(config):
    output_dir = Path(config.require("live_sim", "output_dir"))
    return output_dir / "paper_runtime_events.jsonl"


def _paper_soak_daily_report_path(config):
    output_dir = Path(config.require("live_sim", "output_dir"))
    return output_dir / "paper_soak_daily_report.json"


def _paper_soak_review_path(config):
    output_dir = Path(config.require("live_sim", "output_dir"))
    return output_dir / "paper_soak_review.json"


def _paper_soak_review_history_path(config):
    output_dir = Path(config.require("live_sim", "output_dir"))
    return output_dir / "paper_soak_review_history.jsonl"


def _baseline_freeze_snapshot_path(config):
    output_dir = Path(config.require("live_sim", "output_dir"))
    return output_dir / "baseline_freeze_snapshot.json"


def _portfolio_status_path(config):
    output_dir = Path(config.require("live_sim", "output_dir"))
    return output_dir / "portfolio_status.json"


def _daily_summary_path(config):
    output_dir = Path(config.require("live_sim", "output_dir"))
    return output_dir / "daily_summary.csv"


def _load_live_portfolio_snapshot(config):
    snapshot_path = _portfolio_runtime_state_path(config)
    if not snapshot_path.exists():
        return None, snapshot_path
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except Exception as error:
        print(
            f"Live paper portfolio snapshot is malformed and will be ignored: "
            f"{snapshot_path} | {error}"
        )
        return None, snapshot_path
    if not isinstance(payload, dict):
        print(
            f"Live paper portfolio snapshot is not a JSON object and will be ignored: "
            f"{snapshot_path}"
        )
        return None, snapshot_path
    return payload, snapshot_path


def _timestamp_to_utc_iso(value):
    if value in (None, "", pd.NaT):
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.isoformat()


def _utc_now_timestamp():
    return _timestamp_to_utc_iso(pd.Timestamp.now("UTC"))


def _utc_now_ts():
    return pd.Timestamp(_utc_now_timestamp())


def _latest_runtime_boundary(states_by_symbol):
    timestamps = []
    for frame in dict(states_by_symbol or {}).values():
        if frame is None or frame.empty:
            continue
        timestamps.append(pd.Timestamp(frame.index.max()))
    if not timestamps:
        return None
    return str(max(timestamps))


def _restored_state_summary(portfolio):
    open_positions = list(getattr(portfolio, "open_positions", []) or [])
    lineage_ids = {
        str(getattr(trade, "lineage_id", "") or "").strip()
        for trade in open_positions
        if str(getattr(trade, "lineage_id", "") or "").strip()
    }
    allocator_stats = {
        "strategy_stats_count": int(len(getattr(portfolio, "strategy_stats", {}) or {})),
        "recent_strategy_trade_stats_count": int(
            len(getattr(portfolio, "recent_strategy_trade_stats", {}) or {})
        ),
        "recent_strategy_bucket_trade_stats_count": int(
            len(getattr(portfolio, "recent_strategy_bucket_trade_stats", {}) or {})
        ),
        "selection_reason_total": int(
            sum(int(value or 0) for value in dict(getattr(portfolio, "selection_reason_counts", {}) or {}).values())
        ),
    }
    daily_controls = {
        "current_trading_day": (
            str(getattr(portfolio, "current_trading_day", None))
            if getattr(portfolio, "current_trading_day", None) is not None
            else None
        ),
        "day_start_equity": float(getattr(portfolio, "day_start_equity", 0.0) or 0.0),
        "daily_entries_taken": int(getattr(portfolio, "daily_entries_taken", 0) or 0),
        "daily_closed_trades": int(getattr(portfolio, "daily_closed_trades", 0) or 0),
        "daily_closed_pnl": float(getattr(portfolio, "daily_closed_pnl", 0.0) or 0.0),
        "daily_loss_streak": int(getattr(portfolio, "daily_loss_streak", 0) or 0),
    }
    return {
        "restored_open_positions_count": int(len(open_positions)),
        "restored_lineage_count": int(len(lineage_ids)),
        "restored_allocator_stats": allocator_stats,
        "restored_daily_controls": daily_controls,
    }


def _snapshot_runtime_last_processed(snapshot_payload):
    if not snapshot_payload:
        return None
    runtime_context = dict(snapshot_payload.get("runtime_context") or {})
    return runtime_context.get("runtime_last_processed_timestamp")


def _resolved_history_end_date(config):
    getter = getattr(config, "get", None)
    if callable(getter):
        return getter("history", "end_date", default=None)
    return None


def _build_paper_runtime_startup_report(
    *,
    config,
    readiness,
    bootstrap_metadata_by_symbol,
    catchup_metadata_by_symbol,
    restored_state_used,
    restored_state_path,
    restore_summary,
    runtime_start_timestamp,
    runtime_first_processed_candle,
    runtime_last_processed_candle,
):
    runtime_config = dict(readiness.get("runtime_config", {}) or {})
    latest_canonical = [
        value.get("canonical_history_last_timestamp")
        for value in bootstrap_metadata_by_symbol.values()
        if value.get("canonical_history_last_timestamp")
    ]
    latest_canonical_boundary = max(latest_canonical) if latest_canonical else None
    return {
        "generated_at_utc": _utc_now_timestamp(),
        "runtime_mode": "portfolio_paper",
        "classification": readiness.get("classification"),
        "paper_runtime_allowed": bool(readiness.get("paper_runtime_allowed")),
        "real_money_allowed": bool(readiness.get("real_money_allowed")),
        "blockers": list(readiness.get("blockers") or []),
        "validated_boundary": readiness.get("validated_boundary"),
        "runtime_start_timestamp": runtime_start_timestamp,
        "runtime_first_processed_candle": runtime_first_processed_candle,
        "runtime_last_processed_candle": runtime_last_processed_candle,
        "canonical_history_end_date_resolved": _resolved_history_end_date(config),
        "canonical_bootstrap_boundary": latest_canonical_boundary,
        "validated_boundary_matches_canonical_bootstrap": (
            bool(readiness.get("validated_boundary"))
            and readiness.get("validated_boundary") == latest_canonical_boundary
        ),
        "restored_state_used": bool(restored_state_used),
        "restored_state_path": str(restored_state_path),
        "restored_positions_count": int(restore_summary.get("restored_open_positions_count", 0)),
        "restored_lineage_count": int(restore_summary.get("restored_lineage_count", 0)),
        "restored_allocator_stats": dict(restore_summary.get("restored_allocator_stats") or {}),
        "restored_daily_controls": dict(restore_summary.get("restored_daily_controls") or {}),
        "active_sleeves": list(runtime_config.get("active_sleeves", [])),
        "disabled_sleeves": list(runtime_config.get("disabled_sleeves", [])),
        "allowed_sides": list(runtime_config.get("allowed_sides", [])),
        "strategy_allowed_sides": dict(runtime_config.get("strategy_allowed_sides", {}) or {}),
        "ssl_verify": bool(readiness.get("tls", {}).get("ssl_verify")),
        "official_gate_root": readiness.get("gate_root"),
        "official_gate_summary_path": readiness.get("summary_path"),
        "official_gate_report_path": readiness.get("promotion_readiness_report_path"),
        "scenario_manifest_paths": dict(readiness.get("scenario_manifest_paths") or {}),
        "bootstrap_metadata_by_symbol": bootstrap_metadata_by_symbol,
        "catchup_metadata_by_symbol": catchup_metadata_by_symbol,
    }


def _write_paper_runtime_startup_report(config, payload):
    report_path = _paper_runtime_startup_report_path(config)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return report_path


def _append_paper_runtime_event(config, payload):
    event_path = _paper_runtime_events_path(config)
    event_path.parent.mkdir(parents=True, exist_ok=True)
    with event_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str) + "\n")
    return event_path


def _latest_price_by_symbol(states_by_symbol):
    prices = {}
    for symbol, frame in dict(states_by_symbol or {}).items():
        if frame is None or frame.empty:
            continue
        try:
            prices[str(symbol).upper()] = float(frame["close"].iloc[-1])
        except Exception:
            continue
    return prices


def _trade_unrealized_pnl(trade, latest_price):
    if latest_price in (None, ""):
        return 0.0
    total = 0.0
    for entry_price, size in list(getattr(trade, "entries", []) or []):
        if getattr(trade, "side", "long") == "short":
            move = float(entry_price) - float(latest_price)
        else:
            move = float(latest_price) - float(entry_price)
        total += move * float(size)
    return float(total)


def _portfolio_unrealized_pnl(portfolio, latest_prices):
    total = 0.0
    for trade in list(getattr(portfolio, "open_positions", []) or []):
        symbol = str(getattr(trade, "symbol", "") or "").upper()
        total += _trade_unrealized_pnl(trade, latest_prices.get(symbol))
    return float(total)


def _strategy_trade_counts(portfolio):
    rows = {}
    for strategy_type, values in dict(getattr(portfolio, "strategy_stats", {}) or {}).items():
        rows[str(strategy_type)] = int(values.get("count", 0) or 0)
    return rows


def _strategy_trade_pnl(portfolio):
    rows = {}
    for strategy_type, values in dict(getattr(portfolio, "strategy_stats", {}) or {}).items():
        rows[str(strategy_type)] = float(values.get("total_pnl", 0.0) or 0.0)
    return rows


def _strategy_open_positions_by_type(portfolio):
    rows = defaultdict(int)
    for trade in list(getattr(portfolio, "open_positions", []) or []):
        rows[str(getattr(trade, "strategy_type", "core") or "core")] += 1
    return {key: int(value) for key, value in rows.items()}


def _latest_allocator_rejection_counts(selection_summary):
    counts = {}
    for reason, count in dict(selection_summary.get("final_reason_counts", {}) or {}).items():
        if str(reason) == "opened":
            continue
        counts[str(reason)] = int(count or 0)
    return counts


def _allocator_decision_counts(selection_summary):
    final_reason_counts = dict(selection_summary.get("final_reason_counts", {}) or {})
    return {
        key: int(final_reason_counts.get(key, 0) or 0)
        for key in ALLOCATOR_DECISION_KEYS
    }


def _strategy_unrealized_pnl_by_type(portfolio, latest_prices):
    rows = defaultdict(float)
    for trade in list(getattr(portfolio, "open_positions", []) or []):
        strategy_type = str(getattr(trade, "strategy_type", "core") or "core")
        symbol = str(getattr(trade, "symbol", "") or "").upper()
        rows[strategy_type] += _trade_unrealized_pnl(trade, latest_prices.get(symbol))
    return {key: float(value) for key, value in rows.items()}


def _strategy_daily_evidence(portfolio, latest_prices):
    strategy_stats = dict(getattr(portfolio, "strategy_stats", {}) or {})
    open_positions_by_type = _strategy_open_positions_by_type(portfolio)
    unrealized_by_type = _strategy_unrealized_pnl_by_type(portfolio, latest_prices)
    selection_reasons_by_strategy = dict(
        getattr(portfolio, "selection_reason_counts_by_strategy", {}) or {}
    )
    recent_rejections_by_strategy = dict(
        getattr(portfolio, "recent_selection_reason_counts_by_strategy", {}) or {}
    )
    rows = {}
    all_strategy_names = list(
        dict.fromkeys(
            PAPER_SOAK_STRATEGY_ORDER
            + list(strategy_stats.keys())
            + list(open_positions_by_type.keys())
            + list(selection_reasons_by_strategy.keys())
        )
    )
    for strategy_name in all_strategy_names:
        stats = dict(strategy_stats.get(strategy_name) or {})
        count = int(stats.get("count", 0) or 0)
        wins = int(stats.get("wins", 0) or 0)
        realized_pnl = float(stats.get("total_pnl", 0.0) or 0.0)
        open_positions = int(open_positions_by_type.get(strategy_name, 0) or 0)
        latest_reason_counts = {
            str(key): int(value or 0)
            for key, value in dict(selection_reasons_by_strategy.get(strategy_name, {}) or {}).items()
        }
        latest_rejection_reasons = {
            str(key): int(value or 0)
            for key, value in latest_reason_counts.items()
            if str(key) != "opened"
        }
        rows[strategy_name] = {
            "trades_opened": int(count + open_positions),
            "trades_closed": count,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": float(unrealized_by_type.get(strategy_name, 0.0) or 0.0),
            "win_count": wins,
            "loss_count": max(0, count - wins),
            "open_positions_count": open_positions,
            "latest_signal_count": int(sum(latest_reason_counts.values())),
            "latest_opened_count": int(latest_reason_counts.get("opened", 0) or 0),
            "latest_rejection_reasons": latest_rejection_reasons,
            "recent_rejection_reasons": {
                str(key): int(value or 0)
                for key, value in dict(recent_rejections_by_strategy.get(strategy_name, {}) or {}).items()
                if str(key) != "opened"
            },
        }
    return rows


def _read_latest_jsonl_event(path):
    if not path.exists():
        return {}
    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception:
        return {}
    if not lines:
        return {}
    try:
        payload = json.loads(lines[-1])
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_json_file(path):
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_jsonl_records(path):
    if not path.exists():
        return []
    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception:
        return []
    records = []
    for line in lines:
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _paper_soak_minimum_days(config):
    getter = getattr(config, "get", None)
    if not callable(getter):
        return PAPER_SOAK_MIN_DAYS
    value = getter("paper_soak", "minimum_days_before_review", default=PAPER_SOAK_MIN_DAYS)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return PAPER_SOAK_MIN_DAYS


def _config_manifest_metadata(config):
    config_path = getattr(config, "config_path", None)
    resolved = Path(config_path) if config_path else Path("config/settings.json")
    if not resolved.exists():
        return {
            "config_path": str(resolved),
            "config_sha256": None,
        }
    content = resolved.read_bytes()
    return {
        "config_path": str(resolved),
        "config_sha256": hashlib.sha256(content).hexdigest(),
    }


def _git_commit_or_none():
    try:
        output = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None
    return output or None
    value = getter("paper_soak", "minimum_days_before_review", default=PAPER_SOAK_MIN_DAYS)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return PAPER_SOAK_MIN_DAYS


def _artifact_health_status(path, *, stale_after_seconds):
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "status": "missing",
            "last_modified_timestamp": None,
            "age_seconds": None,
            "stale_after_seconds": float(stale_after_seconds),
        }
    try:
        age_seconds = max(
            0.0,
            float(pd.Timestamp.now("UTC").timestamp() - path.stat().st_mtime),
        )
    except Exception:
        age_seconds = None
    status = "healthy"
    if age_seconds is None or age_seconds > float(stale_after_seconds):
        status = "stale"
    return {
        "path": str(path),
        "exists": True,
        "status": status,
        "last_modified_timestamp": _timestamp_to_utc_iso(pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC")),
        "age_seconds": age_seconds,
        "stale_after_seconds": float(stale_after_seconds),
    }


def _paper_soak_artifact_health(config):
    return {
        "paper_soak_daily_report": _artifact_health_status(
            _paper_soak_daily_report_path(config),
            stale_after_seconds=24 * 3600.0,
        ),
        "paper_soak_status": _artifact_health_status(
            _paper_soak_status_path(config),
            stale_after_seconds=300.0,
        ),
        "paper_runtime_events": _artifact_health_status(
            _paper_runtime_events_path(config),
            stale_after_seconds=24 * 3600.0,
        ),
        "portfolio_status": _artifact_health_status(
            _portfolio_status_path(config),
            stale_after_seconds=300.0,
        ),
        "portfolio_runtime_state": _artifact_health_status(
            _portfolio_runtime_state_path(config),
            stale_after_seconds=900.0,
        ),
    }


def _daily_summary_frame(config):
    path = _daily_summary_path(config)
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _daily_summary_value_summary(frame, column, *, latest_value=None):
    if frame.empty or column not in frame.columns:
        return {
            "days": 0,
            "avg": None,
            "median": None,
            "min": None,
            "max": None,
            "latest": latest_value,
        }
    series = pd.to_numeric(frame[column], errors="coerce").dropna()
    if series.empty:
        return {
            "days": 0,
            "avg": None,
            "median": None,
            "min": None,
            "max": None,
            "latest": latest_value,
        }
    latest = latest_value if latest_value is not None else float(series.iloc[-1])
    return {
        "days": int(series.shape[0]),
        "avg": float(series.mean()),
        "median": float(series.median()),
        "min": float(series.min()),
        "max": float(series.max()),
        "latest": float(latest) if latest is not None else None,
    }


def _max_paper_drawdown_from_daily_summary(frame, *, current_equity=None):
    if frame.empty or "equity_end" not in frame.columns:
        return None
    series = pd.to_numeric(frame["equity_end"], errors="coerce").dropna()
    if current_equity is not None:
        series = pd.concat([series, pd.Series([float(current_equity)])], ignore_index=True)
    if series.empty:
        return None
    running_max = series.cummax().replace(0.0, pd.NA)
    drawdowns = ((series - running_max) / running_max).dropna()
    if drawdowns.empty:
        return None
    return float(abs(drawdowns.min()))


def _state_contamination_check(*, startup_report, runtime_state_path, portfolio_state):
    restored_state_path = str(startup_report.get("restored_state_path") or "")
    runtime_state_file = str(runtime_state_path)
    payload_source = str(portfolio_state.get("runtime_context", {}).get("restored_state_path") or "")
    inspected_paths = [value for value in [restored_state_path, runtime_state_file, payload_source] if value]
    contaminated_paths = [
        value for value in inspected_paths if any(token in value.lower() for token in ["backtest", "holdout"])
    ]
    uses_live_runtime_state = (
        not restored_state_path
        or "portfolio_runtime_state.json" in restored_state_path
    )
    return {
        "passed": bool(uses_live_runtime_state and not contaminated_paths),
        "restored_state_path": restored_state_path or None,
        "runtime_state_path": runtime_state_file,
        "payload_source": payload_source or None,
        "contaminated_paths": contaminated_paths,
    }


def _active_sleeve_match(readiness, soak_status):
    runtime_config = dict(readiness.get("runtime_config", {}) or {})
    expected_active = list(runtime_config.get("active_sleeves", []) or [])
    expected_disabled = list(runtime_config.get("disabled_sleeves", []) or [])
    observed_active = list(soak_status.get("active_sleeves", []) or [])
    observed_disabled = list(soak_status.get("disabled_sleeves", []) or [])
    return {
        "passed": set(observed_active) == set(expected_active) and set(observed_disabled) == set(expected_disabled),
        "expected_active": expected_active,
        "observed_active": observed_active,
        "expected_disabled": expected_disabled,
        "observed_disabled": observed_disabled,
    }


def _paper_soak_review_status(*, criteria, soak_days_completed, required_days):
    if float(soak_days_completed) < float(required_days):
        return "insufficient_forward_paper_duration"
    statuses = [str((value or {}).get("status", "unknown")).lower() for value in criteria.values()]
    if any(status == "fail" for status in statuses):
        return "review_blocked"
    if any(status == "warn" for status in statuses):
        return "manual_review_required"
    if all(status == "pass" for status in statuses):
        return "manual_promotion_review_ready"
    return "manual_review_required"


def _manual_review_outcome_from_soak_review(soak_review):
    allowed_outcomes = [
        "continue_paper_soak",
        "paper_soak_failed",
        "eligible_for_capital_refactor_research",
        "eligible_for_tiny_live_pilot_later",
    ]
    criteria = dict(soak_review.get("soak_review_criteria") or {})
    failed_criteria = sorted(
        key for key, value in criteria.items() if str((value or {}).get("status", "unknown")).lower() == "fail"
    )
    warned_criteria = sorted(
        key for key, value in criteria.items() if str((value or {}).get("status", "unknown")).lower() == "warn"
    )
    missing_or_stale_artifacts = sorted(
        key
        for key, value in dict(soak_review.get("artifact_health") or {}).items()
        if str((value or {}).get("status", "missing")).lower() != "healthy"
    )
    no_go = bool(
        failed_criteria
        or missing_or_stale_artifacts
        or bool(soak_review.get("real_money_allowed"))
        or not bool(soak_review.get("ssl_verify"))
        or not bool(soak_review.get("paper_runtime_allowed"))
    )
    review_status = str(soak_review.get("soak_review_status") or "")
    if no_go:
        outcome = "paper_soak_failed"
        rationale = "One or more no-go conditions failed or required artifacts are missing/stale."
    elif review_status == "insufficient_forward_paper_duration":
        outcome = "continue_paper_soak"
        rationale = "Minimum forward-paper duration has not been reached."
    elif warned_criteria:
        outcome = "eligible_for_capital_refactor_research"
        rationale = "Forward-paper evidence is present but still requires non-live research follow-up."
    else:
        outcome = "eligible_for_tiny_live_pilot_later"
        rationale = "All current governance checks pass, but any live pilot still requires a separate explicit task and human approval."
    return {
        "manual_review_outcome": outcome,
        "allowed_manual_review_outcomes": allowed_outcomes,
        "manual_review_no_go": no_go,
        "failed_criteria": failed_criteria,
        "warned_criteria": warned_criteria,
        "missing_or_stale_artifacts": missing_or_stale_artifacts,
        "rationale": rationale,
        "automatic_real_money_promotion": False,
    }


def _build_baseline_freeze_snapshot(
    *,
    config,
    readiness,
    startup_report,
    daily_report,
    soak_review,
):
    manifest_metadata = _config_manifest_metadata(config)
    manual_review = _manual_review_outcome_from_soak_review(soak_review)
    return {
        "generated_at_utc": _utc_now_timestamp(),
        "classification": readiness.get("classification"),
        "validated_boundary": readiness.get("validated_boundary"),
        "paper_runtime_allowed": bool(readiness.get("paper_runtime_allowed")),
        "real_money_allowed": False,
        "ssl_verify": bool(readiness.get("tls", {}).get("ssl_verify")),
        "minimum_soak_days": int(_paper_soak_minimum_days(config)),
        "current_soak_days": float(soak_review.get("soak_days_completed", 0.0) or 0.0),
        "active_sleeves": list((readiness.get("runtime_config", {}) or {}).get("active_sleeves", [])),
        "disabled_sleeves": list((readiness.get("runtime_config", {}) or {}).get("disabled_sleeves", [])),
        "config_manifest": manifest_metadata,
        "scenario_manifest_paths": dict(readiness.get("scenario_manifest_paths") or {}),
        "validation_artifact_paths": {
            "summary_path": readiness.get("summary_path"),
            "promotion_readiness_report_path": readiness.get("promotion_readiness_report_path"),
            "gate_root": readiness.get("gate_root"),
        },
        "paper_artifact_paths": {
            "paper_runtime_startup_report": str(_paper_runtime_startup_report_path(config)),
            "paper_runtime_events": str(_paper_runtime_events_path(config)),
            "paper_soak_status": str(_paper_soak_status_path(config)),
            "paper_soak_daily_report": str(_paper_soak_daily_report_path(config)),
            "paper_soak_review": str(_paper_soak_review_path(config)),
            "paper_soak_review_history": str(_paper_soak_review_history_path(config)),
            "portfolio_runtime_state": str(_portfolio_runtime_state_path(config)),
            "portfolio_status": str(_portfolio_status_path(config)),
        },
        "current_soak_review_status": soak_review.get("soak_review_status"),
        "current_promotion_status": (daily_report.get("promotion_criteria") or {}).get("promotion_status"),
        "manual_review": manual_review,
        "manual_review_status": "no_go" if manual_review.get("manual_review_no_go") else "governance_only",
        "startup_report_runtime_mode": startup_report.get("runtime_mode"),
        "startup_report_generated_at": startup_report.get("generated_at_utc"),
        "git_commit": _git_commit_or_none(),
        "window_policy": "governance_freeze_only",
    }


def _write_baseline_freeze_snapshot(config, payload):
    snapshot_path = _baseline_freeze_snapshot_path(config)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return snapshot_path


def _build_paper_soak_review(
    *,
    config,
    readiness,
    soak_status,
    daily_report,
    startup_report,
    event_log_path,
):
    minimum_days = _paper_soak_minimum_days(config)
    uptime_seconds = float(soak_status.get("runtime_uptime_seconds", 0.0) or 0.0)
    soak_days_completed = uptime_seconds / 86400.0
    event_records = _read_jsonl_records(event_log_path)
    successful_restore_count = sum(1 for row in event_records if bool(row.get("restore_happened")))
    portfolio_status = _read_json_file(_portfolio_status_path(config))
    runtime_state = _read_json_file(_portfolio_runtime_state_path(config))
    daily_summary = _daily_summary_frame(config)
    artifact_health = _paper_soak_artifact_health(config)
    stale_artifacts = [
        key for key, value in artifact_health.items() if str(value.get("status")) != "healthy"
    ]
    contamination = _state_contamination_check(
        startup_report=startup_report,
        runtime_state_path=_portfolio_runtime_state_path(config),
        portfolio_state=runtime_state,
    )
    sleeve_match = _active_sleeve_match(readiness, soak_status)
    heartbeat_health = str(daily_report.get("heartbeat_status") or "unknown").lower()
    current_equity = float(daily_report.get("current_paper_equity", 0.0) or 0.0)
    realized_pnl = float(daily_report.get("realized_pnl_since_paper_start", 0.0) or 0.0)
    unrealized_pnl = float(daily_report.get("unrealized_pnl", 0.0) or 0.0)
    max_drawdown = _max_paper_drawdown_from_daily_summary(
        daily_summary,
        current_equity=current_equity,
    )
    daily_pnl_summary = _daily_summary_value_summary(
        daily_summary,
        "realized_pnl",
        latest_value=daily_report.get("daily_pnl"),
    )
    daily_trade_count_summary = {
        "closed_trades": _daily_summary_value_summary(
            daily_summary,
            "closed_trades",
            latest_value=daily_report.get("daily_closed_trades"),
        ),
        "entries_taken": _daily_summary_value_summary(
            daily_summary,
            "entries_taken",
            latest_value=daily_report.get("daily_entries"),
        ),
    }
    h6_route_counts = dict(daily_report.get("h6_route_counts") or {})
    h6_zero = all(int(h6_route_counts.get(key, 0) or 0) == 0 for key in ["h6_standard", "h6_moonshot"])
    drawdown_acceptable = max_drawdown is None or float(max_drawdown) <= 0.10
    pnl_proxy_ok = current_equity >= (float(soak_status.get("paper_start_equity", current_equity) or current_equity) * 0.98)
    criteria = {
        "minimum_soak_duration_reached": {
            "status": "pass" if soak_days_completed >= minimum_days else "warn",
            "completed_days": float(round(soak_days_completed, 4)),
            "required_days": int(minimum_days),
        },
        "no_operational_blockers": {
            "status": "pass" if not list(daily_report.get("blocker_list") or []) else "fail",
            "blocker_count": int(len(list(daily_report.get("blocker_list") or []))),
        },
        "real_money_allowed_remains_false": {
            "status": "pass" if not bool(daily_report.get("real_money_allowed")) else "fail",
        },
        "paper_runtime_allowed_remains_true": {
            "status": "pass" if bool(daily_report.get("paper_runtime_allowed")) else "fail",
        },
        "ssl_verify_remains_true": {
            "status": "pass" if bool(daily_report.get("ssl_verify")) else "fail",
        },
        "heartbeat_healthy": {
            "status": "pass" if heartbeat_health == "healthy" else "warn",
            "heartbeat_status": heartbeat_health,
        },
        "no_stale_artifacts": {
            "status": "pass" if not stale_artifacts else "warn",
            "stale_or_missing_artifacts": stale_artifacts,
        },
        "no_state_contamination": {
            "status": "pass" if contamination.get("passed") else "fail",
            **contamination,
        },
        "restarts_are_safe": {
            "status": "pass" if event_records else "unknown",
            "restart_count": int(len(event_records)),
            "successful_restore_count": int(successful_restore_count),
        },
        "no_backtest_holdout_trades_imported": {
            "status": "pass" if contamination.get("passed") else "fail",
            "restored_state_path": contamination.get("restored_state_path"),
        },
        "h6_routes_zero_trades": {
            "status": "pass" if h6_zero else "fail",
            "route_counts": h6_route_counts,
        },
        "h1_short_override_active": {
            "status": "pass" if bool(daily_report.get("h1_short_override_active")) else "fail",
        },
        "active_sleeves_match_validated_stack": {
            "status": "pass" if sleeve_match.get("passed") else "fail",
            **sleeve_match,
        },
        "paper_drawdown_acceptable": {
            "status": "pass" if drawdown_acceptable else "warn",
            "max_paper_drawdown_fraction": max_drawdown,
            "acceptable_threshold_fraction": 0.10,
        },
        "paper_pnl_not_materially_worse_than_expectation": {
            "status": "pass" if pnl_proxy_ok else "warn",
            "current_equity": current_equity,
            "paper_start_equity": float(soak_status.get("paper_start_equity", current_equity) or current_equity),
            "proxy_floor_fraction": -0.02,
        },
        "holdout_thin_warning_acknowledged": {
            "status": "warn" if bool(readiness.get("holdout_is_thin", True)) else "pass",
        },
    }
    soak_review_status = _paper_soak_review_status(
        criteria=criteria,
        soak_days_completed=soak_days_completed,
        required_days=minimum_days,
    )
    return {
        "review_generated_at_utc": _utc_now_timestamp(),
        "classification": soak_status.get("classification"),
        "paper_runtime_allowed": bool(soak_status.get("paper_runtime_allowed")),
        "real_money_allowed": False,
        "ssl_verify": bool(soak_status.get("ssl_verify")),
        "validated_boundary": soak_status.get("validated_boundary"),
        "runtime_started_at": soak_status.get("runtime_started_at") or startup_report.get("runtime_start_timestamp"),
        "runtime_last_processed_timestamp": soak_status.get("runtime_last_processed_timestamp"),
        "soak_days_completed": float(round(soak_days_completed, 4)),
        "required_soak_days": int(minimum_days),
        "runtime_uptime_seconds": uptime_seconds,
        "heartbeat_health": heartbeat_health,
        "stale_warning_count": int(len(list(daily_report.get("stale_warnings") or []))),
        "blocker_count": int(len(list(daily_report.get("blocker_list") or []))),
        "restart_count": int(len(event_records)),
        "successful_restore_count": int(successful_restore_count),
        "state_contamination_check": contamination,
        "open_positions_count": int(daily_report.get("open_positions", 0) or 0),
        "active_sleeves": list(daily_report.get("active_sleeves") or []),
        "disabled_sleeves": list(daily_report.get("disabled_sleeves") or []),
        "h1_short_override_status": bool(daily_report.get("h1_short_override_active")),
        "h6_disabled_status": bool(daily_report.get("h6_disabled_status")) and h6_zero,
        "current_paper_equity": current_equity,
        "realized_pnl_since_paper_start": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "max_paper_drawdown_fraction": max_drawdown,
        "daily_pnl_summary": daily_pnl_summary,
        "daily_trade_count_summary": daily_trade_count_summary,
        "strategy_level_evidence": dict(daily_report.get("strategy_daily_evidence") or {}),
        "allocator_rejection_evidence": {
            "latest_allocator_rejection_counts": dict(daily_report.get("allocator_rejection_counts") or {}),
            "allocator_decision_counts": dict(daily_report.get("allocator_decision_counts") or {}),
        },
        "warning_list": list(daily_report.get("warning_list") or []),
        "blocker_list": list(daily_report.get("blocker_list") or []),
        "restored_state_used": bool(daily_report.get("restored_state_used")),
        "restored_positions_count": int(daily_report.get("restored_positions_count", 0) or 0),
        "portfolio_status_snapshot": {
            "equity": portfolio_status.get("equity"),
            "open_positions": portfolio_status.get("open_positions"),
            "top_symbols": portfolio_status.get("top_symbols"),
        },
        "runtime_state_snapshot": {
            "open_positions_count": int(len(list(runtime_state.get("open_positions") or []))),
            "runtime_last_processed_timestamp": (
                runtime_state.get("runtime_context", {}) or {}
            ).get("runtime_last_processed_timestamp"),
        },
        "artifact_health": artifact_health,
        "soak_review_criteria": criteria,
        "soak_review_status": soak_review_status,
        "window_policy": "forward_paper_evidence_only",
    }


def _write_paper_soak_review(config, payload):
    report_path = _paper_soak_review_path(config)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return report_path


def _append_paper_soak_review_history(config, payload):
    history_path = _paper_soak_review_history_path(config)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    compact_payload = {
        "timestamp": payload.get("review_generated_at_utc"),
        "soak_days_completed": payload.get("soak_days_completed"),
        "current_equity": payload.get("current_paper_equity"),
        "realized_pnl": payload.get("realized_pnl_since_paper_start"),
        "drawdown_fraction": payload.get("max_paper_drawdown_fraction"),
        "blockers": payload.get("blocker_list"),
        "warnings": payload.get("warning_list"),
        "soak_review_status": payload.get("soak_review_status"),
    }
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(compact_payload, default=str) + "\n")
    return history_path


def _promotion_criteria_report(
    *,
    readiness,
    startup_report,
    soak_status,
    daily_report,
    event_log_path,
):
    uptime_seconds = float(soak_status.get("runtime_uptime_seconds", 0.0) or 0.0)
    completed_days = uptime_seconds / 86400.0
    warning_list = list(soak_status.get("warning_list") or [])
    blocker_list = list(soak_status.get("blocker_list") or [])
    current_equity = float(soak_status.get("current_paper_equity", 0.0) or 0.0)
    start_equity = float(soak_status.get("paper_start_equity", 0.0) or 0.0)
    equity_floor = start_equity * 0.95 if start_equity > 0.0 else 0.0
    restored_state_path = str(startup_report.get("restored_state_path") or "")
    latest_event = _read_latest_jsonl_event(event_log_path)
    no_state_contamination = (
        not restored_state_path
        or (
            "portfolio_runtime_state.json" in restored_state_path
            and "backtest" not in restored_state_path.lower()
            and "holdout" not in restored_state_path.lower()
        )
    )
    criteria = {
        "minimum_soak_days_completed": {
            "status": "pass" if completed_days >= PAPER_SOAK_MIN_DAYS else "pending",
            "required_days": PAPER_SOAK_MIN_DAYS,
            "completed_days": float(round(completed_days, 4)),
        },
        "no_operational_blockers": {
            "status": "pass" if not blocker_list else "warn",
            "blocker_count": len(blocker_list),
        },
        "no_stale_heartbeat": {
            "status": "pass" if not any("stale" in str(item).lower() for item in warning_list) else "warn",
            "warnings": [item for item in warning_list if "stale" in str(item).lower()],
        },
        "successful_restart_evidence": {
            "status": "pass" if latest_event else "pending",
            "event_log_path": str(event_log_path),
            "latest_startup_time": latest_event.get("startup_time"),
        },
        "no_state_contamination": {
            "status": "pass" if no_state_contamination else "warn",
            "restored_state_path": restored_state_path or None,
        },
        "paper_runtime_stable": {
            "status": "pass" if not blocker_list and not any("stale" in str(item).lower() for item in warning_list) else "warn",
        },
        "h6_disabled_as_expected": {
            "status": "pass" if bool(soak_status.get("h6_routes_zero_trades_expected")) else "warn",
        },
        "h1_short_override_active_as_expected": {
            "status": "pass" if bool(soak_status.get("h1_short_override_active")) else "warn",
        },
        "paper_pnl_and_drawdown_acceptable": {
            "status": (
                "pass"
                if current_equity >= equity_floor and int(daily_report.get("daily_loss_streak", 0) or 0) < 5
                else "warn"
            ),
            "current_equity": current_equity,
            "equity_floor_proxy": float(equity_floor),
            "daily_loss_streak": int(daily_report.get("daily_loss_streak", 0) or 0),
            "note": "Runtime does not publish a full drawdown series here; equity-vs-start proxy is used for operator reporting only.",
        },
        "holdout_thin_warning_acknowledged": {
            "status": "warn" if bool(readiness.get("holdout_is_thin", True)) else "pass",
        },
    }
    return {
        "promotion_status": "paper_soak_in_progress",
        "real_money_allowed": False,
        "criteria": criteria,
    }


def _build_paper_soak_daily_report(
    *,
    readiness,
    portfolio,
    soak_status,
    startup_report,
    latest_prices,
    selection_summary,
    event_log_path,
):
    current_equity = float(soak_status.get("current_paper_equity", 0.0) or 0.0)
    start_equity = float(soak_status.get("paper_start_equity", 0.0) or 0.0)
    total_return = ((current_equity / start_equity) - 1.0) if start_equity > 0.0 else 0.0
    strategy_daily_evidence = _strategy_daily_evidence(portfolio, latest_prices)
    report = {
        "report_generated_at_utc": _utc_now_timestamp(),
        "classification": soak_status.get("classification"),
        "paper_runtime_allowed": bool(soak_status.get("paper_runtime_allowed")),
        "real_money_allowed": False,
        "ssl_verify": bool(soak_status.get("ssl_verify")),
        "validated_boundary": soak_status.get("validated_boundary"),
        "paper_runtime_started_at": soak_status.get("runtime_started_at"),
        "runtime_last_processed_timestamp": soak_status.get("runtime_last_processed_timestamp"),
        "uptime_seconds": float(soak_status.get("runtime_uptime_seconds", 0.0) or 0.0),
        "heartbeat_status": "stale" if any("stale" in str(item).lower() for item in list(soak_status.get("warning_list") or [])) else "healthy",
        "stale_warnings": [item for item in list(soak_status.get("warning_list") or []) if "stale" in str(item).lower()],
        "current_paper_equity": current_equity,
        "realized_pnl_since_paper_start": float(soak_status.get("realized_paper_pnl_since_runtime_start", 0.0) or 0.0),
        "unrealized_pnl": float(soak_status.get("unrealized_paper_pnl", 0.0) or 0.0),
        "total_paper_return": float(total_return),
        "daily_pnl": float(soak_status.get("daily_closed_pnl", 0.0) or 0.0),
        "daily_entries": int(soak_status.get("daily_entries", 0) or 0),
        "daily_closed_trades": int(soak_status.get("daily_closed_trades", 0) or 0),
        "daily_loss_streak": int(getattr(portfolio, "daily_loss_streak", 0) or 0),
        "open_positions": int(soak_status.get("open_positions_count", 0) or 0),
        "restored_state_used": bool(soak_status.get("restored_state_used")),
        "restored_positions_count": int(soak_status.get("restored_positions_count", 0) or 0),
        "active_sleeves": list(soak_status.get("active_sleeves") or []),
        "disabled_sleeves": list(soak_status.get("disabled_sleeves") or []),
        "h1_short_override_active": bool(soak_status.get("h1_short_override_active")),
        "h6_disabled_status": bool(soak_status.get("h6_routes_zero_trades_expected")),
        "h6_route_counts": {
            "h6_standard": int(dict(getattr(portfolio, "strategy_stats", {}) or {}).get("h6_standard", {}).get("count", 0) or 0),
            "h6_moonshot": int(dict(getattr(portfolio, "strategy_stats", {}) or {}).get("h6_moonshot", {}).get("count", 0) or 0),
        },
        "blocker_list": list(soak_status.get("blocker_list") or []),
        "warning_list": list(soak_status.get("warning_list") or []),
        "allocator_decision_counts": _allocator_decision_counts(selection_summary),
        "allocator_rejection_counts": dict(soak_status.get("latest_allocator_rejection_counts") or {}),
        "strategy_daily_evidence": strategy_daily_evidence,
        "recent_rejection_counts_by_strategy": {
            strategy_type: dict(values or {})
            for strategy_type, values in dict(
                getattr(portfolio, "recent_selection_reason_counts_by_strategy", {}) or {}
            ).items()
        },
        "startup_report_summary": {
            "runtime_mode": startup_report.get("runtime_mode"),
            "runtime_start_timestamp": startup_report.get("runtime_start_timestamp"),
            "restored_state_path": startup_report.get("restored_state_path"),
            "restored_positions_count": startup_report.get("restored_positions_count"),
        },
        "last_runtime_event": _read_latest_jsonl_event(event_log_path),
    }
    report["promotion_criteria"] = _promotion_criteria_report(
        readiness=readiness,
        startup_report=startup_report,
        soak_status=soak_status,
        daily_report=report,
        event_log_path=event_log_path,
    )
    return report


def _write_paper_soak_daily_report(config, payload):
    report_path = _paper_soak_daily_report_path(config)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return report_path


def _runtime_lag_warning_seconds(poll_seconds):
    return max(300.0, (float(poll_seconds) * 4.0) + 120.0)


def _build_paper_soak_warnings(
    *,
    readiness,
    runtime_last_processed_timestamp,
    heartbeat_timestamp,
    poll_seconds,
    runtime_boundary_lag_seconds,
):
    warnings = list(readiness.get("warnings") or [])
    threshold = _runtime_lag_warning_seconds(poll_seconds)
    if runtime_last_processed_timestamp:
        now_closed = pd.Timestamp.now("UTC").floor("min") - pd.Timedelta(minutes=1)
        runtime_ts = pd.Timestamp(runtime_last_processed_timestamp)
        if runtime_ts.tzinfo is None:
            runtime_ts = runtime_ts.tz_localize("UTC")
        else:
            runtime_ts = runtime_ts.tz_convert("UTC")
        lag_seconds = max(0.0, float((now_closed - runtime_ts).total_seconds()))
        if lag_seconds > threshold:
            warnings.append(
                "runtime_last_processed_timestamp_stale:"
                f"{int(lag_seconds)}s>{int(threshold)}s"
            )
    if heartbeat_timestamp:
        heartbeat_ts = pd.Timestamp(heartbeat_timestamp)
        if heartbeat_ts.tzinfo is None:
            heartbeat_ts = heartbeat_ts.tz_localize("UTC")
        else:
            heartbeat_ts = heartbeat_ts.tz_convert("UTC")
        heartbeat_lag = max(
            0.0,
            float((_utc_now_ts() - heartbeat_ts).total_seconds()),
        )
        if heartbeat_lag > threshold:
            warnings.append(
                "engine_heartbeat_stale:"
                f"{int(heartbeat_lag)}s>{int(threshold)}s"
            )
    if runtime_boundary_lag_seconds is not None and float(runtime_boundary_lag_seconds) > threshold:
        warnings.append(
            "runtime_boundary_behind_expected_closed_candle:"
            f"{int(float(runtime_boundary_lag_seconds))}s>{int(threshold)}s"
        )
    return list(dict.fromkeys(warnings))


def _runtime_boundary_lag_seconds(runtime_last_processed_timestamp):
    if not runtime_last_processed_timestamp:
        return None
    now_closed = pd.Timestamp.now("UTC").floor("min") - pd.Timedelta(minutes=1)
    runtime_ts = pd.Timestamp(runtime_last_processed_timestamp)
    if runtime_ts.tzinfo is None:
        runtime_ts = runtime_ts.tz_localize("UTC")
    else:
        runtime_ts = runtime_ts.tz_convert("UTC")
    return max(0.0, float((now_closed - runtime_ts).total_seconds()))


def _build_paper_soak_status(
    *,
    readiness,
    portfolio,
    runtime_started_at,
    runtime_last_processed_timestamp,
    restored_state_used,
    restored_positions_count,
    latest_prices,
    selection_summary,
    heartbeat_payload,
    runtime_start_equity,
):
    runtime_config = dict(readiness.get("runtime_config", {}) or {})
    current_equity = float(getattr(getattr(portfolio, "account", None), "equity", 0.0) or 0.0)
    unrealized_pnl = _portfolio_unrealized_pnl(portfolio, latest_prices)
    runtime_uptime_seconds = max(
        0.0,
        float(
            (
                _utc_now_ts()
                - pd.Timestamp(runtime_started_at)
            ).total_seconds()
        ),
    )
    heartbeat_timestamp = (
        heartbeat_payload.get("last_heartbeat_timestamp")
        or heartbeat_payload.get("cycle_completed_at")
    )
    boundary_lag = _runtime_boundary_lag_seconds(runtime_last_processed_timestamp)
    warnings = _build_paper_soak_warnings(
        readiness=readiness,
        runtime_last_processed_timestamp=runtime_last_processed_timestamp,
        heartbeat_timestamp=heartbeat_timestamp,
        poll_seconds=float(heartbeat_payload.get("poll_seconds", 0.0) or 0.0),
        runtime_boundary_lag_seconds=boundary_lag,
    )
    return {
        "classification": readiness.get("classification"),
        "paper_runtime_allowed": bool(readiness.get("paper_runtime_allowed")),
        "real_money_allowed": bool(readiness.get("real_money_allowed")),
        "ssl_verify": bool(readiness.get("tls", {}).get("ssl_verify")),
        "validated_boundary": readiness.get("validated_boundary"),
        "runtime_started_at": runtime_started_at,
        "runtime_last_processed_timestamp": runtime_last_processed_timestamp,
        "runtime_uptime_seconds": float(runtime_uptime_seconds),
        "restored_state_used": bool(restored_state_used),
        "restored_positions_count": int(restored_positions_count),
        "open_positions_count": int(len(getattr(portfolio, "open_positions", []) or [])),
        "active_sleeves": list(runtime_config.get("active_sleeves", [])),
        "disabled_sleeves": list(runtime_config.get("disabled_sleeves", [])),
        "allowed_sides": list(runtime_config.get("allowed_sides", [])),
        "strategy_allowed_sides": dict(runtime_config.get("strategy_allowed_sides", {}) or {}),
        "current_paper_equity": current_equity,
        "paper_start_equity": float(runtime_start_equity),
        "realized_paper_pnl_since_runtime_start": float(current_equity - float(runtime_start_equity)),
        "unrealized_paper_pnl": float(unrealized_pnl),
        "daily_entries": int(getattr(portfolio, "daily_entries_taken", 0) or 0),
        "daily_closed_trades": int(getattr(portfolio, "daily_closed_trades", 0) or 0),
        "daily_closed_pnl": float(getattr(portfolio, "daily_closed_pnl", 0.0) or 0.0),
        "latest_allocator_rejection_counts": _latest_allocator_rejection_counts(selection_summary),
        "latest_strategy_level_trade_counts": _strategy_trade_counts(portfolio),
        "latest_strategy_level_pnl": _strategy_trade_pnl(portfolio),
        "strategy_open_positions_by_type": _strategy_open_positions_by_type(portfolio),
        "last_heartbeat_timestamp": heartbeat_timestamp,
        "runtime_boundary_lag_seconds": boundary_lag,
        "warning_list": warnings,
        "blocker_list": list(readiness.get("blockers") or []),
        "h1_short_override_active": (
            list(runtime_config.get("strategy_allowed_sides", {}).get("h1_execution", [])) == ["short"]
        ),
        "h6_routes_zero_trades_expected": (
            "h6_standard" in list(runtime_config.get("disabled_sleeves", []))
            and "h6_moonshot" in list(runtime_config.get("disabled_sleeves", []))
        ),
        "heartbeat": dict(heartbeat_payload or {}),
        "generated_at_utc": _utc_now_timestamp(),
    }


def _write_paper_soak_status(config, payload):
    status_path = _paper_soak_status_path(config)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return status_path


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
    df_1m, source_path, _ = _load_live_bootstrap_history_with_metadata(
        symbol=symbol,
        interval=interval,
        warmup_minutes=warmup_minutes,
        config=config,
    )
    return df_1m, source_path


def _load_live_bootstrap_history_with_metadata(symbol, interval, warmup_minutes, config):
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

    canonical_df = load_from_csv(source_path)
    canonical_last_timestamp = None if canonical_df.empty else canonical_df.index.max()
    df_1m = _trim_live_window(canonical_df, warmup_minutes)
    runtime_path = _runtime_state_path(symbol, interval, config)
    metadata = {
        "symbol": str(symbol).upper(),
        "interval": interval,
        "canonical_history_path": str(source_path),
        "canonical_history_last_timestamp": _timestamp_to_utc_iso(canonical_last_timestamp),
        "bootstrap_source_path": str(source_path),
        "runtime_state_used": False,
        "runtime_state_path": str(runtime_path),
        "runtime_state_last_timestamp": None,
        "state_rows_after_bootstrap": int(len(df_1m)),
    }
    if runtime_path.exists():
        runtime_df = _recover_runtime_state_csv(runtime_path, config)
        if runtime_df is not None:
            runtime_last_timestamp = None if runtime_df.empty else runtime_df.index.max()
            df_1m = _merge_recent_into_state(df_1m, runtime_df, warmup_minutes)
            metadata.update(
                {
                    "bootstrap_source_path": str(runtime_path),
                    "runtime_state_used": True,
                    "runtime_state_last_timestamp": _timestamp_to_utc_iso(runtime_last_timestamp),
                    "state_rows_after_bootstrap": int(len(df_1m)),
                }
            )
            return df_1m, runtime_path, metadata
    return df_1m, source_path, metadata


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
    df_1m_state, _ = _catch_up_live_state_with_metadata(
        symbol=symbol,
        interval=interval,
        df_1m_state=df_1m_state,
        warmup_minutes=warmup_minutes,
        config=config,
        client=client,
    )
    return df_1m_state


def _catch_up_live_state_with_metadata(
    symbol,
    interval,
    df_1m_state,
    warmup_minutes,
    config,
    *,
    client=None,
):
    latest_ms = _frame_end_utc_ms(df_1m_state)
    if latest_ms is None:
        return df_1m_state, {
            "symbol": str(symbol).upper(),
            "catchup_applied": False,
            "fresh_closed_rows_added": 0,
            "runtime_first_processed_candle": None,
            "runtime_last_processed_candle": None,
        }

    catchup_end = pd.Timestamp.now("UTC").floor("min") - pd.Timedelta(minutes=1)
    catchup_end_ms = int(catchup_end.timestamp() * 1000)
    if latest_ms >= catchup_end_ms:
        latest_timestamp = _timestamp_to_utc_iso(pd.Timestamp(latest_ms, unit="ms", tz="UTC"))
        return df_1m_state, {
            "symbol": str(symbol).upper(),
            "catchup_applied": False,
            "fresh_closed_rows_added": 0,
            "runtime_first_processed_candle": latest_timestamp,
            "runtime_last_processed_candle": latest_timestamp,
        }

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
        latest_timestamp = _timestamp_to_utc_iso(pd.Timestamp(latest_ms, unit="ms", tz="UTC"))
        return df_1m_state, {
            "symbol": str(symbol).upper(),
            "catchup_applied": False,
            "fresh_closed_rows_added": 0,
            "runtime_first_processed_candle": latest_timestamp,
            "runtime_last_processed_candle": latest_timestamp,
        }

    merged = _merge_recent_into_state(df_1m_state, catchup, warmup_minutes)
    return merged, {
        "symbol": str(symbol).upper(),
        "catchup_applied": True,
        "fresh_closed_rows_added": int(len(catchup)),
        "runtime_first_processed_candle": _timestamp_to_utc_iso(catchup.index.min()),
        "runtime_last_processed_candle": _timestamp_to_utc_iso(catchup.index.max()),
    }


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
        "last_heartbeat_timestamp": _timestamp_to_utc_iso(cycle_completed_at),
        "cycle_duration_seconds": float(cycle_duration_seconds),
        "poll_seconds": float(poll_seconds),
        "symbol_count": int(len(symbols)),
        "symbols_with_recent_fetch": int(sum(1 for count in recent_row_counts.values() if count > 0)),
        "total_recent_1m_rows": int(sum(recent_row_counts.values())),
        "total_state_1m_rows": int(sum(len(frame) for frame in states.values())),
        "latest_recent_1m_timestamp": latest_recent_timestamp,
        "runtime_last_processed_timestamp": _latest_runtime_boundary(states),
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
    readiness = build_runtime_readiness(config, mode="portfolio_paper")
    runtime_start_timestamp = _utc_now_timestamp()
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
    print(
        "Validation boundary: "
        f"{readiness.get('validated_boundary') or 'unknown'} | "
        f"classification: {readiness.get('classification')}"
    )
    for warning in list(readiness.get("warnings") or []):
        print(f"Readiness warning: {warning}")

    states = {}
    binance_client = BinanceClient(config=config)
    persisted_state_timestamps = {}
    bootstrap_metadata_by_symbol = {}
    catchup_metadata_by_symbol = {}
    for symbol in symbols:
        df_1m_state, source_path, bootstrap_metadata = _load_live_bootstrap_history_with_metadata(
            symbol=symbol,
            interval=interval,
            warmup_minutes=warmup_minutes,
            config=config,
        )
        df_1m_state, catchup_metadata = _catch_up_live_state_with_metadata(
            symbol=symbol,
            interval=interval,
            df_1m_state=df_1m_state,
            warmup_minutes=warmup_minutes,
            config=config,
            client=binance_client,
        )
        states[symbol] = df_1m_state
        bootstrap_metadata_by_symbol[symbol] = bootstrap_metadata
        catchup_metadata_by_symbol[symbol] = catchup_metadata
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
    snapshot_payload, snapshot_path = _load_live_portfolio_snapshot(config)
    restored_positions = 0
    restored_from_state = False
    restored_runtime_boundary = _snapshot_runtime_last_processed(snapshot_payload)
    if snapshot_payload:
        portfolio.restore_state(snapshot_payload)
        restored_positions = int(len(portfolio.open_positions))
        restored_from_state = restored_positions > 0 or bool(snapshot_payload)
    restore_summary = _restored_state_summary(portfolio)
    runtime_boundary = _latest_runtime_boundary(states)
    fresh_runtime_timestamps = [
        value.get("runtime_first_processed_candle")
        for value in catchup_metadata_by_symbol.values()
        if value.get("runtime_first_processed_candle")
    ]
    runtime_first_processed_candle = min(fresh_runtime_timestamps) if fresh_runtime_timestamps else None
    runtime_start_equity = float(getattr(portfolio.account, "equity", 0.0) or 0.0)
    portfolio.set_runtime_context(
        mode="portfolio_paper",
        readiness=dict(readiness),
        validation_boundary=readiness.get("validated_boundary"),
        runtime_start_timestamp=runtime_start_timestamp,
        runtime_first_processed_candle=runtime_first_processed_candle,
        runtime_last_processed_timestamp=runtime_boundary,
        restored_from_live_state=restored_from_state,
        restored_position_count=restored_positions,
        restored_lineage_count=int(restore_summary.get("restored_lineage_count", 0)),
        restored_allocator_stats=dict(restore_summary.get("restored_allocator_stats") or {}),
        restored_daily_controls=dict(restore_summary.get("restored_daily_controls") or {}),
        restored_state_path=str(snapshot_path),
        paper_runtime_allowed=bool(readiness.get("paper_runtime_allowed")),
        real_money_allowed=bool(readiness.get("real_money_allowed")),
        active_sleeves=list(readiness.get("runtime_config", {}).get("active_sleeves", [])),
        disabled_sleeves=list(readiness.get("runtime_config", {}).get("disabled_sleeves", [])),
        ssl_verify=bool(readiness.get("tls", {}).get("ssl_verify")),
    )
    print(
        "Live-paper portfolio restore: "
        f"restored={restored_from_state} | positions={restored_positions} | "
        f"state_path={snapshot_path}"
    )
    print(
        "Restore detail: "
        f"lineage={restore_summary.get('restored_lineage_count', 0)} | "
        f"allocator_stats={restore_summary.get('restored_allocator_stats')} | "
        f"daily_controls={restore_summary.get('restored_daily_controls')}"
    )
    print(f"Runtime last processed timestamp: {runtime_boundary or 'unknown'}")
    portfolio.flush_state()
    startup_report = _build_paper_runtime_startup_report(
        config=config,
        readiness=readiness,
        bootstrap_metadata_by_symbol=bootstrap_metadata_by_symbol,
        catchup_metadata_by_symbol=catchup_metadata_by_symbol,
        restored_state_used=restored_from_state,
        restored_state_path=snapshot_path,
        restore_summary=restore_summary,
        runtime_start_timestamp=runtime_start_timestamp,
        runtime_first_processed_candle=runtime_first_processed_candle,
        runtime_last_processed_candle=runtime_boundary,
    )
    startup_report_path = _write_paper_runtime_startup_report(config, startup_report)
    event_payload = {
        "startup_time": runtime_start_timestamp,
        "restore_happened": bool(restored_from_state),
        "restored_positions_count": int(restored_positions),
        "last_processed_timestamp_before_restore": restored_runtime_boundary,
        "first_processed_timestamp_after_restore": runtime_first_processed_candle,
        "validation_boundary": readiness.get("validated_boundary"),
        "scenario_manifest_paths": dict(readiness.get("scenario_manifest_paths") or {}),
        "startup_report_path": str(startup_report_path),
        "readiness_summary_path": readiness.get("summary_path"),
        "classification": readiness.get("classification"),
        "real_money_allowed": bool(readiness.get("real_money_allowed")),
    }
    event_log_path = _append_paper_runtime_event(config, event_payload)
    print(f"Paper runtime startup report: {startup_report_path}")
    print(f"Paper runtime event log: {event_log_path}")
    initial_soak_status = _build_paper_soak_status(
        readiness=readiness,
        portfolio=portfolio,
        runtime_started_at=runtime_start_timestamp,
        runtime_last_processed_timestamp=runtime_boundary,
        restored_state_used=restored_from_state,
        restored_positions_count=restored_positions,
        latest_prices=_latest_price_by_symbol(states),
        selection_summary={"final_reason_counts": {}},
        heartbeat_payload={
            "poll_seconds": float(poll_seconds),
            "last_heartbeat_timestamp": runtime_start_timestamp,
            "runtime_last_processed_timestamp": runtime_boundary,
        },
        runtime_start_equity=runtime_start_equity,
    )
    initial_soak_status_path = _write_paper_soak_status(config, initial_soak_status)
    initial_daily_report = _build_paper_soak_daily_report(
        readiness=readiness,
        portfolio=portfolio,
        soak_status=initial_soak_status,
        startup_report=startup_report,
        latest_prices=_latest_price_by_symbol(states),
        selection_summary={"final_reason_counts": {}},
        event_log_path=event_log_path,
    )
    initial_daily_report_path = _write_paper_soak_daily_report(config, initial_daily_report)
    initial_soak_review = _build_paper_soak_review(
        config=config,
        readiness=readiness,
        soak_status=initial_soak_status,
        daily_report=initial_daily_report,
        startup_report=startup_report,
        event_log_path=event_log_path,
    )
    initial_soak_review_path = _write_paper_soak_review(config, initial_soak_review)
    initial_soak_review_history_path = _append_paper_soak_review_history(config, initial_soak_review)
    initial_baseline_freeze_snapshot = _build_baseline_freeze_snapshot(
        config=config,
        readiness=readiness,
        startup_report=startup_report,
        daily_report=initial_daily_report,
        soak_review=initial_soak_review,
    )
    initial_baseline_freeze_snapshot_path = _write_baseline_freeze_snapshot(
        config,
        initial_baseline_freeze_snapshot,
    )
    initial_scaffold_inventory_path = write_scaffold_inventory(config, readiness=readiness)
    print(f"Paper soak status: {initial_soak_status_path}")
    print(f"Paper soak daily report: {initial_daily_report_path}")
    print(f"Paper soak review: {initial_soak_review_path}")
    print(f"Paper soak review history: {initial_soak_review_history_path}")
    print(f"Baseline freeze snapshot: {initial_baseline_freeze_snapshot_path}")
    print(f"Capital refactor scaffold inventory: {initial_scaffold_inventory_path}")
    last_candle_times = {symbol: None for symbol in symbols}
    cycle_count = 0

    while True:
        cycle_count += 1
        cycle_start = time.time()
        cycle_started_at = pd.Timestamp.now("UTC")
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
        cycle_completed_at = pd.Timestamp.now("UTC")
        runtime_boundary = _latest_runtime_boundary(states)
        portfolio.set_runtime_context(
            mode="portfolio_paper",
            readiness=dict(readiness),
            validation_boundary=readiness.get("validated_boundary"),
            runtime_start_timestamp=runtime_start_timestamp,
            runtime_first_processed_candle=runtime_first_processed_candle,
            runtime_last_processed_timestamp=runtime_boundary,
            restored_from_live_state=restored_from_state,
            restored_position_count=restored_positions,
            restored_lineage_count=int(restore_summary.get("restored_lineage_count", 0)),
            restored_allocator_stats=dict(restore_summary.get("restored_allocator_stats") or {}),
            restored_daily_controls=dict(restore_summary.get("restored_daily_controls") or {}),
            restored_state_path=str(snapshot_path),
            paper_runtime_allowed=bool(readiness.get("paper_runtime_allowed")),
            real_money_allowed=bool(readiness.get("real_money_allowed")),
            active_sleeves=list(readiness.get("runtime_config", {}).get("active_sleeves", [])),
            disabled_sleeves=list(readiness.get("runtime_config", {}).get("disabled_sleeves", [])),
            ssl_verify=bool(readiness.get("tls", {}).get("ssl_verify")),
        )
        startup_report["runtime_last_processed_candle"] = runtime_boundary
        startup_report["generated_at_utc"] = _utc_now_timestamp()
        _write_paper_runtime_startup_report(config, startup_report)
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
        latest_prices = _latest_price_by_symbol(states)
        soak_status = _build_paper_soak_status(
            readiness=readiness,
            portfolio=portfolio,
            runtime_started_at=runtime_start_timestamp,
            runtime_last_processed_timestamp=runtime_boundary,
            restored_state_used=restored_from_state,
            restored_positions_count=restored_positions,
            latest_prices=latest_prices,
            selection_summary=selection_summary,
            heartbeat_payload=engine_heartbeat,
            runtime_start_equity=runtime_start_equity,
        )
        soak_status_path = _write_paper_soak_status(config, soak_status)
        daily_report = _build_paper_soak_daily_report(
            readiness=readiness,
            portfolio=portfolio,
            soak_status=soak_status,
            startup_report=startup_report,
            latest_prices=latest_prices,
            selection_summary=selection_summary,
            event_log_path=event_log_path,
        )
        daily_report_path = _write_paper_soak_daily_report(config, daily_report)
        soak_review = _build_paper_soak_review(
            config=config,
            readiness=readiness,
            soak_status=soak_status,
            daily_report=daily_report,
            startup_report=startup_report,
            event_log_path=event_log_path,
        )
        soak_review_path = _write_paper_soak_review(config, soak_review)
        soak_review_history_path = _append_paper_soak_review_history(config, soak_review)
        baseline_freeze_snapshot = _build_baseline_freeze_snapshot(
            config=config,
            readiness=readiness,
            startup_report=startup_report,
            daily_report=daily_report,
            soak_review=soak_review,
        )
        baseline_freeze_snapshot_path = _write_baseline_freeze_snapshot(
            config,
            baseline_freeze_snapshot,
        )
        scaffold_inventory_path = write_scaffold_inventory(config, readiness=readiness)
        portfolio.state_logger.write_engine_heartbeat(engine_heartbeat)
        portfolio.state_logger.append_engine_cycle(engine_heartbeat)
        portfolio.state_logger.write_symbol_pipeline_status(symbol_pipeline_rows)
        portfolio.flush_state()
        print(f"\nPortfolio cycle completed in {cycle_time:.2f}s")
        print(f"Paper soak daily report: {daily_report_path}")
        print(f"Paper soak review: {soak_review_path}")
        print(f"Paper soak review history: {soak_review_history_path}")
        print(f"Baseline freeze snapshot: {baseline_freeze_snapshot_path}")
        print(f"Capital refactor scaffold inventory: {scaffold_inventory_path}")
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
    normalized_mode = str(mode).lower()
    if normalized_mode in {"portfolio_live", "live_capital", "real_money"}:
        build_runtime_readiness(config, mode=normalized_mode)
        raise RuntimeError(
            "Real-money execution mode is intentionally disabled in this repository."
        )
    if normalized_mode == "portfolio_paper":
        return _run_portfolio_live_paper_sim(config=config)
    return _run_single_symbol_live_sim(symbol=symbol, config=config)


if __name__ == "__main__":
    run_live_sim()
