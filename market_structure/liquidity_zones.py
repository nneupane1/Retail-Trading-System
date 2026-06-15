from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Iterable, Sequence

import pandas as pd

from .support_resistance import SupportResistanceKind, detect_pivot_levels


class LiquidityZoneKind(StrEnum):
    LIQUIDITY_HIGH = "liquidity_high"
    LIQUIDITY_LOW = "liquidity_low"
    EQUAL_HIGHS = "equal_highs"
    EQUAL_LOWS = "equal_lows"
    SWEEP_HIGH = "sweep_high"
    SWEEP_LOW = "sweep_low"
    STOP_HUNT_ZONE = "stop_hunt_zone"
    FAILED_BREAKOUT = "failed_breakout"
    FAILED_BREAKDOWN = "failed_breakdown"
    RETEST_ZONE = "retest_zone"
    LIQUIDITY_POOL = "liquidity_pool"


@dataclass(frozen=True)
class LiquidityZone:
    kind: LiquidityZoneKind
    price: float
    anchor_timestamp: str
    timeframe_source: str
    touch_count: int = 1
    strength_score: float | None = None
    display_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_equal_highs_lows(
    candles: Sequence[dict[str, Any]] | pd.DataFrame | Iterable[dict[str, Any]],
    *,
    cutoff_timestamp: Any = None,
    timeframe_source: str = "unknown",
    tolerance_pct: float = 0.001,
) -> list[LiquidityZone]:
    pivots = detect_pivot_levels(
        candles,
        left_bars=1,
        right_bars=1,
        cutoff_timestamp=cutoff_timestamp,
        timeframe_source=timeframe_source,
    )
    zones: list[LiquidityZone] = []
    swing_highs = [level for level in pivots if level.kind == SupportResistanceKind.SWING_HIGH]
    swing_lows = [level for level in pivots if level.kind == SupportResistanceKind.SWING_LOW]

    for previous, current in zip(swing_highs, swing_highs[1:]):
        tolerance = max(abs(previous.price), abs(current.price)) * tolerance_pct
        if abs(previous.price - current.price) <= tolerance:
            zones.append(
                LiquidityZone(
                    kind=LiquidityZoneKind.EQUAL_HIGHS,
                    price=(previous.price + current.price) / 2.0,
                    anchor_timestamp=current.anchor_timestamp,
                    timeframe_source=timeframe_source,
                    touch_count=2,
                    display_only=True,
                )
            )

    for previous, current in zip(swing_lows, swing_lows[1:]):
        tolerance = max(abs(previous.price), abs(current.price)) * tolerance_pct
        if abs(previous.price - current.price) <= tolerance:
            zones.append(
                LiquidityZone(
                    kind=LiquidityZoneKind.EQUAL_LOWS,
                    price=(previous.price + current.price) / 2.0,
                    anchor_timestamp=current.anchor_timestamp,
                    timeframe_source=timeframe_source,
                    touch_count=2,
                    display_only=True,
                )
            )

    return zones


def detect_liquidity_placeholders(
    candles: Sequence[dict[str, Any]] | pd.DataFrame | Iterable[dict[str, Any]],
    *,
    cutoff_timestamp: Any = None,
    timeframe_source: str = "unknown",
) -> list[LiquidityZone]:
    _ = detect_equal_highs_lows(
        candles,
        cutoff_timestamp=cutoff_timestamp,
        timeframe_source=timeframe_source,
    )
    return []
