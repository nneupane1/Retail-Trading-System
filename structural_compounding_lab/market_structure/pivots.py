from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import pandas as pd


def _to_utc_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


@dataclass(frozen=True)
class PivotPoint:
    timestamp: str
    price: float
    side: str
    timeframe_source: str
    left_bars: int
    right_bars: int
    no_future_data: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_pivots(
    frame: pd.DataFrame,
    *,
    left_bars: int = 3,
    right_bars: int = 3,
    cutoff_timestamp: Any = None,
    timeframe_source: str = "unknown",
) -> list[PivotPoint]:
    if frame.empty:
        return []
    working = frame.copy()
    if cutoff_timestamp is not None:
        cutoff = _to_utc_timestamp(cutoff_timestamp)
        index = pd.DatetimeIndex(working.index)
        if index.tz is None:
            index = index.tz_localize("UTC")
        else:
            index = index.tz_convert("UTC")
        working = working.loc[index <= cutoff]
    if len(working) < left_bars + right_bars + 1:
        return []
    rows: list[PivotPoint] = []
    for index in range(left_bars, len(working) - right_bars):
        center = working.iloc[index]
        left = working.iloc[index - left_bars:index]
        right = working.iloc[index + 1:index + 1 + right_bars]
        timestamp = pd.Timestamp(working.index[index])
        if all(center["high"] > row["high"] for _, row in left.iterrows()) and all(center["high"] >= row["high"] for _, row in right.iterrows()):
            rows.append(
                PivotPoint(
                    timestamp=timestamp.isoformat(),
                    price=float(center["high"]),
                    side="high",
                    timeframe_source=timeframe_source,
                    left_bars=left_bars,
                    right_bars=right_bars,
                )
            )
        if all(center["low"] < row["low"] for _, row in left.iterrows()) and all(center["low"] <= row["low"] for _, row in right.iterrows()):
            rows.append(
                PivotPoint(
                    timestamp=timestamp.isoformat(),
                    price=float(center["low"]),
                    side="low",
                    timeframe_source=timeframe_source,
                    left_bars=left_bars,
                    right_bars=right_bars,
                )
            )
    return rows
