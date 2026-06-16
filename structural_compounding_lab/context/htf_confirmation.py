from __future__ import annotations

from typing import Any

import pandas as pd

from .trend_regime import classify_trend_regime


def _latest_row_at_or_before(frame: pd.DataFrame, timestamp: pd.Timestamp) -> pd.Series | None:
    if frame.empty:
        return None
    subset = frame.loc[frame.index <= timestamp]
    if subset.empty:
        return None
    return subset.iloc[-1]


def build_htf_context(
    timeframe_bundle: dict[str, pd.DataFrame],
    timestamp: pd.Timestamp,
) -> dict[str, Any]:
    context: dict[str, Any] = {"timestamp": timestamp.isoformat()}
    score = 0.0
    votes: list[str] = []
    for timeframe in ("12h", "1d", "1w"):
        frame = timeframe_bundle.get(timeframe)
        row = _latest_row_at_or_before(frame, timestamp) if frame is not None else None
        if row is None:
            context[f"{timeframe}_trend"] = "unknown"
            continue
        trend = classify_trend_regime(row)
        context[f"{timeframe}_trend"] = trend
        votes.append(trend)
        if trend == "bullish":
            score += 1.0
        elif trend == "bearish":
            score -= 1.0
    bias = "neutral"
    if score >= 1.5:
        bias = "bullish"
    elif score <= -1.5:
        bias = "bearish"
    context["bias"] = bias
    context["score"] = score
    context["votes"] = votes
    return context
