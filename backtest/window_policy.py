"""Centralized validation window policies for production-style evaluation gates."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from backtest.portfolio_runner import _discover_portfolio_symbols, _load_full_history
from config import AppConfig


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat_utc_timestamp(value: pd.Timestamp | datetime | None) -> str | None:
    if value is None:
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.isoformat()


@dataclass
class ValidationWindowMetadata:
    window_policy: str
    train_start: str | None
    train_end: str | None
    holdout_start: str | None
    holdout_end: str | None
    latest_data_timestamp: str
    resolved_at_utc: str
    latest_common_end_date: str
    universe_symbols: list[str]
    symbol_latest_timestamps: list[dict[str, str]]

    def to_dict(self) -> dict:
        return asdict(self)


def _normalized_symbols(config: AppConfig, symbols: list[str] | None = None) -> list[str]:
    if symbols:
        return [str(symbol).upper() for symbol in symbols]
    return [str(symbol).upper() for symbol in _discover_portfolio_symbols(config)]


def resolve_latest_common_data_timestamp(
    config: AppConfig,
    *,
    symbols: list[str] | None = None,
    interval: str | None = None,
) -> tuple[pd.Timestamp, list[dict[str, str]]]:
    """Return the latest timestamp common across the supplied universe."""

    interval = interval or str(config.require("binance", "default_interval"))
    universe_symbols = _normalized_symbols(config, symbols)
    symbol_rows: list[dict[str, str]] = []
    latest_timestamps: list[pd.Timestamp] = []

    for symbol in universe_symbols:
        df_1m, source_path = _load_full_history(symbol, interval, config)
        if df_1m.empty:
            raise ValueError(f"No historical 1m rows available for {symbol}.")
        latest_timestamp = pd.Timestamp(df_1m.index.max())
        if latest_timestamp.tzinfo is None:
            latest_timestamp = latest_timestamp.tz_localize("UTC")
        else:
            latest_timestamp = latest_timestamp.tz_convert("UTC")
        latest_timestamps.append(latest_timestamp)
        symbol_rows.append(
            {
                "symbol": symbol,
                "latest_timestamp": latest_timestamp.isoformat(),
                "source_path": str(source_path),
            }
        )

    latest_common = min(latest_timestamps)
    return latest_common, symbol_rows


def resolve_full_history_window(
    config: AppConfig,
    *,
    symbols: list[str] | None = None,
    policy_name: str = "full_history_latest_closed_day_v1",
) -> ValidationWindowMetadata:
    latest_common, symbol_rows = resolve_latest_common_data_timestamp(
        config,
        symbols=symbols,
    )
    latest_common_end_date = str(latest_common.date())
    return ValidationWindowMetadata(
        window_policy=policy_name,
        train_start=str(config.require("history", "start_date")),
        train_end=latest_common_end_date,
        holdout_start=None,
        holdout_end=None,
        latest_data_timestamp=latest_common.isoformat(),
        resolved_at_utc=_utc_now().isoformat(),
        latest_common_end_date=latest_common_end_date,
        universe_symbols=_normalized_symbols(config, symbols),
        symbol_latest_timestamps=symbol_rows,
    )


def resolve_trailing_12m_holdout_window(
    config: AppConfig,
    *,
    symbols: list[str] | None = None,
    policy_name: str = "trailing_12m_unseen_holdout_v1",
) -> ValidationWindowMetadata:
    latest_common, symbol_rows = resolve_latest_common_data_timestamp(
        config,
        symbols=symbols,
    )
    holdout_end_ts = pd.Timestamp(latest_common.date())
    holdout_start_ts = (holdout_end_ts + pd.Timedelta(days=1)) - pd.DateOffset(years=1)
    train_start_ts = pd.Timestamp(str(config.require("history", "start_date")))
    train_end_ts = holdout_start_ts - pd.Timedelta(days=1)
    if train_end_ts < train_start_ts:
        raise ValueError(
            "Trailing 12-month holdout would leave no non-overlapping training window."
        )
    return ValidationWindowMetadata(
        window_policy=policy_name,
        train_start=train_start_ts.strftime("%Y-%m-%d"),
        train_end=train_end_ts.strftime("%Y-%m-%d"),
        holdout_start=holdout_start_ts.strftime("%Y-%m-%d"),
        holdout_end=holdout_end_ts.strftime("%Y-%m-%d"),
        latest_data_timestamp=latest_common.isoformat(),
        resolved_at_utc=_utc_now().isoformat(),
        latest_common_end_date=holdout_end_ts.strftime("%Y-%m-%d"),
        universe_symbols=_normalized_symbols(config, symbols),
        symbol_latest_timestamps=symbol_rows,
    )


def write_validation_window_artifact(target_dir: str | Path, metadata: ValidationWindowMetadata | dict) -> Path:
    payload = metadata.to_dict() if isinstance(metadata, ValidationWindowMetadata) else dict(metadata)
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    path = target / "validation_window.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path
