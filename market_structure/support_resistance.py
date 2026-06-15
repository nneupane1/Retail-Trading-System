from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Iterable, Sequence

import pandas as pd


class SupportResistanceKind(StrEnum):
    SUPPORT_LEVEL = "support_level"
    RESISTANCE_LEVEL = "resistance_level"
    RANGE_HIGH = "range_high"
    RANGE_LOW = "range_low"
    MIDPOINT = "midpoint"
    SWING_HIGH = "swing_high"
    SWING_LOW = "swing_low"


@dataclass(frozen=True)
class SupportResistanceLevel:
    kind: SupportResistanceKind
    price: float
    anchor_timestamp: str
    timeframe_source: str
    touch_count: int = 1
    strength_score: float | None = None
    display_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SupportResistanceZone:
    kind: SupportResistanceKind
    lower_bound: float
    upper_bound: float
    midpoint: float
    anchor_timestamp: str
    timeframe_source: str
    touch_count: int = 1
    strength_score: float | None = None
    display_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _NormalizedCandle:
    timestamp: pd.Timestamp
    open: float
    high: float
    low: float
    close: float


def _normalize_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _candle_timestamp_from_row(index: Any, row: dict[str, Any]) -> pd.Timestamp:
    for key in ("timestamp", "time", "datetime", "date"):
        if key in row and row[key] not in (None, ""):
            return _normalize_timestamp(row[key])
    return _normalize_timestamp(index)


def _normalize_candles(
    candles: Sequence[dict[str, Any]] | pd.DataFrame | Iterable[dict[str, Any]],
    *,
    cutoff_timestamp: Any = None,
) -> list[_NormalizedCandle]:
    cutoff = _normalize_timestamp(cutoff_timestamp) if cutoff_timestamp is not None else None
    rows: list[_NormalizedCandle] = []
    if isinstance(candles, pd.DataFrame):
        iterable = ((index, row.to_dict()) for index, row in candles.iterrows())
    else:
        iterable = ((row.get("timestamp") or row.get("time") or position, dict(row)) for position, row in enumerate(candles))

    for index, row in iterable:
        timestamp = _candle_timestamp_from_row(index, row)
        if cutoff is not None and timestamp > cutoff:
            continue
        rows.append(
            _NormalizedCandle(
                timestamp=timestamp,
                open=float(row.get("open", 0.0)),
                high=float(row.get("high", 0.0)),
                low=float(row.get("low", 0.0)),
                close=float(row.get("close", 0.0)),
            )
        )
    rows.sort(key=lambda item: item.timestamp)
    return rows


def detect_pivot_levels(
    candles: Sequence[dict[str, Any]] | pd.DataFrame | Iterable[dict[str, Any]],
    *,
    left_bars: int = 2,
    right_bars: int = 2,
    cutoff_timestamp: Any = None,
    timeframe_source: str = "unknown",
) -> list[SupportResistanceLevel]:
    rows = _normalize_candles(candles, cutoff_timestamp=cutoff_timestamp)
    if len(rows) < (left_bars + right_bars + 1):
        return []

    levels: list[SupportResistanceLevel] = []
    for index in range(left_bars, len(rows) - right_bars):
        center = rows[index]
        left = rows[index - left_bars:index]
        right = rows[index + 1:index + 1 + right_bars]

        if all(center.high > row.high for row in left) and all(center.high >= row.high for row in right):
            levels.append(
                SupportResistanceLevel(
                    kind=SupportResistanceKind.SWING_HIGH,
                    price=center.high,
                    anchor_timestamp=center.timestamp.isoformat(),
                    timeframe_source=timeframe_source,
                    display_only=True,
                )
            )

        if all(center.low < row.low for row in left) and all(center.low <= row.low for row in right):
            levels.append(
                SupportResistanceLevel(
                    kind=SupportResistanceKind.SWING_LOW,
                    price=center.low,
                    anchor_timestamp=center.timestamp.isoformat(),
                    timeframe_source=timeframe_source,
                    display_only=True,
                )
            )
    return levels


def build_support_resistance_zones(
    levels: Sequence[SupportResistanceLevel],
    *,
    zone_width_pct: float = 0.0015,
) -> list[SupportResistanceZone]:
    zones: list[SupportResistanceZone] = []
    for level in levels:
        if level.kind not in {
            SupportResistanceKind.SWING_HIGH,
            SupportResistanceKind.SWING_LOW,
            SupportResistanceKind.SUPPORT_LEVEL,
            SupportResistanceKind.RESISTANCE_LEVEL,
        }:
            continue
        half_width = abs(level.price) * zone_width_pct
        zone_kind = (
            SupportResistanceKind.RESISTANCE_LEVEL
            if level.kind == SupportResistanceKind.SWING_HIGH
            else SupportResistanceKind.SUPPORT_LEVEL
            if level.kind == SupportResistanceKind.SWING_LOW
            else level.kind
        )
        zones.append(
            SupportResistanceZone(
                kind=zone_kind,
                lower_bound=level.price - half_width,
                upper_bound=level.price + half_width,
                midpoint=level.price,
                anchor_timestamp=level.anchor_timestamp,
                timeframe_source=level.timeframe_source,
                touch_count=level.touch_count,
                strength_score=level.strength_score,
                display_only=True,
            )
        )
    return zones

