from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class MarketStructureContext:
    nearest_support: float | None = None
    nearest_resistance: float | None = None
    distance_to_support_pct: float | None = None
    distance_to_resistance_pct: float | None = None
    inside_range: bool = False
    near_range_high: bool = False
    near_range_low: bool = False
    after_breakout: bool = False
    after_breakdown: bool = False
    after_retest: bool = False
    liquidity_sweep_detected: bool = False
    htf_level_nearby: bool = False
    confidence: float | None = None
    source_timeframe: str = "unknown"
    display_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_display_only_context(
    *,
    nearest_support: float | None = None,
    nearest_resistance: float | None = None,
    current_price: float | None = None,
    source_timeframe: str = "unknown",
) -> MarketStructureContext:
    distance_to_support_pct = None
    distance_to_resistance_pct = None
    if current_price and nearest_support is not None:
        distance_to_support_pct = ((current_price - nearest_support) / current_price) * 100.0
    if current_price and nearest_resistance is not None:
        distance_to_resistance_pct = ((nearest_resistance - current_price) / current_price) * 100.0

    return MarketStructureContext(
        nearest_support=nearest_support,
        nearest_resistance=nearest_resistance,
        distance_to_support_pct=distance_to_support_pct,
        distance_to_resistance_pct=distance_to_resistance_pct,
        inside_range=nearest_support is not None and nearest_resistance is not None and current_price is not None and nearest_support <= current_price <= nearest_resistance,
        source_timeframe=source_timeframe,
        display_only=True,
    )

